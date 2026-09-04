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
    return re.sub(r"[^a-z0-9]", "", str(value or "").lower())


def _pick(row: dict[str, Any], *names: str) -> str:
    normalized = {_norm(k): _clean(v) for k, v in row.items() if k is not None}
    wanted = [_norm(name) for name in names]
    for name in wanted:
        if normalized.get(name):
            return normalized[name]
    for key, value in normalized.items():
        if value and any(name and (name in key or key in name) for name in wanted):
            return value
    return ""


def _stable_id(prefix: str, value: str, scope: str = "") -> str:
    seed = f"{scope.strip().lower()}:{value.strip().lower()}" if scope else value.strip().lower()
    digest = hashlib.sha256(seed.encode("utf-8")).hexdigest()[:24]
    return f"{prefix}_{digest}"


def _number(value: str) -> float:
    try:
        return float(re.sub(r"[^0-9.-]", "", value) or 0)
    except ValueError:
        return 0.0


def _reader(csv_text: str) -> csv.DictReader:
    text = csv_text.lstrip("\ufeff").replace("\x00", "")
    try:
        dialect = csv.Sniffer().sniff(text[:8192], delimiters=",;\t|")
    except csv.Error:
        dialect = csv.excel
    return csv.DictReader(io.StringIO(text, newline=""), dialect=dialect, restkey="__extra__")


def inspect_and_build(csv_text: str, business_id: str | None = None) -> dict[str, Any]:
    if not isinstance(csv_text, str) or not csv_text.strip():
        raise ValueError("The selected file is empty")
    if len(csv_text.encode("utf-8")) > MAX_CSV_BYTES:
        raise ValueError("CSV file is larger than the 5 MB import limit")
    try:
        reader = _reader(csv_text)
        if not reader.fieldnames:
            raise ValueError("CSV has no header row")
        headers = [str(h or "").strip() for h in reader.fieldnames]
        normalized_headers = {_norm(h) for h in headers}
        rows = list(reader)
    except csv.Error as exc:
        raise ValueError(f"Could not parse this CSV: {exc}") from exc

    if not any("email" in h for h in normalized_headers):
        raise ValueError("CSV must contain an email column so Known can recognize customers")

    has_order_signals = any(signal in normalized_headers or any(signal in h for h in normalized_headers) for signal in ("financialstatus", "fulfillmentstatus", "total", "ordertotal", "lineitemname", "lineitemsku", "orderid", "ordernumber"))
    has_customer_signals = any(signal in normalized_headers for signal in ("customerid", "firstname", "lastname", "acceptsmarketing", "phonenumber"))

    customers: dict[str, dict[str, Any]] = {}
    orders: dict[str, dict[str, Any]] = {}
    scope = business_id or ""
    for row in rows:
        if not isinstance(row, dict):
            continue
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
        customer_id = _stable_id("csv_customer", email, scope)
        customers[email] = {"id": customer_id, "name": name, "email": email, "tier": _pick(row, "tier", "customer_tier") or "standard"}
        if has_order_signals:
            order_ref = _pick(row, "order_id", "order_number", "order_name", "name")
            if order_ref:
                order_id = _stable_id("csv_order", order_ref, scope)
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

    if not customers:
        raise ValueError("No customer records with email addresses were found in this CSV")
    return {"row_count": len(rows), "headers": headers, "customers": list(customers.values()), "orders": list(orders.values()), "customer_count": len(customers), "order_count": len(orders), "source_type": "order_export" if has_order_signals else "customer_export" if has_customer_signals else "customer_data"}
