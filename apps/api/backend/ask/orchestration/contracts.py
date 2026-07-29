from __future__ import annotations

import json
import re
from datetime import datetime
from enum import StrEnum
from types import MappingProxyType
from typing import Annotated, Any, Literal, Protocol, Self
from uuid import UUID

from pydantic import (
    BaseModel,
    ConfigDict,
    Field,
    TypeAdapter,
    field_validator,
    model_validator,
)

from backend.ask.decision.models import KnowledgeMode, TimeDimension

ORCHESTRATION_SCHEMA_VERSION = "1"
ORCHESTRATION_POLICY_VERSION = "ask-ai-orchestrator-v1"
SAFE_ERROR_CODE = re.compile(r"^[A-Z][A-Z0-9_]{0,99}$")


class ParticipationClass(StrEnum):
    MANDATORY = "mandatory"
    CONDITIONAL_MANDATORY = "conditional_mandatory"
    SUPPORTING = "supporting"
    OPTIONAL = "optional"
    FALLBACK = "fallback"
    SKIPPED = "skipped"


class LatencyProfileName(StrEnum):
    FAST_EXACT = "fast_exact"
    FOCUSED_GROUNDED = "focused_grounded"
    LIVE_COMBINED = "live_combined"
    DEEP_STRUCTURED = "deep_structured"
    COMPOSITE_RESEARCH = "composite_research"


class CapabilityTerminalState(StrEnum):
    SATISFIED = "satisfied"
    PARTIAL = "partial"
    NO_MATCH = "no_match"
    AMBIGUOUS = "ambiguous"
    CONTRADICTORY = "contradictory"
    TIMED_OUT = "timed_out"
    UNAVAILABLE = "unavailable"
    INVALID_OUTPUT = "invalid_output"
    SUPERSEDED = "superseded"
    CANCELLED = "cancelled"
    SKIPPED = "skipped"


class SectionTerminalState(StrEnum):
    READY = "ready"
    READY_WITHOUT_SYNTHESIS = "ready_without_synthesis"
    DEGRADED = "degraded"
    EMPTY_BY_EVIDENCE = "empty_by_evidence"
    OMITTED = "omitted"
    NEEDS_CLARIFICATION = "needs_clarification"
    CANCELLED = "cancelled"


class OrchestratorCapability(StrEnum):
    INTENT_CLASSIFIER = "intent_classifier"
    ENTITY_RESOLVER = "entity_resolver"
    REGULATORY_RETRIEVER = "regulatory_retriever"
    KNOWLEDGE_GRAPH = "knowledge_graph"
    TIMELINE_BUILDER = "timeline_builder"
    NEWS_RETRIEVER = "news_retriever"
    GENERAL_AI = "general_ai"
    CITATION_VERIFIER = "citation_verifier"
    RESPONSE_COMPOSER = "response_composer"
    FOLLOW_UP_GENERATOR = "follow_up_generator"


class ArtifactProducer(StrEnum):
    USER_CONTEXT = "user_context"
    DECISION_ENGINE = "decision_engine"
    ORCHESTRATOR = "orchestrator"
    INTENT_CLASSIFIER = OrchestratorCapability.INTENT_CLASSIFIER
    ENTITY_RESOLVER = OrchestratorCapability.ENTITY_RESOLVER
    REGULATORY_RETRIEVER = OrchestratorCapability.REGULATORY_RETRIEVER
    KNOWLEDGE_GRAPH = OrchestratorCapability.KNOWLEDGE_GRAPH
    TIMELINE_BUILDER = OrchestratorCapability.TIMELINE_BUILDER
    NEWS_RETRIEVER = OrchestratorCapability.NEWS_RETRIEVER
    GENERAL_AI = OrchestratorCapability.GENERAL_AI
    CITATION_VERIFIER = OrchestratorCapability.CITATION_VERIFIER
    RESPONSE_COMPOSER = OrchestratorCapability.RESPONSE_COMPOSER
    FOLLOW_UP_GENERATOR = OrchestratorCapability.FOLLOW_UP_GENERATOR


class ArtifactKind(StrEnum):
    RESEARCH_REQUEST = "research_request"
    INTERPRETATION_RESULT = "interpretation_result"
    RESOLUTION_SET = "resolution_set"
    APPROVED_WORK_PLAN = "approved_work_plan"
    EVIDENCE_UNIT = "evidence_unit"
    STRUCTURED_FACT = "structured_fact"
    TIMELINE_EVENT = "timeline_event"
    GENERAL_KNOWLEDGE_UNIT = "general_knowledge_unit"
    CANDIDATE_CLAIM = "candidate_claim"
    VERIFICATION_RESULT = "verification_result"
    SECTION_DRAFT = "section_draft"
    FOLLOW_UP_CANDIDATES = "follow_up_candidates"
    COMPLETION_SUMMARY = "completion_summary"


class ProvenanceClass(StrEnum):
    INTERNAL_REGULATORY_CORPUS = "internal_regulatory_corpus"
    LIVE_WEB_SOURCES = "live_web_sources"
    GENERAL_AI_KNOWLEDGE = "general_ai_knowledge"


