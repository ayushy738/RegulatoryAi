from __future__ import annotations

import json
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path
from uuid import UUID, uuid4

import pytest
from sqlalchemy import text
from sqlalchemy.orm import Session

from backend.ask.orchestration.contracts import (
    ArtifactEnvelope,
    ArtifactProducer,
    CapabilityScope,
    ResearchRequestPayload,
)
from backend.ask.orchestration.state_machine import initialize_orchestration
from backend.ask.regeneration import (
    REGENERATION_POLICY_VERSION,
    RefreshResponseRequest,
    RegenerateResponseRequest,
    ResponseRegenerationConflict,
    ResponseRegenerationNotFound,
    ResponseRegenerationService,
    ResponseSourceStrategy,
    ResponseStyleVariant,
)
from backend.core.migrations import apply_pending_migrations, discover_migrations
from backend.tests.ask_ai_postgres import POSTGRES_MARK, insert_auth_user

pytestmark = POSTGRES_MARK

MIGRATIONS_DIR = Path(__file__).parents[1] / "migrations"
REGENERATION_MIGRATION = (
    MIGRATIONS_DIR / "0032_ask_ai_response_regenerations.sql"
)
MIGRATION_README = MIGRATIONS_DIR / "README.md"


def _initial_state(run_id: UUID):
    research_request = ArtifactEnvelope(
        artifact_id=f"research:{run_id}",
        producer=ArtifactProducer.USER_CONTEXT,
        scope=CapabilityScope(
            atomic_question_ids=("question-1",),
            section_keys=("overview",),
        ),
        payload=ResearchRequestPayload(
            query="What changed in the filing rule?",
            explicit_constraints=("jurisdiction:in",),
        ),
    )
    return initialize_orchestration(
        run_id=run_id,
        plan_id=f"plan:{run_id}",
        policy_version="ask-ai-orchestration-v1",
        research_request=research_request,
    )


def _seed_source(engine) -> dict[str, UUID | int]:
    user_id = uuid4()
    session_id = uuid4()
    user_message_public_id = uuid4()
    source_message_public_id = uuid4()
    source_run_id = uuid4()
    source_id = uuid4()
    feedback_id = uuid4()
    state = _initial_state(source_run_id)
    with engine.begin() as connection:
        insert_auth_user(connection, user_id)
        connection.execute(
            text(
                """
                insert into public.chat_sessions (id, user_id, title)
                values (:session_id, :user_id, 'Versioned research')
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
                  :public_id, :session_id, :user_id, 'user',
                  'What changed in the filing rule?', 'completed'
                )
                returning id
                """
            ),
            {
                "public_id": user_message_public_id,
                "session_id": session_id,
                "user_id": user_id,
            },
        ).scalar_one()
        source_message_id = connection.execute(
            text(
                """
                insert into public.chat_messages (
                  public_id, session_id, user_id, role, content, status,
                  response_version, reply_to_message_id
                )
                values (
                  :public_id, :session_id, :user_id, 'assistant',
                  'The original answer.', 'completed', 1, :user_message_id
                )
                returning id
                """
            ),
            {
                "public_id": source_message_public_id,
                "session_id": session_id,
                "user_id": user_id,
                "user_message_id": user_message_id,
            },
        ).scalar_one()
        connection.execute(
            text(
                """
                insert into public.ask_runs (
                  id, session_id, user_id, user_message_id,
                  assistant_message_id, status, orchestration_state,
                  policy_version, response_version
                )
                values (
                  :run_id, :session_id, :user_id, :user_message_id,
                  :assistant_message_id, 'completed',
                  cast(:orchestration_state as jsonb),
                  'ask-ai-orchestration-v1', 1
                )
                """
            ),
            {
                "run_id": source_run_id,
                "session_id": session_id,
                "user_id": user_id,
                "user_message_id": user_message_id,
                "assistant_message_id": source_message_id,
                "orchestration_state": json.dumps(
                    state.model_dump(mode="json")
                ),
            },
        )
        connection.execute(
            text(
                """
                insert into public.ask_sources (
                  id, run_id, session_id, user_id, ordinal, source_key,
                  source_class, source_type, title_snapshot, url_snapshot,
                  publisher_snapshot, published_at, retrieved_at,
                  evidence_snapshot, metadata
                )
                values (
                  :source_id, :run_id, :session_id, :user_id, 0, 'live:1',
                  'live', 'web', 'Regulator update',
                  'https://example.test/update', 'Regulator',
                  '2026-07-01T00:00:00Z', '2026-07-02T00:00:00Z',
                  'Immutable source evidence.', '{"safe": true}'::jsonb
                )
                """
            ),
            {
                "source_id": source_id,
                "run_id": source_run_id,
                "session_id": session_id,
                "user_id": user_id,
            },
        )
        connection.execute(
            text(
                """
                insert into public.ask_feedback (
                  id, run_id, session_id, user_id, response_version,
                  value, reason_code, comment
                )
                values (
                  :feedback_id, :run_id, :session_id, :user_id, 1,
                  'not_helpful', 'outdated', 'Refresh this answer.'
                )
                """
            ),
            {
                "feedback_id": feedback_id,
                "run_id": source_run_id,
                "session_id": session_id,
                "user_id": user_id,
            },
        )
    return {
        "user_id": user_id,
        "session_id": session_id,
        "user_message_id": user_message_id,
        "user_message_public_id": user_message_public_id,
        "source_message_id": source_message_id,
        "source_message_public_id": source_message_public_id,
        "source_run_id": source_run_id,
        "source_id": source_id,
        "feedback_id": feedback_id,
    }


