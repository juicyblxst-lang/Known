from __future__ import annotations

import os

from .shopify import _graphql

MUTATION = """
mutation CreateWebhook($topic: WebhookSubscriptionTopic!, $webhookSubscription: WebhookSubscriptionInput!) {
  webhookSubscriptionCreate(topic: $topic, webhookSubscription: $webhookSubscription) {
    webhookSubscription { id topic uri }
    userErrors { field message }
  }
}
"""


def register_webhooks(shop_domain: str, token: str) -> None:
    endpoint = os.getenv("SHOPIFY_WEBHOOK_URL", "").strip()
    if not endpoint:
        raise RuntimeError("SHOPIFY_WEBHOOK_URL is not configured")
    for topic in ("CUSTOMERS_CREATE", "CUSTOMERS_UPDATE", "CUSTOMERS_DELETE", "ORDERS_CREATE", "ORDERS_UPDATED", "ORDERS_CANCELLED", "ORDERS_FULFILLED", "APP_UNINSTALLED"):
        data = _graphql(shop_domain, token, MUTATION, {"topic": topic, "webhookSubscription": {"uri": endpoint}})
        result = data.get("webhookSubscriptionCreate") or {}
        errors = result.get("userErrors") or []
        if errors:
            # Shopify can report an already-existing subscription as a user error.
            message = "; ".join(str(item.get("message", "")) for item in errors)
            if "already" not in message.lower() and "exist" not in message.lower():
                raise RuntimeError(f"Shopify webhook registration failed for {topic}: {message}")
