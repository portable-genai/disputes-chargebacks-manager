"""Local ConversationChannelPort: scripted fictional intake turns, no live channel.

Drives the intake path offline. A small registry of obviously-synthetic conversations keyed by
ref, plus a default script for any unknown ref, so the demo and the gate can classify a real
transcript without Dialogflow. Every party is fictional and every contact is an ``.example``
address.
"""

from __future__ import annotations

from ...config import Settings
from ...domain.models import IntakeTurn

_SCRIPTS: dict[str, tuple[IntakeTurn, ...]] = {
    "conv-unauth-001": (
        IntakeTurn("customer", "I see a card charge I never made at an online shop."),
        IntakeTurn("agent", "I can raise an unauthorised transaction dispute for you."),
        IntakeTurn("customer", "Yes please, it was 420.00 and I still have my card."),
    ),
    "conv-notrecv-002": (
        IntakeTurn("customer", "My marketplace order never arrived and the seller went quiet."),
        IntakeTurn("agent", "Let me open a goods-not-received dispute."),
    ),
    "conv-complaint-003": (
        IntakeTurn("customer", "This is a formal complaint, I want it escalated to the regulator."),
        IntakeTurn("agent", "Understood, I will log a regulatory complaint."),
    ),
    # A regulatory complaint carrying a planted synthetic national id, so the demo's redaction
    # beat can prove the transcript is masked before it reaches the audit record or the console.
    "conv-demo-pii": (
        IntakeTurn(
            "customer",
            "Formal complaint for the regulator: my NRIC S1234567D was mishandled by staff.",
        ),
        IntakeTurn("agent", "I will escalate this as a regulatory complaint."),
    ),
    # An OPENING intake that also carries a planted synthetic national id. Unlike the regulatory
    # script above (which fails closed and records only a redacted citation snippet), this one
    # classifies to a card category and OPENS, so the transcript itself becomes the audit summary:
    # it exercises the redact-before-audit step on the primary summary sink, which the eval's
    # pii_safety metric scans.
    "conv-eval-pii-open": (
        IntakeTurn("customer", "I never made this card charge; my NRIC is S1234567D."),
        IntakeTurn("agent", "I will raise an unauthorised transaction dispute for you."),
    ),
}

_DEFAULT = (
    IntakeTurn("customer", "I want to dispute a charge on my account."),
    IntakeTurn("agent", "Tell me what happened and I will classify it."),
)


class LocalConversationChannel:
    """Return scripted turns for the SDK-free ``local`` profile."""

    def __init__(self, settings: Settings) -> None:
        self._settings = settings

    def fetch_turns(self, conversation_ref: str) -> tuple[IntakeTurn, ...]:
        return _SCRIPTS.get(conversation_ref, _DEFAULT)
