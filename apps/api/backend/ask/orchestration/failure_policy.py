from __future__ import annotations

import json
from enum import StrEnum
from typing import Literal

from pydantic import Field, model_validator

from backend.ask.orchestration.contracts import (
    ArtifactKind,
    CapabilityTerminalState,
    ContractModel,
    OrchestratorCapability,
    ParticipationClass,
    VerificationResultPayload,
    VerificationStatus,
)
from backend.ask.orchestration.state_machine import (
    CapabilityNode,
    CapabilityOperation,
    OrchestrationState,
)

FAILURE_POLICY_SCHEMA_VERSION = "1"
FAILURE_POLICY_VERSION = "ask-ai-failure-v1"


class FailureSignal(StrEnum):
    PARTIAL = "partial"
    HEALTHY_NO_MATCH = "healthy_no_match"
    AMBIGUOUS = "ambiguous"
    TIMED_OUT = "timed_out"
    UNAVAILABLE = "unavailable"
    INVALID_OUTPUT = "invalid_output"
    EVIDENCE_REJECTED = "evidence_rejected"
    CLAIM_REJECTED = "claim_rejected"
    ALL_CLAIMS_REJECTED = "all_claims_rejected"


class SectionFailureDisposition(StrEnum):
    NEEDS_CLARIFICATION = "needs_clarification"
    EMPTY_BY_EVIDENCE = "empty_by_evidence"
    DEGRADED = "degraded"
    OMITTED = "omitted"
    READY_WITHOUT_SYNTHESIS = "ready_without_synthesis"
    CORE_UNCHANGED = "core_unchanged"


class FallbackAction(StrEnum):
    EXPLICIT_ACTION_OR_CLARIFICATION = "explicit_action_or_clarification"
    PRESENT_ENTITY_CANDIDATES = "present_entity_candidates"
    GENERAL_AI_NO_DOCUMENTS_DISCLOSURE = (
        "general_ai_no_documents_disclosure"
    )
    SAVED_EVIDENCE_OR_MANUAL_SEARCH = "saved_evidence_or_manual_search"
    OFFICIAL_DOCUMENT_FACTS = "official_document_facts"
    VERIFIED_DATE_CARDS_OR_SOURCES = "verified_date_cards_or_sources"
    NO_VERIFIED_LIVE_UPDATES = "no_verified_live_updates"
    INTERNAL_CORPUS_ONLY = "internal_corpus_only"
    INTERPRETATION_OR_MANUAL_SEARCH = "interpretation_or_manual_search"
    NARROW_OR_REMOVE_CLAIM = "narrow_or_remove_claim"
    OFFICIAL_SOURCE_CARDS = "official_source_cards"
    VERIFIED_ARTIFACTS_DIRECTLY = "verified_artifacts_directly"
    OMIT_SUGGESTIONS = "omit_suggestions"
    NO_ADDITIONAL_CAPABILITY = "no_additional_capability"


class FailurePropagation(StrEnum):
    DECLARED_DEPENDENTS = "declared_dependents"
    SCOPED_SECTION_ONLY = "scoped_section_only"
    NONE = "none"


class FailurePolicyRule(ContractModel):
    capability: OrchestratorCapability
    signal: FailureSignal
    section_disposition: SectionFailureDisposition
    fallback_action: FallbackAction
    propagation: FailurePropagation
    safe_notice_code: str = Field(pattern=r"^[A-Z][A-Z0-9_]{0,99}$")
    fallback_capability: OrchestratorCapability | None = None
    max_fallback_transitions: Literal[0, 1]
    max_revision_passes: Literal[0, 1]

    @model_validator(mode="after")
    def validate_bounds(self) -> FailurePolicyRule:
        if (
            self.fallback_capability is None
            and self.max_fallback_transitions != 0
        ):
            raise ValueError(
                "Fallback transitions require a declared fallback capability"
            )
        if (
            self.fallback_capability is not None
            and self.max_fallback_transitions != 1
        ):
            raise ValueError("Declared fallback capability permits one transition")
        if (
            self.max_revision_passes
            and self.capability is not OrchestratorCapability.CITATION_VERIFIER
        ):
            raise ValueError("Only claim verification permits a revision pass")
        return self


