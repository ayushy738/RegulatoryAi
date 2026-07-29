from __future__ import annotations

import base64
import binascii
import json
from datetime import datetime, timedelta
from enum import StrEnum
from typing import Literal
from uuid import UUID

from pydantic import Field, model_validator
from sqlalchemy import text
from sqlalchemy.orm import Session

from backend.ask.orchestration.contracts import ContractModel, OrchestratorCapability
from backend.ask.orchestration.state_machine import (
    CAPABILITY_TERMINAL_STATES,
    PHASE_INDEX,
    SECTION_TERMINAL_STATES,
    CapabilityWorkState,
    OrchestrationState,
    RunTerminalState,
    SectionWorkState,
)

DURABILITY_SCHEMA_VERSION = "1"
DURABILITY_POLICY_VERSION = "ask-ai-durability-v1"
RUN_EVENT_READ_SCHEMA_VERSION = "1"
RUN_EVENT_CURSOR_SCHEMA_VERSION = "1"
MAX_RUN_EVENT_PAGE_SIZE = 200


class DurableEventType(StrEnum):
    LEASE_ACQUIRED = "lease_acquired"
    LEASE_RENEWED = "lease_renewed"
    LEASE_RELEASED = "lease_released"
    STATE_TRANSITION = "state_transition"
    CANCELLATION_REQUESTED = "cancellation_requested"
    CANCELLATION_APPLIED = "cancellation_applied"


class DurableRunStatus(StrEnum):
    PENDING = "pending"
    RUNNING = "running"
    COMPLETED = "completed"
    PARTIAL = "partial"
    FAILED = "failed"
    CANCELLED = "cancelled"


SAFE_RUN_EVENT_STATUSES = frozenset(
    status.value
    for status in (
        *DurableRunStatus,
        *RunTerminalState,
        *CapabilityWorkState,
        *CAPABILITY_TERMINAL_STATES,
        *SectionWorkState,
        *SECTION_TERMINAL_STATES,
    )
)
TERMINAL_RUN_EVENT_STATUSES = frozenset(
    {
        DurableRunStatus.COMPLETED.value,
        DurableRunStatus.PARTIAL.value,
        DurableRunStatus.FAILED.value,
        DurableRunStatus.CANCELLED.value,
        *(status.value for status in RunTerminalState),
    }
)


class DurableRunEvent(ContractModel):
    schema_version: Literal["1"] = DURABILITY_SCHEMA_VERSION
    policy_version: str = Field(default=DURABILITY_POLICY_VERSION, min_length=1)
    public_id: UUID
    run_id: UUID
    session_id: UUID
    user_id: UUID
    sequence: int = Field(ge=0)
    execution_version: int = Field(gt=0)
    event_type: DurableEventType
    capability: str | None = None
    status: str | None = None
    payload: dict[str, object]
    created_at: datetime

    @model_validator(mode="after")
    def validate_time(self) -> DurableRunEvent:
        if self.created_at.tzinfo is None or self.created_at.utcoffset() is None:
            raise ValueError("Durable event timestamps must be timezone-aware")
        return self


class DurableRunEventReadModel(ContractModel):
    schema_version: Literal["1"] = RUN_EVENT_READ_SCHEMA_VERSION
    policy_version: str = Field(min_length=1)
    event_id: UUID
    run_id: UUID
    sequence: int = Field(ge=0)
    execution_version: int = Field(gt=0)
    event_type: DurableEventType
    capability: OrchestratorCapability | None = None
    status: str | None = None
    orchestration_state: OrchestrationState | None = None
    cancellation_reason_code: str | None = Field(
        default=None,
        pattern=r"^[A-Z][A-Z0-9_]{0,99}$",
    )
    created_at: datetime

    @model_validator(mode="after")
    def validate_event(self) -> DurableRunEventReadModel:
        _require_aware(self.created_at)
        if (
            self.orchestration_state is not None
            and self.orchestration_state.run_id != self.run_id
        ):
            raise ValueError("Event state must belong to the durable run")
        if (
            self.status is not None
            and self.status not in SAFE_RUN_EVENT_STATUSES
        ):
            raise ValueError("Event status is not a safe lifecycle value")
        return self


class DurableRunEventCursor(ContractModel):
    schema_version: Literal["1"] = RUN_EVENT_CURSOR_SCHEMA_VERSION
    event_id: UUID
    run_id: UUID
    sequence: int = Field(ge=0)
    execution_version: int = Field(gt=0)

    @model_validator(mode="after")
    def validate_position(self) -> DurableRunEventCursor:
        if self.execution_version != self.sequence + 1:
            raise ValueError("Event cursor sequence and execution version must align")
        return self


class DurableRunEventPage(ContractModel):
    schema_version: Literal["1"] = RUN_EVENT_READ_SCHEMA_VERSION
    run_id: UUID
    snapshot_execution_version: int = Field(ge=0)
    snapshot_next_sequence: int = Field(ge=0)
    items: tuple[DurableRunEventReadModel, ...]
    resume_cursor: str | None
    has_more: bool


