from __future__ import annotations

import asyncio
from datetime import UTC, datetime, timedelta
from uuid import UUID, uuid4

import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient
from pydantic import ValidationError

from backend.api.auth import CurrentUser, current_user
from backend.api.routes import chat_runs
from backend.ask.orchestration.contracts import (
    CapabilityResult,
    CapabilityTerminalState,
    CapabilityTiming,
    OrchestratorCapability,
    ProvenanceClass,
)
from backend.ask.orchestration.durability import (
    CancellationRequest,
    DurableRunSnapshot,
    DurableRunStatus,
)
from backend.ask.orchestration.retry import (
    CAPABILITY_RETRY_SAFE_ERROR_CODE,
    CapabilityRetryClaim,
    CapabilityRetryConflict,
    CapabilityRetryNotEligible,
    CapabilityRetryPlan,
    CapabilityRetryRecord,
    CapabilityRetryRequestBody,
    CapabilityRetryResponse,
    CapabilityRetryService,
    CapabilityRetryStale,
    CapabilityRetryStatus,
    plan_capability_retry,
)
from backend.ask.orchestration.state_machine import (
    FAILURE_TERMINAL_STATES,
    OrchestrationState,
)
from backend.core.config import settings
from backend.tests.test_ask_ai_orchestration_failure_policy import (
    _fallback_state,
    _terminalize,
)
from backend.tests.test_ask_ai_orchestration_scheduler import (
    _fanout_state,
    _NodeSpec,
    _scope,
)
from backend.tests.test_ask_ai_orchestration_state_machine import (
    CLAIM_VERIFIER_NODE,
    _complete_state_before_finalization,
)

NOW = datetime(2026, 7, 27, 12, 0, tzinfo=UTC)
SESSION_ID = UUID("11111111-1111-4111-8111-111111111111")
USER_ID = UUID("22222222-2222-4222-8222-222222222222")
RETRY_ID = UUID("33333333-3333-4333-8333-333333333333")
NODE_ID = "regulatory:official"


def _snapshot(
    terminal_state: CapabilityTerminalState = (
        CapabilityTerminalState.UNAVAILABLE
    ),
) -> DurableRunSnapshot:
    state = _terminalize(
        _fallback_state(),
        NODE_ID,
        terminal_state,
    )
    return DurableRunSnapshot(
        run_id=state.run_id,
        session_id=SESSION_ID,
        user_id=USER_ID,
        status=DurableRunStatus.PARTIAL,
        execution_version=7,
        next_event_sequence=7,
        orchestration_state=state,
    )


def _snapshot_for_capability(
    capability: OrchestratorCapability,
) -> tuple[DurableRunSnapshot, str]:
    if capability is OrchestratorCapability.REGULATORY_RETRIEVER:
        return _snapshot(), NODE_ID
    if capability is OrchestratorCapability.CITATION_VERIFIER:
        state = _complete_state_before_finalization(
            _scope(("official_sources",))
        )
        values = state.model_dump(mode="python")
        nodes = []
        for node in state.capabilities:
            if node.node_id != CLAIM_VERIFIER_NODE:
                nodes.append(node)
                continue
            assert node.request is not None
            result = CapabilityResult(
                request_id=node.request.request_id,
                run_id=node.request.run_id,
                capability=node.request.capability,
                terminal_state=CapabilityTerminalState.UNAVAILABLE,
                scope_echo=node.request.scope,
                timing=CapabilityTiming(
                    started_at=NOW,
                    completed_at=NOW,
                    duration_ms=0,
                ),
                safe_error_code="TEST_TRANSIENT_FAILURE",
            )
            nodes.append(
                node.model_copy(
                    update={
                        "state": CapabilityTerminalState.UNAVAILABLE,
                        "result": result,
                    }
                )
            )
        values["capabilities"] = tuple(nodes)
        failed = OrchestrationState.model_validate(values)
        return (
            DurableRunSnapshot(
                run_id=failed.run_id,
                session_id=SESSION_ID,
                user_id=USER_ID,
                status=DurableRunStatus.PARTIAL,
                execution_version=7,
                next_event_sequence=7,
                orchestration_state=failed,
            ),
            CLAIM_VERIFIER_NODE,
        )
    provenance = (
        ProvenanceClass.LIVE_WEB_SOURCES
        if capability is OrchestratorCapability.NEWS_RETRIEVER
        else ProvenanceClass.GENERAL_AI_KNOWLEDGE
    )
    node_id = f"{capability.value}:question-1"
    state = _terminalize(
        _fanout_state(
            (
                _NodeSpec(
                    node_id=node_id,
                    capability=capability,
                    section_key=capability.value,
                    provenance_class=provenance,
                ),
            )
        ),
        node_id,
        CapabilityTerminalState.UNAVAILABLE,
    )
    return (
        DurableRunSnapshot(
            run_id=state.run_id,
            session_id=SESSION_ID,
            user_id=USER_ID,
            status=DurableRunStatus.PARTIAL,
            execution_version=7,
            next_event_sequence=7,
            orchestration_state=state,
        ),
        node_id,
    )