PROVENANCE_AUTHORITY = {
    ProvenanceClass.INTERNAL_REGULATORY_CORPUS: 3,
    ProvenanceClass.LIVE_WEB_SOURCES: 2,
    ProvenanceClass.GENERAL_AI_KNOWLEDGE: 1,
}


class ContentDerivation(StrEnum):
    DIRECT = "direct"
    EXTRACTED = "extracted"
    INFERRED = "inferred"
    SUMMARIZED = "summarized"
    GENERATED = "generated"


class VerificationStatus(StrEnum):
    PENDING = "pending"
    SUPPORTED = "supported"
    PARTIALLY_SUPPORTED = "partially_supported"
    UNSUPPORTED = "unsupported"
    CONTRADICTORY = "contradictory"
    UNVERIFIABLE = "unverifiable"
    NOT_APPLICABLE = "not_applicable"


class ContractModel(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True, str_strip_whitespace=True)


def _unique(values: tuple[str, ...], label: str) -> tuple[str, ...]:
    normalized = tuple(value.strip() for value in values)
    if any(not value for value in normalized):
        raise ValueError(f"{label} cannot contain blank values")
    if len(set(normalized)) != len(normalized):
        raise ValueError(f"{label} must be unique")
    return normalized


class CapabilityScope(ContractModel):
    atomic_question_ids: tuple[str, ...]
    section_keys: tuple[str, ...]
    entity_ids: tuple[str, ...] = ()
    jurisdiction: str | None = None
    stakeholder: str | None = None
    time_scope: str | None = None
    date_semantics: tuple[TimeDimension, ...] = ()
    constraints: tuple[str, ...] = ()

    @field_validator(
        "atomic_question_ids",
        "section_keys",
        "entity_ids",
        "constraints",
    )
    @classmethod
    def validate_unique_text(
        cls,
        value: tuple[str, ...],
        info: Any,
    ) -> tuple[str, ...]:
        return _unique(value, info.field_name)

    @field_validator("jurisdiction", "stakeholder", "time_scope")
    @classmethod
    def normalize_optional_text(cls, value: str | None) -> str | None:
        if value is None:
            return None
        normalized = value.strip()
        return normalized or None

    @model_validator(mode="after")
    def validate_target_scope(self) -> Self:
        if not self.atomic_question_ids:
            raise ValueError("Capability scope requires an atomic question")
        if not self.section_keys:
            raise ValueError("Capability scope requires a section target")
        if len(set(self.date_semantics)) != len(self.date_semantics):
            raise ValueError("Date semantics must be unique")
        return self


class SourceIdentity(ContractModel):
    source_id: str = Field(min_length=1)
    provenance_class: ProvenanceClass
    title: str = Field(min_length=1)
    uri: str | None = None
    issuer_or_publisher: str | None = None
    publication_at: datetime | None = None
    issue_at: datetime | None = None
    effective_at: datetime | None = None
    event_at: datetime | None = None
    retrieved_at: datetime | None = None

    @field_validator("source_id", "title")
    @classmethod
    def strip_required_text(cls, value: str) -> str:
        normalized = value.strip()
        if not normalized:
            raise ValueError("Source identity text cannot be blank")
        return normalized

    @model_validator(mode="after")
    def validate_source_identity(self) -> Self:
        timestamps = (
            self.publication_at,
            self.issue_at,
            self.effective_at,
            self.event_at,
            self.retrieved_at,
        )
        if any(value is not None and value.tzinfo is None for value in timestamps):
            raise ValueError("Source timestamps must include a timezone")
        if self.provenance_class is ProvenanceClass.GENERAL_AI_KNOWLEDGE:
            raise ValueError("General AI knowledge has no source identity")
        if self.provenance_class is ProvenanceClass.LIVE_WEB_SOURCES:
            if (
                not self.issuer_or_publisher
                or self.publication_at is None
                or self.retrieved_at is None
            ):
                raise ValueError(
                    "Live sources require publisher, publication, and retrieval identity"
                )
        return self


class TransformationStep(ContractModel):
    capability: OrchestratorCapability
    derivation: ContentDerivation
    input_artifact_ids: tuple[str, ...]
    input_provenance: tuple[ProvenanceClass, ...]
    output_provenance: ProvenanceClass

    @field_validator("input_artifact_ids")
    @classmethod
    def validate_inputs(cls, value: tuple[str, ...]) -> tuple[str, ...]:
        normalized = _unique(value, "Transformation input artifact IDs")
        if not normalized:
            raise ValueError("A transformation requires an input artifact")
        return normalized

    @model_validator(mode="after")
    def prevent_authority_upgrade(self) -> Self:
        if not self.input_provenance:
            raise ValueError("A transformation requires input provenance")
        if len(set(self.input_provenance)) != len(self.input_provenance):
            raise ValueError("Transformation input provenance must be unique")
        weakest_input = min(PROVENANCE_AUTHORITY[item] for item in self.input_provenance)
        if PROVENANCE_AUTHORITY[self.output_provenance] > weakest_input:
            raise ValueError("Transformation cannot increase provenance authority")
        return self


