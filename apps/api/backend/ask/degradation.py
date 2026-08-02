from __future__ import annotations

import json
from enum import StrEnum
from typing import Literal, Self

from pydantic import BaseModel, ConfigDict, Field, field_validator, model_validator

from backend.ask.knowledge_modes import (
    LIVE_REFRESH_UNAVAILABLE_NOTICE,
    NO_OFFICIAL_DOCUMENTS_DISCLOSURE,
    NO_VERIFIED_LIVE_UPDATES_NOTICE,
    OFFICIAL_SEARCH_UNAVAILABLE_DISCLOSURE,
)
from backend.ask.orchestration.contracts import (
    CapabilityTerminalState,
    OrchestratorCapability,
)
from backend.ask.orchestration.failure_policy import (
    FailureSignal,
    FailureTransitionDecision,
    SectionFailureDisposition,
)
from backend.ask.orchestration.retry import (
    RETRYABLE_CAPABILITIES,
    RETRYABLE_TERMINAL_STATES,
)

DEGRADATION_SCHEMA_VERSION = "1"
DEGRADATION_POLICY_VERSION = "ask-ai-capability-degradation-v1"

_INTENT_BODY = (
    "The request could not be interpreted reliably. Clarify the intended "
    "question; no evidence conclusion has been made."
)
_ENTITY_BODY = (
    "The named entity could not be resolved reliably. Choose the intended "
    "entity or refine the name before regulatory conclusions are shown."
)
_OFFICIAL_PARTIAL_BODY = (
    "Some official evidence is available, but coverage is incomplete. Existing "
    "sources remain available; search official documents manually for "
    "additional coverage."
)
_GRAPH_BODY = (
    "Structured relationships could not be completed. Official document facts "
    "and sources remain available."
)
_TIMELINE_BODY = (
    "A complete structured timeline could not be established. Verified dates "
    "and official sources remain available."
)
_LIVE_PARTIAL_BODY = (
    "Some live sources are available, but current coverage is incomplete. "
    "Internal Regulatory Corpus research remains available."
)
_LIVE_UNAVAILABLE_BODY = (
    "Internal Regulatory Corpus research remains available. Live coverage is "
    "unknown until sources are refreshed."
)
_GENERAL_UNAVAILABLE_BODY = (
    "AI synthesis is temporarily unavailable. Retrieved evidence and manual "
    "document search remain available."
)
_CLAIM_REJECTED_BODY = (
    "The unsupported claim was withheld or narrowed. Other verified claims and "
    "source excerpts remain available."
)
_EVIDENCE_REJECTED_BODY = (
    "One or more evidence links could not be verified. Stored source metadata, "
    "excerpts, and manual document search remain available."
)
_VERIFICATION_UNAVAILABLE_BODY = (
    "Verified source excerpts remain available, but synthesized claims are "
    "withheld until citation verification succeeds."
)
_COMPOSER_UNAVAILABLE_BODY = (
    "Verified evidence and structured results remain available without "
    "generated narrative."
)


class DegradationSeverity(StrEnum):
    INFORMATION = "information"
    LIMITED = "limited"
    UNAVAILABLE = "unavailable"
    NEEDS_INPUT = "needs_input"


class DegradationConfidenceEffect(StrEnum):
    UNCHANGED = "unchanged"
    LIMITED = "limited"
    UNKNOWN = "unknown"


class DegradationActionType(StrEnum):
    RETRY_OFFICIAL_SEARCH = "retry_official_search"
    REFRESH_LIVE_SOURCES = "refresh_live_sources"
    RETRY_EXPLANATION = "retry_explanation"
    RETRY_CITATION_VERIFICATION = "retry_citation_verification"
    SEARCH_OFFICIAL_DOCUMENTS_MANUALLY = "search_official_documents_manually"
    CLARIFY_REQUEST = "clarify_request"
    CHOOSE_ENTITY = "choose_entity"


class DegradationActionKind(StrEnum):
    CAPABILITY_RETRY = "capability_retry"
    NAVIGATE = "navigate"
    PROVIDE_INPUT = "provide_input"


class DegradationModel(BaseModel):
    model_config = ConfigDict(
        extra="forbid",
        frozen=True,
        strict=True,
        str_strip_whitespace=True,
    )


