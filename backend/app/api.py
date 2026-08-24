from __future__ import annotations

import logging
import os

import httpx
from fastapi import APIRouter, Depends, HTTPException, Query, Request
from fastapi.responses import RedirectResponse
from pydantic import BaseModel

from .auth import AuthContext, require_auth
from .csv_import import inspect_and_build
from .memory import SibylMemory
from .models import ActionRequest, ActionResponse
from .shopify import authorization_url, consume_oauth_state, create_oauth_state, exchange_code, installation, installation_by_shop, save_installation, sync_shop, validate_shop_domain, verify_oauth_hmac, verify_webhook, webhook_claim, webhook_complete, webhook_fail
from .shopify_webhooks import register_webhooks
from .store import StructuredStore
from .supabase_sessions import SupabaseSessionStore
from .workspace import WorkspaceResponse

logger = logging.getLogger("known.shopify")
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


@router.get("/search")
async def search_workspace(q: str = Query("", min_length=1, max_length=120), auth: AuthContext = Depends(require_auth)) -> dict[str, list[dict]]:
    try:
        return store.search(auth.business_id, q)
    except (httpx.HTTPError, ValueError):
        raise upstream_error()


class CSVImportRequest(BaseModel):
    csv_text: str
    file_name: str | None = None


@router.post("/imports")
async def list_imports(auth: AuthContext = Depends(require_auth)) -> list[dict]:
    try:
        return store.imports(auth.business_id)
    except (httpx.HTTPError, ValueError):
        raise upstream_error()


@router.post("/imports/csv/inspect")
async def inspect_csv(request: CSVImportRequest, auth: AuthContext = Depends(require_auth)) -> dict:
    try:
        result = inspect_and_build(request.csv_text)
        return {key: value for key, value in result.items() if key not in {"customers", "orders"}} | {"status": "ready"}
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc


@router.post("/imports/csv/commit")
async def commit_csv(request: CSVImportRequest, auth: AuthContext = Depends(require_auth)) -> dict[str, object]:
    try:
        result = inspect_and_build(request.csv_text)
        counts = store.import_csv_records(auth.business_id, result["customers"], result["orders"])
        import_row = store.create_import(auth.business_id, request.file_name or "customer-import.csv", counts["customers"], counts["orders"])
        memory_counts = memory.import_customer_history(auth.business_id, result["customers"], result["orders"])
        if memory_counts["memories"] != len(result["customers"]):
            raise RuntimeError("Customer memory could not be fully initialized")
        return {"status": "complete", **counts, **memory_counts, "memory_ready": True, "import_id": import_row.get("id"), "first_customer_id": result["customers"][0]["id"] if result["customers"] else None}
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    except (httpx.HTTPError, RuntimeError) as exc:
        raise upstream_error() from exc


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
    frontend = os.getenv("KNOWN_PUBLIC_URL", "/").rstrip("/") or "/"
    try:
        params = {key: value for key, value in request.query_params.items()}
        shop_domain = validate_shop_domain(params.get("shop", ""))
        if not verify_oauth_hmac(params):
            raise HTTPException(status_code=401, detail="Invalid Shopify OAuth signature")
        if params.get("error"):
            raise HTTPException(status_code=400, detail="Shopify authorization was not completed")
        code, state = params.get("code"), params.get("state")
        if not code or not state:
            raise HTTPException(status_code=400, detail="Missing Shopify OAuth parameters")
        state_data = consume_oauth_state(state, shop_domain)
        token_data = exchange_code(shop_domain, code)
        save_installation(state_data["business_id"], shop_domain, token_data)
        try:
            register_webhooks(shop_domain, token_data["access_token"])
        except Exception as exc:
            logger.warning("Shopify webhook registration skipped after successful connection: %s", exc)
        sync_shop(state_data["business_id"], shop_domain)
        return RedirectResponse(url=f"{frontend}/?shopify=connected", status_code=303)
    except HTTPException as exc:
        logger.warning("Shopify OAuth failed: %s", exc.detail)
    except Exception:
        logger.exception("Shopify OAuth callback failed")
    return RedirectResponse(url=f"{frontend}/?shopify=error", status_code=303)


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
    claim = webhook_claim(webhook_id, shop, topic)
    if claim == "processed": return {"status": "duplicate"}
    if claim == "processing": return {"status": "accepted", "sync": "in_progress"}
    current = installation_by_shop(shop)
    if not current:
        webhook_fail(webhook_id, "No active Known installation for Shopify store")
        return {"status": "ignored"}
    try:
        sync_shop(current["business_id"], shop); webhook_complete(webhook_id)
    except Exception as exc:
        webhook_fail(webhook_id, str(exc)); raise HTTPException(status_code=503, detail="Shopify change could not be synchronized") from exc
    return {"status": "accepted", "sync": "complete"}


@router.get("/sessions/{session_id}")
async def get_conversation_session(session_id: str, customer_id: str, auth: AuthContext = Depends(require_auth)) -> dict:
    if not sessions.configured: raise HTTPException(status_code=503, detail="Durable conversation persistence is not configured")
    try: session = sessions.get(session_id, customer_id, auth.business_id)
    except (httpx.HTTPError, ValueError): raise upstream_error()
    if session is None: raise HTTPException(status_code=404, detail="session not found")
    return {"session_id": session.id, "customer_id": session.customer_id, "messages": [message.model_dump() for message in session.messages], "created_at": session.created_at, "updated_at": session.updated_at, "persistence": "supabase"}
