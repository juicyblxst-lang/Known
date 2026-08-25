create table if not exists public.gmail_connections (
  id uuid primary key default gen_random_uuid(),
  business_id uuid not null references public.businesses(id) on delete cascade,
  gmail_address text not null,
  access_token text not null,
  refresh_token text not null,
  token_type text,
  expires_at timestamptz,
  scopes text,
  created_at timestamptz not null default now(),
  updated_at timestamptz not null default now(),
  unique (business_id)
);

create index if not exists gmail_connections_business_id_idx on public.gmail_connections(business_id);

alter table public.gmail_connections enable row level security;
