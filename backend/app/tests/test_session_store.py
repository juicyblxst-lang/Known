import pytest

from app.models import Message
from app.session_store import InMemorySessionStore


def test_session_persists_messages_for_same_customer():
    store = InMemorySessionStore()
    session = store.get_or_create("session-1", "customer-1")
    session.append(Message(role="user", content="Where is my order?"))

    restored = store.get_or_create("session-1", "customer-1")
    assert restored.messages[0].content == "Where is my order?"


def test_session_cannot_be_reused_by_another_customer():
    store = InMemorySessionStore()
    store.create("session-1", "customer-1")

    with pytest.raises(ValueError):
        store.get_or_create("session-1", "customer-2")
