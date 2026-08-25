create table if not exists public.gmail_messages (
  id uuid primary key default gen_random_uuid(),
  business_id uuid not null references public.businesses(id) on delete cascade,
  gmail_message_id text not null,
  gmail_thread_id text,
  customer_id text not null,
  conversation_id text not null,
  direction text not null check (direction in ('inbound','outbound')),
  from_email text,
  to_email text,
  subject text,
  created_at timestamptz not null default now(),
  unique (business_id, gmail_message_id)
);
create index if not exists gmail_messages_thread_idx on public.gmail_messages(business_id,gmail_thread_id);
create index if not exists gmail_messages_customer_idx on public.gmail_messages(business_id,customer_id);
alter table public.gmail_messages enable row level security;
