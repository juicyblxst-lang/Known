from __future__ import annotations

import csv
import hashlib
import io
import re
from typing import Any

MAX_CSV_BYTES = 5 * 1024 * 1024


def _clean(value: Any) -> str:
    return " ".join(str(value or "").strip().split())


def _norm(value: str) -> str:
    return re.sub(r"[^a-z0-9]", "", value.lower())


def _pick(row: dict[str, str], *names: str) -> str:
    normalized = {_norm(k): _clean(v) for k, v in row.items()}
    wanted = [_norm(name) for name in names]
    for name in wanted:
        if normalized.get(name):
            return normalized[name]
    for key, value in normalized.items():
        if value and any(name and (name in key or key in name) for name in wanted):
            return value
    return ""


def _stable_id(prefix: str, value: str) -> str:
    digest = hashlib.sha256(value.strip().lower().encode("utf-8")).hexdigest()[:24]
    return f"{prefix}_{digest}"


def _number(value: str) -> float:
    try:
        return float(re.sub(r"[^0-9.-]", "", value) or 0)
    except ValueError:
        return 0.0


def inspect_and_build(csv_text: str) -> dict[str, Any]:
    if len(csv_text.encode("utf-8")) > MAX_CSV_BYTES:
        raise ValueError("CSV file is larger than the 5 MB import limit")

    reader = csv.DictReader(io.StringIO(csv_text.lstrip("\ufeff")))
    if not reader.fieldnames:
        raise ValueError("CSV has no header row")
    headers = reader.fieldnames
    normalized_headers = {_norm(h) for h in headers}
    rows = list(reader)

    if not any("email" in h for h in normalized_headers):
        raise ValueError("CSV must contain an email column so Known can recognize customers")

    has_order_signals = any(
        signal in normalized_headers or any(signal in h for h in normalized_headers)
        for signal in ("financialstatus", "fulfillmentstatus", "total", "ordertotal", "lineitemname", "lineitemsku", "orderid", "ordernumber")
    )
    has_customer_signals = any(signal in normalized_headers for signal in ("customerid", "firstname", "lastname", "acceptsmarketing", "phonenumber"))

    customers: dict[str, dict[str, Any]] = {}
    orders: dict[str, dict[str, Any]] = {}

    for row in rows:
        email = _pick(row, "email", "customer_email", "email_address").lower()
        if not email:
            continue
        first = _pick(row, "first_name", "firstname")
        last = _pick(row, "last_name", "lastname")
        name = _pick(row, "customer_name", "full_name") or " ".join(x for x in (first, last) if x).strip()
        if not name and not has_order_signals:
            name = _pick(row, "name")
        if not name:
            name = email.split("@", 1)[0]

        customer_id = _stable_id("csv_customer", email)
        customers[email] = {"id": customer_id, "name": name, "email": email, "tier": _pick(row, "tier", "customer_tier") or "standard"}

        if has_order_signals:
            order_ref = _pick(row, "order_id", "order_number", "order_name", "name")
            if order_ref:
                order_id = _stable_id("csv_order", order_ref)
                item_name = _pick(row, "lineitem_name", "line_item_name", "product_name", "item_name")
                quantity_raw = _pick(row, "lineitem_quantity", "line_item_quantity", "quantity")
                try:
                    quantity = int(float(quantity_raw)) if quantity_raw else 1
                except ValueError:
                    quantity = 1
                item = {"name": item_name, "quantity": quantity} if item_name else None
                existing = orders.get(order_id)
                if existing:
                    if item:
                        existing["items"].append(item)
                else:
                    orders[order_id] = {"id": order_id, "customer_id": customer_id, "status": _pick(row, "financial_status", "fulfillment_status", "status") or "unknown", "total": _number(_pick(row, "total", "total_price", "order_total", "amount")), "items": [item] if item else []}

    return {"row_count": len(rows), "headers": headers, "customers": list(customers.values()), "orders": list(orders.values()), "customer_count": len(customers), "order_count": len(orders), "source_type": "order_export" if has_order_signals else "customer_export" if has_customer_signals else "customer_data"}
