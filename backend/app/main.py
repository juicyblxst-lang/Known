from __future__ import annotations
import os
from pathlib import Path
import httpx
from fastapi import Depends,FastAPI,HTTPException
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
app=FastAPI(title='Known',version='0.6.0')
app.add_middleware(CORSMiddleware,allow_origins=[x.strip() for x in os.getenv('KNOWN_CORS_ORIGINS','http://localhost:8000').split(',') if x.strip()],allow_credentials=True,allow_methods=['*'],allow_headers=['*'])
app.include_router(router);app.include_router(lifecycle_router);agent=KnownAgent();durable_sessions=SupabaseSessionStore();store=StructuredStore()
class SupportSessionResponse(SupportResponse):
 session_id:str;conversation:list[Message];persistence:str
@app.get('/health')
def health():return {'status':'ok','service':'known','version':'0.6.0','conversation_persistence':'supabase' if durable_sessions.configured else 'unavailable'}
@app.get('/ready')
def ready():
 sibyl=agent.memory.health() if isinstance(agent.memory,SibylMemory) else {'configured':True};checks={'frontend':(Path(__file__).resolve().parents[2]/'frontend').exists(),'supabase':store.configured and durable_sessions.configured,'openai':bool(os.getenv('OPENAI_API_KEY')),'sibyl':bool(sibyl.get('configured'))};return {'status':'ready' if all(checks.values()) else 'degraded','checks':checks,'sibyl':sibyl}
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
