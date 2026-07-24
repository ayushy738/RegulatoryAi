insert into identity.roles (id, code, name, description, is_system)
values
  (
    '10000000-0000-4000-8000-000000000001',
    'user',
    'User',
    'Authenticated application user.',
    true
  ),
  (
    '10000000-0000-4000-8000-000000000002',
    'admin',
    'Admin',
    'Administrative application user.',
    true
  )
on conflict (code) do update
set
  name = excluded.name,
  description = excluded.description,
  is_system = excluded.is_system,
  updated_at = now();

insert into identity.permissions (id, code, resource, action, description)
values
  (
    '20000000-0000-4000-8000-000000000001',
    'application.access',
    'application',
    'access',
    'Access authenticated application functionality.'
  ),
  (
    '20000000-0000-4000-8000-000000000002',
    'admin.access',
    'admin',
    'access',
    'Access administrative functionality.'
  )
on conflict (code) do update
set
  resource = excluded.resource,
  action = excluded.action,
  description = excluded.description;

insert into identity.role_permissions (role_id, permission_id)
select role_record.id, permission_record.id
from (
  values
    ('user', 'application.access'),
    ('admin', 'application.access'),
    ('admin', 'admin.access')
) as mapping(role_code, permission_code)
join identity.roles role_record
  on role_record.code = mapping.role_code
join identity.permissions permission_record
  on permission_record.code = mapping.permission_code
on conflict (role_id, permission_id) do nothing;

create or replace function identity.backfill_from_supabase()
returns table (
  users_seen integer,
  users_changed integer,
  profiles_seen integer,
  profiles_changed integer,
  roles_changed integer
)
language plpgsql
security definer
set search_path = pg_catalog
as $function$
declare
  v_auth_user auth.users%%rowtype;
  v_public_profile public.profiles%%rowtype;
  v_user_changed boolean;
  v_profile_changed boolean;
  v_role_changed boolean;
begin
  users_seen := 0;
  users_changed := 0;
  profiles_seen := 0;
  profiles_changed := 0;
  roles_changed := 0;

  for v_auth_user in
    select auth_user.*
    from auth.users auth_user
    order by auth_user.id
  loop
    users_seen := users_seen + 1;
    v_user_changed := identity.sync_auth_user(
      v_auth_user.id,
      v_auth_user.email,
      v_auth_user.email_confirmed_at,
      v_auth_user.banned_until,
      v_auth_user.deleted_at,
      v_auth_user.created_at,
      v_auth_user.updated_at,
      'coexistence.user_backfilled',
      'BACKFILL'
    );
    users_changed := users_changed + case when v_user_changed then 1 else 0 end;
  end loop;

  for v_public_profile in
    select public_profile.*
    from public.profiles public_profile
    order by public_profile.id
  loop
    profiles_seen := profiles_seen + 1;

    select sync_result.profile_changed, sync_result.role_changed
    into v_profile_changed, v_role_changed
    from identity.sync_public_profile(
      v_public_profile.id,
      v_public_profile.full_name,
      v_public_profile.role::text,
      v_public_profile.created_at,
      true,
      'BACKFILL'
    ) sync_result;

    profiles_changed := profiles_changed
      + case when v_profile_changed then 1 else 0 end;
    roles_changed := roles_changed
      + case when v_role_changed then 1 else 0 end;
  end loop;

  return next;
end
$function$;

revoke all on function identity.backfill_from_supabase() from public;

do $backfill$
declare
  v_run_id uuid;
  v_result record;
begin
  insert into identity.coexistence_runs (
    run_type,
    status,
    metadata
  )
  values (
    'backfill',
    'running',
    jsonb_build_object('migration', '0020_identity_backfill.sql')
  )
  returning id into v_run_id;

  select *
  into v_result
  from identity.backfill_from_supabase();

  update identity.coexistence_runs
  set
    status = 'succeeded',
    finished_at = clock_timestamp(),
    users_seen = v_result.users_seen,
    users_changed = v_result.users_changed,
    profiles_seen = v_result.profiles_seen,
    profiles_changed = v_result.profiles_changed,
    roles_changed = v_result.roles_changed
  where id = v_run_id;
end
$backfill$;
