from __future__ import annotations

from collections.abc import Iterator
from contextlib import contextmanager
from pathlib import Path
from uuid import UUID, uuid4

import pytest
from sqlalchemy import text
from sqlalchemy.engine import Connection, Engine
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from backend.ask.persistence import AskPersistenceService
from backend.core.migrations import apply_pending_migrations, discover_migrations
from backend.tests.ask_ai_postgres import POSTGRES_MARK, insert_auth_user

MIGRATIONS_DIR = Path(__file__).parents[1] / "migrations"
LINEAGE_MIGRATION = MIGRATIONS_DIR / "0027_ask_ai_feedback_version_lineage.sql"
MIGRATION_README = MIGRATIONS_DIR / "README.md"


def _normalized(path: Path) -> str:
    return " ".join(path.read_text(encoding="utf-8").lower().split())


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


def _seed_question(
    connection: Connection,
    *,
    user_id: UUID,
    session_id: UUID | None = None,
) -> tuple[UUID, int, UUID]:
    resolved_session_id = session_id or uuid4()
    if session_id is None:
        connection.execute(
            text(
                """
                insert into public.chat_sessions (id, user_id, title)
                values (:session_id, :user_id, 'Version workspace')
                """
            ),
            {"session_id": resolved_session_id, "user_id": user_id},
        )
    public_id = uuid4()
    message_id = connection.execute(
        text(
            """
            insert into public.chat_messages (
              public_id,
              session_id,
              user_id,
              role,
              content,
              status
            )
            values (
              :public_id,
              :session_id,
              :user_id,
              'user',
              'What changed?',
              'completed'
            )
            returning id
            """
        ),
        {
            "public_id": public_id,
            "session_id": resolved_session_id,
            "user_id": user_id,
        },
    ).scalar_one()
    return resolved_session_id, message_id, public_id


def _insert_version(
    connection: Connection,
    *,
    session_id: UUID,
    user_id: UUID,
    user_message_id: int,
    response_version: int,
    parent_message_id: int | None,
    content: str,
) -> tuple[int, UUID]:
    assistant_message_id = connection.execute(
        text(
            """
            insert into public.chat_messages (
              public_id,
              session_id,
              user_id,
              role,
              content,
              status,
              response_version,
              reply_to_message_id,
              parent_message_id
            )
            values (
              :public_id,
              :session_id,
              :user_id,
              'assistant',
              :content,
              'completed',
              :response_version,
              :user_message_id,
              :parent_message_id
            )
            returning id
            """
        ),
        {
            "public_id": uuid4(),
            "session_id": session_id,
            "user_id": user_id,
            "content": content,
            "response_version": response_version,
            "user_message_id": user_message_id,
            "parent_message_id": parent_message_id,
        },
    ).scalar_one()
    run_id = connection.execute(
        text(
            """
            insert into public.ask_runs (
              session_id,
              user_id,
              user_message_id,
              assistant_message_id,
              response_version,
              status
            )
            values (
              :session_id,
              :user_id,
              :user_message_id,
              :assistant_message_id,
              :response_version,
              'completed'
            )
            returning id
            """
        ),
        {
            "session_id": session_id,
            "user_id": user_id,
            "user_message_id": user_message_id,
            "assistant_message_id": assistant_message_id,
            "response_version": response_version,
        },
    ).scalar_one()
    connection.execute(
        text(
            """
            insert into public.ask_sections (
              run_id,
              session_id,
              user_id,
              response_version,
              ordinal,
              section_type,
              status,
              knowledge_mode,
              provenance_label,
              plain_text
            )
            values (
              :run_id,
              :session_id,
              :user_id,
              :response_version,
              0,
              'answer',
              'completed',
              'official',
              'Internal Regulatory Corpus',
              :content
            )
            """
        ),
        {
            "run_id": run_id,
            "session_id": session_id,
            "user_id": user_id,
            "response_version": response_version,
            "content": content,
        },
    )
    return assistant_message_id, run_id


def test_0027_is_additive_version_owned_and_least_privilege() -> None:
    migration = next(
        item for item in discover_migrations(MIGRATIONS_DIR) if item.version == "0027"
    )
    sql = _normalized(LINEAGE_MIGRATION)
    readme = _normalized(MIGRATION_README)

    assert migration.filename == "0027_ask_ai_feedback_version_lineage.sql"
    assert "create table public.ask_feedback" in sql
    assert "add column response_version integer" in sql
    assert "add column reply_to_message_id bigint" in sql
    assert "add column parent_message_id bigint" in sql
    assert "ask_sections_run_owner_version_fkey" in sql
    assert "alter table public.ask_feedback enable row level security" in sql
    assert "grant select on table public.ask_feedback to authenticated" in sql
    assert "feedback and response-version lineage" in readme
    assert "drop table" not in sql
    assert "delete from public.chat_messages" not in sql


