from __future__ import annotations

import json
from enum import StrEnum
from types import MappingProxyType
from typing import Literal, TypeAlias
from uuid import UUID

from pydantic import Field, field_validator, model_validator

from backend.ask.decision.models import KnowledgeMode
from backend.ask.orchestration.contracts import (
    CAPABILITY_CONTRACTS,
    ApprovedWorkPlanPayload,
    ArtifactEnvelope,
    ArtifactKind,
    CandidateClaimPayload,
    CapabilityRequest,
    CapabilityResult,
    CapabilityScope,
    CapabilityTerminalState,
    ContractModel,
    OrchestratorCapability,
    ParticipationClass,
    ProvenanceClass,
    SectionTerminalState,
    VerificationResultPayload,
    VerificationStatus,
    validate_capability_exchange,
)

ORCHESTRATION_STATE_SCHEMA_VERSION = "1"


class OrchestrationPhase(StrEnum):
    REQUEST_SCOPE = "request_scope"
    INTERPRETATION = "interpretation"
    PLAN_APPROVAL = "plan_approval"
    EVIDENCE_FAN_OUT = "evidence_fan_out"
    EVIDENCE_ADMISSION = "evidence_admission"
    STRUCTURED_TRANSFORMATIONS = "structured_transformations"
    SECTION_COMPOSITION = "section_composition"
    VERIFICATION = "verification"
    DETERMINISTIC_MERGE = "deterministic_merge"
    COMPLETION = "completion"


class CapabilityWorkState(StrEnum):
    QUEUED = "queued"
    ACTIVE = "active"


class CapabilityOperation(StrEnum):
    STANDARD = "standard"
    EVIDENCE_INTEGRITY = "evidence_integrity"
    CLAIM_SUPPORT = "claim_support"


class SectionWorkState(StrEnum):
    PLANNED = "planned"
    COLLECTING = "collecting"
    DRAFTABLE = "draftable"
    COMPOSING = "composing"
    VERIFYING = "verifying"
    REVISING = "revising"
    EMPTY = "empty"
    DEGRADED_PENDING = "degraded_pending"


class RunTerminalState(StrEnum):
    COMPLETE = "complete"
    DEGRADED_COMPLETE = "degraded_complete"
    CLARIFICATION_RESULT = "clarification_result"
    CANCELLED = "cancelled"


CapabilityLifecycleState: TypeAlias = CapabilityWorkState | CapabilityTerminalState
SectionLifecycleState: TypeAlias = SectionWorkState | SectionTerminalState

CAPABILITY_TERMINAL_STATES = frozenset(CapabilityTerminalState)
SECTION_TERMINAL_STATES = frozenset(SectionTerminalState)

PHASE_ORDER = tuple(OrchestrationPhase)
PHASE_INDEX = MappingProxyType(
    {phase: index for index, phase in enumerate(PHASE_ORDER)}
)

CAPABILITY_TRANSITIONS = MappingProxyType(
    {
        CapabilityWorkState.QUEUED: frozenset({CapabilityWorkState.ACTIVE}),
        CapabilityWorkState.ACTIVE: frozenset(
            state
            for state in CapabilityTerminalState
            if state is not CapabilityTerminalState.SKIPPED
        ),
    }
)

CAPABILITY_ACTIVATION_PHASES = MappingProxyType(
    {
        (
            OrchestratorCapability.INTENT_CLASSIFIER,
            CapabilityOperation.STANDARD,
        ): frozenset({OrchestrationPhase.INTERPRETATION}),
        (
            OrchestratorCapability.ENTITY_RESOLVER,
            CapabilityOperation.STANDARD,
        ): frozenset({OrchestrationPhase.INTERPRETATION}),
        (
            OrchestratorCapability.REGULATORY_RETRIEVER,
            CapabilityOperation.STANDARD,
        ): frozenset({OrchestrationPhase.EVIDENCE_FAN_OUT}),
        (
            OrchestratorCapability.KNOWLEDGE_GRAPH,
            CapabilityOperation.STANDARD,
        ): frozenset({OrchestrationPhase.EVIDENCE_FAN_OUT}),
        (
            OrchestratorCapability.NEWS_RETRIEVER,
            CapabilityOperation.STANDARD,
        ): frozenset({OrchestrationPhase.EVIDENCE_FAN_OUT}),
        (
            OrchestratorCapability.TIMELINE_BUILDER,
            CapabilityOperation.STANDARD,
        ): frozenset({OrchestrationPhase.STRUCTURED_TRANSFORMATIONS}),
        (
            OrchestratorCapability.GENERAL_AI,
            CapabilityOperation.STANDARD,
        ): frozenset(
            {
                OrchestrationPhase.EVIDENCE_FAN_OUT,
                OrchestrationPhase.EVIDENCE_ADMISSION,
            }
        ),
        (
            OrchestratorCapability.CITATION_VERIFIER,
            CapabilityOperation.EVIDENCE_INTEGRITY,
        ): frozenset({OrchestrationPhase.EVIDENCE_ADMISSION}),
        (
            OrchestratorCapability.RESPONSE_COMPOSER,
            CapabilityOperation.STANDARD,
        ): frozenset({OrchestrationPhase.SECTION_COMPOSITION}),
        (
            OrchestratorCapability.CITATION_VERIFIER,
            CapabilityOperation.CLAIM_SUPPORT,
        ): frozenset({OrchestrationPhase.VERIFICATION}),
        (
            OrchestratorCapability.FOLLOW_UP_GENERATOR,
            CapabilityOperation.STANDARD,
        ): frozenset({OrchestrationPhase.COMPLETION}),
    }
)

