from app.csv_import import inspect_and_build
from app.production_agent import KnownAgent


def test_import_customer_ids_are_tenant_scoped():
    csv = "email,first_name\nalice@example.com,Alice\n"
    a = inspect_and_build(csv, "business-a")
    b = inspect_and_build(csv, "business-b")
    assert a["customers"][0]["id"] != b["customers"][0]["id"]


def test_import_customer_id_is_stable_within_tenant():
    csv = "email,first_name\nalice@example.com,Alice\n"
    first = inspect_and_build(csv, "business-a")
    second = inspect_and_build(csv, "business-a")
    assert first["customers"][0]["id"] == second["customers"][0]["id"]


def test_durable_memory_extracts_explicit_preferences_and_constraints():
    assert KnownAgent._extract_durable_memory("I prefer blue") == ("Customer customer preference: blue.", "customer_preference")
    assert KnownAgent._extract_durable_memory("I'm allergic to peanuts") == ("Customer customer constraint: peanuts.", "customer_constraint")
    assert KnownAgent._extract_durable_memory("Please remember that I need size medium") == ("Customer customer preference: I need size medium.", "customer_preference")


def test_durable_memory_does_not_infer_from_ordinary_support_text():
    assert KnownAgent._extract_durable_memory("My package arrived late") is None
