from __future__ import annotations

import base64, hashlib, hmac, logging, os, time
from email.utils import parseaddr
from typing import Any
from urllib.parse import urlencode

import httpx

logger = logging.getLogger("known.gmail")


class GmailIntegration:
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
        try:
            raw = base64.urlsafe_b64decode(value.encode()).decode()
            business_id, issued, signature = raw.rsplit(":", 2)
        except Exception as exc:
            raise ValueError("invalid OAuth state") from exc
        payload = f"{business_id}:{issued}"
        if not hmac.compare_digest(signature, hmac.new(self.secret.encode(), payload.encode(), hashlib.sha256).hexdigest()):
            raise ValueError("invalid OAuth state")
        if int(time.time()) - int(issued) > max_age:
            raise ValueError("expired OAuth state")
        return business_id

    def authorize_url(self, state: str) -> str:
        return "https://accounts.google.com/o/oauth2/v2/auth?" + urlencode({"client_id": self.client_id, "redirect_uri": self.redirect_uri, "response_type": "code", "scope": self.scope, "access_type": "offline", "prompt": "consent", "state": state})

    def exchange(self, code: str) -> dict[str, Any]:
        response = httpx.post("https://oauth2.googleapis.com/token", data={"code": code, "client_id": self.client_id, "client_secret": self.client_secret, "redirect_uri": self.redirect_uri, "grant_type": "authorization_code"}, timeout=15)
        if response.status_code >= 400:
            try:
                body = response.json()
            except ValueError:
                body = {"error": response.text[:300]}
            logger.warning("Google OAuth token exchange failed: status=%s error=%s description=%s", response.status_code, body.get("error"), body.get("error_description"))
            raise RuntimeError(f"Google token exchange failed: {body.get('error') or response.status_code}: {body.get('error_description') or 'unknown error'}")
        token = response.json()
        logger.info("Google OAuth token exchange succeeded: token_type=%s scope=%s expires_in=%s has_refresh_token=%s", token.get("token_type"), token.get("scope"), token.get("expires_in"), bool(token.get("refresh_token")))
        if not token.get("access_token"):
            raise RuntimeError("Google token exchange returned no access token")
        return token

    def refresh(self, refresh_token: str) -> dict[str, Any]:
        response = httpx.post("https://oauth2.googleapis.com/token", data={"refresh_token": refresh_token, "client_id": self.client_id, "client_secret": self.client_secret, "grant_type": "refresh_token"}, timeout=15)
        if response.status_code >= 400:
            try:
                body = response.json()
            except ValueError:
                body = {"error": response.text[:300]}
            logger.warning("Google OAuth refresh failed: status=%s error=%s description=%s", response.status_code, body.get("error"), body.get("error_description"))
            raise RuntimeError(f"Google token refresh failed: {body.get('error') or response.status_code}: {body.get('error_description') or 'unknown error'}")
        token = response.json()
        logger.info("Google OAuth refresh succeeded: token_type=%s scope=%s expires_in=%s", token.get("token_type"), token.get("scope"), token.get("expires_in"))
        if not token.get("access_token"):
            raise RuntimeError("Google token refresh returned no access token")
        return token

    def _request(self, token: str, method: str, path: str, **kwargs: Any) -> Any:
        response = httpx.request(method, f"https://gmail.googleapis.com/gmail/v1/users/me/{path}", headers={"Authorization": f"Bearer {token}"}, timeout=20, **kwargs)
        if response.status_code >= 400:
            try:
                body = response.json()
            except ValueError:
                body = {"error": response.text[:300]}
            logger.warning("Gmail API request failed: method=%s path=%s status=%s error=%s message=%s", method, path, response.status_code, body.get("error"), body.get("message"))
            raise httpx.HTTPStatusError(f"Gmail API {method} {path} returned {response.status_code}", request=response.request, response=response)
        return response.json() if response.content else {}

    def profile(self, token: str) -> dict[str, Any]:
        profile = self._request(token, "GET", "profile")
        if not profile.get("emailAddress"):
            raise RuntimeError("Gmail profile response did not include an email address")
        logger.info("Gmail profile verified: email_domain=%s has_history_id=%s", profile["emailAddress"].split("@", 1)[-1], bool(profile.get("historyId")))
        return profile

    def list_message_ids(self, token: str, max_results: int = 20) -> list[str]:
        data = self._request(token, "GET", "messages", params={"maxResults": str(max_results), "labelIds": "INBOX", "q": "is:unread -from:me"})
        return [item["id"] for item in data.get("messages", []) if item.get("id")]

    def get_message(self, token: str, message_id: str) -> dict[str, Any]:
        return self._request(token, "GET", f"messages/{message_id}", params={"format": "full"})

    def list_messages(self, token: str, max_results: int = 20) -> list[dict[str, Any]]:
        return [self.get_message(token, message_id) for message_id in self.list_message_ids(token, max_results=max_results)]

    def mark_read(self, token: str, message_id: str) -> None:
        self._request(token, "POST", f"messages/{message_id}/modify", json={"removeLabelIds": ["UNREAD"]})

    @staticmethod
    def _text_parts(payload: dict[str, Any]) -> list[str]:
        if payload.get("mimeType") == "text/plain" and payload.get("body", {}).get("data"):
            try:
                return [base64.urlsafe_b64decode(payload["body"]["data"] + "===").decode("utf-8", errors="replace")]
            except Exception:
                return []
        out: list[str] = []
        for part in payload.get("parts") or []:
            out.extend(GmailIntegration._text_parts(part))
        return out

    @staticmethod
    def parse_message(message: dict[str, Any]) -> dict[str, Any]:
        headers = {h["name"].lower(): h["value"] for h in message.get("payload", {}).get("headers", [])}
        parts = GmailIntegration._text_parts(message.get("payload", {}))
        body = "\n\n".join(x.strip() for x in parts if x.strip())
        sender_name, sender_email = parseaddr(headers.get("from", ""))
        _, recipient_email = parseaddr(headers.get("to", ""))
        return {"external_message_id": message.get("id"), "external_thread_id": message.get("threadId"), "sender_name": sender_name, "sender_email": sender_email.lower(), "recipient_email": recipient_email.lower(), "subject": headers.get("subject", ""), "body": body, "message_id_header": headers.get("message-id")}

    def send(self, token: str, to: str, subject: str, body: str, thread_id: str | None = None, in_reply_to: str | None = None) -> dict[str, Any]:
        headers = [f"To: {to}", f"Subject: {subject}", "Content-Type: text/plain; charset=utf-8"]
        if in_reply_to:
            headers += [f"In-Reply-To: {in_reply_to}", f"References: {in_reply_to}"]
        payload: dict[str, Any] = {"raw": base64.urlsafe_b64encode(("\r\n".join(headers) + "\r\n\r\n" + body).encode()).decode()}
        if thread_id:
            payload["threadId"] = thread_id
        return self._request(token, "POST", "messages/send", json=payload)
