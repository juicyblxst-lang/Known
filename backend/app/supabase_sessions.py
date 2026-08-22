from __future__ import annotations

import os
from typing import Any

import httpx

from .models import Message
from .session_store import ConversationSession


class SupabaseSessionStore:
    """Durable conversation store backed by the existing Supabase schema.

    When Supabase is not configured, callers can continue using the local
    development store. No fake persistence is created here.
    """

    def __init__(self) -> None:
        self.url = os.getenv("SUPABASE_URL", "").rstrip("/")
        self.key = os.getenv("SUPABASE_SERVICE_ROLE_KEY", "")

    @property
    def configured(self) -> bool:
        return bool(self.url and self.key)

    @property
    def headers(self) -> dict[str, str]:
        return {"apikey": self.key, "Authorization": f"Bearer {self.key}", "Content-Type": "application/json"}

    def _request(self, method: str, table: str, **kwargs: Any) -> list[dict[str, Any]]:
        response = httpx.request(method, f"{self.url}/rest/v1/{table}", headers=self.headers, timeout=10, **kwargs)
        response.raise_for_status()
        if not response.content:
            return []
        data = response.json()
        return data if isinstance(data, list) else []

    def get_or_create(self, session_id: str, customer_id: str, business_id: str) -> ConversationSession:
        rows = self._request("GET", "conversations", params={"id": f"eq.{session_id}", "select": "id,customer_id,created_at,updated_at", "limit": "1"})
        if rows:
            row = rows[0]
            if row["customer_id"] != customer_id:
                raise ValueError("session does not belong to customer")
            messages = self._request("GET", "conversation_messages", params={"conversation_id": f"eq.{session_id}", "select": "role,content,created_at", "order": "created_at.asc"})
            return ConversationSession(
                id=row["id"],
                customer_id=row["customer_id"],
                messages=[Message(role=m["role"], content=m["content"]) for m in messages],
                created_at=row["created_at"],
                updated_at=row["updated_at"],
            )
        self._request("POST", "conversations", json={"id": session_id, "business_id": business_id, "customer_id": customer_id})
        return ConversationSession(id=session_id, customer_id=customer_id)

    def append(self, session_id: str, message: Message) -> None:
        self._request("POST", "conversation_messages", json={"conversation_id": session_id, "role": message.role, "content": message.content})
        self._request("PATCH", "conversations", params={"id": f"eq.{session_id}"}, json={"updated_at": "now()"})
