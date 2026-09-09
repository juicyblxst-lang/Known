from __future__ import annotations
import logging
import os
from datetime import datetime, timedelta, timezone
from typing import Any
import httpx
from .auth import AuthContext
from .gmail import GmailIntegration
from .models import Customer, Message, Order, SupportContextRequest
from .production_agent import KnownAgent
from .store import StructuredStore
from .supabase_credentials import service_headers, service_key
from .supabase_sessions import SupabaseSessionStore

logger = logging.getLogger("known.integrations")

class IntegrationStore:
    def __init__(self)->None:
        self.url=os.getenv("SUPABASE_URL","").rstrip("/"); self.key=service_key()
    @property
    def configured(self)->bool: return bool(self.url and self.key)
    def _request(self,method:str,table:str,**kwargs:Any)->list[dict[str,Any]]:
        if not self.configured: raise RuntimeError("Integration storage is not configured")
        request_headers={**service_headers(self.key), **(kwargs.pop("headers", {}) or {})}
        r=httpx.request(method,f"{self.url}/rest/v1/{table}",headers=request_headers,timeout=15,**kwargs)
        if r.status_code >= 400:
            logger.error("Supabase integration request failed: method=%s table=%s status=%s body=%s",method,table,r.status_code,r.text[:1000])
        r.raise_for_status(); data=r.json() if r.content else []; return data if isinstance(data,list) else []
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
    def message_status(self,business_id:str,external_id:str)->dict[str,Any]|None:
        rows=self._request("GET","external_messages",params={"business_id":f"eq.{business_id}","provider":"eq.gmail","external_message_id":f"eq.{external_id}","select":"processing_status,attempt_count,customer_id,session_id,outbound_body,outbound_message_id,external_thread_id","limit":"1"})
        return rows[0] if rows else None
    def seen(self,business_id:str,external_id:str)->bool:
        return bool(self.message_status(business_id,external_id))
    def claim_message(self,business_id:str,data:dict[str,Any])->dict[str,Any]|None:
        external_id=data.get("external_message_id")
        if not external_id: return None
        existing=self._request("GET","external_messages",params={"business_id":f"eq.{business_id}","provider":"eq.gmail","external_message_id":f"eq.{external_id}","select":"*","limit":"1"})
        now=datetime.now(timezone.utc).isoformat()
        if existing:
            row=existing[0]; status=row.get("processing_status"); attempts=int(row.get("attempt_count") or 0)
            if status=="processed": return None
            if status in {"failed","processing"} and attempts>=2:
                logger.warning("Skipping repeatedly failed Gmail message: business=%s external_id=%s attempts=%d status=%s",business_id,external_id,attempts,status)
                return None
            updated=self._request("PATCH","external_messages",params={"id":f"eq.{row['id']}"},json={"processing_status":"processing","attempt_count":attempts+1,"last_attempt_at":now,"last_error":None})
            return updated[0] if updated else row
        payload={"business_id":business_id,"provider":"gmail","external_message_id":external_id,"external_thread_id":data.get("external_thread_id"),"customer_id":None,"session_id":None,"direction":"inbound","sender_email":data.get("sender_email"),"recipient_email":data.get("recipient_email"),"subject":data.get("subject"),"body":data.get("body","") ,"received_at":now,"processed_at":None,"processing_status":"processing","attempt_count":1,"last_attempt_at":now}
        rows=self._request("POST","external_messages",headers={"Prefer":"return=representation"},json=payload)
        return rows[0] if rows else None
    def mark_sent(self,business_id:str,external_id:str,sent_id:str,reply:str,customer_id:str,session_id:str)->None:
        self._request("PATCH","external_messages",params={"business_id":f"eq.{business_id}","provider":"eq.gmail","external_message_id":f"eq.{external_id}"},json={"processing_status":"sent","outbound_message_id":sent_id,"outbound_body":reply,"customer_id":customer_id,"session_id":session_id,"last_error":None})
    def mark_processed(self,business_id:str,external_id:str)->None:
        self._request("PATCH","external_messages",params={"business_id":f"eq.{business_id}","provider":"eq.gmail","external_message_id":f"eq.{external_id}"},json={"processing_status":"processed","processed_at":datetime.now(timezone.utc).isoformat(),"last_error":None})
    def mark_failed(self,business_id:str,external_id:str,error:str)->None:
        self._request("PATCH","external_messages",params={"business_id":f"eq.{business_id}","provider":"eq.gmail","external_message_id":f"eq.{external_id}"},json={"processing_status":"failed","last_error":error[:1000]})
    def list_processed_messages(self,business_id:str,limit:int=50)->list[dict[str,Any]]: return self._request("GET","external_messages",params={"business_id":f"eq.{business_id}","provider":"eq.gmail","direction":"eq.inbound","select":"external_message_id,external_thread_id,customer_id,session_id,sender_email,subject,body,received_at","order":"received_at.desc","limit":str(limit)})
    def record_message(self,business_id:str,data:dict[str,Any],customer_id:str|None,session_id:str|None,direction:str,external_id:str|None=None)->None:
        payload={"business_id":business_id,"provider":"gmail","external_message_id":external_id or data["external_message_id"],"external_thread_id":data.get("external_thread_id"),"customer_id":customer_id,"session_id":session_id,"direction":direction,"sender_email":data.get("sender_email"),"recipient_email":data.get("recipient_email"),"subject":data.get("subject"),"body":data.get("body","") ,"received_at":datetime.now(timezone.utc).isoformat(),"processed_at":datetime.now(timezone.utc).isoformat()}
        self._request("POST","external_messages",headers={"Prefer":"resolution=ignore-duplicates"},json=payload)
    def remember_identity(self,business_id:str,customer_id:str,email:str)->None: self._request("POST","customer_external_identities",params={"on_conflict":"business_id,provider,external_id"},headers={"Prefer":"resolution=ignore-duplicates"},json={"business_id":business_id,"customer_id":customer_id,"provider":"gmail","external_id":email.lower()})