class DegradationAction(DegradationModel):
    action: DegradationActionType
    kind: DegradationActionKind
    label: str = Field(min_length=1, max_length=100)
    target: str = Field(min_length=1, max_length=2_000)
    capability: OrchestratorCapability | None = None

    @model_validator(mode="after")
    def validate_action(self) -> Self:
        if self.kind is DegradationActionKind.CAPABILITY_RETRY:
            if self.capability not in RETRYABLE_CAPABILITIES:
                raise ValueError("Retry action requires one retryable capability")
        elif self.capability is not None:
            raise ValueError("Only retry actions identify a capability")
        if self.kind is DegradationActionKind.NAVIGATE:
            _validate_local_target(self.target)
        return self


class DegradationProjectionRequest(DegradationModel):
    decision: FailureTransitionDecision
    explicitly_requested: bool = True
    capability_retry_available: bool = False
    manual_search_target: str = "/browse"

    @field_validator("manual_search_target")
    @classmethod
    def validate_manual_target(cls, value: str) -> str:
        return _validate_local_target(value)


class CapabilityDegradationProjection(DegradationModel):
    schema_version: Literal["1"] = DEGRADATION_SCHEMA_VERSION
    policy_version: Literal["ask-ai-capability-degradation-v1"] = (
        DEGRADATION_POLICY_VERSION
    )
    capability: OrchestratorCapability
    terminal_state: CapabilityTerminalState
    signal: FailureSignal
    visible: bool
    severity: DegradationSeverity | None
    title: str | None = Field(default=None, max_length=200)
    body: str | None = Field(default=None, max_length=2_000)
    confidence_effect: DegradationConfidenceEffect
    safe_notice_code: str = Field(pattern=r"^[A-Z][A-Z0-9_]{0,99}$")
    affected_section_ids: tuple[str, ...]
    unaffected_section_ids: tuple[str, ...]
    preserved_artifact_ids: tuple[str, ...]
    actions: tuple[DegradationAction, ...] = ()

    @model_validator(mode="after")
    def validate_projection(self) -> Self:
        if self.visible:
            if self.severity is None or not self.title or not self.body:
                raise ValueError("Visible degradation requires safe product copy")
        elif any((self.severity, self.title, self.body, self.actions)):
            raise ValueError("Hidden degradation cannot expose presentation")
        if len({item.action for item in self.actions}) != len(self.actions):
            raise ValueError("Degradation actions must be unique")
        for action in self.actions:
            if action.kind is DegradationActionKind.CAPABILITY_RETRY:
                if (
                    action.capability is not self.capability
                    or self.terminal_state not in RETRYABLE_TERMINAL_STATES
                ):
                    raise ValueError("Retry action crossed its failed capability")
        if set(self.affected_section_ids) & set(self.unaffected_section_ids):
            raise ValueError("Affected and unaffected sections must remain disjoint")
        return self


def project_capability_degradation(
    request: DegradationProjectionRequest,
) -> CapabilityDegradationProjection:
    request = DegradationProjectionRequest.model_validate_json(
        request.model_dump_json()
    )
    decision = request.decision
    hidden = (
        decision.section_disposition
        in {
            SectionFailureDisposition.OMITTED,
            SectionFailureDisposition.CORE_UNCHANGED,
        }
        or (
            decision.capability is OrchestratorCapability.NEWS_RETRIEVER
            and decision.signal is FailureSignal.HEALTHY_NO_MATCH
            and not request.explicitly_requested
        )
    )
    if hidden:
        return _projection(
            decision,
            visible=False,
            severity=None,
            title=None,
            body=None,
            confidence_effect=DegradationConfidenceEffect.UNCHANGED,
            actions=(),
        )
    severity, title, body, confidence = _copy(decision)
    actions = _actions(request)
    return _projection(
        decision,
        visible=True,
        severity=severity,
        title=title,
        body=body,
        confidence_effect=confidence,
        actions=actions,
    )


def degradation_projection_json(
    projection: CapabilityDegradationProjection,
) -> str:
    return json.dumps(
        projection.model_dump(mode="json"),
        ensure_ascii=False,
        separators=(",", ":"),
        sort_keys=True,
    )


