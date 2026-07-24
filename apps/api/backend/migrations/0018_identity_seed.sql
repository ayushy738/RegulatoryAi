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

