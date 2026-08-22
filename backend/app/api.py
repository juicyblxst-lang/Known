from __future__ import annotations

from fastapi import APIRouter, Depends, Query

from .auth import AuthContext, require_auth
from .demo import comparison
from .memory import SibylMemory
from .store import StructuredStore
from .workspace import WorkspaceResponse

router = APIRouter(prefix="/api")
store = StructuredStore()
memory = SibylMemory()


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


@router.get("/demo/memory-comparison")
def memory_comparison() -> dict:
    return comparison()