def _copy(
    decision: FailureTransitionDecision,
) -> tuple[
    DegradationSeverity,
    str,
    str,
    DegradationConfidenceEffect,
]:
    capability = decision.capability
    signal = decision.signal
    if capability is OrchestratorCapability.INTENT_CLASSIFIER:
        return (
            DegradationSeverity.NEEDS_INPUT,
            "Clarification needed",
            _INTENT_BODY,
            DegradationConfidenceEffect.UNKNOWN,
        )
    if capability is OrchestratorCapability.ENTITY_RESOLVER:
        return (
            DegradationSeverity.NEEDS_INPUT,
            "Entity selection needed",
            _ENTITY_BODY,
            DegradationConfidenceEffect.UNKNOWN,
        )
    if capability is OrchestratorCapability.REGULATORY_RETRIEVER:
        if signal is FailureSignal.HEALTHY_NO_MATCH:
            return (
                DegradationSeverity.INFORMATION,
                "No official documents found",
                NO_OFFICIAL_DOCUMENTS_DISCLOSURE,
                DegradationConfidenceEffect.LIMITED,
            )
        if signal is FailureSignal.PARTIAL:
            return (
                DegradationSeverity.LIMITED,
                "Official evidence coverage is incomplete",
                _OFFICIAL_PARTIAL_BODY,
                DegradationConfidenceEffect.LIMITED,
            )
        return (
            DegradationSeverity.UNAVAILABLE,
            "Official search temporarily unavailable",
            OFFICIAL_SEARCH_UNAVAILABLE_DISCLOSURE,
            DegradationConfidenceEffect.UNKNOWN,
        )
    if capability is OrchestratorCapability.KNOWLEDGE_GRAPH:
        return (
            DegradationSeverity.LIMITED,
            "Relationship coverage is incomplete",
            _GRAPH_BODY,
            DegradationConfidenceEffect.LIMITED,
        )
    if capability is OrchestratorCapability.TIMELINE_BUILDER:
        return (
            DegradationSeverity.LIMITED,
            "Timeline coverage is incomplete",
            _TIMELINE_BODY,
            DegradationConfidenceEffect.LIMITED,
        )
    if capability is OrchestratorCapability.NEWS_RETRIEVER:
        if signal is FailureSignal.HEALTHY_NO_MATCH:
            return (
                DegradationSeverity.INFORMATION,
                "No live updates found",
                NO_VERIFIED_LIVE_UPDATES_NOTICE,
                DegradationConfidenceEffect.UNCHANGED,
            )
        if signal is FailureSignal.PARTIAL:
            return (
                DegradationSeverity.LIMITED,
                "Live source coverage is incomplete",
                _LIVE_PARTIAL_BODY,
                DegradationConfidenceEffect.LIMITED,
            )
        return (
            DegradationSeverity.UNAVAILABLE,
            LIVE_REFRESH_UNAVAILABLE_NOTICE,
            _LIVE_UNAVAILABLE_BODY,
            DegradationConfidenceEffect.UNKNOWN,
        )
    if capability is OrchestratorCapability.GENERAL_AI:
        return (
            DegradationSeverity.UNAVAILABLE,
            "General explanation unavailable",
            _GENERAL_UNAVAILABLE_BODY,
            DegradationConfidenceEffect.UNCHANGED,
        )
    if capability is OrchestratorCapability.CITATION_VERIFIER:
        if signal is FailureSignal.CLAIM_REJECTED:
            return (
                DegradationSeverity.LIMITED,
                "One claim could not be verified",
                _CLAIM_REJECTED_BODY,
                DegradationConfidenceEffect.LIMITED,
            )
        if signal is FailureSignal.EVIDENCE_REJECTED:
            return (
                DegradationSeverity.LIMITED,
                "Evidence verification is incomplete",
                _EVIDENCE_REJECTED_BODY,
                DegradationConfidenceEffect.LIMITED,
            )
        return (
            DegradationSeverity.UNAVAILABLE,
            "Citation verification incomplete",
            _VERIFICATION_UNAVAILABLE_BODY,
            DegradationConfidenceEffect.UNKNOWN,
        )
    if capability is OrchestratorCapability.RESPONSE_COMPOSER:
        return (
            DegradationSeverity.UNAVAILABLE,
            "Synthesis temporarily unavailable",
            _COMPOSER_UNAVAILABLE_BODY,
            DegradationConfidenceEffect.UNCHANGED,
        )
    return (
        DegradationSeverity.INFORMATION,
        "Follow-up suggestions unavailable",
        "The completed research remains available. Follow-up suggestions were omitted.",
        DegradationConfidenceEffect.UNCHANGED,
    )