SECTION_TRANSITIONS = MappingProxyType(
    {
        SectionWorkState.PLANNED: frozenset(
            {
                SectionWorkState.COLLECTING,
                SectionTerminalState.CANCELLED,
            }
        ),
        SectionWorkState.COLLECTING: frozenset(
            {
                SectionWorkState.DRAFTABLE,
                SectionWorkState.EMPTY,
                SectionWorkState.DEGRADED_PENDING,
                SectionTerminalState.NEEDS_CLARIFICATION,
                SectionTerminalState.CANCELLED,
            }
        ),
        SectionWorkState.DRAFTABLE: frozenset(
            {
                SectionWorkState.COMPOSING,
                SectionTerminalState.READY_WITHOUT_SYNTHESIS,
                SectionTerminalState.CANCELLED,
            }
        ),
        SectionWorkState.COMPOSING: frozenset(
            {
                SectionWorkState.VERIFYING,
                SectionTerminalState.READY,
                SectionTerminalState.READY_WITHOUT_SYNTHESIS,
                SectionWorkState.DEGRADED_PENDING,
                SectionTerminalState.CANCELLED,
            }
        ),
        SectionWorkState.VERIFYING: frozenset(
            {
                SectionTerminalState.READY,
                SectionWorkState.REVISING,
                SectionTerminalState.DEGRADED,
                SectionTerminalState.CANCELLED,
            }
        ),
        SectionWorkState.REVISING: frozenset(
            {
                SectionWorkState.VERIFYING,
                SectionTerminalState.DEGRADED,
                SectionTerminalState.CANCELLED,
            }
        ),
        SectionWorkState.EMPTY: frozenset(
            {
                SectionTerminalState.OMITTED,
                SectionTerminalState.READY,
                SectionTerminalState.EMPTY_BY_EVIDENCE,
                SectionTerminalState.CANCELLED,
            }
        ),
        SectionWorkState.DEGRADED_PENDING: frozenset(
            {
                SectionTerminalState.READY,
                SectionTerminalState.READY_WITHOUT_SYNTHESIS,
                SectionTerminalState.DEGRADED,
                SectionTerminalState.CANCELLED,
            }
        ),
    }
)

FAILURE_TERMINAL_STATES = frozenset(
    {
        CapabilityTerminalState.TIMED_OUT,
        CapabilityTerminalState.UNAVAILABLE,
        CapabilityTerminalState.INVALID_OUTPUT,
        CapabilityTerminalState.CANCELLED,
    }
)
TERMINAL_VERIFICATION_STATES = frozenset(
    {
        VerificationStatus.SUPPORTED,
        VerificationStatus.PARTIALLY_SUPPORTED,
        VerificationStatus.UNSUPPORTED,
        VerificationStatus.CONTRADICTORY,
        VerificationStatus.UNVERIFIABLE,
    }
)


class CapabilityNode(ContractModel):
    node_id: str = Field(min_length=1)
    capability: OrchestratorCapability
    participation: ParticipationClass
    operation: CapabilityOperation = CapabilityOperation.STANDARD
    atomic_question_id: str | None = None
    section_key: str | None = None
    provenance_class: ProvenanceClass | None = None
    dependencies: tuple[str, ...] = ()
    state: CapabilityLifecycleState
    request: CapabilityRequest | None = None
    result: CapabilityResult | None = None

    @field_validator("dependencies")
    @classmethod
    def validate_dependencies(
        cls,
        value: tuple[str, ...],
    ) -> tuple[str, ...]:
        normalized = tuple(item.strip() for item in value)
        if any(not item for item in normalized):
            raise ValueError("Capability dependency IDs cannot be blank")
        if len(set(normalized)) != len(normalized):
            raise ValueError("Capability dependencies must be unique")
        return normalized

    @model_validator(mode="after")
    def validate_lifecycle(self) -> CapabilityNode:
        if self.node_id in self.dependencies:
            raise ValueError("A capability cannot depend on itself")
        if self.capability is OrchestratorCapability.CITATION_VERIFIER:
            if (
                self.participation is not ParticipationClass.SKIPPED
                and self.operation is CapabilityOperation.STANDARD
            ):
                raise ValueError("Selected Citation Verifier nodes require a pass")
        elif self.operation is not CapabilityOperation.STANDARD:
            raise ValueError("Only Citation Verifier has multiple operations")
        scope_parts = (
            self.atomic_question_id,
            self.section_key,
            self.provenance_class,
        )
        if sum(item is not None for item in scope_parts) not in {0, 3}:
            raise ValueError(
                "Scoped capability nodes require question, section, and provenance"
            )
        if (
            self.participation is ParticipationClass.SKIPPED
            and any(item is not None for item in scope_parts)
        ):
            raise ValueError("Skipped capability nodes cannot retain execution scope")
        if self.participation is ParticipationClass.SKIPPED:
            if self.state is not CapabilityTerminalState.SKIPPED:
                raise ValueError("Skipped participation must start and remain skipped")
            if self.request is not None or self.result is not None:
                raise ValueError("Skipped capabilities cannot have execution state")
            return self
        if self.state is CapabilityTerminalState.SKIPPED:
            raise ValueError("Selected capabilities cannot become skipped")
        if self.state is CapabilityWorkState.QUEUED:
            if self.request is not None or self.result is not None:
                raise ValueError("Queued capabilities cannot have execution output")
        elif self.state is CapabilityWorkState.ACTIVE:
            if self.request is None or self.result is not None:
                raise ValueError("Active capabilities require a request only")
        else:
            if self.request is None or self.result is None:
                raise ValueError("Terminal selected capabilities require request and result")
            if self.result.terminal_state is not self.state:
                raise ValueError("Capability node and result terminal states must agree")
        if self.request is not None:
            if self.request.capability is not self.capability:
                raise ValueError("Capability node request identity does not match")
            if self.request.participation is not self.participation:
                raise ValueError("Capability node participation does not match its request")
        return self


