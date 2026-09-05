from __future__ import annotations

import os


def service_key() -> str:
    """Return the preferred server-side Supabase credential, with legacy fallback."""
    return os.getenv("SUPABASE_SECRET_KEY", "") or os.getenv("SUPABASE_SERVICE_ROLE_KEY", "")


def service_headers(key: str | None = None) -> dict[str, str]:
    """Build headers for privileged Supabase REST/Auth calls.

    New opaque secret keys are sent through apikey only; legacy credentials
    retain the bearer header during migration.
    """
    value = key or service_key()
    headers = {"apikey": value, "Content-Type": "application/json"}
    if value and not value.startswith("sb_secret_"):
        headers["Authorization"] = f"Bearer {value}"
    return headers