def _service(engine) -> ResponseRegenerationService:
    return ResponseRegenerationService(
        session_scope_factory=lambda: Session(engine),
    )


def _source_snapshot(engine, seeded: dict[str, UUID | int]):
    with engine.connect() as connection:
        return connection.execute(
            text(
                """
                select
                  message.content,
                  message.status as message_status,
                  run.status as run_status,
                  run.orchestration_state,
                  source.evidence_snapshot,
                  source.metadata,
                  feedback.value,
                  feedback.reason_code,
                  feedback.comment
                from public.chat_messages message
                join public.ask_runs run
                  on run.assistant_message_id = message.id
                join public.ask_sources source
                  on source.run_id = run.id
                join public.ask_feedback feedback
                  on feedback.run_id = run.id
                where run.id = :run_id
                """
            ),
            {"run_id": seeded["source_run_id"]},
        ).mappings().one()


def test_0032_is_ordered_additive_and_documents_retained_rollback() -> None:
    migrations = discover_migrations(MIGRATIONS_DIR)
    migration = next(item for item in migrations if item.version == "0032")
    sql = " ".join(
        REGENERATION_MIGRATION.read_text(encoding="utf-8").lower().split()
    )
    readme = " ".join(
        MIGRATION_README.read_text(encoding="utf-8").lower().split()
    )

    assert migration.filename == "0032_ask_ai_response_regenerations.sql"
    assert migrations[migrations.index(migration) + 1].version == "0033"
    assert "create table public.ask_response_regenerations" in sql
    assert "target_response_version = parent_response_version + 1" in sql
    assert "enable row level security" in sql
    assert "rollback is flag-off and worker stop" in readme
    assert "do not delete or renumber versions" in readme


