from __future__ import annotations

import csv
import hashlib
import io
import re
from typing import Any


def _clean(value: Any) -> str:
    return " ".join(str(value or "").strip().split())


def _pick(row: dict[str, str], *names: str) -> str:
    normalized = {re.sub(r"[^a-z0-9]", "", k.lower()): _clean(v) for k, v in row.items()}
    for name in names:
        key = re.sub(r"[^a-z0-9]", "", name.lower())
        if normalized.get(key):
            return normalized[key]
    for key, value in normalized.items():
        if value and any(part in key for part in [re.sub(r"[^a-z0-9]", "", n.lower()) for n in names]):
            return value
    return ""


def _stable_id(prefix: str, value: str) -> str:
    digest = hashlib.sha256(value.strip().lower().encode("utf-8")).hexdigest()[:24]
    return f"{prefix}_{digest}"


def inspect_and_build(csv_text: str) -> dict[str, Any]:
    if len(csv_text.encode("utf-8")) > 5 * 1024 * 1024:
        raise ValueError("CSV file is larger than the 5 MB import limit")
    reader = csv.DictReader(io.StringIO(csv_text.lstrip("\ufeff")))
    if not reader.fieldnames:
        raise ValueError("CSV has no header row")
    rows = list(reader)
    customers: dict[str, dict[str, Any]] = {}
    orders: dict[str, dict[str, Any]] = {}
    for row in rows:
        email = _pick(row, "email", "customer_email", "email_address").lower()
        name = _pick(row, "name", "customer_name", "full_name", "first_name")
        if not name:
            name = " ".join(x for x in [_pick(row, "first_name"), _pick(row, "last_name")] if x).strip()
        if email:
            customer_id = _stable_id("csv_customer", email)
            customers[email] = {"id": customer_id, "name": name or email.split("@")[0], "email": email, "tier": _pick(row, "tier", "customer_tier") or "standard"}
            order_ref = _pick(row, "order_id", "order_number", "order_name", "id")
            if order_ref and any(k for k in row if "order" in k.lower()):
                order_id = _stable_id("csv_order", order_ref)
                total_raw = _pick(row, "total", "total_price", "order_total", "amount")
                try:
                    total = float(re.sub(r"[^0-9.-]", "", total_raw) or 0)
                except ValueError:
                    total = 0.0
                orders[order_id] = {"id": order_id, "customer_id": customer_id, "status": _pick(row, "status", "financial_status", "fulfillment_status") or "unknown", "total": total, "items": []}
    return {"row_count": len(rows), "headers": reader.fieldnames, "customers": list(customers.values()), "orders": list(orders.values()), "customer_count": len(customers), "order_count": len(orders)}
