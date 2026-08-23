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
    """Resolve an existing membership or provision the first user's tenant.

    Older Known accounts were created directly in Supabase Auth, before the
    application attached a business_id to app_metadata. Keep tenant identity
    server-side and repair that missing association once, rather than making
    the user create a second account.
    """
    user_id = str(user["id"])
    headers = _headers(service_key)
    async with httpx.AsyncClient(timeout=10) as client:
        membership = await client.get(
            f"{url}/rest/v1/memberships",
            params={"user_id": f"eq.{user_id}", "select": "business_id", "limit": "1"},
            headers=headers,
        )
        membership.raise_for_status()
        rows = membership.json()
        if rows:
            return str(rows[0]["business_id"])

        business_id = str(uuid.uuid4())
        email = user.get("email") or ""
        local = email.split("@", 1)[0].strip() if email else ""
        business_name = f"{local or 'My'} workspace"

        created = await client.post(
            f"{url}/rest/v1/businesses",
            headers={**headers, "Prefer": "return=representation"},
            json={"id": business_id, "name": business_name},
        )
        created.raise_for_status()

        membership = await client.post(
            f"{url}/rest/v1/memberships",
            headers={**headers, "Prefer": "return=representation"},
            json={"business_id": business_id, "user_id": user_id, "role": "owner"},
        )
        membership.raise_for_status()

        updated_metadata = dict(user.get("app_metadata") or {})
        updated_metadata["business_id"] = business_id
        auth_update = await client.put(
            f"{url}/auth/v1/admin/users/{user_id}",
            headers=headers,
            json={"app_metadata": updated_metadata},
        )
        auth_update.raise_for_status()
        return business_id


async def require_auth(authorization: str | None = Header(default=None)) -> AuthContext:
    """Validate a Supabase access token and resolve its business tenant.

    The browser token is never trusted for tenant identity. Supabase Auth is
    queried to validate the token, and the business_id is resolved server-side
    from the membership table. Existing app_metadata is preserved as a fast
    path; legacy users without tenant metadata are provisioned once.
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
        try:
            business_id = await _provision_business(url, service_key, user)
        except httpx.HTTPStatusError as exc:
            # Surface a stable application error rather than leaking Supabase
            # response details. The original tenant-less account remains safe
            # to retry after the underlying schema/configuration is corrected.
            raise HTTPException(status_code=503, detail="Unable to provision Known workspace") from exc
        except (httpx.HTTPError, KeyError, ValueError) as exc:
            raise HTTPException(status_code=503, detail="Unable to provision Known workspace") from exc

    return AuthContext(user_id=user["id"], business_id=str(business_id), email=user.get("email"))
