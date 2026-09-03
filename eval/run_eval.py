#!/usr/bin/env python3
"""Evaluation gate for Disputes and Chargebacks Manager (F2).

Two named layers via ``--mode`` (the scaffold is ``agent_eval_kit.eval_main``):

* **smoke** (default) - the offline pre-merge check CI runs on every change. It drives the REAL
  deterministic engines and the SDK-free local adapters against a golden set and scores six
  metrics, each against the dataset's OWN ``expected_*`` label (an independent oracle), never
  against the pipeline's own verdict. Before scoring it PROVES every metric can go red
  (``agent_eval_kit.assert_each_can_go_red``): a metric that cannot fail proves nothing.
* **gate** - the promotion verdict from the shared Hrz4 authority (requires the ``gcp`` profile),
  via ``agent_eval_kit.PromotionGateClient``.

Exit is ``0`` iff every metric meets its threshold (and, in gate mode, the authority agrees).

The consequential numbers and verdicts here (eligibility, abuse band, lifecycle states) come from
pure engines; the model's only scored jobs are the closed-set intake classification and the
grounded narration, so ``groundedness`` rejects any figure the engine did not source and
``pii_safety`` proves the redactor runs before the audit write. Nothing in this file produces a
number a model could have moved.
"""

from __future__ import annotations

import json
import os
import re
from collections.abc import Mapping, Sequence
from dataclasses import dataclass
from pathlib import Path
from typing import Any

from agent_eval_kit import (
    EvalMetricResult,
    EvalReport,
    PromotionGateClient,
    assert_each_can_go_red,
    eval_main,
)
from pii_kit import pack_leak, redact

from disputes_chargebacks_manager.config import (
    Settings,
    build_container,
    build_service,
    load_policy,
)
from disputes_chargebacks_manager.domain.abuse_engine import AbuseEngine
from disputes_chargebacks_manager.domain.eligibility_engine import EligibilityEngine
from disputes_chargebacks_manager.domain.kernel import parse_date
from disputes_chargebacks_manager.domain.models import (
    CustomerHistory,
    Dispute,
    DisputeTrack,
    IntakeCategory,
)
from disputes_chargebacks_manager.domain.pii import PII_PATTERNS
from disputes_chargebacks_manager.domain.state_machine import replay
from disputes_chargebacks_manager.domain.workflows import workflow_for

_REPO_ROOT = Path(__file__).resolve().parent.parent
DEFAULT_DATASET = _REPO_ROOT / "eval" / "datasets" / "golden_cases.jsonl"

#: The per-metric acceptance bars. The deterministic decision metrics are held at 1.0 (any single
#: divergence fails, which is the strictest possible bar, not a weakened one); the classification
#: bar reflects a model that need not be perfect; the two safety metrics tolerate no leak.
THRESHOLDS: dict[str, float] = {
    "eligibility_accuracy": 1.0,
    "abuse_accuracy": 1.0,
    "intake_accuracy": 0.80,
    "lifecycle_trace": 1.0,
    "groundedness": 0.99,
    "pii_safety": 0.99,
}
#: The registered Hrz4 metric bundle for this vertical (Hrz4 owns the metrics + thresholds).
_BUNDLE = "disputes-chargebacks-manager"

#: The CLOSED set the model may classify an intake into (every category except UNKNOWN). A label
#: outside it is coerced to UNKNOWN, exactly as ``DisputeService.intake`` does.
_INTAKE_CATEGORIES: tuple[str, ...] = tuple(
    c.value for c in IntakeCategory if c is not IntakeCategory.UNKNOWN
)

_DIGITS = re.compile(r"\d+")


def _load(path: Path) -> list[dict[str, Any]]:
    cases: list[dict[str, Any]] = []
    for raw in path.read_text(encoding="utf-8").splitlines():
        line = raw.strip()
        if not line or line.startswith("#"):
            continue
        cases.append(json.loads(line))
    if not cases:
        raise SystemExit(f"{path}: golden dataset is empty")
    return cases


def _of_kind(rows: Sequence[Mapping[str, Any]], kind: str) -> list[Mapping[str, Any]]:
    found = [row for row in rows if row.get("kind") == kind]
    if not found:
        raise SystemExit(f"golden dataset has no {kind!r} cases; every metric needs its own")
    return found