def _record(
    plan: CapabilityRetryPlan,
    *,
    status: CapabilityRetryStatus = CapabilityRetryStatus.PENDING,
    result: CapabilityResult | None = None,
    safe_error_code: str | None = None,
    lease_id: UUID | None = None,
    lease_expires_at: datetime | None = None,
) -> CapabilityRetryRecord:
    completed = (
        NOW
        if status
        in {CapabilityRetryStatus.SUCCEEDED, CapabilityRetryStatus.FAILED}
        else None
    )
    return CapabilityRetryRecord(
        retry_id=plan.retry_id,
        run_id=plan.run_id,
        session_id=SESSION_ID,
        user_id=USER_ID,
        plan=plan,
        status=status,
        result=result,
        safe_error_code=safe_error_code,
        lease_id=lease_id,
        lease_expires_at=lease_expires_at,
        created_at=NOW,
        updated_at=NOW,
        completed_at=completed,
    )


class MemoryRetryStore:
    def __init__(self, snapshot: DurableRunSnapshot | None) -> None:
        self.snapshot = snapshot
        self.records: dict[UUID, CapabilityRetryRecord] = {}
        self.original_retry_id: UUID | None = None

    async def load_owned_snapshot(
        self,
        *,
        run_id: UUID,
        user_id: UUID,
    ) -> DurableRunSnapshot | None:
        if (
            self.snapshot is None
            or self.snapshot.run_id != run_id
            or self.snapshot.user_id != user_id
        ):
            return None
        return self.snapshot

    async def create(
        self,
        *,
        snapshot: DurableRunSnapshot,
        plan: CapabilityRetryPlan,
        now: datetime,
    ) -> CapabilityRetryRecord:
        del snapshot, now
        if self.original_retry_id is not None:
            existing = self.records[self.original_retry_id]
            if existing.retry_id != plan.retry_id:
                raise CapabilityRetryConflict("bounded retry already exists")
            if existing.plan != plan:
                raise CapabilityRetryConflict("idempotency mismatch")
            return existing
        record = _record(plan)
        self.records[plan.retry_id] = record
        self.original_retry_id = plan.retry_id
        return record

    async def claim(
        self,
        *,
        retry_id: UUID,
        user_id: UUID,
        lease_id: UUID,
        now: datetime,
        ttl: timedelta,
    ) -> CapabilityRetryClaim:
        record = self.records[retry_id]
        assert record.user_id == user_id
        if record.status in {
            CapabilityRetryStatus.SUCCEEDED,
            CapabilityRetryStatus.FAILED,
        }:
            return CapabilityRetryClaim(record=record, acquired=False)
        if (
            record.status is CapabilityRetryStatus.RUNNING
            and record.lease_expires_at is not None
            and record.lease_expires_at > now
        ):
            return CapabilityRetryClaim(record=record, acquired=False)
        claimed = _record(
            record.plan,
            status=CapabilityRetryStatus.RUNNING,
            lease_id=lease_id,
            lease_expires_at=now + ttl,
        )
        self.records[retry_id] = claimed
        return CapabilityRetryClaim(record=claimed, acquired=True)

    async def finish(
        self,
        *,
        retry_id: UUID,
        user_id: UUID,
        lease_id: UUID,
        result: CapabilityResult | None,
        safe_error_code: str | None,
        now: datetime,
    ) -> CapabilityRetryRecord:
        del now
        record = self.records[retry_id]
        assert record.user_id == user_id
        if record.lease_id != lease_id:
            raise CapabilityRetryStale("stale retry worker")
        failed = (
            result is None
            or result.terminal_state in FAILURE_TERMINAL_STATES
        )
        finished = _record(
            record.plan,
            status=(
                CapabilityRetryStatus.FAILED
                if failed
                else CapabilityRetryStatus.SUCCEEDED
            ),
            result=result,
            safe_error_code=safe_error_code if result is None else None,
        )
        self.records[retry_id] = finished
        return finished


