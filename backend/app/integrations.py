from __future__ import annotations
import os
from datetime import datetime, timedelta, timezone
from typing import Any
import httpx
from .auth import AuthContext
from .gmail import GmailIntegration
from .models import Customer, Message, Order, SupportContextRequest
from .production_agent import KnownAgent
from .store import StructuredStore
from .supabase_sessions import SupabaseSessionStore

class IntegrationStore:
    def __init__(self)->None:
        self.url=os.getenv("SUPABASE_URL","").rstrip("/"); self.key=os.getenv("SUPABASE_SERVICE_ROLE_KEY","")
    @property
    def configured(self)->bool: return bool(self.url and self.key)
    def _request(self,method:str,table:str,**kwargs:Any)->list[dict[str,Any]]:
        if not self.configured: raise RuntimeError("Integration storage is not configured")
        r=httpx.request(method,f"{self.url}/rest/v1/{table}",headers={"apikey":self.key,"Authorization":f"Bearer {self.key}","Content-Type":"application/json"},timeout=15,**kwargs); r.raise_for_status(); data=r.json() if r.content else []; return data if isinstance(data,list) else []
    def connection(self,business_id:str)->dict[str,Any]|None:
        rows=self._request("GET","integration_connections",params={"business_id":f"eq.{business_id}","provider":"eq.gmail","select":"*","limit":"1"}); return rows[0] if rows else None
    def connections(self)->list[dict[str,Any]]: return self._request("GET","integration_connections",params={"provider":"eq.gmail","select":"*","order":"updated_at.desc"})
    def save_connection(self,business_id:str,token:dict[str,Any],profile:dict[str,Any])->dict[str,Any]|None:
        expires=(datetime.now(timezone.utc)+timedelta(seconds=int(token.get("expires_in",3600)))).isoformat() if token.get("expires_in") else None
        payload={"business_id":business_id,"provider":"gmail","external_account_id":profile.get("emailAddress"),"access_token":token.get("access_token",""),"refresh_token":token.get("refresh_token"),"token_expires_at":expires,"metadata":{"email":profile.get("emailAddress"),"history_id":profile.get("historyId")}}
        rows=self._request("POST","integration_connections",params={"on_conflict":"business_id,provider"},headers={"Prefer":"resolution=merge-duplicates,return=representation"},json=payload)
        return rows[0] if rows else self.connection(business_id)
    def update_tokens(self,connection_id:str,token:dict[str,Any])->None:
        expires=(datetime.now(timezone.utc)+timedelta(seconds=int(token.get("expires_in",3600)))).isoformat() if token.get("expires_in") else None
        self._request("PATCH","integration_connections",params={"id":f"eq.{connection_id}"},json={"access_token":token.get("access_token"),"token_expires_at":expires,"updated_at":datetime.now(timezone.utc).isoformat()})
    def seen(self,business_id:str,external_id:str)->bool: return bool(self._request("GET","external_messages",params={"business_id":f"eq.{business_id}","provider":"eq.gmail","external_message_id":f"eq.{external_id}","select":"id","limit":"1"}))
    def list_processed_messages(self,business_id:str,limit:int=50)->list[dict[str,Any]]: return self._request("GET","external_messages",params={"business_id":f"eq.{business_id}","provider":"eq.gmail","direction":"eq.inbound","select":"external_message_id,external_thread_id,customer_id,session_id,sender_email,subject,body,received_at","order":"received_at.desc","limit":str(limit)})
    def record_message(self,business_id:str,data:dict[str,Any],customer_id:str|None,session_id:str|None,direction:str,external_id:str|None=None)->None:
        payload={"business_id":business_id,"provider":"gmail","external_message_id":external_id or data["external_message_id"],"external_thread_id":data.get("external_thread_id"),"customer_id":customer_id,"session_id":session_id,"direction":direction,"sender_email":data.get("sender_email"),"recipient_email":data.get("recipient_email"),"subject":data.get("subject"),"body":data.get("body","") ,"received_at":datetime.now(timezone.utc).isoformat(),"processed_at":datetime.now(timezone.utc).isoformat()}
        self._request("POST","external_messages",headers={"Prefer":"resolution=ignore-duplicates"},json=payload)
    def remember_identity(self,business_id:str,customer_id:str,email:str)->None: self._request("POST","customer_external_identities",headers={"Prefer":"resolution=ignore-duplicates"},json={"business_id":business_id,"customer_id":customer_id,"provider":"gmail","external_id":email.lower()})

