create table identity.coexistence_runs (
  id uuid primary key default gen_random_uuid(),
  run_type text not null,
  status text not null,
  started_at timestamptz not null default now(),
  finished_at timestamptz,
  users_seen integer not null default 0,
  users_changed integer not null default 0,
  profiles_seen integer not null default 0,
  profiles_changed integer not null default 0,
  roles_changed integer not null default 0,
  drift_count integer,
  error_code text,
  error_message text,
  metadata jsonb not null default '{}'::jsonb,
  constraint identity_coexistence_runs_type_chk
    check (run_type in ('backfill', 'reconciliation', 'trigger')),
  constraint identity_coexistence_runs_status_chk
    check (status in ('running', 'succeeded', 'failed')),
  constraint identity_coexistence_runs_counts_chk
    check (
      users_seen >= 0
      and users_changed >= 0
      and profiles_seen >= 0
      and profiles_changed >= 0
      and roles_changed >= 0
      and (drift_count is null or drift_count >= 0)
    ),
  constraint identity_coexistence_runs_finished_at_chk
    check (
      (status = 'running' and finished_at is null)
      or (status <> 'running' and finished_at is not null)
    ),
  constraint identity_coexistence_runs_error_chk
    check (
      (status = 'failed' and error_code is not null)
      or (status <> 'failed' and error_code is null and error_message is null)
    ),
  constraint identity_coexistence_runs_metadata_object_chk
    check (jsonb_typeof(metadata) = 'object')
);

create index identity_coexistence_runs_started_at_idx
  on identity.coexistence_runs (started_at desc);

create index identity_coexistence_runs_type_status_idx
  on identity.coexistence_runs (run_type, status, started_at desc);

revoke all on table identity.coexistence_runs from public;

create or replace function identity.derive_user_status(
  p_email_confirmed_at timestamptz,
  p_banned_until timestamptz,
  p_deleted_at timestamptz
)
returns identity.identity_user_status_t
language sql
stable
set search_path = pg_catalog
as $function$
  select case
    when p_deleted_at is not null then 'deleted'::identity.identity_user_status_t
    when p_banned_until is not null and p_banned_until > clock_timestamp()
      then 'disabled'::identity.identity_user_status_t
    when p_email_confirmed_at is null
      then 'pending_verification'::identity.identity_user_status_t
    else 'active'::identity.identity_user_status_t
  end
$function$;

create or replace function identity.append_coexistence_audit(
  p_action text,
  p_target_user_id uuid,
  p_outcome identity.audit_outcome_t,
  p_reason_code text,
  p_metadata jsonb
)
returns uuid
language plpgsql
security definer
set search_path = pg_catalog
as $function$
declare
  v_event_id uuid := gen_random_uuid();
begin
  insert into identity.audit_events (
    id,
    target_user_id,
    action,
    outcome,
    reason_code,
    metadata
  )
  values (
    v_event_id,
    p_target_user_id,
    p_action,
    p_outcome,
    p_reason_code,
    coalesce(p_metadata, '{}'::jsonb)
  );

  return v_event_id;
end
$function$;

create or replace function identity.sync_auth_user(
  p_user_id uuid,
  p_email text,
  p_email_confirmed_at timestamptz,
  p_banned_until timestamptz,
  p_deleted_at timestamptz,
  p_created_at timestamptz,
  p_updated_at timestamptz,
  p_audit_action text,
  p_operation text
)
returns boolean
language plpgsql
security definer
set search_path = pg_catalog
as $function$
declare
  v_changed boolean := false;
  v_email text;
  v_status identity.identity_user_status_t;
