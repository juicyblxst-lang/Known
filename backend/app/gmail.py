from __future__ import annotations
import base64, json, os, secrets, urllib.parse
from email import message_from_bytes
from email.header import decode_header
from email.utils import parseaddr
import httpx

GOOGLE_AUTH = "https://accounts.google.com/o/oauth2/v2/auth"
GOOGLE_TOKEN = "https://oauth2.googleapis.com/token"
GMAIL_API = "https://gmail.googleapis.com/gmail/v1/users/me"
SCOPES = "https://www.googleapis.com/auth/gmail.modify https://www.googleapis.com/auth/gmail.send"

class GmailMailbox:
    def __init__(self):
        self.client_id=os.getenv("GOOGLE_CLIENT_ID","")
        self.client_secret=os.getenv("GOOGLE_CLIENT_SECRET","")
        self.redirect_uri=os.getenv("GOOGLE_REDIRECT_URI","")
    @property
    def configured(self): return bool(self.client_id and self.client_secret and self.redirect_uri)
    def authorization_url(self,state:str)->str:
        q={"client_id":self.client_id,"redirect_uri":self.redirect_uri,"response_type":"code","scope":SCOPES,"access_type":"offline","prompt":"consent","state":state}
        return GOOGLE_AUTH+"?"+urllib.parse.urlencode(q)
    def exchange_code(self,code:str)->dict:
        r=httpx.post(GOOGLE_TOKEN,data={"code":code,"client_id":self.client_id,"client_secret":self.client_secret,"redirect_uri":self.redirect_uri,"grant_type":"authorization_code"},timeout=20);r.raise_for_status();return r.json()
    def refresh(self,refresh_token:str)->dict:
        r=httpx.post(GOOGLE_TOKEN,data={"refresh_token":refresh_token,"client_id":self.client_id,"client_secret":self.client_secret,"grant_type":"refresh_token"},timeout=20);r.raise_for_status();return r.json()
    def messages(self,access_token:str,q:str="is:unread",max_results:int=25)->list[dict]:
        h={"Authorization":f"Bearer {access_token}"};r=httpx.get(f"{GMAIL_API}/messages",headers=h,params={"q":q,"maxResults":max_results},timeout=20);r.raise_for_status();return r.json().get("messages",[])
    def message(self,access_token:str,message_id:str)->dict:
        h={"Authorization":f"Bearer {access_token}"};r=httpx.get(f"{GMAIL_API}/messages/{message_id}",headers=h,params={"format":"raw"},timeout=20);r.raise_for_status();return r.json()
    @staticmethod
    def parse_raw(raw:str)->dict:
        msg=message_from_bytes(base64.urlsafe_b64decode(raw+'='*((4-len(raw)%4)%4)))
        def hdr(name):
            value=msg.get(name,""); return "".join((p.decode(enc or 'utf-8','replace') if isinstance(p,bytes) else p) for p,enc in decode_header(value))
        body=""
        if msg.is_multipart():
            for part in msg.walk():
                if part.get_content_type()=="text/plain" and part.get_content_disposition() not in ("attachment",): body=part.get_payload(decode=True).decode(part.get_content_charset() or 'utf-8','replace');break
        else: body=msg.get_payload(decode=True).decode(msg.get_content_charset() or 'utf-8','replace') if msg.get_payload(decode=True) else ""
        name,email=parseaddr(hdr("From"))
        return {"message_id":hdr("Message-ID"),"thread_id":hdr("X-GM-THRID"),"from_name":name,"from_email":email.lower(),"subject":hdr("Subject"),"body":body.strip()}
    def send(self,access_token:str,to:str,subject:str,body:str,thread_id:str|None=None)->dict:
        raw=f"To: {to}\r\nSubject: {subject}\r\nContent-Type: text/plain; charset=utf-8\r\n\r\n{body}".encode(); encoded=base64.urlsafe_b64encode(raw).decode().rstrip('=');payload={"raw":encoded};
        if thread_id: payload["threadId"]=thread_id
        r=httpx.post(f"{GMAIL_API}/messages/send",headers={"Authorization":f"Bearer {access_token}","Content-Type":"application/json"},json=payload,timeout=20);r.raise_for_status();return r.json()