class ProvenanceLineage(ContractModel):
    provenance_class: ProvenanceClass
    knowledge_mode: KnowledgeMode
    sources: tuple[SourceIdentity, ...] = ()
    derivation: ContentDerivation
    transformations: tuple[TransformationStep, ...] = ()
    verification_status: VerificationStatus = VerificationStatus.PENDING

    @model_validator(mode="after")
    def validate_lane(self) -> Self:
        expected_mode = {
            ProvenanceClass.INTERNAL_REGULATORY_CORPUS: (
                KnowledgeMode.GROUNDED_REGULATORY
            ),
            ProvenanceClass.LIVE_WEB_SOURCES: KnowledgeMode.LIVE_INTELLIGENCE,
            ProvenanceClass.GENERAL_AI_KNOWLEDGE: KnowledgeMode.GENERAL_AI,
        }[self.provenance_class]
        if self.knowledge_mode is not expected_mode:
            raise ValueError("Knowledge mode must match the provenance lane")
        if self.provenance_class is ProvenanceClass.GENERAL_AI_KNOWLEDGE:
            if self.sources:
                raise ValueError("General AI knowledge cannot fabricate source identity")
            if self.verification_status not in {
                VerificationStatus.PENDING,
                VerificationStatus.NOT_APPLICABLE,
            }:
                raise ValueError("General AI knowledge is not verified as Mode 1")
        elif not self.sources:
            raise ValueError("Official and live factual lineage requires a source")
        if any(
            source.provenance_class is not self.provenance_class
            for source in self.sources
        ):
            raise ValueError("Source identities must remain in one provenance lane")
        if self.derivation is ContentDerivation.DIRECT and self.transformations:
            raise ValueError("Direct content cannot declare transformation steps")
        if self.derivation in {
            ContentDerivation.EXTRACTED,
            ContentDerivation.INFERRED,
            ContentDerivation.SUMMARIZED,
        } and not self.transformations:
            raise ValueError("Derived content requires transformation lineage")
        for previous, current in zip(
            self.transformations,
            self.transformations[1:],
            strict=False,
        ):
            if previous.output_provenance not in current.input_provenance:
                raise ValueError("Transformation provenance chain is discontinuous")
        if (
            self.transformations
            and self.transformations[-1].output_provenance
            is not self.provenance_class
        ):
            raise ValueError("Final transformation output must match artifact provenance")
        return self


class ConfidenceSignals(ContractModel):
    evidence_authority: float | None = Field(default=None, ge=0, le=1)
    retrieval_relevance: float | None = Field(default=None, ge=0, le=1)
    claim_coverage: float | None = Field(default=None, ge=0, le=1)
    source_agreement: float | None = Field(default=None, ge=0, le=1)
    freshness_validity: float | None = Field(default=None, ge=0, le=1)
    scope_resolution: float | None = Field(default=None, ge=0, le=1)
    critical_input_ceiling: float | None = Field(default=None, ge=0, le=1)
    reasons: tuple[str, ...] = ()

    @field_validator("reasons")
    @classmethod
    def validate_reasons(cls, value: tuple[str, ...]) -> tuple[str, ...]:
        return _unique(value, "Confidence reasons")


class ResearchRequestPayload(ContractModel):
    kind: Literal[ArtifactKind.RESEARCH_REQUEST] = ArtifactKind.RESEARCH_REQUEST
    query: str = Field(min_length=1)
    selected_object_ids: tuple[str, ...] = ()
    explicit_constraints: tuple[str, ...] = ()


class InterpretationResultPayload(ContractModel):
    kind: Literal[ArtifactKind.INTERPRETATION_RESULT] = (
        ArtifactKind.INTERPRETATION_RESULT
    )
    primary_intent: str = Field(min_length=1)
    secondary_intents: tuple[str, ...] = ()
    atomic_questions: tuple[str, ...]
    temporal_cues: tuple[str, ...] = ()
    modifiers: tuple[str, ...] = ()
    audience: str | None = None
    requested_form: str | None = None
    interpretation_confidence: float = Field(ge=0, le=1)
    ambiguity_reasons: tuple[str, ...] = ()


class ResolutionSetPayload(ContractModel):
    kind: Literal[ArtifactKind.RESOLUTION_SET] = ArtifactKind.RESOLUTION_SET
    canonical_entity_ids: tuple[str, ...]
    original_mentions: tuple[str, ...]
    aliases: tuple[str, ...] = ()
    alternatives: tuple[str, ...] = ()
    resolution_confidence: float = Field(ge=0, le=1)
    needs_clarification: bool = False
    ambiguity_reasons: tuple[str, ...] = ()


class CapabilityParticipation(ContractModel):
    capability: OrchestratorCapability
    participation: ParticipationClass


class CapabilityDependency(ContractModel):
    capability: OrchestratorCapability
    dependencies: tuple[OrchestratorCapability, ...] = ()