class RunLease(ContractModel):
    lease_id: UUID
    expires_at: datetime
    heartbeat_at: datetime

    @model_validator(mode="after")
    def validate_times(self) -> RunLease:
        for value in (self.expires_at, self.heartbeat_at):
            if value.tzinfo is None or value.utcoffset() is None:
                raise ValueError("Lease timestamps must be timezone-aware")
        if self.expires_at <= self.heartbeat_at:
            raise ValueError("Lease expiry must follow its heartbeat")
        return self


class CancellationRequest(ContractModel):
    request_id: UUID
    requested_at: datetime
    reason_code: str | None = Field(
        default=None,
        pattern=r"^[A-Z][A-Z0-9_]{0,99}$",
    )

    @model_validator(mode="after")
    def validate_time(self) -> CancellationRequest:
        _require_aware(self.requested_at)
        return self


class DurableRunSnapshot(ContractModel):
    schema_version: Literal["1"] = DURABILITY_SCHEMA_VERSION
    policy_version: str = Field(default=DURABILITY_POLICY_VERSION, min_length=1)
    run_id: UUID
    session_id: UUID
    user_id: UUID
    status: DurableRunStatus
    execution_version: int = Field(ge=0)
    next_event_sequence: int = Field(ge=0)
    orchestration_state: OrchestrationState
    lease: RunLease | None = None
    cancellation: CancellationRequest | None = None


class CancellationPlan(ContractModel):
    active_node_ids: tuple[str, ...]
    queued_node_ids: tuple[str, ...]
    preserved_artifact_ids: tuple[str, ...]
    preserved_terminal_section_ids: tuple[str, ...]
    nonterminal_section_ids: tuple[str, ...]
    withheld_claim_ids: tuple[str, ...]


class DurabilityError(RuntimeError):
    pass


class DurableRunNotFound(DurabilityError):
    pass


class StaleExecutionVersion(DurabilityError):
    pass


class LeaseConflict(DurabilityError):
    pass


class RunEventCursorError(DurabilityError):
    pass