class FailureTransitionDecision(ContractModel):
    schema_version: Literal["1"] = FAILURE_POLICY_SCHEMA_VERSION
    policy_version: str = Field(default=FAILURE_POLICY_VERSION, min_length=1)
    failed_node_id: str = Field(min_length=1)
    capability: OrchestratorCapability
    terminal_state: CapabilityTerminalState
    signal: FailureSignal
    section_disposition: SectionFailureDisposition
    fallback_action: FallbackAction
    propagation: FailurePropagation
    safe_notice_code: str = Field(pattern=r"^[A-Z][A-Z0-9_]{0,99}$")
    affected_section_ids: tuple[str, ...]
    unaffected_section_ids: tuple[str, ...]
    declared_dependent_node_ids: tuple[str, ...]
    propagated_node_ids: tuple[str, ...]
    fallback_node_ids: tuple[str, ...]
    rejected_claim_ids: tuple[str, ...] = ()
    preserved_artifact_ids: tuple[str, ...]
    max_fallback_transitions: Literal[0, 1]
    max_revision_passes: Literal[0, 1]

    @model_validator(mode="after")
    def validate_isolation(self) -> FailureTransitionDecision:
        unique_fields = {
            "affected sections": self.affected_section_ids,
            "unaffected sections": self.unaffected_section_ids,
            "declared dependents": self.declared_dependent_node_ids,
            "propagated nodes": self.propagated_node_ids,
            "fallback nodes": self.fallback_node_ids,
            "rejected claims": self.rejected_claim_ids,
            "preserved artifacts": self.preserved_artifact_ids,
        }
        for label, values in unique_fields.items():
            if len(values) != len(set(values)):
                raise ValueError(f"Failure decision {label} must be unique")
        if set(self.affected_section_ids) & set(self.unaffected_section_ids):
            raise ValueError("Affected and unaffected sections must be disjoint")
        declared = set(self.declared_dependent_node_ids)
        if not set(self.propagated_node_ids).issubset(declared):
            raise ValueError("Failure propagation must follow declared dependencies")
        if not set(self.fallback_node_ids).issubset(declared):
            raise ValueError("Fallback activation must follow declared dependencies")
        if set(self.propagated_node_ids) & set(self.fallback_node_ids):
            raise ValueError("Fallback nodes cannot also receive failure propagation")
        if bool(self.fallback_node_ids) is not bool(
            self.max_fallback_transitions
        ):
            raise ValueError(
                "Fallback bound must match admitted fallback node availability"
            )
        if (
            self.max_revision_passes
            and self.signal is not FailureSignal.CLAIM_REJECTED
        ):
            raise ValueError("Only a rejected claim permits one revision pass")
        return self


class FailurePolicyError(RuntimeError):
    pass


