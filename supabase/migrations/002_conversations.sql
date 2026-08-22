create table if not exists public.conversations (
  id text primary key,
  business_id uuid not null references public.businesses(id) on delete cascade,
  customer_id text not null references public.customers(id) on delete cascade,
  created_at timestamptz not null default now(),
  updated_at timestamptz not null default now()
);

create table if not exists public.conversation_messages (
  id uuid primary key default gen_random_uuid(),
  conversation_id text not null references public.conversations(id) on delete cascade,
  role text not null check (role in ('user', 'assistant', 'system')),
  content text not null,
  created_at timestamptz not null default now()
);

create index if not exists conversations_customer_idx on public.conversations(business_id, customer_id, updated_at desc);
create index if not exists conversation_messages_conversation_idx on public.conversation_messages(conversation_id, created_at);

alter table public.conversations enable row level security;
alter table public.conversation_messages enable row level security;

create policy "conversations own business" on public.conversations
  for all using (business_id::text = coalesce(auth.jwt()->>'business_id', ''))
  with check (business_id::text = coalesce(auth.jwt()->>'business_id', ''));

create policy "conversation messages own business" on public.conversation_messages
  for all using (
    conversation_id in (
      select id from public.conversations
      where business_id::text = coalesce(auth.jwt()->>'business_id', '')
    )
  )
  with check (
    conversation_id in (
      select id from public.conversations
      where business_id::text = coalesce(auth.jwt()->>'business_id', '')
    )
  );
