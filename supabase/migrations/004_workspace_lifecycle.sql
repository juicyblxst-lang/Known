alter table public.customers add column if not exists archived_at timestamptz;
create index if not exists customers_business_archived_idx on public.customers(business_id, archived_at);

create table if not exists public.imports (
  id uuid primary key default gen_random_uuid(),
  business_id uuid not null references public.businesses(id) on delete cascade,
  name text not null,
  customer_count integer not null default 0,
  order_count integer not null default 0,
  status text not null default 'complete',
  archived_at timestamptz,
  created_at timestamptz not null default now()
);
create index if not exists imports_business_created_idx on public.imports(business_id, created_at desc);
alter table public.imports enable row level security;
create policy "imports own business" on public.imports for all using (business_id::text = coalesce(auth.jwt()->>'business_id','')) with check (business_id::text = coalesce(auth.jwt()->>'business_id',''));