class DurableRunRepository:
    def __init__(self, session: Session) -> None:
        self._session = session

    def acquire_lease(
        self,
        *,
        run_id: UUID,
        session_id: UUID,
        user_id: UUID,
        lease_id: UUID,
        event_id: UUID,
        now: datetime,
        ttl: timedelta,
    ) -> DurableRunEvent:
        _require_aware(now)
        if ttl <= timedelta(0):
            raise ValueError("Lease TTL must be positive")
        run = self._lock_run(run_id, session_id, user_id)
        existing = self._existing_event(event_id, run_id, session_id, user_id)
        if existing is not None:
            _require_idempotent_event(
                existing,
                event_type=DurableEventType.LEASE_ACQUIRED,
                payload={"lease_id": str(lease_id)},
            )
            return existing
        if run["status"] in {
            DurableRunStatus.COMPLETED.value,
            DurableRunStatus.PARTIAL.value,
            DurableRunStatus.FAILED.value,
            DurableRunStatus.CANCELLED.value,
        }:
            raise DurabilityError("Terminal durable runs cannot acquire a lease")
        if (
            run["lease_id"] is not None
            and run["lease_expires_at"] > now
        ):
            raise LeaseConflict("Run already has an unexpired worker lease")
        expires_at = now + ttl
        event = self._insert_event(
            run,
            event_id=event_id,
            event_type=DurableEventType.LEASE_ACQUIRED,
            payload={
                "lease_id": str(lease_id),
                "expires_at": expires_at.isoformat(),
            },
            status=DurableRunStatus.RUNNING,
        )
        self._session.execute(
            text(
                """
                update public.ask_runs
                set
                  lease_id = :lease_id,
                  lease_expires_at = :expires_at,
                  lease_heartbeat_at = :now,
                  status = 'running',
                  started_at = coalesce(started_at, :now),
                  execution_version = :execution_version,
                  next_event_sequence = :next_event_sequence,
                  updated_at = :now
                where id = :run_id
                  and session_id = :session_id
                  and user_id = :user_id
                """
            ),
            {
                **_owner_parameters(run_id, session_id, user_id),
                "lease_id": lease_id,
                "expires_at": expires_at,
                "now": now,
                "execution_version": event.execution_version,
                "next_event_sequence": event.sequence + 1,
            },
        )
        return event

    def renew_lease(
        self,
        *,
        run_id: UUID,
        session_id: UUID,
        user_id: UUID,
        lease_id: UUID,
        event_id: UUID,
        expected_version: int,
        now: datetime,
        ttl: timedelta,
    ) -> DurableRunEvent:
        _require_aware(now)
        if ttl <= timedelta(0):
            raise ValueError("Lease TTL must be positive")
        run = self._lock_run(run_id, session_id, user_id)
        existing = self._existing_event(event_id, run_id, session_id, user_id)
        if existing is not None:
            _require_idempotent_event(
                existing,
                event_type=DurableEventType.LEASE_RENEWED,
                payload={"lease_id": str(lease_id)},
            )
            return existing
        self._require_version(run, expected_version)
        self._require_lease(run, lease_id, now)
        expires_at = now + ttl
        event = self._insert_event(
            run,
            event_id=event_id,
            event_type=DurableEventType.LEASE_RENEWED,
            payload={
                "lease_id": str(lease_id),
                "expires_at": expires_at.isoformat(),
            },
            status=run["status"],
        )
        self._session.execute(
            text(
                """
                update public.ask_runs
                set
                  lease_expires_at = :expires_at,
                  lease_heartbeat_at = :now,
                  execution_version = :execution_version,
                  next_event_sequence = :next_event_sequence,
                  updated_at = :now
                where id = :run_id
                  and session_id = :session_id
                  and user_id = :user_id
                """
            ),
            {
                **_owner_parameters(run_id, session_id, user_id),
                "expires_at": expires_at,
                "now": now,
                "execution_version": event.execution_version,
                "next_event_sequence": event.sequence + 1,
            },
        )
        return event

    def release_lease(
        self,
        *,
        run_id: UUID,
        session_id: UUID,
        user_id: UUID,
        lease_id: UUID,
        event_id: UUID,
        expected_version: int,
        now: datetime,
    ) -> DurableRunEvent:
        _require_aware(now)
        run = self._lock_run(run_id, session_id, user_id)
        existing = self._existing_event(event_id, run_id, session_id, user_id)
        if existing is not None:
            _require_idempotent_event(
                existing,
                event_type=DurableEventType.LEASE_RELEASED,
                payload={"lease_id": str(lease_id)},
            )
            return existing
        self._require_version(run, expected_version)
        if run["lease_id"] != lease_id:
            raise LeaseConflict("Only the current worker may release the lease")
        event = self._insert_event(
            run,
            event_id=event_id,
            event_type=DurableEventType.LEASE_RELEASED,
            payload={"lease_id": str(lease_id)},
            status=run["status"],
        )
        self._session.execute(
            text(
                """
                update public.ask_runs
                set
                  lease_id = null,
                  lease_expires_at = null,
                  lease_heartbeat_at = null,
                  execution_version = :execution_version,
                  next_event_sequence = :next_event_sequence,
                  updated_at = :now
                where id = :run_id
                  and session_id = :session_id
                  and user_id = :user_id
                """
            ),
            {
                **_owner_parameters(run_id, session_id, user_id),
                "execution_version": event.execution_version,
                "next_event_sequence": event.sequence + 1,
                "now": now,
            },
        )
        return event

    def append_state_transition(
        self,
        *,
        run_id: UUID,
        session_id: UUID,
        user_id: UUID,
        lease_id: UUID,
        event_id: UUID,
        expected_version: int,
        state: OrchestrationState,
        now: datetime,
    ) -> DurableRunEvent:
        _require_aware(now)
        if state.run_id != run_id:
            raise ValueError("Orchestration state must belong to the durable run")
        run = self._lock_run(run_id, session_id, user_id)
        existing = self._existing_event(event_id, run_id, session_id, user_id)
        if existing is not None:
            _require_idempotent_event(
                existing,
                event_type=DurableEventType.STATE_TRANSITION,
                payload={
                    "orchestration_state": state.model_dump(mode="json"),
                },
            )
            return existing
        self._require_version(run, expected_version)
        self._require_lease(run, lease_id, now)
        try:
            previous_state = OrchestrationState.model_validate(
                run["orchestration_state"]
            )
        except (TypeError, ValueError) as exc:
            raise DurabilityError(
                "Durable run has no valid orchestration state"
            ) from exc
        validate_orchestration_progress(previous_state, state)
        event = self._insert_event(
            run,
            event_id=event_id,
            event_type=DurableEventType.STATE_TRANSITION,
            payload={
                "orchestration_state": state.model_dump(mode="json"),
            },
            status=(
                state.terminal_state.value
                if state.terminal_state is not None
                else DurableRunStatus.RUNNING
            ),
        )
        terminal = state.terminal_state is not None
        run_status = (
            _durable_status_for_state(state)
            if terminal
            else DurableRunStatus.RUNNING
        )
        self._session.execute(
            text(
                """
                update public.ask_runs
                set
                  orchestration_state = cast(:state as jsonb),
                  status = :status,
                  execution_version = :execution_version,
                  next_event_sequence = :next_event_sequence,
                  completed_at = case
                    when :terminal then :now
                    else completed_at
                  end,
                  lease_id = case when :terminal then null else lease_id end,
                  lease_expires_at = case
                    when :terminal then null
                    else lease_expires_at
                  end,
                  lease_heartbeat_at = case
                    when :terminal then null
                    else lease_heartbeat_at
                  end,
                  updated_at = :now
                where id = :run_id
                  and session_id = :session_id
                  and user_id = :user_id
                """
            ),
            {
                **_owner_parameters(run_id, session_id, user_id),
                "state": json.dumps(state.model_dump(mode="json")),
                "status": run_status.value,
                "execution_version": event.execution_version,
                "next_event_sequence": event.sequence + 1,
                "terminal": terminal,
                "now": now,
            },
        )
        return event

    def apply_cancellation(
        self,
        *,
        run_id: UUID,
        session_id: UUID,
        user_id: UUID,
        lease_id: UUID,
        request_id: UUID,
        event_id: UUID,
        expected_version: int,
        state: OrchestrationState,
        now: datetime,
    ) -> DurableRunEvent:
        _require_aware(now)
        if state.run_id != run_id:
            raise ValueError("Orchestration state must belong to the durable run")
        cancellation_plan = plan_safe_cancellation(state)
        payload = {
            "cancellation_request_id": str(request_id),
            "orchestration_state": state.model_dump(mode="json"),
            "cancellation_plan": cancellation_plan.model_dump(mode="json"),
        }
        run = self._lock_run(run_id, session_id, user_id)
        existing = self._existing_event(event_id, run_id, session_id, user_id)
        if existing is not None:
            _require_idempotent_event(
                existing,
                event_type=DurableEventType.CANCELLATION_APPLIED,
                payload=payload,
            )
            return existing
        self._require_version(run, expected_version)
        self._require_lease(run, lease_id, now)
        if run["cancellation_request_id"] != request_id:
            raise DurabilityError(
                "Cancellation request is missing or no longer current"
            )
        run_status = (
            DurableRunStatus.PARTIAL
            if cancellation_plan.preserved_terminal_section_ids
            else DurableRunStatus.CANCELLED
        )
        event = self._insert_event(
            run,
            event_id=event_id,
            event_type=DurableEventType.CANCELLATION_APPLIED,
            payload=payload,
            status=run_status,
        )
        self._session.execute(
            text(
                """
                update public.ask_runs
                set
                  orchestration_state = cast(:state as jsonb),
                  status = :status,
                  execution_version = :execution_version,
                  next_event_sequence = :next_event_sequence,
                  completed_at = :now,
                  lease_id = null,
                  lease_expires_at = null,
                  lease_heartbeat_at = null,
                  updated_at = :now
                where id = :run_id
                  and session_id = :session_id
                  and user_id = :user_id
                """
            ),
            {
                **_owner_parameters(run_id, session_id, user_id),
                "state": json.dumps(state.model_dump(mode="json")),
                "status": run_status.value,
                "execution_version": event.execution_version,
                "next_event_sequence": event.sequence + 1,
                "now": now,
            },
        )
        return event

    def request_cancellation(
        self,
        *,
        run_id: UUID,
        session_id: UUID,
        user_id: UUID,
        request_id: UUID,
        now: datetime,
        reason_code: str | None = None,
    ) -> DurableRunEvent:
        _require_aware(now)
        CancellationRequest(
            request_id=request_id,
            requested_at=now,
            reason_code=reason_code,
        )
        run = self._lock_run(run_id, session_id, user_id)
        existing = self._existing_event(request_id, run_id, session_id, user_id)
        if existing is not None:
            _require_idempotent_event(
                existing,
                event_type=DurableEventType.CANCELLATION_REQUESTED,
                payload={"reason_code": reason_code},
            )
            return existing
        if run["status"] in {
            DurableRunStatus.COMPLETED.value,
            DurableRunStatus.PARTIAL.value,
            DurableRunStatus.FAILED.value,
            DurableRunStatus.CANCELLED.value,
        }:
            raise DurabilityError("Terminal durable runs cannot be cancelled again")
        if run["cancellation_request_id"] is not None:
            raise DurabilityError("Run already has a different cancellation request")
        event = self._insert_event(
            run,
            event_id=request_id,
            event_type=DurableEventType.CANCELLATION_REQUESTED,
            payload={"reason_code": reason_code},
            status=run["status"],
        )
        self._session.execute(
            text(
                """
                update public.ask_runs
                set
                  cancellation_request_id = :request_id,
                  cancellation_requested_at = :now,
                  cancellation_reason_code = :reason_code,
                  execution_version = :execution_version,
                  next_event_sequence = :next_event_sequence,
                  updated_at = :now
                where id = :run_id
                  and session_id = :session_id
                  and user_id = :user_id
                """
            ),
            {
                **_owner_parameters(run_id, session_id, user_id),
                "request_id": request_id,
                "now": now,
                "reason_code": reason_code,
                "execution_version": event.execution_version,
                "next_event_sequence": event.sequence + 1,
            },
        )
        return event

    def load_snapshot(
        self,
        *,
        run_id: UUID,
        session_id: UUID,
        user_id: UUID,
    ) -> DurableRunSnapshot:
        row = self._session.execute(
            text(
                """
                select
                  id,
                  session_id,
                  user_id,
                  status,
                  orchestration_state,
                  execution_version,
                  next_event_sequence,
                  lease_id,
                  lease_expires_at,
                  lease_heartbeat_at,
                  cancellation_request_id,
                  cancellation_requested_at,
                  cancellation_reason_code
                from public.ask_runs
                where id = :run_id
                  and session_id = :session_id
                  and user_id = :user_id
                """
            ),
            _owner_parameters(run_id, session_id, user_id),
        ).mappings().one_or_none()
        if row is None:
            raise DurableRunNotFound("Durable run is inaccessible")
        try:
            state = OrchestrationState.model_validate(row["orchestration_state"])
        except (TypeError, ValueError) as exc:
            raise DurabilityError("Durable run has no valid orchestration state") from exc
        lease = (
            RunLease(
                lease_id=row["lease_id"],
                expires_at=row["lease_expires_at"],
                heartbeat_at=row["lease_heartbeat_at"],
            )
            if row["lease_id"] is not None
            else None
        )
        cancellation = (
            CancellationRequest(
                request_id=row["cancellation_request_id"],
                requested_at=row["cancellation_requested_at"],
                reason_code=row["cancellation_reason_code"],
            )
            if row["cancellation_request_id"] is not None
            else None
        )
        return DurableRunSnapshot(
            run_id=row["id"],
            session_id=row["session_id"],
            user_id=row["user_id"],
            status=row["status"],
            execution_version=row["execution_version"],
            next_event_sequence=row["next_event_sequence"],
            orchestration_state=state,
            lease=lease,
            cancellation=cancellation,
        )

    def load_events(
        self,
        *,
        run_id: UUID,
        session_id: UUID,
        user_id: UUID,
        after_sequence: int = -1,
    ) -> tuple[DurableRunEvent, ...]:
        if after_sequence < -1:
            raise ValueError("Replay cursor cannot be below -1")
        rows = self._session.execute(
            text(
                """
                select
                  public_id,
                  run_id,
                  session_id,
                  user_id,
                  sequence,
                  execution_version,
                  event_type,
                  capability,
                  status,
                  payload,
                  created_at
                from public.ask_run_events
                where run_id = :run_id
                  and session_id = :session_id
                  and user_id = :user_id
                  and sequence > :after_sequence
                order by sequence, id
                """
            ),
            {
                **_owner_parameters(run_id, session_id, user_id),
                "after_sequence": after_sequence,
            },
        ).mappings()
        return tuple(_event(row) for row in rows)

    def load_event_page(
        self,
        *,
        run_id: UUID,
        session_id: UUID,
        user_id: UUID,
        cursor: str | None = None,
        limit: int = 100,
    ) -> DurableRunEventPage:
        if isinstance(limit, bool) or not isinstance(limit, int):
            raise TypeError("Run event page size must be an integer")
        if limit < 1 or limit > MAX_RUN_EVENT_PAGE_SIZE:
            raise ValueError(
                f"Run event page size must be between 1 and "
                f"{MAX_RUN_EVENT_PAGE_SIZE}"
            )
        boundary = self._session.execute(
            text(
                """
                select execution_version, next_event_sequence
                from public.ask_runs
                where id = :run_id
                  and session_id = :session_id
                  and user_id = :user_id
                """
            ),
            _owner_parameters(run_id, session_id, user_id),
        ).mappings().one_or_none()
        if boundary is None:
            raise DurableRunNotFound("Durable run is inaccessible")

        after_sequence = -1
        after_version = 0
        decoded_cursor: DurableRunEventCursor | None = None
        if cursor is not None:
            decoded_cursor = decode_run_event_cursor(cursor)
            if decoded_cursor.run_id != run_id:
                raise RunEventCursorError(
                    "Durable event cursor belongs to another run"
                )
            anchor = self._session.execute(
                text(
                    """
                    select public_id, execution_version
                    from public.ask_run_events
                    where run_id = :run_id
                      and session_id = :session_id
                      and user_id = :user_id
                      and sequence = :sequence
                    """
                ),
                {
                    **_owner_parameters(run_id, session_id, user_id),
                    "sequence": decoded_cursor.sequence,
                },
            ).mappings().one_or_none()
            if (
                anchor is None
                or anchor["public_id"] != decoded_cursor.event_id
                or anchor["execution_version"]
                != decoded_cursor.execution_version
            ):
                raise RunEventCursorError(
                    "Durable event cursor does not match persisted history"
                )
            after_sequence = decoded_cursor.sequence
            after_version = decoded_cursor.execution_version

        snapshot_execution_version = boundary["execution_version"]
        snapshot_next_sequence = boundary["next_event_sequence"]
        remaining_by_sequence = snapshot_next_sequence - after_sequence - 1
        remaining_by_version = snapshot_execution_version - after_version
        if (
            remaining_by_sequence < 0
            or remaining_by_version < 0
            or remaining_by_sequence != remaining_by_version
        ):
            raise DurabilityError(
                "Durable run counters do not match persisted event history"
            )

        rows = self._session.execute(
            text(
                """
                select
                  public_id,
                  run_id,
                  session_id,
                  user_id,
                  sequence,
                  execution_version,
                  event_type,
                  capability,
                  status,
                  payload,
                  created_at
                from public.ask_run_events
                where run_id = :run_id
                  and session_id = :session_id
                  and user_id = :user_id
                  and sequence > :after_sequence
                  and sequence < :snapshot_next_sequence
                order by sequence, id
                limit :row_limit
                """
            ),
            {
                **_owner_parameters(run_id, session_id, user_id),
                "after_sequence": after_sequence,
                "snapshot_next_sequence": snapshot_next_sequence,
                "row_limit": limit + 1,
            },
        ).mappings().all()
        events = tuple(_event(row) for row in rows)
        expected_loaded = min(remaining_by_sequence, limit + 1)
        if len(events) != expected_loaded:
            raise DurabilityError("Durable event history contains a sequence gap")
        _validate_event_batch(
            events,
            run_id=run_id,
            session_id=session_id,
            user_id=user_id,
            first_sequence=after_sequence + 1,
            first_execution_version=after_version + 1,
        )

        selected = events[:limit]
        items = tuple(run_event_read_model(event) for event in selected)
        has_more = remaining_by_sequence > len(selected)
        resume_cursor = (
            encode_run_event_cursor(items[-1])
            if items
            else cursor
        )
        return DurableRunEventPage(
            run_id=run_id,
            snapshot_execution_version=snapshot_execution_version,
            snapshot_next_sequence=snapshot_next_sequence,
            items=items,
            resume_cursor=resume_cursor,
            has_more=has_more,
        )

    def _lock_run(
        self,
        run_id: UUID,
        session_id: UUID,
        user_id: UUID,
    ):
        row = self._session.execute(
            text(
                """
                select
                  id,
                  session_id,
                  user_id,
                  status,
                  orchestration_state,
                  execution_version,
                  next_event_sequence,
                  lease_id,
                  lease_expires_at,
                  cancellation_request_id
                from public.ask_runs
                where id = :run_id
                  and session_id = :session_id
                  and user_id = :user_id
                for update
                """
            ),
            _owner_parameters(run_id, session_id, user_id),
        ).mappings().one_or_none()
        if row is None:
            raise DurableRunNotFound("Durable run is inaccessible")
        return row

    def _existing_event(
        self,
        event_id: UUID,
        run_id: UUID,
        session_id: UUID,
        user_id: UUID,
    ) -> DurableRunEvent | None:
        row = self._session.execute(
            text(
                """
                select
                  public_id,
                  run_id,
                  session_id,
                  user_id,
                  sequence,
                  execution_version,
                  event_type,
                  capability,
                  status,
                  payload,
                  created_at
                from public.ask_run_events
                where public_id = :event_id
                """
            ),
            {"event_id": event_id},
        ).mappings().one_or_none()
        if row is not None and (
            row["run_id"] != run_id
            or row["session_id"] != session_id
            or row["user_id"] != user_id
        ):
            raise DurabilityError("Durable event identifier is already in use")
        return _event(row) if row is not None else None

    def _insert_event(
        self,
        run,
        *,
        event_id: UUID,
        event_type: DurableEventType,
        payload: dict[str, object],
        status: str | DurableRunStatus,
    ) -> DurableRunEvent:
        row = self._session.execute(
            text(
                """
                insert into public.ask_run_events (
                  public_id,
                  run_id,
                  session_id,
                  user_id,
                  sequence,
                  execution_version,
                  event_type,
                  status,
                  payload
                )
                values (
                  :event_id,
                  :run_id,
                  :session_id,
                  :user_id,
                  :sequence,
                  :execution_version,
                  :event_type,
                  :status,
                  cast(:payload as jsonb)
                )
                returning
                  public_id,
                  run_id,
                  session_id,
                  user_id,
                  sequence,
                  execution_version,
                  event_type,
                  capability,
                  status,
                  payload,
                  created_at
                """
            ),
            {
                "event_id": event_id,
                "run_id": run["id"],
                "session_id": run["session_id"],
                "user_id": run["user_id"],
                "sequence": run["next_event_sequence"],
                "execution_version": run["execution_version"] + 1,
                "event_type": event_type.value,
                "status": (
                    status.value if isinstance(status, DurableRunStatus) else status
                ),
                "payload": json.dumps(payload),
            },
        ).mappings().one()
        return _event(row)

    @staticmethod
    def _require_version(run, expected_version: int) -> None:
        if run["execution_version"] != expected_version:
            raise StaleExecutionVersion("Durable run execution version is stale")

    @staticmethod
    def _require_lease(run, lease_id: UUID, now: datetime) -> None:
        if (
            run["lease_id"] != lease_id
            or run["lease_expires_at"] is None
            or run["lease_expires_at"] <= now
        ):
            raise LeaseConflict("Durable run lease is missing, stale, or expired")


