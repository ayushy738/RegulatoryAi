-- Emergency synchronization rollback.
-- This intentionally preserves identity data, audit history, and migration history.

drop trigger if exists on_auth_user_identity_updated on auth.users;
drop trigger if exists on_auth_user_identity_deleted on auth.users;
drop trigger if exists on_profile_identity_inserted on public.profiles;
drop trigger if exists on_profile_identity_updated on public.profiles;

create or replace function public.handle_new_user()
returns trigger
language plpgsql
security definer
set search_path = pg_catalog
as $function$
begin
  insert into public.profiles (id, email)
  values (new.id, new.email)
  on conflict (id) do nothing;
  return new;
end
$function$;

revoke all on function public.handle_new_user() from public;

-- Keep the original trigger name and restore its pre-coexistence behavior.
drop trigger if exists on_auth_user_created on auth.users;
create trigger on_auth_user_created
  after insert on auth.users
  for each row
  execute function public.handle_new_user();
