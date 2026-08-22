create extension if not exists pgcrypto;

create table if not exists public.businesses (
  id uuid primary key default gen_random_uuid(),
  name text not null,
  created_at timestamptz not null default now()
);

create table if not exists public.customers (
  id text primary key,
  business_id uuid not null references public.businesses(id) on delete cascade,
  name text not null,
  email text not null,
  tier text not null default 'standard',
  created_at timestamptz not null default now()
);

create table if not exists public.orders (
  id text primary key,
  business_id uuid not null references public.businesses(id) on delete cascade,
  customer_id text not null references public.customers(id) on delete cascade,
  status text not null,
  total numeric(12,2) not null default 0,
  items jsonb not null default '[]'::jsonb,
  created_at timestamptz not null default now()
);

create index if not exists customers_business_id_idx on public.customers(business_id);
create index if not exists orders_business_customer_idx on public.orders(business_id, customer_id);

alter table public.businesses enable row level security;
alter table public.customers enable row level security;
alter table public.orders enable row level security;

-- Application access should be through authenticated tenant-scoped policies.
-- The service-role key used by the backend bypasses RLS; browser clients must
-- never receive that key.
create policy "customers own business" on public.customers
  for all using (business_id::text = coalesce(auth.jwt()->>'business_id', ''))
  with check (business_id::text = coalesce(auth.jwt()->>'business_id', ''));

create policy "orders own business" on public.orders
  for all using (business_id::text = coalesce(auth.jwt()->>'business_id', ''))
  with check (business_id::text = coalesce(auth.jwt()->>'business_id', ''));
