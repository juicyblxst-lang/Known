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
from .models import Message, SupportRequest, SupportResponse
from .session_store import InMemorySessionStore
from .supabase_sessions import SupabaseSessionStore

app = FastAPI(title="Known", version="0.5.0")
app.add_middleware(
    CORSMiddleware,
    allow_origins=[x.strip() for x in os.getenv("KNOWN_CORS_ORIGINS", "http://localhost:8000").split(",") if x.strip()],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)
app.include_router(router)
agent = KnownAgent()
local_sessions = InMemorySessionStore()
durable_sessions = SupabaseSessionStore()


class SupportSessionResponse(SupportResponse):
    session_id: str
    conversation: list[Message]
    persistence: str


@app.get("/health")
def health() -> dict[str, str]:
    return {
        "status": "ok",
        "service": "known",
        "version": "0.5.0",
        "conversation_persistence": "supabase" if durable_sessions.configured else "local-development",
    }


@app.get("/ready")
def ready() -> dict[str, object]:
    checks = {
        "frontend": (Path(__file__).resolve().parents[2] / "frontend").exists(),
        "supabase": durable_sessions.configured,
        "openai": bool(os.getenv("OPENAI_API_KEY")),
    }
    return {"status": "ready" if all(checks.values()) else "degraded", "checks": checks}


@app.post("/api/support", response_model=SupportSessionResponse)
async def support(
    request: SupportRequest,
    session_id: str | None = None,
    auth: AuthContext = Depends(require_auth),
) -> SupportSessionResponse:
    resolved_session_id = session_id or f"{request.customer.id}:default"

    if durable_sessions.configured:
        try:
            session = durable_sessions.get_or_create(resolved_session_id, request.customer.id, auth.business_id)
        except ValueError as exc:
            raise HTTPException(status_code=403, detail="session does not belong to customer") from exc
        except httpx.HTTPError as exc:
            raise HTTPException(status_code=502, detail="Conversation persistence service unavailable") from exc
        append = lambda message: durable_sessions.append(resolved_session_id, message)
        persistence = "supabase"
    else:
        try:
            session = local_sessions.get_or_create(resolved_session_id, request.customer.id)
        except ValueError as exc:
            raise HTTPException(status_code=403, detail="session does not belong to customer") from exc
        append = session.append
        persistence = "local-development"

    conversation = list(session.messages) if session.messages else list(request.conversation)
    agent_request = request.model_copy(update={"conversation": conversation})

    user_message = Message(role="user", content=request.message)
    try:
        append(user_message)
    except httpx.HTTPError as exc:
        raise HTTPException(status_code=502, detail="Conversation persistence service unavailable") from exc
    session.messages.append(user_message)

    try:
        result = agent.handle(agent_request)
    except Exception as exc:
        raise HTTPException(status_code=502, detail="Agent service unavailable") from exc

    assistant_message = Message(role="assistant", content=result.reply)
    try:
        append(assistant_message)
    except httpx.HTTPError as exc:
        raise HTTPException(status_code=502, detail="Conversation persistence service unavailable") from exc
    session.messages.append(assistant_message)

    return SupportSessionResponse(
        **result.model_dump(),
        session_id=resolved_session_id,
        conversation=list(session.messages),
        persistence=persistence,
    )


@app.get("/api/sessions/{session_id}")
def get_session(session_id: str) -> dict:
    if durable_sessions.configured:
        raise HTTPException(status_code=400, detail="Use /api/sessions/{session_id}?customer_id=... to load a durable session")
    session = local_sessions.get(session_id)
    if session is None:
        raise HTTPException(status_code=404, detail="session not found")
    return session.__dict__


FRONTEND_DIR = Path(__file__).resolve().parents[2] / "frontend"

if FRONTEND_DIR.exists():
    app.mount("/", StaticFiles(directory=FRONTEND_DIR, html=True), name="frontend")
else:
    @app.get("/")
    def frontend_unavailable() -> RedirectResponse:
        return RedirectResponse(url="/health")