@POSTGRES_MARK
def test_0027_applies_from_empty_schema_with_rls_and_ledger(
    postgres_engine: Engine,
) -> None:
    applied = apply_pending_migrations(
        postgres_engine,
        MIGRATIONS_DIR,
        through="0027",
    )

    assert len(applied) == 27
    assert applied[-1].version == "0027"
    with postgres_engine.connect() as connection:
        assert connection.execute(
            text("select relrowsecurity from pg_class where oid = 'public.ask_feedback'::regclass")
        ).scalar_one() is True
        assert connection.execute(
            text(
                """
                select has_table_privilege(
                  'authenticated',
                  'public.ask_feedback',
                  'select'
                )
                """
            )
        ).scalar_one() is True
        assert connection.execute(
            text(
                """
                select has_table_privilege(
                  'authenticated',
                  'public.ask_feedback',
                  'insert,update,delete'
                )
                """
            )
        ).scalar_one() is False


@POSTGRES_MARK
def test_0027_upgrade_preserves_existing_turn_and_backfills_initial_lineage(
    postgres_engine: Engine,
) -> None:
    apply_pending_migrations(postgres_engine, MIGRATIONS_DIR, through="0026")
    owner_id = uuid4()
    with postgres_engine.begin() as connection:
        insert_auth_user(connection, owner_id)
        session_id = uuid4()
        connection.execute(
            text(
                """
                insert into public.chat_sessions (id, user_id, title)
                values (:session_id, :user_id, 'Existing workspace')
                """
            ),
            {"session_id": session_id, "user_id": owner_id},
        )
        user_message_id = connection.execute(
            text(
                """
                insert into public.chat_messages (
                  public_id, session_id, user_id, role, content
                )
                values (:public_id, :session_id, :user_id, 'user', 'Existing question')
                returning id
                """
            ),
            {
                "public_id": uuid4(),
                "session_id": session_id,
                "user_id": owner_id,
            },
        ).scalar_one()
        assistant_message_id = connection.execute(
            text(
                """
                insert into public.chat_messages (
                  public_id, session_id, user_id, role, content
                )
                values (:public_id, :session_id, :user_id, 'assistant', 'Existing answer')
                returning id
                """
            ),
            {
                "public_id": uuid4(),
                "session_id": session_id,
                "user_id": owner_id,
            },
        ).scalar_one()
        run_id = connection.execute(
            text(
                """
                insert into public.ask_runs (
                  session_id, user_id, user_message_id, assistant_message_id, status
                )
                values (
                  :session_id, :user_id, :user_message_id, :assistant_message_id, 'completed'
                )
                returning id
                """
            ),
            {
                "session_id": session_id,
                "user_id": owner_id,
                "user_message_id": user_message_id,
                "assistant_message_id": assistant_message_id,
            },
        ).scalar_one()
        connection.execute(
            text(
                """
                insert into public.ask_sections (
                  run_id, session_id, user_id, ordinal, section_type, status,
                  knowledge_mode, provenance_label, plain_text
                )
                values (
                  :run_id, :session_id, :user_id, 0, 'answer', 'completed',
                  'official', 'Internal Regulatory Corpus', 'Existing answer'
                )
                """
            ),
            {"run_id": run_id, "session_id": session_id, "user_id": owner_id},
        )
        before = connection.execute(
            text(
                """
                select id, public_id, session_id, user_id, role, content, created_at
                from public.chat_messages
                where id in (:user_message_id, :assistant_message_id)
                order by id
                """
            ),
            {
                "user_message_id": user_message_id,
                "assistant_message_id": assistant_message_id,
            },
        ).all()

    assert [
        migration.version
        for migration in apply_pending_migrations(
            postgres_engine,
            MIGRATIONS_DIR,
            through="0027",
        )
    ] == ["0027"]
    with postgres_engine.connect() as connection:
        after = connection.execute(
            text(
                """
                select id, public_id, session_id, user_id, role, content, created_at
                from public.chat_messages
                where id in (:user_message_id, :assistant_message_id)
                order by id
                """
            ),
            {
                "user_message_id": user_message_id,
                "assistant_message_id": assistant_message_id,
            },
        ).all()
        lineage = connection.execute(
            text(
                """
                select
                  message.status,
                  message.response_version,
                  message.reply_to_message_id,
                  message.parent_message_id,
                  run.response_version
                from public.ask_runs run
                join public.chat_messages message
                  on message.id = run.assistant_message_id
                where run.id = :run_id
                """
            ),
            {"run_id": run_id},
        ).one()

    assert after == before
    assert lineage == ("completed", 1, user_message_id, None, 1)