def plan_safe_cancellation(state: OrchestrationState) -> CancellationPlan:
    terminal_sections = tuple(
        section.section_id
        for section in state.sections
        if section.state in SECTION_TERMINAL_STATES
    )
    material_claim_ids = {
        claim_id
        for section in state.sections
        for claim_id in section.material_claim_ids
    }
    terminal_claim_ids = {
        claim_id
        for section in state.sections
        for claim_id in section.terminal_verification_claim_ids
    }
    return CancellationPlan(
        active_node_ids=tuple(
            node.node_id
            for node in state.capabilities
            if node.state is CapabilityWorkState.ACTIVE
        ),
        queued_node_ids=tuple(
            node.node_id
            for node in state.capabilities
            if node.state is CapabilityWorkState.QUEUED
        ),
        preserved_artifact_ids=tuple(
            artifact.artifact_id for artifact in state.admitted_artifacts
        ),
        preserved_terminal_section_ids=terminal_sections,
        nonterminal_section_ids=tuple(
            section.section_id
            for section in state.sections
            if section.section_id not in terminal_sections
        ),
        withheld_claim_ids=tuple(sorted(material_claim_ids - terminal_claim_ids)),
    )


def replay_orchestration(
    events: tuple[DurableRunEvent, ...],
) -> OrchestrationState:
    if not events:
        raise DurabilityError("Replay contains no orchestration state")
    first = events[0]
    _validate_event_batch(
        events,
        run_id=first.run_id,
        session_id=first.session_id,
        user_id=first.user_id,
        first_sequence=0,
        first_execution_version=1,
    )
    previous_state: OrchestrationState | None = None
    terminal_event_seen = False
    for event in events:
        if terminal_event_seen:
            raise DurabilityError(
                "Replay cannot append events after a terminal run event"
            )
        state_payload = event.payload.get("orchestration_state")
        if state_payload is None:
            terminal_event_seen = event.status in TERMINAL_RUN_EVENT_STATUSES
            continue
        try:
            state = OrchestrationState.model_validate(state_payload)
        except (TypeError, ValueError) as exc:
            raise DurabilityError(
                "Replay contains an invalid orchestration state"
            ) from exc
        if state.run_id != event.run_id:
            raise DurabilityError(
                "Replay orchestration state belongs to another run"
            )
        if previous_state is not None:
            validate_orchestration_progress(previous_state, state)
        previous_state = state
        terminal_event_seen = (
            event.status in TERMINAL_RUN_EVENT_STATUSES
            or state.terminal_state is not None
        )
    if previous_state is None:
        raise DurabilityError("Replay contains no orchestration state")
    return previous_state


