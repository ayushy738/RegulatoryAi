from __future__ import annotations

from collections.abc import Iterator
from contextlib import contextmanager
from pathlib import Path
from typing import Any
from uuid import UUID, uuid4

import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient
from sqlalchemy import text
from sqlalchemy.engine import Connection, Engine
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from backend.api.auth import CurrentUser, current_user
from backend.api.routes import chat_evidence, chat_sessions
from backend.ask.persistence import AskPersistenceService
from backend.core.migrations import apply_pending_migrations, discover_migrations
from backend.tests.ask_ai_postgres import POSTGRES_MARK, insert_auth_user

MIGRATIONS_DIR = Path(__file__).parents[1] / "migrations"
SAVED_ITEM_MIGRATION = MIGRATIONS_DIR / "0028_ask_ai_saved_items.sql"
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


def _seed_targets(
    connection: Connection,
    *,
    user_id: UUID,
) -> dict[str, Any]:
    session_id = uuid4()
    connection.execute(
        text(
            """
            insert into public.chat_sessions (id, user_id, title)
            values (:session_id, :user_id, 'Saved evidence workspace')
            """
        ),
        {"session_id": session_id, "user_id": user_id},
    )
    user_message_id = connection.execute(
        text(
            """
            insert into public.chat_messages (
              public_id, session_id, user_id, role, content, status
            )
            values (
              :public_id, :session_id, :user_id, 'user', 'Latest DSM?', 'completed'
            )
            returning id
            """
        ),
        {"public_id": uuid4(), "session_id": session_id, "user_id": user_id},
    ).scalar_one()
    assistant_public_id = uuid4()
    assistant_message_id = connection.execute(
        text(
            """
            insert into public.chat_messages (
              public_id, session_id, user_id, role, content, status,
              response_version, reply_to_message_id
            )
            values (
              :public_id, :session_id, :user_id, 'assistant', 'Latest answer',
              'completed', 1, :user_message_id
            )
            returning id
            """
        ),
        {
            "public_id": assistant_public_id,
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
              :session_id, :user_id, :user_message_id, :assistant_message_id,
              1, 'completed'
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
    section_id = connection.execute(
        text(
            """
            insert into public.ask_sections (
              run_id, session_id, user_id, response_version, ordinal,
              section_type, status, knowledge_mode, provenance_label, title,
              plain_text
            )
            values (
              :run_id, :session_id, :user_id, 1, 0,
              'latest_update', 'completed', 'live', 'Live Web Sources',
              'Latest update', 'Deadline changed.'
            )
            returning id
            """
        ),
        {"run_id": run_id, "session_id": session_id, "user_id": user_id},
    ).scalar_one()
    source_id = connection.execute(
        text(
            """
            insert into public.ask_sources (
              run_id, session_id, user_id, ordinal, source_key, source_class,
              source_type, title_snapshot, url_snapshot, publisher_snapshot,
              published_at, retrieved_at, evidence_snapshot
            )
            values (
              :run_id, :session_id, :user_id, 0, 'live:save', 'live',
              'news', 'Consultation update', 'https://example.test/update',
              'Regulatory Bulletin', now(), now(), 'The deadline changed.'
            )
            returning id
            """
        ),
        {"run_id": run_id, "session_id": session_id, "user_id": user_id},
    ).scalar_one()
    claim_id = connection.execute(
        text(
            """
            insert into public.ask_claims (
              run_id, section_id, session_id, user_id, ordinal, knowledge_mode,
              claim_text, support_status, support_score
            )
            values (
              :run_id, :section_id, :session_id, :user_id, 0, 'live',
              'The deadline changed.', 'supported', 0.95
            )
            returning id
            """
        ),
        {
            "run_id": run_id,
            "section_id": section_id,
            "session_id": session_id,
            "user_id": user_id,
        },
    ).scalar_one()
    citation_id = connection.execute(
        text(
            """
            insert into public.ask_citations (
              run_id, claim_id, source_id, session_id, user_id, ordinal,
              claim_knowledge_mode, source_class, citation_kind, marker,
              evidence_snapshot, verification_status
            )
            values (
              :run_id, :claim_id, :source_id, :session_id, :user_id, 0,
              'live', 'live', 'live_source_link', '[1]',
              'The deadline changed.', 'verified'
            )
            returning id
            """
        ),
        {
            "run_id": run_id,
            "claim_id": claim_id,
            "source_id": source_id,
            "session_id": session_id,
            "user_id": user_id,
        },
    ).scalar_one()
    entity_id = f"test.entity.{uuid4().hex}"
    connection.execute(
        text(
            """
            insert into public.regulatory_entity_catalog (
              canonical_id, canonical_name, entity_class, jurisdiction,
              provenance_kind, provenance_ref
            )
            values (
              :entity_id, 'Test DSM Entity', 'regulatory_concept', 'central',
              'curated_catalog', 'test-fixture'
            )
            """
        ),
        {"entity_id": entity_id},
    )
    document_id = connection.execute(
        text(
            """
            insert into public.documents (
              url_hash, source_url, title, issuing_body, jurisdiction
            )
            values (
              :url_hash, 'https://example.test/document', 'DSM Regulation',
              'CERC', 'central'
            )
            returning id
            """
        ),
        {"url_hash": f"saved-{uuid4().hex}"},
    ).scalar_one()
    return {
        "session_id": session_id,
        "assistant_public_id": assistant_public_id,
        "run_id": run_id,
        "section_id": section_id,
        "source_id": source_id,
        "citation_id": citation_id,
        "entity_id": entity_id,
        "document_id": document_id,
    }


def test_0028_is_additive_owner_scoped_and_least_privilege() -> None:
    migration = next(
        item for item in discover_migrations(MIGRATIONS_DIR) if item.version == "0028"
    )
    sql = _normalized(SAVED_ITEM_MIGRATION)
    readme = _normalized(MIGRATION_README)

    assert migration.filename == "0028_ask_ai_saved_items.sql"
    assert "create table public.ask_saved_items" in sql
    assert "ask_saved_items_run_owner_version_fkey" in sql
    assert "item_type in ('source', 'citation', 'card', 'entity', 'document')" in sql
    assert "alter table public.ask_saved_items enable row level security" in sql
    assert "grant select on table public.ask_saved_items to authenticated" in sql
    assert "saved items" in readme
    assert "drop table" not in sql
    assert "delete from public" not in sql


@POSTGRES_MARK
def test_0028_applies_from_empty_and_0027_without_mutating_artifacts(
    postgres_engine: Engine,
) -> None:
    applied = apply_pending_migrations(
        postgres_engine,
        MIGRATIONS_DIR,
        through="0028",
    )
    assert len(applied) == 28
    assert applied[-1].version == "0028"
    with postgres_engine.connect() as connection:
        assert connection.execute(
            text(
                "select relrowsecurity from pg_class "
                "where oid = 'public.ask_saved_items'::regclass"
            )
        ).scalar_one() is True
        assert connection.execute(
            text(
                """
                select has_table_privilege(
                  'authenticated', 'public.ask_saved_items', 'select'
                )
                """
            )
        ).scalar_one() is True
        assert connection.execute(
            text(
                """
                select has_table_privilege(
                  'authenticated',
                  'public.ask_saved_items',
                  'insert,update,delete'
                )
                """
            )
        ).scalar_one() is False

@POSTGRES_MARK
def test_0028_populated_upgrade_preserves_existing_artifacts(
    postgres_engine: Engine,
) -> None:
    apply_pending_migrations(postgres_engine, MIGRATIONS_DIR, through="0027")
    owner_id = uuid4()
    with postgres_engine.begin() as connection:
        insert_auth_user(connection, owner_id)
        targets = _seed_targets(connection, user_id=owner_id)
        before = connection.execute(
            text(
                """
                select source.id, source.title_snapshot, citation.id, section.id
                from public.ask_sources source
                join public.ask_citations citation on citation.source_id = source.id
                join public.ask_sections section on section.run_id = source.run_id
                where source.run_id = :run_id
                """
            ),
            {"run_id": targets["run_id"]},
        ).one()

    assert [
        item.version
        for item in apply_pending_migrations(
            postgres_engine,
            MIGRATIONS_DIR,
            through="0028",
        )
    ] == ["0028"]
    with postgres_engine.connect() as connection:
        after = connection.execute(
            text(
                """
                select source.id, source.title_snapshot, citation.id, section.id
                from public.ask_sources source
                join public.ask_citations citation on citation.source_id = source.id
                join public.ask_sections section on section.run_id = source.run_id
                where source.run_id = :run_id
                """
            ),
            {"run_id": targets["run_id"]},
        ).one()
    assert after == before


@POSTGRES_MARK
def test_saved_items_are_exact_idempotent_and_owner_isolated(
    postgres_engine: Engine,
) -> None:
    apply_pending_migrations(postgres_engine, MIGRATIONS_DIR, through="0028")
    owner_id = uuid4()
    other_id = uuid4()
    with postgres_engine.begin() as connection:
        insert_auth_user(connection, owner_id)
        insert_auth_user(connection, other_id)
        targets = _seed_targets(connection, user_id=owner_id)

    service = _service(postgres_engine)
    target_pairs = (
        ("source", str(targets["source_id"])),
        ("citation", str(targets["citation_id"])),
        ("card", str(targets["section_id"])),
        ("entity", targets["entity_id"]),
        ("document", str(targets["document_id"])),
    )
    saved = [
        service.save_item(
            session_id=targets["session_id"],
            user_id=owner_id,
            item_type=item_type,
            target_key=target_key,
        )
        for item_type, target_key in target_pairs
    ]
    assert all(item is not None for item in saved)
    resolved = [item for item in saved if item is not None]
    assert [item.item_type for item in resolved] == [
        "source",
        "citation",
        "card",
        "entity",
        "document",
    ]
    assert all(
        item.response_version == 1
        for item in resolved
        if item.item_type in {"source", "citation", "card"}
    )
    duplicate = service.save_item(
        session_id=targets["session_id"],
        user_id=owner_id,
        item_type="source",
        target_key=str(targets["source_id"]),
    )
    assert duplicate is not None
    assert duplicate.id == resolved[0].id

    assert service.save_item(
        session_id=targets["session_id"],
        user_id=other_id,
        item_type="source",
        target_key=str(targets["source_id"]),
    ) is None
    assert service.list_saved_items(
        session_id=targets["session_id"],
        user_id=other_id,
    ) is None
    listed = service.list_saved_items(
        session_id=targets["session_id"],
        user_id=owner_id,
    )
    assert listed is not None
    assert [item.id for item in listed] == [item.id for item in resolved]
    assert service.delete_saved_item(
        saved_item_id=resolved[0].id,
        session_id=targets["session_id"],
        user_id=other_id,
    ) is False
    assert service.delete_saved_item(
        saved_item_id=resolved[0].id,
        session_id=targets["session_id"],
        user_id=owner_id,
    ) is True

    with pytest.raises(IntegrityError), postgres_engine.begin() as connection:
        connection.execute(
            text(
                """
                insert into public.ask_saved_items (
                  session_id, user_id, item_type, target_key, run_id,
                  response_version, source_id, label_snapshot
                )
                values (
                  :session_id, :other_id, 'source', :target_key, :run_id,
                  1, :source_id, 'Cross-owner source'
                )
                """
            ),
            {
                "session_id": targets["session_id"],
                "other_id": other_id,
                "target_key": str(targets["source_id"]),
                "run_id": targets["run_id"],
                "source_id": targets["source_id"],
            },
        )


@POSTGRES_MARK
def test_saved_item_rls_hides_non_owner_rows(postgres_engine: Engine) -> None:
    apply_pending_migrations(postgres_engine, MIGRATIONS_DIR, through="0028")
    owner_id = uuid4()
    other_id = uuid4()
    with postgres_engine.begin() as connection:
        insert_auth_user(connection, owner_id)
        insert_auth_user(connection, other_id)
        targets = _seed_targets(connection, user_id=owner_id)
    item = _service(postgres_engine).save_item(
        session_id=targets["session_id"],
        user_id=owner_id,
        item_type="source",
        target_key=str(targets["source_id"]),
    )
    assert item is not None

    for principal_id, expected_count in ((owner_id, 1), (other_id, 0)):
        with postgres_engine.begin() as connection:
            connection.execute(text("set local role authenticated"))
            connection.execute(
                text("select set_config('request.jwt.claim.sub', :user_id, true)"),
                {"user_id": str(principal_id)},
            )
            assert connection.execute(
                text("select count(*) from public.ask_saved_items")
            ).scalar_one() == expected_count


@POSTGRES_MARK
def test_evidence_feedback_and_saved_item_endpoints_enforce_real_ownership(
    postgres_engine: Engine,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    apply_pending_migrations(postgres_engine, MIGRATIONS_DIR, through="0028")
    owner_id = uuid4()
    other_id = uuid4()
    with postgres_engine.begin() as connection:
        insert_auth_user(connection, owner_id)
        insert_auth_user(connection, other_id)
        targets = _seed_targets(connection, user_id=owner_id)

    principal = {"id": owner_id}
    api = FastAPI()
    api.include_router(chat_evidence.router)
    api.include_router(chat_evidence.saved_items_router)
    api.dependency_overrides[current_user] = lambda: CurrentUser(
        id=str(principal["id"]),
        email="evidence-api@example.test",
    )
    api.dependency_overrides[chat_evidence.get_ask_evidence_service] = lambda: _service(
        postgres_engine
    )
    monkeypatch.setattr(chat_sessions.settings, "ask_ai_v2_api_enabled", True)

    with TestClient(api) as client:
        evidence = client.get(
            f"/chat/messages/{targets['assistant_public_id']}"
        )
        sources = client.get(
            f"/chat/messages/{targets['assistant_public_id']}/sources"
        )
        feedback = client.post(
            f"/chat/messages/{targets['assistant_public_id']}/feedback",
            json={
                "value": "not_helpful",
                "reason_code": "missing_source",
                "comment": "Add the notice.",
            },
        )
        feedback_update = client.post(
            f"/chat/messages/{targets['assistant_public_id']}/feedback",
            json={"value": "helpful"},
        )
        saved = client.post(
            f"/chat/sessions/{targets['session_id']}/saved-items",
            json={"item_type": "source", "target_id": str(targets["source_id"])},
        )
        saved_duplicate = client.post(
            f"/chat/sessions/{targets['session_id']}/saved-items",
            json={"item_type": "source", "target_id": str(targets["source_id"])},
        )
        listed = client.get(
            f"/chat/sessions/{targets['session_id']}/saved-items"
        )

        assert evidence.status_code == sources.status_code == feedback.status_code == 200
        assert evidence.json()["response_version"] == 1
        assert evidence.json()["message"]["id"] == str(targets["assistant_public_id"])
        assert sources.json()["sources"][0]["id"] == str(targets["source_id"])
        assert sources.json()["citations"][0]["id"] == str(targets["citation_id"])
        assert feedback.json()["response_version"] == 1
        assert feedback_update.status_code == 200
        assert feedback_update.json()["id"] == feedback.json()["id"]
        assert feedback_update.json()["value"] == "helpful"
        assert saved.status_code == 201
        assert saved.json()["target_id"] == str(targets["source_id"])
        assert saved_duplicate.status_code == 201
        assert saved_duplicate.json()["id"] == saved.json()["id"]
        assert listed.status_code == 200
        assert listed.json()["items"] == [saved.json()]

        principal["id"] = other_id
        hidden_responses = (
            client.get(f"/chat/messages/{targets['assistant_public_id']}"),
            client.get(
                f"/chat/messages/{targets['assistant_public_id']}/sources"
            ),
            client.post(
                f"/chat/messages/{targets['assistant_public_id']}/feedback",
                json={"value": "helpful"},
            ),
            client.get(f"/chat/sessions/{targets['session_id']}/saved-items"),
            client.post(
                f"/chat/sessions/{targets['session_id']}/saved-items",
                json={"item_type": "source", "target_id": str(targets["source_id"])},
            ),
            client.delete(
                f"/chat/sessions/{targets['session_id']}/saved-items/"
                f"{saved.json()['id']}"
            ),
        )

    assert all(response.status_code == 404 for response in hidden_responses)
