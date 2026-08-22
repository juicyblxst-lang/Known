from __future__ import annotations

import os

import httpx
from fastapi import APIRouter, Depends, HTTPException, Query, Request
from fastapi.responses import RedirectResponse
from pydantic import BaseModel

from .auth import AuthContext, require_auth
from .memory import SibylMemory
from .models import ActionRequest, ActionResponse
from .shopify import authorization_url, consume_oauth_state, create_oauth_state, exchange_code, installation, save_installation, sync_shop, validate_shop_domain, verify_webhook, webhook_seen
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


class ShopifyConnectRequest(BaseModel):
    shop_domain: str


@router.get("/shopify/status")
async def shopify_status(auth: AuthContext = Depends(require_auth)) -> dict:
    connected = installation(auth.business_id)
    return {"connected": bool(connected), "installation": connected}


@router.post("/shopify/connect")
async def shopify_connect(request: ShopifyConnectRequest, auth: AuthContext = Depends(require_auth)) -> dict[str, str]:
    try:
        shop = validate_shop_domain(request.shop_domain)
        state = create_oauth_state(auth.business_id, auth.user_id, shop)
        return {"authorization_url": authorization_url(shop, state)}
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    except RuntimeError as exc:
        raise HTTPException(status_code=503, detail=str(exc)) from exc


@router.post("/shopify/sync")
async def shopify_sync(auth: AuthContext = Depends(require_auth)) -> dict[str, object]:
    current = installation(auth.business_id)
    if not current:
        raise HTTPException(status_code=409, detail="Connect a Shopify store before syncing")
    try:
        counts = sync_shop(auth.business_id, current["shop_domain"])
        return {"status": "complete", **counts}
    except (httpx.HTTPError, RuntimeError) as exc:
        raise upstream_error() from exc
    except ValueError as exc:
        raise HTTPException(status_code=409, detail=str(exc)) from exc


@router.get("/shopify/callback")
async def shopify_callback(shop: str, code: str, state: str, hmac: str | None = None) -> RedirectResponse:
    try:
        shop_domain = validate_shop_domain(shop)
        state_data = consume_oauth_state(state, shop_domain)
        token_data = exchange_code(shop_domain, code)
        save_installation(state_data["business_id"], shop_domain, token_data)
        sync_shop(state_data["business_id"], shop_domain)
        return RedirectResponse(url="/?shopify=connected", status_code=303)
    except Exception:
        return RedirectResponse(url="/?shopify=error", status_code=303)


@router.post("/shopify/webhooks")
async def shopify_webhook(request: Request) -> dict[str, str]:
    body = await request.body()
    if not verify_webhook(body, request.headers.get("X-Shopify-Hmac-Sha256")):
        raise HTTPException(status_code=401, detail="Invalid Shopify webhook signature")
    shop = request.headers.get("X-Shopify-Shop-Domain", "").lower()
    topic = request.headers.get("X-Shopify-Topic", "")
    webhook_id = request.headers.get("X-Shopify-Webhook-Id", "")
    if not shop or not topic:
        raise HTTPException(status_code=400, detail="Missing Shopify webhook headers")
    if webhook_seen(webhook_id, shop, topic):
        return {"status": "duplicate"}
    rows = __import__("backend.app.shopify", fromlist=["_db_get"])._db_get("shopify_installations", {"shop_domain": f"eq.{shop}", "limit": "1"})
    if not rows:
        return {"status": "ignored"}
    try:
        sync_shop(rows[0]["business_id"], shop)
    except Exception:
        # The event is acknowledged after signature validation; reconciliation/sync can retry later.
        return {"status": "accepted", "sync": "deferred"}
    return {"status": "accepted", "sync": "complete"}


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
