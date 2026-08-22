from __future__ import annotations

import os
from typing import Any

import httpx


class StructuredStore:
    """Supabase REST adapter for structured support data.

    The service remains usable without Supabase for local development; callers
    receive empty data rather than fabricated customer/order records.
    """

    def __init__(self) -> None:
        self.url = os.getenv("SUPABASE_URL", "").rstrip("/")
        self.key = os.getenv("SUPABASE_SERVICE_ROLE_KEY", "")

    @property
    def configured(self) -> bool:
        return bool(self.url and self.key)

    def _get(self, table: str, params: dict[str, str]) -> list[dict[str, Any]]:
        if not self.configured:
            return []
        response = httpx.get(
            f"{self.url}/rest/v1/{table}",
            params=params,
            headers={"apikey": self.key, "Authorization": f"Bearer {self.key}"},
            timeout=10,
        )
        response.raise_for_status()
        data = response.json()
        return data if isinstance(data, list) else []

    def customer(self, customer_id: str) -> dict[str, Any] | None:
        rows = self._get("customers", {"id": f"eq.{customer_id}", "limit": "1"})
        return rows[0] if rows else None

    def orders(self, customer_id: str) -> list[dict[str, Any]]:
        return self._get("orders", {"customer_id": f"eq.{customer_id}", "order": "created_at.desc"})
