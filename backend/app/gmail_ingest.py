from __future__ import annotations
from .gmail import GmailMailbox
from .gmail_store import GmailConnectionStore
from .store import StructuredStore
from .supabase_sessions import SupabaseSessionStore
from .models import Message, SupportContextRequest
from .production_agent import KnownAgent

class GmailIngestor:
 def __init__(self,gmail:GmailMailbox,connections:GmailConnectionStore,store:StructuredStore,sessions:SupabaseSessionStore,agent:KnownAgent):
  self.gmail=gmail;self.connections=connections;self.store=store;self.sessions=sessions;self.agent=agent
 def poll(self,business_id:str,max_results:int=25)->dict:
  connection=self.connections.get(business_id)
  if not connection:return {"connected":False,"processed":0,"matched":0,"ignored":0}
  token=connection["access_token"]
  try: messages=self.gmail.messages(token,"is:unread -from:me",max_results)
  except Exception:
   refreshed=self.gmail.refresh(connection["refresh_token"]);token=refreshed["access_token"];self.connections.upsert(business_id,{"gmail_address":connection["gmail_address"],"access_token":token,"refresh_token":connection["refresh_token"],"token_type":refreshed.get("token_type"),"expires_at":None,"scopes":connection.get("scopes","")});messages=self.gmail.messages(token,"is:unread -from:me",max_results)
  processed=matched=ignored=0
  for item in messages:
   raw=self.gmail.message(token,item["id"]).get("raw")
   if not raw:continue
   parsed=self.gmail.parse_raw(raw)
   customer=self.store.customer_by_email(parsed["from_email"],business_id)
   if not customer:
    ignored+=1;continue
   matched+=1
   session_id=f"gmail:{parsed.get('thread_id') or item['id']}"
   session=self.sessions.get_or_create(session_id,customer["id"],business_id)
   self.sessions.append(session_id,Message(role="user",content=parsed["body"]))
   result=self.agent.handle(SupportContextRequest(customer=customer,message=parsed["body"],conversation=session.messages+[Message(role="user",content=parsed["body"])],orders=self.store.orders(customer["id"],business_id)),auth=type("A",(),{"business_id":business_id})())
   self.sessions.append(session_id,Message(role="assistant",content=result.reply))
   self.gmail.send(token,parsed["from_email"],"Re: "+parsed["subject"],result.reply,parsed.get("thread_id"))
   processed+=1
  return {"connected":True,"processed":processed,"matched":matched,"ignored":ignored}
