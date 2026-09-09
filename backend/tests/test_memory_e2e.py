from pathlib import Path
import json

from app.memory import SibylMemory
from app.models import SupportRequest
from app.production_agent import KnownAgent
from app.workspace import WorkspaceOrder


class FakeResponse:
    def __init__(self, text):
        self.output_text = text


class FakeResponses:
    def __init__(self):
        self.inputs = []

    def create(self, *, model, instructions, input):
        self.inputs.append(input)
        input_text = input.lower()
        personalized = "maya prefers expedited handling" in input_text
        approval_memory = any(term in input_text for term in ("auto-ship", "auto ship", "automatically", "without my approval", "confirm first", "ask me first"))
        shipping_memory = "shipping instruction" in input_text and any(term in input_text for term in ("17th", "canada", "new address", "office"))
        decision = {
            "reply": "Replacement requires customer approval" if approval_memory else ("The requested shipping details are recorded." if shipping_memory else ("Personalized response" if personalized else "Generic response")),
            "recommendation": "Confirm before replacement" if approval_memory else ("Use the recorded shipping details" if shipping_memory else ("Prioritize expedited handling" if personalized else None)),
            "action": "confirm_before_replacement" if approval_memory else ("use_recorded_shipping_details" if shipping_memory else "none"),
            "memory_influence": "The customer's stored constraint changes the replacement decision." if approval_memory else ("The customer's newly supplied shipping details change the delivery context." if shipping_memory else ("The customer's stored preference changes the delivery recommendation." if personalized else "No relevant memory found")),
            "should_remember": None,
            "memory_type": "none",
        }
        return FakeResponse(json.dumps(decision))


class FakeClient:
    def __init__(self):
        self.responses = FakeResponses()


def request(message):
    return SupportRequest(customer_id="customer-1", message=message)


def auth():
    return type("Auth", (), {"business_id": "business-1"})()


def test_session_one_memory_changes_session_two_reasoning(tmp_path: Path, monkeypatch):
    monkeypatch.setenv("SIBYL_MEMORY_DB", str(tmp_path / "memory.db"))
    memory = SibylMemory()
    client = FakeClient()
    agent = KnownAgent(memory=memory, client=client)

    first = agent.handle(request("Please remember Maya prefers expedited handling for late deliveries."), auth=auth())
    assert first.memory_written is True

    second = agent.handle(request("My delivery is late."), auth=auth())
    assert second.memories_used
    assert "Maya prefers expedited handling" in client.responses.inputs[-1]
    assert second.reply == "Personalized response"

    same_customer = memory.search("business-1", "customer-1", "late deliveries")
    assert same_customer.available and same_customer.memories

    other_customer = memory.search("business-1", "customer-2", "late deliveries")
    assert other_customer.available and other_customer.memories == []


def test_natural_language_approval_constraint_is_persisted_and_changes_action(tmp_path: Path, monkeypatch):
    monkeypatch.setenv("SIBYL_MEMORY_DB", str(tmp_path / "memory.db"))
    memory = SibylMemory()
    client = FakeClient()
    agent = KnownAgent(memory=memory, client=client)

    first = agent.handle(
        request("I travel a lot, so please never ship replacements automatically. Confirm first."),
        auth=auth(),
    )
    assert first.memory_written is True
    assert any("never ship replacements automatically" in m["content"].lower() for m in first.memories_used) is False

    # A genuinely separate support request has no prior conversation supplied to the agent.
    second = agent.handle(request("Hi, my coffee grinder arrived damaged."), auth=auth())
    assert second.memories_used
    assert second.recommended_action == "Confirm the customer's approval before arranging a replacement; do not auto-ship it."
    assert "never ship replacements automatically" in client.responses.inputs[-1].lower()
    assert second.reply == "Replacement requires customer approval"


def test_shipping_details_learned_mid_conversation_are_persisted(tmp_path: Path, monkeypatch):
    monkeypatch.setenv("SIBYL_MEMORY_DB", str(tmp_path / "memory.db"))
    memory = SibylMemory()
    client = FakeClient()
    agent = KnownAgent(memory=memory, client=client)

    first = agent.handle(
        request("Ship the replacement to me on September 17. I will be in Canada, so use my new office address: 14 King Street, Toronto."),
        auth=auth(),
    )
    assert first.memory_written is True

    second = agent.handle(request("Why haven't I received my order?"), auth=auth())
    assert second.memories_used
    assert "september 17" in client.responses.inputs[-1].lower()
    assert "canada" in client.responses.inputs[-1].lower()
    assert "new office address" in client.responses.inputs[-1].lower()
    assert second.recommended_action.startswith("Use the customer's previously recorded shipping timing")


def test_supabase_durability_failure_does_not_break_sibyl_memory(tmp_path: Path, monkeypatch):
    monkeypatch.setenv("SIBYL_MEMORY_DB", str(tmp_path / "memory.db"))
    memory = SibylMemory()
    monkeypatch.setattr(memory, "_durable_remember", lambda *args, **kwargs: (_ for _ in ()).throw(RuntimeError("Supabase 500")))

    ok, error = memory.remember("business-1", "customer-1", "Customer constraint: never auto-ship replacements.", "customer_constraint")
    assert ok is True
    assert error == ""

    result = memory.search("business-1", "customer-1", "damaged replacement")
    assert result.available is True
    assert any("never auto-ship replacements" in str(hit.get("content", "")) for hit in result.memories)


def test_durable_search_failure_does_not_hide_sibyl_memory(tmp_path: Path, monkeypatch):
    monkeypatch.setenv("SIBYL_MEMORY_DB", str(tmp_path / "memory.db"))
    memory = SibylMemory()
    ok, error = memory.remember("business-1", "customer-1", "Customer preference: expedited handling.", "customer_preference")
    assert ok is True and error == ""
    monkeypatch.setattr(memory, "_durable_search", lambda *args, **kwargs: (_ for _ in ()).throw(RuntimeError("Supabase 500")))

    result = memory.search("business-1", "customer-1", "late delivery")
    assert result.available is True
    assert any("expedited handling" in str(hit.get("content", "")) for hit in result.memories)


def test_approval_constraint_variants_are_adaptive():
    variants = [
        "Please don't send replacements without asking me first.",
        "I do not want replacement orders sent automatically; check with me before shipping.",
        "Never auto-ship replacements. Ask me first.",
        "I avoid automatic replacement shipments. Confirm with me first.",
    ]
    for message in variants:
        extracted = KnownAgent._extract_durable_memory(message)
        assert extracted is not None, message
        content, memory_type = extracted
        assert memory_type == "customer_constraint"
        assert content


def test_workspace_order_items_are_readable():
    order = WorkspaceOrder(
        id="order-1",
        status="fulfilled",
        total=49.0,
        items=[{"name": "Milk Frother", "quantity": 2}, {"name": "Coffee Beans", "quantity": 1}],
    )
    assert order.items == ["Milk Frother × 2", "Coffee Beans"]
