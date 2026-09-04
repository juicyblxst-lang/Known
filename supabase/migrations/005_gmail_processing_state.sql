alter table public.external_messages
  add column if not exists processing_status text not null default 'processed',
  add column if not exists attempt_count integer not null default 0,
  add column if not exists last_error text,
  add column if not exists last_attempt_at timestamptz,
  add column if not exists outbound_message_id text,
  add column if not exists outbound_body text;

create index if not exists external_messages_processing_idx
  on public.external_messages(business_id, provider, processing_status, last_attempt_at);
