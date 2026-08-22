from app.agent import KnownAgent
from app.models import SupportRequest


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


def request(message):
    return SupportRequest(customer_id="c1", message=message)


def test_late_delivery_uses_expedited_memory():
    memory = FakeMemory([{"type": "customer_preference", "content": "Maya prefers expedited shipping when an order is time-sensitive."}])
    result = KnownAgent(memory=memory).handle(request("My order is late and I need it before Friday."))
    assert "expedited" in result.recommended_action.lower()
    assert result.memories_used == memory.memories
    assert result.degraded_memory is False


def test_agent_returns_a_response_when_ai_is_not_configured_for_unit_tests():
    result = KnownAgent(memory=FakeMemory()).handle(request("Where is my order?"))
    assert result.customer_id == "c1"
    assert result.reply


def test_preference_language_writes_memory():
    memory = FakeMemory()
    result = KnownAgent(memory=memory).handle(request("Please remember I prefer expedited shipping."))
    assert result.memory_written is True
    assert memory.writes == [("c1", "Please remember I prefer expedited shipping.", "customer_preference")]


def test_degraded_memory_is_reported():
    result = KnownAgent(memory=FakeMemory(available=False)).handle(request("Where is my order?"))
    assert result.degraded_memory is True