class CapabilityNodePlan(ContractModel):
    node_id: str = Field(min_length=1)
    capability: OrchestratorCapability
    participation: ParticipationClass
    operation: CapabilityOperation = CapabilityOperation.STANDARD
    atomic_question_id: str | None = None
    section_key: str | None = None
    provenance_class: ProvenanceClass | None = None
    dependencies: tuple[str, ...] = ()

    @model_validator(mode="after")
    def validate_plan_node(self) -> CapabilityNodePlan:
        CapabilityNode(
            **self.model_dump(mode="python"),
            state=(
                CapabilityTerminalState.SKIPPED
                if self.participation is ParticipationClass.SKIPPED
                else CapabilityWorkState.QUEUED
            ),
        )
        return self


class SectionNode(ContractModel):
    section_id: str = Field(min_length=1)
    atomic_question_id: str = Field(min_length=1)
    section_key: str = Field(min_length=1)
    required: bool
    knowledge_mode: KnowledgeMode
    provenance_class: ProvenanceClass
    state: SectionLifecycleState = SectionWorkState.PLANNED
    material_claim_ids: tuple[str, ...] = ()
    terminal_verification_claim_ids: tuple[str, ...] = ()

    @field_validator("material_claim_ids", "terminal_verification_claim_ids")
    @classmethod
    def validate_claim_ids(
        cls,
        value: tuple[str, ...],
    ) -> tuple[str, ...]:
        normalized = tuple(item.strip() for item in value)
        if any(not item for item in normalized):
            raise ValueError("Section claim IDs cannot contain blank values")
        if len(set(normalized)) != len(normalized):
            raise ValueError("Section claim IDs must be unique")
        return normalized

    @model_validator(mode="after")
    def validate_section(self) -> SectionNode:
        expected_mode = {
            ProvenanceClass.INTERNAL_REGULATORY_CORPUS: (
                KnowledgeMode.GROUNDED_REGULATORY
            ),
            ProvenanceClass.LIVE_WEB_SOURCES: KnowledgeMode.LIVE_INTELLIGENCE,
            ProvenanceClass.GENERAL_AI_KNOWLEDGE: KnowledgeMode.GENERAL_AI,
        }[self.provenance_class]
        if self.knowledge_mode is not expected_mode:
            raise ValueError("Section knowledge mode must match its provenance lane")
        if not set(self.terminal_verification_claim_ids).issubset(
            self.material_claim_ids
        ):
            raise ValueError("Terminal verification must reference a material claim")
        if self.required and self.state is SectionTerminalState.OMITTED:
            raise ValueError("Required sections cannot be omitted")
        if (
            self.state in {
                SectionTerminalState.READY,
                SectionTerminalState.READY_WITHOUT_SYNTHESIS,
                SectionTerminalState.DEGRADED,
            }
            and self.knowledge_mode is KnowledgeMode.GROUNDED_REGULATORY
            and not set(self.material_claim_ids).issubset(
                self.terminal_verification_claim_ids
            )
        ):
            raise ValueError(
                "Grounded material claims must be terminal before section completion"
            )
        return self