begin
  perform pg_advisory_xact_lock(hashtextextended(p_user_id::text, 21901));

  v_email := btrim(p_email);
  if v_email is null or v_email = '' then
    raise exception using
      errcode = '23502',
      message = 'IDENTITY_SYNC_FAILURE: auth.users.email is required';
  end if;

  v_status := identity.derive_user_status(
    p_email_confirmed_at,
    p_banned_until,
    p_deleted_at
  );

  insert into identity.users (
    id,
    email,
    email_normalized,
    password_hash,
    status,
    email_verified_at,
    created_at,
    updated_at,
    deleted_at
  )
  values (
    p_user_id,
    v_email,
    lower(v_email),
    null,
    v_status,
    p_email_confirmed_at,
    coalesce(p_created_at, clock_timestamp()),
    coalesce(p_updated_at, p_created_at, clock_timestamp()),
    p_deleted_at
  )
  on conflict (id) do update
  set
    email = excluded.email,
    email_normalized = excluded.email_normalized,
    status = excluded.status,
    email_verified_at = excluded.email_verified_at,
    created_at = excluded.created_at,
    updated_at = excluded.updated_at,
    deleted_at = excluded.deleted_at
  where (
    identity.users.email,
    identity.users.email_normalized,
    identity.users.status,
    identity.users.email_verified_at,
    identity.users.created_at,
    identity.users.updated_at,
    identity.users.deleted_at
  ) is distinct from (
    excluded.email,
    excluded.email_normalized,
    excluded.status,
    excluded.email_verified_at,
    excluded.created_at,
    excluded.updated_at,
    excluded.deleted_at
  )
  returning true into v_changed;

  v_changed := coalesce(v_changed, false);
  if v_changed then
    perform identity.append_coexistence_audit(
      p_audit_action,
      p_user_id,
      'success'::identity.audit_outcome_t,
      null,
      jsonb_build_object(
        'source', 'auth.users',
        'operation', p_operation,
        'sync_version', '0019'
      )
    );
  end if;

  return v_changed;
end
$function$;

create or replace function identity.ensure_default_role(
  p_user_id uuid,
  p_operation text
)
returns boolean
language plpgsql
security definer
set search_path = pg_catalog
as $function$
declare
  v_role_id uuid;
  v_changed boolean := false;
begin
  perform pg_advisory_xact_lock(hashtextextended(p_user_id::text, 21901));

  select role_record.id
  into strict v_role_id
  from identity.roles role_record
  where role_record.code = 'user';

  if not exists (
    select 1
    from identity.user_role_assignments assignment
    where assignment.user_id = p_user_id
      and assignment.revoked_at is null
  ) then
    insert into identity.user_role_assignments (
      user_id,
      role_id,
      reason
    )
    values (
      p_user_id,
      v_role_id,
      'Supabase coexistence default role'
    );
    v_changed := true;

    perform identity.append_coexistence_audit(
      'coexistence.role_defaulted',
      p_user_id,
      'success'::identity.audit_outcome_t,
      null,
      jsonb_build_object(
        'source', 'auth.users',
        'operation', p_operation,
        'role', 'user',
        'sync_version', '0019'
      )
    );
  end if;

  return v_changed;
end
$function$;

create or replace function identity.sync_legacy_role(
  p_user_id uuid,
  p_role_code text,
  p_effective_at timestamptz,
  p_operation text
)
returns boolean
language plpgsql
security definer
set search_path = pg_catalog
as $function$
declare
  v_desired_role_id uuid;
  v_active_assignment_id uuid;
  v_active_role_code text;
  v_changed boolean := false;
begin
  perform pg_advisory_xact_lock(hashtextextended(p_user_id::text, 21901));

  if p_role_code not in ('user', 'admin') then
    raise exception using
      errcode = '22023',
      message = 'IDENTITY_SYNC_FAILURE: unsupported public.profiles role';
  end if;

  select role_record.id
  into strict v_desired_role_id
  from identity.roles role_record
  where role_record.code = p_role_code;

  select assignment.id, role_record.code
  into v_active_assignment_id, v_active_role_code
  from identity.user_role_assignments assignment
  join identity.roles role_record
    on role_record.id = assignment.role_id
  where assignment.user_id = p_user_id
    and assignment.revoked_at is null
  for update of assignment;

  if v_active_assignment_id is null then
    insert into identity.user_role_assignments (
      user_id,
      role_id,
      reason
    )
    values (
      p_user_id,
      v_desired_role_id,
      'Mirrored from public.profiles'
    );
    v_changed := true;
  elsif v_active_role_code = p_role_code then
    return false;
  elsif v_active_role_code in ('user', 'admin') then
    update identity.user_role_assignments
    set
      revoked_at = coalesce(p_effective_at, clock_timestamp()),
      reason = 'Superseded by explicit public.profiles role change'
    where id = v_active_assignment_id;

    insert into identity.user_role_assignments (
      user_id,
      role_id,
      reason
    )
    values (
      p_user_id,
      v_desired_role_id,
      'Mirrored from public.profiles'
    );
    v_changed := true;
  else
    perform identity.append_coexistence_audit(
      'coexistence.role_preserved',
      p_user_id,
      'denied'::identity.audit_outcome_t,
      'UNRELATED_ACTIVE_ROLE',
      jsonb_build_object(
        'source', 'public.profiles',
        'operation', p_operation,
        'active_role', v_active_role_code,
        'requested_role', p_role_code,
        'sync_version', '0019'
      )
    );
    return false;
  end if;

  if v_changed then
    perform identity.append_coexistence_audit(
      'coexistence.role_synced',
      p_user_id,
      'success'::identity.audit_outcome_t,
      null,
      jsonb_build_object(
        'source', 'public.profiles',
        'operation', p_operation,
        'previous_role', v_active_role_code,
        'role', p_role_code,
        'sync_version', '0019'
      )
    );
  end if;

  return v_changed;
