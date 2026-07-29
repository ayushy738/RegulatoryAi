from __future__ import annotations

from collections.abc import Iterator
from contextlib import contextmanager
from datetime import UTC, datetime, timedelta
from pathlib import Path
from uuid import UUID, uuid4

import pytest
from sqlalchemy import text
from sqlalchemy.engine import Engine
from sqlalchemy.exc import ProgrammingError
from sqlalchemy.orm import Session

from backend.ask.persistence import AskPersistenceService
from backend.core.migrations import apply_pending_migrations
from backend.tests.ask_ai_postgres import POSTGRES_MARK, insert_auth_user

pytestmark = POSTGRES_MARK

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


def _service(engine: Engine) -> AskPersistenceService:
    return AskPersistenceService(lambda: _session_scope(engine))


@pytest.fixture
def migrated_engine(postgres_engine: Engine) -> Engine:
    apply_pending_migrations(postgres_engine, MIGRATIONS_DIR, through="0030")
    return postgres_engine


def _seed_search_session(
    engine: Engine,
    *,
    user_id: UUID,
    title: str,
    message: str,
    source_title: str,
    entity: str,
    mode: str,
    updated_at: datetime,
    pinned: bool = False,
    archived: bool = False,
) -> UUID:
    session_id = uuid4()
    with engine.begin() as connection:
        connection.execute(
            text(
                """
                insert into public.chat_sessions (
                  id, user_id, title, primary_entity, is_pinned, archived_at,
                  updated_at
                )
                values (
                  :session_id, :user_id, :title, :entity, :pinned,
                  case when :archived then :updated_at else null end,
                  :updated_at
                )
                """
            ),
            {
                "session_id": session_id,
                "user_id": user_id,
                "title": title,
                "entity": entity,
                "pinned": pinned,
                "archived": archived,
                "updated_at": updated_at,
            },
        )
        user_message_id = connection.execute(
            text(
                """
                insert into public.chat_messages (
                  public_id, session_id, user_id, role, content, status
                )
                values (
                  :public_id, :session_id, :user_id, 'user', :message,
                  'completed'
                )
                returning id
                """
            ),
            {
                "public_id": uuid4(),
                "session_id": session_id,
                "user_id": user_id,
                "message": message,
            },
        ).scalar_one()
        assistant_message_id = connection.execute(
            text(
                """
                insert into public.chat_messages (
                  public_id, session_id, user_id, role, content, status,
                  response_version, reply_to_message_id
                )
                values (
                  :public_id, :session_id, :user_id, 'assistant', 'Answer',
                  'completed', 1, :user_message_id
                )
                returning id
                """
            ),
            {
                "public_id": uuid4(),
                "session_id": session_id,
                "user_id": user_id,
                "user_message_id": user_message_id,
            },
        ).scalar_one()
        run_id = connection.execute(
            text(
                """
                insert into public.ask_runs (
                  session_id, user_id, user_message_id, assistant_message_id,
                  response_version, status
                )
                values (
                  :session_id, :user_id, :user_message_id,
                  :assistant_message_id, 1, 'completed'
                )
                returning id
                """
            ),
            {
                "session_id": session_id,
                "user_id": user_id,
                "user_message_id": user_message_id,
                "assistant_message_id": assistant_message_id,
            },
        ).scalar_one()
        provenance = {
            "official": "Internal Regulatory Corpus",
            "general": "General AI Knowledge",
            "live": "Live Web Sources",
        }[mode]
        connection.execute(
            text(
                """
                insert into public.ask_sections (
                  run_id, session_id, user_id, response_version, ordinal,
                  section_type, status, knowledge_mode, provenance_label,
                  model, policy_version, required_disclosure
                )
                values (
                  :run_id, :session_id, :user_id, 1, 0, 'answer', 'completed',
                  :mode, :provenance, :model, :policy_version, :disclosure
                )
                """
            ),
            {
                "run_id": run_id,
                "session_id": session_id,
                "user_id": user_id,
                "mode": mode,
                "provenance": provenance,
                "model": "general-model" if mode == "general" else None,
                "policy_version": "policy-v1" if mode == "general" else None,
                "disclosure": (
                    "General AI knowledge only." if mode == "general" else None
                ),
            },
        )
        connection.execute(
            text(
                """
                insert into public.ask_sources (
                  run_id, session_id, user_id, ordinal, source_key,
                  source_class, source_type, title_snapshot, url_snapshot,
                  publisher_snapshot, published_at, retrieved_at,
                  evidence_snapshot
                )
                values (
                  :run_id, :session_id, :user_id, 0, :source_key, 'live',
                  'news', :source_title, :url, 'Regulatory Bulletin',
                  :updated_at, :updated_at, 'Retained source evidence'
                )
                """
            ),
            {
                "run_id": run_id,
                "session_id": session_id,
                "user_id": user_id,
                "source_key": f"live:{uuid4()}",
                "source_title": source_title,
                "url": f"https://example.test/{uuid4()}",
                "updated_at": updated_at,
            },
        )
    return session_id


