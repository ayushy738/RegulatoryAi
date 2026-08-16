-- Durable retry metadata for async regulatory email notifications.
-- notifications_log already has unique (user_id, event_id, channel) for idempotency.

alter table notifications_log
  add column if not exists attempts int not null default 0;

alter table notifications_log
  add column if not exists updated_at timestamptz not null default now();

create index if not exists notifications_log_delivery_idx
  on notifications_log (status, updated_at, id)
  where status in ('pending', 'failed');