def _mean(scores: Sequence[float]) -> float:
    return round(sum(scores) / len(scores), 4) if scores else 0.0


def _figures(text: str) -> set[str]:
    """The set of digit runs in ``text``: the figures a groundedness check compares."""
    return set(_DIGITS.findall(text))


def grounded_score(draft: str, source: str) -> float:
    """1.0 iff every figure in ``draft`` also appears in the engine-sourced ``source`` text.

    A model that invents a number (one absent from the case facts and the cited evidence) drops
    this below 1.0. Pure, so the not-falsely-green proof drives it with a hand-built mutant draft.
    """
    return 1.0 if _figures(draft) <= _figures(source) else 0.0


def pii_clean_score(blob: str, planted: Sequence[str]) -> float:
    """1.0 unless a raw identifier survives ``blob``: the shared pack fires, or a planted literal.

    Two-part, the C4 lesson: the pack scan catches any known pattern, and the planted-literal
    check fires even if a pack row is broken, so the metric cannot be quietly disarmed.
    """
    leaked = pack_leak(blob, PII_PATTERNS) or any(token in blob for token in planted)
    return 0.0 if leaked else 1.0


@dataclass(frozen=True)
class _Harness:
    """The real engines and local adapters the smoke scorers drive, built once per run."""

    eligibility: EligibilityEngine
    abuse: AbuseEngine
    narrator: Any
    service: Any
    audit: Any

    # -- per-case scorers, each against the row's own expected_* label ---------------------- #
    def score_eligibility(self, row: Mapping[str, Any]) -> float:
        outcome = self.eligibility.assess(_dispute_from(row), as_of=parse_date(row["as_of"]))
        return 1.0 if outcome.eligible == bool(row["expected_eligible"]) else 0.0

    def score_abuse(self, row: Mapping[str, Any]) -> float:
        history = CustomerHistory(
            dispute_count_90d=int(row.get("dispute_count_90d", 0)),
            prior_abuse_count=int(row.get("prior_abuse_count", 0)),
            refund_total_minor_90d=int(row.get("refund_total_minor_90d", 0)),
        )
        outcome = self.abuse.assess(_dispute_from(row), history).outcome
        return 1.0 if outcome.value == row["expected_outcome"] else 0.0

    def score_intake(self, row: Mapping[str, Any]) -> float:
        raw = self.narrator.classify(
            redact(row["transcript"], PII_PATTERNS), categories=_INTAKE_CATEGORIES
        )
        category = raw if raw in _INTAKE_CATEGORIES else IntakeCategory.UNKNOWN.value
        return 1.0 if category == row["expected_category"] else 0.0

    def score_lifecycle(self, row: Mapping[str, Any]) -> float:
        workflow = workflow_for(DisputeTrack(row["track"]))
        visited = [state.value for state in replay(workflow, tuple(row["triggers"]))]
        return 1.0 if visited == list(row["expected_states"]) else 0.0

    def score_groundedness(self, row: Mapping[str, Any]) -> float:
        dispute = _dispute_from(row)
        evidence = tuple((doc["id"], doc["text"]) for doc in row.get("evidence", []))
        pack = self.service.draft_representment(dispute, evidence, actor="eval-bot")
        source = " ".join(
            [dispute.id, dispute.reason_code, str(dispute.amount_minor), dispute.currency]
            + [text for _, text in evidence]
        )
        return grounded_score(pack.draft_text, source)

    def score_pii(self, rows: Sequence[Mapping[str, Any]]) -> float:
        """Run the intake pipeline over PII-bearing conversations, then scan every audit record.

        The redactor runs inside the pipeline (before the audit write and before the citation
        snippet is stored); this reads the records back and asserts no planted identifier and no
        known pattern survived either sink.
        """
        for row in rows:
            self.service.intake(row["conversation_ref"], tenant="eval-bank", actor="eval-bot")
        blob = " ".join(json.dumps(record, default=str) for record in self.audit.log.read_all())
        planted = [str(row["planted"]) for row in rows if row.get("planted")]
        return pii_clean_score(blob, planted)


