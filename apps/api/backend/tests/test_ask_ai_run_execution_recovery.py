from __future__ import annotations

import asyncio
from datetime import UTC, datetime, timedelta
from pathlib import Path
from uuid import UUID, uuid4

import pytest
from sqlalchemy.engine import Engine
from sqlalchemy.orm import Session, sessionmaker

from backend.ask.orchestration import (
    CapabilityTerminalState,
    DurableEventType,
    DurableRunExecutionCoordinator,
    DurableRunExecutionStore,
    DurableRunNotFound,
    DurableRunRepository,
    DurableRunStatus,
    OrchestratorCapability,
    ProvenanceClass,
    RunExecutionError,
    RunExecutionInterrupted,
    RunExecutionOutcome,
    StaleRunExecution,
    activate_capability,
    finalize_orchestration,
    replay_orchestration,
)
from backend.core.migrations import apply_pending_migrations
from backend.tests.ask_ai_postgres import POSTGRES_MARK, insert_auth_user
from backend.tests.test_ask_ai_orchestration_durability import _seed_run
from backend.tests.test_ask_ai_orchestration_scheduler import (
    _fanout_state,
    _NodeSpec,
    _RequestFactory,
    _scope,
)
from backend.tests.test_ask_ai_orchestration_state_machine import (
    _complete_state_before_finalization,
)

pytestmark = POSTGRES_MARK

MIGRATIONS_DIR = Path(__file__).parents[1] / "migrations"
NOW = datetime(2026, 7, 27, 12, 0, tzinfo=UTC)
LEASE_TTL = timedelta(seconds=30)


class _Clock:
    def __init__(self, value: datetime) -> None:
        self.value = value

    def __call__(self) -> datetime:
        return self.value

    def advance(self, delta: timedelta) -> None:
        self.value += delta


class _FinalizingDriver:
    async def advance(self, state):
        return finalize_orchestration(state)


class _CrashingDriver:
    async def advance(self, state):
        raise RuntimeError("simulated process interruption")


class _BlockingFinalizingDriver:
    def __init__(self) -> None:
        self.started = asyncio.Event()
        self.release = asyncio.Event()

    async def advance(self, state):
        self.started.set()
        await self.release.wait()
        return finalize_orchestration(state)


class _CrossPlanDriver:
    async def advance(self, state):
        return state.model_copy(update={"plan_id": "crossed-plan"})


class _AppendBarrierStore(DurableRunExecutionStore):
    def __init__(self, session_factory) -> None:
        super().__init__(session_factory)
        self.append_started = asyncio.Event()
        self.release_append = asyncio.Event()

    async def append_state_transition(self, **kwargs):
        self.append_started.set()
        await self.release_append.wait()
        return await super().append_state_transition(**kwargs)


class _InspectingCrashDriver:
    def __init__(self) -> None:
        self.state = None

    async def advance(self, state):
        self.state = state
        raise RuntimeError("stop after recovery inspection")


@pytest.fixture
def recovery_run(
    postgres_engine: Engine,
) -> tuple[Engine, UUID, UUID, UUID]:
    apply_pending_migrations(postgres_engine, MIGRATIONS_DIR, through="0029")
    user_id = uuid4()
    state = _complete_state_before_finalization(
        _scope(("official_sources",))
    )
    with postgres_engine.begin() as connection:
        insert_auth_user(connection, user_id)
        run_id, session_id = _seed_run(
            connection,
            user_id=user_id,
            state=state,
        )
    return postgres_engine, run_id, session_id, user_id


def _store(engine: Engine) -> DurableRunExecutionStore:
    factory = sessionmaker(bind=engine, expire_on_commit=False)
    return DurableRunExecutionStore(factory)


