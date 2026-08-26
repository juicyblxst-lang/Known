create table if not exists public.customer_memories (
  id uuid primary key default gen_random_uuid(),
  business_id uuid not null references public.businesses(id) on delete cascade,
  customer_id text not null references public.customers(id) on delete cascade,
  memory_type text not null default 'customer_history',
  content text not null,
  source text not null default 'support',
  source_id text,
  created_at timestamptz not null default now(),
  unique (business_id, customer_id, memory_type, content)
);

create index if not exists customer_memories_lookup_idx on public.customer_memories(business_id, customer_id, created_at desc);

create table if not exists public.integration_connections (
  id uuid primary key default gen_random_uuid(),
  business_id uuid not null references public.businesses(id) on delete cascade,
  provider text not null,
  external_account_id text,
  access_token text not null,
  refresh_token text,
  token_expires_at timestamptz,
  metadata jsonb not null default '{}'::jsonb,
  created_at timestamptz not null default now(),
  updated_at timestamptz not null default now(),
  unique (business_id, provider)
);

create table if not exists public.external_messages (
  id uuid primary key default gen_random_uuid(),
  business_id uuid not null references public.businesses(id) on delete cascade,
  provider text not null,
  external_message_id text not null,
  external_thread_id text,
  customer_id text references public.customers(id) on delete set null,
  session_id text,
  direction text not null,
  sender_email text,
  recipient_email text,
  subject text,
  body text not null default '',
  received_at timestamptz,
  processed_at timestamptz,
  created_at timestamptz not null default now(),
  unique (business_id, provider, external_message_id)
);

create table if not exists public.customer_external_identities (
  id uuid primary key default gen_random_uuid(),
  business_id uuid not null references public.businesses(id) on delete cascade,
  customer_id text not null references public.customers(id) on delete cascade,
  provider text not null,
  external_id text not null,
  created_at timestamptz not null default now(),
  unique (business_id, provider, external_id)
);

alter table public.customer_memories enable row level security;
alter table public.integration_connections enable row level security;
alter table public.external_messages enable row level security;
alter table public.customer_external_identities enable row level security;

create policy "customer memories own business" on public.customer_memories for all using (business_id::text = coalesce(auth.jwt()->>'business_id','')) with check (business_id::text = coalesce(auth.jwt()->>'business_id',''));
create policy "integration connections own business" on public.integration_connections for all using (business_id::text = coalesce(auth.jwt()->>'business_id','')) with check (business_id::text = coalesce(auth.jwt()->>'business_id',''));
create policy "external messages own business" on public.external_messages for all using (business_id::text = coalesce(auth.jwt()->>'business_id','')) with check (business_id::text = coalesce(auth.jwt()->>'business_id',''));
create policy "external identities own business" on public.customer_external_identities for all using (business_id::text = coalesce(auth.jwt()->>'business_id','')) with check (business_id::text = coalesce(auth.jwt()->>'business_id',''));
