import pytest

from app.models import Message
from app.session_store import InMemorySessionStore


def test_session_round_trip_preserves_messages():
    store = InMemorySessionStore()
    session = store.get_or_create("session-1", "customer-1")
    session.append(Message(role="user", content="Where is my order?"))
    session.append(Message(role="assistant", content="I am checking it now."))

    loaded = store.get("session-1")

    assert loaded is session
    assert [message.content for message in loaded.messages] == [
        "Where is my order?",
        "I am checking it now.",
    ]


def test_session_cannot_be_reused_for_another_customer():
    store = InMemorySessionStore()
    store.create("session-1", "customer-1")

    with pytest.raises(ValueError, match="session does not belong to customer"):
        store.get_or_create("session-1", "customer-2")