class RecordingExecutor:
    def __init__(self, *, malformed: bool = False) -> None:
        self.malformed = malformed
        self.calls: list[tuple[str, UUID]] = []

    async def execute(self, *, node_id: str, request):
        self.calls.append((node_id, request.request_id))
        if self.malformed:
            return object()
        return CapabilityResult(
            request_id=request.request_id,
            run_id=request.run_id,
            capability=request.capability,
            terminal_state=CapabilityTerminalState.SATISFIED,
            scope_echo=request.scope,
            timing=CapabilityTiming(
                started_at=NOW,
                completed_at=NOW,
                duration_ms=0,
            ),
        )


def test_retry_plan_targets_only_transient_selected_node_and_preserves_state() -> None:
    snapshot = _snapshot()
    original_state = snapshot.orchestration_state

    plan = plan_capability_retry(
        snapshot,
        node_id=NODE_ID,
        idempotency_key=RETRY_ID,
    )

    assert plan.retry_id == RETRY_ID
    assert plan.node_id == NODE_ID
    assert plan.capability is OrchestratorCapability.REGULATORY_RETRIEVER
    assert plan.request.request_id == RETRY_ID
    assert plan.request.run_id == snapshot.run_id
    assert plan.original_execution_version == 7
    assert plan.failure_decision.failed_node_id == NODE_ID
    assert plan.preserved_artifact_ids == tuple(
        item.artifact_id for item in original_state.admitted_artifacts
    )
    assert snapshot.orchestration_state == original_state


@pytest.mark.parametrize(
    "capability",
    [
        OrchestratorCapability.REGULATORY_RETRIEVER,
        OrchestratorCapability.NEWS_RETRIEVER,
        OrchestratorCapability.GENERAL_AI,
        OrchestratorCapability.CITATION_VERIFIER,
    ],
)
def test_each_frozen_independent_capability_builds_an_exact_retry(
    capability: OrchestratorCapability,
) -> None:
    snapshot, node_id = _snapshot_for_capability(capability)

    plan = plan_capability_retry(
        snapshot,
        node_id=node_id,
        idempotency_key=RETRY_ID,
    )

    assert plan.capability is capability
    assert plan.node_id == node_id
    assert plan.request.capability is capability


@pytest.mark.parametrize(
    "terminal_state",
    [
        CapabilityTerminalState.SATISFIED,
        CapabilityTerminalState.PARTIAL,
        CapabilityTerminalState.NO_MATCH,
        CapabilityTerminalState.CANCELLED,
    ],
)
def test_retry_refuses_nontransient_or_cancelled_outcomes(
    terminal_state: CapabilityTerminalState,
) -> None:
    with pytest.raises(CapabilityRetryNotEligible):
        plan_capability_retry(
            _snapshot(terminal_state),
            node_id=NODE_ID,
            idempotency_key=RETRY_ID,
        )


def test_retry_refuses_a_durable_cancellation_request() -> None:
    snapshot = _snapshot().model_copy(
        update={
            "cancellation": CancellationRequest(
                request_id=uuid4(),
                requested_at=NOW,
                reason_code="USER_STOP",
            )
        }
    )

    with pytest.raises(CapabilityRetryNotEligible, match="Cancelled"):
        plan_capability_retry(
            snapshot,
            node_id=NODE_ID,
            idempotency_key=RETRY_ID,
        )


