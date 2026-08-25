from __future__ import annotations
import os
import httpx

class GmailConnectionStore:
    def __init__(self):
        self.url=os.getenv('SUPABASE_URL','').rstrip('/')
        self.key=os.getenv('SUPABASE_SERVICE_ROLE_KEY','')
    @property
    def configured(self): return bool(self.url and self.key)
    def _headers(self): return {'apikey':self.key,'Authorization':f'Bearer {self.key}','Content-Type':'application/json'}
    def upsert(self,business_id:str,data:dict):
        payload={**data,'business_id':business_id}
        r=httpx.post(f'{self.url}/rest/v1/gmail_connections',params={'on_conflict':'business_id'},headers={**self._headers(),'Prefer':'resolution=merge-duplicates,return=representation'},json=payload,timeout=10);r.raise_for_status(); rows=r.json(); return rows[0] if rows else None
    def get(self,business_id:str):
        r=httpx.get(f'{self.url}/rest/v1/gmail_connections',params={'business_id':f'eq.{business_id}','limit':'1'},headers=self._headers(),timeout=10);r.raise_for_status(); rows=r.json(); return rows[0] if rows else None
    def delete(self,business_id:str):
        r=httpx.delete(f'{self.url}/rest/v1/gmail_connections',params={'business_id':f'eq.{business_id}'},headers=self._headers(),timeout=10);r.raise_for_status()