class OrchestrationState(ContractModel):
    schema_version: Literal["1"] = ORCHESTRATION_STATE_SCHEMA_VERSION
    run_id: UUID
    plan_id: str = Field(min_length=1)
    policy_version: str = Field(min_length=1)
    phase: OrchestrationPhase
    research_request: ArtifactEnvelope
    approved_plan: ArtifactEnvelope | None = None
    capabilities: tuple[CapabilityNode, ...]
    sections: tuple[SectionNode, ...] = ()
    admitted_artifacts: tuple[ArtifactEnvelope, ...]
    terminal_state: RunTerminalState | None = None

    @model_validator(mode="after")
    def validate_state(self) -> OrchestrationState:
        if self.research_request.payload.kind is not ArtifactKind.RESEARCH_REQUEST:
            raise ValueError("Orchestration requires a Research Request artifact")
        node_ids = tuple(item.node_id for item in self.capabilities)
        if len(set(node_ids)) != len(node_ids):
            raise ValueError("Orchestration capability node IDs must be unique")
        capability_names = tuple(item.capability for item in self.capabilities)
        section_ids = tuple(section.section_id for section in self.sections)
        if len(set(section_ids)) != len(section_ids):
            raise ValueError("Orchestration section IDs must be unique")
        section_targets = tuple(
            (
                section.atomic_question_id,
                section.section_key,
                section.provenance_class,
            )
            for section in self.sections
        )
        if len(set(section_targets)) != len(section_targets):
            raise ValueError("Orchestration section targets must be unique")
        artifact_ids = tuple(
            artifact.artifact_id for artifact in self.admitted_artifacts
        )
        if len(set(artifact_ids)) != len(artifact_ids):
            raise ValueError("Admitted artifact IDs must be unique")
        if self.research_request.artifact_id not in artifact_ids:
            raise ValueError("Research Request must remain admitted")
        if self.approved_plan is None:
            if self.phase not in {
                OrchestrationPhase.REQUEST_SCOPE,
                OrchestrationPhase.INTERPRETATION,
            }:
                raise ValueError("Later phases require an Approved Work Plan")
            if set(node_ids) != {
                OrchestratorCapability.INTENT_CLASSIFIER.value,
                OrchestratorCapability.ENTITY_RESOLVER.value,
            } or set(capability_names) != {
                OrchestratorCapability.INTENT_CLASSIFIER,
                OrchestratorCapability.ENTITY_RESOLVER,
            }:
                raise ValueError(
                    "Pre-plan orchestration contains only interpretation capabilities"
                )
            if self.sections:
                raise ValueError("Sections cannot exist before plan approval")
        else:
            if not isinstance(self.approved_plan.payload, ApprovedWorkPlanPayload):
                raise ValueError("Approved plan artifact has the wrong kind")
            if self.approved_plan.artifact_id not in artifact_ids:
                raise ValueError("Approved Work Plan must remain admitted")
            if set(capability_names) != set(OrchestratorCapability):
                raise ValueError("Approved orchestration must decide every capability")
            if not self.sections:
                raise ValueError("Approved orchestration requires response sections")
            if not any(section.required for section in self.sections):
                raise ValueError("Approved orchestration requires a core section")
            roles = {
                item.capability: item.participation
                for item in self.approved_plan.payload.capability_roles
            }
            dependencies = {
                item.capability: item.dependencies
                for item in self.approved_plan.payload.dependencies
            }
            node_plans = tuple(
                CapabilityNodePlan(
                    node_id=node.node_id,
                    capability=node.capability,
                    participation=node.participation,
                    operation=node.operation,
                    atomic_question_id=node.atomic_question_id,
                    section_key=node.section_key,
                    provenance_class=node.provenance_class,
                    dependencies=node.dependencies,
                )
                for node in self.capabilities
            )
            _validate_capability_node_plan(
                self.approved_plan,
                node_plans,
                self.sections,
                roles,
                dependencies,
            )
        if self.terminal_state is not None:
            if any(
                node.state in {CapabilityWorkState.QUEUED, CapabilityWorkState.ACTIVE}
                for node in self.capabilities
            ):
                raise ValueError("Terminal runs cannot retain active capabilities")
            if any(
                section.state not in SECTION_TERMINAL_STATES
                for section in self.sections
            ):
                raise ValueError("Terminal runs cannot retain active sections")
            if self.approved_plan is None:
                if (
                    self.terminal_state is not RunTerminalState.CLARIFICATION_RESULT
                    or self.phase is not OrchestrationPhase.INTERPRETATION
                ):
                    raise ValueError(
                        "Only an interpretation clarification can finish before a plan"
                    )
            else:
                if self.phase is not OrchestrationPhase.COMPLETION:
                    raise ValueError("Planned terminal runs require the completion phase")
                if self.terminal_state is not _derive_run_terminal_state(self):
                    raise ValueError(
                        "Run terminal state does not match terminal section outcomes"
                    )
        return self


def can_advance_phase(
    current: OrchestrationPhase,
    target: OrchestrationPhase,
) -> bool:
    return PHASE_INDEX[target] == PHASE_INDEX[current] + 1


def can_transition_capability(
    current: CapabilityLifecycleState,
    target: CapabilityLifecycleState,
) -> bool:
    return target in CAPABILITY_TRANSITIONS.get(current, frozenset())


def can_transition_section(
    current: SectionLifecycleState,
    target: SectionLifecycleState,
) -> bool:
    return target in SECTION_TRANSITIONS.get(current, frozenset())


def can_activate_in_phase(
    capability: OrchestratorCapability,
    operation: CapabilityOperation,
    phase: OrchestrationPhase,
) -> bool:
    return phase in CAPABILITY_ACTIVATION_PHASES.get(
        (capability, operation),
        frozenset(),
    )


def initialize_orchestration(
    *,
    run_id: UUID,
    plan_id: str,
    policy_version: str,
    research_request: ArtifactEnvelope,
    entity_participation: ParticipationClass = ParticipationClass.MANDATORY,
) -> OrchestrationState:
    if entity_participation not in {
        ParticipationClass.MANDATORY,
        ParticipationClass.CONDITIONAL_MANDATORY,
        ParticipationClass.SUPPORTING,
        ParticipationClass.SKIPPED,
    }:
        raise ValueError("Entity bootstrap participation is not eligible")
    return OrchestrationState(
        run_id=run_id,
        plan_id=plan_id,
        policy_version=policy_version,
        phase=OrchestrationPhase.REQUEST_SCOPE,
        research_request=research_request,
        capabilities=(
            CapabilityNode(
                node_id=OrchestratorCapability.INTENT_CLASSIFIER.value,
                capability=OrchestratorCapability.INTENT_CLASSIFIER,
                participation=ParticipationClass.MANDATORY,
                state=CapabilityWorkState.QUEUED,
            ),
            CapabilityNode(
                node_id=OrchestratorCapability.ENTITY_RESOLVER.value,
                capability=OrchestratorCapability.ENTITY_RESOLVER,
                participation=entity_participation,
                state=(
                    CapabilityTerminalState.SKIPPED
                    if entity_participation is ParticipationClass.SKIPPED
                    else CapabilityWorkState.QUEUED
                ),
            ),
        ),
        admitted_artifacts=(research_request,),
    )


