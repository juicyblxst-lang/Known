from __future__ import annotations

import csv
import io
from datetime import datetime
from typing import Any

from .store import StructuredStore

REQUIRED = {"customer_id", "first_name", "last_name", "email", "order_id", "order_date", "order_status", "fulfillment_status", "product_name", "quantity", "total_price", "currency", "shipping_city", "shipping_country"}


def _clean(value: Any) -> str:
    return str(value or "").strip()


def import_csv(contents: bytes, business_id: str, store: StructuredStore) -> dict[str, int]:
    text = contents.decode("utf-8-sig")
    reader = csv.DictReader(io.StringIO(text))
    fields = {f.strip() for f in (reader.fieldnames or []) if f}
    missing = sorted(REQUIRED - fields)
    if missing:
        raise ValueError(f"CSV missing required columns: {', '.join(missing)}")

    customers: dict[str, dict[str, Any]] = {}
    orders: dict[str, dict[str, Any]] = {}
    for raw in reader:
        cid, oid, email = _clean(raw.get("customer_id")), _clean(raw.get("order_id")), _clean(raw.get("email")).lower()
        if not cid or not email or not oid:
            continue
        name = " ".join(x for x in (_clean(raw.get("first_name")), _clean(raw.get("last_name"))) if x)
        customers[cid] = {"id": cid, "business_id": business_id, "name": name or email, "email": email, "tier": "standard"}
        item = _clean(raw.get("product_name"))
        variant = _clean(raw.get("product_variant"))
        if variant:
            item = f"{item} ({variant})" if item else variant
        order = orders.setdefault(oid, {"id": oid, "business_id": business_id, "customer_id": cid, "status": _clean(raw.get("order_status")) or "unknown", "total": 0, "items": []})
        order["status"] = _clean(raw.get("order_status")) or order["status"]
        try:
            order["total"] = float(_clean(raw.get("total_price")) or 0)
        except ValueError:
            pass
        if item and item not in order["items"]:
            order["items"].append(item)

    # Use explicit REST helpers so imports remain tenant-scoped and idempotent.
    import httpx
    inserted_customers = inserted_orders = 0
    if not store.configured:
        raise RuntimeError("Structured backend is not configured")
    for customer in customers.values():
        r = httpx.post(f"{store.url}/rest/v1/customers", headers={**store._headers(), "Prefer": "resolution=merge-duplicates"}, params={"on_conflict": "id"}, json=customer, timeout=10)
        r.raise_for_status(); inserted_customers += 1
    for order in orders.values():
        r = httpx.post(f"{store.url}/rest/v1/orders", headers={**store._headers(), "Prefer": "resolution=merge-duplicates"}, params={"on_conflict": "id"}, json=order, timeout=10)
        r.raise_for_status(); inserted_orders += 1
    return {"customers": inserted_customers, "orders": inserted_orders, "rows": sum(1 for _ in [])}
