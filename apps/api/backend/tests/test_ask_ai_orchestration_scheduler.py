from __future__ import annotations

import asyncio
import threading
import time
from dataclasses import dataclass
from datetime import UTC, datetime, timedelta
from uuid import UUID

import pytest
from pydantic import ValidationError

from backend.ask.decision import KnowledgeMode
from backend.ask.orchestration import (
    CapabilityBinding,
    CapabilityInvocation,
    CapabilityNode,
    CapabilityNodePlan,
    CapabilityRequest,
    CapabilityResult,
    CapabilityScope,
    CapabilityTerminalState,
    CapabilityTiming,
    CapabilityWorkState,
    ExecutionMode,
    OrchestrationPhase,
    OrchestrationState,
    OrchestratorCapability,
    ParticipationClass,
    ProvenanceClass,
    SchedulerConfig,
    SchedulerError,
    SectionNode,
    approve_work_plan,
    execute_ready_phase,
    scheduler_report_json,
)
from backend.tests.test_ask_ai_orchestration_state_machine import (
    PLAN_ID,
    RUN_ID,
    _approved_plan,
    _interpreted_state,
)

STARTED_AT = datetime(2026, 7, 27, 10, 0, tzinfo=UTC)


@dataclass(frozen=True, slots=True)
class _NodeSpec:
    node_id: str
    capability: OrchestratorCapability
    section_key: str
    provenance_class: ProvenanceClass
    dependencies: tuple[str, ...] = ()
    participation: ParticipationClass = ParticipationClass.SUPPORTING


def _scope(section_keys: tuple[str, ...]) -> CapabilityScope:
    return CapabilityScope(
        atomic_question_ids=("question-1",),
        section_keys=section_keys,
        entity_ids=("entity-1",),
        jurisdiction="India",
    )


def _fanout_state(specs: tuple[_NodeSpec, ...]) -> OrchestrationState:
    section_keys = tuple(dict.fromkeys(spec.section_key for spec in specs))
    scope = _scope(section_keys)
    roles = {
        capability: ParticipationClass.SKIPPED
        for capability in OrchestratorCapability
    }
    roles[OrchestratorCapability.INTENT_CLASSIFIER] = ParticipationClass.MANDATORY
    roles[OrchestratorCapability.ENTITY_RESOLVER] = ParticipationClass.MANDATORY
    for spec in specs:
        roles[spec.capability] = spec.participation

    node_capabilities = {
        spec.node_id: spec.capability for spec in specs
    }
    node_capabilities[OrchestratorCapability.ENTITY_RESOLVER.value] = (
        OrchestratorCapability.ENTITY_RESOLVER
    )
    dependencies = {
        capability: ()
        for capability in OrchestratorCapability
    }
    for spec in specs:
        dependency_capabilities = tuple(
            dict.fromkeys(
                node_capabilities[dependency] for dependency in spec.dependencies
            )
        )
        dependencies[spec.capability] = tuple(
            dict.fromkeys(
                (*dependencies[spec.capability], *dependency_capabilities)
            )
        )

    capability_nodes: list[CapabilityNodePlan] = [
        CapabilityNodePlan(
            node_id=OrchestratorCapability.INTENT_CLASSIFIER.value,
            capability=OrchestratorCapability.INTENT_CLASSIFIER,
            participation=ParticipationClass.MANDATORY,
        ),
        CapabilityNodePlan(
            node_id=OrchestratorCapability.ENTITY_RESOLVER.value,
            capability=OrchestratorCapability.ENTITY_RESOLVER,
            participation=ParticipationClass.MANDATORY,
        ),
    ]
    for capability in OrchestratorCapability:
        if capability in {
            OrchestratorCapability.INTENT_CLASSIFIER,
            OrchestratorCapability.ENTITY_RESOLVER,
        }:
            continue
        matching = tuple(spec for spec in specs if spec.capability is capability)
        if matching:
            capability_nodes.extend(
                CapabilityNodePlan(
                    node_id=spec.node_id,
                    capability=spec.capability,
                    participation=spec.participation,
                    atomic_question_id="question-1",
                    section_key=spec.section_key,
                    provenance_class=spec.provenance_class,
                    dependencies=spec.dependencies,
                )
                for spec in matching
            )
        else:
            capability_nodes.append(
                CapabilityNodePlan(
                    node_id=capability.value,
                    capability=capability,
                    participation=ParticipationClass.SKIPPED,
                )
            )

    sections = tuple(
        _section_for_spec(
            next(spec for spec in specs if spec.section_key == section_key),
            required=index == 0,
        )
        for index, section_key in enumerate(section_keys)
    )
    mode_eligibility = tuple(
        dict.fromkeys(section.knowledge_mode for section in sections)
    )
    state = _interpreted_state(scope)
    state = approve_work_plan(
        state,
        approved_plan=_approved_plan(
            scope,
            dependencies=dependencies,
            roles=roles,
            mode_eligibility=mode_eligibility,
        ),
        capability_nodes=tuple(capability_nodes),
        sections=sections,
    )
    return _replace_phase(state, OrchestrationPhase.EVIDENCE_FAN_OUT)


