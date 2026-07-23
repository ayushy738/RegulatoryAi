-- User-editable profile fields must not include authorization state.
-- The backend's privileged database role remains responsible for admin role changes.
drop policy if exists own_profile on public.profiles;

create policy own_profile_select on public.profiles
  for select to authenticated
  using (id = auth.uid());

create policy own_profile_update on public.profiles
  for update to authenticated
  using (id = auth.uid())
  with check (id = auth.uid());

revoke insert, delete, update on table public.profiles from public, anon, authenticated;
grant update (full_name) on table public.profiles to authenticated;