def test_request_and_execution_are_idempotent_and_invoke_one_exact_node() -> None:
    snapshot = _snapshot()
    store = MemoryRetryStore(snapshot)
    identities = iter(
        (
            UUID("44444444-4444-4444-8444-444444444444"),
            UUID("55555555-5555-4555-8555-555555555555"),
        )
    )
    service = CapabilityRetryService(
        store,
        clock=lambda: NOW,
        identity_factory=lambda: next(identities),
    )

    first = asyncio.run(
        service.request(
            run_id=snapshot.run_id,
            user_id=USER_ID,
            node_id=NODE_ID,
            idempotency_key=RETRY_ID,
        )
    )
    repeated = asyncio.run(
        service.request(
            run_id=snapshot.run_id,
            user_id=USER_ID,
            node_id=NODE_ID,
            idempotency_key=RETRY_ID,
        )
    )
    executor = RecordingExecutor()
    completed = asyncio.run(
        service.execute(
            retry_id=RETRY_ID,
            user_id=USER_ID,
            executor=executor,
            lease_ttl=timedelta(seconds=5),
        )
    )
    completed_again = asyncio.run(
        service.execute(
            retry_id=RETRY_ID,
            user_id=USER_ID,
            executor=executor,
            lease_ttl=timedelta(seconds=5),
        )
    )

    assert first == repeated
    assert completed.status is CapabilityRetryStatus.SUCCEEDED
    assert completed_again == completed
    assert executor.calls == [(NODE_ID, RETRY_ID)]
    assert snapshot.orchestration_state == _snapshot().orchestration_state


def test_different_idempotency_key_cannot_create_a_second_bounded_retry() -> None:
    snapshot = _snapshot()
    store = MemoryRetryStore(snapshot)
    service = CapabilityRetryService(store, clock=lambda: NOW)
    asyncio.run(
        service.request(
            run_id=snapshot.run_id,
            user_id=USER_ID,
            node_id=NODE_ID,
            idempotency_key=RETRY_ID,
        )
    )

    with pytest.raises(CapabilityRetryConflict):
        asyncio.run(
            service.request(
                run_id=snapshot.run_id,
                user_id=USER_ID,
                node_id=NODE_ID,
                idempotency_key=uuid4(),
            )
        )


def test_executor_failure_is_safe_and_never_retries_automatically() -> None:
    snapshot = _snapshot()
    store = MemoryRetryStore(snapshot)
    service = CapabilityRetryService(
        store,
        clock=lambda: NOW,
        identity_factory=lambda: uuid4(),
    )
    asyncio.run(
        service.request(
            run_id=snapshot.run_id,
            user_id=USER_ID,
            node_id=NODE_ID,
            idempotency_key=RETRY_ID,
        )
    )
    executor = RecordingExecutor(malformed=True)

    failed = asyncio.run(
        service.execute(
            retry_id=RETRY_ID,
            user_id=USER_ID,
            executor=executor,
            lease_ttl=timedelta(seconds=5),
        )
    )

    assert failed.status is CapabilityRetryStatus.FAILED
    assert failed.safe_error_code == CAPABILITY_RETRY_SAFE_ERROR_CODE
    assert executor.calls == [(NODE_ID, RETRY_ID)]
    response = CapabilityRetryResponse.from_record(failed)
    assert "invalid" not in response.model_dump_json().lower()


def test_expired_retry_lease_can_be_taken_over_and_fences_old_worker() -> None:
    snapshot = _snapshot()
    store = MemoryRetryStore(snapshot)
    service = CapabilityRetryService(store, clock=lambda: NOW)
    asyncio.run(
        service.request(
            run_id=snapshot.run_id,
            user_id=USER_ID,
            node_id=NODE_ID,
            idempotency_key=RETRY_ID,
        )
    )
    first_lease = uuid4()
    second_lease = uuid4()
    first = asyncio.run(
        store.claim(
            retry_id=RETRY_ID,
            user_id=USER_ID,
            lease_id=first_lease,
            now=NOW,
            ttl=timedelta(seconds=1),
        )
    )
    takeover = asyncio.run(
        store.claim(
            retry_id=RETRY_ID,
            user_id=USER_ID,
            lease_id=second_lease,
            now=NOW + timedelta(seconds=2),
            ttl=timedelta(seconds=5),
        )
    )

    assert first.acquired is True
    assert takeover.acquired is True
    assert takeover.record.lease_id == second_lease
    with pytest.raises(CapabilityRetryStale):
        asyncio.run(
            store.finish(
                retry_id=RETRY_ID,
                user_id=USER_ID,
                lease_id=first_lease,
                result=None,
                safe_error_code=CAPABILITY_RETRY_SAFE_ERROR_CODE,
                now=NOW + timedelta(seconds=2),
            )
        )


