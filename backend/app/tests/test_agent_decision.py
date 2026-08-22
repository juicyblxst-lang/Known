from app.agent import KnownAgent
from app.demo import DemoMemory
from app.models import Customer, Order, SupportRequest


def make_request():
    customer = Customer(id="c1", name="Maya Chen", email="maya@example.com", tier="vip")
    return SupportRequest(
        customer=customer,
        message="My order is late and I need it before Friday.",
        orders=[Order(id="o1", customer_id="c1", status="delayed", total=128, items=["linen shirt"])],
    )


def test_relevant_memory_changes_delivery_action():
    plain = KnownAgent(DemoMemory([])).handle(make_request())
    remembered = KnownAgent(DemoMemory([
        {"id": "m1", "type": "preference", "content": "Maya prefers expedited shipping when an order is time-sensitive."}
    ])).handle(make_request())

    assert plain.recommended_action != remembered.recommended_action
    assert "expedited" in remembered.recommended_action.lower()
