from __future__ import annotations

import os

import httpx
from fastapi import Header, HTTPException
from pydantic import BaseModel


class AuthContext(BaseModel):
    user_id: str
    business_id: str
    email: str | None = None


async def require_auth(authorization: str | None = Header(default=None)) -> AuthContext:
    """Validate a Supabase access token and resolve its business tenant.

    The browser token is never trusted for tenant identity. Supabase Auth is
    queried to validate the token, and the business_id is taken from the
    authenticated user's app metadata.
    """
    if not authorization or not authorization.lower().startswith("bearer "):
        raise HTTPException(status_code=401, detail="Bearer access token required")

    url = os.getenv("SUPABASE_URL", "").rstrip("/")
    service_key = os.getenv("SUPABASE_SERVICE_ROLE_KEY", "")
    if not url or not service_key:
        raise HTTPException(status_code=503, detail="Supabase authentication is not configured")

    token = authorization.split(" ", 1)[1].strip()
    try:
        async with httpx.AsyncClient(timeout=10) as client:
            response = await client.get(
                f"{url}/auth/v1/user",
                headers={
                    "apikey": service_key,
                    "Authorization": f"Bearer {token}",
                },
            )
    except httpx.HTTPError as exc:
        raise HTTPException(status_code=503, detail="Authentication service unavailable") from exc

    if response.status_code != 200:
        raise HTTPException(status_code=401, detail="Invalid or expired access token")

    user = response.json()
    metadata = user.get("app_metadata") or {}
    business_id = metadata.get("business_id")
    if not business_id:
        raise HTTPException(status_code=403, detail="Authenticated user has no business tenant")

    return AuthContext(user_id=user["id"], business_id=str(business_id), email=user.get("email"))
