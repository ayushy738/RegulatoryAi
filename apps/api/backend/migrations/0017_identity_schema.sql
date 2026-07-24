create schema identity;

revoke all on schema identity from public;

create type identity.identity_user_status_t as enum (
  'pending_verification',
  'active',
  'locked',
  'disabled',
  'deleted'
);

create type identity.audit_outcome_t as enum (
  'success',
  'failure',
  'denied'
);

create table identity.users (
  id uuid primary key default gen_random_uuid(),
  email text not null,
  email_normalized text not null,
  password_hash text,
  status identity.identity_user_status_t not null default 'pending_verification',
  email_verified_at timestamptz,
  auth_version bigint not null default 1,
  failed_login_count integer not null default 0,
  locked_until timestamptz,
  password_changed_at timestamptz,
  last_login_at timestamptz,
  created_at timestamptz not null default now(),
  updated_at timestamptz not null default now(),
  deleted_at timestamptz,
  constraint identity_users_email_not_blank_chk
    check (length(btrim(email)) > 0),
  constraint identity_users_email_normalized_chk
    check (
      length(email_normalized) > 0
      and email_normalized = lower(btrim(email))
    ),
  constraint identity_users_email_normalized_key unique (email_normalized),
  constraint identity_users_auth_version_chk check (auth_version > 0),
  constraint identity_users_failed_login_count_chk check (failed_login_count >= 0),
  constraint identity_users_deleted_at_chk
    check (status <> 'deleted' or deleted_at is not null)
);

create index identity_users_status_idx
  on identity.users (status);

create index identity_users_created_at_idx
  on identity.users (created_at desc);

create index identity_users_locked_until_idx
  on identity.users (locked_until)
  where locked_until is not null;

create index identity_users_deleted_at_idx
  on identity.users (deleted_at)
  where deleted_at is not null;

create table identity.user_profiles (
  user_id uuid primary key
    references identity.users(id) on delete cascade,
  display_name text,
  organization text,
  avatar_url text,
  preferences jsonb not null default '{}'::jsonb,
  bio text,
  created_at timestamptz not null default now(),
  updated_at timestamptz not null default now(),
  constraint identity_user_profiles_display_name_chk
    check (display_name is null or length(display_name) <= 200),
  constraint identity_user_profiles_organization_chk
    check (organization is null or length(organization) <= 255),
  constraint identity_user_profiles_avatar_url_chk
    check (avatar_url is null or length(avatar_url) <= 2048),
  constraint identity_user_profiles_bio_chk
    check (bio is null or length(bio) <= 2000),
  constraint identity_user_profiles_preferences_object_chk
    check (jsonb_typeof(preferences) = 'object')
);

create table identity.roles (
  id uuid primary key default gen_random_uuid(),
  code text not null,
  name text not null,
  description text,
  is_system boolean not null default true,
  created_at timestamptz not null default now(),
  updated_at timestamptz not null default now(),
  constraint identity_roles_code_key unique (code),
  constraint identity_roles_code_chk
    check (code ~ '^[a-z][a-z0-9_.-]{0,63}$'),
  constraint identity_roles_name_chk
    check (length(btrim(name)) between 1 and 100)
);

create table identity.permissions (
  id uuid primary key default gen_random_uuid(),
  code text not null,
  resource text not null,
  action text not null,
  description text,
  created_at timestamptz not null default now(),
  constraint identity_permissions_code_key unique (code),
  constraint identity_permissions_code_chk
    check (code ~ '^[a-z][a-z0-9_]*\.[a-z][a-z0-9_]*$'),
  constraint identity_permissions_resource_chk
    check (resource ~ '^[a-z][a-z0-9_]*$'),
  constraint identity_permissions_action_chk
    check (action ~ '^[a-z][a-z0-9_]*$'),
  constraint identity_permissions_parts_chk
    check (code = resource || '.' || action)
);

create table identity.role_permissions (
  role_id uuid not null
    references identity.roles(id) on delete cascade,
  permission_id uuid not null
    references identity.permissions(id) on delete cascade,
  created_at timestamptz not null default now(),
  primary key (role_id, permission_id)
);

create index identity_role_permissions_permission_idx
  on identity.role_permissions (permission_id, role_id);

create table identity.user_role_assignments (
  id uuid primary key default gen_random_uuid(),
  user_id uuid not null
    references identity.users(id) on delete cascade,
  role_id uuid not null
    references identity.roles(id) on delete restrict,
  granted_by uuid
    references identity.users(id) on delete set null,
  granted_at timestamptz not null default now(),
  revoked_at timestamptz,
  reason text,
  constraint identity_user_role_assignments_revoked_at_chk
    check (revoked_at is null or revoked_at >= granted_at),
  constraint identity_user_role_assignments_reason_chk
    check (reason is null or length(reason) <= 500)
);

create unique index identity_user_role_assignments_active_user_idx
  on identity.user_role_assignments (user_id)
  where revoked_at is null;

create index identity_user_role_assignments_role_idx
  on identity.user_role_assignments (role_id)
  where revoked_at is null;

create index identity_user_role_assignments_history_idx
  on identity.user_role_assignments (user_id, granted_at desc);

create table identity.password_reset_tokens (
  id uuid primary key default gen_random_uuid(),
  user_id uuid not null
    references identity.users(id) on delete cascade,
  token_hash bytea not null,
  created_at timestamptz not null default now(),
  expires_at timestamptz not null,
  consumed_at timestamptz,
  invalidated_at timestamptz,
  constraint identity_password_reset_tokens_hash_key unique (token_hash),
  constraint identity_password_reset_tokens_hash_length_chk
    check (octet_length(token_hash) = 32),
  constraint identity_password_reset_tokens_expiry_chk
    check (expires_at > created_at),
  constraint identity_password_reset_tokens_consumed_at_chk
    check (consumed_at is null or consumed_at >= created_at),
  constraint identity_password_reset_tokens_invalidated_at_chk
    check (invalidated_at is null or invalidated_at >= created_at)
);

