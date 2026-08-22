from __future__ import annotations

import hashlib
import os
from dataclasses import dataclass
from pathlib import Path
from typing import Any

from sibyl_memory_client import MemoryClient
from sibyl_memory_client.exceptions import (
    CapExceededError,
    NotFoundError,
    SibylMemoryError,
    TierGateError,
    TierVerificationError,
    ValidationError,
)


@dataclass
class MemoryResult:
    memories: list[dict[str, Any]]
    available: bool
    error: str | None = None


class SibylMemory:
    """Production adapter over the official Sibyl Memory SDK."""

    def __init__(self) -> None:
        configured = os.getenv("SIBYL_MEMORY_DB")
        default_path = Path("data") / "sibyl" / "memory.db"
        self.db_path = Path(configured or default_path).expanduser()
        self.account_id = os.getenv("SIBYL_ACCOUNT_ID") or None
        self.session_token = os.getenv("SIBYL_SESSION_TOKEN") or None
        self.tier = os.getenv("SIBYL_TIER", "free")

    @property
    def configured(self) -> bool:
        try:
            self.db_path.parent.mkdir(parents=True, exist_ok=True)
            return self.db_path.parent.is_dir() and os.access(self.db_path.parent, os.W_OK)
        except OSError:
            return False

    def health(self) -> dict[str, Any]:
        if not self.configured:
            return {"configured": False, "writable": False, "path": str(self.db_path), "error": "Sibyl memory path is not writable"}
        client = None
        try:
            client = self._client("__health__", "__health__")
            return {"configured": True, "writable": True, "path": str(self.db_path)}
        except Exception as exc:
            return {"configured": False, "writable": True, "path": str(self.db_path), "error": self._error_message(exc)}
        finally:
            if client is not None:
                self._close(client)

    def _tenant_id(self, business_id: str, customer_id: str) -> str:
        return f"{business_id}:{customer_id}"

    def _client(self, business_id: str, customer_id: str) -> MemoryClient:
        self.db_path.parent.mkdir(parents=True, exist_ok=True)
        return MemoryClient.local(
            str(self.db_path),
            tenant_id=self._tenant_id(business_id, customer_id),
            account_id=self.account_id,
            session_token=self.session_token,
            tier=self.tier,
        )

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
            results = client.search(query.strip(), limit=min(max(limit, 1), 50))
            return MemoryResult([self._normalize_hit(hit) for hit in results], True)
        except Exception as exc:
            return MemoryResult([], False, self._error_message(exc))
        finally:
            if client is not None:
                self._close(client)

    def remember(self, business_id: str, customer_id: str, content: str, memory_type: str = "customer_preference") -> tuple[bool, str]:
        if not content.strip():
            return False, "Sibyl memory content is empty"
        client = None
        try:
            client = self._client(business_id, customer_id)
            digest = hashlib.sha256(content.encode("utf-8")).hexdigest()[:24]
            client.set_entity(memory_type, f"memory-{digest}", {"content": content, "customer_id": customer_id, "type": memory_type})
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
            return True, str(event_id)
        except Exception as exc:
            return False, self._error_message(exc)
        finally:
            if client is not None:
                self._close(client)
