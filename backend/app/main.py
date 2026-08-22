from __future__ import annotations

import os
from pathlib import Path

import httpx
from fastapi import Depends, FastAPI, HTTPException
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import RedirectResponse
from fastapi.staticfiles import StaticFiles

from .agent import KnownAgent
from .api import router
from .auth import AuthContext, require_auth
from .memory import SibylMemory
from .models import Message, SupportContextRequest, SupportRequest, SupportResponse
from .supabase_sessions import SupabaseSessionStore
from .store import StructuredStore

app = FastAPI(title="Known", version="0.6.0")
app.add_middleware(CORSMiddleware, allow_origins=[x.strip() for x in os.getenv("KNOWN_CORS_ORIGINS", "http://localhost:8000").split(",") if x.strip()], allow_credentials=True, allow_methods=["*"], allow_headers=["*"])
app.include_router(router)
agent = KnownAgent(); durable_sessions = SupabaseSessionStore(); store = StructuredStore()

class SupportSessionResponse(SupportResponse):
    session_id: str
    conversation: list[Message]
    persistence: str

@app.get("/health")
def health() -> dict[str, object]:
    return {"status":"ok","service":"known","version":"0.6.0","conversation_persistence":"supabase" if durable_sessions.configured else "unavailable"}

@app.get("/ready")
def ready() -> dict[str, object]:
    sibyl = agent.memory.health() if isinstance(agent.memory, SibylMemory) else {"configured": True}
    checks={
        "frontend":(Path(__file__).resolve().parents[2]/"frontend").exists(),
        "supabase":store.configured and durable_sessions.configured,
        "openai":bool(os.getenv("OPENAI_API_KEY")),
        "sibyl":bool(sibyl.get("configured")),
    }
    return {"status":"ready" if all(checks.values()) else "degraded","checks":checks,"sibyl":sibyl}

@app.post("/api/support",response_model=SupportSessionResponse)
async def support(request: SupportRequest,session_id:str|None=None,auth:AuthContext=Depends(require_auth))->SupportSessionResponse:
    customer_id=request.customer_id
    try:
        customer_data=store.customer(customer_id,auth.business_id)
        if customer_data is None: raise HTTPException(status_code=404,detail="customer not found")
        orders_data=store.orders(customer_id,auth.business_id)
    except HTTPException: raise
    except (httpx.HTTPError,ValueError) as exc: raise HTTPException(status_code=502,detail="Customer data service unavailable") from exc
    if not durable_sessions.configured:
        raise HTTPException(status_code=503,detail="Durable conversation persistence is not configured")
    resolved_session_id=session_id or request.conversation_id or f"{customer_id}:{os.urandom(8).hex()}"
    try:
        session=durable_sessions.get_or_create(resolved_session_id,customer_id,auth.business_id)
    except ValueError as exc: raise HTTPException(status_code=403,detail="session does not belong to customer") from exc
    except httpx.HTTPError as exc: raise HTTPException(status_code=502,detail="Conversation persistence service unavailable") from exc
    context_request=SupportContextRequest(customer=customer_data,message=request.message,conversation=list(session.messages),orders=orders_data)
    user_message=Message(role="user",content=request.message)
    try:
        durable_sessions.append(resolved_session_id,user_message)
    except httpx.HTTPError as exc:
        raise HTTPException(status_code=502,detail="Conversation persistence service unavailable") from exc
    session.messages.append(user_message)
    try:
        result=agent.handle(context_request,auth=auth)
    except RuntimeError as exc:
        raise HTTPException(status_code=502,detail=str(exc)) from exc
    except Exception as exc:
        raise HTTPException(status_code=502,detail="Agent service unavailable") from exc
    assistant_message=Message(role="assistant",content=result.reply)
    try:
        durable_sessions.append(resolved_session_id,assistant_message)
    except httpx.HTTPError as exc:
        raise HTTPException(status_code=502,detail="Conversation persistence service unavailable") from exc
    session.messages.append(assistant_message)
    return SupportSessionResponse(**result.model_dump(),session_id=resolved_session_id,conversation=list(session.messages),persistence="supabase")

@app.get("/api/sessions/{session_id}")
def get_session(session_id:str,customer_id:str,auth:AuthContext=Depends(require_auth))->dict:
    if not durable_sessions.configured:
        raise HTTPException(status_code=503,detail="Durable conversation persistence is not configured")
    try:
        session=durable_sessions.get(session_id,customer_id,auth.business_id)
    except httpx.HTTPError as exc:
        raise HTTPException(status_code=502,detail="Conversation persistence service unavailable") from exc
    if session is None:
        raise HTTPException(status_code=404,detail="session not found")
    return {"session_id":session.id,"customer_id":session.customer_id,"messages":[m.model_dump() for m in session.messages],"created_at":session.created_at,"updated_at":session.updated_at,"persistence":"supabase"}

FRONTEND_DIR=Path(__file__).resolve().parents[2]/"frontend"
if FRONTEND_DIR.exists(): app.mount("/",StaticFiles(directory=FRONTEND_DIR,html=True),name="frontend")
else:
    @app.get("/")
    def frontend_unavailable()->RedirectResponse: return RedirectResponse(url="/health")