def test_0032_applies_with_exact_constraints_index_and_rls(
    postgres_engine,
) -> None:
    applied = apply_pending_migrations(
        postgres_engine,
        MIGRATIONS_DIR,
        through="0032",
    )
    assert applied[-1].version == "0032"

    with postgres_engine.connect() as connection:
        constraints = {
            row[0]
            for row in connection.execute(
                text(
                    """
                    select conname
                    from pg_constraint
                    where conrelid =
                      'public.ask_response_regenerations'::regclass
                    """
                )
            )
        }
        indexes = {
            row[0]
            for row in connection.execute(
                text(
                    """
                    select indexname
                    from pg_indexes
                    where schemaname = 'public'
                      and tablename = 'ask_response_regenerations'
                    """
                )
            )
        }
        security = connection.execute(
            text(
                """
                select relrowsecurity
                from pg_class
                where oid =
                  'public.ask_response_regenerations'::regclass
                """
            )
        ).scalar_one()

    assert {
        "ask_response_regenerations_source_run_owner_version_fkey",
        "ask_response_regenerations_target_run_owner_version_fkey",
        "ask_response_regenerations_source_message_fkey",
        "ask_response_regenerations_parent_message_fkey",
        "ask_response_regenerations_target_message_fkey",
        "ask_response_regenerations_versions_chk",
    } <= constraints
    assert "ask_response_regenerations_turn_version_idx" in indexes
    assert security is True


def test_0032_populated_upgrade_preserves_existing_answer_and_evidence(
    postgres_engine,
) -> None:
    apply_pending_migrations(postgres_engine, MIGRATIONS_DIR, through="0031")
    seeded = _seed_source(postgres_engine)
    before = dict(_source_snapshot(postgres_engine, seeded))

    applied = apply_pending_migrations(
        postgres_engine,
        MIGRATIONS_DIR,
        through="0032",
    )

    assert applied[-1].version == "0032"
    assert dict(_source_snapshot(postgres_engine, seeded)) == before
    with postgres_engine.connect() as connection:
        assert connection.execute(
            text("select count(*) from public.ask_response_regenerations")
        ).scalar_one() == 0


def test_same_source_is_idempotent_append_only_and_durable(
    postgres_engine,
) -> None:
    apply_pending_migrations(postgres_engine, MIGRATIONS_DIR, through="0032")
    seeded = _seed_source(postgres_engine)
    before = dict(_source_snapshot(postgres_engine, seeded))
    request = RegenerateResponseRequest(
        idempotency_key=uuid4(),
        assistant_message_id=uuid4(),
        style_variant=ResponseStyleVariant.CONCISE,
    )
    service = _service(postgres_engine)

    created = service.regenerate(
        source_message_id=seeded["source_message_public_id"],
        user_id=seeded["user_id"],
        request=request,
    )
    repeated = service.regenerate(
        source_message_id=seeded["source_message_public_id"],
        user_id=seeded["user_id"],
        request=request,
    )

    assert repeated == created
    assert created.plan.source_response_version == 1
    assert created.plan.parent_response_version == 1
    assert created.plan.target_response_version == 2
    assert created.plan.source_snapshot_ids == (seeded["source_id"],)
    assert created.plan.reused_source_snapshot_ids == (seeded["source_id"],)
    assert created.plan.refresh_knowledge_modes == ()
    assert created.plan.style_variant is ResponseStyleVariant.CONCISE
    assert dict(_source_snapshot(postgres_engine, seeded)) == before

    with postgres_engine.connect() as connection:
        counts = connection.execute(
            text(
                """
                select
                  count(*) filter (
                    where run.user_message_id = :user_message_id
                  ) as run_count,
                  count(*) filter (
                    where mutation.request_id = :request_id
                  ) as mutation_count
                from public.ask_runs run
                left join public.ask_response_regenerations mutation
                  on mutation.target_run_id = run.id
                where run.user_message_id = :user_message_id
                """
            ),
            {
                "user_message_id": seeded["user_message_id"],
                "request_id": request.idempotency_key,
            },
        ).mappings().one()
        target = connection.execute(
            text(
                """
                select
                  run.status,
                  run.response_version,
                  run.orchestration_state,
                  message.status as message_status,
                  message.content,
                  message.parent_message_id
                from public.ask_runs run
                join public.chat_messages message
                  on message.id = run.assistant_message_id
                where run.id = :target_run_id
                """
            ),
            {"target_run_id": created.plan.target_run_id},
        ).mappings().one()

    state = target["orchestration_state"]
    assert counts == {"run_count": 2, "mutation_count": 1}
    assert target["status"] == target["message_status"] == "pending"
    assert target["content"] == ""
    assert target["parent_message_id"] == seeded["source_message_id"]
    assert target["response_version"] == 2
    assert state["run_id"] == str(created.plan.target_run_id)
    assert state["policy_version"] == REGENERATION_POLICY_VERSION
    assert "response_source_strategy:same_sources" in (
        state["research_request"]["payload"]["explicit_constraints"]
    )
    assert "response_style:concise" in (
        state["research_request"]["payload"]["explicit_constraints"]
    )

    with pytest.raises(ResponseRegenerationConflict):
        service.regenerate(
            source_message_id=seeded["source_message_public_id"],
            user_id=seeded["user_id"],
            request=request.model_copy(
                update={"assistant_message_id": uuid4()}
            ),
        )