def test_search_ranks_title_message_and_document_source_without_owner_leakage(
    migrated_engine: Engine,
) -> None:
    owner_id = uuid4()
    other_id = uuid4()
    with migrated_engine.begin() as connection:
        insert_auth_user(connection, owner_id)
        insert_auth_user(connection, other_id)
    base = datetime(2026, 7, 27, 8, tzinfo=UTC)
    title_id = _seed_search_session(
        migrated_engine,
        user_id=owner_id,
        title="Needle balancing reform",
        message="unrelated question",
        source_title="unrelated source",
        entity="CERC",
        mode="official",
        updated_at=base,
    )
    message_id = _seed_search_session(
        migrated_engine,
        user_id=owner_id,
        title="Message result",
        message="Explain the needle deviation",
        source_title="unrelated instrument",
        entity="DERC",
        mode="general",
        updated_at=base + timedelta(minutes=2),
    )
    source_id = _seed_search_session(
        migrated_engine,
        user_id=owner_id,
        title="Source result",
        message="unrelated question",
        source_title="Needle Grid Code Amendment",
        entity="SERC",
        mode="live",
        updated_at=base + timedelta(minutes=4),
    )
    _seed_search_session(
        migrated_engine,
        user_id=other_id,
        title="Needle other owner",
        message="needle",
        source_title="needle",
        entity="CERC",
        mode="official",
        updated_at=base + timedelta(minutes=6),
    )

    page = _service(migrated_engine).list_sessions(
        user_id=owner_id,
        limit=10,
        query="needle",
    )

    assert [item.id for item in page.items] == [title_id, message_id, source_id]
    assert page.relevances == (500, 400, 300)
    assert page.has_more is False


def test_search_filters_mode_entity_lifecycle_and_pin(
    migrated_engine: Engine,
) -> None:
    owner_id = uuid4()
    with migrated_engine.begin() as connection:
        insert_auth_user(connection, owner_id)
    base = datetime(2026, 7, 27, 9, tzinfo=UTC)
    official = _seed_search_session(
        migrated_engine,
        user_id=owner_id,
        title="Official active",
        message="filterable",
        source_title="Official source",
        entity="CERC",
        mode="official",
        updated_at=base,
        pinned=True,
    )
    archived = _seed_search_session(
        migrated_engine,
        user_id=owner_id,
        title="General archived",
        message="filterable",
        source_title="General source",
        entity="DERC",
        mode="general",
        updated_at=base + timedelta(minutes=1),
        archived=True,
    )

    service = _service(migrated_engine)
    official_page = service.list_sessions(
        user_id=owner_id,
        limit=10,
        query="filterable",
        knowledge_mode="official",
        entity="cerc",
        pinned=True,
    )
    archived_page = service.list_sessions(
        user_id=owner_id,
        limit=10,
        knowledge_mode="general",
        entity="derc",
        archived=True,
    )

    assert [item.id for item in official_page.items] == [official]
    assert [item.id for item in archived_page.items] == [archived]
    assert service.list_sessions(
        user_id=owner_id,
        limit=10,
        archived=False,
        pinned=False,
    ).items == ()


