from app.agent import KnownAgent
from app.models import Customer, Message, SupportRequest


class FakeMemory:
    def __init__(self, memories=None, available=True):
        self.memories = memories or []
        self.available = available
        self.writes = []

    def search(self, customer_id, query):
        return type("Result", (), {"memories": self.memories, "available": self.available})()

    def remember(self, customer_id, content, memory_type):
        self.writes.append((customer_id, content, memory_type))
        return True, None


def request(message, orders=None):
    return SupportRequest(
        customer=Customer(id="c1", name="Maya Chen", email="maya@example.com", tier="vip"),
        message=message,
        conversation=[Message(role="user", content=message)],
        orders=orders or [],
    )


def test_late_delivery_uses_expedited_memory():
    memory = FakeMemory([{"type": "customer_preference", "content": "Maya prefers expedited shipping when an order is time-sensitive."}])
    result = KnownAgent(memory=memory).handle(request("My order is late and I need it before Friday."))

    assert "expedited" in result.recommended_action.lower()
    assert result.memories_used == memory.memories
    assert result.degraded_memory is False


def test_agent_can_fallback_without_openai():
    memory = FakeMemory()
    result = KnownAgent(memory=memory).handle(request("Where is my order?"))

    assert result.customer_id == "c1"
    assert result.reply
    assert "shipment" in result.reply.lower() or "order" in result.reply.lower()


def test_preference_language_writes_memory():
    memory = FakeMemory()
    result = KnownAgent(memory=memory).handle(request("Please remember I prefer expedited shipping."))

    assert result.memory_written is True
    assert memory.writes == [("c1", "Please remember I prefer expedited shipping.", "customer_preference")]


def test_degraded_memory_is_reported():
    memory = FakeMemory(available=False)
    result = KnownAgent(memory=memory).handle(request("Where is my order?"))

    assert result.degraded_memory is True
