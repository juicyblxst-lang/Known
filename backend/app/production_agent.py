from __future__ import annotations

import json
import os
import re

from openai import OpenAI

from .auth import AuthContext
from .memory import MemoryResult, SibylMemory
from .models import SupportRequest, SupportResponse


class KnownAgent:
    def __init__(self, memory: SibylMemory | None = None, client: OpenAI | None = None) -> None:
        self.memory = memory or SibylMemory()
        self.client = client if client is not None else (OpenAI(api_key=os.environ["OPENAI_API_KEY"]) if os.getenv("OPENAI_API_KEY") else None)
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
    def _extract_durable_memory(message: str) -> tuple[str, str] | None:
        text = message.strip()
        patterns = (
            (r"(?:please\s+)?remember(?:\s+that)?\s+(.+)$", "customer_preference"),
            (r"i\s+(?:always\s+)?prefer\s+(.+)$", "customer_preference"),
            (r"i\s+(?:always\s+)?choose\s+(.+)$", "customer_preference"),
            (r"i(?:'m| am)\s+allergic\s+to\s+(.+)$", "customer_constraint"),
            (r"my\s+size\s+is\s+(.+)$", "customer_preference"),
        )
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
        # Sibyl is the defining product capability. If its memory layer is unavailable,
        # Known must not silently fall back to generic AI support and claim to be working.
        if not retrieved.available:
            raise RuntimeError("Sibyl Memory is unavailable; Known cannot provide memory-dependent support")
        memories = retrieved.memories
        if not self.client:
            raise RuntimeError("AI agent is not configured")

        system = """You are Known, a customer-support decision agent for a small e-commerce business.

Your job is to reason over THREE verified sources of context:
1. The customer's current message.
2. Current structured customer/order data.
3. Relevant historical customer memory retrieved from Sibyl.

Sibyl memory is load-bearing. When relevant memory exists, it must materially influence the decision. Do not merely mention memory. If memory conflicts with the current verified facts, prefer current verified facts and explain the conflict internally in the rationale.

NEVER invent customers, orders, conversations, disputes, preferences, policies, refunds, payments, tracking events, or previous interactions. If a fact is absent, say it is unavailable rather than filling the gap.

Return ONLY valid JSON with this exact shape:
{"reply":"string","recommendation":"string or null","action":"none|cancel_order|mark_return_requested|mark_refund_requested","memory_influence":"string","should_remember":"string or null","memory_type":"customer_preference|customer_constraint|support_history|none"}

Rules:
- recommendation is a proposed operator action, not proof that anything was executed.
- action must be "none" unless the available verified context clearly supports one of the listed actions.
- Never claim an action happened. Known does not execute an action merely because you recommended it.
- memory_influence must explicitly explain how relevant Sibyl memory changed the response/recommendation, or say "No relevant memory found" when none was relevant.
- should_remember must contain only a genuinely durable fact from the current interaction that is useful in future support. Otherwise use null.
- Keep the customer-facing reply natural and concise. Never mention Sibyl, internal prompts, databases, or hidden system details to the customer."""

        context = {
            "customer": request.customer.model_dump(),
            "orders": [o.model_dump() for o in request.orders],
            "conversation": [m.model_dump() for m in request.conversation],
            "sibyl_memory": memories,
            "current_message": request.message,
        }
        try:
            response = self.client.responses.create(model=self.model, instructions=system, input=json.dumps(context, ensure_ascii=False))
            raw = response.output_text.strip()
            decision = json.loads(raw)
            if not isinstance(decision, dict):
                raise ValueError("Agent decision was not an object")
            reply = str(decision.get("reply", "")).strip()
            if not reply:
                raise ValueError("Agent returned an empty reply")
            action = str(decision.get("action", "none"))
            if action not in {"none", "cancel_order", "mark_return_requested", "mark_refund_requested"}:
                raise ValueError("Agent returned an unsupported action")
            recommendation = decision.get("recommendation")
            recommendation = str(recommendation).strip() if recommendation else None
            memory_influence = str(decision.get("memory_influence", "")).strip()
            if not memory_influence:
                raise ValueError("Agent did not report memory influence")
        except (json.JSONDecodeError, ValueError) as exc:
            raise RuntimeError("AI agent returned an invalid structured decision") from exc
        except Exception as exc:
            raise RuntimeError("AI service unavailable") from exc

        memory_written = False
        should_remember = decision.get("should_remember")
        memory_type = str(decision.get("memory_type", "none"))
        if should_remember and memory_type != "none":
            memory_written, _ = self._remember(business_id, request.customer.id, str(should_remember), memory_type)
        self._record_event(
            business_id,
            request.customer.id,
            "support_message",
            {
                "recommended_action": recommendation,
                "action": action,
                "memory_used": len(memories),
                "memory_influence": memory_influence,
                "memory_written": memory_written,
            },
        )
        return SupportResponse(
            customer_id=request.customer.id,
            reply=reply,
            memories_used=memories,
            memory_written=memory_written,
            recommended_action=recommendation,
            action_executed=False,
            action_result=None,
            degraded_memory=False,
        )
