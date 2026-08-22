create table if not exists public.shopify_installations (
  id uuid primary key default gen_random_uuid(),
  business_id uuid not null references public.businesses(id) on delete cascade,
  shop_domain text not null,
  shop_name text,
  access_token_encrypted text not null,
  refresh_token_encrypted text,
  access_token_expires_at timestamptz,
  scopes text[] not null default '{}',
  installed_at timestamptz not null default now(),
  updated_at timestamptz not null default now(),
  last_synced_at timestamptz,
  sync_status text not null default 'never',
  sync_error text,
  unique (business_id),
  unique (shop_domain)
);

create table if not exists public.shopify_oauth_states (
  nonce text primary key,
  business_id uuid not null references public.businesses(id) on delete cascade,
  user_id uuid not null,
  shop_domain text not null,
  expires_at timestamptz not null,
  used_at timestamptz
);

create table if not exists public.shopify_webhook_events (
  webhook_id text primary key,
  shop_domain text not null,
  topic text not null,
  received_at timestamptz not null default now()
);

alter table public.shopify_installations enable row level security;
alter table public.shopify_oauth_states enable row level security;
alter table public.shopify_webhook_events enable row level security;

create policy "shopify installation own business" on public.shopify_installations
  for all using (business_id::text = coalesce(auth.jwt()->>'business_id', ''))
  with check (business_id::text = coalesce(auth.jwt()->>'business_id', ''));

create index if not exists shopify_installations_business_idx on public.shopify_installations(business_id);
create index if not exists shopify_oauth_states_expiry_idx on public.shopify_oauth_states(expires_at);
