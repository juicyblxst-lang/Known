from __future__ import annotations

import base64
import hashlib
import hmac
import os
import re
import secrets
from datetime import datetime, timedelta, timezone
from typing import Any
from urllib.parse import urlencode

import httpx
from cryptography.fernet import Fernet

SHOPIFY_API_VERSION = os.getenv("SHOPIFY_API_VERSION", "2026-07")
SHOPIFY_SCOPES = os.getenv("SHOPIFY_SCOPES", "read_customers,read_orders").strip()
SHOP_DOMAIN_RE = re.compile(r"^[a-z0-9][a-z0-9-]*\.myshopify\.com$")

def utcnow() -> datetime:
    return datetime.now(timezone.utc)

def validate_shop_domain(value: str) -> str:
    shop = value.strip().lower().replace("https://", "").replace("http://", "").rstrip("/")
    if not SHOP_DOMAIN_RE.fullmatch(shop):
        raise ValueError("Enter a valid Shopify myshopify.com domain")
    return shop

def _fernet() -> Fernet:
    key = os.getenv("SHOPIFY_TOKEN_ENCRYPTION_KEY", "")
    if not key:
        raise RuntimeError("SHOPIFY_TOKEN_ENCRYPTION_KEY is not configured")
    try:
        return Fernet(key.encode())
    except Exception as exc:
        raise RuntimeError("SHOPIFY_TOKEN_ENCRYPTION_KEY is invalid") from exc

def encrypt_token(token: str) -> str:
    return _fernet().encrypt(token.encode()).decode()

def decrypt_token(token: str) -> str:
    return _fernet().decrypt(token.encode()).decode()

def _supabase() -> tuple[str, dict[str, str]]:
    url = os.getenv("SUPABASE_URL", "").rstrip("/")
    key = os.getenv("SUPABASE_SERVICE_ROLE_KEY", "")
    if not url or not key:
        raise RuntimeError("Supabase backend is not configured")
    return url, {"apikey": key, "Authorization": f"Bearer {key}", "Content-Type": "application/json"}

def _db_get(table: str, params: dict[str, str]) -> list[dict[str, Any]]:
    url, headers = _supabase()
    response = httpx.get(f"{url}/rest/v1/{table}", params=params, headers=headers, timeout=10)
    response.raise_for_status()
    data = response.json()
    return data if isinstance(data, list) else []

def _db_write(table: str, payload: dict[str, Any], *, conflict: str | None = None) -> dict[str, Any] | None:
    url, headers = _supabase()
    headers = {**headers, "Prefer": "resolution=merge-duplicates,return=representation" if conflict else "return=representation"}
    response = httpx.post(f"{url}/rest/v1/{table}", params={"on_conflict": conflict} if conflict else {}, headers=headers, json=payload, timeout=10)
    response.raise_for_status()
    rows = response.json()
    return rows[0] if rows else None

def _db_patch(table: str, filters: dict[str, str], payload: dict[str, Any]) -> dict[str, Any] | None:
    url, headers = _supabase()
    response = httpx.patch(f"{url}/rest/v1/{table}", params=filters, headers={**headers, "Prefer": "return=representation"}, json=payload, timeout=10)
    response.raise_for_status()
    rows = response.json()
    return rows[0] if rows else None

def create_oauth_state(business_id: str, user_id: str, shop_domain: str) -> str:
    nonce = secrets.token_urlsafe(32)
    _db_write("shopify_oauth_states", {"nonce": nonce, "business_id": business_id, "user_id": user_id, "shop_domain": shop_domain, "expires_at": (utcnow() + timedelta(minutes=10)).isoformat()})
    return nonce

def consume_oauth_state(nonce: str, shop_domain: str) -> dict[str, Any]:
    rows = _db_get("shopify_oauth_states", {"nonce": f"eq.{nonce}", "shop_domain": f"eq.{shop_domain}", "used_at": "is.null", "limit": "1"})
    if not rows:
        raise ValueError("Invalid or already-used Shopify OAuth state")
    state = rows[0]
    if datetime.fromisoformat(state["expires_at"].replace("Z", "+00:00")) <= utcnow():
        raise ValueError("Shopify OAuth state expired")
    _db_patch("shopify_oauth_states", {"nonce": f"eq.{nonce}"}, {"used_at": utcnow().isoformat()})
    return state

