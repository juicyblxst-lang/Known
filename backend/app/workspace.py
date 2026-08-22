from __future__ import annotations

from typing import Any
from pydantic import BaseModel, Field


class WorkspaceCustomer(BaseModel):
    id: str
    name: str
    email: str
    tier: str = "standard"


class WorkspaceOrder(BaseModel):
    id: str
    status: str
    total: float = 0
    items: list[str] = Field(default_factory=list)


class WorkspaceResponse(BaseModel):
    customer: WorkspaceCustomer | None = None
    orders: list[WorkspaceOrder] = Field(default_factory=list)
    memory: list[dict[str, Any]] = Field(default_factory=list)
    memory_available: bool = False