def advance_phase(
    state: OrchestrationState,
    target: OrchestrationPhase,
) -> OrchestrationState:
    _ensure_active_run(state)
    if not can_advance_phase(state.phase, target):
        raise ValueError("Orchestration phases advance one step and never regress")
    if target is OrchestrationPhase.PLAN_APPROVAL:
        raise ValueError("Plan approval requires approve_work_plan")
    if target is OrchestrationPhase.DETERMINISTIC_MERGE:
        _require_terminal_required_sections(state)
    if target is OrchestrationPhase.COMPLETION:
        _require_terminal_required_sections(state)
    return _replace_state(state, phase=target)


def activate_capability(
    state: OrchestrationState,
    node_id: str,
    request: CapabilityRequest,
) -> OrchestrationState:
    _ensure_active_run(state)
    index, node = _capability_node(state, node_id)
    if node.capability is not request.capability:
        raise ValueError("Capability request does not match its state node")
    if not can_transition_capability(node.state, CapabilityWorkState.ACTIVE):
        raise ValueError("Capability is not queued for activation")
    if not _activation_allowed(node, state.phase):
        raise ValueError("Capability cannot activate in the current phase")
    if request.run_id != state.run_id or request.plan_id != state.plan_id:
        raise ValueError("Capability request does not belong to this run and plan")
    if any(
        existing.request is not None
        and existing.request.request_id == request.request_id
        for existing in state.capabilities
        if existing.node_id != node.node_id
    ):
        raise ValueError("Capability request identity must be unique per state node")
    if request.policy_version != state.policy_version:
        raise ValueError("Capability request policy does not match orchestration")
    if request.participation is not node.participation:
        raise ValueError("Capability request participation does not match the plan")
    expected_scope = (
        state.approved_plan.scope
        if state.approved_plan is not None
        else state.research_request.scope
    )
    expected_scope = _scoped_capability_scope(node, expected_scope)
    if request.scope != expected_scope:
        raise ValueError("Capability request scope does not match the active phase")
    admitted_ids = {
        artifact.artifact_id for artifact in state.admitted_artifacts
    }
    if not set(request.input_artifact_ids).issubset(admitted_ids):
        raise ValueError("Capability request contains an unadmitted input")
    accepted_kinds = set(CAPABILITY_CONTRACTS[node.capability].accepted_inputs)
    if any(
        artifact.payload.kind not in accepted_kinds
        for artifact in request.input_artifacts
    ):
        raise ValueError("Capability request contains an undeclared input kind")
    nodes = {item.node_id: item for item in state.capabilities}
    for dependency in node.dependencies:
        dependency_node = nodes[dependency]
        if dependency_node.state not in CAPABILITY_TERMINAL_STATES:
            raise ValueError("Capability dependency is not terminal")
        if dependency_node.state is CapabilityTerminalState.SKIPPED:
            raise ValueError("A selected dependency cannot be skipped")
    updated = CapabilityNode(
        node_id=node.node_id,
        capability=node.capability,
        participation=node.participation,
        operation=node.operation,
        atomic_question_id=node.atomic_question_id,
        section_key=node.section_key,
        provenance_class=node.provenance_class,
        dependencies=node.dependencies,
        state=CapabilityWorkState.ACTIVE,
        request=request,
    )
    return _replace_capability(state, index, updated)


def finish_capability(
    state: OrchestrationState,
    node_id: str,
    result: CapabilityResult,
) -> OrchestrationState:
    _ensure_active_run(state)
    index, node = _capability_node(state, node_id)
    if node.capability is not result.capability:
        raise ValueError("Capability result does not match its state node")
    if node.state is not CapabilityWorkState.ACTIVE or node.request is None:
        raise ValueError("Only an active capability can become terminal")
    if not can_transition_capability(node.state, result.terminal_state):
        raise ValueError("Capability terminal transition is forbidden")
    validate_capability_exchange(node.request, result)
    if any(
        artifact.provenance is not None
        and node.provenance_class is not None
        and artifact.provenance.provenance_class is not node.provenance_class
        for artifact in result.artifacts
    ):
        raise ValueError("Capability output crossed its provenance-lane boundary")
    admitted_ids = {
        artifact.artifact_id for artifact in state.admitted_artifacts
    }
    output_ids = tuple(artifact.artifact_id for artifact in result.artifacts)
    if len(set(output_ids)) != len(output_ids) or admitted_ids & set(output_ids):
        raise ValueError("Capability output artifact identity must be new and unique")
    sections = _apply_claim_updates(state.sections, result.artifacts)
    updated = CapabilityNode(
        node_id=node.node_id,
        capability=node.capability,
        participation=node.participation,
        operation=node.operation,
        atomic_question_id=node.atomic_question_id,
        section_key=node.section_key,
        provenance_class=node.provenance_class,
        dependencies=node.dependencies,
        state=result.terminal_state,
        request=node.request,
        result=result,
    )
    next_state = _replace_capability(state, index, updated)
    return _replace_state(
        next_state,
        sections=sections,
        admitted_artifacts=(*state.admitted_artifacts, *result.artifacts),
    )


