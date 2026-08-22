"""Tool functions an agent runtime calls: thin, side-effect-honest wrappers on the services.

Design rules, in the order they matter:

* **No business logic here.** The domain service decides HOW; the model only decides WHICH tool
  to call. A rule that lives in a tool wrapper is a rule the CLI and the API do not have.
* **Rule R8 applies on this path too.** A consequential result is ROUTED from inside the service,
  in the same call that produced it, so an agent surface is not a third place an escalation can
  quietly stop.
* **Import-safe without a runtime.** ``google.adk`` is imported lazily inside
  :func:`build_function_tools`, so these callables are importable, testable and runnable with no
  ADK and no cloud SDK installed.
* **Typed and documented.** A runtime derives each tool's name, description and JSON parameter
  schema from the signature and the docstring, so both are part of the contract.
"""

from __future__ import annotations

from typing import TYPE_CHECKING, Any

from hex_service_kit.serialization import to_jsonable
from pii_kit import redact

from ..config import Container, Settings, build_container, build_service
from ..domain.kernel import parse_date
from ..domain.models import CustomerHistory, Dispute, DisputeTrack
from ..domain.pii import PII_PATTERNS

if TYPE_CHECKING:  # pragma: no cover - typing only, never imported at runtime
    from google.adk.tools import FunctionTool

#: The identity a tool call is attributed to when the runtime propagates none. It names the
#: SERVICE, not a person, so an unattributed action is never mistaken for a human's.
DEFAULT_ACTOR = "disputes-chargebacks-manager-agent"


def _container(settings: Settings | None) -> Container:
    return build_container(settings)


def _redacted(node: Any) -> Any:
    """Mask personal data in every string of a tool result, however deeply it is nested (P-04)."""
    if isinstance(node, str):
        return redact(node, PII_PATTERNS)
    if isinstance(node, dict):
        return {key: _redacted(value) for key, value in node.items()}
    if isinstance(node, list):
        return [_redacted(value) for value in node]
    return node


def _as_dict(payload: Any) -> dict[str, Any]:
    result = _redacted(to_jsonable(payload))
    if not isinstance(result, dict):  # pragma: no cover - dataclasses serialise to objects
        raise TypeError("a tool result must serialise to a JSON object")
    return result


def open_dispute(
    dispute_id: str,
    track: str,
    reason_code: str,
    amount_minor: int,
    currency: str,
    transaction_date: str,
    intake_date: str,
    as_of: str,
    actor: str = DEFAULT_ACTOR,
    tenant: str = "",
    settings: Settings | None = None,
) -> dict[str, Any]:
    """Assess eligibility and open a dispute case; an ineligible rejection is routed (rule R8).

    Args:
      dispute_id: The dispute identifier.
      track: ``card_scheme`` or ``retail``.
      reason_code: The scheme or retail reason code.
      amount_minor: The disputed amount in integer minor units.
      currency: The three-letter currency code.
      transaction_date: ISO date of the transaction.
      intake_date: ISO date the dispute was filed.
      as_of: ISO date to assess eligibility as of.
      actor: The verified identity this call is attributed to.
      tenant: Tenant partition asserted on an outbound review.

    Returns:
      A JSON-safe result: the eligibility verdict, the opened case state and deadlines, and
      ``review_ref`` (where an ineligible rejection was routed; empty when eligible).
    """
    service = build_service(_container(settings))
    dispute = Dispute(
        id=dispute_id,
        tenant=tenant,
        track=DisputeTrack(track),
        reason_code=reason_code,
        amount_minor=amount_minor,
        currency=currency,
        transaction_date=parse_date(transaction_date),
        intake_date=parse_date(intake_date),
    )
    result = service.open_dispute(dispute, actor=actor, as_of=parse_date(as_of))
    payload = _as_dict(result.eligibility)
    payload["state"] = result.case.state.value
    payload["requires_human_review"] = result.disposition.requires_human_review
    payload["review_ref"] = result.review_ref
    return payload


def assess_refund_abuse(
    dispute_id: str,
    track: str,
    reason_code: str,
    amount_minor: int,
    currency: str,
    transaction_date: str,
    intake_date: str,
    dispute_count_90d: int = 0,
    prior_abuse_count: int = 0,
    refund_total_minor_90d: int = 0,
    actor: str = DEFAULT_ACTOR,
    tenant: str = "",
    settings: Settings | None = None,
) -> dict[str, Any]:
    """Score refund abuse deterministically; a DENY or REVIEW is routed to sign-off (rule R8).

    Returns:
      A JSON-safe result: the outcome, the transparent score and firing signals, and
      ``review_ref`` (where a consequential outcome was routed; empty for ALLOW).
    """
    service = build_service(_container(settings))
    dispute = Dispute(
        id=dispute_id,
        tenant=tenant,
        track=DisputeTrack(track),
        reason_code=reason_code,
        amount_minor=amount_minor,
        currency=currency,
        transaction_date=parse_date(transaction_date),
        intake_date=parse_date(intake_date),
    )
    history = CustomerHistory(
        dispute_count_90d=dispute_count_90d,
        prior_abuse_count=prior_abuse_count,
        refund_total_minor_90d=refund_total_minor_90d,
    )
    decision = service.assess_abuse(dispute, history, actor=actor)
    payload = _as_dict(decision.assessment)
    payload["requires_human_review"] = decision.disposition is not None
    payload["review_ref"] = decision.review_ref
    return payload


def classify_intake(
    conversation_ref: str,
    actor: str = DEFAULT_ACTOR,
    tenant: str = "",
    settings: Settings | None = None,
) -> dict[str, Any]:
    """Classify an intake conversation into the closed set; unclassifiable fails closed to R8.

    Returns:
      A JSON-safe result: the category, whether it opens a lifecycle case, and ``review_ref``
      (where an unclassifiable or regulatory intake was routed; empty when it opened).
    """
    service = build_service(_container(settings))
    result = service.intake(conversation_ref, tenant=tenant, actor=actor)
    payload = _as_dict(result.classification)
    payload["opened"] = result.opened
    payload["review_ref"] = result.review_ref
    return payload


def verify_audit_trail(settings: Settings | None = None) -> dict[str, Any]:
    """Verify the audit trail's hash chain and its external head anchor.

    Returns:
      A dict with ``ok``, the record counts and a ``detail`` string. ``ok`` is false for an
      edited, deleted or reordered record, and, when an external anchor is configured, for a
      truncated tail as well.
    """
    resolved = settings or Settings.load()
    audit = _container(resolved).audit
    verify = getattr(audit, "verify", None)
    if verify is None:
        raise NotImplementedError(
            f"the {resolved.profile} audit adapter does not expose chain verification; a "
            "managed WORM sink is verified by its own retention policy, not from here"
        )
    report = verify()
    return {
        "ok": report.ok,
        "entries": report.entries,
        "chained": report.chained,
        "legacy": report.legacy,
        "first_bad_seq": report.first_bad_seq,
        "detail": report.detail,
        "anchored": bool(resolved.audit_anchor_path),
    }


#: The tool table. The agent card advertises exactly these, by function name.
TOOL_FUNCTIONS = (open_dispute, assess_refund_abuse, classify_intake, verify_audit_trail)


def build_function_tools() -> list[FunctionTool]:
    """Wrap each callable as a runtime FunctionTool (the only ADK-dependent code path)."""
    from google.adk.tools import FunctionTool

    return [FunctionTool(func=function) for function in TOOL_FUNCTIONS]
