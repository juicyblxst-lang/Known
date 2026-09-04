from app.integrations import process_gmail_messages


class FakeStore:
    def _get(self, table, params):
        return [{"id": "customer-1", "name": "Maya Rivera", "email": "maya@example.com", "tier": "standard"}]
    def customer_by_email(self, email, business_id): return self._get("customers", {})[0] if email == "maya@example.com" else None
    def orders(self, customer_id, business_id):
        return [{"id": "10482", "customer_id": customer_id, "status": "shipped", "total": 125.0, "items": ["Sneakers"]}]


class FakeSessions:
    def __init__(self): self.sessions = {}
    def get_or_create(self, session_id, customer_id, business_id):
        self.sessions.setdefault(session_id, type("S", (), {"messages": []})())
        return self.sessions[session_id]
    def get(self, session_id, customer_id, business_id): return self.sessions.get(session_id)
    def append(self, session_id, message): self.sessions[session_id].messages.append(message)


class FakeIntegrationStore:
    def __init__(self): self.rows = {}; self.records = []
    def seen(self, business_id, external_id): return self.rows.get(external_id, {}).get("processing_status") == "processed"
    def claim_message(self, business_id, data):
        external_id = data["external_message_id"]
        if external_id in self.rows and self.rows[external_id].get("processing_status") == "processed": return None
        row = self.rows.setdefault(external_id, {"id": external_id, "processing_status": "processing", "attempt_count": 0})
        row["processing_status"] = "processing"; row["attempt_count"] += 1
        self.records.append(("inbound", None, data.get("body", "")))
        return row
    def mark_sent(self, business_id, external_id, sent_id, reply, customer_id, session_id):
        self.rows[external_id].update(processing_status="sent", outbound_message_id=sent_id, outbound_body=reply, customer_id=customer_id, session_id=session_id)
    def mark_processed(self, business_id, external_id): self.rows[external_id]["processing_status"] = "processed"
    def mark_failed(self, business_id, external_id, error): self.rows[external_id].update(processing_status="failed", last_error=error)
    def remember_identity(self, business_id, customer_id, email): self.records.append(("identity", customer_id, email))
    def record_message(self, business_id, data, customer_id, session_id, direction, external_id=None): self.records.append((direction, customer_id, data.get("body", "")))
    def update_tokens(self, *args): pass


class FakeGmail:
    def list_messages(self, token, max_results=20): return [{"id": "m1", "threadId": "t1"}]
    def parse_message(self, message): return {"external_message_id": "m1", "external_thread_id": "t1", "sender_email": "maya@example.com", "recipient_email": "support@example.com", "subject": "Where is my order?", "body": "Where is my order?", "message_id_header": "<m1@example.com>"}
    def send(self, token, to, subject, body, thread_id=None, in_reply_to=None):
        assert thread_id == "t1" and in_reply_to == "<m1@example.com>"
        return {"id": "out1"}
    def mark_read(self, token, message_id): pass


class FakeMemory:
    def search(self, business_id, customer_id, query): return type("R", (), {"available": True, "memories": [{"content": "Maya prefers leave at door."}], "error": ""})()
    def remember(self, *args): return True, ""
    def record_event(self, *args): return True, ""


class FakeAgent:
    def __init__(self): self.memory = FakeMemory()
    def handle(self, request, auth=None):
        assert auth.business_id == "business-a"
        memories = self.memory.search("business-a", request.customer.id, request.message).memories
        assert any("leave at door" in m["content"] for m in memories)
        return type("R", (), {"reply": "Hi Maya, I found your order #10482 and your leave-at-door preference. I'll check the latest status for you."})()


def test_gmail_to_customer_to_sibyl_to_agent_to_gmail():
    integration = FakeIntegrationStore()
    result = process_gmail_messages("business-a", {"access_token": "token"}, FakeAgent(), FakeStore(), FakeSessions(), integration, FakeGmail())
    assert result["processed"] == 1
    assert result["matched"] == 1
    assert result["ignored"] == 0
    assert result["created"] == 0
    assert result["failed"] == 0
    assert integration.rows["m1"]["processing_status"] == "processed"
    assert any(r[0] == "inbound" for r in integration.records)
    assert any(r[0] == "outbound" for r in integration.records)
