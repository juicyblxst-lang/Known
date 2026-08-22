from __future__ import annotations

from .agent import KnownAgent
from .memory import SibylMemory
from .models import Customer, Message, Order, SupportRequest


class DemoMemory(SibylMemory):
    def __init__(self, memories: list[dict]):
        self._memories = memories
        self.command = "sibyl"
        self.workspace = None

    def search(self, customer_id: str, query: str, limit: int = 8):
        from .memory import MemoryResult
        return MemoryResult(self._memories, True)

    def remember(self, customer_id: str, content: str, memory_type: str = "fact"):
        return True, "demo"


def comparison() -> dict:
    customer = Customer(id="demo-customer", name="Maya Chen", email="maya@example.com", tier="vip")
    order = Order(id="ORD-1042", customer_id=customer.id, status="delayed", total=128, items=["linen shirt"])
    request = SupportRequest(
        customer=customer,
        message="My order is late and I need help before Friday.",
        conversation=[Message(role="user", content="I am worried it won't arrive in time.")],
        orders=[order],
    )
    without_memory = KnownAgent(DemoMemory([])).handle(request)
    with_memory = KnownAgent(DemoMemory([
        {"id": "m1", "type": "preference", "content": "Maya prefers expedited shipping when an order is time-sensitive."},
        {"id": "m2", "type": "history", "content": "Maya had a previous delayed shipment and asked support to proactively monitor delivery."},
    ])).handle(request)
    return {
        "without_memory": without_memory.model_dump(),
        "with_memory": with_memory.model_dump(),
        "different_context": without_memory.memories_used != with_memory.memories_used,
    }
