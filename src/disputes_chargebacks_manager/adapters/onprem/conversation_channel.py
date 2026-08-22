"""On-prem ConversationChannelPort: fail-fast portability placeholder (P-12).

The client runs its own contact-centre channel on-premises, so this binding refuses rather than
inventing turns that would be classified into a real, consequential case.
"""

from __future__ import annotations

from ...config import Settings
from ...domain.models import IntakeTurn


class OnPremConversationChannel:
    """Satisfies ConversationChannelPort but refuses: bind the client's own channel on-prem."""

    def __init__(self, settings: Settings) -> None:
        self._settings = settings

    def fetch_turns(self, conversation_ref: str) -> tuple[IntakeTurn, ...]:
        raise NotImplementedError(
            "on-prem conversation channel is a portability placeholder: bind the client's own "
            "contact-centre channel (see docs/onprem-migration.md)."
        )
