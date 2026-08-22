"""Local NarrationPort: deterministic classify and narrate, no LLM SDK.

The offline stand-in for the model's two narrow jobs. ``classify`` maps keyword hits to one label
from the supplied closed set and returns ``""`` when nothing matches (the caller fails that to
human review). ``narrate`` templates the engine facts into a short paragraph and adds nothing not
in the facts. Both are pure and replayable, which is exactly what the eval's groundedness metric
needs a floor to check against.
"""

from __future__ import annotations

from ...config import Settings

#: Keyword -> the category label to prefer. First match in this order wins, so a transcript that
#: mentions several is classified by the strongest signal.
_KEYWORDS: tuple[tuple[str, str], ...] = (
    ("regulator", "complaint_regulatory"),
    ("complaint", "complaint_regulatory"),
    ("never made", "card_unauthorised"),
    ("unauthorised", "card_unauthorised"),
    ("unauthorized", "card_unauthorised"),
    ("fraud", "card_unauthorised"),
    ("never arrived", "card_goods_not_received"),
    ("not received", "card_goods_not_received"),
    ("never came", "retail_not_received"),
    ("not as described", "card_not_as_described"),
    ("refund", "retail_refund"),
)


class LocalNarrator:
    """Deterministic classify/narrate for the SDK-free ``local`` profile."""

    def __init__(self, settings: Settings) -> None:
        self._settings = settings

    def classify(self, text: str, *, categories: tuple[str, ...]) -> str:
        lowered = text.lower()
        for keyword, label in _KEYWORDS:
            if keyword in lowered and label in categories:
                return label
        return ""

    def narrate(self, *, instruction: str, facts: tuple[tuple[str, str], ...]) -> str:
        rendered = "; ".join(f"{k}: {v}" for k, v in facts)
        return f"{instruction} Based on the case record ({rendered})."