def run_event_read_model(event: DurableRunEvent) -> DurableRunEventReadModel:
    state: OrchestrationState | None = None
    state_payload = event.payload.get("orchestration_state")
    if state_payload is not None:
        try:
            state = OrchestrationState.model_validate(state_payload)
        except (TypeError, ValueError) as exc:
            raise DurabilityError(
                "Durable event contains an invalid orchestration state"
            ) from exc
    if event.event_type in {
        DurableEventType.STATE_TRANSITION,
        DurableEventType.CANCELLATION_APPLIED,
    } and state is None:
        raise DurabilityError(
            "Durable state event does not contain orchestration state"
        )
    reason_code = (
        event.payload.get("reason_code")
        if event.event_type is DurableEventType.CANCELLATION_REQUESTED
        else None
    )
    if reason_code is not None and not isinstance(reason_code, str):
        raise DurabilityError(
            "Durable cancellation reason code is invalid"
        )
    try:
        return DurableRunEventReadModel(
            policy_version=event.policy_version,
            event_id=event.public_id,
            run_id=event.run_id,
            sequence=event.sequence,
            execution_version=event.execution_version,
            event_type=event.event_type,
            capability=event.capability,
            status=event.status,
            orchestration_state=state,
            cancellation_reason_code=reason_code,
            created_at=event.created_at,
        )
    except ValueError as exc:
        raise DurabilityError("Durable event read model is invalid") from exc