class ApprovedWorkPlanPayload(ContractModel):
    kind: Literal[ArtifactKind.APPROVED_WORK_PLAN] = ArtifactKind.APPROVED_WORK_PLAN
    plan_id: str = Field(min_length=1)
    capability_roles: tuple[CapabilityParticipation, ...]
    dependencies: tuple[CapabilityDependency, ...]
    mode_eligibility: tuple[KnowledgeMode, ...]
    budget_profile: LatencyProfileName

    @model_validator(mode="after")
    def validate_plan_entries(self) -> Self:
        role_names = tuple(entry.capability for entry in self.capability_roles)
        dependency_names = tuple(entry.capability for entry in self.dependencies)
        if len(set(role_names)) != len(role_names):
            raise ValueError("Capability participation entries must be unique")
        if len(set(dependency_names)) != len(dependency_names):
            raise ValueError("Capability dependency entries must be unique")
        if set(role_names) != set(dependency_names):
            raise ValueError("Capability roles and dependencies must cover the same set")
        if len(set(self.mode_eligibility)) != len(self.mode_eligibility):
            raise ValueError("Mode eligibility must be unique")
        return self


class EvidenceUnitPayload(ContractModel):
    kind: Literal[ArtifactKind.EVIDENCE_UNIT] = ArtifactKind.EVIDENCE_UNIT
    excerpt: str = Field(min_length=1)
    locator: str | None = None
    source_status: str | None = None
    match_reasons: tuple[str, ...] = ()
    duplicate_match_methods: tuple[str, ...] = ()


class ArtifactAttribute(ContractModel):
    key: str = Field(min_length=1)
    value: str = Field(min_length=1)


class StructuredFactPayload(ContractModel):
    kind: Literal[ArtifactKind.STRUCTURED_FACT] = ArtifactKind.STRUCTURED_FACT
    subject_id: str = Field(min_length=1)
    relationship: str = Field(min_length=1)
    object_id_or_value: str = Field(min_length=1)
    qualifiers: tuple[ArtifactAttribute, ...] = ()
    extraction_confidence: float = Field(ge=0, le=1)
    discovery_only: bool = False

    @field_validator("qualifiers")
    @classmethod
    def validate_qualifiers(
        cls,
        value: tuple[ArtifactAttribute, ...],
    ) -> tuple[ArtifactAttribute, ...]:
        keys = tuple(item.key for item in value)
        if len(set(keys)) != len(keys):
            raise ValueError("Structured fact qualifier keys must be unique")
        return value


class TimelineEventPayload(ContractModel):
    kind: Literal[ArtifactKind.TIMELINE_EVENT] = ArtifactKind.TIMELINE_EVENT
    label: str = Field(min_length=1)
    event_type: str = Field(min_length=1)
    date_value: datetime | None = None
    date_semantic: TimeDimension
    date_confidence: float = Field(ge=0, le=1)
    inferred_order: bool = False
    related_event_ids: tuple[str, ...] = ()

    @field_validator("date_value")
    @classmethod
    def validate_date_timezone(cls, value: datetime | None) -> datetime | None:
        if value is not None and value.tzinfo is None:
            raise ValueError("Timeline event dates must include a timezone")
        return value


class GeneralKnowledgeUnitPayload(ContractModel):
    kind: Literal[ArtifactKind.GENERAL_KNOWLEDGE_UNIT] = (
        ArtifactKind.GENERAL_KNOWLEDGE_UNIT
    )
    content: str = Field(min_length=1)
    assumptions: tuple[str, ...] = ()
    uncertainty_statements: tuple[str, ...] = ()
    required_disclosure: str | None = Field(default=None, min_length=1)


class CandidateClaimPayload(ContractModel):
    kind: Literal[ArtifactKind.CANDIDATE_CLAIM] = ArtifactKind.CANDIDATE_CLAIM
    claim_text: str = Field(min_length=1)
    material: bool
    supporting_artifact_ids: tuple[str, ...] = ()
    confidence_ceiling: float | None = Field(default=None, ge=0, le=1)


class VerificationResultPayload(ContractModel):
    kind: Literal[ArtifactKind.VERIFICATION_RESULT] = (
        ArtifactKind.VERIFICATION_RESULT
    )
    target_artifact_id: str = Field(min_length=1)
    target_kind: Literal[
        ArtifactKind.EVIDENCE_UNIT,
        ArtifactKind.CANDIDATE_CLAIM,
    ]
    status: VerificationStatus
    supported_boundary: str | None = None
    reasons: tuple[str, ...]
    correction_reason: str | None = None


class SectionContentBlock(ContractModel):
    block_type: str = Field(min_length=1)
    content: str = Field(min_length=1)
    attributes: tuple[ArtifactAttribute, ...] = ()


class SectionDraftPayload(ContractModel):
    kind: Literal[ArtifactKind.SECTION_DRAFT] = ArtifactKind.SECTION_DRAFT
    section_type: str = Field(min_length=1)
    title: str | None = None
    content_blocks: tuple[SectionContentBlock, ...]
    candidate_claim_ids: tuple[str, ...] = ()
    explicit_unknowns: tuple[str, ...] = ()
    gaps: tuple[str, ...] = ()
    required_disclosure: str | None = None