end
$function$;

create or replace function identity.sync_public_profile(
  p_user_id uuid,
  p_full_name text,
  p_role_code text,
  p_created_at timestamptz,
  p_sync_role boolean,
  p_operation text
)
returns table (profile_changed boolean, role_changed boolean)
language plpgsql
security definer
set search_path = pg_catalog
as $function$
declare
  v_auth_user auth.users%%rowtype;
  v_profile_changed boolean := false;
  v_role_changed boolean := false;
begin
  perform pg_advisory_xact_lock(hashtextextended(p_user_id::text, 21901));

  select auth_user.*
  into v_auth_user
  from auth.users auth_user
  where auth_user.id = p_user_id;

  if not found then
    raise exception using
      errcode = '23503',
      message = 'IDENTITY_SYNC_FAILURE: public.profiles user is missing from auth.users';
  end if;

  perform identity.sync_auth_user(
    v_auth_user.id,
    v_auth_user.email,
    v_auth_user.email_confirmed_at,
    v_auth_user.banned_until,
    v_auth_user.deleted_at,
    v_auth_user.created_at,
    v_auth_user.updated_at,
    'coexistence.user_synced',
    p_operation
  );

  insert into identity.user_profiles (
    user_id,
    display_name,
    created_at,
    updated_at
  )
  values (
    p_user_id,
    p_full_name,
    coalesce(p_created_at, clock_timestamp()),
    clock_timestamp()
  )
  on conflict (user_id) do update
  set
    display_name = excluded.display_name,
    updated_at = excluded.updated_at
  where identity.user_profiles.display_name is distinct from excluded.display_name
  returning true into v_profile_changed;

  v_profile_changed := coalesce(v_profile_changed, false);
  if v_profile_changed then
    perform identity.append_coexistence_audit(
      'coexistence.profile_synced',
      p_user_id,
      'success'::identity.audit_outcome_t,
      null,
      jsonb_build_object(
        'source', 'public.profiles',
        'operation', p_operation,
        'sync_version', '0019'
      )
    );
  end if;

  if p_sync_role then
    v_role_changed := identity.sync_legacy_role(
      p_user_id,
      p_role_code,
      clock_timestamp(),
      p_operation
    );
  end if;

  return query select v_profile_changed, v_role_changed;
end
$function$;

create or replace function public.handle_new_user()
returns trigger
language plpgsql
security definer
set search_path = pg_catalog
as $function$
declare
  v_profile_inserted boolean := false;
begin
  perform identity.sync_auth_user(
    new.id,
    new.email,
    new.email_confirmed_at,
    new.banned_until,
    new.deleted_at,
    new.created_at,
    new.updated_at,
    'coexistence.user_created',
    'INSERT'
  );

  insert into identity.user_profiles (
    user_id,
    display_name,
    created_at,
    updated_at
  )
  values (
    new.id,
    null,
    coalesce(new.created_at, clock_timestamp()),
    coalesce(new.updated_at, new.created_at, clock_timestamp())
  )
  on conflict (user_id) do nothing
  returning true into v_profile_inserted;

  if coalesce(v_profile_inserted, false) then
    perform identity.append_coexistence_audit(
      'coexistence.profile_created',
      new.id,
      'success'::identity.audit_outcome_t,
      null,
      jsonb_build_object(
        'source', 'auth.users',
        'operation', 'INSERT',
        'sync_version', '0019'
      )
    );
  end if;

  perform identity.ensure_default_role(new.id, 'INSERT');

  insert into public.profiles (id, email)
  values (new.id, new.email)
  on conflict (id) do nothing;

  perform identity.append_coexistence_audit(
    'coexistence.signup_synced',
    new.id,
    'success'::identity.audit_outcome_t,
    null,
    jsonb_build_object(
      'source', 'auth.users',
      'operation', 'INSERT',
      'sync_version', '0019'
    )
  );

  return new;
end
$function$;

create or replace function identity.handle_auth_user_updated()
returns trigger
language plpgsql
security definer
set search_path = pg_catalog
as $function$
begin
  perform identity.sync_auth_user(
    new.id,
    new.email,
    new.email_confirmed_at,
    new.banned_until,
    new.deleted_at,
    new.created_at,
    new.updated_at,
    'coexistence.user_synced',
    'UPDATE'
  );
  return new;
