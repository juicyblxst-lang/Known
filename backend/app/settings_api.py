from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel
import httpx
import os
from .auth import AuthContext, require_auth
from .supabase_credentials import service_headers, service_key

router = APIRouter(prefix="/api")

class NotificationSettings(BaseModel):
    import_completed: bool = True
    new_conversations: bool = True

def _headers(key: str) -> dict[str,str]: return service_headers(key)

async def _user(url: str, key: str, user_id: str) -> dict:
    async with httpx.AsyncClient(timeout=10) as client:
        response=await client.get(f"{url}/auth/v1/admin/users/{user_id}",headers=_headers(key))
    response.raise_for_status(); return response.json()

@router.get("/settings/notifications")
async def get_notification_settings(auth: AuthContext = Depends(require_auth)) -> NotificationSettings:
    url=os.getenv("SUPABASE_URL","").rstrip("/"); key=service_key()
    if not url or not key: raise HTTPException(status_code=503,detail="Supabase authentication is not configured")
    try:
        user=await _user(url,key,auth.user_id); data=(user.get("user_metadata") or {}).get("known_notification_settings") or {}
        return NotificationSettings(**data)
    except httpx.HTTPError as exc: raise HTTPException(status_code=503,detail="Unable to load notification settings") from exc

@router.patch("/settings/notifications")
async def set_notification_settings(request: NotificationSettings, auth: AuthContext = Depends(require_auth)) -> NotificationSettings:
    url=os.getenv("SUPABASE_URL","").rstrip("/"); key=service_key()
    if not url or not key: raise HTTPException(status_code=503,detail="Supabase authentication is not configured")
    try:
        user=await _user(url,key,auth.user_id); metadata=dict(user.get("user_metadata") or {}); metadata["known_notification_settings"]=request.model_dump()
        async with httpx.AsyncClient(timeout=10) as client:
            response=await client.put(f"{url}/auth/v1/admin/users/{auth.user_id}",headers=_headers(key),json={"user_metadata":metadata})
        response.raise_for_status(); return request
    except httpx.HTTPError as exc: raise HTTPException(status_code=503,detail="Unable to save notification settings") from exc
