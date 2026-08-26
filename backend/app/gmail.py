from __future__ import annotations

import base64
import hashlib
import hmac
import os
import time
from email.utils import parseaddr
from typing import Any
from urllib.parse import urlencode

import httpx


class GmailIntegration:
    """Minimal Gmail OAuth/API adapter using Google's HTTPS APIs directly."""
    def __init__(self) -> None:
        self.client_id = os.getenv("GOOGLE_CLIENT_ID", "")
        self.client_secret = os.getenv("GOOGLE_CLIENT_SECRET", "")
        self.redirect_uri = os.getenv("GOOGLE_REDIRECT_URI", "")
        self.secret = os.getenv("GMAIL_STATE_SECRET") or self.client_secret
        self.scope = "https://www.googleapis.com/auth/gmail.modify https://www.googleapis.com/auth/gmail.send"

    @property
    def configured(self) -> bool:
        return bool(self.client_id and self.client_secret and self.redirect_uri and self.secret)

    def state(self, business_id: str) -> str:
        payload = f"{business_id}:{int(time.time())}"
        sig = hmac.new(self.secret.encode(), payload.encode(), hashlib.sha256).hexdigest()
        return base64.urlsafe_b64encode(f"{payload}:{sig}".encode()).decode()

    def verify_state(self, value: str, max_age: int = 600) -> str:
        raw = base64.urlsafe_b64decode(value.encode()).decode()
        business_id, issued, signature = raw.rsplit(":", 2)
        payload = f"{business_id}:{issued}"
        if not hmac.compare_digest(signature, hmac.new(self.secret.encode(), payload.encode(), hashlib.sha256).hexdigest()):
            raise ValueError("invalid OAuth state")
        if int(time.time()) - int(issued) > max_age:
            raise ValueError("expired OAuth state")
        return business_id

    def authorize_url(self, state: str) -> str:
        params = {"client_id": self.client_id, "redirect_uri": self.redirect_uri, "response_type": "code", "scope": self.scope, "access_type": "offline", "prompt": "consent", "state": state}
        return "https://accounts.google.com/o/oauth2/v2/auth?" + urlencode(params)

    def exchange(self, code: str) -> dict[str, Any]:
        r = httpx.post("https://oauth2.googleapis.com/token", data={"code": code, "client_id": self.client_id, "client_secret": self.client_secret, "redirect_uri": self.redirect_uri, "grant_type": "authorization_code"}, timeout=15)
        r.raise_for_status(); return r.json()

    def refresh(self, refresh_token: str) -> dict[str, Any]:
        r = httpx.post("https://oauth2.googleapis.com/token", data={"refresh_token": refresh_token, "client_id": self.client_id, "client_secret": self.client_secret, "grant_type": "refresh_token"}, timeout=15)
        r.raise_for_status(); return r.json()

    def _request(self, token: str, method: str, path: str, **kwargs: Any) -> Any:
        r = httpx.request(method, f"https://gmail.googleapis.com/gmail/v1/users/me/{path}", headers={"Authorization": f"Bearer {token}"}, timeout=20, **kwargs)
        r.raise_for_status(); return r.json() if r.content else {}

    def profile(self, token: str) -> dict[str, Any]:
        return self._request(token, "GET", "profile")

    def list_messages(self, token: str, history_id: str | None = None, max_results: int = 20) -> list[dict[str, Any]]:
        params = {"maxResults": str(max_results), "labelIds": "INBOX", "q": "-from:me"}
        if history_id:
            params["startHistoryId"] = history_id
            try:
                history = self._request(token, "GET", "history", params={"startHistoryId": history_id, "historyTypes": "messageAdded"})
                ids = []
                for item in history.get("history", []):
                    ids.extend(x.get("message", {}).get("id") for x in item.get("messagesAdded", []) if x.get("message", {}).get("id"))
            except httpx.HTTPStatusError:
                ids = []
        else:
            data = self._request(token, "GET", "messages", params=params)
            ids = [x["id"] for x in data.get("messages", [])]
        return [self._request(token, "GET", f"messages/{mid}", params={"format": "full"}) for mid in dict.fromkeys(ids)]

    @staticmethod
    def parse_message(message: dict[str, Any]) -> dict[str, Any]:
        headers = {h["name"].lower(): h["value"] for h in message.get("payload", {}).get("headers", [])}
        body = ""
        payload = message.get("payload", {})
        parts = payload.get("parts") or [payload]
        for part in parts:
            if part.get("mimeType") == "text/plain" and part.get("body", {}).get("data"):
                body = base64.urlsafe_b64decode(part["body"]["data"] + "===").decode("utf-8", errors="replace"); break
        sender_name, sender_email = parseaddr(headers.get("from", ""))
        _, recipient_email = parseaddr(headers.get("to", ""))
        return {"external_message_id": message.get("id"), "external_thread_id": message.get("threadId"), "sender_name": sender_name, "sender_email": sender_email.lower(), "recipient_email": recipient_email.lower(), "subject": headers.get("subject", ""), "body": body, "received_at": None}

    def send(self, token: str, to: str, subject: str, body: str, thread_id: str | None = None, in_reply_to: str | None = None) -> dict[str, Any]:
        headers = [f"To: {to}", f"Subject: {subject}", "Content-Type: text/plain; charset=utf-8"]
        if in_reply_to:
            headers.append(f"In-Reply-To: {in_reply_to}"); headers.append(f"References: {in_reply_to}")
        raw = "\r\n".join(headers) + "\r\n\r\n" + body
        encoded = base64.urlsafe_b64encode(raw.encode()).decode()
        payload: dict[str, Any] = {"raw": encoded}
        if thread_id: payload["threadId"] = thread_id
        return self._request(token, "POST", "messages/send", json=payload)
