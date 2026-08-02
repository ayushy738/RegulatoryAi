from __future__ import annotations

from pathlib import Path
from typing import Any
from uuid import UUID, uuid4

import pytest
from sqlalchemy import text
from sqlalchemy.engine import Connection, Engine
from sqlalchemy.exc import IntegrityError

from backend.core.migrations import apply_pending_migrations, discover_migrations
from backend.tests.ask_ai_postgres import (
    POSTGRES_MARK,
    insert_auth_user,
)

MIGRATIONS_DIR = Path(__file__).parents[1] / "migrations"
ARTIFACT_MIGRATION = MIGRATIONS_DIR / "0024_ask_ai_artifacts.sql"
MIGRATION_README = MIGRATIONS_DIR / "README.md"

ARTIFACT_TABLES = (
    "ask_runs",
    "ask_sections",
    "ask_sources",
    "ask_claims",
    "ask_citations",
    "ask_followups",
    "ask_run_events",
)


def _normalized_sql(path: Path) -> str:
    return " ".join(path.read_text(encoding="utf-8").lower().split())


def _seed_turn(
    connection: Connection,
    *,
    user_id: UUID,
) -> tuple[UUID, int, int]:
    session_id = uuid4()
    connection.execute(
        text(
            """
            insert into public.chat_sessions (id, user_id, title)
            values (:session_id, :user_id, 'Artifact workspace')
            """
        ),
        {"session_id": session_id, "user_id": user_id},
    )
    user_message_id = connection.execute(
        text(
            """
            insert into public.chat_messages (
              public_id,
              session_id,
              user_id,
              role,
              content
            )
            values (:public_id, :session_id, :user_id, 'user', 'What changed?')
            returning id
            """
        ),
        {
            "public_id": uuid4(),
            "session_id": session_id,
            "user_id": user_id,
        },
    ).scalar_one()
    assistant_message_id = connection.execute(
        text(
            """
            insert into public.chat_messages (
              public_id,
              session_id,
              user_id,
              role,
              content
            )
            values (:public_id, :session_id, :user_id, 'assistant', '')
            returning id
            """
        ),
        {
            "public_id": uuid4(),
            "session_id": session_id,
            "user_id": user_id,
        },
    ).scalar_one()
    return session_id, user_message_id, assistant_message_id