def approve_work_plan(
    state: OrchestrationState,
    *,
    approved_plan: ArtifactEnvelope,
    capability_nodes: tuple[CapabilityNodePlan, ...],
    sections: tuple[SectionNode, ...],
) -> OrchestrationState:
    _ensure_active_run(state)
    if state.phase is not OrchestrationPhase.INTERPRETATION:
        raise ValueError("Work plan approval occurs only after interpretation")
    if state.approved_plan is not None:
        raise ValueError("The work plan is immutable after approval")
    if not isinstance(approved_plan.payload, ApprovedWorkPlanPayload):
        raise ValueError("Plan approval requires an Approved Work Plan artifact")
    if approved_plan.payload.plan_id != state.plan_id:
        raise ValueError("Approved plan identity does not match orchestration")
    if approved_plan.artifact_id in {
        artifact.artifact_id for artifact in state.admitted_artifacts
    }:
        raise ValueError("Approved plan artifact identity must be new")
    _require_interpretation_terminal(state)
    if any(
        section.atomic_question_id
        not in approved_plan.scope.atomic_question_ids
        or section.section_key not in approved_plan.scope.section_keys
        for section in sections
    ):
        raise ValueError("Response sections must remain inside approved scope")
    if any(
        section.knowledge_mode not in approved_plan.payload.mode_eligibility
        for section in sections
    ):
        raise ValueError("Response section mode is not eligible in the approved plan")
    roles = {
        item.capability: item.participation
        for item in approved_plan.payload.capability_roles
    }
    dependencies = {
        item.capability: item.dependencies
        for item in approved_plan.payload.dependencies
    }
    if set(roles) != set(OrchestratorCapability):
        raise ValueError("Approved plan must decide every Orchestrator capability")
    if set(dependencies) != set(OrchestratorCapability):
        raise ValueError("Approved plan must declare every dependency set")
    _validate_capability_node_plan(
        approved_plan,
        capability_nodes,
        sections,
        roles,
        dependencies,
    )
    existing = {node.node_id: node for node in state.capabilities}
    nodes: list[CapabilityNode] = []
    for planned in capability_nodes:
        if planned.node_id in existing:
            current = existing[planned.node_id]
            if (
                planned.capability is not current.capability
                or planned.participation is not current.participation
                or planned.operation is not current.operation
                or planned.dependencies
                or planned.atomic_question_id is not None
                or planned.section_key is not None
                or planned.provenance_class is not None
            ):
                raise ValueError(
                    "Approved interpretation roles must match completed bootstrap work"
                )
            nodes.append(current)
            continue
        nodes.append(
            CapabilityNode(
                **planned.model_dump(mode="python"),
                state=(
                    CapabilityTerminalState.SKIPPED
                    if planned.participation is ParticipationClass.SKIPPED
                    else CapabilityWorkState.QUEUED
                ),
            )
        )
    return OrchestrationState(
        run_id=state.run_id,
        plan_id=state.plan_id,
        policy_version=state.policy_version,
        phase=OrchestrationPhase.PLAN_APPROVAL,
        research_request=state.research_request,
        approved_plan=approved_plan,
        capabilities=tuple(nodes),
        sections=sections,
        admitted_artifacts=(*state.admitted_artifacts, approved_plan),
    )


def transition_section(
    state: OrchestrationState,
    section_id: str,
    target: SectionLifecycleState,
) -> OrchestrationState:
    _ensure_active_run(state)
    index, section = _section_node(state, section_id)
    if not can_transition_section(section.state, target):
        raise ValueError("Section lifecycle transition is forbidden")
    if target is SectionTerminalState.OMITTED and section.required:
        raise ValueError("Required sections cannot be omitted")
    updated = SectionNode(
        section_id=section.section_id,
        atomic_question_id=section.atomic_question_id,
        section_key=section.section_key,
        required=section.required,
        knowledge_mode=section.knowledge_mode,
        provenance_class=section.provenance_class,
        state=target,
        material_claim_ids=section.material_claim_ids,
        terminal_verification_claim_ids=(
            section.terminal_verification_claim_ids
        ),
    )
    sections = list(state.sections)
    sections[index] = updated
    return _replace_state(state, sections=tuple(sections))


def finalize_clarification(state: OrchestrationState) -> OrchestrationState:
    _ensure_active_run(state)
    if state.phase is not OrchestrationPhase.INTERPRETATION:
        raise ValueError("Early clarification can complete only interpretation")
    _require_interpretation_terminal(state)
    if not any(
        node.state is CapabilityTerminalState.AMBIGUOUS
        for node in state.capabilities
    ):
        raise ValueError("Clarification completion requires material ambiguity")
    return _replace_state(
        state,
        terminal_state=RunTerminalState.CLARIFICATION_RESULT,
    )


def finalize_orchestration(state: OrchestrationState) -> OrchestrationState:
    _ensure_active_run(state)
    if state.phase is not OrchestrationPhase.COMPLETION:
        raise ValueError("Run finalization requires the completion phase")
    _require_terminal_capabilities(state)
    _require_terminal_sections(state)
    return _replace_state(
        state,
        terminal_state=_derive_run_terminal_state(state),
    )