def _find_customer(store:StructuredStore,business_id:str,email:str)->dict[str,Any]|None:
    if hasattr(store,"customer_by_email"): return store.customer_by_email(email,business_id)
    rows=store._get("customers",{"business_id":f"eq.{business_id}","email":f"eq.{email.lower()}","archived_at":"is.null","select":"id,name,email,tier","limit":"1"}); return rows[0] if rows else None

def process_gmail_messages(business_id:str,connection:dict[str,Any],agent:KnownAgent,store:StructuredStore,sessions:SupabaseSessionStore,integration_store:IntegrationStore,gmail:GmailIntegration)->dict[str,int]:
    token=connection["access_token"]
    try: messages=gmail.list_messages(token,max_results=20)
    except httpx.HTTPStatusError as exc:
        if exc.response.status_code!=401 or not connection.get("refresh_token"): raise
        refreshed=gmail.refresh(connection["refresh_token"]); token=refreshed["access_token"]; integration_store.update_tokens(connection["id"],refreshed); messages=gmail.list_messages(token,max_results=20)
    processed=matched=ignored=created=failed=0
    for raw in messages:
        parsed=gmail.parse_message(raw); external_id=parsed.get("external_message_id")
        if not external_id or integration_store.seen(business_id,external_id): ignored+=1; continue
        sender=parsed.get("sender_email","")
        if not sender: ignored+=1; gmail.mark_read(token,external_id); continue
        try:
            customer=_find_customer(store,business_id,sender)
            if customer is None:
                if not hasattr(store,"create_customer"): raise RuntimeError("Customer store cannot create new customers")
                customer=store.create_customer(business_id,sender,parsed.get("sender_name","") or sender.split("@",1)[0]); created+=1
            integration_store.remember_identity(business_id,customer["id"],customer["email"])
            session_id=f"gmail:{parsed.get('external_thread_id') or external_id}"; session=sessions.get_or_create(session_id,customer["id"],business_id)
            body=(parsed.get("body") or "").strip() or "Please review this support email."
            if not any(m.content==body and m.role=="user" for m in session.messages): sessions.append(session_id,Message(role="user",content=body))
            orders=store.orders(customer["id"],business_id); request=SupportContextRequest(customer=Customer(**customer),message=body,conversation=list(session.messages),orders=[Order(**o) for o in orders])
            result=agent.handle(request,auth=AuthContext(user_id="gmail",business_id=business_id,email=customer.get("email")))
            sent=gmail.send(token,customer["email"],f"Re: {parsed.get('subject','Support request')}",result.reply,thread_id=parsed.get("external_thread_id"),in_reply_to=parsed.get("message_id_header"))
            sessions.append(session_id,Message(role="assistant",content=result.reply)); integration_store.record_message(business_id,parsed,customer["id"],session_id,"inbound"); integration_store.record_message(business_id,{**parsed,"external_message_id":sent.get("id",f"sent:{external_id}"),"sender_email":parsed.get("recipient_email"),"recipient_email":customer["email"],"body":result.reply},customer["id"],session_id,"outbound",sent.get("id")); gmail.mark_read(token,external_id); processed+=1; matched+=1
        except Exception:
            failed+=1
            continue
    return {"processed":processed,"matched":matched,"ignored":ignored,"created":created,"failed":failed}
