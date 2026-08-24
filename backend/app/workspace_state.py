from __future__ import annotations

import json
import os
from pathlib import Path
from threading import Lock
from typing import Any


class WorkspaceState:
    """Small durable V1 state store for workspace-only lifecycle metadata.

    Structured customer/order data remains in Supabase. This file only stores
    UI/workspace metadata that is intentionally not part of those source rows.
    """

    def __init__(self) -> None:
        configured = os.getenv("KNOWN_WORKSPACE_STATE")
        self.path = Path(configured or "data/sibyl/workspace-state.json").expanduser()
        self.lock = Lock()

    def _read(self) -> dict[str, Any]:
        try:
            return json.loads(self.path.read_text())
        except (FileNotFoundError, json.JSONDecodeError, OSError):
            return {"businesses": {}}

    def _write(self, data: dict[str, Any]) -> None:
        self.path.parent.mkdir(parents=True, exist_ok=True)
        temp = self.path.with_suffix(".tmp")
        temp.write_text(json.dumps(data, indent=2))
        temp.replace(self.path)

    def _business(self, data: dict[str, Any], business_id: str) -> dict[str, Any]:
        return data.setdefault("businesses", {}).setdefault(business_id, {"archived_customers": [], "imports": {}})

    def archived_customers(self, business_id: str) -> set[str]:
        with self.lock:
            return set(self._business(self._read(), business_id).get("archived_customers", []))

    def set_customer_archived(self, business_id: str, customer_id: str, archived: bool) -> None:
        with self.lock:
            data = self._read(); state = self._business(data, business_id)
            ids = set(state.get("archived_customers", []))
            if archived: ids.add(customer_id)
            else: ids.discard(customer_id)
            state["archived_customers"] = sorted(ids)
            self._write(data)

    def imports(self, business_id: str) -> list[dict[str, Any]]:
        with self.lock:
            values = self._business(self._read(), business_id).get("imports", {})
            return sorted(values.values(), key=lambda item: item.get("importedAt", ""), reverse=True)

    def save_import(self, business_id: str, record: dict[str, Any]) -> None:
        with self.lock:
            data = self._read(); state = self._business(data, business_id)
            imports = state.setdefault("imports", {})
            imports[record["id"]] = record
            self._write(data)

    def update_import(self, business_id: str, import_id: str, **changes: Any) -> dict[str, Any] | None:
        with self.lock:
            data = self._read(); state = self._business(data, business_id)
            item = state.setdefault("imports", {}).get(import_id)
            if not item: return None
            item.update(changes)
            self._write(data)
            return item

    def delete_import(self, business_id: str, import_id: str) -> bool:
        with self.lock:
            data = self._read(); state = self._business(data, business_id)
            existed = state.setdefault("imports", {}).pop(import_id, None) is not None
            if existed: self._write(data)
            return existed
