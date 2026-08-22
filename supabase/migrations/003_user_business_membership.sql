create table if not exists public.business_memberships (
  user_id uuid not null references auth.users(id) on delete cascade,
  business_id uuid not null references public.businesses(id) on delete cascade,
  role text not null default 'agent' check (role in ('owner', 'admin', 'agent')),
  created_at timestamptz not null default now(),
  primary key (user_id, business_id)
);

create index if not exists business_memberships_business_idx on public.business_memberships(business_id);

alter table public.business_memberships enable row level security;

create policy "members can view own memberships" on public.business_memberships
  for select using (user_id = auth.uid());

create policy "business data follows membership" on public.businesses
  for select using (
    id in (select business_id from public.business_memberships where user_id = auth.uid())
  );

-- Populate app_metadata.business_id from this membership table through the
-- provisioning/onboarding service. The backend never accepts business_id from
-- an untrusted browser request.
