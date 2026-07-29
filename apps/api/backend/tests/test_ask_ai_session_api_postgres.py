from __future__ import annotations

from collections.abc import Iterator
from contextlib import contextmanager
from datetime import UTC, datetime, timedelta
from pathlib import Path
from uuid import UUID, uuid4

import pytest
from sqlalchemy import text
from sqlalchemy.engine import Engine
from sqlalchemy.orm import Session

from backend.ask.persistence import AskPersistenceService
from backend.core.migrations import apply_pending_migrations
from backend.tests.ask_ai_postgres import POSTGRES_MARK, insert_auth_user

MIGRATIONS_DIR = Path(__file__).parents[1] / "migrations"


@contextmanager
def _session_scope(engine: Engine) -> Iterator[Session]:
    database_session = Session(bind=engine)
    try:
        yield database_session
        database_session.commit()
    except Exception:
        database_session.rollback()
        raise
    finally:
        database_session.close()


@pytest.fixture
def migrated_engine(postgres_engine: Engine) -> Engine:
    apply_pending_migrations(postgres_engine, MIGRATIONS_DIR, through="0025")
    return postgres_engine


def _service(engine: Engine) -> AskPersistenceService:
    return AskPersistenceService(lambda: _session_scope(engine))


def _set_session_state(
    engine: Engine,
    *,
    session_id: UUID,
    updated_at: datetime,
    archived: bool = False,
    deleted: bool = False,
) -> None:
    with engine.begin() as connection:
        connection.execute(
            text(
                """
                update public.chat_sessions
                set
                  updated_at = :updated_at,
                  archived_at = case when :archived then :updated_at else null end,
                  deleted_at = case when :deleted then :updated_at else null end
                where id = :session_id
                """
            ),
            {
                "session_id": session_id,
                "updated_at": updated_at,
                "archived": archived,
                "deleted": deleted,
            },
        )


@POSTGRES_MARK
def test_owned_detail_and_active_list_do_not_leak_other_or_deleted_sessions(
    migrated_engine: Engine,
) -> None:
    owner_id = uuid4()
    other_id = uuid4()
    with migrated_engine.begin() as connection:
        insert_auth_user(connection, owner_id)
        insert_auth_user(connection, other_id)

    service = _service(migrated_engine)
    active = service.create_session(user_id=owner_id, title="Active")
    archived = service.create_session(user_id=owner_id, title="Archived")
    deleted = service.create_session(user_id=owner_id, title="Deleted")
    service.create_session(user_id=other_id, title="Other owner")
    now = datetime(2026, 7, 27, 7, tzinfo=UTC)
    _set_session_state(
        migrated_engine,
        session_id=active.id,
        updated_at=now,
    )
    _set_session_state(
        migrated_engine,
        session_id=archived.id,
        updated_at=now - timedelta(minutes=1),
        archived=True,
    )
    _set_session_state(
        migrated_engine,
        session_id=deleted.id,
        updated_at=now - timedelta(minutes=2),
        deleted=True,
    )

    page = service.list_sessions(user_id=owner_id, limit=20)

    assert [item.id for item in page.items] == [active.id]
    assert page.has_more is False
    assert service.get_session(session_id=active.id, user_id=owner_id) == page.items[0]
    assert service.get_session(session_id=archived.id, user_id=owner_id) is not None
    assert service.get_session(session_id=deleted.id, user_id=owner_id) is None
    assert service.get_session(session_id=active.id, user_id=other_id) is None


@POSTGRES_MARK
def test_session_keyset_cursor_is_stable_when_a_newer_session_is_inserted(
    migrated_engine: Engine,
) -> None:
    owner_id = uuid4()
    with migrated_engine.begin() as connection:
        insert_auth_user(connection, owner_id)

    service = _service(migrated_engine)
    base = datetime(2026, 7, 27, 8, tzinfo=UTC)
    sessions = [
        service.create_session(
            user_id=owner_id,
            session_id=UUID(f"00000000-0000-4000-8000-{index:012d}"),
            title=f"Session {index}",
        )
        for index in range(1, 5)
    ]
    for index, session in enumerate(sessions, start=1):
        _set_session_state(
            migrated_engine,
            session_id=session.id,
            updated_at=base + timedelta(minutes=index),
        )

    first_page = service.list_sessions(user_id=owner_id, limit=2)
    assert [item.title for item in first_page.items] == ["Session 4", "Session 3"]
    assert first_page.has_more is True

    concurrent = service.create_session(user_id=owner_id, title="Concurrent newer")
    _set_session_state(
        migrated_engine,
        session_id=concurrent.id,
        updated_at=base + timedelta(minutes=5),
    )
    cursor_session = first_page.items[-1]
    second_page = service.list_sessions(
        user_id=owner_id,
        limit=2,
        cursor_updated_at=cursor_session.updated_at,
        cursor_id=cursor_session.id,
    )

    assert [item.title for item in second_page.items] == ["Session 2", "Session 1"]
    assert second_page.has_more is False
    assert {item.id for item in first_page.items}.isdisjoint(
        item.id for item in second_page.items
    )
    assert concurrent.id not in {item.id for item in second_page.items}