def _seed_artifact_graph(
    connection: Connection,
    *,
    user_id: UUID,
) -> dict[str, Any]:
    session_id, user_message_id, assistant_message_id = _seed_turn(
        connection,
        user_id=user_id,
    )
    run_id = connection.execute(
        text(
            """
            insert into public.ask_runs (
              session_id,
              user_id,
              user_message_id,
              assistant_message_id,
              status,
              knowledge_mode_summary
            )
            values (
              :session_id,
              :user_id,
              :user_message_id,
              :assistant_message_id,
              'running',
              '{"official": true, "general": true, "live": true}'::jsonb
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

    section_ids: dict[str, UUID] = {}
    section_rows = (
        (0, "official", "Internal Regulatory Corpus", None),
        (1, "general", "General AI Knowledge", "No official evidence was used."),
        (2, "live", "Live Web Sources", None),
    )
    for ordinal, mode, provenance, disclosure in section_rows:
        section_ids[mode] = connection.execute(
            text(
                """
                insert into public.ask_sections (
                  run_id,
                  session_id,
                  user_id,
                  ordinal,
                  section_type,
                  status,
                  knowledge_mode,
                  provenance_label,
                  content,
                  model,
                  policy_version,
                  required_disclosure
                )
                values (
                  :run_id,
                  :session_id,
                  :user_id,
                  :ordinal,
                  'answer',
                  'completed',
                  :mode,
                  :provenance,
                  '{}'::jsonb,
                  :model,
                  :policy_version,
                  :disclosure
                )
                returning id
                """
            ),
            {
                "run_id": run_id,
                "session_id": session_id,
                "user_id": user_id,
                "ordinal": ordinal,
                "mode": mode,
                "provenance": provenance,
                "model": "parallel-general" if mode == "general" else None,
                "policy_version": "policy-v1" if mode == "general" else None,
                "disclosure": disclosure,
            },
        ).scalar_one()

    source_code = f"ask-{uuid4()}"
    source_id = connection.execute(
        text(
            """
            insert into public.sources (
              code,
              name,
              jurisdiction,
              url
            )
            values (:code, 'Artifact source', 'central', :url)
            returning id
            """
        ),
        {"code": source_code, "url": f"https://example.invalid/{source_code}"},
    ).scalar_one()
    document_id = connection.execute(
        text(
            """
            insert into public.documents (
              source_id,
              url_hash,
              source_url,
              title
            )
            values (:source_id, :url_hash, :source_url, 'Official instrument')
            returning id
            """
        ),
        {
            "source_id": source_id,
            "url_hash": str(uuid4()),
            "source_url": f"https://example.invalid/document/{uuid4()}",
        },
    ).scalar_one()
    version_id = connection.execute(
        text(
            """
            insert into public.document_versions (document_id, file_hash)
            values (:document_id, :file_hash)
            returning id
            """
        ),
        {"document_id": document_id, "file_hash": str(uuid4())},
    ).scalar_one()
    chunk_id = connection.execute(
        text(
            """
            insert into public.document_chunks (
              document_id,
              version_id,
              chunk_index,
              text
            )
            values (:document_id, :version_id, 0, 'Official evidence')
            returning id
            """
        ),
        {"document_id": document_id, "version_id": version_id},
    ).scalar_one()

    official_source_id = connection.execute(
        text(
            """
            insert into public.ask_sources (
              run_id,
              session_id,
              user_id,
              ordinal,
              source_key,
              source_class,
              source_type,
              document_id,
              document_version_id,
              chunk_id,
              title_snapshot,
              url_snapshot,
              issuer_snapshot,
              retrieved_at,
              evidence_snapshot
            )
            values (
              :run_id,
              :session_id,
              :user_id,
              0,
              'official-1',
              'official',
              'document_chunk',
              :document_id,
              :version_id,
              :chunk_id,
              'Official instrument',
              'https://example.invalid/official',
              'CERC',
              now(),
              'Official evidence'
            )
            returning id
            """
        ),
        {
            "run_id": run_id,
            "session_id": session_id,
            "user_id": user_id,
            "document_id": document_id,
            "version_id": version_id,
            "chunk_id": chunk_id,
        },
    ).scalar_one()
    live_source_id = connection.execute(
        text(
            """
            insert into public.ask_sources (
              run_id,
              session_id,
              user_id,
              ordinal,
              source_key,
              source_class,
              source_type,
              title_snapshot,
              url_snapshot,
              publisher_snapshot,
              published_at,
              retrieved_at,
              evidence_snapshot
            )
            values (
              :run_id,
              :session_id,
              :user_id,
              1,
              'live-1',
              'live',
              'news_article',
              'Live update',
              'https://example.invalid/live',
              'Example News',
              now() - interval '1 hour',
              now(),
              'Live evidence'
            )
            returning id
            """
        ),
        {"run_id": run_id, "session_id": session_id, "user_id": user_id},
    ).scalar_one()

    claim_ids: dict[str, UUID] = {}
    claim_rows = (
        ("official", "supported", 0, "Official claim", None, None, None),
        (
            "general",
            "not_applicable",
            0,
            "General explanation",
            "parallel-general",
            "policy-v1",
            "No official evidence was used.",
        ),
        ("live", "pending", 0, "Live claim", None, None, None),
    )
    for (
        mode,
        support_status,
        ordinal,
        claim_text,
        model,
        policy_version,
        disclosure,
    ) in claim_rows:
        claim_ids[mode] = connection.execute(
            text(
                """
                insert into public.ask_claims (
                  run_id,
                  section_id,
                  session_id,
                  user_id,
                  ordinal,
                  knowledge_mode,
                  claim_text,
                  support_status,
                  model,
                  policy_version,
                  required_disclosure
                )
                values (
                  :run_id,
                  :section_id,
                  :session_id,
                  :user_id,
                  :ordinal,
                  :mode,
                  :claim_text,
                  :support_status,
                  :model,
                  :policy_version,
                  :disclosure
                )
                returning id
                """
            ),
            {
                "run_id": run_id,
                "section_id": section_ids[mode],
                "session_id": session_id,
                "user_id": user_id,
                "ordinal": ordinal,
                "mode": mode,
                "claim_text": claim_text,
                "support_status": support_status,
                "model": model,
                "policy_version": policy_version,
                "disclosure": disclosure,
            },
        ).scalar_one()

    connection.execute(
        text(
            """
            insert into public.ask_citations (
              run_id,
              claim_id,
              source_id,
              session_id,
              user_id,
              ordinal,
              claim_knowledge_mode,
              source_class,
              citation_kind,
              evidence_snapshot
            )
            values (
              :run_id,
              :claim_id,
              :source_id,
              :session_id,
              :user_id,
              0,
              'official',
              'official',
              'official_citation',
              'Official evidence'
            )
            """
        ),
        {
            "run_id": run_id,
            "claim_id": claim_ids["official"],
            "source_id": official_source_id,
            "session_id": session_id,
            "user_id": user_id,
        },
    )
    connection.execute(
        text(
            """
            insert into public.ask_followups (
              run_id,
              session_id,
              user_id,
              ordinal,
              label,
              question
            )
            values (
              :run_id,
              :session_id,
              :user_id,
              0,
              'Compare',
              'Compare with the prior instrument'
            )
            """
        ),
        {"run_id": run_id, "session_id": session_id, "user_id": user_id},
    )
    connection.execute(
        text(
            """
            insert into public.ask_run_events (
              run_id,
              session_id,
              user_id,
              sequence,
              event_type,
              status
            )
            values (
              :run_id,
              :session_id,
              :user_id,
              0,
              'run.started',
              'running'
            )
            """
        ),
        {"run_id": run_id, "session_id": session_id, "user_id": user_id},
    )
    return {
        "session_id": session_id,
        "run_id": run_id,
        "official_source_id": official_source_id,
        "live_source_id": live_source_id,
        "claim_ids": claim_ids,
    }


def test_0024_is_ordered_additive_and_excludes_general_ai_sources() -> None:
    migrations = discover_migrations(MIGRATIONS_DIR)
    artifact_migration = next(
        migration for migration in migrations if migration.version == "0024"
    )
    sql = _normalized_sql(ARTIFACT_MIGRATION)
    readme = " ".join(
        MIGRATION_README.read_text(encoding="utf-8").lower().split()
    )

    assert artifact_migration.filename == "0024_ask_ai_artifacts.sql"
    for table in ARTIFACT_TABLES:
        assert f"create table public.{table}" in sql
        assert f"alter table public.{table} enable row level security" in sql
    assert "create table public.ask_feedback" not in sql
    assert "create table public.ask_saved_items" not in sql
    assert "source_class in ('official', 'live')" in sql
    assert "knowledge_mode in ('official', 'general', 'live')" in sql
    assert "general ai provenance is stored on runs, sections, and claims" in readme
    assert "drop table" not in sql
    assert "delete from public.chat_messages" not in sql


@POSTGRES_MARK
def test_0024_applies_from_empty_schema_with_rls_and_ledger(
    postgres_engine: Engine,
) -> None:
    applied = apply_pending_migrations(
        postgres_engine,
        MIGRATIONS_DIR,
        through="0024",
    )

    assert len(applied) == 24
    assert applied[-1].version == "0024"
    with postgres_engine.connect() as connection:
        assert connection.execute(
            text(
                """
                select count(*)
                from public.schema_migrations
                where version = '0024'
                  and filename = '0024_ask_ai_artifacts.sql'
                """
            )
        ).scalar_one() == 1
        for table in ARTIFACT_TABLES:
            assert connection.execute(
                text(
                    """
                    select relrowsecurity
                    from pg_class
                    where oid = to_regclass(:table_name)
                    """
                ),
                {"table_name": f"public.{table}"},
            ).scalar_one() is True
            assert connection.execute(
                text(
                    """
                    select has_table_privilege(
                      'authenticated',
                      :table_name,
                      'select'
                    )
                    """
                ),
                {"table_name": f"public.{table}"},
            ).scalar_one() is True
            assert connection.execute(
                text(
                    """
                    select has_table_privilege(
                      'authenticated',
                      :table_name,
                      'insert,update,delete'
                    )
                    """
                ),
                {"table_name": f"public.{table}"},
            ).scalar_one() is False


@POSTGRES_MARK
def test_0024_upgrades_0023_without_mutating_existing_turns(
    postgres_engine: Engine,
) -> None:
    apply_pending_migrations(postgres_engine, MIGRATIONS_DIR, through="0023")
    owner_id = uuid4()
    with postgres_engine.begin() as connection:
        insert_auth_user(connection, owner_id)
        session_id, user_message_id, assistant_message_id = _seed_turn(
            connection,
            user_id=owner_id,
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
            through="0024",
        )
    ] == ["0024"]
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
        assert connection.execute(
            text("select count(*) from public.chat_sessions where id = :session_id"),
            {"session_id": session_id},
        ).scalar_one() == 1

    assert after == before


@POSTGRES_MARK
def test_0024_artifact_rls_hides_every_table_from_non_owners(
    postgres_engine: Engine,
) -> None:
    apply_pending_migrations(postgres_engine, MIGRATIONS_DIR, through="0024")
    owner_id = uuid4()
    other_id = uuid4()
    with postgres_engine.begin() as connection:
        insert_auth_user(connection, owner_id)
        insert_auth_user(connection, other_id)
        _seed_artifact_graph(connection, user_id=owner_id)

    for principal_id, should_see_rows in ((owner_id, True), (other_id, False)):
        with postgres_engine.begin() as connection:
            connection.execute(text("set local role authenticated"))
            connection.execute(
                text("select set_config('request.jwt.claim.sub', :user_id, true)"),
                {"user_id": str(principal_id)},
            )
            for table in ARTIFACT_TABLES:
                count = connection.execute(
                    text(f"select count(*) from public.{table}")
                ).scalar_one()
                assert (count > 0) is should_see_rows


@POSTGRES_MARK
def test_0024_rejects_general_sources_mixed_provenance_and_event_replay(
    postgres_engine: Engine,
) -> None:
    apply_pending_migrations(postgres_engine, MIGRATIONS_DIR, through="0024")
    owner_id = uuid4()
    other_id = uuid4()
    with postgres_engine.begin() as connection:
        insert_auth_user(connection, owner_id)
        insert_auth_user(connection, other_id)
        graph = _seed_artifact_graph(connection, user_id=owner_id)

    base = {
        "run_id": graph["run_id"],
        "session_id": graph["session_id"],
        "user_id": owner_id,
    }
    with pytest.raises(IntegrityError), postgres_engine.begin() as connection:
        connection.execute(
            text(
                """
                insert into public.ask_sources (
                  run_id,
                  session_id,
                  user_id,
                  ordinal,
                  source_key,
                  source_class,
                  source_type,
                  title_snapshot,
                  url_snapshot,
                  retrieved_at,
                  evidence_snapshot
                )
                values (
                  :run_id,
                  :session_id,
                  :user_id,
                  9,
                  'general-ai',
                  'general',
                  'model',
                  'General AI',
                  'https://example.invalid/general',
                  now(),
                  'Generated text'
                )
                """
            ),
            base,
        )

    with pytest.raises(IntegrityError), postgres_engine.begin() as connection:
        connection.execute(
            text(
                """
                insert into public.ask_citations (
                  run_id,
                  claim_id,
                  source_id,
                  session_id,
                  user_id,
                  ordinal,
                  claim_knowledge_mode,
                  source_class,
                  citation_kind,
                  evidence_snapshot
                )
                values (
                  :run_id,
                  :claim_id,
                  :source_id,
                  :session_id,
                  :user_id,
                  0,
                  'general',
                  'official',
                  'official_citation',
                  'Invalid borrowed evidence'
                )
                """
            ),
            {
                **base,
                "claim_id": graph["claim_ids"]["general"],
                "source_id": graph["official_source_id"],
            },
        )

    with pytest.raises(IntegrityError), postgres_engine.begin() as connection:
        connection.execute(
            text(
                """
                insert into public.ask_citations (
                  run_id,
                  claim_id,
                  source_id,
                  session_id,
                  user_id,
                  ordinal,
                  claim_knowledge_mode,
                  source_class,
                  citation_kind,
                  evidence_snapshot
                )
                values (
                  :run_id,
                  :claim_id,
                  :source_id,
                  :session_id,
                  :user_id,
                  1,
                  'official',
                  'live',
                  'live_source_link',
                  'Invalid mixed evidence'
                )
                """
            ),
            {
                **base,
                "claim_id": graph["claim_ids"]["official"],
                "source_id": graph["live_source_id"],
            },
        )

    with pytest.raises(IntegrityError), postgres_engine.begin() as connection:
        connection.execute(
            text(
                """
                insert into public.ask_followups (
                  run_id,
                  session_id,
                  user_id,
                  ordinal,
                  label,
                  question
                )
                values (
                  :run_id,
                  :session_id,
                  :other_id,
                  1,
                  'Cross owner',
                  'Should fail'
                )
                """
            ),
            {**base, "other_id": other_id},
        )

    with pytest.raises(IntegrityError), postgres_engine.begin() as connection:
        connection.execute(
            text(
                """
                insert into public.ask_run_events (
                  run_id,
                  session_id,
                  user_id,
                  sequence,
                  event_type
                )
                values (
                  :run_id,
                  :session_id,
                  :user_id,
                  0,
                  'run.started.replay'
                )
                """
            ),
            base,
        )