def _find_customer(store:StructuredStore,business_id:str,email:str)->dict[str,Any]|None:
    if hasattr(store,"customer_by_email"): return store.customer_by_email(email,business_id)
    rows=store._get("customers",{"business_id":f"eq.{business_id}","email":f"eq.{email.lower()}","archived_at":"is.null","select":"id,name,email,tier","limit":"1"}); return rows[0] if rows else None

def _gmail_session(sessions:SupabaseSessionStore,thread_id:str|None,customer_id:str,business_id:str)->tuple[str,Any]:
    base=f"gmail:{thread_id}" if thread_id else f"gmail:{customer_id}"
    try:
        return base,sessions.get_or_create(base,customer_id,business_id)
    except ValueError as exc:
        scoped=f"{base}:{customer_id}"
        logger.warning("Gmail thread belongs to another customer; using customer-scoped session: business=%s thread=%s customer=%s",business_id,thread_id,customer_id)
        return scoped,sessions.get_or_create(scoped,customer_id,business_id)

def _restore_sent_message(business_id:str,external_id:str,status_row:dict[str,Any],sessions:SupabaseSessionStore,integration_store:IntegrationStore,gmail:GmailIntegration,token:str)->bool:
    session_id=status_row.get("session_id"); customer_id=status_row.get("customer_id"); reply=status_row.get("outbound_body") or ""
    if session_id and customer_id and reply:
        session=sessions.get(session_id,customer_id,business_id)
        if session and not any(m.role=="assistant" and m.content==reply for m in session.messages):
            sessions.append(session_id,Message(role="assistant",content=reply))
        sent_id=status_row.get("outbound_message_id")
        if sent_id:
            integration_store.record_message(business_id,{"external_message_id":sent_id,"external_thread_id":status_row.get("external_thread_id"),"sender_email":"","recipient_email":"","body":reply},customer_id,session_id,"outbound",sent_id)
    integration_store.mark_processed(business_id,external_id)
    gmail.mark_read(token,external_id)
    return True