class FollowUpCandidate(ContractModel):
    question: str = Field(min_length=1)
    expected_response_strategy: str = Field(min_length=1)
    reason: str = Field(min_length=1)


class FollowUpCandidatesPayload(ContractModel):
    kind: Literal[ArtifactKind.FOLLOW_UP_CANDIDATES] = (
        ArtifactKind.FOLLOW_UP_CANDIDATES
    )
    candidates: tuple[FollowUpCandidate, ...] = ()

    @model_validator(mode="after")
    def validate_candidate_count(self) -> Self:
        if len(self.candidates) not in {0, 3, 4, 5}:
            raise ValueError("Follow-up candidates must contain zero or three to five items")
        questions = tuple(candidate.question for candidate in self.candidates)
        if len(set(questions)) != len(questions):
            raise ValueError("Follow-up questions must be unique")
        return self


class CompletionSection(ContractModel):
    section_key: str = Field(min_length=1)
    state: SectionTerminalState
    knowledge_mode: KnowledgeMode
    source_coverage: float = Field(ge=0, le=1)
    confidence_score: float | None = Field(default=None, ge=0, le=1)


class CompletionSummaryPayload(ContractModel):
    kind: Literal[ArtifactKind.COMPLETION_SUMMARY] = ArtifactKind.COMPLETION_SUMMARY
    sections: tuple[CompletionSection, ...]
    assumptions: tuple[str, ...] = ()
    degraded_capabilities: tuple[OrchestratorCapability, ...] = ()


ArtifactPayload = Annotated[
    ResearchRequestPayload
    | InterpretationResultPayload
    | ResolutionSetPayload
    | ApprovedWorkPlanPayload
    | EvidenceUnitPayload
    | StructuredFactPayload
    | TimelineEventPayload
    | GeneralKnowledgeUnitPayload
    | CandidateClaimPayload
    | VerificationResultPayload
    | SectionDraftPayload
    | FollowUpCandidatesPayload
    | CompletionSummaryPayload,
    Field(discriminator="kind"),
]

FACTUAL_ARTIFACTS = {
    ArtifactKind.EVIDENCE_UNIT,
    ArtifactKind.STRUCTURED_FACT,
    ArtifactKind.TIMELINE_EVENT,
    ArtifactKind.GENERAL_KNOWLEDGE_UNIT,
    ArtifactKind.CANDIDATE_CLAIM,
    ArtifactKind.SECTION_DRAFT,
}

ARTIFACT_PRODUCERS = MappingProxyType({
    ArtifactKind.RESEARCH_REQUEST: frozenset({
        ArtifactProducer.USER_CONTEXT,
        ArtifactProducer.DECISION_ENGINE,
    }),
    ArtifactKind.INTERPRETATION_RESULT: frozenset({
        ArtifactProducer.INTENT_CLASSIFIER
    }),
    ArtifactKind.RESOLUTION_SET: frozenset({ArtifactProducer.ENTITY_RESOLVER}),
    ArtifactKind.APPROVED_WORK_PLAN: frozenset({
        ArtifactProducer.DECISION_ENGINE
    }),
    ArtifactKind.EVIDENCE_UNIT: frozenset({
        ArtifactProducer.REGULATORY_RETRIEVER,
        ArtifactProducer.NEWS_RETRIEVER,
    }),
    ArtifactKind.STRUCTURED_FACT: frozenset({
        ArtifactProducer.KNOWLEDGE_GRAPH
    }),
    ArtifactKind.TIMELINE_EVENT: frozenset({
        ArtifactProducer.TIMELINE_BUILDER
    }),
    ArtifactKind.GENERAL_KNOWLEDGE_UNIT: frozenset({
        ArtifactProducer.GENERAL_AI
    }),
    ArtifactKind.CANDIDATE_CLAIM: frozenset({
        ArtifactProducer.RESPONSE_COMPOSER
    }),
    ArtifactKind.VERIFICATION_RESULT: frozenset({
        ArtifactProducer.CITATION_VERIFIER
    }),
    ArtifactKind.SECTION_DRAFT: frozenset({
        ArtifactProducer.RESPONSE_COMPOSER
    }),
    ArtifactKind.FOLLOW_UP_CANDIDATES: frozenset({
        ArtifactProducer.FOLLOW_UP_GENERATOR
    }),
    ArtifactKind.COMPLETION_SUMMARY: frozenset({
        ArtifactProducer.ORCHESTRATOR
    }),
})


