from __future__ import annotations

from typing import Any
import httpx


class DurableMemoryStore:
    """Small Supabase-backed durable memory store used in hosted environments.

    This intentionally mirrors the operations used by SibylMemory so the agent
    can keep its existing memory contract while Render's ephemeral filesystem
    remains disposable.
    """
    def __init__(self) -> None:
        import os
        self.url = os.getenv("SUPABASE_URL", "").rstrip("/")
        self.key = os.getenv("SUPABASE_SERVICE_ROLE_KEY", "")

    @property
    def configured(self) -> bool:
        return bool(self.url and self.key)

    def _headers(self) -> dict[str, str]:
        return {"apikey": self.key, "Authorization": f"Bearer {self.key}", "Content-Type": "application/json"}

    def search(self, business_id: str, customer_id: str, query: str, limit: int = 8) -> list[dict[str, Any]]:
        if not self.configured or not query.strip():
            return []
        # PostgREST text search is intentionally avoided here so this remains
        # compatible with the existing minimal schema. Fetch the customer's
        # bounded memory set and rank simple lexical overlap in application code.
        r = httpx.get(f"{self.url}/rest/v1/customer_memories", params={
            "business_id": f"eq.{business_id}", "customer_id": f"eq.{customer_id}",
            "select": "id,memory_type,content,source,created_at", "order": "created_at.desc", "limit": "100",
        }, headers=self._headers(), timeout=10)
        r.raise_for_status()
        rows = r.json() if isinstance(r.json(), list) else []
        terms = {x.lower() for x in query.split() if len(x) >= 3}
        scored = []
        for row in rows:
            content = str(row.get("content", ""))
            score = sum(1 for term in terms if term in content.lower())
            scored.append((score, row))
        scored.sort(key=lambda item: (item[0], item[1].get("created_at", "")), reverse=True)
        return [row for score, row in scored[:limit] if score > 0] or [row for _, row in scored[:limit]]

    def remember(self, business_id: str, customer_id: str, content: str, memory_type: str, source: str = "support", source_id: str | None = None) -> bool:
        if not self.configured or not content.strip():
            return False
        r = httpx.post(f"{self.url}/rest/v1/customer_memories", headers={**self._headers(), "Prefer": "resolution=ignore-duplicates"}, json={
            "business_id": business_id, "customer_id": customer_id, "memory_type": memory_type,
            "content": content.strip(), "source": source, "source_id": source_id,
        }, timeout=10)
        r.raise_for_status()
        return True

    def event(self, business_id: str, customer_id: str, kind: str, body: dict[str, Any]) -> bool:
        return self.remember(business_id, customer_id, f"Support event: {kind}. {body}", "support_event")
