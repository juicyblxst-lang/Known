from app.agent import KnownAgent
from app.demo import DemoMemory
from app.models import Customer, Message, Order, SupportRequest


def request() -> SupportRequest:
    customer = Customer(id="demo-customer", name="Maya Chen", email="maya@example.com", tier="vip")
    return SupportRequest(
        customer=customer,
        message="My order is late and I need help before Friday.",
        conversation=[Message(role="user", content="I am worried it won't arrive in time.")],
        orders=[Order(id="ORD-1042", customer_id=customer.id, status="delayed", total=128, items=["linen shirt"])],
    )


def test_memory_changes_recommended_resolution():
    without_memory = KnownAgent(DemoMemory([])).handle(request())
    with_memory = KnownAgent(DemoMemory([
        {"id": "m1", "type": "preference", "content": "Maya prefers expedited shipping when an order is time-sensitive."},
    ])).handle(request())

    assert without_memory.memories_used == []
    assert with_memory.memories_used
    assert without_memory.recommended_action != with_memory.recommended_action
    assert "expedited" in with_memory.recommended_action.lower()
