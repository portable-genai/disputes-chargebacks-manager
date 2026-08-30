"""Managed ConversationChannelPort: Dialogflow CX / CCAI (SDK import stays lazy).

The ``google.cloud`` import lives inside the method, so the offline profiles import this module
with no GCP SDK present and the parity suite sees the import fail when nothing is reachable.
"""

from __future__ import annotations

from ...config import Settings
from ...domain.models import IntakeTurn


class CloudConversationChannel:
    """Read intake turns from a Dialogflow CX conversation in the managed profile."""

    def __init__(self, settings: Settings) -> None:
        self._settings = settings

    def fetch_turns(
        self, conversation_ref: str
    ) -> tuple[IntakeTurn, ...]:  # pragma: no cover - needs live CCAI
        # The lazy import stays FIRST, and stays real: with no SDK installed this refuses
        # exactly as it always did, which is what the behavioural-parity contract pins.
        from google.cloud import dialogflowcx_v3  # noqa: F401

        # This port was never going to work. `SessionsClient` has no
        # `get_session_entity_type`: that method lives on `SessionEntityTypesClient`, and a
        # session entity type is a slot-value override rather than a transcript, so even the
        # right client would not have returned conversation turns. Nothing caught it because
        # the SDK import is lazy and the whole method is excluded from coverage, so it
        # imported clean and would have raised AttributeError on its first live call.
        #
        # It refuses explicitly rather than being replaced with a guess: Dialogflow CX serves
        # transcripts through Conversational Insights, not through the Sessions API, and
        # writing that against no live CCAI to test it would be inventing an implementation.
        # This is the same shape the sibling adapters in this fleet already use for a port
        # that is named but not yet wired.
        raise NotImplementedError(
            "Dialogflow CX conversation turns are not wired: they come from Conversational "
            "Insights rather than the Sessions API (see docs/runbook.md). The offline "
            f"profile serves {conversation_ref!r} from fixtures."
        )
