from pathlib import Path

from app.agent import KnownAgent
from app.memory import SibylMemory
from app.models import SupportRequest


class FakeResponse:
    def __init__(self, text):
        self.output_text = text


class FakeResponses:
    def __init__(self):
        self.inputs = []

    def create(self, *, model, instructions, input):
        self.inputs.append(input)
        return FakeResponse("Personalized response" if "expedited shipping" in input.lower() else "Generic response")


class FakeClient:
    def __init__(self):
        self.responses = FakeResponses()


def request(message):
    return SupportRequest(customer_id="customer-1", message=message)


def test_session_one_memory_changes_session_two_reasoning(tmp_path: Path, monkeypatch):
    monkeypatch.setenv("SIBYL_MEMORY_DB", str(tmp_path / "memory.db"))
    memory = SibylMemory()
    client = FakeClient()
    agent = KnownAgent(memory=memory, client=client)

    first = agent.handle(request("Please remember I prefer expedited shipping when an order is time-sensitive."), auth=type("Auth", (), {"business_id": "business-1"})())
    assert first.memory_written is True

    second = agent.handle(request("My delivery is late and I need expedited shipping."), auth=type("Auth", (), {"business_id": "business-1"})())
    assert second.memories_used
    assert "expedited" in client.responses.inputs[-1].lower()
    assert second.reply == "Personalized response"

    same_customer = memory.search("business-1", "customer-1", "expedited shipping")
    assert same_customer.available
    assert same_customer.memories

    other_customer = memory.search("business-1", "customer-2", "expedited shipping")
    assert other_customer.available
    assert other_customer.memories == []
