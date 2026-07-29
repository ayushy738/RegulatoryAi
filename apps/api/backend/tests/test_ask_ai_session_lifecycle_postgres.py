from __future__ import annotations

from datetime import UTC, datetime, timedelta
from pathlib import Path
from uuid import UUID, uuid4

import pytest
from sqlalchemy.engine import Engine

from backend.ask.persistence import (
    AskPersistenceService,
    ChatSessionStateConflictError,
)
from backend.core.migrations import apply_pending_migrations
from backend.tests.ask_ai_postgres import POSTGRES_MARK, insert_auth_user
from backend.tests.test_ask_ai_message_history_postgres import (
    _create_run_turn,
    _session_scope,
)

pytestmark = POSTGRES_MARK

MIGRATIONS_DIR = Path(__file__).parents[1] / "migrations"
NOW = datetime(2026, 7, 27, 12, 0, tzinfo=UTC)


def _service(engine: Engine, now: datetime = NOW) -> AskPersistenceService:
    return AskPersistenceService(
        lambda: _session_scope(engine),
        clock=lambda: now,
    )


@pytest.fixture
def lifecycle_owner(postgres_engine: Engine) -> tuple[Engine, UUID]:
    apply_pending_migrations(postgres_engine, MIGRATIONS_DIR, through="0029")
    owner_id = uuid4()
    with postgres_engine.begin() as connection:
        insert_auth_user(connection, owner_id)
    return postgres_engine, owner_id


def test_rename_pin_archive_restore_are_owned_idempotent_transitions(
    lifecycle_owner,
) -> None:
    engine, owner_id = lifecycle_owner
    service = _service(engine)
    session = service.create_session(
        user_id=owner_id,
        title="Original",
        primary_entity="CERC",
        primary_topic="tariff",
        scope_snapshot={"jurisdiction": "central"},
    )

    patched = service.patch_session(
        session_id=session.id,
        user_id=owner_id,
        title="Renamed",
        is_pinned=True,
    )
    assert patched is not None
    assert patched.title == "Renamed"
    assert patched.is_pinned is True
    assert patched.updated_at == NOW
    repeated_patch = _service(engine, NOW + timedelta(minutes=5)).patch_session(
        session_id=session.id,
        user_id=owner_id,
        title="Renamed",
        is_pinned=True,
    )
    assert repeated_patch is not None
    assert repeated_patch.updated_at == NOW

    archived = service.archive_session(
        session_id=session.id,
        user_id=owner_id,
    )
    repeated_archive = service.archive_session(
        session_id=session.id,
        user_id=owner_id,
    )
    assert archived is not None
    assert repeated_archive is not None
    assert archived.archived_at == repeated_archive.archived_at == NOW
    assert archived.updated_at == repeated_archive.updated_at == NOW
    assert archived.is_pinned is False

    with pytest.raises(ChatSessionStateConflictError, match="cannot be pinned"):
        service.patch_session(
            session_id=session.id,
            user_id=owner_id,
            title=None,
            is_pinned=True,
        )

    restore_time = NOW + timedelta(minutes=1)
    restored_service = _service(engine, restore_time)
    restored = restored_service.restore_session(
        session_id=session.id,
        user_id=owner_id,
    )
    repeated_restore = restored_service.restore_session(
        session_id=session.id,
        user_id=owner_id,
    )
    assert restored is not None
    assert repeated_restore is not None
    assert restored.archived_at is None
    assert restored.updated_at == repeated_restore.updated_at == restore_time
    assert service.patch_session(
        session_id=session.id,
        user_id=uuid4(),
        title="Crossed",
        is_pinned=None,
    ) is None


def test_duplicate_creates_independent_context_without_copying_grounded_output(
    lifecycle_owner,
) -> None:
    engine, owner_id = lifecycle_owner
    service = _service(engine)
    source = service.create_session(
        user_id=owner_id,
        title="A" * 200,
        primary_entity="DSM",
        primary_topic="overview",
        scope_snapshot={"jurisdiction": "India"},
        knowledge_mode_summary={"grounded": True},
        freshness_state="current",
    )
    _create_run_turn(
        engine,
        owner_id=owner_id,
        session_id=source.id,
        at=NOW,
        label="source",
        with_artifacts=True,
    )
    duplicate_id = uuid4()

    duplicate = service.duplicate_session(
        session_id=source.id,
        user_id=owner_id,
        duplicate_session_id=duplicate_id,
    )

    assert duplicate is not None
    assert duplicate.id == duplicate_id
    assert duplicate.user_id == owner_id
    assert len(duplicate.title or "") <= 200
    assert duplicate.title is not None and duplicate.title.endswith(" (Copy)")
    assert duplicate.primary_entity == source.primary_entity
    assert duplicate.primary_topic == source.primary_topic
    assert duplicate.scope_snapshot == source.scope_snapshot
    assert duplicate.knowledge_mode_summary == {}
    assert duplicate.freshness_state is None
    assert duplicate.is_pinned is False
    assert duplicate.archived_at is None
    assert service.list_turns(
        session_id=duplicate.id,
        user_id=owner_id,
        limit=10,
    ).items == ()
    assert service.get_session(
        session_id=source.id,
        user_id=owner_id,
    ) is not None


def test_export_is_exact_safe_and_owner_scoped(lifecycle_owner) -> None:
    engine, owner_id = lifecycle_owner
    service = _service(engine)
    session = service.create_session(user_id=owner_id, title="Export research")
    _create_run_turn(
        engine,
        owner_id=owner_id,
        session_id=session.id,
        at=NOW,
        label="export",
        with_artifacts=True,
    )

    exported = service.export_session(
        session_id=session.id,
        user_id=owner_id,
    )
    repeated = service.export_session(
        session_id=session.id,
        user_id=owner_id,
    )

    assert exported is not None
    assert exported == repeated
    assert exported.session.id == session.id
    assert len(exported.turns) == 1
    assert exported.turns[0].run is not None
    assert exported.turns[0].run.sections[0].plain_text == "Deadline changed."
    assert exported.turns[0].run.decision_record == {}
    assert exported.saved_items == ()
    assert service.export_session(
        session_id=session.id,
        user_id=uuid4(),
    ) is None


def test_soft_delete_is_recoverable_idempotent_and_hides_session(
    lifecycle_owner,
) -> None:
    engine, owner_id = lifecycle_owner
    service = _service(engine)
    session = service.create_session(user_id=owner_id, title="Delete me")

    assert service.soft_delete_session(
        session_id=session.id,
        user_id=owner_id,
    ) is True
    assert service.soft_delete_session(
        session_id=session.id,
        user_id=owner_id,
    ) is True
    assert service.get_session(
        session_id=session.id,
        user_id=owner_id,
    ) is None
    assert service.export_session(
        session_id=session.id,
        user_id=owner_id,
    ) is None
    assert service.duplicate_session(
        session_id=session.id,
        user_id=owner_id,
    ) is None
    assert service.soft_delete_session(
        session_id=session.id,
        user_id=uuid4(),
    ) is None
