alter table public.customers add column if not exists phone text;
alter table public.orders add column if not exists order_date timestamptz;
alter table public.orders add column if not exists fulfillment_status text;
alter table public.orders add column if not exists currency text;
alter table public.orders add column if not exists shipping_city text;
alter table public.orders add column if not exists shipping_country text;
alter table public.orders add column if not exists product_variant text;

create index if not exists customers_business_email_idx on public.customers(business_id, lower(email));
