from __future__ import annotations

import json
from concurrent.futures import ThreadPoolExecutor
from datetime import UTC, datetime, timedelta
from pathlib import Path
from uuid import UUID, uuid4

import pytest
from sqlalchemy import text
from sqlalchemy.engine import Connection, Engine
from sqlalchemy.orm import Session

from backend.ask.orchestration import (
    DURABILITY_POLICY_VERSION,
    DurabilityError,
    DurableEventType,
    DurableRunEvent,
    DurableRunNotFound,
    DurableRunRepository,
    DurableRunStatus,
    LeaseConflict,
    OrchestrationPhase,
    RunEventCursorError,
    StaleExecutionVersion,
    encode_run_event_cursor,
    finalize_orchestration,
    plan_safe_cancellation,
    replay_orchestration,
)
from backend.ask.orchestration.streaming import PostgresRunEventStreamStore
from backend.core.migrations import apply_pending_migrations
from backend.tests.ask_ai_postgres import POSTGRES_MARK, insert_auth_user
from backend.tests.test_ask_ai_orchestration_scheduler import _scope
from backend.tests.test_ask_ai_orchestration_state_machine import (
    RUN_ID,
    _approved_state,
    _complete_state_before_finalization,
    _interpreted_state,
)

pytestmark = POSTGRES_MARK

MIGRATIONS_DIR = Path(__file__).parents[1] / "migrations"
NOW = datetime(2026, 7, 27, 12, 0, tzinfo=UTC)
LEASE_TTL = timedelta(seconds=30)
REPLAY_SESSION_ID = UUID("b03db54e-f96a-4079-aac8-7ca9ae91e0e5")
REPLAY_USER_ID = UUID("64f55e6f-a6e1-46de-b008-fb5f3fd99ff4")


