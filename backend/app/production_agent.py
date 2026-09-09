from __future__ import annotations

import os
import re
from typing import Any

from openai import OpenAI

from .auth import AuthContext
from .models import SupportContextRequest, SupportRequest, SupportResponse


class KnownAgent:
    """Production support agent. Sibyl is a mandatory dependency for every request."""

    def __init__(self, memory: Any | None = None, client: OpenAI | None = None) -> None:
        if memory is None:
            from .durable_memory import configured_memory
            memory = configured_memory()
        self.memory = memory
        self.provider = os.getenv("LLM_PROVIDER", "openai").lower()
        if client is not None:
            self.client = client
            self.model = os.getenv("DEEPSEEK_MODEL", "deepseek-chat") if self.provider == "deepseek" else os.getenv("OPENAI_MODEL", "gpt-5-mini")
        elif self.provider == "deepseek":
            key = os.getenv("DEEPSEEK_API_KEY") or os.getenv("OPENAI_API_KEY")
            self.client = OpenAI(api_key=key, base_url=os.getenv("DEEPSEEK_BASE_URL", "https://api.deepseek.com")) if key else None
            self.model = os.getenv("DEEPSEEK_MODEL", "deepseek-chat")
        else:
            key = os.getenv("OPENAI_API_KEY")
            self.client = OpenAI(api_key=key) if key else None
            self.model = os.getenv("OPENAI_MODEL", "gpt-5-mini")

    @staticmethod
    def _customer_id(request: SupportRequest | SupportContextRequest) -> str:
        if isinstance(request, SupportContextRequest): return request.customer.id
        return request.customer.id if request.customer is not None else request.customer_id  # type: ignore[return-value]

    @staticmethod
    def _customer_payload(request: SupportRequest | SupportContextRequest) -> dict:
        if isinstance(request, SupportContextRequest): return request.customer.model_dump()
        return request.customer.model_dump() if request.customer is not None else {"id": request.customer_id}

    @staticmethod
    def _orders(request: SupportRequest | SupportContextRequest) -> list[dict]: return [o.model_dump() for o in getattr(request, "orders", [])]
    @staticmethod
    def _conversation(request: SupportRequest | SupportContextRequest) -> list[dict]: return [m.model_dump() for m in getattr(request, "conversation", [])]

    def _search_memory(self, business_id: str, customer_id: str, query: str): return self.memory.search(business_id, customer_id, query)
    def _remember(self, business_id: str, customer_id: str, content: str, memory_type: str): return self.memory.remember(business_id, customer_id, content, memory_type)
    def _record_event(self, business_id: str, customer_id: str, kind: str, body: dict): return self.memory.record_event(business_id, customer_id, kind, body)

    @staticmethod
    def _extract_durable_memory(message: str) -> tuple[str, str] | None:
        """Extract explicit customer-authored durable facts without inventing memory."""
        text = " ".join(message.strip().split()).rstrip(".")
        if not text:
            return None
        patterns: tuple[tuple[str, str], ...] = (
            (r"(?:please\s+)?remember(?:\s+that)?\s+(.+)$", "customer_preference"),
            (r"i\s+(?:always\s+)?prefer\s+(.+)$", "customer_preference"),
            (r"i\s+(?:usually\s+)?choose\s+(.+)$", "customer_preference"),
            (r"i\s+(?:really\s+)?like\s+(.+)$", "customer_preference"),
            (r"i\s+(?:really\s+)?love\s+(.+)$", "customer_preference"),
            (r"i\s+(?:really\s+)?don(?:'t|t)\s+like\s+(.+)$", "customer_preference"),
            (r"i\s+(?:always\s+)?avoid\s+(.+)$", "customer_constraint"),
            (r"i\s+(?:never\s+)?want\s+(.+)$", "customer_preference"),
            (r"i\s+(?:really\s+)?don(?:'t|t)\s+want\s+(.+)$", "customer_constraint"),
            (r"i(?:'m| am)\s+allergic\s+to\s+(.+)$", "customer_constraint"),
            (r"i(?:'m| am)\s+(?:sensitive|intolerant)\s+to\s+(.+)$", "customer_constraint"),
            (r"my\s+size\s+is\s+(.+)$", "customer_preference"),
            (r"my\s+(?:usual|preferred)\s+size\s+is\s+(.+)$", "customer_preference"),
            (r"(?:please\s+)?(?:ship|send)\s+my\s+orders?\s+(.+)$", "customer_preference"),
            (r"(?:please\s+)?contact\s+me\s+(?:by|via)\s+(.+)$", "customer_preference"),
            (r"(?=.*\b(?:never|don(?:'t|t)|do not|avoid)\b)(?=.*\b(?:replace\w*|replacement\w*|ship\w*|send\w*)\b)(?=.*\b(?:automatically|auto[- ]?ship|without\s+(?:my\s+)?(?:approval|permission|asking)|confirm(?:ation)?|ask\s+me|check\s+with\s+me)\b)(.{1,1000})$", "customer_constraint"),
            (r"(.{1,500}\b(?:confirm|ask|check)\s+(?:with\s+me\s+)?first\b.{0,500}\b(?:replace|replacement|ship|send)\b.{0,300})$", "customer_constraint"),
            (r"(?=.*\b(?:ship|send|reship|re-?ship)\w*\b)(?=.*\b(?:\d{1,2}(?:st|nd|rd|th)?\s+(?:of\s+)?(?:jan|feb|mar|apr|may|jun|jul|aug|sep|sept|oct|nov|dec)[a-z]*|(?:jan|feb|mar|apr|may|jun|jul|aug|sep|sept|oct|nov|dec)[a-z]*\s+\d{1,2}(?:st|nd|rd|th)?)\b)(.{1,1500})$", "shipping_instruction"),
            (r"(?=.*\b(?:new\s+address|different\s+address|office|workplace|address\s+is)\b)(?=.*\b(?:ship|send|reship|re-?ship)\w*\b)(.{1,1500})$", "shipping_instruction"),
        )
        for pattern, memory_type in patterns:
            match = re.match(pattern, text, re.IGNORECASE)
            if match:
                value = match.group(1).strip()
                if value and len(value) <= 500:
                    return f"Customer {memory_type.replace('_', ' ')}: {value}.", memory_type
        return None

    def _generate(self, system: str, context: dict[str, Any]) -> str:
        if not self.client: raise RuntimeError("AI agent is not configured")
        try:
            if self.provider == "deepseek":
                response = self.client.chat.completions.create(model=self.model, messages=[{"role": "system", "content": system}, {"role": "user", "content": str(context)}])
                return (response.choices[0].message.content or "").strip()
            response = self.client.responses.create(model=self.model, instructions=system, input=str(context)); return response.output_text.strip()
        except Exception as exc: raise RuntimeError("AI service unavailable") from exc

    def handle(self, request: SupportRequest | SupportContextRequest, auth: AuthContext | None = None) -> SupportResponse:
        business_id = auth.business_id if auth else os.getenv("KNOWN_LOCAL_BUSINESS_ID", "local-development")
        customer_id = self._customer_id(request)
        retrieved = self._search_memory(business_id, customer_id, request.message)
        if not retrieved.available:
            error = getattr(retrieved, "error", None)
            raise RuntimeError(f"Sibyl Memory is unavailable: {error or 'unknown error'}")
        memories = retrieved.memories
        action = self._action(request.message, memories)
        system = """You are Known, a customer-support agent for a small e-commerce business.
Relevant durable customer memory is required context for Known's support decisions.
Use relevant memory as decision-making context, not merely as a citation.
Never invent customer history. Give a concise, empathetic answer. Treat order data as current facts and memory as historical context.
If memory establishes a relevant preference, shipping instruction, prior support decision, or newly supplied customer detail, adapt the proposed resolution to it.
When a customer message is vague, use the customer's stored history to explain what is known and ask only the next useful question.
Do not repeat information unnecessarily. Apologize only when the situation warrants it.
Never claim an operational action has happened unless the backend has actually executed it."""
        context = {"customer": self._customer_payload(request), "orders": self._orders(request), "conversation": self._conversation(request), "retrieved_memory": memories, "decision_and_action": action, "current_message": request.message}
        raw_reply = self._generate(system, context)
        reply = raw_reply
        try:
            parsed = __import__("json").loads(raw_reply)
            if isinstance(parsed, dict) and isinstance(parsed.get("reply"), str): reply = parsed["reply"]
        except (ValueError, TypeError):
            pass

        memory_written = False
        extracted = self._extract_durable_memory(request.message)
        if extracted:
            content, memory_type = extracted
            memory_written, error = self._remember(business_id, customer_id, content, memory_type)
            if not memory_written: raise RuntimeError(f"Customer memory persistence failed: {error}")

        interaction = f"Customer support interaction. Customer message: {request.message.strip()}\nKnown response: {reply.strip()}"
        interaction_ok, interaction_error = self._remember(business_id, customer_id, interaction[:4000], "support_history")
        if not interaction_ok: raise RuntimeError(f"Customer support history persistence failed: {interaction_error}")
        memory_written = memory_written or interaction_ok

        event_written, event_error = self._record_event(business_id, customer_id, "support_message", {"recommended_action": action, "memory_used": len(memories), "memory_written": memory_written})
        if not event_written: raise RuntimeError(f"Customer memory event persistence failed: {event_error}")
        return SupportResponse(customer_id=customer_id, reply=reply, memories_used=memories, memory_written=memory_written, recommended_action=action, degraded_memory=False)

    @staticmethod
    def _action(message: str, memories: list[dict]) -> str | None:
        text = message.lower()
        memory_text = " ".join(str(m.get("content", "")) for m in memories).lower()
        if any(word in text for word in ("refund", "return", "cancel")): return "Review order eligibility and offer the applicable return/refund workflow."
        if any(word in text for word in ("replace", "replacement", "damaged")) and any(x in memory_text for x in ("automatically", "auto-ship", "auto ship", "without my approval", "without approval", "confirm first", "ask me first")):
            return "Confirm the customer's approval before arranging a replacement; do not auto-ship it."
        delivery_issue = any(word in text for word in ("late", "where is", "tracking", "delivery", "not received", "didn't receive", "did not receive")) or bool(re.search(r"\b(?:haven't|have not|didn't|did not)\s+(?:(?:yet|still)\s+)?(?:i\s+)?(?:received|gotten|got)\b", text))
        if delivery_issue:
            has_recorded_shipping = any(term in memory_text for term in ("shipping instruction", "new address", "different address", "shipping details")) or bool(re.search(r"\b(?:jan|feb|mar|apr|may|jun|jul|aug|sep|sept|oct|nov|dec)[a-z]*\s+\d{1,2}\b|\b\d{1,2}(?:st|nd|rd|th)?\s+(?:of\s+)?(?:jan|feb|mar|apr|may|jun|jul|aug|sep|sept|oct|nov|dec)[a-z]*\b", memory_text))
            if has_recorded_shipping:
                return "Use the customer's previously recorded shipping timing and destination to explain the current delivery status, then ask whether they want to change the schedule."
            if any(x in memory_text for x in ("expedited", "urgent", "time-sensitive")): return "Prioritize the latest shipment check and reflect the customer's previous expedited preference."
            if any(x in memory_text for x in ("monitor", "previous delayed")): return "Check the latest shipment status and proactively monitor the delivery, reflecting the customer's previous support preference."
            return "Check the latest shipment status and provide the tracking update."
        return None
