from __future__ import annotations

import asyncio
from datetime import UTC, datetime, timedelta
from uuid import uuid4

import pytest

from backend.ask.orchestration import (
    CapabilityTerminalState,
    CapabilityWorkState,
    DurableRunExecutionCoordinator,
    OrchestratorCapability,
    ProvenanceClass,
    RunExecutionError,
    activate_capability,
    recover_interrupted_capabilities,
)
from backend.tests.test_ask_ai_orchestration_scheduler import (
    _fanout_state,
    _NodeSpec,
    _RequestFactory,
)

NOW = datetime(2026, 7, 27, 12, 0, tzinfo=UTC)


def test_interrupted_active_capability_becomes_safe_terminal_outcome() -> None:
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

    recovered, node_ids = recover_interrupted_capabilities(active, now=NOW)
    recovered_node = next(
        item for item in recovered.capabilities if item.node_id == node.node_id
    )

    assert node_ids == (node.node_id,)
    assert next(
        item for item in active.capabilities if item.node_id == node.node_id
    ).state is CapabilityWorkState.ACTIVE
    assert recovered_node.state is CapabilityTerminalState.UNAVAILABLE
    assert recovered_node.result is not None
    assert (
        recovered_node.result.safe_error_code
        == "CAPABILITY_EXECUTION_INTERRUPTED"
    )
    assert recovered_node.result.timing.duration_ms == 0


def test_recovery_without_active_nodes_is_identity_preserving() -> None:
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

    recovered, node_ids = recover_interrupted_capabilities(state, now=NOW)

    assert recovered is state
    assert node_ids == ()


def test_recovery_refuses_naive_time() -> None:
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

    with pytest.raises(ValueError, match="timezone-aware"):
        recover_interrupted_capabilities(
            state,
            now=datetime(2026, 7, 27, 12, 0),
        )


def test_coordinator_refuses_unbounded_execution_inputs() -> None:
    class _UnusedDriver:
        async def advance(self, state):
            return state

    coordinator = DurableRunExecutionCoordinator(
        store=object(),  # type: ignore[arg-type]
        driver=_UnusedDriver(),
    )

    with pytest.raises(ValueError, match="TTL"):
        asyncio.run(
            coordinator.execute(
                run_id=uuid4(),
                session_id=uuid4(),
                user_id=uuid4(),
                lease_ttl=timedelta(0),
            )
        )
    with pytest.raises(ValueError, match="max steps"):
        asyncio.run(
            coordinator.execute(
                run_id=uuid4(),
                session_id=uuid4(),
                user_id=uuid4(),
                lease_ttl=timedelta(seconds=1),
                max_steps=10_001,
            )
        )


def test_coordinator_clock_must_be_timezone_aware() -> None:
    class _UnusedDriver:
        async def advance(self, state):
            return state

    coordinator = DurableRunExecutionCoordinator(
        store=object(),  # type: ignore[arg-type]
        driver=_UnusedDriver(),
        clock=lambda: datetime(2026, 7, 27, 12, 0),
    )

    with pytest.raises(RunExecutionError, match="timezone-aware"):
        coordinator._now()
