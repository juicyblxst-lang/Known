from __future__ import annotations
import os
from typing import Any
import httpx
class StructuredStore:
 def __init__(self): self.url=os.getenv("SUPABASE_URL","").rstrip("/"); self.key=os.getenv("SUPABASE_SERVICE_ROLE_KEY","")
 @property
 def configured(self): return bool(self.url and self.key)
 def _headers(self): return {"apikey":self.key,"Authorization":f"Bearer {self.key}","Content-Type":"application/json"}
 def _get(self,table,params):
  if not self.configured:return []
  r=httpx.get(f"{self.url}/rest/v1/{table}",params=params,headers=self._headers(),timeout=10);r.raise_for_status();d=r.json();return d if isinstance(d,list) else []
 def _post_many(self,table,rows):
  if not self.configured:raise RuntimeError("Structured backend is not configured")
  if not rows:return []
  r=httpx.post(f"{self.url}/rest/v1/{table}",params={"on_conflict":"id"},headers={**self._headers(),"Prefer":"resolution=merge-duplicates,return=representation"},json=rows,timeout=20);r.raise_for_status();d=r.json();return d if isinstance(d,list) else []
 def customers(self,business_id): return self._get("customers",{"business_id":f"eq.{business_id}","archived_at":"is.null","select":"id,name,email,tier,created_at","order":"name.asc"})
 def search(self,business_id,query):
  v=query.strip()
  if not v:return {"customers":[],"orders":[]}
  p=f"%{v}%"; c=self._get("customers",{"business_id":f"eq.{business_id}","archived_at":"is.null","or":f"name.ilike.{p},email.ilike.{p},id.ilike.{p}","select":"id,name,email,tier","limit":"8","order":"name.asc"}); o=self._get("orders",{"business_id":f"eq.{business_id}","id":f"ilike.{p}","select":"id,customer_id,status,total,items,created_at","limit":"8","order":"created_at.desc"}); return {"customers":c,"orders":o}
 def customer(self,customer_id,business_id=None):
  p={"id":f"eq.{customer_id}","archived_at":"is.null","limit":"1"}
  if business_id:p["business_id"]=f"eq.{business_id}"
  rows=self._get("customers",p);return rows[0] if rows else None
 def customer_by_email(self,email,business_id):
  normalized=email.strip().lower()
  if not normalized:return None
  rows=self._get("customers",{"business_id":f"eq.{business_id}","email":f"eq.{normalized}","archived_at":"is.null","select":"id,name,email,tier,created_at","limit":"1"})
  return rows[0] if rows else None
 def orders(self,customer_id,business_id=None):
  p={"customer_id":f"eq.{customer_id}","order":"created_at.desc"}
  if business_id:p["business_id"]=f"eq.{business_id}"
  return self._get("orders",p)
 def import_csv_records(self,business_id,customers,orders):
  cr=[{**r,"business_id":business_id} for r in customers];orr=[{**r,"business_id":business_id} for r in orders];return {"customers":len(self._post_many("customers",cr)),"orders":len(self._post_many("orders",orr))}
 def set_customer_archived(self,customer_id,business_id,archived=True):
  r=httpx.patch(f"{self.url}/rest/v1/customers",params={"id":f"eq.{customer_id}","business_id":f"eq.{business_id}"},headers={**self._headers(),"Prefer":"return=representation"},json={"archived_at":"now()" if archived else None},timeout=10);r.raise_for_status();d=r.json();return d[0] if d else None
 def delete_customer(self,customer_id,business_id):
  r=httpx.delete(f"{self.url}/rest/v1/customers",params={"id":f"eq.{customer_id}","business_id":f"eq.{business_id}"},headers=self._headers(),timeout=10);r.raise_for_status();return True
 def imports(self,business_id): return self._get("imports",{"business_id":f"eq.{business_id}","archived_at":"is.null","select":"id,name,customer_count,order_count,status,created_at,archived_at","order":"created_at.desc"})
 def create_import(self,business_id,name,customers,orders): return self._post_many("imports",[{"business_id":business_id,"name":name,"customer_count":customers,"order_count":orders}])[0]
 def rename_import(self,import_id,business_id,name):
  r=httpx.patch(f"{self.url}/rest/v1/imports",params={"id":f"eq.{import_id}","business_id":f"eq.{business_id}"},headers={**self._headers(),"Prefer":"return=representation"},json={"name":name},timeout=10);r.raise_for_status();d=r.json();return d[0] if d else None
 def archive_import(self,import_id,business_id):
  r=httpx.patch(f"{self.url}/rest/v1/imports",params={"id":f"eq.{import_id}","business_id":f"eq.{business_id}"},headers={**self._headers(),"Prefer":"return=representation"},json={"archived_at":"now()"},timeout=10);r.raise_for_status();d=r.json();return d[0] if d else None
 def delete_import(self,import_id,business_id):
  r=httpx.delete(f"{self.url}/rest/v1/imports",params={"id":f"eq.{import_id}","business_id":f"eq.{business_id}"},headers=self._headers(),timeout=10);r.raise_for_status();return True