def test_refresh_from_historical_version_uses_current_parent_and_fresh_modes(
    postgres_engine,
) -> None:
    apply_pending_migrations(postgres_engine, MIGRATIONS_DIR, through="0032")
    seeded = _seed_source(postgres_engine)
    service = _service(postgres_engine)
    official = service.refresh(
        source_message_id=seeded["source_message_public_id"],
        user_id=seeded["user_id"],
        request=RefreshResponseRequest(
            idempotency_key=uuid4(),
            assistant_message_id=uuid4(),
            source_strategy=ResponseSourceStrategy.REFRESH_OFFICIAL,
        ),
    )
    live = service.refresh(
        source_message_id=seeded["source_message_public_id"],
        user_id=seeded["user_id"],
        request=RefreshResponseRequest(
            idempotency_key=uuid4(),
            assistant_message_id=uuid4(),
            source_strategy=ResponseSourceStrategy.INCLUDE_LIVE,
            style_variant=ResponseStyleVariant.LEGAL_DETAIL,
        ),
    )

    assert official.plan.source_response_version == 1
    assert official.plan.target_response_version == 2
    assert official.plan.reused_source_snapshot_ids == ()
    assert official.plan.refresh_knowledge_modes == ("official",)
    assert live.plan.source_response_version == 1
    assert live.plan.parent_response_version == 2
    assert live.plan.parent_assistant_message_id == (
        official.plan.target_assistant_message_id
    )
    assert live.plan.target_response_version == 3
    assert live.plan.reused_source_snapshot_ids == ()
    assert live.plan.refresh_knowledge_modes == ("official", "live")
    assert live.plan.style_variant is ResponseStyleVariant.LEGAL_DETAIL


def test_concurrent_requests_allocate_one_linear_version_each(
    postgres_engine,
) -> None:
    apply_pending_migrations(postgres_engine, MIGRATIONS_DIR, through="0032")
    seeded = _seed_source(postgres_engine)
    requests = (
        RegenerateResponseRequest(
            idempotency_key=uuid4(),
            assistant_message_id=uuid4(),
        ),
        RegenerateResponseRequest(
            idempotency_key=uuid4(),
            assistant_message_id=uuid4(),
            style_variant=ResponseStyleVariant.BEGINNER,
        ),
    )

    def create(request: RegenerateResponseRequest):
        return _service(postgres_engine).regenerate(
            source_message_id=seeded["source_message_public_id"],
            user_id=seeded["user_id"],
            request=request,
        )

    with ThreadPoolExecutor(max_workers=2) as executor:
        records = tuple(executor.map(create, requests))

    assert {item.plan.target_response_version for item in records} == {2, 3}
    assert {item.plan.parent_response_version for item in records} == {1, 2}
    assert all(item.plan.source_response_version == 1 for item in records)
    with postgres_engine.connect() as connection:
        versions = tuple(
            connection.execute(
                text(
                    """
                    select response_version
                    from public.ask_runs
                    where user_message_id = :user_message_id
                    order by response_version
                    """
                ),
                {"user_message_id": seeded["user_message_id"]},
            ).scalars()
        )
    assert versions == (1, 2, 3)