def _section_for_spec(spec: _NodeSpec, *, required: bool) -> SectionNode:
    mode = {
        ProvenanceClass.INTERNAL_REGULATORY_CORPUS: (
            KnowledgeMode.GROUNDED_REGULATORY
        ),
        ProvenanceClass.LIVE_WEB_SOURCES: KnowledgeMode.LIVE_INTELLIGENCE,
        ProvenanceClass.GENERAL_AI_KNOWLEDGE: KnowledgeMode.GENERAL_AI,
    }[spec.provenance_class]
    return SectionNode(
        section_id=f"section:{spec.section_key}",
        atomic_question_id="question-1",
        section_key=spec.section_key,
        required=required,
        knowledge_mode=mode,
        provenance_class=spec.provenance_class,
    )


def _replace_phase(
    state: OrchestrationState,
    phase: OrchestrationPhase,
) -> OrchestrationState:
    values = state.model_dump(mode="python")
    values["phase"] = phase
    return OrchestrationState.model_validate(values)


class _RequestFactory:
    def __init__(self) -> None:
        self.calls: list[str] = []
        self.ids: dict[str, UUID] = {}

    def __call__(
        self,
        state: OrchestrationState,
        node: CapabilityNode,
    ) -> CapabilityRequest:
        self.calls.append(node.node_id)
        request_id = self.ids.setdefault(
            node.node_id,
            UUID(int=1000 + len(self.ids)),
        )
        plan = state.approved_plan
        assert plan is not None
        resolution = next(
            artifact
            for artifact in state.admitted_artifacts
            if artifact.artifact_id == "resolution-1"
        )
        values = plan.scope.model_dump(mode="python")
        values["atomic_question_ids"] = (node.atomic_question_id,)
        values["section_keys"] = (node.section_key,)
        return CapabilityRequest(
            request_id=request_id,
            run_id=RUN_ID,
            plan_id=PLAN_ID,
            capability=node.capability,
            participation=node.participation,
            scope=CapabilityScope.model_validate(values),
            input_artifacts=(plan, resolution),
        )


def _success_result(
    invocation: CapabilityInvocation,
    *,
    offset: int = 0,
) -> CapabilityResult:
    return CapabilityResult(
        request_id=invocation.request.request_id,
        run_id=invocation.request.run_id,
        capability=invocation.request.capability,
        terminal_state=CapabilityTerminalState.SATISFIED,
        scope_echo=invocation.request.scope,
        timing=CapabilityTiming(
            started_at=STARTED_AT + timedelta(milliseconds=offset),
            completed_at=STARTED_AT + timedelta(milliseconds=offset + 1),
            duration_ms=1,
        ),
    )


class _AsyncExecutor:
    def __init__(self, delay: float = 0.01) -> None:
        self.delay = delay
        self.calls: list[str] = []
        self.active = 0
        self.max_active = 0

    async def execute(
        self,
        invocation: CapabilityInvocation,
    ) -> CapabilityResult:
        self.calls.append(invocation.node.node_id)
        self.active += 1
        self.max_active = max(self.max_active, self.active)
        try:
            await asyncio.sleep(self.delay)
            return _success_result(invocation, offset=len(self.calls))
        finally:
            self.active -= 1


class _RaisingAsyncExecutor:
    async def execute(
        self,
        invocation: CapabilityInvocation,
    ) -> CapabilityResult:
        raise RuntimeError("secret provider connection detail")


