from __future__ import annotations

from typing import Any
import httpx


class DurableMemoryStore:
    """Supabase-backed durable memory provider with the SibylMemory contract."""
    def __init__(self) -> None:
        import os
        self.url = os.getenv("SUPABASE_URL", "").rstrip("/")
        self.key = os.getenv("SUPABASE_SERVICE_ROLE_KEY", "")

    @property
    def configured(self) -> bool:
        return bool(self.url and self.key)

    def health(self) -> dict[str, Any]:
        return {"configured": self.configured, "writable": self.configured, "path": "supabase:customer_memories"}

    def _headers(self) -> dict[str, str]:
        return {"apikey": self.key, "Authorization": f"Bearer {self.key}", "Content-Type": "application/json"}

    def search(self, business_id: str, customer_id: str, query: str, limit: int = 8):
        from .memory import MemoryResult
        if not self.configured or not query.strip():
            return MemoryResult([], True)
        r = httpx.get(f"{self.url}/rest/v1/customer_memories", params={"business_id": f"eq.{business_id}", "customer_id": f"eq.{customer_id}", "select": "id,memory_type,content,source,created_at", "order": "created_at.desc", "limit": "100"}, headers=self._headers(), timeout=10)
        r.raise_for_status()
        rows = r.json() if isinstance(r.json(), list) else []
        terms = {x.lower() for x in query.split() if len(x) >= 3}
        scored = []
        for row in rows:
            content = str(row.get("content", ""))
            scored.append((sum(1 for term in terms if term in content.lower()), row))
        scored.sort(key=lambda item: (item[0], item[1].get("created_at", "")), reverse=True)
        return MemoryResult([row for _, row in scored[:limit]], True)

    def remember(self, business_id: str, customer_id: str, content: str, memory_type: str = "customer_preference") -> tuple[bool, str]:
        if not self.configured or not content.strip():
            return False, "Supabase memory is not configured or content is empty"
        r = httpx.post(f"{self.url}/rest/v1/customer_memories", headers={**self._headers(), "Prefer": "resolution=ignore-duplicates"}, json={"business_id": business_id, "customer_id": customer_id, "memory_type": memory_type, "content": content.strip(), "source": "support"}, timeout=10)
        r.raise_for_status()
        return True, ""

    def record_event(self, business_id: str, customer_id: str, kind: str, body: dict[str, Any]) -> tuple[bool, str]:
        return self.remember(business_id, customer_id, f"Support event: {kind}. {body}", "support_event")


def configured_memory():
    import os
    if os.getenv("MEMORY_PROVIDER", "sibyl").lower() == "supabase":
        return DurableMemoryStore()
    from .memory import SibylMemory
    return SibylMemory()