@POSTGRES_MARK
def test_lineage_constraints_reject_cross_question_gaps_and_duplicate_versions(
    postgres_engine: Engine,
) -> None:
    apply_pending_migrations(postgres_engine, MIGRATIONS_DIR, through="0027")
    owner_id = uuid4()
    other_id = uuid4()
    with postgres_engine.begin() as connection:
        insert_auth_user(connection, owner_id)
        insert_auth_user(connection, other_id)
        session_id, first_question_id, _ = _seed_question(
            connection,
            user_id=owner_id,
        )
        _, second_question_id, _ = _seed_question(
            connection,
            user_id=owner_id,
            session_id=session_id,
        )
        first_v1, _ = _insert_version(
            connection,
            session_id=session_id,
            user_id=owner_id,
            user_message_id=first_question_id,
            response_version=1,
            parent_message_id=None,
            content="First v1",
        )
        second_v1, _ = _insert_version(
            connection,
            session_id=session_id,
            user_id=owner_id,
            user_message_id=second_question_id,
            response_version=1,
            parent_message_id=None,
            content="Second v1",
        )
        other_session_id, other_session_question_id, _ = _seed_question(
            connection,
            user_id=owner_id,
        )
        other_session_v1, _ = _insert_version(
            connection,
            session_id=other_session_id,
            user_id=owner_id,
            user_message_id=other_session_question_id,
            response_version=1,
            parent_message_id=None,
            content="Other session v1",
        )
        other_owner_session_id, other_owner_question_id, _ = _seed_question(
            connection,
            user_id=other_id,
        )
        other_owner_v1, _ = _insert_version(
            connection,
            session_id=other_owner_session_id,
            user_id=other_id,
            user_message_id=other_owner_question_id,
            response_version=1,
            parent_message_id=None,
            content="Other owner v1",
        )

    with pytest.raises(IntegrityError), postgres_engine.begin() as connection:
        _insert_version(
            connection,
            session_id=session_id,
            user_id=owner_id,
            user_message_id=first_question_id,
            response_version=2,
            parent_message_id=second_v1,
            content="Cross-question parent",
        )

    with pytest.raises(IntegrityError), postgres_engine.begin() as connection:
        _insert_version(
            connection,
            session_id=session_id,
            user_id=owner_id,
            user_message_id=first_question_id,
            response_version=2,
            parent_message_id=other_session_v1,
            content="Cross-session parent",
        )

    with pytest.raises(IntegrityError), postgres_engine.begin() as connection:
        _insert_version(
            connection,
            session_id=session_id,
            user_id=owner_id,
            user_message_id=first_question_id,
            response_version=2,
            parent_message_id=other_owner_v1,
            content="Cross-owner parent",
        )

    with pytest.raises(IntegrityError), postgres_engine.begin() as connection:
        _insert_version(
            connection,
            session_id=session_id,
            user_id=owner_id,
            user_message_id=first_question_id,
            response_version=3,
            parent_message_id=first_v1,
            content="Skipped v2",
        )

    with postgres_engine.begin() as connection:
        first_v2, first_run_v2 = _insert_version(
            connection,
            session_id=session_id,
            user_id=owner_id,
            user_message_id=first_question_id,
            response_version=2,
            parent_message_id=first_v1,
            content="First v2",
        )

    with pytest.raises(IntegrityError), postgres_engine.begin() as connection:
        _insert_version(
            connection,
            session_id=session_id,
            user_id=owner_id,
            user_message_id=first_question_id,
            response_version=2,
            parent_message_id=first_v1,
            content="Duplicate v2",
        )

    with pytest.raises(IntegrityError), postgres_engine.begin() as connection:
        connection.execute(
            text(
                """
                insert into public.ask_sections (
                  run_id, session_id, user_id, response_version, ordinal,
                  section_type, status, knowledge_mode, provenance_label
                )
                values (
                  :run_id, :session_id, :user_id, 1, 9,
                  'answer', 'completed', 'official',
                  'Internal Regulatory Corpus'
                )
                """
            ),
            {
                "run_id": first_run_v2,
                "session_id": session_id,
                "user_id": owner_id,
            },
        )

    with pytest.raises(IntegrityError), postgres_engine.begin() as connection:
        connection.execute(
            text(
                """
                update public.chat_messages
                set parent_message_id = :second_v1
                where id = :first_v2
                """
            ),
            {"second_v1": second_v1, "first_v2": first_v2},
        )