def failure_rule(
    capability: OrchestratorCapability,
    signal: FailureSignal,
) -> FailurePolicyRule:
    generic_failure = signal in {
        FailureSignal.PARTIAL,
        FailureSignal.TIMED_OUT,
        FailureSignal.UNAVAILABLE,
        FailureSignal.INVALID_OUTPUT,
    }
    if capability is OrchestratorCapability.INTENT_CLASSIFIER:
        _require_signal(
            signal,
            {
                FailureSignal.PARTIAL,
                FailureSignal.AMBIGUOUS,
                FailureSignal.TIMED_OUT,
                FailureSignal.UNAVAILABLE,
                FailureSignal.INVALID_OUTPUT,
            },
        )
        return _rule(
            capability,
            signal,
            SectionFailureDisposition.NEEDS_CLARIFICATION,
            FallbackAction.EXPLICIT_ACTION_OR_CLARIFICATION,
            FailurePropagation.DECLARED_DEPENDENTS,
            "ASK_AI_INTENT_UNRESOLVED",
        )
    if capability is OrchestratorCapability.ENTITY_RESOLVER:
        _require_signal(
            signal,
            {
                FailureSignal.PARTIAL,
                FailureSignal.AMBIGUOUS,
                FailureSignal.TIMED_OUT,
                FailureSignal.UNAVAILABLE,
                FailureSignal.INVALID_OUTPUT,
            },
        )
        return _rule(
            capability,
            signal,
            SectionFailureDisposition.NEEDS_CLARIFICATION,
            FallbackAction.PRESENT_ENTITY_CANDIDATES,
            FailurePropagation.DECLARED_DEPENDENTS,
            "ASK_AI_ENTITY_UNRESOLVED",
        )
    if capability is OrchestratorCapability.REGULATORY_RETRIEVER:
        if signal is FailureSignal.HEALTHY_NO_MATCH:
            return _rule(
                capability,
                signal,
                SectionFailureDisposition.EMPTY_BY_EVIDENCE,
                FallbackAction.GENERAL_AI_NO_DOCUMENTS_DISCLOSURE,
                FailurePropagation.DECLARED_DEPENDENTS,
                "ASK_AI_OFFICIAL_NO_MATCH",
                fallback_capability=OrchestratorCapability.GENERAL_AI,
            )
        _require_signal(
            signal,
            {
                FailureSignal.PARTIAL,
                FailureSignal.TIMED_OUT,
                FailureSignal.UNAVAILABLE,
                FailureSignal.INVALID_OUTPUT,
            },
        )
        return _rule(
            capability,
            signal,
            SectionFailureDisposition.DEGRADED,
            FallbackAction.SAVED_EVIDENCE_OR_MANUAL_SEARCH,
            FailurePropagation.DECLARED_DEPENDENTS,
            "ASK_AI_OFFICIAL_COVERAGE_UNKNOWN",
            fallback_capability=(
                None
                if signal is FailureSignal.PARTIAL
                else OrchestratorCapability.GENERAL_AI
            ),
        )
    if capability is OrchestratorCapability.KNOWLEDGE_GRAPH:
        _require_signal(
            signal,
            {
                FailureSignal.PARTIAL,
                FailureSignal.HEALTHY_NO_MATCH,
                FailureSignal.TIMED_OUT,
                FailureSignal.UNAVAILABLE,
                FailureSignal.INVALID_OUTPUT,
            },
        )
        return _rule(
            capability,
            signal,
            SectionFailureDisposition.DEGRADED,
            FallbackAction.OFFICIAL_DOCUMENT_FACTS,
            FailurePropagation.SCOPED_SECTION_ONLY,
            "ASK_AI_GRAPH_INCOMPLETE",
        )
    if capability is OrchestratorCapability.TIMELINE_BUILDER:
        _require_signal(
            signal,
            {
                FailureSignal.PARTIAL,
                FailureSignal.HEALTHY_NO_MATCH,
                FailureSignal.TIMED_OUT,
                FailureSignal.UNAVAILABLE,
                FailureSignal.INVALID_OUTPUT,
            },
        )
        return _rule(
            capability,
            signal,
            SectionFailureDisposition.DEGRADED,
            FallbackAction.VERIFIED_DATE_CARDS_OR_SOURCES,
            FailurePropagation.SCOPED_SECTION_ONLY,
            "ASK_AI_TIMELINE_INCOMPLETE",
        )
    if capability is OrchestratorCapability.NEWS_RETRIEVER:
        if signal is FailureSignal.HEALTHY_NO_MATCH:
            return _rule(
                capability,
                signal,
                SectionFailureDisposition.EMPTY_BY_EVIDENCE,
                FallbackAction.NO_VERIFIED_LIVE_UPDATES,
                FailurePropagation.SCOPED_SECTION_ONLY,
                "ASK_AI_LIVE_NO_MATCH",
            )
        _require_signal(
            signal,
            {
                FailureSignal.PARTIAL,
                FailureSignal.TIMED_OUT,
                FailureSignal.UNAVAILABLE,
                FailureSignal.INVALID_OUTPUT,
            },
        )
        return _rule(
            capability,
            signal,
            SectionFailureDisposition.DEGRADED,
            FallbackAction.INTERNAL_CORPUS_ONLY,
            FailurePropagation.SCOPED_SECTION_ONLY,
            "ASK_AI_LIVE_COVERAGE_UNKNOWN",
        )
    if capability is OrchestratorCapability.GENERAL_AI:
        _require_signal(
            signal,
            {
                FailureSignal.PARTIAL,
                FailureSignal.HEALTHY_NO_MATCH,
                FailureSignal.TIMED_OUT,
                FailureSignal.UNAVAILABLE,
                FailureSignal.INVALID_OUTPUT,
            },
        )
        return _rule(
            capability,
            signal,
            SectionFailureDisposition.READY_WITHOUT_SYNTHESIS,
            FallbackAction.INTERPRETATION_OR_MANUAL_SEARCH,
            FailurePropagation.SCOPED_SECTION_ONLY,
            "ASK_AI_GENERAL_SYNTHESIS_UNAVAILABLE",
        )
    if capability is OrchestratorCapability.CITATION_VERIFIER:
        _require_signal(
            signal,
            {
                FailureSignal.PARTIAL,
                FailureSignal.TIMED_OUT,
                FailureSignal.UNAVAILABLE,
                FailureSignal.INVALID_OUTPUT,
                FailureSignal.EVIDENCE_REJECTED,
                FailureSignal.CLAIM_REJECTED,
                FailureSignal.ALL_CLAIMS_REJECTED,
            },
        )
        if signal is FailureSignal.EVIDENCE_REJECTED:
            return _rule(
                capability,
                signal,
                SectionFailureDisposition.DEGRADED,
                FallbackAction.SAVED_EVIDENCE_OR_MANUAL_SEARCH,
                FailurePropagation.SCOPED_SECTION_ONLY,
                "ASK_AI_EVIDENCE_UNVERIFIED",
            )
        all_claims = signal in {
            FailureSignal.TIMED_OUT,
            FailureSignal.UNAVAILABLE,
            FailureSignal.INVALID_OUTPUT,
            FailureSignal.ALL_CLAIMS_REJECTED,
        }
        return _rule(
            capability,
            signal,
            (
                SectionFailureDisposition.READY_WITHOUT_SYNTHESIS
                if all_claims
                else SectionFailureDisposition.DEGRADED
            ),
            (
                FallbackAction.OFFICIAL_SOURCE_CARDS
                if all_claims
                else FallbackAction.NARROW_OR_REMOVE_CLAIM
            ),
            FailurePropagation.SCOPED_SECTION_ONLY,
            (
                "ASK_AI_ALL_CLAIMS_UNVERIFIED"
                if all_claims
                else "ASK_AI_CLAIM_UNVERIFIED"
            ),
            max_revision_passes=0 if all_claims else 1,
        )
    if capability is OrchestratorCapability.RESPONSE_COMPOSER:
        _require_signal(
            signal,
            {
                FailureSignal.PARTIAL,
                FailureSignal.TIMED_OUT,
                FailureSignal.UNAVAILABLE,
                FailureSignal.INVALID_OUTPUT,
            },
        )
        return _rule(
            capability,
            signal,
            SectionFailureDisposition.READY_WITHOUT_SYNTHESIS,
            FallbackAction.VERIFIED_ARTIFACTS_DIRECTLY,
            FailurePropagation.SCOPED_SECTION_ONLY,
            "ASK_AI_COMPOSITION_UNAVAILABLE",
        )
    if capability is OrchestratorCapability.FOLLOW_UP_GENERATOR:
        _require_signal(
            signal,
            {
                FailureSignal.PARTIAL,
                FailureSignal.TIMED_OUT,
                FailureSignal.UNAVAILABLE,
                FailureSignal.INVALID_OUTPUT,
            },
        )
        return _rule(
            capability,
            signal,
            SectionFailureDisposition.CORE_UNCHANGED,
            FallbackAction.OMIT_SUGGESTIONS,
            FailurePropagation.NONE,
            "ASK_AI_FOLLOW_UPS_OMITTED",
        )
    if generic_failure:
        raise FailurePolicyError("Capability failure policy is not declared")
    raise FailurePolicyError("Failure signal is not eligible for this capability")


