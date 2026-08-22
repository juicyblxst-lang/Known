from __future__ import annotations

import os

import httpx
from fastapi import APIRouter, Depends, HTTPException, Query

from .auth import AuthContext, require_auth
from .memory import SibylMemory
from .models import ActionRequest, ActionResponse
from .store import StructuredStore
from .supabase_sessions import SupabaseSessionStore
from .workspace import WorkspaceResponse

router = APIRouter(prefix="/api")
store = StructuredStore()
memory = SibylMemory()
sessions = SupabaseSessionStore()


def upstream_error() -> HTTPException:
    return HTTPException(status_code=502, detail="Upstream data service unavailable")


@router.get("/config")
def get_public_config() -> dict[str, str]:
    return {"supabase_url": os.getenv("SUPABASE_URL", ""), "supabase_anon_key": os.getenv("SUPABASE_ANON_KEY", "")}


@router.get("/customers")
async def get_customers(auth: AuthContext = Depends(require_auth)) -> list[dict]:
    try:
        return store.customers(auth.business_id)
    except (httpx.HTTPError, ValueError):
        raise upstream_error()


@router.get("/workspace/{customer_id}", response_model=WorkspaceResponse)
async def get_workspace(customer_id: str, memory_query: str = Query("customer history"), auth: AuthContext = Depends(require_auth)) -> WorkspaceResponse:
    try:
        customer = store.customer(customer_id, auth.business_id)
        if customer is None:
            raise HTTPException(status_code=404, detail="customer not found")
        orders = store.orders(customer_id, auth.business_id)
    except HTTPException:
        raise
    except (httpx.HTTPError, ValueError):
        raise upstream_error()
    retrieved = memory.search(auth.business_id, customer_id, memory_query)
    return WorkspaceResponse(customer=customer, orders=orders, memory=retrieved.memories, memory_available=retrieved.available)


@router.post("/actions", response_model=ActionResponse)
async def execute_action(request: ActionRequest, auth: AuthContext = Depends(require_auth)) -> ActionResponse:
    customer = store.customer(request.customer_id, auth.business_id)
    if customer is None:
        raise HTTPException(status_code=404, detail="customer not found")
    status = {"cancel_order": "cancelled", "mark_return_requested": "return_requested", "mark_refund_requested": "refund_requested"}[request.action]
    try:
        order = store.update_order_status(request.order_id, request.customer_id, auth.business_id, status)
    except LookupError as exc:
        raise HTTPException(status_code=404, detail="order not found") from exc
    except (httpx.HTTPError, RuntimeError):
        raise upstream_error()
    written, _ = memory.record_event(auth.business_id, request.customer_id, "support_action", {"action": request.action, "order_id": request.order_id, "status": status})
    return ActionResponse(action=request.action, order=order, memory_written=written)


@router.get("/sessions/{session_id}")
async def get_conversation_session(session_id: str, customer_id: str, auth: AuthContext = Depends(require_auth)) -> dict:
    if not sessions.configured:
        raise HTTPException(status_code=503, detail="Durable conversation persistence is not configured")
    try:
        session = sessions.get(session_id, customer_id, auth.business_id)
    except (httpx.HTTPError, ValueError):
        raise upstream_error()
    if session is None:
        raise HTTPException(status_code=404, detail="session not found")
    return {"session_id": session.id, "customer_id": session.customer_id, "messages": [message.model_dump() for message in session.messages], "created_at": session.created_at, "updated_at": session.updated_at, "persistence": "supabase"}
