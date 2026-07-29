from __future__ import annotations

from datetime import UTC, datetime
from uuid import UUID, uuid4

import pytest

from backend.ask.orchestration import (
    DURABILITY_POLICY_VERSION,
    DurabilityError,
    DurableEventType,
    DurableRunEvent,
    DurableRunStatus,
    RunEventCursorError,
    decode_run_event_cursor,
    encode_run_event_cursor,
    finalize_orchestration,
    replay_orchestration,
    run_event_read_model,
)
from backend.tests.test_ask_ai_orchestration_scheduler import _scope
from backend.tests.test_ask_ai_orchestration_state_machine import (
    RUN_ID,
    _complete_state_before_finalization,
    _interpreted_state,
)

NOW = datetime(2026, 7, 27, 12, 0, tzinfo=UTC)
SESSION_ID = UUID("a5bb1fc9-ebda-47fb-9454-72ba0b255b3a")
USER_ID = UUID("c65c81a4-b99f-420a-b3f2-6ca8e60ab68d")


def _event(
    *,
    sequence: int,
    execution_version: int,
    run_id: UUID = RUN_ID,
    public_id: UUID | None = None,
    policy_version: str = DURABILITY_POLICY_VERSION,
    payload: dict[str, object] | None = None,
) -> DurableRunEvent:
    state = _interpreted_state(_scope(("official_sources",)))
    return DurableRunEvent(
        public_id=public_id or uuid4(),
        run_id=run_id,
        session_id=SESSION_ID,
        user_id=USER_ID,
        sequence=sequence,
        execution_version=execution_version,
        event_type=DurableEventType.STATE_TRANSITION,
        status=DurableRunStatus.RUNNING,
        payload=(
            {"orchestration_state": state.model_dump(mode="json")}
            if payload is None
            else payload
        ),
        created_at=NOW,
        policy_version=policy_version,
    )


def test_read_model_is_versioned_owner_neutral_and_state_bearing() -> None:
    state = _interpreted_state(_scope(("official_sources",)))
    event = _event(
        sequence=0,
        execution_version=1,
        payload={
            "orchestration_state": state.model_dump(mode="json"),
            "lease_id": "internal-worker-identity",
        },
    )

    model = run_event_read_model(event)
    encoded = model.model_dump(mode="json")

    assert model.schema_version == "1"
    assert model.policy_version == DURABILITY_POLICY_VERSION
    assert model.orchestration_state == state
    assert encoded["event_id"] == str(event.public_id)
    assert "user_id" not in encoded
    assert "session_id" not in encoded
    assert "payload" not in encoded
    assert "internal-worker-identity" not in str(encoded)


def test_cursor_round_trip_binds_exact_run_event_and_version() -> None:
    model = run_event_read_model(
        _event(sequence=0, execution_version=1),
    )

    cursor = encode_run_event_cursor(model)
    decoded = decode_run_event_cursor(cursor)

    assert decoded.event_id == model.event_id
    assert decoded.run_id == model.run_id
    assert decoded.sequence == 0
    assert decoded.execution_version == 1
    assert str(model.run_id) not in cursor


@pytest.mark.parametrize(
    "cursor",
    ("", "not-base64!", "e30", "a" * 513),
)
def test_cursor_refuses_malformed_or_unsupported_values(cursor: str) -> None:
    with pytest.raises(RunEventCursorError, match="Invalid"):
        decode_run_event_cursor(cursor)


def test_cursor_model_refuses_crossed_sequence_and_version() -> None:
    model = run_event_read_model(
        _event(sequence=0, execution_version=1),
    ).model_copy(update={"sequence": 3, "execution_version": 2})

    with pytest.raises(ValueError, match="align"):
        encode_run_event_cursor(model)


@pytest.mark.parametrize(
    ("events", "message"),
    (
        (
            (
                _event(sequence=1, execution_version=1),
            ),
            "sequences",
        ),
        (
            (
                _event(sequence=0, execution_version=1),
                _event(sequence=2, execution_version=2),
            ),
            "sequences",
        ),
        (
            (
                _event(sequence=0, execution_version=1),
                _event(sequence=1, execution_version=3),
            ),
            "versions",
        ),
    ),
)
def test_replay_refuses_sequence_or_version_gaps(
    events: tuple[DurableRunEvent, ...],
    message: str,
) -> None:
    with pytest.raises(DurabilityError, match=message):
        replay_orchestration(events)


def test_replay_refuses_crossed_identity_policy_and_duplicate_event() -> None:
    first = _event(sequence=0, execution_version=1)
    cases = (
        (
            first,
            _event(
                sequence=1,
                execution_version=2,
                run_id=uuid4(),
            ),
            "identity",
        ),
        (
            first,
            _event(
                sequence=1,
                execution_version=2,
                policy_version="other-policy",
            ),
            "policy",
        ),
        (
            first,
            _event(
                sequence=1,
                execution_version=2,
                public_id=first.public_id,
            ),
            "duplicate",
        ),
    )

    for left, right, message in cases:
        with pytest.raises(DurabilityError, match=message):
            replay_orchestration((left, right))


def test_replay_refuses_state_from_another_run() -> None:
    state = _interpreted_state(_scope(("official_sources",)))
    event = _event(
        sequence=0,
        execution_version=1,
        run_id=uuid4(),
        payload={"orchestration_state": state.model_dump(mode="json")},
    )

    with pytest.raises(DurabilityError, match="another run"):
        replay_orchestration((event,))


def test_replay_refuses_non_state_event_after_terminal_state() -> None:
    terminal = finalize_orchestration(
        _complete_state_before_finalization(_scope(("official_sources",)))
    )
    terminal_event = _event(
        sequence=0,
        execution_version=1,
        payload={"orchestration_state": terminal.model_dump(mode="json")},
    )
    later_event = _event(
        sequence=1,
        execution_version=2,
        payload={"lease_id": str(uuid4())},
    ).model_copy(update={"event_type": DurableEventType.LEASE_ACQUIRED})

    with pytest.raises(DurabilityError, match="after a terminal"):
        replay_orchestration((terminal_event, later_event))


def test_read_model_requires_state_for_state_bearing_events() -> None:
    event = _event(sequence=0, execution_version=1, payload={})

    with pytest.raises(DurabilityError, match="does not contain"):
        run_event_read_model(event)


@pytest.mark.parametrize(
    ("change", "message"),
    (
        ({"status": "provider HTTP 500"}, "read model"),
        ({"capability": "internal_prompt_runner"}, "read model"),
    ),
)
def test_read_model_refuses_unsafe_lifecycle_fields(
    change: dict[str, object],
    message: str,
) -> None:
    event = _event(sequence=0, execution_version=1).model_copy(update=change)

    with pytest.raises(DurabilityError, match=message):
        run_event_read_model(event)