def decide_failure_transition(
    state: OrchestrationState,
    failed_node_id: str,
) -> FailureTransitionDecision:
    failed = _node(state, failed_node_id)
    if failed.result is None:
        raise FailurePolicyError("Failure decisions require a terminal result")
    signal, rejected_claim_ids = _failure_signal(state, failed)
    rule = failure_rule(failed.capability, signal)
    declared_dependents = _declared_descendants(state, failed.node_id)
    fallback_node_ids = tuple(
        node_id
        for node_id in declared_dependents
        if rule.fallback_capability is not None
        and _node(state, node_id).capability is rule.fallback_capability
        and _node(state, node_id).participation
        in {
            ParticipationClass.CONDITIONAL_MANDATORY,
            ParticipationClass.FALLBACK,
        }
    )
    propagated_node_ids = (
        _propagated_descendants(
            state,
            failed.node_id,
            frozenset(fallback_node_ids),
        )
        if rule.propagation is FailurePropagation.DECLARED_DEPENDENTS
        else ()
    )
    affected_section_ids = _affected_sections(
        state,
        failed,
        rejected_claim_ids,
        propagated_node_ids,
    )
    affected = set(affected_section_ids)
    section_disposition = _resolved_section_disposition(
        state,
        rule,
        affected_section_ids,
    )
    return FailureTransitionDecision(
        failed_node_id=failed.node_id,
        capability=failed.capability,
        terminal_state=failed.result.terminal_state,
        signal=signal,
        section_disposition=section_disposition,
        fallback_action=(
            FallbackAction.NO_ADDITIONAL_CAPABILITY
            if (
                rule.fallback_action
                is FallbackAction.GENERAL_AI_NO_DOCUMENTS_DISCLOSURE
                and not fallback_node_ids
            )
            else rule.fallback_action
        ),
        propagation=rule.propagation,
        safe_notice_code=rule.safe_notice_code,
        affected_section_ids=affected_section_ids,
        unaffected_section_ids=tuple(
            section.section_id
            for section in state.sections
            if section.section_id not in affected
        ),
        declared_dependent_node_ids=declared_dependents,
        propagated_node_ids=propagated_node_ids,
        fallback_node_ids=fallback_node_ids,
        rejected_claim_ids=rejected_claim_ids,
        preserved_artifact_ids=tuple(
            artifact.artifact_id for artifact in state.admitted_artifacts
        ),
        max_fallback_transitions=(
            rule.max_fallback_transitions if fallback_node_ids else 0
        ),
        max_revision_passes=rule.max_revision_passes,
    )


