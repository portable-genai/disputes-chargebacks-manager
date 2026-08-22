"""ConversationChannelPort: the in-channel intake source (absorbed ex-E4 intake).

The managed adapter reads turns from a conversation platform (Dialogflow CX / CCAI); the local
adapter drives scripted fictional turns so intake is testable offline; on-prem fails fast. The
port only SOURCES turns: classification into the closed category set, eligibility and routing are
deterministic and live in the intake service, never in the channel.
"""

from __future__ import annotations

from typing import Protocol, runtime_checkable

from ..domain.models import IntakeTurn


@runtime_checkable
class ConversationChannelPort(Protocol):
    def fetch_turns(self, conversation_ref: str) -> tuple[IntakeTurn, ...]:
        """Return the ordered turns of one intake conversation. Never empty for a known ref."""
        ...