def _dispute_from(row: Mapping[str, Any]) -> Dispute:
    """Build a synthetic :class:`Dispute` from a golden row (fields absent from a kind default)."""
    return Dispute(
        id=str(row.get("dispute_id", "DSP-EVAL")),
        tenant=str(row.get("tenant", "eval-bank")),
        track=DisputeTrack(str(row["track"])),
        reason_code=str(row["reason_code"]),
        amount_minor=int(row.get("amount_minor", 1000)),
        currency=str(row.get("currency", "SGD")),
        transaction_date=parse_date(str(row["transaction_date"])),
        intake_date=parse_date(str(row["intake_date"])),
        product=str(row.get("product", "")),
        market=str(row.get("market", "")),
    )


def _build_harness() -> _Harness:
    """Force the ``local`` profile: the smoke check is offline and must not bind a cloud adapter."""
    packs, abuse_policy = load_policy()
    settings = Settings(
        profile="local",
        audit_path=":memory:",
        tenant="eval-bank",
        reason_code_packs=packs,
        abuse_policy=abuse_policy,
    )
    container = build_container(settings)
    return _Harness(
        eligibility=EligibilityEngine(packs),
        abuse=AbuseEngine(abuse_policy),
        narrator=container.narration,
        service=build_service(container),
        audit=container.audit,
    )


def _prove_metrics_can_go_red(h: _Harness) -> None:
    """Fail the gate unless EACH metric can distinguish a right label from a wrong one.

    The green/red pairs are crafted, not drawn from the dataset: the green case scores at the bar
    and the red case (the SAME scenario carrying a wrong label, or a mutant draft/record) scores
    below it. If a red case still passes, the metric is falsely green and this raises.
    """
    assert_each_can_go_red(
        h.score_eligibility,
        {
            "within_window": (_ELIG_GREEN, {**_ELIG_GREEN, "expected_eligible": False}),
            "past_window": (_ELIG_RED, {**_ELIG_RED, "expected_eligible": True}),
        },
        threshold=THRESHOLDS["eligibility_accuracy"],
        metric="eligibility_accuracy",
    )
    assert_each_can_go_red(
        h.score_abuse,
        {
            "deny": (_ABUSE_DENY, {**_ABUSE_DENY, "expected_outcome": "allow"}),
            "allow": (_ABUSE_ALLOW, {**_ABUSE_ALLOW, "expected_outcome": "deny"}),
        },
        threshold=THRESHOLDS["abuse_accuracy"],
        metric="abuse_accuracy",
    )
    assert_each_can_go_red(
        h.score_intake,
        {
            "card": (_INTAKE_CARD, {**_INTAKE_CARD, "expected_category": "retail_refund"}),
            "unknown": (
                _INTAKE_UNKNOWN,
                {**_INTAKE_UNKNOWN, "expected_category": "card_unauthorised"},
            ),
        },
        threshold=THRESHOLDS["intake_accuracy"],
        metric="intake_accuracy",
    )
    assert_each_can_go_red(
        h.score_lifecycle,
        {
            "card": (_LIFECYCLE_CARD, {**_LIFECYCLE_CARD, "expected_states": _WRONG_STATES}),
            "retail": (_LIFECYCLE_RETAIL, {**_LIFECYCLE_RETAIL, "expected_states": _WRONG_STATES}),
        },
        threshold=THRESHOLDS["lifecycle_trace"],
        metric="lifecycle_trace",
    )
    assert_each_can_go_red(
        lambda pair: grounded_score(*pair),
        {"pack": (("restating 42000 and 9988", "42000 9988 SGD"), ("adds 55555", "42000 9988"))},
        threshold=THRESHOLDS["groundedness"],
        metric="groundedness",
    )
    _raw = "complaint from NRIC S1234567D on file"
    assert_each_can_go_red(
        lambda pair: pii_clean_score(*pair),
        {"nric": ((redact(_raw, PII_PATTERNS), ["S1234567D"]), (_raw, ["S1234567D"]))},
        threshold=THRESHOLDS["pii_safety"],
        metric="pii_safety",
    )


