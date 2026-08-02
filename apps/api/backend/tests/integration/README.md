# Dual-authentication integration suite

This suite exercises the FastAPI identity routes, SQLAlchemy repositories,
session cookies, JWT validation, refresh rotation, Supabase-to-identity
exchange, password lifecycle, and coexistence behavior as one HTTP-level test
surface.

The tests use the project's existing isolated identity database pattern:

- SQLite runs in memory with an attached `identity` schema.
- FastAPI routes use the real authentication services and repositories.
- Argon2 uses reduced test-only cost parameters.
- Supabase bearer validation is represented by a deterministic local verifier.
- No Supabase, internet, or other external network request is made.
- Each test receives a new database and application.
- No test uses sleeps or wall-clock polling.

## Run the integration module

From `apps/api`:

```bash
python -m pytest -q -p no:cacheprovider \
  backend/tests/integration/test_dual_authentication_integration.py
```

## Run the complete authentication suite

From `apps/api`:

```bash
python -m pytest -q -p no:cacheprovider \
  backend/tests/test_auth_security.py \
  backend/tests/test_identity_authentication_api.py \
  backend/tests/test_identity_authentication_service.py \
  backend/tests/integration/test_dual_authentication_integration.py
```

PowerShell single-line equivalent:

```powershell
python -m pytest -q -p no:cacheprovider backend/tests/test_auth_security.py backend/tests/test_identity_authentication_api.py backend/tests/test_identity_authentication_service.py backend/tests/integration/test_dual_authentication_integration.py
```

The optional pytest cache provider is disabled because it is not required by
the suite and can block process shutdown on restricted Windows workspaces.

The focused integration module covers:

- valid, invalid, and missing Supabase bearer tokens;
- verified password enrollment and duplicate rejection;
- successful and failed identity login, including locked accounts;
- `/identity/me` source attribution for both authentication systems;
- refresh rotation, replay detection, session revocation, and logout;
- password-change invalidation and concurrent-session revocation;
- Supabase session exchange into a usable first-party identity session;
- session listing and selective revocation;
- expired and tampered JWT rejection;
- authentication-source boundaries and cookie CSRF enforcement;
- continued Supabase and identity coexistence.