def encode_run_event_cursor(event: DurableRunEventReadModel) -> str:
    cursor = DurableRunEventCursor(
        event_id=event.event_id,
        run_id=event.run_id,
        sequence=event.sequence,
        execution_version=event.execution_version,
    )
    encoded = json.dumps(
        cursor.model_dump(mode="json"),
        sort_keys=True,
        separators=(",", ":"),
    ).encode("utf-8")
    return base64.urlsafe_b64encode(encoded).decode("ascii").rstrip("=")


def decode_run_event_cursor(cursor: str) -> DurableRunEventCursor:
    if not cursor or len(cursor) > 512:
        raise RunEventCursorError("Invalid durable event cursor")
    try:
        padding = "=" * (-len(cursor) % 4)
        decoded = base64.b64decode(
            cursor + padding,
            altchars=b"-_",
            validate=True,
        )
        payload = json.loads(decoded.decode("utf-8"))
        return DurableRunEventCursor.model_validate(payload)
    except (
        binascii.Error,
        UnicodeDecodeError,
        json.JSONDecodeError,
        TypeError,
        ValueError,
    ) as exc:
        raise RunEventCursorError("Invalid durable event cursor") from exc


def _validate_event_batch(
    events: tuple[DurableRunEvent, ...],
    *,
    run_id: UUID,
    session_id: UUID,
    user_id: UUID,
    first_sequence: int,
    first_execution_version: int,
) -> None:
    public_ids: set[UUID] = set()
    policy_version: str | None = None
    for index, event in enumerate(events):
        if (
            event.run_id != run_id
            or event.session_id != session_id
            or event.user_id != user_id
        ):
            raise DurabilityError("Durable replay identity changed")
        if policy_version is None:
            policy_version = event.policy_version
        elif event.policy_version != policy_version:
            raise DurabilityError("Durable replay policy version changed")
        if event.public_id in public_ids:
            raise DurabilityError("Durable replay contains a duplicate event")
        public_ids.add(event.public_id)
        if event.sequence != first_sequence + index:
            raise DurabilityError(
                "Durable event sequences must be contiguous"
            )
        if event.execution_version != first_execution_version + index:
            raise DurabilityError(
                "Durable execution versions must be contiguous"
            )
        if event.execution_version != event.sequence + 1:
            raise DurabilityError(
                "Durable event sequence and execution version do not align"
            )