@POSTGRES_MARK
def test_feedback_upsert_and_lineage_restore_are_exact_and_owner_scoped(
    postgres_engine: Engine,
) -> None:
    apply_pending_migrations(postgres_engine, MIGRATIONS_DIR, through="0027")
    owner_id = uuid4()
    other_id = uuid4()
    with postgres_engine.begin() as connection:
        insert_auth_user(connection, owner_id)
        insert_auth_user(connection, other_id)
        session_id, user_message_id, user_message_public_id = _seed_question(
            connection,
            user_id=owner_id,
        )
        assistant_v1, _ = _insert_version(
            connection,
            session_id=session_id,
            user_id=owner_id,
            user_message_id=user_message_id,
            response_version=1,
            parent_message_id=None,
            content="Original answer",
        )
        _, run_v2 = _insert_version(
            connection,
            session_id=session_id,
            user_id=owner_id,
            user_message_id=user_message_id,
            response_version=2,
            parent_message_id=assistant_v1,
            content="Regenerated answer",
        )

    service = _service(postgres_engine)
    created = service.record_feedback(
        run_id=run_v2,
        session_id=session_id,
        user_id=owner_id,
        response_version=2,
        value="helpful",
        comment="Useful",
    )
    assert created is not None
    updated = service.record_feedback(
        run_id=run_v2,
        session_id=session_id,
        user_id=owner_id,
        response_version=2,
        value="not_helpful",
        reason_code="missing_detail",
        comment="Needs one citation",
    )
    assert updated is not None
    assert updated.id == created.id
    assert updated.created_at == created.created_at
    assert updated.updated_at >= created.updated_at
    assert service.record_feedback(
        run_id=run_v2,
        session_id=session_id,
        user_id=other_id,
        response_version=2,
        value="helpful",
    ) is None
    assert service.record_feedback(
        run_id=run_v2,
        session_id=session_id,
        user_id=owner_id,
        response_version=1,
        value="helpful",
    ) is None

    lineage = service.get_response_lineage(
        session_id=session_id,
        user_id=owner_id,
        user_message_public_id=user_message_public_id,
    )
    assert lineage is not None
    assert [item.response_version for item in lineage.versions] == [1, 2]
    assert [item.assistant_message.content for item in lineage.versions] == [
        "Original answer",
        "Regenerated answer",
    ]
    assert lineage.versions[1].assistant_message.parent_message_id == assistant_v1
    assert lineage.versions[0].feedback is None
    assert lineage.versions[1].feedback == updated
    assert service.get_response_lineage(
        session_id=session_id,
        user_id=other_id,
        user_message_public_id=user_message_public_id,
    ) is None

    turn_page = service.list_turns(
        session_id=session_id,
        user_id=owner_id,
        limit=10,
    )
    assert turn_page is not None
    assert len(turn_page.items) == 1
    assert turn_page.items[0].run is not None
    assert turn_page.items[0].run.response_version == 2
    assert turn_page.items[0].assistant_message is not None
    assert turn_page.items[0].assistant_message.content == "Regenerated answer"


@POSTGRES_MARK
def test_feedback_rls_hides_non_owner_rows(postgres_engine: Engine) -> None:
    apply_pending_migrations(postgres_engine, MIGRATIONS_DIR, through="0027")
    owner_id = uuid4()
    other_id = uuid4()
    with postgres_engine.begin() as connection:
        insert_auth_user(connection, owner_id)
        insert_auth_user(connection, other_id)
        session_id, user_message_id, _ = _seed_question(
            connection,
            user_id=owner_id,
        )
        _, run_id = _insert_version(
            connection,
            session_id=session_id,
            user_id=owner_id,
            user_message_id=user_message_id,
            response_version=1,
            parent_message_id=None,
            content="Answer",
        )
        connection.execute(
            text(
                """
                insert into public.ask_feedback (
                  run_id, session_id, user_id, response_version, value
                )
                values (:run_id, :session_id, :user_id, 1, 'helpful')
                """
            ),
            {"run_id": run_id, "session_id": session_id, "user_id": owner_id},
        )

    for principal_id, expected_count in ((owner_id, 1), (other_id, 0)):
        with postgres_engine.begin() as connection:
            connection.execute(text("set local role authenticated"))
            connection.execute(
                text("select set_config('request.jwt.claim.sub', :user_id, true)"),
                {"user_id": str(principal_id)},
            )
            assert connection.execute(
                text("select count(*) from public.ask_feedback")
            ).scalar_one() == expected_count