def failure_transition_json(decision: FailureTransitionDecision) -> str:
    return json.dumps(
        decision.model_dump(mode="json"),
        ensure_ascii=False,
        separators=(",", ":"),
        sort_keys=True,
    )


def _rule(
    capability: OrchestratorCapability,
    signal: FailureSignal,
    section_disposition: SectionFailureDisposition,
    fallback_action: FallbackAction,
    propagation: FailurePropagation,
    safe_notice_code: str,
    *,
    fallback_capability: OrchestratorCapability | None = None,
    max_revision_passes: Literal[0, 1] = 0,
) -> FailurePolicyRule:
    return FailurePolicyRule(
        capability=capability,
        signal=signal,
        section_disposition=section_disposition,
        fallback_action=fallback_action,
        propagation=propagation,
        safe_notice_code=safe_notice_code,
        fallback_capability=fallback_capability,
        max_fallback_transitions=1 if fallback_capability is not None else 0,
        max_revision_passes=max_revision_passes,
    )


def _require_signal(
    signal: FailureSignal,
    allowed: set[FailureSignal],
) -> None:
    if signal not in allowed:
        raise FailurePolicyError("Failure signal is not eligible for this capability")


def _node(state: OrchestrationState, node_id: str) -> CapabilityNode:
    try:
        return next(node for node in state.capabilities if node.node_id == node_id)
    except StopIteration as exc:
        raise FailurePolicyError("Failure node is not declared") from exc


def _failure_signal(
    state: OrchestrationState,
    node: CapabilityNode,
) -> tuple[FailureSignal, tuple[str, ...]]:
    if node.capability is OrchestratorCapability.CITATION_VERIFIER:
        if (
            node.operation is CapabilityOperation.EVIDENCE_INTEGRITY
            and _evidence_integrity_rejected(node)
        ):
            return FailureSignal.EVIDENCE_REJECTED, ()
        rejected = _rejected_claim_ids(node)
        if rejected:
            affected_sections = tuple(
                section
                for section in state.sections
                if set(section.material_claim_ids) & set(rejected)
            )
            all_rejected = bool(affected_sections) and all(
                section.material_claim_ids
                and set(section.material_claim_ids).issubset(rejected)
                for section in affected_sections
            )
            return (
                (
                    FailureSignal.ALL_CLAIMS_REJECTED
                    if all_rejected
                    else FailureSignal.CLAIM_REJECTED
                ),
                rejected,
            )
    terminal_signals = {
        CapabilityTerminalState.PARTIAL: FailureSignal.PARTIAL,
        CapabilityTerminalState.NO_MATCH: FailureSignal.HEALTHY_NO_MATCH,
        CapabilityTerminalState.AMBIGUOUS: FailureSignal.AMBIGUOUS,
        CapabilityTerminalState.TIMED_OUT: FailureSignal.TIMED_OUT,
        CapabilityTerminalState.UNAVAILABLE: FailureSignal.UNAVAILABLE,
        CapabilityTerminalState.INVALID_OUTPUT: FailureSignal.INVALID_OUTPUT,
    }
    try:
        signal = terminal_signals[node.result.terminal_state]
    except KeyError as exc:
        raise FailurePolicyError(
            "Capability result does not require a failure transition"
        ) from exc
    if (
        node.capability is OrchestratorCapability.CITATION_VERIFIER
        and signal is FailureSignal.HEALTHY_NO_MATCH
    ):
        raise FailurePolicyError("Citation verification cannot report healthy no-match")
    return signal, ()


