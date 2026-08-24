from __future__ import annotations

import os
from typing import Any

import httpx


class StructuredStore:
    """Supabase REST adapter for tenant-scoped structured support data."""

    def __init__(self) -> None:
        self.url = os.getenv("SUPABASE_URL", "").rstrip("/")
        self.key = os.getenv("SUPABASE_SERVICE_ROLE_KEY", "")

    @property
    def configured(self) -> bool:
        return bool(self.url and self.key)

    def _headers(self) -> dict[str, str]:
        return {"apikey": self.key, "Authorization": f"Bearer {self.key}", "Content-Type": "application/json"}

    def _get(self, table: str, params: dict[str, str]) -> list[dict[str, Any]]:
        if not self.configured:
            return []
        response = httpx.get(f"{self.url}/rest/v1/{table}", params=params, headers=self._headers(), timeout=10)
        response.raise_for_status()
        data = response.json()
        return data if isinstance(data, list) else []

    def _post_many(self, table: str, rows: list[dict[str, Any]]) -> list[dict[str, Any]]:
        if not self.configured:
            raise RuntimeError("Structured backend is not configured")
        if not rows:
            return []
        response = httpx.post(f"{self.url}/rest/v1/{table}", params={"on_conflict": "id"}, headers={**self._headers(), "Prefer": "resolution=merge-duplicates,return=representation"}, json=rows, timeout=20)
        response.raise_for_status()
        data = response.json()
        return data if isinstance(data, list) else []

    def customers(self, business_id: str) -> list[dict[str, Any]]:
        return self._get("customers", {"business_id": f"eq.{business_id}", "select": "id,name,email,tier", "order": "name.asc"})

    def search(self, business_id: str, query: str) -> dict[str, list[dict[str, Any]]]:
        value = query.strip()
        if not value:
            return {"customers": [], "orders": []}
        pattern = f"*{value}*"
        customers = self._get("customers", {"business_id": f"eq.{business_id}", "or": f"name.ilike.{pattern},email.ilike.{pattern},id.ilike.{pattern}", "select": "id,name,email,tier", "limit": "8", "order": "name.asc"})
        orders = self._get("orders", {"business_id": f"eq.{business_id}", "id": f"ilike.{pattern}", "select": "id,customer_id,status,total,items,created_at", "limit": "8", "order": "created_at.desc"})
        return {"customers": customers, "orders": orders}

    def customer(self, customer_id: str, business_id: str | None = None) -> dict[str, Any] | None:
        params = {"id": f"eq.{customer_id}", "limit": "1"}
        if business_id:
            params["business_id"] = f"eq.{business_id}"
        rows = self._get("customers", params)
        return rows[0] if rows else None

    def orders(self, customer_id: str, business_id: str | None = None) -> list[dict[str, Any]]:
        params = {"customer_id": f"eq.{customer_id}", "order": "created_at.desc"}
        if business_id:
            params["business_id"] = f"eq.{business_id}"
        return self._get("orders", params)

    def import_csv_records(self, business_id: str, customers: list[dict[str, Any]], orders: list[dict[str, Any]]) -> dict[str, int]:
        customer_rows = [{**row, "business_id": business_id} for row in customers]
        order_rows = [{**row, "business_id": business_id} for row in orders]
        imported_customers = self._post_many("customers", customer_rows)
        imported_orders = self._post_many("orders", order_rows)
        return {"customers": len(imported_customers), "orders": len(imported_orders)}

    def update_order_status(self, order_id: str, customer_id: str, business_id: str, status: str) -> dict[str, Any]:
        if not self.configured:
            raise RuntimeError("Structured backend is not configured")
        params = {"id": f"eq.{order_id}", "customer_id": f"eq.{customer_id}", "business_id": f"eq.{business_id}"}
        response = httpx.patch(f"{self.url}/rest/v1/orders", params=params, headers={**self._headers(), "Prefer": "return=representation"}, json={"status": status}, timeout=10)
        response.raise_for_status()
        rows = response.json()
        if not rows:
            raise LookupError("order not found")
        return rows[0]