class ArtifactEnvelope(ContractModel):
    schema_version: Literal["1"] = ORCHESTRATION_SCHEMA_VERSION
    artifact_id: str = Field(min_length=1)
    producer: ArtifactProducer
    scope: CapabilityScope
    payload: ArtifactPayload
    provenance: ProvenanceLineage | None = None
    confidence_signals: ConfidenceSignals | None = None
    ancestry: tuple[str, ...] = ()
    capability_status: CapabilityTerminalState | None = None
    conflicts: tuple[str, ...] = ()
    warnings: tuple[str, ...] = ()

    @field_validator("artifact_id")
    @classmethod
    def normalize_artifact_id(cls, value: str) -> str:
        normalized = value.strip()
        if not normalized:
            raise ValueError("Artifact ID cannot be blank")
        return normalized

    @field_validator("ancestry", "conflicts", "warnings")
    @classmethod
    def validate_unique_metadata(
        cls,
        value: tuple[str, ...],
        info: Any,
    ) -> tuple[str, ...]:
        return _unique(value, info.field_name)

    @model_validator(mode="after")
    def validate_semantic_contract(self) -> Self:
        kind = self.payload.kind
        if self.producer not in ARTIFACT_PRODUCERS[kind]:
            raise ValueError("Artifact producer is not authoritative for this kind")
        if kind in FACTUAL_ARTIFACTS:
            if self.provenance is None:
                raise ValueError("Factual artifacts require provenance lineage")
            if self.capability_status is None:
                raise ValueError("Factual artifacts require capability terminal status")
        if self.provenance is None and self.confidence_signals is not None:
            raise ValueError("Knowledge confidence signals require provenance")
        if self.artifact_id in self.ancestry:
            raise ValueError("An artifact cannot be its own ancestor")
        if isinstance(self.payload, GeneralKnowledgeUnitPayload):
            if (
                self.provenance is None
                or self.provenance.provenance_class
                is not ProvenanceClass.GENERAL_AI_KNOWLEDGE
            ):
                raise ValueError("General knowledge requires General AI provenance")
        if isinstance(self.payload, CandidateClaimPayload):
            missing = set(self.payload.supporting_artifact_ids) - set(self.ancestry)
            if missing:
                raise ValueError("Claim support must be present in artifact ancestry")
        transformation_inputs = {
            input_id
            for step in self.provenance.transformations
            for input_id in step.input_artifact_ids
        } if self.provenance is not None else set()
        if not transformation_inputs.issubset(set(self.ancestry)):
            raise ValueError("Transformation inputs must be present in artifact ancestry")
        return self


class CapabilityTiming(ContractModel):
    started_at: datetime
    completed_at: datetime
    duration_ms: int = Field(ge=0)

    @field_validator("started_at", "completed_at")
    @classmethod
    def validate_timezone(cls, value: datetime) -> datetime:
        if value.tzinfo is None:
            raise ValueError("Capability timing must include a timezone")
        return value

    @model_validator(mode="after")
    def validate_order(self) -> Self:
        if self.completed_at < self.started_at:
            raise ValueError("Capability completion cannot precede its start")
        return self


class CapabilityRequest(ContractModel):
    schema_version: Literal["1"] = ORCHESTRATION_SCHEMA_VERSION
    policy_version: str = Field(default=ORCHESTRATION_POLICY_VERSION, min_length=1)
    request_id: UUID
    run_id: UUID
    plan_id: str = Field(min_length=1)
    capability: OrchestratorCapability
    participation: ParticipationClass
    scope: CapabilityScope
    input_artifacts: tuple[ArtifactEnvelope, ...] = ()

    @model_validator(mode="after")
    def validate_skipped_request(self) -> Self:
        artifact_ids = tuple(artifact.artifact_id for artifact in self.input_artifacts)
        if len(set(artifact_ids)) != len(artifact_ids):
            raise ValueError("Capability input artifact IDs must be unique")
        if self.participation is ParticipationClass.SKIPPED and self.input_artifacts:
            raise ValueError("Skipped capability requests cannot admit artifacts")
        return self

    @property
    def input_artifact_ids(self) -> tuple[str, ...]:
        return tuple(artifact.artifact_id for artifact in self.input_artifacts)


FAILURE_STATES = {
    CapabilityTerminalState.TIMED_OUT,
    CapabilityTerminalState.UNAVAILABLE,
    CapabilityTerminalState.INVALID_OUTPUT,
}


class CapabilityResult(ContractModel):
    schema_version: Literal["1"] = ORCHESTRATION_SCHEMA_VERSION
    policy_version: str = Field(default=ORCHESTRATION_POLICY_VERSION, min_length=1)
    request_id: UUID
    run_id: UUID
    capability: OrchestratorCapability
    terminal_state: CapabilityTerminalState
    scope_echo: CapabilityScope
    artifacts: tuple[ArtifactEnvelope, ...] = ()
    confidence_signals: ConfidenceSignals = Field(default_factory=ConfidenceSignals)
    timing: CapabilityTiming | None = None
    safe_error_code: str | None = None
    warnings: tuple[str, ...] = ()

    @field_validator("warnings")
    @classmethod
    def validate_warnings(cls, value: tuple[str, ...]) -> tuple[str, ...]:
        return _unique(value, "Capability result warnings")

    @field_validator("safe_error_code")
    @classmethod
    def validate_safe_error(cls, value: str | None) -> str | None:
        if value is not None and SAFE_ERROR_CODE.fullmatch(value) is None:
            raise ValueError("Capability safe error code is invalid")
        return value

    @model_validator(mode="after")
    def validate_terminal_result(self) -> Self:
        if self.terminal_state is CapabilityTerminalState.SKIPPED:
            if self.timing is not None or self.artifacts or self.safe_error_code:
                raise ValueError("Skipped results cannot contain execution output")
        elif self.timing is None:
            raise ValueError("Executed capability results require timing")
        if self.terminal_state is CapabilityTerminalState.INVALID_OUTPUT and self.artifacts:
            raise ValueError("Invalid output artifacts must be excluded")
        if self.terminal_state in FAILURE_STATES and self.safe_error_code is None:
            raise ValueError("Failed capability results require a safe error code")
        if self.terminal_state not in FAILURE_STATES and self.safe_error_code is not None:
            raise ValueError("Only failed capability results carry safe error codes")
        expected_producer = ArtifactProducer(self.capability.value)
        if any(artifact.producer is not expected_producer for artifact in self.artifacts):
            raise ValueError("Capability result contains an artifact from another producer")
        if any(
            artifact.capability_status is not None
            and artifact.capability_status is not self.terminal_state
            for artifact in self.artifacts
        ):
            raise ValueError("Artifact and capability terminal statuses must agree")
        if any(artifact.scope != self.scope_echo for artifact in self.artifacts):
            raise ValueError("Capability artifact scope must match the result scope echo")
        return self