def _seed_run(
    connection: Connection,
    *,
    user_id: UUID,
    state,
) -> tuple[UUID, UUID]:
    session_id = uuid4()
    connection.execute(
        text(
            """
            insert into public.chat_sessions (id, user_id, title)
            values (:session_id, :user_id, 'Durability workspace')
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
              :public_id, :session_id, :user_id, 'user', 'Resume this run.',
              'completed'
            )
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
              content,
              status,
              response_version,
              reply_to_message_id
            )
            values (
              :public_id,
              :session_id,
              :user_id,
              'assistant',
              '',
              'pending',
              1,
              :user_message_id
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
    connection.execute(
        text(
            """
            insert into public.ask_runs (
              id,
              session_id,
              user_id,
              user_message_id,
              assistant_message_id,
              status,
              orchestration_state,
              policy_version
            )
            values (
              :run_id,
              :session_id,
              :user_id,
              :user_message_id,
              :assistant_message_id,
              'pending',
              cast(:state as jsonb),
              :policy_version
            )
            """
        ),
        {
            "run_id": state.run_id,
            "session_id": session_id,
            "user_id": user_id,
            "user_message_id": user_message_id,
            "assistant_message_id": assistant_message_id,
            "state": json.dumps(state.model_dump(mode="json")),
            "policy_version": DURABILITY_POLICY_VERSION,
        },
    )
    return state.run_id, session_id


@pytest.fixture
def durable_run(postgres_engine: Engine) -> tuple[Engine, UUID, UUID, UUID, object]:
    apply_pending_migrations(postgres_engine, MIGRATIONS_DIR, through="0029")
    user_id = uuid4()
    state = _interpreted_state(_scope(("official_sources",)))
    with postgres_engine.begin() as connection:
        insert_auth_user(connection, user_id)
        run_id, session_id = _seed_run(
            connection,
            user_id=user_id,
            state=state,
        )
    return postgres_engine, run_id, session_id, user_id, state


def test_lease_lifecycle_is_durable_idempotent_and_fenced(durable_run) -> None:
    engine, run_id, session_id, user_id, _state = durable_run
    lease_id = uuid4()
    acquire_id = uuid4()
    with Session(engine) as session, session.begin():
        repository = DurableRunRepository(session)
        acquired = repository.acquire_lease(
            run_id=run_id,
            session_id=session_id,
            user_id=user_id,
            lease_id=lease_id,
            event_id=acquire_id,
            now=NOW,
            ttl=LEASE_TTL,
        )
        retried = repository.acquire_lease(
            run_id=run_id,
            session_id=session_id,
            user_id=user_id,
            lease_id=lease_id,
            event_id=acquire_id,
            now=NOW + timedelta(seconds=1),
            ttl=LEASE_TTL,
        )
        assert retried == acquired
        with pytest.raises(LeaseConflict):
            repository.acquire_lease(
                run_id=run_id,
                session_id=session_id,
                user_id=user_id,
                lease_id=uuid4(),
                event_id=uuid4(),
                now=NOW + timedelta(seconds=1),
                ttl=LEASE_TTL,
            )
        renewed = repository.renew_lease(
            run_id=run_id,
            session_id=session_id,
            user_id=user_id,
            lease_id=lease_id,
            event_id=uuid4(),
            expected_version=1,
            now=NOW + timedelta(seconds=2),
            ttl=LEASE_TTL,
        )
        released = repository.release_lease(
            run_id=run_id,
            session_id=session_id,
            user_id=user_id,
            lease_id=lease_id,
            event_id=uuid4(),
            expected_version=2,
            now=NOW + timedelta(seconds=3),
        )
        snapshot = repository.load_snapshot(
            run_id=run_id,
            session_id=session_id,
            user_id=user_id,
        )

    assert acquired.sequence == 0
    assert renewed.event_type is DurableEventType.LEASE_RENEWED
    assert released.execution_version == 3
    assert snapshot.execution_version == 3
    assert snapshot.next_event_sequence == 3
    assert snapshot.lease is None


def test_expired_lease_can_be_replaced_but_old_worker_cannot_release_it(
    durable_run,
) -> None:
    engine, run_id, session_id, user_id, _state = durable_run
    old_lease = uuid4()
    new_lease = uuid4()
    with Session(engine) as session, session.begin():
        repository = DurableRunRepository(session)
        repository.acquire_lease(
            run_id=run_id,
            session_id=session_id,
            user_id=user_id,
            lease_id=old_lease,
            event_id=uuid4(),
            now=NOW,
            ttl=timedelta(seconds=1),
        )
        replacement = repository.acquire_lease(
            run_id=run_id,
            session_id=session_id,
            user_id=user_id,
            lease_id=new_lease,
            event_id=uuid4(),
            now=NOW + timedelta(seconds=2),
            ttl=LEASE_TTL,
        )
        with pytest.raises(LeaseConflict):
            repository.release_lease(
                run_id=run_id,
                session_id=session_id,
                user_id=user_id,
                lease_id=old_lease,
                event_id=uuid4(),
                expected_version=2,
                now=NOW + timedelta(seconds=3),
            )

    assert replacement.execution_version == 2


def test_state_append_replay_and_cancellation_fence_stale_worker(
    durable_run,
) -> None:
    engine, run_id, session_id, user_id, state = durable_run
    lease_id = uuid4()
    state_event_id = uuid4()
    request_id = uuid4()
    with Session(engine) as session, session.begin():
        repository = DurableRunRepository(session)
        repository.acquire_lease(
            run_id=run_id,
            session_id=session_id,
            user_id=user_id,
            lease_id=lease_id,
            event_id=uuid4(),
            now=NOW,
            ttl=LEASE_TTL,
        )
        appended = repository.append_state_transition(
            run_id=run_id,
            session_id=session_id,
            user_id=user_id,
            lease_id=lease_id,
            event_id=state_event_id,
            expected_version=1,
            state=state,
            now=NOW + timedelta(seconds=1),
        )
        assert (
            repository.append_state_transition(
                run_id=run_id,
                session_id=session_id,
                user_id=user_id,
                lease_id=lease_id,
                event_id=state_event_id,
                expected_version=1,
                state=state,
                now=NOW + timedelta(seconds=2),
            )
            == appended
        )
        cancellation = repository.request_cancellation(
            run_id=run_id,
            session_id=session_id,
            user_id=user_id,
            request_id=request_id,
            now=NOW + timedelta(seconds=2),
            reason_code="USER_REQUESTED",
        )
        with pytest.raises(StaleExecutionVersion):
            repository.append_state_transition(
                run_id=run_id,
                session_id=session_id,
                user_id=user_id,
                lease_id=lease_id,
                event_id=uuid4(),
                expected_version=2,
                state=state,
                now=NOW + timedelta(seconds=3),
            )
        applied = repository.apply_cancellation(
            run_id=run_id,
            session_id=session_id,
            user_id=user_id,
            lease_id=lease_id,
            request_id=request_id,
            event_id=uuid4(),
            expected_version=3,
            state=state,
            now=NOW + timedelta(seconds=3),
        )

    with Session(engine) as session:
        repository = DurableRunRepository(session)
        events = repository.load_events(
            run_id=run_id,
            session_id=session_id,
            user_id=user_id,
        )
        tail = repository.load_events(
            run_id=run_id,
            session_id=session_id,
            user_id=user_id,
            after_sequence=1,
        )
        snapshot = repository.load_snapshot(
            run_id=run_id,
            session_id=session_id,
            user_id=user_id,
        )
        with pytest.raises(DurabilityError, match="Terminal"):
            repository.acquire_lease(
                run_id=run_id,
                session_id=session_id,
                user_id=user_id,
                lease_id=uuid4(),
                event_id=uuid4(),
                now=NOW + timedelta(seconds=4),
                ttl=LEASE_TTL,
            )

    assert cancellation.event_type is DurableEventType.CANCELLATION_REQUESTED
    assert applied.event_type is DurableEventType.CANCELLATION_APPLIED
    assert replay_orchestration(events) == state
    assert tail == (cancellation, applied)
    assert snapshot.cancellation is not None
    assert snapshot.cancellation.request_id == request_id
    assert snapshot.status is DurableRunStatus.CANCELLED
    assert snapshot.lease is None
    assert snapshot.execution_version == 4


def test_event_identifier_reuse_requires_the_same_action(durable_run) -> None:
    engine, run_id, session_id, user_id, _state = durable_run
    event_id = uuid4()
    with Session(engine) as session, session.begin():
        repository = DurableRunRepository(session)
        repository.acquire_lease(
            run_id=run_id,
            session_id=session_id,
            user_id=user_id,
            lease_id=uuid4(),
            event_id=event_id,
            now=NOW,
            ttl=LEASE_TTL,
        )
        with pytest.raises(DurabilityError):
            repository.request_cancellation(
                run_id=run_id,
                session_id=session_id,
                user_id=user_id,
                request_id=event_id,
                now=NOW,
            )


def test_owner_scope_hides_durable_run_and_events(durable_run) -> None:
    engine, run_id, session_id, user_id, _state = durable_run
    with Session(engine) as session:
        repository = DurableRunRepository(session)
        with pytest.raises(DurableRunNotFound):
            repository.load_snapshot(
                run_id=run_id,
                session_id=session_id,
                user_id=uuid4(),
            )
        assert (
            repository.load_events(
                run_id=run_id,
                session_id=session_id,
                user_id=uuid4(),
            )
            == ()
        )


def test_database_rls_hides_durability_rows_from_non_owner(durable_run) -> None:
    engine, run_id, session_id, user_id, _state = durable_run
    with Session(engine) as session, session.begin():
        DurableRunRepository(session).acquire_lease(
            run_id=run_id,
            session_id=session_id,
            user_id=user_id,
            lease_id=uuid4(),
            event_id=uuid4(),
            now=NOW,
            ttl=LEASE_TTL,
        )

    for principal_id, expected_count in ((user_id, 1), (uuid4(), 0)):
        with engine.begin() as connection:
            connection.execute(text("set local role authenticated"))
            connection.execute(
                text(
                    "select set_config("
                    "'request.jwt.claim.sub', :user_id, true"
                    ")"
                ),
                {"user_id": str(principal_id)},
            )
            assert connection.execute(
                text(
                    "select count(*) from public.ask_runs "
                    "where id = :run_id"
                ),
                {"run_id": run_id},
            ).scalar_one() == expected_count
            assert connection.execute(
                text(
                    "select count(*) from public.ask_run_events "
                    "where run_id = :run_id"
                ),
                {"run_id": run_id},
            ).scalar_one() == expected_count


def test_concurrent_appends_allocate_one_version_and_fence_the_loser(
    durable_run,
) -> None:
    engine, run_id, session_id, user_id, state = durable_run
    lease_id = uuid4()
    with Session(engine) as session, session.begin():
        DurableRunRepository(session).acquire_lease(
            run_id=run_id,
            session_id=session_id,
            user_id=user_id,
            lease_id=lease_id,
            event_id=uuid4(),
            now=NOW,
            ttl=LEASE_TTL,
        )

    def append_once(event_id: UUID) -> str:
        try:
            with Session(engine) as session, session.begin():
                DurableRunRepository(session).append_state_transition(
                    run_id=run_id,
                    session_id=session_id,
                    user_id=user_id,
                    lease_id=lease_id,
                    event_id=event_id,
                    expected_version=1,
                    state=state,
                    now=NOW + timedelta(seconds=1),
                )
            return "appended"
        except StaleExecutionVersion:
            return "stale"

    with ThreadPoolExecutor(max_workers=2) as executor:
        outcomes = tuple(executor.map(append_once, (uuid4(), uuid4())))

    with Session(engine) as session:
        events = DurableRunRepository(session).load_events(
            run_id=run_id,
            session_id=session_id,
            user_id=user_id,
        )
    assert sorted(outcomes) == ["appended", "stale"]
    assert [(event.sequence, event.execution_version) for event in events] == [
        (0, 1),
        (1, 2),
    ]


def test_event_pages_are_bounded_resumable_and_owner_neutral(durable_run) -> None:
    engine, run_id, session_id, user_id, state = durable_run
    lease_id = uuid4()
    with Session(engine) as session, session.begin():
        repository = DurableRunRepository(session)
        repository.acquire_lease(
            run_id=run_id,
            session_id=session_id,
            user_id=user_id,
            lease_id=lease_id,
            event_id=uuid4(),
            now=NOW,
            ttl=LEASE_TTL,
        )
        repository.append_state_transition(
            run_id=run_id,
            session_id=session_id,
            user_id=user_id,
            lease_id=lease_id,
            event_id=uuid4(),
            expected_version=1,
            state=state,
            now=NOW + timedelta(seconds=1),
        )
        repository.release_lease(
            run_id=run_id,
            session_id=session_id,
            user_id=user_id,
            lease_id=lease_id,
            event_id=uuid4(),
            expected_version=2,
            now=NOW + timedelta(seconds=2),
        )

    with Session(engine) as session:
        repository = DurableRunRepository(session)
        first = repository.load_event_page(
            run_id=run_id,
            session_id=session_id,
            user_id=user_id,
            limit=2,
        )
        second = repository.load_event_page(
            run_id=run_id,
            session_id=session_id,
            user_id=user_id,
            cursor=first.resume_cursor,
            limit=2,
        )
        idle = repository.load_event_page(
            run_id=run_id,
            session_id=session_id,
            user_id=user_id,
            cursor=second.resume_cursor,
            limit=2,
        )

    assert [item.sequence for item in first.items] == [0, 1]
    assert first.has_more is True
    assert [item.sequence for item in second.items] == [2]
    assert second.has_more is False
    assert idle.items == ()
    assert idle.resume_cursor == second.resume_cursor
    assert first.snapshot_execution_version == 3
    assert second.snapshot_next_sequence == 3
    assert first.items[1].orchestration_state == state
    assert "user_id" not in first.items[0].model_dump(mode="json")
    assert "session_id" not in first.items[0].model_dump(mode="json")


def test_stream_store_resolves_owner_and_reads_exact_resume(
    durable_run,
) -> None:
    engine, run_id, session_id, user_id, _state = durable_run
    with Session(engine) as session, session.begin():
        repository = DurableRunRepository(session)
        repository.acquire_lease(
            run_id=run_id,
            session_id=session_id,
            user_id=user_id,
            lease_id=uuid4(),
            event_id=uuid4(),
            now=NOW,
            ttl=LEASE_TTL,
        )

    store = PostgresRunEventStreamStore(
        session_scope_factory=lambda: Session(engine),
    )
    assert store.resolve_owned_session(
        run_id=run_id,
        user_id=user_id,
    ) == session_id
    assert (
        store.resolve_owned_session(
            run_id=run_id,
            user_id=uuid4(),
        )
        is None
    )

    first = store.read_batch(
        run_id=run_id,
        session_id=session_id,
        user_id=user_id,
        cursor=None,
        limit=1,
    )
    resumed = store.read_batch(
        run_id=run_id,
        session_id=session_id,
        user_id=user_id,
        cursor=first.page.resume_cursor,
        limit=1,
    )

    assert [item.sequence for item in first.page.items] == [0]
    assert resumed.page.items == ()
    assert resumed.page.resume_cursor == first.page.resume_cursor
    assert first.run_status is DurableRunStatus.RUNNING

    with engine.begin() as connection:
        connection.execute(
            text(
                """
                update public.chat_sessions
                set deleted_at = :deleted_at
                where id = :session_id
                  and user_id = :user_id
                """
            ),
            {
                "deleted_at": NOW,
                "session_id": session_id,
                "user_id": user_id,
            },
        )
    assert (
        store.resolve_owned_session(
            run_id=run_id,
            user_id=user_id,
        )
        is None
    )


def test_event_page_refuses_crossed_owner_cursor_and_persisted_gap(
    durable_run,
) -> None:
    engine, run_id, session_id, user_id, _state = durable_run
    with Session(engine) as session, session.begin():
        repository = DurableRunRepository(session)
        repository.acquire_lease(
            run_id=run_id,
            session_id=session_id,
            user_id=user_id,
            lease_id=uuid4(),
            event_id=uuid4(),
            now=NOW,
            ttl=LEASE_TTL,
        )
        page = repository.load_event_page(
            run_id=run_id,
            session_id=session_id,
            user_id=user_id,
            limit=1,
        )
        assert page.resume_cursor is not None

        with pytest.raises(DurableRunNotFound):
            repository.load_event_page(
                run_id=run_id,
                session_id=session_id,
                user_id=uuid4(),
                cursor=page.resume_cursor,
            )

        crossed = page.items[0].model_copy(update={"event_id": uuid4()})

        with pytest.raises(RunEventCursorError, match="persisted history"):
            repository.load_event_page(
                run_id=run_id,
                session_id=session_id,
                user_id=user_id,
                cursor=encode_run_event_cursor(crossed),
            )

        session.execute(
            text(
                """
                update public.ask_run_events
                set sequence = 4
                where run_id = :run_id
                  and sequence = 0
                """
            ),
            {"run_id": run_id},
        )
        with pytest.raises(DurabilityError, match="sequence gap"):
            repository.load_event_page(
                run_id=run_id,
                session_id=session_id,
                user_id=user_id,
            )


def test_safe_cancellation_preserves_admitted_and_verified_work() -> None:
    scope = _scope(("official_sources",))
    active_state = _approved_state(scope)
    completed_state = _complete_state_before_finalization(scope)

    active_plan = plan_safe_cancellation(active_state)
    completed_plan = plan_safe_cancellation(completed_state)

    assert active_plan.queued_node_ids
    assert set(active_plan.preserved_artifact_ids) == {
        artifact.artifact_id for artifact in active_state.admitted_artifacts
    }
    assert completed_plan.preserved_terminal_section_ids == ("section-1",)
    assert completed_plan.nonterminal_section_ids == ()
    assert completed_plan.withheld_claim_ids == ()


@pytest.mark.parametrize("phase", tuple(OrchestrationPhase))
def test_cancellation_plan_is_safe_and_stable_in_every_phase(
    phase: OrchestrationPhase,
) -> None:
    scope = _scope(("official_sources",))
    state = (
        _interpreted_state(scope)
        if phase
        in {
            OrchestrationPhase.REQUEST_SCOPE,
            OrchestrationPhase.INTERPRETATION,
        }
        else _approved_state(scope)
    ).model_copy(update={"phase": phase})
    before = state.model_dump(mode="json")

    plan = plan_safe_cancellation(state)

    assert state.model_dump(mode="json") == before
    assert plan.active_node_ids == ()
    assert set(plan.preserved_artifact_ids) == {
        artifact.artifact_id for artifact in state.admitted_artifacts
    }


def test_replay_rejects_regression_and_terminal_mutation() -> None:
    state = _interpreted_state(_scope(("official_sources",)))
    regressed = state.model_copy(
        update={"phase": OrchestrationPhase.REQUEST_SCOPE},
    )
    first = _state_event(state, sequence=0, execution_version=1)
    second = _state_event(regressed, sequence=1, execution_version=2)

    with pytest.raises(DurabilityError, match="regress"):
        replay_orchestration((first, second))

    terminal = finalize_orchestration(
        _complete_state_before_finalization(_scope(("official_sources",)))
    )
    mutated = terminal.model_copy(
        update={"policy_version": "mutated-policy"},
    )
    with pytest.raises(DurabilityError, match="terminal"):
        replay_orchestration(
            (
                _state_event(terminal, sequence=0, execution_version=1),
                _state_event(mutated, sequence=1, execution_version=2),
            )
        )


def _state_event(
    state,
    *,
    sequence: int,
    execution_version: int,
) -> DurableRunEvent:
    return DurableRunEvent(
        public_id=uuid4(),
        run_id=RUN_ID,
        session_id=REPLAY_SESSION_ID,
        user_id=REPLAY_USER_ID,
        sequence=sequence,
        execution_version=execution_version,
        event_type=DurableEventType.STATE_TRANSITION,
        status=DurableRunStatus.RUNNING,
        payload={"orchestration_state": state.model_dump(mode="json")},
        created_at=NOW,
    )
