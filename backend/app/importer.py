from __future__ import annotations

import csv
import io
from typing import Any

from .store import StructuredStore

REQUIRED = {"customer_id", "first_name", "last_name", "email", "order_id", "order_date", "order_status", "fulfillment_status", "product_name", "quantity", "total_price", "currency", "shipping_city", "shipping_country"}

def _clean(value: Any) -> str:
    return str(value or "").strip()

def import_csv(contents: bytes, business_id: str, store: StructuredStore) -> dict[str, int]:
    reader = csv.DictReader(io.StringIO(contents.decode("utf-8-sig")))
    fields = {f.strip() for f in (reader.fieldnames or []) if f}
    missing = sorted(REQUIRED - fields)
    if missing:
        raise ValueError(f"CSV missing required columns: {', '.join(missing)}")
    customers: dict[str, dict[str, Any]] = {}; orders: dict[str, dict[str, Any]] = {}; row_count = 0
    for raw in reader:
        row_count += 1
        cid, oid, email = _clean(raw.get("customer_id")), _clean(raw.get("order_id")), _clean(raw.get("email")).lower()
        if not cid or not email or not oid: continue
        first, last = _clean(raw.get("first_name")), _clean(raw.get("last_name"))
        customers[cid] = {"id": cid, "business_id": business_id, "name": " ".join(x for x in (first, last) if x) or email, "email": email, "phone": _clean(raw.get("phone")) or None, "tier": "standard"}
        item, variant = _clean(raw.get("product_name")), _clean(raw.get("product_variant"))
        if variant: item = f"{item} ({variant})" if item else variant
        order = orders.setdefault(oid, {"id": oid, "business_id": business_id, "customer_id": cid, "status": "unknown", "total": 0, "items": [], "fulfillment_status": None, "currency": None, "shipping_city": None, "shipping_country": None, "product_variant": variant or None})
        order.update({"status": _clean(raw.get("order_status")) or order["status"], "fulfillment_status": _clean(raw.get("fulfillment_status")) or None, "currency": _clean(raw.get("currency")) or None, "shipping_city": _clean(raw.get("shipping_city")) or None, "shipping_country": _clean(raw.get("shipping_country")) or None, "product_variant": variant or None})
        try: order["total"] = float(_clean(raw.get("total_price")) or 0)
        except ValueError: pass
        if item and item not in order["items"]: order["items"].append(item)
    if not store.configured: raise RuntimeError("Structured backend is not configured")
    import httpx
    headers = {**store._headers(), "Prefer": "resolution=merge-duplicates"}
    for customer in customers.values():
        r = httpx.post(f"{store.url}/rest/v1/customers", headers=headers, params={"on_conflict": "id"}, json=customer, timeout=10); r.raise_for_status()
    for order in orders.values():
        r = httpx.post(f"{store.url}/rest/v1/orders", headers=headers, params={"on_conflict": "id"}, json=order, timeout=10); r.raise_for_status()
    return {"rows": row_count, "customers": len(customers), "orders": len(orders)}