def _evidence_integrity_rejected(node: CapabilityNode) -> bool:
    rejected_statuses = {
        VerificationStatus.PARTIALLY_SUPPORTED,
        VerificationStatus.UNSUPPORTED,
        VerificationStatus.CONTRADICTORY,
        VerificationStatus.UNVERIFIABLE,
    }
    if node.result.terminal_state in {
        CapabilityTerminalState.PARTIAL,
        CapabilityTerminalState.TIMED_OUT,
        CapabilityTerminalState.UNAVAILABLE,
        CapabilityTerminalState.INVALID_OUTPUT,
    }:
        return True
    return any(
        isinstance(artifact.payload, VerificationResultPayload)
        and artifact.payload.target_kind is ArtifactKind.EVIDENCE_UNIT
        and artifact.payload.status in rejected_statuses
        for artifact in node.result.artifacts
    )


def _rejected_claim_ids(node: CapabilityNode) -> tuple[str, ...]:
    rejected_statuses = {
        VerificationStatus.PARTIALLY_SUPPORTED,
        VerificationStatus.UNSUPPORTED,
        VerificationStatus.CONTRADICTORY,
        VerificationStatus.UNVERIFIABLE,
    }
    return tuple(
        dict.fromkeys(
        artifact.payload.target_artifact_id
        for artifact in node.result.artifacts
        if isinstance(artifact.payload, VerificationResultPayload)
        and artifact.payload.target_kind is ArtifactKind.CANDIDATE_CLAIM
        and artifact.payload.status in rejected_statuses
        )
    )


def _declared_descendants(
    state: OrchestrationState,
    node_id: str,
) -> tuple[str, ...]:
    ordered: list[str] = []
    seen: set[str] = set()
    frontier = [node_id]
    while frontier:
        parent = frontier.pop(0)
        for node in state.capabilities:
            if parent not in node.dependencies or node.node_id in seen:
                continue
            seen.add(node.node_id)
            ordered.append(node.node_id)
            frontier.append(node.node_id)
    return tuple(ordered)


def _propagated_descendants(
    state: OrchestrationState,
    node_id: str,
    fallback_node_ids: frozenset[str],
) -> tuple[str, ...]:
    ordered: list[str] = []
    seen: set[str] = set()
    frontier = [node_id]
    while frontier:
        parent = frontier.pop(0)
        for node in state.capabilities:
            if parent not in node.dependencies or node.node_id in seen:
                continue
            seen.add(node.node_id)
            if node.node_id in fallback_node_ids:
                continue
            ordered.append(node.node_id)
            frontier.append(node.node_id)
    return tuple(ordered)


def _affected_sections(
    state: OrchestrationState,
    failed: CapabilityNode,
    rejected_claim_ids: tuple[str, ...],
    propagated_node_ids: tuple[str, ...],
) -> tuple[str, ...]:
    rejected = set(rejected_claim_ids)
    propagated = {
        node_id for node_id in propagated_node_ids
    }
    targets = {
        (
            node.atomic_question_id,
            node.section_key,
            node.provenance_class,
        )
        for node in state.capabilities
        if node.node_id in propagated
        and node.atomic_question_id is not None
    }
    if failed.atomic_question_id is not None:
        targets.add(
            (
                failed.atomic_question_id,
                failed.section_key,
                failed.provenance_class,
            )
        )
    return tuple(
        section.section_id
        for section in state.sections
        if (
            rejected
            and bool(set(section.material_claim_ids) & rejected)
        )
        or (
            section.atomic_question_id,
            section.section_key,
            section.provenance_class,
        )
        in targets
    )


def _resolved_section_disposition(
    state: OrchestrationState,
    rule: FailurePolicyRule,
    affected_section_ids: tuple[str, ...],
) -> SectionFailureDisposition:
    affected = {
        section.section_id: section
        for section in state.sections
        if section.section_id in affected_section_ids
    }
    all_optional = bool(affected) and all(
        not section.required for section in affected.values()
    )
    if (
        all_optional
        and rule.capability is OrchestratorCapability.TIMELINE_BUILDER
    ):
        return SectionFailureDisposition.OMITTED
    if (
        all_optional
        and rule.capability is OrchestratorCapability.NEWS_RETRIEVER
        and rule.signal is FailureSignal.HEALTHY_NO_MATCH
    ):
        return SectionFailureDisposition.OMITTED
    return rule.section_disposition
