from __future__ import annotations

import os
from datetime import datetime, timezone
from typing import Any

import httpx

from .models import Message
from .session_store import ConversationSession
from .supabase_credentials import service_headers, service_key


class SupabaseSessionStore:
    """Durable conversation store backed by the existing Supabase schema."""

    def __init__(self) -> None:
        self.url = os.getenv("SUPABASE_URL", "").rstrip("/")
        self.key = service_key()

    @property
    def configured(self) -> bool:
        return bool(self.url and self.key)

    @property
    def headers(self) -> dict[str, str]:
        return service_headers(self.key)

    def _request(self, method: str, table: str, **kwargs: Any) -> list[dict[str, Any]]:
        response = httpx.request(method, f"{self.url}/rest/v1/{table}", headers=self.headers, timeout=10, **kwargs)
        response.raise_for_status()
        if not response.content:
            return []
        data = response.json()
        return data if isinstance(data, list) else []

    def get(self, session_id: str, customer_id: str, business_id: str) -> ConversationSession | None:
        rows = self._request("GET", "conversations", params={
            "id": f"eq.{session_id}",
            "customer_id": f"eq.{customer_id}",
            "business_id": f"eq.{business_id}",
            "select": "id,customer_id,created_at,updated_at",
            "limit": "1",
        })
        if not rows:
            return None
        row = rows[0]
        messages = self._request("GET", "conversation_messages", params={
            "conversation_id": f"eq.{session_id}",
            "select": "role,content,created_at",
            "order": "created_at.asc",
        })
        return ConversationSession(
            id=row["id"],
            customer_id=row["customer_id"],
            messages=[Message(role=m["role"], content=m["content"]) for m in messages],
            created_at=row["created_at"],
            updated_at=row["updated_at"],
        )

    def get_or_create(self, session_id: str, customer_id: str, business_id: str) -> ConversationSession:
        existing = self.get(session_id, customer_id, business_id)
        if existing is not None:
            return existing
        rows = self._request("GET", "conversations", params={"id": f"eq.{session_id}", "select": "id,customer_id,business_id", "limit": "1"})
        if rows and (rows[0]["customer_id"] != customer_id or str(rows[0]["business_id"]) != str(business_id)):
            raise ValueError("session does not belong to customer")
        self._request("POST", "conversations", json={"id": session_id, "business_id": business_id, "customer_id": customer_id})
        return ConversationSession(id=session_id, customer_id=customer_id)

    def append(self, session_id: str, message: Message) -> None:
        self._request("POST", "conversation_messages", json={"conversation_id": session_id, "role": message.role, "content": message.content})
        self._request(
            "PATCH",
            "conversations",
            params={"id": f"eq.{session_id}"},
            json={"updated_at": datetime.now(timezone.utc).isoformat()},
        )
