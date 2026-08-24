from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel
import httpx
from .auth import AuthContext, require_auth
from .store import StructuredStore
router=APIRouter(prefix="/api")
store=StructuredStore()
def err(): return HTTPException(502,"Upstream data service unavailable")
@router.patch('/customers/{customer_id}/archive')
async def archive_customer(customer_id:str,auth:AuthContext=Depends(require_auth)):
 try:return {"status":"archived","customer":store.set_customer_archived(customer_id,auth.business_id,True)}
 except httpx.HTTPError:raise err()
@router.delete('/customers/{customer_id}')
async def delete_customer(customer_id:str,auth:AuthContext=Depends(require_auth)):
 try:store.delete_customer(customer_id,auth.business_id);return {"status":"deleted"}
 except httpx.HTTPError:raise err()
@router.get('/imports')
async def imports(auth:AuthContext=Depends(require_auth)):
 try:return store.imports(auth.business_id)
 except httpx.HTTPError:raise err()
class ImportRename(BaseModel): name:str
@router.patch('/imports/{import_id}')
async def rename_import(import_id:str,body:ImportRename,auth:AuthContext=Depends(require_auth)):
 try:return store.rename_import(import_id,auth.business_id,body.name.strip())
 except httpx.HTTPError:raise err()
@router.patch('/imports/{import_id}/archive')
async def archive_import(import_id:str,auth:AuthContext=Depends(require_auth)):
 try:return store.archive_import(import_id,auth.business_id)
 except httpx.HTTPError:raise err()
@router.delete('/imports/{import_id}')
async def delete_import(import_id:str,auth:AuthContext=Depends(require_auth)):
 try:store.delete_import(import_id,auth.business_id);return {"status":"deleted"}
 except httpx.HTTPError:raise err()
