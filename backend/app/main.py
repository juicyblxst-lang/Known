from __future__ import annotations
import os
from pathlib import Path
import secrets
import httpx
from fastapi import Depends,FastAPI,HTTPException,Query
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import FileResponse,RedirectResponse
from fastapi.staticfiles import StaticFiles
from .api import router
from .lifecycle import router as lifecycle_router
from .auth import AuthContext,require_auth
from .memory import SibylMemory
from .models import Message,SupportContextRequest,SupportRequest,SupportResponse
from .production_agent import KnownAgent
from .store import StructuredStore
from .supabase_sessions import SupabaseSessionStore
from .gmail import GmailMailbox
from .gmail_store import GmailConnectionStore
from .gmail_ingest import GmailIngestor
app=FastAPI(title='Known',version='0.6.0')
app.add_middleware(CORSMiddleware,allow_origins=[x.strip() for x in os.getenv('KNOWN_CORS_ORIGINS','http://localhost:8000').split(',') if x.strip()],allow_credentials=True,allow_methods=['*'],allow_headers=['*'])
app.include_router(router);app.include_router(lifecycle_router);agent=KnownAgent();durable_sessions=SupabaseSessionStore();store=StructuredStore();gmail=GmailMailbox();gmail_connections=GmailConnectionStore();gmail_ingestor=GmailIngestor(gmail,gmail_connections,store,durable_sessions,agent);_gmail_states:dict[str,str]={}
class SupportSessionResponse(SupportResponse):
 session_id:str;conversation:list[Message];persistence:str
@app.get('/health')
def health():return {'status':'ok','service':'known','version':'0.6.0','conversation_persistence':'supabase' if durable_sessions.configured else 'unavailable'}
@app.get('/ready')
def ready():
 sibyl=agent.memory.health() if isinstance(agent.memory,SibylMemory) else {'configured':True};checks={'frontend':(Path(__file__).resolve().parents[2]/'frontend').exists(),'supabase':store.configured and durable_sessions.configured,'openai':bool(os.getenv('OPENAI_API_KEY')),'sibyl':bool(sibyl.get('configured'))};return {'status':'ready' if all(checks.values()) else 'degraded','checks':checks,'sibyl':sibyl}
@app.get('/api/gmail/connect')
def gmail_connect(auth:AuthContext=Depends(require_auth)):
 if not gmail.configured: raise HTTPException(503,'Gmail OAuth is not configured')
 state=secrets.token_urlsafe(32);_gmail_states[state]=auth.business_id
 return {'authorization_url':gmail.authorization_url(state)}
@app.get('/api/gmail/callback')
def gmail_callback(code:str=Query(...),state:str=Query(...)):
 business_id=_gmail_states.pop(state,None)
 if not business_id: raise HTTPException(400,'Invalid or expired Gmail OAuth state')
 try: tokens=gmail.exchange_code(code)
 except httpx.HTTPStatusError as exc: raise HTTPException(502,'Gmail authorization failed') from exc
 access=tokens.get('access_token');refresh=tokens.get('refresh_token')
 if not access or not refresh: raise HTTPException(502,'Gmail did not return a refresh token; reconnect with consent')
 try:
  profile=httpx.get('https://gmail.googleapis.com/gmail/v1/users/me/profile',headers={'Authorization':f'Bearer {access}'},timeout=10);profile.raise_for_status();email=profile.json().get('emailAddress','')
  gmail_connections.upsert(business_id,{'gmail_address':email,'access_token':access,'refresh_token':refresh,'token_type':tokens.get('token_type'),'expires_at':None,'scopes':tokens.get('scope','')})
 except httpx.HTTPError as exc: raise HTTPException(502,'Unable to save Gmail connection') from exc
 return RedirectResponse(url='/workspace.html?gmail=connected',status_code=303)
@app.get('/api/gmail/status')
def gmail_status(auth:AuthContext=Depends(require_auth)):
 connection=gmail_connections.get(auth.business_id);return {'connected':bool(connection),'email':connection.get('gmail_address') if connection else None}
@app.post('/api/gmail/poll')
def gmail_poll(auth:AuthContext=Depends(require_auth)):
 if not gmail_connections.get(auth.business_id): raise HTTPException(409,'Gmail is not connected')
 try:return gmail_ingestor.poll(auth.business_id)
 except Exception as exc:raise HTTPException(502,'Gmail inbox processing failed') from exc
@app.post('/api/internal/gmail/poll-all')
def gmail_poll_all(x_known_cron_secret:str=Query('',alias='X-Known-Cron-Secret')):
 secret=os.getenv('KNOWN_GMAIL_CRON_SECRET','')
 if not secret or x_known_cron_secret!=secret:raise HTTPException(401,'Unauthorized')
 results=[]
 for business_id in gmail_connections.list_business_ids():
  try:results.append({'business_id':business_id,**gmail_ingestor.poll(business_id)})
  except Exception as exc:results.append({'business_id':business_id,'error':str(exc)})
 return {'processed_businesses':len(results),'results':results}
@app.post('/api/support',response_model=SupportSessionResponse)
async def support(request:SupportRequest,session_id:str|None=None,auth:AuthContext=Depends(require_auth)):
 customer_data=store.customer(request.customer_id,auth.business_id)
 if customer_data is None:raise HTTPException(404,'customer not found')
 orders_data=store.orders(request.customer_id,auth.business_id)
 if not durable_sessions.configured:raise HTTPException(503,'Durable conversation persistence is not configured')
 resolved=session_id or request.conversation_id or f'{request.customer_id}:{os.urandom(8).hex()}'
 try:session=durable_sessions.get_or_create(resolved,request.customer_id,auth.business_id)
 except ValueError as exc:raise HTTPException(403,'session does not belong to customer') from exc
 context=SupportContextRequest(customer=customer_data,message=request.message,conversation=list(session.messages),orders=orders_data)
 durable_sessions.append(resolved,Message(role='user',content=request.message));result=agent.handle(context,auth=auth);durable_sessions.append(resolved,Message(role='assistant',content=result.reply));persisted=durable_sessions.get(resolved,request.customer_id,auth.business_id)
 return SupportSessionResponse(**result.model_dump(),session_id=resolved,conversation=persisted.messages,persistence='supabase')
@app.get('/api/sessions/{session_id}')
def get_session(session_id:str,customer_id:str,auth:AuthContext=Depends(require_auth)):
 if not durable_sessions.configured:raise HTTPException(503,'Durable conversation persistence is not configured')
 session=durable_sessions.get(session_id,customer_id,auth.business_id)
 if session is None:raise HTTPException(404,'session not found')
 return {'session_id':session.id,'customer_id':session.customer_id,'messages':[m.model_dump() for m in session.messages],'created_at':session.created_at,'updated_at':session.updated_at,'persistence':'supabase'}
FRONTEND_DIR=Path(__file__).resolve().parents[2]/'frontend'
if FRONTEND_DIR.exists():
 @app.get('/',include_in_schema=False)
 def landing():return FileResponse(FRONTEND_DIR/'landing.html')
 app.mount('/',StaticFiles(directory=FRONTEND_DIR,html=True),name='frontend')
else:
 @app.get('/')
 def frontend_unavailable():return RedirectResponse(url='/health')