def _actions(
    request: DegradationProjectionRequest,
) -> tuple[DegradationAction, ...]:
    decision = request.decision
    actions: list[DegradationAction] = []
    retry_action = _retry_action(decision)
    if request.capability_retry_available and retry_action is not None:
        actions.append(retry_action)
    if decision.capability is OrchestratorCapability.REGULATORY_RETRIEVER:
        actions.append(_manual_search(request.manual_search_target))
    elif decision.capability is OrchestratorCapability.GENERAL_AI:
        actions.append(_manual_search(request.manual_search_target))
    elif (
        decision.capability is OrchestratorCapability.CITATION_VERIFIER
        and decision.signal is FailureSignal.EVIDENCE_REJECTED
    ):
        actions.append(_manual_search(request.manual_search_target))
    elif decision.capability is OrchestratorCapability.INTENT_CLASSIFIER:
        actions.append(
            DegradationAction(
                action=DegradationActionType.CLARIFY_REQUEST,
                kind=DegradationActionKind.PROVIDE_INPUT,
                label="Clarify request",
                target=decision.failed_node_id,
            )
        )
    elif decision.capability is OrchestratorCapability.ENTITY_RESOLVER:
        actions.append(
            DegradationAction(
                action=DegradationActionType.CHOOSE_ENTITY,
                kind=DegradationActionKind.PROVIDE_INPUT,
                label="Choose entity",
                target=decision.failed_node_id,
            )
        )
    return tuple(actions)


def _retry_action(
    decision: FailureTransitionDecision,
) -> DegradationAction | None:
    if (
        decision.capability not in RETRYABLE_CAPABILITIES
        or decision.terminal_state not in RETRYABLE_TERMINAL_STATES
    ):
        return None
    action, label = {
        OrchestratorCapability.REGULATORY_RETRIEVER: (
            DegradationActionType.RETRY_OFFICIAL_SEARCH,
            "Retry official search",
        ),
        OrchestratorCapability.NEWS_RETRIEVER: (
            DegradationActionType.REFRESH_LIVE_SOURCES,
            "Refresh live sources",
        ),
        OrchestratorCapability.GENERAL_AI: (
            DegradationActionType.RETRY_EXPLANATION,
            "Retry explanation",
        ),
        OrchestratorCapability.CITATION_VERIFIER: (
            DegradationActionType.RETRY_CITATION_VERIFICATION,
            "Retry citation verification",
        ),
    }[decision.capability]
    return DegradationAction(
        action=action,
        kind=DegradationActionKind.CAPABILITY_RETRY,
        label=label,
        target=decision.failed_node_id,
        capability=decision.capability,
    )


def _manual_search(target: str) -> DegradationAction:
    return DegradationAction(
        action=DegradationActionType.SEARCH_OFFICIAL_DOCUMENTS_MANUALLY,
        kind=DegradationActionKind.NAVIGATE,
        label="Search official documents manually",
        target=target,
    )


def _projection(
    decision: FailureTransitionDecision,
    *,
    visible: bool,
    severity: DegradationSeverity | None,
    title: str | None,
    body: str | None,
    confidence_effect: DegradationConfidenceEffect,
    actions: tuple[DegradationAction, ...],
) -> CapabilityDegradationProjection:
    return CapabilityDegradationProjection(
        capability=decision.capability,
        terminal_state=decision.terminal_state,
        signal=decision.signal,
        visible=visible,
        severity=severity,
        title=title,
        body=body,
        confidence_effect=confidence_effect,
        safe_notice_code=decision.safe_notice_code,
        affected_section_ids=decision.affected_section_ids,
        unaffected_section_ids=decision.unaffected_section_ids,
        preserved_artifact_ids=decision.preserved_artifact_ids,
        actions=actions,
    )


def _validate_local_target(value: str) -> str:
    normalized = value.strip()
    if (
        not normalized.startswith("/")
        or normalized.startswith("//")
        or "\\" in normalized
        or any(character.isspace() for character in normalized)
    ):
        raise ValueError("Navigation target must be one safe local path")
    return normalized
