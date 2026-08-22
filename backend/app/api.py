from __future__ import annotations

import os

import httpx
from fastapi import APIRouter, Depends, HTTPException, Query, Request
from fastapi.responses import RedirectResponse
from pydantic import BaseModel

from .auth import AuthContext, require_auth
from .memory import SibylMemory
from .models import ActionRequest, ActionResponse
from .shopify import authorization_url, consume_oauth_state, create_oauth_state, exchange_code, installation, installation_by_shop, save_installation, sync_shop, validate_shop_domain, verify_oauth_hmac, verify_webhook, webhook_seen
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
    # Never pretend a local Supabase status change is a real Shopify action.
    # Real refunds/returns/cancellations must use Shopify's authorized APIs.
    raise HTTPException(status_code=501, detail="Commerce actions are not enabled yet. Known will not fabricate a Shopify action.")


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
async def shopify_callback(request: Request) -> RedirectResponse:
    try:
        params = {key: value for key, value in request.query_params.items()}
        shop_domain = validate_shop_domain(params.get("shop", ""))
        if not verify_oauth_hmac(params):
            raise HTTPException(status_code=401, detail="Invalid Shopify OAuth signature")
        if params.get("error"):
            raise HTTPException(status_code=400, detail="Shopify authorization was not completed")
        code = params.get("code")
        state = params.get("state")
        if not code or not state:
            raise HTTPException(status_code=400, detail="Missing Shopify authorization parameters")
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
    current = installation_by_shop(shop)
    if not current:
        return {"status": "ignored"}
    try:
        sync_shop(current["business_id"], shop)
    except Exception:
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
