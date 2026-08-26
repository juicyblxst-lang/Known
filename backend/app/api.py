from __future__ import annotations
import os
import httpx
from fastapi import APIRouter, Depends, HTTPException, Query, UploadFile, File
from fastapi.responses import RedirectResponse
from .auth import AuthContext, require_auth
from .models import ActionRequest, ActionResponse
from .store import StructuredStore
from .supabase_sessions import SupabaseSessionStore
from .workspace import WorkspaceResponse
from .durable_memory import configured_memory
from .importer import import_csv
from .gmail import GmailIntegration
from .integrations import IntegrationStore, process_gmail_messages
from .production_agent import KnownAgent

router = APIRouter(prefix="/api")
store = StructuredStore(); memory = configured_memory(); sessions = SupabaseSessionStore(); integrations = IntegrationStore(); gmail = GmailIntegration(); agent = KnownAgent(memory=memory)

def upstream_error() -> HTTPException: return HTTPException(status_code=502, detail="Upstream data service unavailable")

@router.get("/config")
def get_public_config() -> dict[str, str]: return {"supabase_url": os.getenv("SUPABASE_URL", ""), "supabase_anon_key": os.getenv("SUPABASE_ANON_KEY", "")}

@router.get("/customers")
async def get_customers(auth: AuthContext = Depends(require_auth)) -> list[dict]:
    try: return store.customers(auth.business_id)
    except (httpx.HTTPError, ValueError): raise upstream_error()

@router.get("/workspace/{customer_id}", response_model=WorkspaceResponse)
async def get_workspace(customer_id: str, memory_query: str = Query("customer history"), auth: AuthContext = Depends(require_auth)) -> WorkspaceResponse:
    try:
        customer = store.customer(customer_id, auth.business_id)
        if customer is None: raise HTTPException(status_code=404, detail="customer not found")
        orders = store.orders(customer_id, auth.business_id)
    except HTTPException: raise
    except (httpx.HTTPError, ValueError): raise upstream_error()
    retrieved = memory.search(auth.business_id, customer_id, memory_query)
    return WorkspaceResponse(customer=customer, orders=orders, memory=retrieved.memories, memory_available=retrieved.available)

@router.post("/import/csv")
async def upload_customer_csv(file: UploadFile = File(...), auth: AuthContext = Depends(require_auth)) -> dict:
    if not (file.filename or "").lower().endswith(".csv"): raise HTTPException(status_code=400, detail="CSV file required")
    try: return import_csv(await file.read(), auth.business_id, store)
    except ValueError as exc: raise HTTPException(status_code=400, detail=str(exc)) from exc
    except httpx.HTTPError as exc: raise upstream_error() from exc

@router.get("/integrations/gmail/status")
async def gmail_status(auth: AuthContext = Depends(require_auth)) -> dict:
    connection = integrations.connection(auth.business_id)
    return {"configured": gmail.configured, "connected": bool(connection), "email": (connection or {}).get("external_account_id")}

@router.get("/integrations/gmail/connect")
async def gmail_connect(auth: AuthContext = Depends(require_auth)) -> RedirectResponse:
    if not gmail.configured: raise HTTPException(status_code=503, detail="Google OAuth is not configured")
    return RedirectResponse(gmail.authorize_url(gmail.state(auth.business_id)))

@router.get("/integrations/gmail/callback")
async def gmail_callback(code: str | None = None, state: str | None = None, error: str | None = None):
    if error: return RedirectResponse("/?gmail=error")
    if not code or not state: raise HTTPException(status_code=400, detail="Missing OAuth callback parameters")
    try:
        business_id = gmail.verify_state(state); token = gmail.exchange(code); profile = gmail.profile(token["access_token"]); integrations.save_connection(business_id, token, profile)
    except (ValueError, httpx.HTTPError) as exc: raise HTTPException(status_code=400, detail="Gmail connection failed") from exc
    return RedirectResponse("/?gmail=connected")

@router.post("/integrations/gmail/sync")
async def gmail_sync(auth: AuthContext = Depends(require_auth)) -> dict:
    connection = integrations.connection(auth.business_id)
    if not connection: raise HTTPException(status_code=409, detail="Gmail is not connected")
    try: return process_gmail_messages(auth.business_id, connection, agent, store, sessions, integrations, gmail)
    except httpx.HTTPError as exc: raise HTTPException(status_code=502, detail="Gmail service unavailable") from exc
    except RuntimeError as exc: raise HTTPException(status_code=502, detail=str(exc)) from exc

@router.get("/integrations/gmail/messages")
async def gmail_messages(auth: AuthContext = Depends(require_auth)) -> dict:
    connection = integrations.connection(auth.business_id)
    if not connection: return {"connected": False, "messages": []}
    try:
        token = connection["access_token"]; raw = gmail.list_messages(token, max_results=20); return {"connected": True, "messages": [gmail.parse_message(x) for x in raw]}
    except httpx.HTTPError as exc: raise HTTPException(status_code=502, detail="Gmail service unavailable") from exc

@router.post("/actions", response_model=ActionResponse)
async def execute_action(request: ActionRequest, auth: AuthContext = Depends(require_auth)) -> ActionResponse:
    customer = store.customer(request.customer_id, auth.business_id)
    if customer is None: raise HTTPException(status_code=404, detail="customer not found")
    status = {"cancel_order":"cancelled","mark_return_requested":"return_requested","mark_refund_requested":"refund_requested"}[request.action]
    try: order = store.update_order_status(request.order_id, request.customer_id, auth.business_id, status)
    except LookupError as exc: raise HTTPException(status_code=404, detail="order not found") from exc
    except (httpx.HTTPError, RuntimeError): raise upstream_error()
    written, _ = memory.record_event(auth.business_id, request.customer_id, "support_action", {"action": request.action, "order_id": request.order_id, "status": status})
    return ActionResponse(action=request.action, order=order, memory_written=written)

@router.get("/sessions/{session_id}")
async def get_conversation_session(session_id: str, customer_id: str, auth: AuthContext = Depends(require_auth)) -> dict:
    if not sessions.configured: raise HTTPException(status_code=503, detail="Durable conversation persistence is not configured")
    try: session = sessions.get(session_id, customer_id, auth.business_id)
    except (httpx.HTTPError, ValueError): raise upstream_error()
    if session is None: raise HTTPException(status_code=404, detail="session not found")
    return {"session_id":session.id,"customer_id":session.customer_id,"messages":[message.model_dump() for message in session.messages],"created_at":session.created_at,"updated_at":session.updated_at,"persistence":"supabase"}