class _InvalidAsyncExecutor:
    async def execute(self, invocation: CapabilityInvocation) -> object:
        return {"unexpected": invocation.node.node_id}


class _BlockingExecutor:
    def __init__(self, delay: float = 0.04) -> None:
        self.delay = delay
        self.calls: list[str] = []
        self.thread_ids: set[int] = set()
        self.active = 0
        self.max_active = 0
        self.lock = threading.Lock()

    def execute(self, invocation: CapabilityInvocation) -> CapabilityResult:
        with self.lock:
            self.calls.append(invocation.node.node_id)
            self.thread_ids.add(threading.get_ident())
            self.active += 1
            self.max_active = max(self.max_active, self.active)
        try:
            time.sleep(self.delay)
            return _success_result(invocation, offset=len(self.calls))
        finally:
            with self.lock:
                self.active -= 1


def _three_branch_specs() -> tuple[_NodeSpec, ...]:
    entity = OrchestratorCapability.ENTITY_RESOLVER.value
    return (
        _NodeSpec(
            node_id="regulatory:official",
            capability=OrchestratorCapability.REGULATORY_RETRIEVER,
            section_key="official",
            provenance_class=ProvenanceClass.INTERNAL_REGULATORY_CORPUS,
            dependencies=(entity,),
        ),
        _NodeSpec(
            node_id="graph:official",
            capability=OrchestratorCapability.KNOWLEDGE_GRAPH,
            section_key="official",
            provenance_class=ProvenanceClass.INTERNAL_REGULATORY_CORPUS,
            dependencies=(entity,),
        ),
        _NodeSpec(
            node_id="news:live",
            capability=OrchestratorCapability.NEWS_RETRIEVER,
            section_key="live",
            provenance_class=ProvenanceClass.LIVE_WEB_SOURCES,
            dependencies=(entity,),
        ),
    )


def test_scheduler_config_rejects_unbounded_or_inverted_limits() -> None:
    with pytest.raises(ValidationError):
        SchedulerConfig(max_concurrency=0)
    with pytest.raises(ValidationError, match="cannot exceed"):
        SchedulerConfig(max_concurrency=2, max_blocking_concurrency=3)


def test_selected_independent_nodes_execute_in_stable_bounded_parallel_order() -> None:
    state = _fanout_state(_three_branch_specs())
    executor = _AsyncExecutor()
    binding = CapabilityBinding(ExecutionMode.ASYNC, executor)
    factory = _RequestFactory()

    report = asyncio.run(
        execute_ready_phase(
            state,
            request_factory=factory,
            bindings={
                OrchestratorCapability.REGULATORY_RETRIEVER: binding,
                OrchestratorCapability.KNOWLEDGE_GRAPH: binding,
                OrchestratorCapability.NEWS_RETRIEVER: binding,
            },
            config=SchedulerConfig(
                max_concurrency=2,
                max_blocking_concurrency=1,
            ),
        )
    )

    expected = tuple(spec.node_id for spec in _three_branch_specs())
    assert report.waves[0].node_ids == expected
    assert executor.calls == list(expected)
    assert factory.calls == list(expected)
    assert executor.max_active == 2
    assert all(
        outcome.terminal_state is CapabilityTerminalState.SATISFIED
        for outcome in report.waves[0].outcomes
    )
    assert all(
        node.state is CapabilityTerminalState.SKIPPED
        for node in report.state.capabilities
        if node.participation is ParticipationClass.SKIPPED
    )
    assert scheduler_report_json(
        report
    ) == scheduler_report_json(type(report).model_validate_json(
        scheduler_report_json(report)
    ))


def test_same_phase_dependencies_execute_in_separate_waves() -> None:
    entity = OrchestratorCapability.ENTITY_RESOLVER.value
    regulatory_id = "regulatory:official"
    specs = (
        _NodeSpec(
            node_id=regulatory_id,
            capability=OrchestratorCapability.REGULATORY_RETRIEVER,
            section_key="official",
            provenance_class=ProvenanceClass.INTERNAL_REGULATORY_CORPUS,
            dependencies=(entity,),
        ),
        _NodeSpec(
            node_id="graph:official",
            capability=OrchestratorCapability.KNOWLEDGE_GRAPH,
            section_key="official",
            provenance_class=ProvenanceClass.INTERNAL_REGULATORY_CORPUS,
            dependencies=(regulatory_id,),
        ),
    )
    state = _fanout_state(specs)
    executor = _AsyncExecutor(delay=0)
    binding = CapabilityBinding(ExecutionMode.ASYNC, executor)

    report = asyncio.run(
        execute_ready_phase(
            state,
            request_factory=_RequestFactory(),
            bindings={
                OrchestratorCapability.REGULATORY_RETRIEVER: binding,
                OrchestratorCapability.KNOWLEDGE_GRAPH: binding,
            },
        )
    )

    assert tuple(wave.node_ids for wave in report.waves) == (
        (regulatory_id,),
        ("graph:official",),
    )
    assert executor.calls == [regulatory_id, "graph:official"]


