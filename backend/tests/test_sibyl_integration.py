from pathlib import Path

from app.memory import SibylMemory


def test_official_sibyl_memory_round_trip(tmp_path: Path, monkeypatch):
    monkeypatch.setenv("SIBYL_MEMORY_DB", str(tmp_path / "memory.db"))
    memory = SibylMemory()

    ok, error = memory.remember(
        "business-a",
        "customer-1",
        "Maya prefers expedited shipping when an order is time-sensitive.",
    )
    assert ok, error

    result = memory.search(
        "business-a",
        "customer-1",
        "expedited shipping",
    )
    assert result.available
    assert any("expedited" in str(item.get("content", "")).lower() for item in result.memories)


def test_sibyl_memory_isolated_by_business_and_customer(tmp_path: Path, monkeypatch):
    monkeypatch.setenv("SIBYL_MEMORY_DB", str(tmp_path / "memory.db"))
    memory = SibylMemory()

    ok, error = memory.remember("business-a", "customer-1", "Customer prefers blue.")
    assert ok, error

    same_customer = memory.search("business-a", "customer-1", "blue")
    other_business = memory.search("business-b", "customer-1", "blue")
    other_customer = memory.search("business-a", "customer-2", "blue")

    assert same_customer.available and same_customer.memories
    assert other_business.available and other_business.memories == []
    assert other_customer.available and other_customer.memories == []
