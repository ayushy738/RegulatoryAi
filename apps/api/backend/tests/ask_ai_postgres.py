from __future__ import annotations

import os
from collections.abc import Iterator
from uuid import UUID

import pytest
from sqlalchemy import create_engine, text
from sqlalchemy.engine import Connection, Engine

TEST_DATABASE_URL = os.getenv("ASK_AI_TEST_DATABASE_URL")
POSTGRES_TESTS_ALLOWED = (
    os.getenv("ALLOW_ASK_AI_POSTGRES_TESTS") == "dedicated-test-database"
)

POSTGRES_MARK = pytest.mark.skipif(
    not TEST_DATABASE_URL or not POSTGRES_TESTS_ALLOWED,
    reason=(
        "Requires ASK_AI_TEST_DATABASE_URL and explicit confirmation that it "
        "targets a disposable dedicated test database"
    ),
)

AUTH_BOOTSTRAP_SQL = """
do $roles$
begin
  if not exists (select 1 from pg_roles where rolname = 'anon') then
    create role anon nologin;
  end if;
  if not exists (select 1 from pg_roles where rolname = 'authenticated') then
    create role authenticated nologin;
  end if;
  if not exists (select 1 from pg_roles where rolname = 'service_role') then
    create role service_role nologin bypassrls;
  end if;
end
$roles$;

create schema auth;

create function auth.uid()
returns uuid
language sql
stable
as $$
  select nullif(current_setting('request.jwt.claim.sub', true), '')::uuid
$$;

create table auth.users (
  id uuid primary key,
  email text,
  email_confirmed_at timestamptz,
  banned_until timestamptz,
  deleted_at timestamptz,
  raw_user_meta_data jsonb not null default '{}'::jsonb,
  created_at timestamptz not null default now(),
  updated_at timestamptz not null default now()
);

grant usage on schema auth to authenticated;
grant execute on function auth.uid() to authenticated;
"""


def _database_url() -> str:
    assert TEST_DATABASE_URL is not None
    if TEST_DATABASE_URL.startswith("postgresql://"):
        return TEST_DATABASE_URL.replace("postgresql://", "postgresql+psycopg://", 1)
    return TEST_DATABASE_URL


@pytest.fixture
def postgres_engine() -> Iterator[Engine]:
    if not TEST_DATABASE_URL or not POSTGRES_TESTS_ALLOWED:
        pytest.skip(
            "Requires a disposable dedicated PostgreSQL database for Ask AI tests"
        )

    engine = create_engine(_database_url())
    with engine.begin() as connection:
        connection.exec_driver_sql("drop schema if exists identity cascade")
        connection.exec_driver_sql("drop schema if exists auth cascade")
        connection.exec_driver_sql("drop schema public cascade")
        connection.exec_driver_sql("create schema public")
        connection.exec_driver_sql("grant all on schema public to public")
        connection.exec_driver_sql(AUTH_BOOTSTRAP_SQL)

    try:
        yield engine
    finally:
        engine.dispose()


def insert_auth_user(connection: Connection, user_id: UUID) -> None:
    connection.execute(
        text(
            """
            insert into auth.users (id, email, email_confirmed_at)
            values (:user_id, :email, now())
            """
        ),
        {"user_id": user_id, "email": f"{user_id}@example.invalid"},
    )
