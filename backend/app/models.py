from __future__ import annotations

from typing import Literal

from pydantic import BaseModel, Field, model_validator


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
    """Accept browser identifiers or an already-resolved customer context."""
    customer_id: str | None = None
    customer: Customer | None = None
    message: str = Field(min_length=1, max_length=12000)
    conversation_id: str | None = None
    conversation: list[Message] = Field(default_factory=list)
    orders: list[Order] = Field(default_factory=list)

    @model_validator(mode="after")
    def validate_customer_reference(self) -> "SupportRequest":
        if self.customer_id is None and self.customer is None:
            raise ValueError("customer_id or customer is required")
        if self.customer_id is None and self.customer is not None:
            self.customer_id = self.customer.id
        return self


class SupportContextRequest(BaseModel):
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
    action_executed: bool = False
    action_result: dict | None = None
    degraded_memory: bool = False


class ActionRequest(BaseModel):
    action: Literal["cancel_order", "mark_return_requested", "mark_refund_requested"]
    order_id: str
    customer_id: str


class ActionResponse(BaseModel):
    action: str
    order: dict
    memory_written: bool = False
