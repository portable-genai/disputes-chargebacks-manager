"""The A2A discovery card: what this agent can be asked to do, in one machine-readable place.

Served at ``/.well-known/agent-card.json`` and registrable with agent-registry (rule R4). The card
is built from the SAME tool table the runtime binds, so an agent cannot advertise a skill it does
not implement or implement one it never advertises; ``tests/unit/test_agent_surface.py`` fails the
build when the two disagree.

Pure: domain types and stdlib only, no ADK and no cloud SDK, so the card can be generated and
inspected offline.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any

from hex_service_kit.serialization import to_jsonable

from ..config import Settings

_CARD_VERSION = "0.1.0"


@dataclass(frozen=True, slots=True)
class AgentSkill:
    """One advertised capability. ``id`` is the tool function's name, never a prose label."""

    id: str
    name: str
    description: str


@dataclass(frozen=True, slots=True)
class AgentCard:
    """The minimal A2A discovery document a peer agent or the registry reads."""

    name: str
    description: str
    url: str
    version: str = _CARD_VERSION
    provider: str = "disputes-chargebacks-manager"
    skills: tuple[AgentSkill, ...] = field(default_factory=tuple)


SKILLS: tuple[AgentSkill, ...] = (
    AgentSkill(
        id="open_dispute",
        name="Open dispute",
        description=(
            "Assess a dispute's reason-code eligibility deterministically, open a case on the "
            "human-review-console spine with its regulatory clocks, and ROUTE an ineligible "
            "rejection to human "
            "sign-off (rule R8). The eligibility verdict is pure stdlib code, never a model."
        ),
    ),
    AgentSkill(
        id="assess_refund_abuse",
        name="Assess refund abuse",
        description=(
            "Score a dispute for refund abuse from a transparent additive signal set (velocity, "
            "amount, cumulative refunds, prior abuse) and ROUTE a DENY or REVIEW to maker-checker "
            "sign-off (rule R8). The score and the verdict are deterministic, never a model's."
        ),
    ),
    AgentSkill(
        id="classify_intake",
        name="Classify intake",
        description=(
            "Classify an in-channel intake conversation into a CLOSED category set; an "
            "unclassifiable or regulatory intake never opens a lifecycle case and fails closed "
            "to human review (rule R8). Eligibility and routing are deterministic."
        ),
    ),
    AgentSkill(
        id="verify_audit_trail",
        name="Audit-trail verification",
        description=(
            "Re-derive the hash chain over the stored audit trail and cross-check the external "
            "head anchor, returning an honest verdict: intact, or the first record that broke "
            "the chain, or the anchor disagreement that exposes a truncated tail."
        ),
    ),
)

#: Joined from short pieces, each carrying at most one template variable, so a longer
#: ``friendly_name`` cannot push a line past the formatter's limit in the rendered repo while
#: the template itself still looks fine. The vertical's own prose belongs in ``README.md``;
#: the card says what the agent IS and what it guarantees.
_DESCRIPTION = " ".join(
    (
        "Disputes and Chargebacks Manager",
        "(F2).",
        "Deterministic decision, cited output, redact-before-audit, and every",
        "consequential result routed to a human reviewer.",
    )
)


def build_agent_card(settings: Settings | None = None) -> AgentCard:
    """Construct the A2A card for this agent in the configured deployment."""
    resolved = settings or Settings.load()
    return AgentCard(
        name="disputes-chargebacks-manager",
        description=_DESCRIPTION,
        url=_resolve_url(resolved),
        skills=SKILLS,
    )


def agent_card_document(settings: Settings | None = None) -> dict[str, Any]:
    """The JSON-safe body served at ``/.well-known/agent-card.json``."""
    document = to_jsonable(build_agent_card(settings))
    if not isinstance(document, dict):  # pragma: no cover - dataclasses serialise to objects
        raise TypeError("an agent card must serialise to a JSON object")
    return document


def _resolve_url(settings: Settings) -> str:
    """Best-effort public URL for the card, region-qualified so residency is visible on it."""
    return f"https://disputes-chargebacks-manager.{settings.region}.internal.example/a2a"
