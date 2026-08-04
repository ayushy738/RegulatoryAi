from collections.abc import Iterator
from contextlib import contextmanager
from functools import lru_cache
from socket import IPPROTO_TCP, getaddrinfo
from urllib.parse import parse_qs, urlparse

from sqlalchemy import create_engine, text
from sqlalchemy.engine import Engine
from sqlalchemy.orm import Session, sessionmaker

from backend.core.config import settings
from backend.core.logging import log_event

CONNECT_ARGS = {"connect_timeout": 5}
POOL_SIZE = 5
MAX_OVERFLOW = 5
POOL_TIMEOUT = 5
POOL_PRE_PING = True


@lru_cache
def get_engine() -> Engine:
    settings.require_database()
    database_url = settings.database_url
    if database_url.startswith("postgresql://"):
        database_url = database_url.replace("postgresql://", "postgresql+psycopg://", 1)
    if database_url.startswith("postgres://"):
        database_url = database_url.replace("postgres://", "postgresql+psycopg://", 1)
    _log_database_startup_diagnostics(database_url)
    return create_engine(
        database_url,
        connect_args=CONNECT_ARGS,
        pool_size=POOL_SIZE,
        max_overflow=MAX_OVERFLOW,
        pool_timeout=POOL_TIMEOUT,
        pool_pre_ping=POOL_PRE_PING,
        future=True,
    )


@lru_cache
def get_session_factory() -> sessionmaker[Session]:
    return sessionmaker(bind=get_engine(), autoflush=False, expire_on_commit=False, future=True)


@contextmanager
def session_scope() -> Iterator[Session]:
    session = get_session_factory()()
    try:
        yield session
        session.commit()
    except Exception:
        session.rollback()
        raise
    finally:
        session.close()


def database_healthcheck() -> bool:
    with get_engine().connect() as connection:
        connection.execute(text("select 1"))
    return True


def _log_database_startup_diagnostics(database_url: str) -> None:
    parsed = urlparse(database_url)
    query = parse_qs(parsed.query)
    host = parsed.hostname
    port = parsed.port or 5432
    resolved_addresses: list[str] = []
    resolution_error: str | None = None
    if host:
        try:
            resolved_addresses = sorted(
                {
                    item[4][0]
                    for item in getaddrinfo(host, port, proto=IPPROTO_TCP)
                    if item[4]
                }
            )
        except Exception as exc:
            resolution_error = f"{type(exc).__name__}: {exc}"
    log_event(
        "database_startup_diagnostics",
        database_scheme=parsed.scheme,
        database_host=host,
        database_port=port,
        database_name=(parsed.path or "").lstrip("/") or None,
        database_username_present=bool(parsed.username),
        database_password_present=bool(parsed.password),
        database_sslmode=(query.get("sslmode") or ["<not set>"])[0],
        database_url_connect_timeout=(
            query.get("connect_timeout") or ["<not set>"]
        )[0],
        database_resolved_addresses=resolved_addresses,
        database_resolution_error=resolution_error,
        sqlalchemy_connect_args=CONNECT_ARGS,
        sqlalchemy_pool_size=POOL_SIZE,
        sqlalchemy_max_overflow=MAX_OVERFLOW,
        sqlalchemy_pool_timeout=POOL_TIMEOUT,
        sqlalchemy_pool_pre_ping=POOL_PRE_PING,
    )