def test_interrupted_run_is_taken_over_after_expiry_and_reaches_terminal(
    recovery_run,
) -> None:
    engine, run_id, session_id, user_id = recovery_run
    clock = _Clock(NOW)
    store = _store(engine)
    first = DurableRunExecutionCoordinator(
        store=store,
        driver=_CrashingDriver(),
        clock=clock,
    )

    with pytest.raises(RunExecutionInterrupted, match="interrupted"):
        asyncio.run(
            first.execute(
                run_id=run_id,
                session_id=session_id,
                user_id=user_id,
                lease_ttl=LEASE_TTL,
            )
        )

    with Session(engine) as session:
        interrupted = DurableRunRepository(session).load_snapshot(
            run_id=run_id,
            session_id=session_id,
            user_id=user_id,
        )
    assert interrupted.status is DurableRunStatus.RUNNING
    assert interrupted.lease is not None

    clock.advance(LEASE_TTL + timedelta(seconds=1))
    recovered = asyncio.run(
        DurableRunExecutionCoordinator(
            store=store,
            driver=_FinalizingDriver(),
            clock=clock,
        ).execute(
            run_id=run_id,
            session_id=session_id,
            user_id=user_id,
            lease_ttl=LEASE_TTL,
        )
    )

    assert recovered.outcome is RunExecutionOutcome.COMPLETED
    assert recovered.accepted_steps == 1
    assert recovered.snapshot.status is DurableRunStatus.COMPLETED
    assert recovered.snapshot.lease is None
    assert recovered.snapshot.orchestration_state.terminal_state is not None

    duplicate = asyncio.run(
        DurableRunExecutionCoordinator(
            store=store,
            driver=_CrashingDriver(),
            clock=clock,
        ).execute(
            run_id=run_id,
            session_id=session_id,
            user_id=user_id,
            lease_ttl=LEASE_TTL,
        )
    )
    assert duplicate.outcome is RunExecutionOutcome.ALREADY_TERMINAL
    assert duplicate.accepted_steps == 0

    with Session(engine) as session:
        events = DurableRunRepository(session).load_events(
            run_id=run_id,
            session_id=session_id,
            user_id=user_id,
        )
    assert [event.event_type for event in events] == [
        DurableEventType.LEASE_ACQUIRED,
        DurableEventType.LEASE_ACQUIRED,
        DurableEventType.STATE_TRANSITION,
    ]
    assert replay_orchestration(events) == recovered.snapshot.orchestration_state


def test_expired_worker_result_is_fenced_after_takeover(recovery_run) -> None:
    engine, run_id, session_id, user_id = recovery_run

    async def scenario() -> None:
        clock = _Clock(NOW)
        store = _store(engine)
        blocked_driver = _BlockingFinalizingDriver()
        stale_task = asyncio.create_task(
            DurableRunExecutionCoordinator(
                store=store,
                driver=blocked_driver,
                clock=clock,
            ).execute(
                run_id=run_id,
                session_id=session_id,
                user_id=user_id,
                lease_ttl=LEASE_TTL,
            )
        )
        await blocked_driver.started.wait()
        clock.advance(LEASE_TTL + timedelta(seconds=1))
        winner = await DurableRunExecutionCoordinator(
            store=store,
            driver=_FinalizingDriver(),
            clock=clock,
        ).execute(
            run_id=run_id,
            session_id=session_id,
            user_id=user_id,
            lease_ttl=LEASE_TTL,
        )
        blocked_driver.release.set()
        with pytest.raises(StaleRunExecution, match="lease"):
            await stale_task
        assert winner.snapshot.status is DurableRunStatus.COMPLETED

    asyncio.run(scenario())


def test_cancellation_request_wins_over_late_driver_result(recovery_run) -> None:
    engine, run_id, session_id, user_id = recovery_run

    async def scenario() -> None:
        clock = _Clock(NOW)
        store = _store(engine)
        driver = _BlockingFinalizingDriver()
        task = asyncio.create_task(
            DurableRunExecutionCoordinator(
                store=store,
                driver=driver,
                clock=clock,
            ).execute(
                run_id=run_id,
                session_id=session_id,
                user_id=user_id,
                lease_ttl=LEASE_TTL,
            )
        )
        await driver.started.wait()

        def request_cancellation() -> None:
            with Session(engine) as session, session.begin():
                DurableRunRepository(session).request_cancellation(
                    run_id=run_id,
                    session_id=session_id,
                    user_id=user_id,
                    request_id=uuid4(),
                    now=clock(),
                    reason_code="USER_REQUESTED",
                )

        await asyncio.to_thread(request_cancellation)
        driver.release.set()
        result = await task

        assert result.outcome is RunExecutionOutcome.CANCELLED
        assert result.accepted_steps == 0
        assert result.snapshot.status is DurableRunStatus.PARTIAL
        assert result.snapshot.lease is None
        assert result.snapshot.orchestration_state.terminal_state is None

    asyncio.run(scenario())