def test_searchable_rows_remain_isolated_by_authenticated_rls(
    migrated_engine: Engine,
) -> None:
    owner_id = uuid4()
    other_id = uuid4()
    with migrated_engine.begin() as connection:
        insert_auth_user(connection, owner_id)
        insert_auth_user(connection, other_id)
    now = datetime(2026, 7, 27, 9, 30, tzinfo=UTC)
    for user_id in (owner_id, other_id):
        _seed_search_session(
            migrated_engine,
            user_id=user_id,
            title="Needle title",
            message="Needle message",
            source_title="Needle source",
            entity="CERC",
            mode="official",
            updated_at=now,
        )

    with migrated_engine.begin() as connection:
        connection.execute(text("set local role authenticated"))
        connection.execute(
            text("select set_config('request.jwt.claim.sub', :user_id, true)"),
            {"user_id": str(owner_id)},
        )
        session_owners = set(
            connection.execute(
                text(
                    """
                    select user_id
                    from public.chat_sessions
                    where (
                      setweight(
                        to_tsvector('simple', coalesce(title, '')),
                        'A'
                      )
                      || setweight(
                        to_tsvector('simple', coalesce(primary_entity, '')),
                        'B'
                      )
                      || setweight(
                        to_tsvector('simple', coalesce(primary_topic, '')),
                        'C'
                      )
                    ) @@ plainto_tsquery('simple', 'needle')
                    """
                )
            ).scalars()
        )
        source_owners = set(
            connection.execute(
                text(
                    """
                    select user_id
                    from public.ask_sources
                    where (
                      setweight(
                        to_tsvector('simple', coalesce(title_snapshot, '')),
                        'A'
                      )
                      || setweight(
                        to_tsvector('simple', coalesce(issuer_snapshot, '')),
                        'B'
                      )
                      || setweight(
                        to_tsvector('simple', coalesce(publisher_snapshot, '')),
                        'B'
                      )
                      || setweight(
                        to_tsvector('simple', coalesce(evidence_snapshot, '')),
                        'C'
                      )
                      || setweight(
                        to_tsvector('simple', coalesce(locator_snapshot, '')),
                        'D'
                      )
                    ) @@ plainto_tsquery('simple', 'needle')
                    """
                )
            ).scalars()
        )

    with pytest.raises(ProgrammingError), migrated_engine.begin() as connection:
        connection.execute(text("set local role authenticated"))
        connection.execute(
            text("select set_config('request.jwt.claim.sub', :user_id, true)"),
            {"user_id": str(owner_id)},
        )
        connection.execute(
            text(
                """
                select user_id
                from public.chat_messages
                where session_id is not null
                  and to_tsvector(
                    'simple',
                    coalesce(content, '')
                  ) @@ plainto_tsquery('simple', 'needle')
                """
            )
        ).all()

    assert session_owners == {owner_id}
    assert source_owners == {owner_id}


def test_rank_cursor_is_stable_when_a_newer_match_is_inserted(
    migrated_engine: Engine,
) -> None:
    owner_id = uuid4()
    with migrated_engine.begin() as connection:
        insert_auth_user(connection, owner_id)
    base = datetime(2026, 7, 27, 10, tzinfo=UTC)
    session_ids = [
        _seed_search_session(
            migrated_engine,
            user_id=owner_id,
            title=f"Needle session {index}",
            message="unrelated",
            source_title="unrelated",
            entity="CERC",
            mode="official",
            updated_at=base + timedelta(minutes=index),
        )
        for index in range(1, 5)
    ]
    service = _service(migrated_engine)

    first = service.list_sessions(user_id=owner_id, limit=2, query="needle")
    assert [item.id for item in first.items] == [session_ids[3], session_ids[2]]

    concurrent = _seed_search_session(
        migrated_engine,
        user_id=owner_id,
        title="Needle concurrent",
        message="unrelated",
        source_title="unrelated",
        entity="CERC",
        mode="official",
        updated_at=base + timedelta(minutes=5),
    )
    anchor = first.items[-1]
    second = service.list_sessions(
        user_id=owner_id,
        limit=2,
        query="needle",
        cursor_relevance=first.relevances[-1],
        cursor_updated_at=anchor.updated_at,
        cursor_id=anchor.id,
    )

    assert [item.id for item in second.items] == [session_ids[1], session_ids[0]]
    assert concurrent not in {item.id for item in second.items}
    assert {item.id for item in first.items}.isdisjoint(
        item.id for item in second.items
    )
