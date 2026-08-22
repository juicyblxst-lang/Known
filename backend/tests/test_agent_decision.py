from app.agent import KnownAgent
from app.models import Customer, Order, SupportRequest


class FakeMemory:
    def __init__(self, memories=None, available=True):
        self.memories = memories or []
        self.available = available

    def search(self, customer_id, query):
        return type("Result", (), {"memories": self.memories, "available": self.available})()

    def remember(self, customer_id, content, memory_type):
        return True, ""


def make_request():
    return SupportRequest(customer_id="c1", message="My order is late and I need it before Friday.", conversation_id=None)


def test_relevant_memory_changes_delivery_action():
    plain = KnownAgent(FakeMemory([])).handle(make_request())
    remembered = KnownAgent(FakeMemory([{"type": "preference", "content": "Maya prefers expedited shipping when an order is time-sensitive."}])).handle(make_request())
    assert plain.recommended_action != remembered.recommended_action
    assert "expedited" in remembered.recommended_action.lower()


def test_memory_is_scoped_to_customer_and_business_contract():
    memory = FakeMemory([{ "content": "Customer prefers expedited shipping." }])
    result = KnownAgent(memory).handle(make_request())
    assert result.memories_used == memory.memories
    assert result.degraded_memory is False
