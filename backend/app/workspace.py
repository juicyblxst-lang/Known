from __future__ import annotations

from typing import Any
from pydantic import BaseModel, Field, field_validator


class WorkspaceCustomer(BaseModel):
    id: str
    name: str
    email: str
    tier: str = "standard"


class WorkspaceOrder(BaseModel):
    id: str
    status: str
    total: float = 0
    items: list[dict[str, Any] | str] = Field(default_factory=list)

    @field_validator("items", mode="before")
    @classmethod
    def normalize_items(cls, value: Any) -> list[dict[str, Any] | str]:
        """Keep the existing order data, but make catalog items readable to the UI."""
        if not isinstance(value, list):
            return []
        normalized: list[dict[str, Any] | str] = []
        for item in value:
            if isinstance(item, dict):
                name = str(item.get("name") or item.get("title") or item.get("product") or "Item").strip()
                quantity = item.get("quantity")
                if quantity not in (None, "", 1, "1"):
                    normalized.append(f"{name} × {quantity}")
                else:
                    normalized.append(name)
            elif item is not None:
                text = str(item).strip()
                if text:
                    normalized.append(text)
        return normalized


class WorkspaceResponse(BaseModel):
    customer: WorkspaceCustomer | None = None
    orders: list[WorkspaceOrder] = Field(default_factory=list)
    memory: list[dict[str, Any]] = Field(default_factory=list)
    memory_available: bool = False