def test_retry_contracts_are_strict_and_lifecycle_consistent() -> None:
    with pytest.raises(ValidationError):
        CapabilityRetryRequestBody.model_validate(
            {
                "idempotency_key": str(RETRY_ID),
                "node_id": NODE_ID,
                "unknown": True,
            }
        )
    with pytest.raises(ValidationError):
        _record(
            plan_capability_retry(
                _snapshot(),
                node_id=NODE_ID,
                idempotency_key=RETRY_ID,
            ),
            status=CapabilityRetryStatus.SUCCEEDED,
        )
    service = CapabilityRetryService(MemoryRetryStore(_snapshot()))
    with pytest.raises(ValueError, match="hard budget"):
        asyncio.run(
            service.execute(
                retry_id=RETRY_ID,
                user_id=USER_ID,
                executor=RecordingExecutor(),
                lease_ttl=timedelta(seconds=31),
            )
        )


class FakeRetryService:
    def __init__(
        self,
        record: CapabilityRetryRecord | None = None,
        error: Exception | None = None,
    ) -> None:
        self.record = record
        self.error = error
        self.calls: list[dict[str, object]] = []

    async def request(self, **kwargs):
        self.calls.append(kwargs)
        if self.error is not None:
            raise self.error
        assert self.record is not None
        return self.record


def _retry_api(service: FakeRetryService) -> FastAPI:
    api = FastAPI()
    api.include_router(chat_runs.router)
    api.dependency_overrides[current_user] = lambda: CurrentUser(
        id=str(USER_ID),
        email="owner@example.com",
    )
    api.dependency_overrides[
        chat_runs.get_capability_retry_service
    ] = lambda: service
    return api


def test_retry_endpoint_is_v2_gated_owner_scoped_and_returns_safe_contract(
    monkeypatch,
) -> None:
    snapshot = _snapshot()
    plan = plan_capability_retry(
        snapshot,
        node_id=NODE_ID,
        idempotency_key=RETRY_ID,
    )
    service = FakeRetryService(_record(plan))
    client = TestClient(_retry_api(service))
    monkeypatch.setattr(settings, "ask_ai_v2_api_enabled", False)
    assert client.post(
        f"/chat/runs/{snapshot.run_id}/retry",
        json={
            "idempotency_key": str(RETRY_ID),
            "node_id": NODE_ID,
        },
    ).status_code == 404

    monkeypatch.setattr(settings, "ask_ai_v2_api_enabled", True)
    monkeypatch.setattr(settings, "ask_ai_streaming_enabled", False)
    response = client.post(
        f"/chat/runs/{snapshot.run_id}/retry",
        json={
            "idempotency_key": str(RETRY_ID),
            "node_id": NODE_ID,
        },
    )

    assert response.status_code == 202
    assert response.json()["retry_id"] == str(RETRY_ID)
    assert response.json()["status"] == "pending"
    assert service.calls == [
        {
            "run_id": snapshot.run_id,
            "user_id": USER_ID,
            "node_id": NODE_ID,
            "idempotency_key": RETRY_ID,
        }
    ]


def test_retry_endpoint_suppresses_internal_error_detail(monkeypatch) -> None:
    snapshot = _snapshot()
    monkeypatch.setattr(settings, "ask_ai_v2_api_enabled", True)
    service = FakeRetryService(
        error=CapabilityRetryConflict("provider credential detail")
    )

    response = TestClient(_retry_api(service)).post(
        f"/chat/runs/{snapshot.run_id}/retry",
        json={
            "idempotency_key": str(RETRY_ID),
            "node_id": NODE_ID,
        },
    )

    assert response.status_code == 409
    assert response.json() == {
        "detail": "Capability retry is not available"
    }
    assert "credential" not in response.text

    unauthenticated = FastAPI()
    unauthenticated.include_router(chat_runs.router)
    assert TestClient(unauthenticated).post(
        f"/chat/runs/{snapshot.run_id}/retry",
        json={
            "idempotency_key": str(RETRY_ID),
            "node_id": NODE_ID,
        },
    ).status_code == 401
