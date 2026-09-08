from __future__ import annotations

import hashlib
import os
import re
from dataclasses import dataclass
from pathlib import Path
from typing import Any

import httpx

from sibyl_memory_client import MemoryClient
from sibyl_memory_client.exceptions import (
    CapExceededError,
    NotFoundError,
    SibylMemoryError,
    TierGateError,
    TierVerificationError,
    ValidationError,
)

from .supabase_credentials import service_headers, service_key


@dataclass
class MemoryResult:
    memories: list[dict[str, Any]]
    available: bool
    error: str | None = None


class SibylMemory:
    """Known memory adapter.

    Sibyl remains the semantic memory engine, while Supabase is the durable
    customer-scoped source of truth. This prevents customer memory from being
    lost when the Render container is replaced and lets retrieval combine
    semantic recall with structured customer history.
    """

    def __init__(self) -> None:
        configured = os.getenv("SIBYL_MEMORY_DB")
        default_path = Path("data") / "sibyl" / "memory.db"
        self.db_path = Path(configured or default_path).expanduser()
        self.account_id = os.getenv("SIBYL_ACCOUNT_ID") or None
        self.session_token = os.getenv("SIBYL_SESSION_TOKEN") or None
        self.tier = os.getenv("SIBYL_TIER", "free")
        self.supabase_url = os.getenv("SUPABASE_URL", "").rstrip("/")
        self.supabase_key = service_key()

    @property
    def configured(self) -> bool:
        try:
            self.db_path.parent.mkdir(parents=True, exist_ok=True)
            return self.db_path.parent.is_dir() and os.access(self.db_path.parent, os.W_OK)
        except OSError:
            return False

    @property
    def durable_configured(self) -> bool:
        return bool(self.supabase_url and self.supabase_key)

    def health(self) -> dict[str, Any]:
        if not self.configured:
            return {"configured": False, "writable": False, "durable_configured": self.durable_configured, "path": str(self.db_path), "error": "Sibyl memory path is not writable"}
        client = None
        try:
            client = self._client("__health__", "__health__")
            durable_ok = self._durable_health()
            return {"configured": True, "writable": True, "durable_configured": self.durable_configured, "durable_available": durable_ok, "path": str(self.db_path)}
        except Exception as exc:
            return {"configured": False, "writable": True, "durable_configured": self.durable_configured, "path": str(self.db_path), "error": self._error_message(exc)}
        finally:
            if client is not None:
                self._close(client)

    def _durable_health(self) -> bool:
        if not self.durable_configured:
            return False
        try:
            response = httpx.get(f"{self.supabase_url}/rest/v1/customer_memories", params={"select": "id", "limit": "1"}, headers=service_headers(self.supabase_key), timeout=5)
            response.raise_for_status()
            return True
        except httpx.HTTPError:
            return False

    def _durable_request(self, method: str, **kwargs: Any) -> list[dict[str, Any]]:
        if not self.durable_configured:
            raise RuntimeError("Durable customer memory is not configured")
        response = httpx.request(method, f"{self.supabase_url}/rest/v1/customer_memories", headers=service_headers(self.supabase_key), timeout=10, **kwargs)
        response.raise_for_status()
        if not response.content:
            return []
        data = response.json()
        return data if isinstance(data, list) else []

    def _durable_search(self, business_id: str, customer_id: str, query: str, limit: int) -> list[dict[str, Any]]:
        rows = self._durable_request("GET", params={"business_id": f"eq.{business_id}", "customer_id": f"eq.{customer_id}", "select": "id,memory_type,content,source,source_id,created_at", "order": "created_at.desc", "limit": "50"})
        terms = {term for term in re.findall(r"[a-z0-9]{3,}", query.lower()) if term not in {"the", "and", "for", "with", "from", "that", "this", "what", "where"}}
        if not terms:
            return rows[:limit]

        def score(row: dict[str, Any]) -> tuple[int, str]:
            text = str(row.get("content", "")).lower()
            return sum(1 for term in terms if term in text), str(row.get("created_at", ""))

        ranked = sorted(rows, key=score, reverse=True)
        relevant = [row for row in ranked if score(row)[0] > 0]
        return (relevant or rows)[:limit]

    def _durable_remember(self, business_id: str, customer_id: str, content: str, memory_type: str) -> None:
        self._durable_request("POST", params={"on_conflict": "business_id,customer_id,memory_type,content"}, headers={**service_headers(self.supabase_key), "Prefer": "resolution=ignore-duplicates,return=minimal"}, json={"business_id": business_id, "customer_id": customer_id, "memory_type": memory_type, "content": content, "source": "known"})

    def _tenant_id(self, business_id: str, customer_id: str) -> str:
        return f"{business_id}:{customer_id}"

    def _client(self, business_id: str, customer_id: str) -> MemoryClient:
        self.db_path.parent.mkdir(parents=True, exist_ok=True)
        return MemoryClient.local(str(self.db_path), tenant_id=self._tenant_id(business_id, customer_id), account_id=self.account_id, session_token=self.session_token, tier=self.tier)

    @staticmethod
    def _close(client: MemoryClient) -> None:
        try:
            getattr(client.storage, "close", lambda: None)()
        except Exception:
            pass

    @staticmethod
    def _normalize_hit(hit: Any) -> dict[str, Any]:
        if not isinstance(hit, dict):
            return {"content": str(hit)}
        body = hit.get("body")
        content = hit.get("content")
        if content is None:
            if isinstance(body, dict):
                content = body.get("content") or body.get("value") or str(body)
            elif body is not None:
                content = str(body)
        normalized = dict(hit)
        if content is not None:
            normalized["content"] = str(content)
        return normalized

    @staticmethod
    def _error_message(exc: Exception) -> str:
        if isinstance(exc, CapExceededError):
            return "Sibyl memory tier capacity exceeded"
        if isinstance(exc, TierGateError):
            return "Sibyl memory feature requires the configured tier"
        if isinstance(exc, TierVerificationError):
            return "Sibyl memory tier verification failed"
        if isinstance(exc, ValidationError):
            return f"Sibyl memory validation failed: {exc}"
        if isinstance(exc, NotFoundError):
            return "Sibyl memory entry not found"
        if isinstance(exc, SibylMemoryError):
            return str(exc)
        return str(exc)

    def search(self, business_id: str, customer_id: str, query: str, limit: int = 8) -> MemoryResult:
        if not query or len(query.strip()) < 3:
            return MemoryResult([], True)
        client = None
        try:
            client = self._client(business_id, customer_id)
            semantic = [self._normalize_hit(hit) for hit in client.search(query.strip(), limit=min(max(limit, 1), 50))]
            durable = self._durable_search(business_id, customer_id, query, min(max(limit, 1), 50))
            merged: list[dict[str, Any]] = []
            seen: set[str] = set()
            for hit in [*semantic, *durable]:
                content = str(hit.get("content", "")).strip()
                key = hashlib.sha256(content.encode("utf-8")).hexdigest() if content else repr(hit)
                if key in seen:
                    continue
                seen.add(key)
                merged.append(hit)
                if len(merged) >= min(max(limit, 1), 50):
                    break
            return MemoryResult(merged, True)
        except Exception as exc:
            return MemoryResult([], False, self._error_message(exc))
        finally:
            if client is not None:
                self._close(client)

    def remember(self, business_id: str, customer_id: str, content: str, memory_type: str = "customer_history") -> tuple[bool, str]:
        if not content.strip():
            return False, "Sibyl memory content is empty"
        client = None
        try:
            client = self._client(business_id, customer_id)
            digest = hashlib.sha256(content.encode("utf-8")).hexdigest()[:24]
            client.set_entity(memory_type, f"memory-{digest}", {"content": content, "customer_id": customer_id, "type": memory_type})
            self._durable_remember(business_id, customer_id, content, memory_type)
            return True, ""
        except Exception as exc:
            return False, self._error_message(exc)
        finally:
            if client is not None:
                self._close(client)

    def record_event(self, business_id: str, customer_id: str, kind: str, body: dict[str, Any]) -> tuple[bool, str]:
        client = None
        try:
            client = self._client(business_id, customer_id)
            event_id = client.write_event(acted={"kind": kind, "body": body}, extra={"customer_id": customer_id})
            content = f"Known support event ({kind}): {body}"
            self._durable_remember(business_id, customer_id, content, "support_event")
            return True, str(event_id)
        except Exception as exc:
            return False, self._error_message(exc)
        finally:
            if client is not None:
                self._close(client)

    def import_customer_history(self, business_id: str, customers: list[dict[str, Any]], orders: list[dict[str, Any]]) -> dict[str, int]:
        """Materialize imported CSV history into per-customer long-term memory."""
        orders_by_customer: dict[str, list[dict[str, Any]]] = {}
        for order in orders:
            orders_by_customer.setdefault(str(order.get("customer_id", "")), []).append(order)

        memories_written = 0
        for customer in customers:
            customer_id = str(customer["id"])
            customer_orders = orders_by_customer.get(customer_id, [])
            lines = [f"Customer: {customer.get('name') or 'Unknown'}", f"Email: {customer.get('email') or 'Unknown'}", f"Tier: {customer.get('tier') or 'standard'}"]
            if customer_orders:
                lines.append("Order history:")
                for order in customer_orders:
                    items = ", ".join(f"{item.get('name') or 'Item'} x{item.get('quantity', 1)}" for item in (order.get("items") or [])) or "No line items"
                    lines.append(f"- {order.get('id')}: {items}; status={order.get('status') or 'unknown'}; total={order.get('total', 0)}")
            content = "\n".join(lines)
            ok, error = self.remember(business_id, customer_id, content, "customer_history")
            if not ok:
                raise RuntimeError(error)
            memories_written += 1

        return {"customers": len(customers), "memories": memories_written}
