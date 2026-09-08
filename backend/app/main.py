from __future__ import annotations
import asyncio
import logging
import os
from pathlib import Path
import httpx
from fastapi import Depends, FastAPI, HTTPException
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import RedirectResponse
from fastapi.staticfiles import StaticFiles
from .api import router
from .gmail import GmailIntegration
from .gmail_api import router as gmail_router
from .integrations import IntegrationStore, process_gmail_messages
from .settings_api import router as settings_router
from .auth import AuthContext, require_auth
from .models import Message, SupportContextRequest, SupportRequest, SupportResponse
from .production_agent import KnownAgent
from .store import StructuredStore
from .supabase_sessions import SupabaseSessionStore

logger = logging.getLogger("known.main")
app = FastAPI(title="Known", version="0.7.0")
app.add_middleware(CORSMiddleware, allow_origins=[x.strip() for x in os.getenv("KNOWN_CORS_ORIGINS", "http://localhost:8000").split(",") if x.strip()], allow_credentials=True, allow_methods=["*"], allow_headers=["*"])
app.include_router(router); app.include_router(gmail_router); app.include_router(settings_router)
agent = KnownAgent(); durable_sessions = SupabaseSessionStore(); store = StructuredStore(); gmail = GmailIntegration(); integrations = IntegrationStore()
gmail_poller_task: asyncio.Task | None = None

async def _poll_gmail_once() -> None:
    if not integrations.configured or not gmail.configured or not durable_sessions.configured: return
    connections = integrations.connections()
    for connection in connections:
        business_id = connection.get("business_id")
        if not business_id: continue
        try:
            result = await asyncio.to_thread(process_gmail_messages, business_id, connection, agent, store, durable_sessions, integrations, gmail)
            logger.info("Background Gmail poll: business=%s processed=%s matched=%s created=%s failed=%s", business_id, result.get("processed", 0), result.get("matched", 0), result.get("created", 0), result.get("failed", 0))
        except Exception:
            logger.exception("Background Gmail poll failed for business %s", business_id)

async def _gmail_poll_loop() -> None:
    while True:
        try:
            await _poll_gmail_once()
        except Exception:
            logger.exception("Background Gmail poll cycle failed")
        await asyncio.sleep(120)

@app.on_event("startup")
async def start_gmail_poller() -> None:
    global gmail_poller_task
    if gmail_poller_task is None:
        gmail_poller_task = asyncio.create_task(_gmail_poll_loop(), name="known-gmail-poller")
        logger.info("Background Gmail poller started: interval_seconds=120")

@app.on_event("shutdown")
async def stop_gmail_poller() -> None:
    global gmail_poller_task
    if gmail_poller_task is not None:
        gmail_poller_task.cancel()
        try: await gmail_poller_task
        except asyncio.CancelledError: pass
        gmail_poller_task = None

class SupportSessionResponse(SupportResponse):
    session_id: str
    conversation: list[Message]
    persistence: str

@app.get("/health")
def health() -> dict[str, object]: return {"status":"ok","service":"known","version":"0.7.0","conversation_persistence":"supabase" if durable_sessions.configured else "unavailable"}

@app.get("/ready")
def ready() -> dict[str, object]:
    memory = agent.memory.health(); provider = os.getenv("LLM_PROVIDER", "openai").lower()
    llm_ok = bool(os.getenv("DEEPSEEK_API_KEY") or os.getenv("OPENAI_API_KEY")) if provider == "deepseek" else bool(os.getenv("OPENAI_API_KEY"))
    checks={"frontend":(Path(__file__).resolve().parents[2]/"frontend").exists(),"supabase":store.configured and durable_sessions.configured,"llm":llm_ok,"memory":bool(memory.get("configured")) and bool(memory.get("durable_available"))}
    return {"status":"ready" if all(checks.values()) else "degraded","checks":checks,"memory":memory,"sibyl":memory,"llm_provider":provider}

@app.post("/api/support",response_model=SupportSessionResponse)
async def support(request: SupportRequest,session_id:str|None=None,auth:AuthContext=Depends(require_auth))->SupportSessionResponse:
    try:
        customer_data=store.customer(request.customer_id,auth.business_id)
        if customer_data is None: raise HTTPException(status_code=404,detail="customer not found")
        orders_data=store.orders(request.customer_id,auth.business_id)
    except HTTPException: raise
    except (httpx.HTTPError,ValueError) as exc: raise HTTPException(status_code=502,detail="Customer data service unavailable") from exc
    if not durable_sessions.configured: raise HTTPException(status_code=503,detail="Durable conversation persistence is not configured")
    resolved_session_id=session_id or request.conversation_id or f"{request.customer_id}:{os.urandom(8).hex()}"
    try: session=durable_sessions.get_or_create(resolved_session_id,request.customer_id,auth.business_id)
    except ValueError as exc: raise HTTPException(status_code=403,detail="session does not belong to customer") from exc
    except httpx.HTTPError as exc: raise HTTPException(status_code=502,detail="Conversation persistence service unavailable") from exc
    try:
        durable_sessions.append(resolved_session_id,Message(role="user",content=request.message))
        context_request=SupportContextRequest(customer=customer_data,message=request.message,conversation=[*session.messages,Message(role="user",content=request.message)],orders=orders_data)
        result=agent.handle(context_request,auth=auth)
        durable_sessions.append(resolved_session_id,Message(role="assistant",content=result.reply))
    except httpx.HTTPError as exc: raise HTTPException(status_code=502,detail="Conversation persistence service unavailable") from exc
    except RuntimeError as exc: raise HTTPException(status_code=502,detail=str(exc)) from exc
    except Exception as exc: raise HTTPException(status_code=502,detail="Agent service unavailable") from exc
    persisted=durable_sessions.get(resolved_session_id,request.customer_id,auth.business_id)
    if persisted is None: raise HTTPException(status_code=502,detail="Conversation persistence verification failed")
    return SupportSessionResponse(**result.model_dump(),session_id=resolved_session_id,conversation=persisted.messages,persistence="supabase")

FRONTEND_DIR=Path(__file__).resolve().parents[2]/"frontend"
if FRONTEND_DIR.exists(): app.mount("/",StaticFiles(directory=FRONTEND_DIR,html=True),name="frontend")
else:
    @app.get("/")
    def frontend_unavailable()->RedirectResponse: return RedirectResponse(url="/health")
