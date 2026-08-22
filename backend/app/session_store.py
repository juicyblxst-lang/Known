from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime, timezone

from .models import Message


@dataclass
class ConversationSession:
    id: str
    customer_id: str
    messages: list[Message] = field(default_factory=list)
    created_at: str = field(default_factory=lambda: datetime.now(timezone.utc).isoformat())
    updated_at: str = field(default_factory=lambda: datetime.now(timezone.utc).isoformat())

    def append(self, message: Message) -> None:
        self.messages.append(message)
        self.updated_at = datetime.now(timezone.utc).isoformat()


class InMemorySessionStore:
    """Local session store used until the conversation table is provisioned.

    The interface is deliberately customer/session scoped so it can be replaced
    by Supabase persistence without changing the support-agent contract.
    """

    def __init__(self) -> None:
        self._sessions: dict[str, ConversationSession] = {}

    def get(self, session_id: str) -> ConversationSession | None:
        return self._sessions.get(session_id)

    def create(self, session_id: str, customer_id: str) -> ConversationSession:
        session = ConversationSession(id=session_id, customer_id=customer_id)
        self._sessions[session_id] = session
        return session

    def get_or_create(self, session_id: str, customer_id: str) -> ConversationSession:
        existing = self.get(session_id)
        if existing is not None:
            if existing.customer_id != customer_id:
                raise ValueError("session does not belong to customer")
            return existing
        return self.create(session_id, customer_id)