create index identity_password_reset_tokens_active_user_idx
  on identity.password_reset_tokens (user_id, expires_at)
  where consumed_at is null and invalidated_at is null;

create index identity_password_reset_tokens_expires_at_idx
  on identity.password_reset_tokens (expires_at);

create table identity.email_verification_tokens (
  id uuid primary key default gen_random_uuid(),
  user_id uuid not null
    references identity.users(id) on delete cascade,
  email_normalized text not null,
  token_hash bytea not null,
  created_at timestamptz not null default now(),
  expires_at timestamptz not null,
  consumed_at timestamptz,
  invalidated_at timestamptz,
  constraint identity_email_verification_tokens_hash_key unique (token_hash),
  constraint identity_email_verification_tokens_email_chk
    check (
      length(email_normalized) > 0
      and email_normalized = lower(btrim(email_normalized))
    ),
  constraint identity_email_verification_tokens_hash_length_chk
    check (octet_length(token_hash) = 32),
  constraint identity_email_verification_tokens_expiry_chk
    check (expires_at > created_at),
  constraint identity_email_verification_tokens_consumed_at_chk
    check (consumed_at is null or consumed_at >= created_at),
  constraint identity_email_verification_tokens_invalidated_at_chk
    check (invalidated_at is null or invalidated_at >= created_at)
);

create index identity_email_verification_tokens_active_user_idx
  on identity.email_verification_tokens (user_id, expires_at)
  where consumed_at is null and invalidated_at is null;

create index identity_email_verification_tokens_expires_at_idx
  on identity.email_verification_tokens (expires_at);

create table identity.auth_sessions (
  sid uuid primary key default gen_random_uuid(),
  user_id uuid not null
    references identity.users(id) on delete cascade,
  auth_version bigint not null,
  created_at timestamptz not null default now(),
  last_seen_at timestamptz not null default now(),
  expires_at timestamptz not null,
  revoked_at timestamptz,
  revocation_reason text,
  device text,
  ip_hash bytea,
  user_agent_hash bytea,
  constraint identity_auth_sessions_auth_version_chk
    check (auth_version > 0),
  constraint identity_auth_sessions_expiry_chk
    check (expires_at > created_at),
  constraint identity_auth_sessions_last_seen_at_chk
    check (last_seen_at >= created_at),
  constraint identity_auth_sessions_revoked_at_chk
    check (revoked_at is null or revoked_at >= created_at),
  constraint identity_auth_sessions_revocation_reason_chk
    check (revocation_reason is null or length(revocation_reason) <= 500),
  constraint identity_auth_sessions_device_chk
    check (device is null or length(device) <= 500),
  constraint identity_auth_sessions_ip_hash_length_chk
    check (ip_hash is null or octet_length(ip_hash) = 32),
  constraint identity_auth_sessions_user_agent_hash_length_chk
    check (user_agent_hash is null or octet_length(user_agent_hash) = 32)
);

create index identity_auth_sessions_active_user_idx
  on identity.auth_sessions (user_id, expires_at)
  where revoked_at is null;

create index identity_auth_sessions_expires_at_idx
  on identity.auth_sessions (expires_at);

create index identity_auth_sessions_revoked_at_idx
  on identity.auth_sessions (revoked_at)
  where revoked_at is not null;

create table identity.audit_events (
  id uuid primary key default gen_random_uuid(),
  occurred_at timestamptz not null default now(),
  actor_user_id uuid
    references identity.users(id) on delete set null,
  target_user_id uuid
    references identity.users(id) on delete set null,
  session_id uuid
    references identity.auth_sessions(sid) on delete set null,
  action text not null,
  outcome identity.audit_outcome_t not null,
  reason_code text,
  request_id text,
  ip_hash bytea,
  user_agent_hash bytea,
  metadata jsonb not null default '{}'::jsonb,
  constraint identity_audit_events_action_chk
    check (
      length(action) between 3 and 100
      and action ~ '^[a-z][a-z0-9_]*\.[a-z][a-z0-9_]*$'
    ),
  constraint identity_audit_events_reason_code_chk
    check (
      reason_code is null
      or reason_code ~ '^[A-Z][A-Z0-9_]{0,99}$'
    ),
  constraint identity_audit_events_request_id_chk
    check (request_id is null or length(request_id) <= 200),
  constraint identity_audit_events_ip_hash_length_chk
    check (ip_hash is null or octet_length(ip_hash) = 32),
  constraint identity_audit_events_user_agent_hash_length_chk
    check (user_agent_hash is null or octet_length(user_agent_hash) = 32),
  constraint identity_audit_events_metadata_object_chk
    check (jsonb_typeof(metadata) = 'object')
);

create index identity_audit_events_occurred_at_idx
  on identity.audit_events (occurred_at desc);

create index identity_audit_events_actor_idx
  on identity.audit_events (actor_user_id, occurred_at desc)
  where actor_user_id is not null;

create index identity_audit_events_target_idx
  on identity.audit_events (target_user_id, occurred_at desc)
  where target_user_id is not null;

create index identity_audit_events_action_idx
  on identity.audit_events (action, occurred_at desc);

revoke update, delete, truncate on identity.audit_events from public;

