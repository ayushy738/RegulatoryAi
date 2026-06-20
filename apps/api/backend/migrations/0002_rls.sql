alter table profiles            enable row level security;
alter table subscriptions       enable row level security;
alter table user_event_state    enable row level security;
alter table chat_messages       enable row level security;
alter table events              enable row level security;
alter table documents           enable row level security;
alter table summaries           enable row level security;
alter table digests             enable row level security;
alter table digest_events       enable row level security;
alter table sources             enable row level security;

-- public regulatory data: authenticated read-only
create policy ev_read    on events        for select to authenticated using (true);
create policy doc_read   on documents     for select to authenticated using (true);
create policy sum_read   on summaries     for select to authenticated using (true);
create policy dig_read   on digests       for select to authenticated using (true);
create policy dige_read  on digest_events for select to authenticated using (true);
create policy src_read   on sources       for select to authenticated using (true);

-- user-owned rows: full CRUD only on own rows
create policy own_profile on profiles
  for all to authenticated using (id = auth.uid()) with check (id = auth.uid());
create policy own_subs on subscriptions
  for all to authenticated using (user_id = auth.uid()) with check (user_id = auth.uid());
create policy own_state on user_event_state
  for all to authenticated using (user_id = auth.uid()) with check (user_id = auth.uid());
create policy own_chat on chat_messages
  for all to authenticated using (user_id = auth.uid()) with check (user_id = auth.uid());