def orchestration_state_json(state: OrchestrationState) -> str:
    return json.dumps(
        state.model_dump(mode="json"),
        ensure_ascii=False,
        separators=(",", ":"),
        sort_keys=True,
    )


def _replace_state(
    state: OrchestrationState,
    **updates: object,
) -> OrchestrationState:
    values = state.model_dump(mode="python")
    values.update(updates)
    return OrchestrationState.model_validate(values)


def _replace_capability(
    state: OrchestrationState,
    index: int,
    node: CapabilityNode,
) -> OrchestrationState:
    capabilities = list(state.capabilities)
    capabilities[index] = node
    return _replace_state(state, capabilities=tuple(capabilities))


def _ensure_active_run(state: OrchestrationState) -> None:
    if state.terminal_state is not None:
        raise ValueError("Terminal orchestration state is immutable")


def _activation_allowed(
    node: CapabilityNode,
    phase: OrchestrationPhase,
) -> bool:
    return can_activate_in_phase(node.capability, node.operation, phase)


def _scoped_capability_scope(
    node: CapabilityNode,
    scope: CapabilityScope,
) -> CapabilityScope:
    if node.atomic_question_id is None or node.section_key is None:
        return scope
    values = scope.model_dump(mode="python")
    values["atomic_question_ids"] = (node.atomic_question_id,)
    values["section_keys"] = (node.section_key,)
    return CapabilityScope.model_validate(values)


def _capability_node(
    state: OrchestrationState,
    node_id: str,
) -> tuple[int, CapabilityNode]:
    for index, node in enumerate(state.capabilities):
        if node.node_id == node_id:
            return index, node
    raise ValueError("Capability node is not declared in this orchestration")


def _section_node(
    state: OrchestrationState,
    section_id: str,
) -> tuple[int, SectionNode]:
    for index, section in enumerate(state.sections):
        if section.section_id == section_id:
            return index, section
    raise ValueError("Section is not declared in this orchestration")


def _require_interpretation_terminal(state: OrchestrationState) -> None:
    nodes = {node.node_id: node for node in state.capabilities}
    for node_id in (
        OrchestratorCapability.INTENT_CLASSIFIER.value,
        OrchestratorCapability.ENTITY_RESOLVER.value,
    ):
        if nodes[node_id].state not in CAPABILITY_TERMINAL_STATES:
            raise ValueError("Interpretation capabilities must be terminal")


def _require_terminal_capabilities(state: OrchestrationState) -> None:
    if any(
        node.state not in CAPABILITY_TERMINAL_STATES
        for node in state.capabilities
    ):
        raise ValueError("Every selected capability must be terminal")


def _require_terminal_sections(state: OrchestrationState) -> None:
    if any(
        section.state not in SECTION_TERMINAL_STATES
        for section in state.sections
    ):
        raise ValueError("Every response section must be terminal")


def _require_terminal_required_sections(state: OrchestrationState) -> None:
    if any(
        section.required and section.state not in SECTION_TERMINAL_STATES
        for section in state.sections
    ):
        raise ValueError("Every core response section must be terminal")


def _validate_capability_node_plan(
    approved_plan: ArtifactEnvelope,
    planned_nodes: tuple[CapabilityNodePlan, ...],
    sections: tuple[SectionNode, ...],
    roles: dict[OrchestratorCapability, ParticipationClass],
    declared_dependencies: dict[
        OrchestratorCapability,
        tuple[OrchestratorCapability, ...],
    ],
) -> None:
    node_ids = tuple(node.node_id for node in planned_nodes)
    if len(set(node_ids)) != len(node_ids):
        raise ValueError("Capability node plan IDs must be unique")
    nodes = {node.node_id: node for node in planned_nodes}
    section_targets = {
        (
            section.atomic_question_id,
            section.section_key,
            section.provenance_class,
        )
        for section in sections
    }
    if {node.capability for node in planned_nodes} != set(OrchestratorCapability):
        raise ValueError("Capability nodes must cover every Orchestrator capability")
    for capability, role in roles.items():
        capability_nodes = tuple(
            node for node in planned_nodes if node.capability is capability
        )
        if not capability_nodes:
            raise ValueError("Every planned capability requires a state node")
        if any(node.participation is not role for node in capability_nodes):
            raise ValueError("Capability node participation must match the plan")
        if role is ParticipationClass.SKIPPED and (
            len(capability_nodes) != 1 or capability_nodes[0].dependencies
        ):
            raise ValueError("Skipped capabilities require one dependency-free node")
        if role is not ParticipationClass.SKIPPED and any(
            node.operation is CapabilityOperation.STANDARD
            and node.capability is OrchestratorCapability.CITATION_VERIFIER
            for node in capability_nodes
        ):
            raise ValueError("Selected Citation Verifier nodes require named passes")
    if (
        roles[OrchestratorCapability.CITATION_VERIFIER]
        is not ParticipationClass.SKIPPED
        and KnowledgeMode.GROUNDED_REGULATORY
        in approved_plan.payload.mode_eligibility
    ):
        verifier_operations = {
            node.operation
            for node in planned_nodes
            if node.capability is OrchestratorCapability.CITATION_VERIFIER
        }
        if verifier_operations != {
            CapabilityOperation.EVIDENCE_INTEGRITY,
            CapabilityOperation.CLAIM_SUPPORT,
        }:
            raise ValueError(
                "Grounded Citation Verifier requires evidence and claim passes"
            )
    for node in planned_nodes:
        if any(dependency_id not in nodes for dependency_id in node.dependencies):
            raise ValueError("Capability node dependency is not declared")

    visiting: set[str] = set()
    visited: set[str] = set()

    def visit(node_id: str) -> None:
        if node_id in visiting:
            raise ValueError("Capability dependency graph cannot contain a cycle")
        if node_id in visited:
            return
        visiting.add(node_id)
        for dependency in nodes[node_id].dependencies:
            visit(dependency)
        visiting.remove(node_id)
        visited.add(node_id)

    for node_id in node_ids:
        visit(node_id)

    for node in planned_nodes:
        if (
            node.atomic_question_id is not None
            and node.atomic_question_id
            not in approved_plan.scope.atomic_question_ids
        ):
            raise ValueError("Capability node question exceeds approved scope")
        if (
            node.section_key is not None
            and node.section_key not in approved_plan.scope.section_keys
        ):
            raise ValueError("Capability node section exceeds approved scope")
        if (
            node.atomic_question_id is not None
            and (
                node.atomic_question_id,
                node.section_key,
                node.provenance_class,
            )
            not in section_targets
        ):
            raise ValueError("Capability node scope has no declared response section")
        for dependency_id in node.dependencies:
            dependency = nodes[dependency_id]
            if dependency.participation is ParticipationClass.SKIPPED:
                raise ValueError("Selected capability dependencies cannot be skipped")
            if (
                dependency.capability is not node.capability
                and dependency.capability
                not in declared_dependencies[node.capability]
            ):
                raise ValueError(
                    "Capability node dependency exceeds the approved plan"
                )
            dependency_phases = CAPABILITY_ACTIVATION_PHASES.get(
                (dependency.capability, dependency.operation),
                frozenset(),
            )
            node_phases = CAPABILITY_ACTIVATION_PHASES.get(
                (node.capability, node.operation),
                frozenset(),
            )
            if not any(
                PHASE_INDEX[dependency_phase] <= PHASE_INDEX[node_phase]
                for dependency_phase in dependency_phases
                for node_phase in node_phases
            ):
                raise ValueError(
                    "Capability node depends on work from a later phase"
                )


