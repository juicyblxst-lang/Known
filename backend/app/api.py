from __future__ import annotations

from fastapi import APIRouter, Depends, HTTPException, Query

from .auth import AuthContext, require_auth
from .demo import comparison
from .memory import SibylMemory
from .store import StructuredStore
from .supabase_sessions import SupabaseSessionStore
from .workspace import WorkspaceResponse

router = APIRouter(prefix="/api")
store = StructuredStore()
memory = SibylMemory()
sessions = SupabaseSessionStore()


@router.get("/customers")
async def get_customers(auth: AuthContext = Depends(require_auth)) -> list[dict]:
    return store.customers(auth.business_id)


@router.get("/workspace/{customer_id}", response_model=WorkspaceResponse)
async def get_workspace(
    customer_id: str,
    memory_query: str = Query("customer history"),
    auth: AuthContext = Depends(require_auth),
) -> WorkspaceResponse:
    customer = store.customer(customer_id, auth.business_id)
    orders = store.orders(customer_id, auth.business_id)
    retrieved = memory.search(customer_id, memory_query)
    return WorkspaceResponse(
        customer=customer,
        orders=orders,
        memory=retrieved.memories,
        memory_available=retrieved.available,
    )


@router.get("/sessions/{session_id}")
async def get_conversation_session(
    session_id: str,
    customer_id: str,
    auth: AuthContext = Depends(require_auth),
) -> dict:
    if not sessions.configured:
        return {"session_id": session_id, "customer_id": customer_id, "messages": [], "persistence": "local-development"}
    try:
        session = sessions.get(session_id, customer_id, auth.business_id)
    except Exception as exc:
        raise HTTPException(status_code=502, detail="Unable to load conversation session") from exc
    if session is None:
        return {"session_id": session_id, "customer_id": customer_id, "messages": [], "persistence": "supabase"}
    return {
        "session_id": session.id,
        "customer_id": session.customer_id,
        "messages": [message.model_dump() for message in session.messages],
        "created_at": session.created_at,
        "updated_at": session.updated_at,
        "persistence": "supabase",
    }


@router.get("/demo/memory-comparison")
def memory_comparison() -> dict:
    return comparison()
