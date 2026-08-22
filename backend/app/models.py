from __future__ import annotations

from pydantic import BaseModel, Field


class Customer(BaseModel):
    id: str
    name: str
    email: str
    tier: str = "standard"


class Order(BaseModel):
    id: str
    customer_id: str
    status: str
    total: float = 0
    items: list[str] = Field(default_factory=list)


class Message(BaseModel):
    role: str
    content: str


class SupportRequest(BaseModel):
    customer: Customer
    message: str
    conversation: list[Message] = Field(default_factory=list)
    orders: list[Order] = Field(default_factory=list)


class SupportResponse(BaseModel):
    customer_id: str
    reply: str
    memories_used: list[dict] = Field(default_factory=list)
    memory_written: bool = False
    recommended_action: str | None = None
    degraded_memory: bool = False