def validate_orchestration_progress(
    previous: OrchestrationState,
    current: OrchestrationState,
) -> None:
    if previous.run_id != current.run_id or previous.plan_id != current.plan_id:
        raise DurabilityError("Replay cannot change run or plan identity")
    if PHASE_INDEX[current.phase] < PHASE_INDEX[previous.phase]:
        raise DurabilityError("Replay cannot regress orchestration phase")
    previous_artifacts = {
        artifact.artifact_id for artifact in previous.admitted_artifacts
    }
    current_artifacts = {
        artifact.artifact_id for artifact in current.admitted_artifacts
    }
    if not previous_artifacts.issubset(current_artifacts):
        raise DurabilityError("Replay cannot discard admitted artifacts")
    current_nodes = {node.node_id: node for node in current.capabilities}
    for node in previous.capabilities:
        if node.node_id not in current_nodes:
            raise DurabilityError("Replay cannot remove capability nodes")
        if (
            node.state in CAPABILITY_TERMINAL_STATES
            and current_nodes[node.node_id].state is not node.state
        ):
            raise DurabilityError("Replay cannot change terminal capability state")
        if (
            node.state is CapabilityWorkState.ACTIVE
            and current_nodes[node.node_id].state is CapabilityWorkState.QUEUED
        ):
            raise DurabilityError("Replay cannot return active work to queued")
    current_sections = {
        section.section_id: section for section in current.sections
    }
    for section in previous.sections:
        if section.section_id not in current_sections:
            raise DurabilityError("Replay cannot remove response sections")
        if (
            section.state in SECTION_TERMINAL_STATES
            and current_sections[section.section_id].state is not section.state
        ):
            raise DurabilityError("Replay cannot change terminal section state")
    if previous.terminal_state is not None and current != previous:
        raise DurabilityError("Replay cannot mutate a terminal orchestration state")