class CapabilityContract(ContractModel):
    capability: OrchestratorCapability
    sole_authority: tuple[str, ...]
    prohibitions: tuple[str, ...]
    accepted_inputs: tuple[ArtifactKind, ...]
    allowed_outputs: tuple[ArtifactKind, ...]

    @model_validator(mode="after")
    def validate_declaration(self) -> Self:
        if not self.sole_authority or not self.prohibitions:
            raise ValueError("Capability authority and prohibitions are required")
        if not self.allowed_outputs:
            raise ValueError("Capability must declare at least one output artifact")
        if len(set(self.accepted_inputs)) != len(self.accepted_inputs):
            raise ValueError("Accepted artifact inputs must be unique")
        if len(set(self.allowed_outputs)) != len(self.allowed_outputs):
            raise ValueError("Allowed artifact outputs must be unique")
        return self


CAPABILITY_CONTRACTS = MappingProxyType({
    OrchestratorCapability.INTENT_CLASSIFIER: CapabilityContract(
        capability=OrchestratorCapability.INTENT_CLASSIFIER,
        sole_authority=("Propose intent candidates and atomic questions.",),
        prohibitions=("Cannot decide final routing, mode, or answer confidence.",),
        accepted_inputs=(ArtifactKind.RESEARCH_REQUEST,),
        allowed_outputs=(ArtifactKind.INTERPRETATION_RESULT,),
    ),
    OrchestratorCapability.ENTITY_RESOLVER: CapabilityContract(
        capability=OrchestratorCapability.ENTITY_RESOLVER,
        sole_authority=("Canonicalize mentions and jurisdiction-compatible entities.",),
        prohibitions=("Cannot infer legal applicability or factual truth.",),
        accepted_inputs=(
            ArtifactKind.RESEARCH_REQUEST,
            ArtifactKind.INTERPRETATION_RESULT,
        ),
        allowed_outputs=(ArtifactKind.RESOLUTION_SET,),
    ),
    OrchestratorCapability.REGULATORY_RETRIEVER: CapabilityContract(
        capability=OrchestratorCapability.REGULATORY_RETRIEVER,
        sole_authority=("Find official-corpus evidence within approved scope.",),
        prohibitions=("Cannot manufacture conclusions, prose, or final citations.",),
        accepted_inputs=(
            ArtifactKind.APPROVED_WORK_PLAN,
            ArtifactKind.RESOLUTION_SET,
        ),
        allowed_outputs=(ArtifactKind.EVIDENCE_UNIT,),
    ),
    OrchestratorCapability.KNOWLEDGE_GRAPH: CapabilityContract(
        capability=OrchestratorCapability.KNOWLEDGE_GRAPH,
        sole_authority=("Supply typed relationships with backing ancestry.",),
        prohibitions=("Cannot treat unbacked edges as law or override documents.",),
        accepted_inputs=(
            ArtifactKind.APPROVED_WORK_PLAN,
            ArtifactKind.RESOLUTION_SET,
        ),
        allowed_outputs=(ArtifactKind.STRUCTURED_FACT,),
    ),
    OrchestratorCapability.TIMELINE_BUILDER: CapabilityContract(
        capability=OrchestratorCapability.TIMELINE_BUILDER,
        sole_authority=("Normalize and relate dated admitted artifacts.",),
        prohibitions=("Cannot invent dates or decide legal force.",),
        accepted_inputs=(
            ArtifactKind.EVIDENCE_UNIT,
            ArtifactKind.STRUCTURED_FACT,
        ),
        allowed_outputs=(ArtifactKind.TIMELINE_EVENT,),
    ),
    OrchestratorCapability.NEWS_RETRIEVER: CapabilityContract(
        capability=OrchestratorCapability.NEWS_RETRIEVER,
        sole_authority=("Find approved current live sources.",),
        prohibitions=("Cannot establish legal effect or create official citations.",),
        accepted_inputs=(
            ArtifactKind.APPROVED_WORK_PLAN,
            ArtifactKind.RESOLUTION_SET,
        ),
        allowed_outputs=(ArtifactKind.EVIDENCE_UNIT,),
    ),
    OrchestratorCapability.GENERAL_AI: CapabilityContract(
        capability=OrchestratorCapability.GENERAL_AI,
        sole_authority=("Produce bounded Mode 2 general knowledge.",),
        prohibitions=("Cannot create official facts, sources, or legal applicability.",),
        accepted_inputs=(
            ArtifactKind.APPROVED_WORK_PLAN,
            ArtifactKind.RESOLUTION_SET,
        ),
        allowed_outputs=(ArtifactKind.GENERAL_KNOWLEDGE_UNIT,),
    ),
    OrchestratorCapability.CITATION_VERIFIER: CapabilityContract(
        capability=OrchestratorCapability.CITATION_VERIFIER,
        sole_authority=("Determine claim support and evidence identity validity.",),
        prohibitions=("Cannot improve source authority or rewrite claims as fact.",),
        accepted_inputs=(
            ArtifactKind.EVIDENCE_UNIT,
            ArtifactKind.STRUCTURED_FACT,
            ArtifactKind.TIMELINE_EVENT,
            ArtifactKind.CANDIDATE_CLAIM,
        ),
        allowed_outputs=(ArtifactKind.VERIFICATION_RESULT,),
    ),
    OrchestratorCapability.RESPONSE_COMPOSER: CapabilityContract(
        capability=OrchestratorCapability.RESPONSE_COMPOSER,
        sole_authority=("Transform admitted knowledge within assigned section lanes.",),
        prohibitions=("Cannot add knowledge, select mode, or perform final merge.",),
        accepted_inputs=(
            ArtifactKind.APPROVED_WORK_PLAN,
            ArtifactKind.EVIDENCE_UNIT,
            ArtifactKind.STRUCTURED_FACT,
            ArtifactKind.TIMELINE_EVENT,
            ArtifactKind.GENERAL_KNOWLEDGE_UNIT,
            ArtifactKind.VERIFICATION_RESULT,
        ),
        allowed_outputs=(
            ArtifactKind.CANDIDATE_CLAIM,
            ArtifactKind.SECTION_DRAFT,
        ),
    ),
    OrchestratorCapability.FOLLOW_UP_GENERATOR: CapabilityContract(
        capability=OrchestratorCapability.FOLLOW_UP_GENERATOR,
        sole_authority=("Propose distinct research-next-step candidates.",),
        prohibitions=("Cannot alter the current answer or initiate research.",),
        accepted_inputs=(
            ArtifactKind.RESOLUTION_SET,
            ArtifactKind.SECTION_DRAFT,
            ArtifactKind.VERIFICATION_RESULT,
        ),
        allowed_outputs=(ArtifactKind.FOLLOW_UP_CANDIDATES,),
    ),
})