def test_missing_exception_and_malformed_adapters_fail_closed_without_details() -> None:
    state = _fanout_state(_three_branch_specs())
    report = asyncio.run(
        execute_ready_phase(
            state,
            request_factory=_RequestFactory(),
            bindings={
                OrchestratorCapability.KNOWLEDGE_GRAPH: CapabilityBinding(
                    ExecutionMode.ASYNC,
                    _RaisingAsyncExecutor(),
                ),
                OrchestratorCapability.NEWS_RETRIEVER: CapabilityBinding(
                    ExecutionMode.ASYNC,
                    _InvalidAsyncExecutor(),
                ),
            },
        )
    )

    outcomes = {
        outcome.node_id: outcome for outcome in report.waves[0].outcomes
    }
    assert outcomes["regulatory:official"].terminal_state is (
        CapabilityTerminalState.UNAVAILABLE
    )
    assert outcomes["regulatory:official"].safe_error_code == (
        "CAPABILITY_ADAPTER_UNAVAILABLE"
    )
    assert outcomes["graph:official"].terminal_state is (
        CapabilityTerminalState.UNAVAILABLE
    )
    assert outcomes["graph:official"].safe_error_code == (
        "CAPABILITY_EXECUTION_UNAVAILABLE"
    )
    assert outcomes["news:live"].terminal_state is (
        CapabilityTerminalState.INVALID_OUTPUT
    )
    assert outcomes["news:live"].safe_error_code == "CAPABILITY_INVALID_OUTPUT"
    assert "secret provider" not in scheduler_report_json(report)


def test_blocking_adapters_leave_event_loop_responsive_and_bound_pool_pressure() -> None:
    entity = OrchestratorCapability.ENTITY_RESOLVER.value
    specs = tuple(
        _NodeSpec(
            node_id=f"regulatory:section-{index}",
            capability=OrchestratorCapability.REGULATORY_RETRIEVER,
            section_key=f"section-{index}",
            provenance_class=ProvenanceClass.INTERNAL_REGULATORY_CORPUS,
            dependencies=(entity,),
        )
        for index in range(4)
    )
    state = _fanout_state(specs)
    executor = _BlockingExecutor()
    main_thread = threading.get_ident()

    async def scenario():
        task = asyncio.create_task(
            execute_ready_phase(
                state,
                request_factory=_RequestFactory(),
                bindings={
                    OrchestratorCapability.REGULATORY_RETRIEVER: (
                        CapabilityBinding(
                            ExecutionMode.BLOCKING_THREAD,
                            executor,
                        )
                    )
                },
                config=SchedulerConfig(
                    max_concurrency=4,
                    max_blocking_concurrency=2,
                ),
            )
        )
        heartbeats = 0
        while not task.done():
            await asyncio.sleep(0.005)
            heartbeats += 1
        return await task, heartbeats

    report, heartbeats = asyncio.run(scenario())

    assert len(report.waves[0].node_ids) == 4
    assert executor.max_active == 2
    assert executor.thread_ids
    assert main_thread not in executor.thread_ids
    assert heartbeats >= 5


def test_request_factory_failure_keeps_input_state_unchanged() -> None:
    state = _fanout_state((_three_branch_specs()[0],))

    def broken_factory(current, node):
        raise RuntimeError("request build failed")

    with pytest.raises(SchedulerError, match="request construction failed"):
        asyncio.run(
            execute_ready_phase(
                state,
                request_factory=broken_factory,
                bindings={},
            )
        )

    regulatory = next(
        node
        for node in state.capabilities
        if node.node_id == "regulatory:official"
    )
    assert regulatory.state is CapabilityWorkState.QUEUED
