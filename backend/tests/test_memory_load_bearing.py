import pytest

from app.production_agent import KnownAgent
from app.models import SupportRequest


class UnavailableMemory:
    def search(self, business_id, customer_id, query):
        return type("Result", (), {"memories": [], "available": False})()

    def remember(self, business_id, customer_id, content, memory_type):
        return False, ""


def test_sibyl_unavailability_blocks_memory_dependent_support():
    agent = KnownAgent(memory=UnavailableMemory(), client=object())
    with pytest.raises(RuntimeError, match="Sibyl Memory is unavailable"):
        agent.handle(SupportRequest(customer_id="customer-1", message="My order is late."))