def verify_oauth_hmac(params: dict[str, str]) -> bool:
    secret = os.getenv("SHOPIFY_CLIENT_SECRET", "")
    supplied = params.get("hmac")
    if not secret or not supplied:
        return False
    message = "&".join(f"{key}={params[key]}" for key in sorted(params) if key != "hmac")
    digest = hmac.new(secret.encode(), message.encode(), hashlib.sha256).hexdigest()
    return hmac.compare_digest(digest, supplied)

def authorization_url(shop_domain: str, state: str) -> str:
    client_id = os.getenv("SHOPIFY_CLIENT_ID", "")
    redirect_uri = os.getenv("SHOPIFY_REDIRECT_URI", "")
    if not client_id or not redirect_uri:
        raise RuntimeError("SHOPIFY_CLIENT_ID and SHOPIFY_REDIRECT_URI are required")
    return f"https://{shop_domain}/admin/oauth/authorize?{urlencode({'client_id': client_id, 'scope': SHOPIFY_SCOPES, 'redirect_uri': redirect_uri, 'state': state})}"

def exchange_code(shop_domain: str, code: str) -> dict[str, Any]:
    client_id = os.getenv("SHOPIFY_CLIENT_ID", "")
    client_secret = os.getenv("SHOPIFY_CLIENT_SECRET", "")
    if not client_id or not client_secret:
        raise RuntimeError("SHOPIFY_CLIENT_ID and SHOPIFY_CLIENT_SECRET are required")
    response = httpx.post(f"https://{shop_domain}/admin/oauth/access_token", json={"client_id": client_id, "client_secret": client_secret, "code": code}, timeout=15)
    response.raise_for_status()
    return response.json()

def _graphql(shop_domain: str, token: str, query: str, variables: dict[str, Any] | None = None) -> dict[str, Any]:
    response = httpx.post(f"https://{shop_domain}/admin/api/{SHOPIFY_API_VERSION}/graphql.json", headers={"X-Shopify-Access-Token": token, "Content-Type": "application/json"}, json={"query": query, "variables": variables or {}}, timeout=20)
    response.raise_for_status()
    body = response.json()
    if body.get("errors"):
        raise RuntimeError("Shopify GraphQL request failed")
    return body.get("data") or {}

def _page_query(shop_domain: str, token: str, query: str, root: str) -> list[dict[str, Any]]:
    items: list[dict[str, Any]] = []
    cursor: str | None = None
    while True:
        connection = _graphql(shop_domain, token, query, {"cursor": cursor})[root]
        items.extend(connection["nodes"])
        if not connection["pageInfo"]["hasNextPage"]:
            return items
        cursor = connection["pageInfo"]["endCursor"]

CUSTOMERS_QUERY = """query Customers($cursor: String) { customers(first: 100, after: $cursor) { nodes { id firstName lastName displayName email } pageInfo { hasNextPage endCursor } } }"""
ORDERS_QUERY = """query Orders($cursor: String) { orders(first: 100, after: $cursor, sortKey: UPDATED_AT) { nodes { id name updatedAt createdAt displayFinancialStatus displayFulfillmentStatus totalPriceSet { shopMoney { amount currencyCode } } customer { id } lineItems(first: 50) { nodes { name quantity } } } pageInfo { hasNextPage endCursor } } }"""
SHOP_QUERY = "query { shop { name myshopifyDomain } }"

def _stable_customer_id(shop_domain: str, shopify_id: str) -> str:
    return "shopify_customer_" + hashlib.sha256(f"{shop_domain}:{shopify_id}".encode()).hexdigest()[:32]

def _stable_order_id(shop_domain: str, shopify_id: str) -> str:
    return "shopify_order_" + hashlib.sha256(f"{shop_domain}:{shopify_id}".encode()).hexdigest()[:32]

