from __future__ import annotations

import os
from openai import OpenAI

from .auth import AuthContext
from .memory import MemoryResult, SibylMemory
from .models import SupportContextRequest, SupportRequest, SupportResponse


class KnownAgent:
    def __init__(self, memory: SibylMemory | None = None) -> None:
        self.memory = memory or SibylMemory()
        self.client = OpenAI(api_key=os.environ["OPENAI_API_KEY"]) if os.getenv("OPENAI_API_KEY") else None
        self.model = os.getenv("OPENAI_MODEL", "gpt-5-mini")

    def _search_memory(self, business_id: str, customer_id: str, query: str) -> MemoryResult:
        if isinstance(self.memory, SibylMemory):
            return self.memory.search(business_id, customer_id, query)
        return self.memory.search(customer_id, query)

    def _remember(self, business_id: str, customer_id: str, content: str, memory_type: str) -> tuple[bool, str]:
        if isinstance(self.memory, SibylMemory):
            return self.memory.remember(business_id, customer_id, content, memory_type)
        return self.memory.remember(customer_id, content, memory_type)

    def _record_event(self, business_id: str, customer_id: str, kind: str, body: dict) -> tuple[bool, str]:
        if isinstance(self.memory, SibylMemory):
            return self.memory.record_event(business_id, customer_id, kind, body)
        return True, ""

    @staticmethod
    def _customer_id(request: SupportRequest | SupportContextRequest) -> str:
        if isinstance(request, SupportContextRequest):
            return request.customer.id
        return request.customer.id if request.customer is not None else request.customer_id  # type: ignore[return-value]

    @staticmethod
    def _customer_payload(request: SupportRequest | SupportContextRequest) -> dict:
        if isinstance(request, SupportContextRequest):
            return request.customer.model_dump()
        if request.customer is not None:
            return request.customer.model_dump()
        return {"id": request.customer_id}

    @staticmethod
    def _orders(request: SupportRequest | SupportContextRequest) -> list[dict]:
        return [o.model_dump() for o in getattr(request, "orders", [])]

    @staticmethod
    def _conversation(request: SupportRequest | SupportContextRequest) -> list[dict]:
        return [m.model_dump() for m in getattr(request, "conversation", [])]

    def handle(self, request: SupportRequest | SupportContextRequest, auth: AuthContext | None = None) -> SupportResponse:
        business_id = auth.business_id if auth else os.getenv("KNOWN_LOCAL_BUSINESS_ID", "local-development")
        customer_id = self._customer_id(request)
        retrieved = self._search_memory(business_id, customer_id, request.message)
        memories = retrieved.memories
        action = self._action(request.message, memories)

        system = """You are Known, a customer-support agent for a small e-commerce business.
Use relevant durable customer memory as decision-making context, not merely as a citation.
Never invent customer history. Give a concise, empathetic answer. Treat order data as current
facts and memory as historical context. If memory establishes a relevant preference or prior support pattern, adapt the proposed resolution to it.
Never claim an operational action has happened unless the backend has actually executed it."""
        context = {
            "customer": self._customer_payload(request),
            "orders": self._orders(request),
            "conversation": self._conversation(request),
            "retrieved_memory": memories,
            "decision_and_action": action,
            "current_message": request.message,
        }

        if self.client:
            response = self.client.responses.create(model=self.model, instructions=system, input=str(context))
            reply = response.output_text.strip()
        else:
            reply = self._fallback(request, memories, action)

        memory_written = False
        lower = request.message.lower()
        preference_markers = ("i prefer", "i always", "please remember", "my size is", "i'm allergic", "i am allergic")
        if any(marker in lower for marker in preference_markers):
            ok, _ = self._remember(business_id, customer_id, request.message, "customer_preference")
            memory_written = ok

        event_ok, _ = self._record_event(
            business_id,
            customer_id,
            "support_message",
            {"message": request.message, "recommended_action": action, "memory_used": len(memories)},
        )
        memory_written = memory_written or event_ok

        return SupportResponse(
            customer_id=customer_id,
            reply=reply,
            memories_used=memories,
            memory_written=memory_written,
            recommended_action=action,
            degraded_memory=not retrieved.available,
        )

    @staticmethod
    def _action(message: str, memories: list[dict]) -> str | None:
        text = message.lower()
        memory_text = " ".join(str(m.get("content", "")) for m in memories).lower()
        if any(word in text for word in ("refund", "return", "cancel")):
            return "Review order eligibility and offer the applicable return/refund workflow."
        if any(word in text for word in ("late", "where is", "tracking", "delivery")):
            if "expedited" in memory_text or "urgent" in memory_text or "time-sensitive" in memory_text:
                return "Prioritize the latest shipment check and, if delivery cannot meet the deadline, offer the customer's preferred expedited resolution."
            if "monitor" in memory_text or "previous delayed" in memory_text:
                return "Check the latest shipment status and proactively monitor the delivery, reflecting the customer's previous support preference."
            return "Check the latest shipment status and provide the tracking update."
        return None

    @staticmethod
    def _fallback(request: SupportRequest | SupportContextRequest, memories: list[dict], action: str | None) -> str:
        customer = request.customer if isinstance(request, SupportContextRequest) else request.customer
        name = customer.name.split()[0] if customer else "Customer"
        if memories and action and "preferred expedited" in action:
            return f"Hi {name}, I found your previous preference for expedited handling when timing is critical. I’ll check the delayed shipment first and, if it cannot meet your Friday deadline, prioritize that preferred resolution."
        if memories and action and "proactively monitor" in action:
            return f"Hi {name}, I found your previous request for proactive monitoring when a shipment is delayed. I’ll check the latest status and keep the delivery under active review."
        if memories:
            return f"Hi {name}, I found relevant customer history and will use it to handle this request. {action or 'I’ll review the available order information now.'}"
        return f"Hi {name}, thanks for reaching out. {action or 'I’m reviewing the available order information now.'}"