def test_concurrent_duplicate_request_allocates_exactly_one_version(
    postgres_engine,
) -> None:
    apply_pending_migrations(postgres_engine, MIGRATIONS_DIR, through="0032")
    seeded = _seed_source(postgres_engine)
    request = RegenerateResponseRequest(
        idempotency_key=uuid4(),
        assistant_message_id=uuid4(),
        style_variant=ResponseStyleVariant.BEGINNER,
    )

    def create(_attempt: int):
        return _service(postgres_engine).regenerate(
            source_message_id=seeded["source_message_public_id"],
            user_id=seeded["user_id"],
            request=request,
        )

    with ThreadPoolExecutor(max_workers=2) as executor:
        records = tuple(executor.map(create, (1, 2)))

    assert records[0] == records[1]
    assert records[0].plan.target_response_version == 2
    with postgres_engine.connect() as connection:
        run_count = connection.execute(
            text(
                """
                select count(*)
                from public.ask_runs
                where user_message_id = :user_message_id
                """
            ),
            {"user_message_id": seeded["user_message_id"]},
        ).scalar_one()
        mutation_count = connection.execute(
            text(
                """
                select count(*)
                from public.ask_response_regenerations
                where request_id = :request_id
                """
            ),
            {"request_id": request.idempotency_key},
        ).scalar_one()
    assert run_count == 2
    assert mutation_count == 1


def test_owner_isolation_and_rls_hide_cross_owner_lineage(
    postgres_engine,
) -> None:
    apply_pending_migrations(postgres_engine, MIGRATIONS_DIR, through="0032")
    seeded = _seed_source(postgres_engine)
    other_user_id = uuid4()
    with postgres_engine.begin() as connection:
        insert_auth_user(connection, other_user_id)
    request = RegenerateResponseRequest(
        idempotency_key=uuid4(),
        assistant_message_id=uuid4(),
    )
    service = _service(postgres_engine)
    created = service.regenerate(
        source_message_id=seeded["source_message_public_id"],
        user_id=seeded["user_id"],
        request=request,
    )

    with pytest.raises(ResponseRegenerationNotFound):
        service.regenerate(
            source_message_id=seeded["source_message_public_id"],
            user_id=other_user_id,
            request=RegenerateResponseRequest(
                idempotency_key=uuid4(),
                assistant_message_id=uuid4(),
            ),
        )
    with pytest.raises(ResponseRegenerationConflict):
        service.regenerate(
            source_message_id=seeded["source_message_public_id"],
            user_id=other_user_id,
            request=request,
        )

    with postgres_engine.begin() as connection:
        connection.execute(
            text(
                "select set_config('request.jwt.claim.sub', :user_id, true)"
            ),
            {"user_id": str(seeded["user_id"])},
        )
        connection.execute(text("set local role authenticated"))
        owner_count = connection.execute(
            text(
                """
                select count(*)
                from public.ask_response_regenerations
                where request_id = :request_id
                """
            ),
            {"request_id": created.request_id},
        ).scalar_one()
    with postgres_engine.begin() as connection:
        connection.execute(
            text(
                "select set_config('request.jwt.claim.sub', :user_id, true)"
            ),
            {"user_id": str(other_user_id)},
        )
        connection.execute(text("set local role authenticated"))
        other_count = connection.execute(
            text(
                """
                select count(*)
                from public.ask_response_regenerations
                where request_id = :request_id
                """
            ),
            {"request_id": created.request_id},
        ).scalar_one()

    assert owner_count == 1
    assert other_count == 0