def process_gmail_messages(business_id:str,connection:dict[str,Any],agent:KnownAgent,store:StructuredStore,sessions:SupabaseSessionStore,integration_store:IntegrationStore,gmail:GmailIntegration)->dict[str,int]:
    token=connection["access_token"]
    try: message_ids=gmail.list_message_ids(token,max_results=20)
    except httpx.HTTPStatusError as exc:
        if exc.response.status_code!=401 or not connection.get("refresh_token"): raise
        logger.warning("Gmail access token rejected; refreshing before polling business=%s",business_id)
        refreshed=gmail.refresh(connection["refresh_token"]); token=refreshed["access_token"]; integration_store.update_tokens(connection["id"],refreshed); message_ids=gmail.list_message_ids(token,max_results=20)
    processed=matched=ignored=created=failed=0
    logger.info("Gmail message batch loaded: business=%s count=%d",business_id,len(message_ids))
    for external_id in message_ids:
        status_row=integration_store.message_status(business_id,external_id)
        status=status_row.get("processing_status") if status_row else None
        attempts=int(status_row.get("attempt_count") or 0) if status_row else 0
        if status=="processed" or (status in {"failed","processing"} and attempts>=2):
            ignored+=1
            continue
        if status=="sent" and status_row:
            try:
                _restore_sent_message(business_id,external_id,status_row,sessions,integration_store,gmail,token)
                processed+=1; matched+=1
            except Exception as exc:
                failed+=1
                logger.exception("Failed to finalize previously sent Gmail message: business=%s external_id=%s error=%s",business_id,external_id,exc)
                try: integration_store.mark_failed(business_id,external_id,str(exc))
                except Exception: pass
            continue
        parsed:dict[str,Any]={}
        try:
            raw=gmail.get_message(token,external_id)
            parsed=gmail.parse_message(raw)
            claim=integration_store.claim_message(business_id,parsed)
            if claim is None:
                ignored+=1; continue
            sender=parsed.get("sender_email","")
            if not sender:
                integration_store.mark_failed(business_id,external_id,"Inbound Gmail message has no sender email")
                ignored+=1; continue
            customer=_find_customer(store,business_id,sender)
            if customer is None:
                if not hasattr(store,"create_customer"): raise RuntimeError("Customer store cannot create new customers")
                customer=store.create_customer(business_id,sender,parsed.get("sender_name","") or sender.split("@",1)[0]); created+=1
            integration_store.remember_identity(business_id,customer["id"],customer["email"])
            session_id,session=_gmail_session(sessions,parsed.get("external_thread_id"),customer["id"],business_id)
            body=(parsed.get("body") or "").strip() or "Please review this support email."
            if not any(m.content==body and m.role=="user" for m in session.messages): sessions.append(session_id,Message(role="user",content=body))
            orders=store.orders(customer["id"],business_id); request=SupportContextRequest(customer=Customer(**customer),message=body,conversation=list(session.messages),orders=[Order(**o) for o in orders])
            result=agent.handle(request,auth=AuthContext(user_id="gmail",business_id=business_id,email=customer.get("email")))
            sent=gmail.send(token,customer["email"],f"Re: {parsed.get('subject','Support request')}",result.reply,thread_id=parsed.get("external_thread_id"),in_reply_to=parsed.get("message_id_header"))
            sent_id=sent.get("id",f"sent:{external_id}")
            integration_store.mark_sent(business_id,external_id,sent_id,result.reply,customer["id"],session_id)
            sessions.append(session_id,Message(role="assistant",content=result.reply))
            integration_store.record_message(business_id,{**parsed,"external_message_id":sent_id,"sender_email":parsed.get("recipient_email"),"recipient_email":customer["email"],"body":result.reply},customer["id"],session_id,"outbound",sent_id)
            integration_store.mark_processed(business_id,external_id)
            gmail.mark_read(token,external_id); processed+=1; matched+=1
        except Exception as exc:
            failed+=1
            logger.exception("Gmail message processing failed: business=%s external_id=%s subject=%r error=%s",business_id,external_id,parsed.get("subject"),exc)
            if external_id:
                try: integration_store.mark_failed(business_id,external_id,str(exc))
                except Exception: pass
            continue
    return {"processed":processed,"matched":matched,"ignored":ignored,"created":created,"failed":failed}
