from pathlib import Path

from app.memory import SibylMemory
from app.models import SupportRequest
from app.production_agent import KnownAgent


class FakeResponse:
    def __init__(self, text):
        self.output_text = text


class FakeResponses:
    def __init__(self):
        self.inputs = []

    def create(self, *, model, instructions, input):
        self.inputs.append(input)
        return FakeResponse("Personalized response" if "Maya prefers expedited handling" in input else "Generic response")


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