def _event(row) -> DurableRunEvent:
    return DurableRunEvent(
        public_id=row["public_id"],
        run_id=row["run_id"],
        session_id=row["session_id"],
        user_id=row["user_id"],
        sequence=row["sequence"],
        execution_version=row["execution_version"],
        event_type=row["event_type"],
        capability=row["capability"],
        status=row["status"],
        payload=row["payload"],
        created_at=row["created_at"],
    )


def _owner_parameters(
    run_id: UUID,
    session_id: UUID,
    user_id: UUID,
) -> dict[str, UUID]:
    return {
        "run_id": run_id,
        "session_id": session_id,
        "user_id": user_id,
    }


def _require_aware(value: datetime) -> None:
    if value.tzinfo is None or value.utcoffset() is None:
        raise ValueError("Durability timestamps must be timezone-aware")


def _require_idempotent_event(
    event: DurableRunEvent,
    *,
    event_type: DurableEventType,
    payload: dict[str, object],
) -> None:
    if event.event_type is not event_type:
        raise DurabilityError("Durable event identifier was reused for another action")
    if any(event.payload.get(key) != value for key, value in payload.items()):
        raise DurabilityError("Durable event retry does not match the original action")


def _durable_status_for_state(state: OrchestrationState) -> DurableRunStatus:
    if state.terminal_state is None:
        return DurableRunStatus.RUNNING
    return {
        "complete": DurableRunStatus.COMPLETED,
        "degraded_complete": DurableRunStatus.PARTIAL,
        "clarification_result": DurableRunStatus.PARTIAL,
        "cancelled": DurableRunStatus.CANCELLED,
    }[state.terminal_state.value]