def test_cancellation_in_final_append_window_is_applied_immediately(
    recovery_run,
) -> None:
    engine, run_id, session_id, user_id = recovery_run

    async def scenario() -> None:
        clock = _Clock(NOW)
        factory = sessionmaker(bind=engine, expire_on_commit=False)
        store = _AppendBarrierStore(factory)
        task = asyncio.create_task(
            DurableRunExecutionCoordinator(
                store=store,
                driver=_FinalizingDriver(),
                clock=clock,
            ).execute(
                run_id=run_id,
                session_id=session_id,
                user_id=user_id,
                lease_ttl=LEASE_TTL,
            )
        )
        await store.append_started.wait()

        def request_cancellation() -> None:
            with Session(engine) as session, session.begin():
                DurableRunRepository(session).request_cancellation(
                    run_id=run_id,
                    session_id=session_id,
                    user_id=user_id,
                    request_id=uuid4(),
                    now=clock(),
                    reason_code="USER_REQUESTED",
                )

        await asyncio.to_thread(request_cancellation)
        store.release_append.set()
        result = await task

        assert result.outcome is RunExecutionOutcome.CANCELLED
        assert result.snapshot.status is DurableRunStatus.PARTIAL
        assert result.snapshot.lease is None

    asyncio.run(scenario())


def test_regressive_driver_state_is_never_persisted(recovery_run) -> None:
    engine, run_id, session_id, user_id = recovery_run

    with pytest.raises(RunExecutionError, match="regressive"):
        asyncio.run(
            DurableRunExecutionCoordinator(
                store=_store(engine),
                driver=_CrossPlanDriver(),
                clock=_Clock(NOW),
            ).execute(
                run_id=run_id,
                session_id=session_id,
                user_id=user_id,
                lease_ttl=LEASE_TTL,
            )
        )

    with Session(engine) as session:
        snapshot = DurableRunRepository(session).load_snapshot(
            run_id=run_id,
            session_id=session_id,
            user_id=user_id,
        )
        events = DurableRunRepository(session).load_events(
            run_id=run_id,
            session_id=session_id,
            user_id=user_id,
        )
    assert snapshot.orchestration_state.plan_id != "crossed-plan"
    assert [event.event_type for event in events] == [
        DurableEventType.LEASE_ACQUIRED
    ]


def test_execution_store_preserves_owner_non_disclosure(recovery_run) -> None:
    engine, run_id, session_id, _user_id = recovery_run

    with pytest.raises(DurableRunNotFound):
        asyncio.run(
            DurableRunExecutionCoordinator(
                store=_store(engine),
                driver=_FinalizingDriver(),
                clock=_Clock(NOW),
            ).execute(
                run_id=run_id,
                session_id=session_id,
                user_id=uuid4(),
                lease_ttl=LEASE_TTL,
            )
        )


def test_persisted_active_capability_is_recovered_before_reexecution(
    postgres_engine: Engine,
) -> None:
    apply_pending_migrations(postgres_engine, MIGRATIONS_DIR, through="0029")
    user_id = uuid4()
    state = _fanout_state(
        (
            _NodeSpec(
                node_id="regulatory-retriever:question-1",
                capability=OrchestratorCapability.REGULATORY_RETRIEVER,
                section_key="overview",
                provenance_class=ProvenanceClass.INTERNAL_REGULATORY_CORPUS,
            ),
        )
    )
    node = next(
        item
        for item in state.capabilities
        if item.node_id == "regulatory-retriever:question-1"
    )
    active = activate_capability(state, node.node_id, _RequestFactory()(state, node))
    with postgres_engine.begin() as connection:
        insert_auth_user(connection, user_id)
        run_id, session_id = _seed_run(
            connection,
            user_id=user_id,
            state=active,
        )
    driver = _InspectingCrashDriver()

    with pytest.raises(RunExecutionInterrupted):
        asyncio.run(
            DurableRunExecutionCoordinator(
                store=_store(postgres_engine),
                driver=driver,
                clock=_Clock(NOW),
            ).execute(
                run_id=run_id,
                session_id=session_id,
                user_id=user_id,
                lease_ttl=LEASE_TTL,
            )
        )

    assert driver.state is not None
    recovered_node = next(
        item
        for item in driver.state.capabilities
        if item.node_id == node.node_id
    )
    assert recovered_node.state is CapabilityTerminalState.UNAVAILABLE
    assert recovered_node.result is not None
    assert (
        recovered_node.result.safe_error_code
        == "CAPABILITY_EXECUTION_INTERRUPTED"
    )
    with Session(postgres_engine) as session:
        snapshot = DurableRunRepository(session).load_snapshot(
            run_id=run_id,
            session_id=session_id,
            user_id=user_id,
        )
    assert snapshot.orchestration_state == driver.state
