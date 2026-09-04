from __future__ import annotations

import os
import uuid

import httpx
from fastapi import Header, HTTPException
from pydantic import BaseModel


class AuthContext(BaseModel):
    user_id: str
    business_id: str
    email: str | None = None


def _headers(service_key: str) -> dict[str, str]:
    return {
        "apikey": service_key,
        "Authorization": f"Bearer {service_key}",
        "Content-Type": "application/json",
    }


async def _provision_business(url: str, service_key: str, user: dict) -> str:
    """Provision the user's first Known tenant and its existing membership record."""
    user_id = str(user["id"])
    headers = _headers(service_key)
    metadata = dict(user.get("app_metadata") or {})
    existing = metadata.get("business_id")
    if existing:
        return str(existing)

    business_id = str(uuid.uuid4())
    email = user.get("email") or ""
    local = email.split("@", 1)[0].strip() if email else ""
    business_name = f"{local or 'My'} workspace"

    async with httpx.AsyncClient(timeout=10) as client:
        created = await client.post(
            f"{url}/rest/v1/businesses",
            headers={**headers, "Prefer": "return=representation"},
            json={"id": business_id, "name": business_name},
        )
        created.raise_for_status()

        membership = await client.post(
            f"{url}/rest/v1/business_memberships",
            headers={**headers, "Prefer": "resolution=ignore-duplicates"},
            json={"user_id": user_id, "business_id": business_id, "role": "owner"},
        )
        membership.raise_for_status()

        metadata["business_id"] = business_id
        auth_update = await client.put(
            f"{url}/auth/v1/admin/users/{user_id}",
            headers=headers,
            json={"app_metadata": metadata},
        )
        auth_update.raise_for_status()

    return business_id


async def require_auth(authorization: str | None = Header(default=None)) -> AuthContext:
    """Validate a Supabase access token and resolve its Known tenant."""
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
                headers={"apikey": service_key, "Authorization": f"Bearer {token}"},
            )
    except httpx.HTTPError as exc:
        raise HTTPException(status_code=503, detail="Authentication service unavailable") from exc

    if response.status_code != 200:
        raise HTTPException(status_code=401, detail="Invalid or expired access token")

    user = response.json()
    business_id = (user.get("app_metadata") or {}).get("business_id")
    if not business_id:
        try:
            business_id = await _provision_business(url, service_key, user)
        except (httpx.HTTPStatusError, httpx.HTTPError, KeyError, ValueError) as exc:
            raise HTTPException(status_code=503, detail="Unable to provision Known workspace") from exc

    return AuthContext(user_id=user["id"], business_id=str(business_id), email=user.get("email"))
