from __future__ import annotations

import os
import re
from typing import Any

from openai import OpenAI

from .auth import AuthContext
from .models import SupportRequest, SupportResponse


class KnownAgent:
    def __init__(self, memory: Any | None = None, client: OpenAI | None = None) -> None:
        if memory is None:
            from .durable_memory import configured_memory
            memory = configured_memory()
        self.memory = memory
        if client is not None:
            self.client = client
        else:
            provider = os.getenv("LLM_PROVIDER", "openai").lower()
            if provider == "deepseek":
                key = os.getenv("DEEPSEEK_API_KEY") or os.getenv("OPENAI_API_KEY")
                base_url = os.getenv("DEEPSEEK_BASE_URL", "https://api.deepseek.com")
                self.client = OpenAI(api_key=key, base_url=base_url) if key else None
                self.model = os.getenv("DEEPSEEK_MODEL", "deepseek-chat")
            else:
                key = os.getenv("OPENAI_API_KEY")
                self.client = OpenAI(api_key=key) if key else None
                self.model = os.getenv("OPENAI_MODEL", "gpt-5-mini")
        if not hasattr(self, "model"):
            self.model = os.getenv("OPENAI_MODEL", "gpt-5-mini")

    def _search_memory(self, business_id: str, customer_id: str, query: str):
        return self.memory.search(business_id, customer_id, query)

    def _remember(self, business_id: str, customer_id: str, content: str, memory_type: str) -> tuple[bool, str]:
        return self.memory.remember(business_id, customer_id, content, memory_type)

    def _record_event(self, business_id: str, customer_id: str, kind: str, body: dict) -> tuple[bool, str]:
        return self.memory.record_event(business_id, customer_id, kind, body)

    @staticmethod
    def _extract_durable_memory(message: str) -> tuple[str, str] | None:
        text = message.strip()
        patterns = ((r"(?:please\s+)?remember(?:\s+that)?\s+(.+)$", "customer_preference"), (r"i\s+(?:always\s+)?prefer\s+(.+)$", "customer_preference"), (r"i\s+(?:always\s+)?choose\s+(.+)$", "customer_preference"), (r"i(?:'m| am)\s+allergic\s+to\s+(.+)$", "customer_constraint"), (r"my\s+size\s+is\s+(.+)$", "customer_preference"))
        for pattern, memory_type in patterns:
            match = re.match(pattern, text, re.IGNORECASE)
            if match:
                value = match.group(1).strip().rstrip(".")
                if value:
                    return f"Customer {memory_type.replace('_', ' ')}: {value}.", memory_type
        return None

    def handle(self, request: SupportRequest, auth: AuthContext | None = None) -> SupportResponse:
        business_id = auth.business_id if auth else os.getenv("KNOWN_LOCAL_BUSINESS_ID", "local-development")
        retrieved = self._search_memory(business_id, request.customer.id, request.message)
        if not retrieved.available:
            raise RuntimeError(f"Customer memory unavailable: {retrieved.error or 'unknown error'}")
        memories = retrieved.memories
        action = self._action(request, memories)
        if not self.client:
            raise RuntimeError("AI agent is not configured")
        system = """You are Known, a customer-support agent for a small e-commerce business.
Relevant durable customer memory is required context for Known's support decisions.
Use relevant memory as decision-making context, not merely as a citation.
Never invent customer history. Give a concise, empathetic answer. Treat order data as current facts and memory as historical context.
If memory establishes a relevant preference or prior support pattern, adapt the proposed resolution to it.
Never claim an operational action has happened unless the backend has actually executed it."""
        context = {"customer": request.customer.model_dump(), "orders": [o.model_dump() for o in request.orders], "conversation": [m.model_dump() for m in request.conversation], "retrieved_memory": memories, "decision_and_action": action, "current_message": request.message}
        try:
            response = self.client.responses.create(model=self.model, instructions=system, input=str(context))
            reply = response.output_text.strip()
        except Exception as exc:
            raise RuntimeError("AI service unavailable") from exc
        memory_written = False
        extracted = self._extract_durable_memory(request.message)
        if extracted:
            content, memory_type = extracted
            memory_written, error = self._remember(business_id, request.customer.id, content, memory_type)
            if not memory_written:
                raise RuntimeError(f"Customer memory persistence failed: {error}")
        event_written, event_error = self._record_event(business_id, request.customer.id, "support_message", {"recommended_action": action, "memory_used": len(memories)})
        if not event_written:
            raise RuntimeError(f"Customer memory event persistence failed: {event_error}")
        return SupportResponse(customer_id=request.customer.id, reply=reply, memories_used=memories, memory_written=memory_written, recommended_action=action, degraded_memory=False)

    @staticmethod
    def _action(request: SupportRequest, memories: list[dict]) -> str | None:
        text = request.message.lower(); memory_text = " ".join(str(m.get("content", "")) for m in memories).lower()
        if any(word in text for word in ("refund", "return", "cancel")):
            return "Review order eligibility and offer the applicable return/refund workflow."
        if any(word in text for word in ("late", "where is", "tracking", "delivery")):
            if any(x in memory_text for x in ("expedited", "urgent", "time-sensitive")):
                return "Prioritize the latest shipment check and reflect the customer's previous expedited preference."
            if any(x in memory_text for x in ("monitor", "previous delayed")):
                return "Check the latest shipment status and proactively monitor the delivery, reflecting the customer's previous support preference."
            return "Check the latest shipment status and provide the tracking update."
        return None