# The crafted proof fixtures (obviously fictional). Kept module-level so the proof reads as data.
_ELIG_GREEN: dict[str, Any] = {
    "track": "card_scheme",
    "reason_code": "10.4",
    "transaction_date": "2025-05-01",
    "intake_date": "2025-05-10",
    "as_of": "2025-06-01",
    "expected_eligible": True,
}
_ELIG_RED: dict[str, Any] = {
    "track": "card_scheme",
    "reason_code": "10.4",
    "transaction_date": "2024-01-01",
    "intake_date": "2025-05-10",
    "as_of": "2025-06-01",
    "expected_eligible": False,
}
_ABUSE_DENY: dict[str, Any] = {
    "track": "retail",
    "reason_code": "R-REFUND",
    "amount_minor": 80000,
    "transaction_date": "2025-05-20",
    "intake_date": "2025-05-25",
    "dispute_count_90d": 9,
    "prior_abuse_count": 1,
    "refund_total_minor_90d": 300000,
    "expected_outcome": "deny",
}
_ABUSE_ALLOW: dict[str, Any] = {
    "track": "retail",
    "reason_code": "R-REFUND",
    "amount_minor": 1500,
    "transaction_date": "2025-05-20",
    "intake_date": "2025-05-25",
    "expected_outcome": "allow",
}
_INTAKE_CARD: dict[str, Any] = {
    "transcript": "I never made this card charge.",
    "expected_category": "card_unauthorised",
}
_INTAKE_UNKNOWN: dict[str, Any] = {
    "transcript": "Just a general question about my balance.",
    "expected_category": "unknown",
}
_LIFECYCLE_CARD: dict[str, Any] = {
    "track": "card_scheme",
    "triggers": ["submit", "ineligible"],
    "expected_states": ["intake", "eligibility_check", "rejected"],
}
_LIFECYCLE_RETAIL: dict[str, Any] = {
    "track": "retail",
    "triggers": ["submit", "eligible", "abuse_confirmed"],
    "expected_states": ["intake", "eligibility_check", "evidence_review", "closed_abuse"],
}
_WRONG_STATES: list[str] = ["intake", "eligibility_check", "evidence_review"]


def run_smoke(dataset: Path) -> EvalReport:
    rows = _load(dataset)
    harness = _build_harness()
    _prove_metrics_can_go_red(harness)

    results = (
        EvalMetricResult.scored(
            "eligibility_accuracy",
            _mean([harness.score_eligibility(r) for r in _of_kind(rows, "eligibility")]),
            THRESHOLDS["eligibility_accuracy"],
        ),
        EvalMetricResult.scored(
            "abuse_accuracy",
            _mean([harness.score_abuse(r) for r in _of_kind(rows, "abuse")]),
            THRESHOLDS["abuse_accuracy"],
        ),
        EvalMetricResult.scored(
            "intake_accuracy",
            _mean([harness.score_intake(r) for r in _of_kind(rows, "intake")]),
            THRESHOLDS["intake_accuracy"],
        ),
        EvalMetricResult.scored(
            "lifecycle_trace",
            _mean([harness.score_lifecycle(r) for r in _of_kind(rows, "lifecycle")]),
            THRESHOLDS["lifecycle_trace"],
        ),
        EvalMetricResult.scored(
            "groundedness",
            _mean([harness.score_groundedness(r) for r in _of_kind(rows, "grounded")]),
            THRESHOLDS["groundedness"],
        ),
        EvalMetricResult.scored(
            "pii_safety",
            harness.score_pii(_of_kind(rows, "pii")),
            THRESHOLDS["pii_safety"],
        ),
    )
    return EvalReport(dataset=str(dataset), results=results, n_examples=len(rows))


def run_gate(dataset: Path) -> tuple[EvalReport, bool]:
    settings = Settings.load()
    if settings.profile != "gcp":
        raise SystemExit(
            "--mode gate is the promotion authority and requires "
            f"DISPUTES_PROFILE=gcp (got {settings.profile!r}); "
            "run --mode smoke for the offline pre-merge check."
        )
    client = PromotionGateClient(
        os.environ.get("DISPUTES_QUALITY_URL", "http://localhost:8084"),
        bundle=_BUNDLE,
        model="gemini-3.5-flash",
    )
    return client.evaluate(str(dataset)), client.gate(str(dataset))


if __name__ == "__main__":
    raise SystemExit(
        eval_main(
            smoke=run_smoke,
            gate=run_gate,
            default_dataset=DEFAULT_DATASET,
            description="Offline / Hrz4 evaluation gate for F2.",
        )
    )