end
$function$;

create or replace function identity.handle_auth_user_deleted()
returns trigger
language plpgsql
security definer
set search_path = pg_catalog
as $function$
begin
  perform pg_advisory_xact_lock(hashtextextended(old.id::text, 21901));

  update identity.users
  set
    status = 'deleted'::identity.identity_user_status_t,
    updated_at = clock_timestamp(),
    deleted_at = coalesce(old.deleted_at, clock_timestamp())
  where id = old.id;

  if found then
    perform identity.append_coexistence_audit(
      'coexistence.user_deleted',
      old.id,
      'success'::identity.audit_outcome_t,
      null,
      jsonb_build_object(
        'source', 'auth.users',
        'operation', 'DELETE',
        'sync_version', '0019'
      )
    );
  end if;

  return old;
end
$function$;

create or replace function identity.handle_public_profile_changed()
returns trigger
language plpgsql
security definer
set search_path = pg_catalog
as $function$
declare
  v_sync_role boolean;
begin
  v_sync_role := tg_op = 'INSERT' or old.role is distinct from new.role;

  perform identity.sync_public_profile(
    new.id,
    new.full_name,
    new.role::text,
    new.created_at,
    v_sync_role,
    tg_op
  );

  return new;
end
$function$;

drop trigger if exists on_auth_user_identity_updated on auth.users;
create trigger on_auth_user_identity_updated
  after update of email, email_confirmed_at, banned_until, deleted_at, updated_at
  on auth.users
  for each row
  when (
    old.email is distinct from new.email
    or old.email_confirmed_at is distinct from new.email_confirmed_at
    or old.banned_until is distinct from new.banned_until
    or old.deleted_at is distinct from new.deleted_at
    or old.updated_at is distinct from new.updated_at
  )
  execute function identity.handle_auth_user_updated();

drop trigger if exists on_auth_user_identity_deleted on auth.users;
create trigger on_auth_user_identity_deleted
  after delete on auth.users
  for each row
  execute function identity.handle_auth_user_deleted();

drop trigger if exists on_profile_identity_inserted on public.profiles;
create trigger on_profile_identity_inserted
  after insert on public.profiles
  for each row
  execute function identity.handle_public_profile_changed();

drop trigger if exists on_profile_identity_updated on public.profiles;
create trigger on_profile_identity_updated
  after update of full_name, role on public.profiles
  for each row
  when (
    old.full_name is distinct from new.full_name
    or old.role is distinct from new.role
  )
  execute function identity.handle_public_profile_changed();

create or replace view identity.coexistence_drift
with (security_invoker = true)
as
select
  'missing_identity_user'::text as drift_type,
  auth_user.id as user_id,
  auth_user.email::text as source_value,
  null::text as mirror_value
from auth.users auth_user
left join identity.users identity_user on identity_user.id = auth_user.id
where identity_user.id is null

union all

select
  'orphan_identity_user',
  identity_user.id,
  null,
  identity_user.email
from identity.users identity_user
left join auth.users auth_user on auth_user.id = identity_user.id
where auth_user.id is null
  and identity_user.status <> 'deleted'::identity.identity_user_status_t

union all

select
  'email_mismatch',
  auth_user.id,
  lower(btrim(auth_user.email)),
  identity_user.email_normalized
from auth.users auth_user
join identity.users identity_user on identity_user.id = auth_user.id
where lower(btrim(auth_user.email)) is distinct from identity_user.email_normalized

union all

select
  'verification_mismatch',
  auth_user.id,
  auth_user.email_confirmed_at::text,
  identity_user.email_verified_at::text
from auth.users auth_user
join identity.users identity_user on identity_user.id = auth_user.id
where auth_user.email_confirmed_at is distinct from identity_user.email_verified_at

union all

select
  'status_mismatch',
  auth_user.id,
  identity.derive_user_status(
    auth_user.email_confirmed_at,
    auth_user.banned_until,
    auth_user.deleted_at
  )::text,
  identity_user.status::text
from auth.users auth_user
join identity.users identity_user on identity_user.id = auth_user.id
where identity.derive_user_status(
  auth_user.email_confirmed_at,
  auth_user.banned_until,
  auth_user.deleted_at
) is distinct from identity_user.status

union all

select
  'missing_public_profile',
  auth_user.id,
  auth_user.email,
  null