def sync_shop(business_id: str, shop_domain: str) -> dict[str, int]:
    rows = _db_get("shopify_installations", {"business_id": f"eq.{business_id}", "shop_domain": f"eq.{shop_domain}", "limit": "1"})
    if not rows:
        raise ValueError("Shopify store is not connected to this business")
    installation = rows[0]
    token = decrypt_token(installation["access_token_encrypted"])
    try:
        customers = _page_query(shop_domain, token, CUSTOMERS_QUERY, "customers")
        orders = _page_query(shop_domain, token, ORDERS_QUERY, "orders")
        customer_map: dict[str, str] = {}
        for customer in customers:
            sid = customer["id"]
            cid = _stable_customer_id(shop_domain, sid)
            customer_map[sid] = cid
            name = customer.get("displayName") or " ".join(x for x in [customer.get("firstName"), customer.get("lastName")] if x) or "Shopify customer"
            _db_write("customers", {"id": cid, "business_id": business_id, "name": name, "email": customer.get("email") or "", "tier": "standard"}, conflict="id")
        for order in orders:
            customer_sid = (order.get("customer") or {}).get("id")
            customer_id = customer_map.get(customer_sid) if customer_sid else None
            if not customer_id:
                continue
            money = order.get("totalPriceSet", {}).get("shopMoney", {})
            items = [f"{x.get('name','item')} x{x.get('quantity',0)}" for x in (order.get("lineItems", {}).get("nodes") or [])]
            _db_write("orders", {"id": _stable_order_id(shop_domain, order["id"]), "business_id": business_id, "customer_id": customer_id, "status": (order.get("displayFulfillmentStatus") or order.get("displayFinancialStatus") or "unknown").lower(), "total": float(money.get("amount") or 0), "items": items, "created_at": order.get("createdAt") or utcnow().isoformat()}, conflict="id")
        _db_patch("shopify_installations", {"business_id": f"eq.{business_id}", "shop_domain": f"eq.{shop_domain}"}, {"last_synced_at": utcnow().isoformat(), "sync_status": "complete", "sync_error": None, "updated_at": utcnow().isoformat()})
        return {"customers": len(customers), "orders": len(orders)}
    except Exception as exc:
        _db_patch("shopify_installations", {"business_id": f"eq.{business_id}", "shop_domain": f"eq.{shop_domain}"}, {"sync_status": "failed", "sync_error": str(exc)[:500], "updated_at": utcnow().isoformat()})
        raise

def save_installation(business_id: str, shop_domain: str, token_data: dict[str, Any]) -> None:
    scopes = [x for x in str(token_data.get("scope", SHOPIFY_SCOPES)).split(",") if x]
    expires_at = (utcnow() + timedelta(seconds=int(token_data["expires_in"]))).isoformat() if token_data.get("expires_in") else None
    shop = _graphql(shop_domain, token_data["access_token"], SHOP_QUERY)["shop"]
    _db_write("shopify_installations", {"business_id": business_id, "shop_domain": shop_domain, "shop_name": shop.get("name"), "access_token_encrypted": encrypt_token(token_data["access_token"]), "refresh_token_encrypted": encrypt_token(token_data["refresh_token"]) if token_data.get("refresh_token") else None, "access_token_expires_at": expires_at, "scopes": scopes, "updated_at": utcnow().isoformat(), "sync_status": "pending"}, conflict="business_id")

def verify_webhook(body: bytes, hmac_header: str | None) -> bool:
    secret = os.getenv("SHOPIFY_CLIENT_SECRET", "")
    if not secret or not hmac_header:
        return False
    digest = base64.b64encode(hmac.new(secret.encode(), body, hashlib.sha256).digest()).decode()
    return hmac.compare_digest(digest, hmac_header)

def webhook_seen(webhook_id: str, shop_domain: str, topic: str) -> bool:
    if not webhook_id:
        return False
    rows = _db_get("shopify_webhook_events", {"webhook_id": f"eq.{webhook_id}", "limit": "1"})
    if rows:
        return True
    _db_write("shopify_webhook_events", {"webhook_id": webhook_id, "shop_domain": shop_domain, "topic": topic})
    return False

def installation(business_id: str) -> dict[str, Any] | None:
    rows = _db_get("shopify_installations", {"business_id": f"eq.{business_id}", "select": "shop_domain,shop_name,scopes,installed_at,last_synced_at,sync_status,sync_error", "limit": "1"})
    return rows[0] if rows else None

def installation_by_shop(shop_domain: str) -> dict[str, Any] | None:
    rows = _db_get("shopify_installations", {"shop_domain": f"eq.{shop_domain}", "limit": "1"})
    return rows[0] if rows else None
