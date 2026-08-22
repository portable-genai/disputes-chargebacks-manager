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
        from google.cloud import dialogflowcx_v3

        client = dialogflowcx_v3.SessionsClient()
        response = client.get_session_entity_type(name=conversation_ref)
        turns = tuple(IntakeTurn("customer", str(part)) for part in response.entities)
        return turns