from auth.users auth_user
left join public.profiles public_profile on public_profile.id = auth_user.id
where public_profile.id is null

union all

select
  'missing_identity_profile',
  auth_user.id,
  public_profile.full_name,
  null
from auth.users auth_user
left join public.profiles public_profile on public_profile.id = auth_user.id
left join identity.user_profiles identity_profile
  on identity_profile.user_id = auth_user.id
where identity_profile.user_id is null

union all

select
  'profile_mismatch',
  public_profile.id,
  public_profile.full_name,
  identity_profile.display_name
from public.profiles public_profile
join identity.user_profiles identity_profile
  on identity_profile.user_id = public_profile.id
where public_profile.full_name is distinct from identity_profile.display_name

union all

select
  'missing_role_assignment',
  public_profile.id,
  public_profile.role::text,
  null
from public.profiles public_profile
left join identity.user_role_assignments assignment
  on assignment.user_id = public_profile.id
  and assignment.revoked_at is null
where assignment.id is null

union all

select
  'role_mismatch',
  public_profile.id,
  public_profile.role::text,
  role_record.code
from public.profiles public_profile
join identity.user_role_assignments assignment
  on assignment.user_id = public_profile.id
  and assignment.revoked_at is null
join identity.roles role_record on role_record.id = assignment.role_id
where public_profile.role::text is distinct from role_record.code

union all

select
  'duplicate_auth_email',
  auth_user.id,
  lower(btrim(auth_user.email)),
  duplicate_record.duplicate_count::text
from auth.users auth_user
join (
  select lower(btrim(email)) as email_normalized, count(*) as duplicate_count
  from auth.users
  where email is not null
  group by lower(btrim(email))
  having count(*) > 1
) duplicate_record
  on duplicate_record.email_normalized = lower(btrim(auth_user.email))

union all

select
  'duplicate_identity_email',
  identity_user.id,
  identity_user.email_normalized,
  duplicate_record.duplicate_count::text
from identity.users identity_user
join (
  select email_normalized, count(*) as duplicate_count
  from identity.users
  group by email_normalized
  having count(*) > 1
) duplicate_record
  on duplicate_record.email_normalized = identity_user.email_normalized;

create or replace view identity.coexistence_metrics
with (security_invoker = true)
as
select
  (select count(*) from auth.users) as source_users,
  (
    select count(*)
    from auth.users auth_user
    join identity.users identity_user on identity_user.id = auth_user.id
  ) as users_mirrored,
  (
    select count(*)
    from auth.users auth_user
    left join identity.users identity_user on identity_user.id = auth_user.id
    where identity_user.id is null
  ) as pending_users,
  (
    select count(*)
    from identity.coexistence_drift
  ) as drift_count,
  (
    select count(*)
    from identity.coexistence_runs
    where run_type = 'trigger' and status = 'failed'
  ) as trigger_failures,
  (
    select count(*)
    from identity.coexistence_runs
    where run_type in ('backfill', 'reconciliation') and status = 'failed'
  ) as sync_failures,
  (
    select max(finished_at)
    from identity.coexistence_runs
    where run_type = 'reconciliation' and status = 'succeeded'
  ) as last_reconciliation,
  case
    when (select count(*) from auth.users) = 0 then 1::numeric
    else round(
      (
        select count(*)::numeric
        from auth.users auth_user
        join identity.users identity_user on identity_user.id = auth_user.id
      ) / (select count(*)::numeric from auth.users),
      6
    )
  end as backfill_progress;

revoke all on function identity.derive_user_status(
  timestamptz,
  timestamptz,
  timestamptz
) from public;
revoke all on function identity.append_coexistence_audit(
  text,
  uuid,
  identity.audit_outcome_t,
  text,
  jsonb
) from public;
revoke all on function identity.sync_auth_user(
  uuid,
  text,
  timestamptz,
  timestamptz,
  timestamptz,
  timestamptz,
  timestamptz,
  text,
  text
) from public;
revoke all on function identity.ensure_default_role(uuid, text) from public;
revoke all on function identity.sync_legacy_role(
  uuid,
  text,
  timestamptz,
  text
) from public;
revoke all on function identity.sync_public_profile(
  uuid,
  text,
  text,
  timestamptz,
  boolean,
  text
) from public;
revoke all on function identity.handle_auth_user_updated() from public;
revoke all on function identity.handle_auth_user_deleted() from public;
revoke all on function identity.handle_public_profile_changed() from public;
revoke all on function public.handle_new_user() from public;
revoke all on table identity.coexistence_drift from public;
revoke all on table identity.coexistence_metrics from public;