def validate_capability_exchange(
    request: CapabilityRequest,
    result: CapabilityResult,
) -> None:
    if (
        request.request_id != result.request_id
        or request.run_id != result.run_id
        or request.capability is not result.capability
    ):
        raise ValueError("Capability result identity does not match its request")
    if request.scope != result.scope_echo:
        raise ValueError("Capability result scope echo does not match approved scope")
    if (request.participation is ParticipationClass.SKIPPED) is not (
        result.terminal_state is CapabilityTerminalState.SKIPPED
    ):
        raise ValueError("Skipped participation and terminal state must agree")
    contract = CAPABILITY_CONTRACTS[request.capability]
    accepted_inputs = set(contract.accepted_inputs)
    if any(
        artifact.payload.kind not in accepted_inputs
        for artifact in request.input_artifacts
    ):
        raise ValueError("Capability request contains an undeclared artifact kind")
    allowed_outputs = set(contract.allowed_outputs)
    if any(artifact.payload.kind not in allowed_outputs for artifact in result.artifacts):
        raise ValueError("Capability result contains an undeclared artifact kind")
    admitted_inputs = set(request.input_artifact_ids)
    if any(not set(artifact.ancestry).issubset(admitted_inputs) for artifact in result.artifacts):
        raise ValueError("Capability output ancestry exceeds admitted inputs")


class ArtifactAdapter(Protocol):
    def adapt(
        self,
        source: object,
        *,
        scope: CapabilityScope,
    ) -> ArtifactEnvelope: ...


ARTIFACT_ADAPTER = TypeAdapter(ArtifactEnvelope)
CAPABILITY_RESULT_ADAPTER = TypeAdapter(CapabilityResult)


def artifact_json(artifact: ArtifactEnvelope) -> str:
    return json.dumps(
        artifact.model_dump(mode="json"),
        ensure_ascii=False,
        separators=(",", ":"),
        sort_keys=True,
    )


def capability_result_json(result: CapabilityResult) -> str:
    return json.dumps(
        result.model_dump(mode="json"),
        ensure_ascii=False,
        separators=(",", ":"),
        sort_keys=True,
    )
