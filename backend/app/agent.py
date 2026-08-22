from __future__ import annotations

import os
from openai import OpenAI

from .memory import SibylMemory
from .models import SupportRequest, SupportResponse


class KnownAgent:
    def __init__(self, memory: SibylMemory | None = None) -> None:
        self.memory = memory or SibylMemory()
        self.client = OpenAI(api_key=os.environ["OPENAI_API_KEY"]) if os.getenv("OPENAI_API_KEY") else None
        self.model = os.getenv("OPENAI_MODEL", "gpt-5-mini")

    def handle(self, request: SupportRequest) -> SupportResponse:
        memory_query = request.message
        retrieved = self.memory.search(request.customer.id, memory_query)
        memories = retrieved.memories

        system = """You are Known, a customer-support agent for a small e-commerce business.
Use durable customer memory only when it is relevant to the current request. Never invent
customer history. Give a concise, empathetic answer and recommend one concrete next action
when appropriate. Treat order data as current structured facts and memory as historical context.
"""
        context = {
            "customer": request.customer.model_dump(),
            "orders": [o.model_dump() for o in request.orders],
            "conversation": [m.model_dump() for m in request.conversation],
            "retrieved_memory": memories,
            "current_message": request.message,
        }

        if self.client:
            response = self.client.responses.create(
                model=self.model,
                instructions=system,
                input=str(context),
            )
            reply = response.output_text.strip()
        else:
            reply = self._fallback(request, memories)

        # Persist only a durable preference/fact that is explicitly present in the
        # customer's message. This avoids turning every support message into memory.
        memory_written = False
        lower = request.message.lower()
        preference_markers = ("i prefer", "i always", "please remember", "my size is", "i'm allergic", "i am allergic")
        if any(marker in lower for marker in preference_markers):
            ok, _ = self.memory.remember(request.customer.id, request.message, "customer_preference")
            memory_written = ok

        action = self._action(request)
        return SupportResponse(
            customer_id=request.customer.id,
            reply=reply,
            memories_used=memories,
            memory_written=memory_written,
            recommended_action=action,
            degraded_memory=not retrieved.available,
        )

    @staticmethod
    def _action(request: SupportRequest) -> str | None:
        if any(word in request.message.lower() for word in ("refund", "return", "cancel")):
            return "Review order eligibility and offer the applicable return/refund workflow."
        if any(word in request.message.lower() for word in ("late", "where is", "tracking", "delivery")):
            return "Check the latest shipment status and provide the tracking update."
        return None

    @staticmethod
    def _fallback(request: SupportRequest, memories: list[dict]) -> str:
        name = request.customer.name.split()[0] or request.customer.name
        history = " I found relevant history and will use it here." if memories else ""
        return f"Hi {name}, thanks for reaching out.{history} I’m reviewing your request and the available order information now."