def _apply_claim_updates(
    sections: tuple[SectionNode, ...],
    artifacts: tuple[ArtifactEnvelope, ...],
) -> tuple[SectionNode, ...]:
    updated = list(sections)
    for artifact in artifacts:
        if (
            isinstance(artifact.payload, CandidateClaimPayload)
            and artifact.payload.material
            and artifact.provenance is not None
            and artifact.provenance.knowledge_mode
            is KnowledgeMode.GROUNDED_REGULATORY
        ):
            matched = False
            for index, section in enumerate(updated):
                if (
                    section.section_key in artifact.scope.section_keys
                    and section.atomic_question_id
                    in artifact.scope.atomic_question_ids
                    and section.knowledge_mode
                    is KnowledgeMode.GROUNDED_REGULATORY
                ):
                    if section.state in SECTION_TERMINAL_STATES:
                        raise ValueError(
                            "Material claims cannot enter a terminal section"
                        )
                    values = section.model_dump(mode="python")
                    values["material_claim_ids"] = (
                        *section.material_claim_ids,
                        artifact.artifact_id,
                    )
                    updated[index] = SectionNode.model_validate(values)
                    matched = True
            if not matched:
                raise ValueError("Material claim does not target a grounded section")
        if isinstance(artifact.payload, VerificationResultPayload):
            if artifact.payload.target_kind is not ArtifactKind.CANDIDATE_CLAIM:
                continue
            if artifact.payload.status not in TERMINAL_VERIFICATION_STATES:
                continue
            claim_id = artifact.payload.target_artifact_id
            matched = False
            for index, section in enumerate(updated):
                if claim_id in section.material_claim_ids:
                    values = section.model_dump(mode="python")
                    values["terminal_verification_claim_ids"] = (
                        *section.terminal_verification_claim_ids,
                        claim_id,
                    )
                    updated[index] = SectionNode.model_validate(values)
                    matched = True
            if not matched:
                raise ValueError("Verification result references an unknown claim")
    return tuple(updated)


def _is_degraded_completion(
    state: OrchestrationState,
    required_sections: tuple[SectionNode, ...],
) -> bool:
    if any(
        section.state
        in {
            SectionTerminalState.DEGRADED,
            SectionTerminalState.CANCELLED,
        }
        for section in required_sections
    ):
        return True
    return any(
        node.participation
        in {
            ParticipationClass.MANDATORY,
            ParticipationClass.CONDITIONAL_MANDATORY,
        }
        and node.state
        in {
            *FAILURE_TERMINAL_STATES,
            CapabilityTerminalState.AMBIGUOUS,
        }
        for node in state.capabilities
    )


def _derive_run_terminal_state(state: OrchestrationState) -> RunTerminalState:
    required_sections = tuple(
        section for section in state.sections if section.required
    )
    if required_sections and all(
        section.state is SectionTerminalState.CANCELLED
        for section in required_sections
    ):
        return RunTerminalState.CANCELLED
    if any(
        section.state is SectionTerminalState.NEEDS_CLARIFICATION
        for section in required_sections
    ):
        return RunTerminalState.CLARIFICATION_RESULT
    if _is_degraded_completion(state, required_sections):
        return RunTerminalState.DEGRADED_COMPLETE
    return RunTerminalState.COMPLETE
