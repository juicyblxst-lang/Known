from app.integrations import IntegrationStore


def test_gmail_identity_insert_targets_composite_unique_constraint():
    store = IntegrationStore.__new__(IntegrationStore)
    captured = {}

    def fake_request(method, table, **kwargs):
        captured.update(method=method, table=table, kwargs=kwargs)
        return []

    store._request = fake_request
    store.remember_identity("business-a", "customer-a", "MAYA@EXAMPLE.COM")

    assert captured["method"] == "POST"
    assert captured["table"] == "customer_external_identities"
    assert captured["kwargs"]["params"] == {"on_conflict": "business_id,provider,external_id"}
    assert captured["kwargs"]["headers"] == {"Prefer": "resolution=ignore-duplicates"}
    assert captured["kwargs"]["json"] == {
        "business_id": "business-a",
        "customer_id": "customer-a",
        "provider": "gmail",
        "external_id": "maya@example.com",
    }
