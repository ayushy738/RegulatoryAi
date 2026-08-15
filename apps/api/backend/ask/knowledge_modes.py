from __future__ import annotations

import json
from enum import StrEnum
from typing import Literal, Self

from pydantic import BaseModel, ConfigDict, Field, field_validator, model_validator

from backend.ask.decision.models import ConfidenceLabel, KnowledgeMode
from backend.ask.orchestration.contracts import ProvenanceClass

KNOWLEDGE_MODE_SCHEMA_VERSION = "1"
KNOWLEDGE_MODE_POLICY_VERSION = "ask-ai-knowledge-mode-v1"

NO_OFFICIAL_DOCUMENTS_DISCLOSURE = (
    "This explanation is generated from general AI knowledge because no "
    "sufficiently relevant official corpus evidence was selected for this question."
)
OFFICIAL_SEARCH_UNAVAILABLE_DISCLOSURE = (
    "Official document search is temporarily unavailable. You can still view "
    "previously retrieved sources or search documents manually. Any "
    "explanation generated now will be labeled as general AI knowledge."
)
NO_VERIFIED_LIVE_UPDATES_NOTICE = (
    "No verified live updates were found for this period."
)
LIVE_REFRESH_UNAVAILABLE_NOTICE = "Live sources could not be refreshed"


class OfficialEvidenceOutcome(StrEnum):
    NOT_REQUIRED = "not_required"
    PENDING = "pending"
    SUFFICIENT = "sufficient"
    PARTIAL = "partial"
    HEALTHY_NO_MATCH = "healthy_no_match"
    UNAVAILABLE = "unavailable"
    SELECTED_DOCUMENT_UNAVAILABLE = "selected_document_unavailable"


class LiveEvidenceOutcome(StrEnum):
    NOT_REQUESTED = "not_requested"
    PENDING = "pending"
    FOUND_OFFICIAL = "found_official"
    FOUND_CREDIBLE_REPORTING = "found_credible_reporting"
    FOUND_UNVERIFIED = "found_unverified"
    HEALTHY_NO_MATCH = "healthy_no_match"
    UNAVAILABLE = "unavailable"


class ScopeResolutionState(StrEnum):
    RESOLVED = "resolved"
    BOUNDED_ASSUMPTION = "bounded_assumption"
    MATERIAL_UNRESOLVED = "material_unresolved"
    LEGAL_STATUS_UNRESOLVED = "legal_status_unresolved"


class ModeSelectionState(StrEnum):
    READY = "ready"
    WAITING = "waiting"
    DEGRADED = "degraded"
    EMPTY_BY_EVIDENCE = "empty_by_evidence"
    NEEDS_DOCUMENT = "needs_document"


class ModeTrigger(StrEnum):
    SUFFICIENT_OFFICIAL_EVIDENCE = "sufficient_official_evidence"
    PARTIAL_OFFICIAL_EVIDENCE = "partial_official_evidence"
    HEALTHY_OFFICIAL_NO_MATCH = "healthy_official_no_match"
    OFFICIAL_RETRIEVAL_UNAVAILABLE = "official_retrieval_unavailable"
    EXPLICIT_GENERAL_QUESTION = "explicit_general_question"
    OPTIONAL_GENERAL_BACKGROUND = "optional_general_background"
    OFFICIAL_LIVE_SOURCE = "official_live_source"
    CREDIBLE_LIVE_REPORTING = "credible_live_reporting"
    UNVERIFIED_LIVE_SOURCE = "unverified_live_source"


class CitationCardPolicy(StrEnum):
    REQUIRED = "required"
    PROHIBITED = "prohibited"


class SourcePresentationPolicy(StrEnum):
    OFFICIAL_CITATIONS = "official_citations"
    NO_SOURCE_IDENTITY = "no_source_identity"
    LIVE_SOURCE_ATTRIBUTION = "live_source_attribution"


class LegalForcePolicy(StrEnum):
    VERIFIED_OFFICIAL_STATUS_ONLY = "verified_official_status_only"
    PROHIBITED = "prohibited"


class ProhibitedClaim(StrEnum):
    UNSUPPORTED_MATERIAL_FACT = "unsupported_material_fact"
    OFFICIAL_INTERPRETATION = "official_interpretation"
    SPECIFIC_LEGAL_APPLICABILITY = "specific_legal_applicability"
    BINDING_OBLIGATION = "binding_obligation"
    FABRICATED_CITATION_IDENTITY = "fabricated_citation_identity"
    LEGAL_FORCE_FROM_LIVE_REPORTING = "legal_force_from_live_reporting"


class ModeNoticeCode(StrEnum):
    OFFICIAL_SEARCH_UNAVAILABLE = "official_search_unavailable"
    NO_VERIFIED_LIVE_UPDATES = "no_verified_live_updates"
    LIVE_REFRESH_UNAVAILABLE = "live_refresh_unavailable"


class KnowledgeModeModel(BaseModel):
    model_config = ConfigDict(
        extra="forbid",
        frozen=True,
        strict=True,
        str_strip_whitespace=True,
    )


class KnowledgeModeRequest(KnowledgeModeModel):
    official_outcome: OfficialEvidenceOutcome
    live_outcome: LiveEvidenceOutcome = LiveEvidenceOutcome.NOT_REQUESTED
    explicit_general_question: bool = False
    include_general_background: bool = False
    qualified_general_fallback_allowed: bool = False
    scope_state: ScopeResolutionState = ScopeResolutionState.RESOLVED

    @model_validator(mode="after")
    def validate_request(self) -> Self:
        if (
            self.explicit_general_question
            and self.official_outcome is not OfficialEvidenceOutcome.NOT_REQUIRED
        ):
            raise ValueError(
                "An explicit general question does not run official retrieval"
            )
        if (
            self.qualified_general_fallback_allowed
            and self.official_outcome is not OfficialEvidenceOutcome.UNAVAILABLE
        ):
            raise ValueError(
                "Qualified General AI fallback applies only to retrieval outage"
            )
        if (
            self.official_outcome
            is OfficialEvidenceOutcome.SELECTED_DOCUMENT_UNAVAILABLE
            and (
                self.live_outcome is not LiveEvidenceOutcome.NOT_REQUESTED
                or self.include_general_background
                or self.qualified_general_fallback_allowed
                or self.explicit_general_question
            )
        ):
            raise ValueError(
                "An unavailable selected-document explanation cannot add other lanes"
            )
        if (
            self.official_outcome is OfficialEvidenceOutcome.NOT_REQUIRED
            and not self.explicit_general_question
            and self.live_outcome is LiveEvidenceOutcome.NOT_REQUESTED
        ):
            raise ValueError("At least one knowledge lane must be requested")
        return self


class ModeNotice(KnowledgeModeModel):
    code: ModeNoticeCode
    text: str = Field(min_length=1)

    @model_validator(mode="after")
    def require_frozen_copy(self) -> Self:
        expected = {
            ModeNoticeCode.OFFICIAL_SEARCH_UNAVAILABLE: (
                OFFICIAL_SEARCH_UNAVAILABLE_DISCLOSURE
            ),
            ModeNoticeCode.NO_VERIFIED_LIVE_UPDATES: (
                NO_VERIFIED_LIVE_UPDATES_NOTICE
            ),
            ModeNoticeCode.LIVE_REFRESH_UNAVAILABLE: (
                LIVE_REFRESH_UNAVAILABLE_NOTICE
            ),
        }[self.code]
        if self.text != expected:
            raise ValueError("Mode notice must use frozen product copy")
        return self


class KnowledgeModeSectionPolicy(KnowledgeModeModel):
    section_key: str = Field(min_length=1)
    mode: KnowledgeMode
    trigger: ModeTrigger
    provenance_lane: ProvenanceClass
    confidence_ceiling: ConfidenceLabel
    citation_cards: CitationCardPolicy
    source_presentation: SourcePresentationPolicy
    required_disclosure: str | None = None
    official_claim_verification_required: bool
    legal_force_policy: LegalForcePolicy
    prohibited_claims: tuple[ProhibitedClaim, ...]
    reason_code: str = Field(pattern=r"^[A-Z][A-Z0-9_]{0,99}$")

    @field_validator("section_key")
    @classmethod
    def normalize_section_key(cls, value: str) -> str:
        normalized = value.strip()
        if not normalized:
            raise ValueError("Section key cannot be blank")
        return normalized

    @model_validator(mode="after")
    def enforce_mode_lane(self) -> Self:
        expected_lane = {
            KnowledgeMode.GROUNDED_REGULATORY: (
                ProvenanceClass.INTERNAL_REGULATORY_CORPUS
            ),
            KnowledgeMode.GENERAL_AI: ProvenanceClass.GENERAL_AI_KNOWLEDGE,
            KnowledgeMode.LIVE_INTELLIGENCE: ProvenanceClass.LIVE_WEB_SOURCES,
        }[self.mode]
        if self.provenance_lane is not expected_lane:
            raise ValueError("A section cannot cross knowledge provenance lanes")

        if self.mode is KnowledgeMode.GROUNDED_REGULATORY:
            self._validate_grounded()
        elif self.mode is KnowledgeMode.GENERAL_AI:
            self._validate_general_ai()
        else:
            self._validate_live()
        return self

    def _validate_grounded(self) -> None:
        if self.trigger not in {
            ModeTrigger.SUFFICIENT_OFFICIAL_EVIDENCE,
            ModeTrigger.PARTIAL_OFFICIAL_EVIDENCE,
        }:
            raise ValueError("Mode 1 requires admitted official evidence")
        if self.citation_cards is not CitationCardPolicy.REQUIRED:
            raise ValueError("Mode 1 material claims require citation cards")
        if (
            self.source_presentation
            is not SourcePresentationPolicy.OFFICIAL_CITATIONS
        ):
            raise ValueError("Mode 1 requires official citation presentation")
        if self.required_disclosure is not None:
            raise ValueError("Mode 1 does not use a General AI disclosure")
        if not self.official_claim_verification_required:
            raise ValueError("Mode 1 material claims require verification")
        if (
            self.legal_force_policy
            is not LegalForcePolicy.VERIFIED_OFFICIAL_STATUS_ONLY
        ):
            raise ValueError(
                "Mode 1 legal force requires verified official status evidence"
            )
        if self.prohibited_claims != (
            ProhibitedClaim.UNSUPPORTED_MATERIAL_FACT,
        ):
            raise ValueError("Mode 1 must prohibit unsupported material facts")
        base = (
            ConfidenceLabel.HIGH
            if self.trigger is ModeTrigger.SUFFICIENT_OFFICIAL_EVIDENCE
            else ConfidenceLabel.MEDIUM
        )
        _require_at_or_below(self.confidence_ceiling, base)

    def _validate_general_ai(self) -> None:
        if self.trigger not in {
            ModeTrigger.HEALTHY_OFFICIAL_NO_MATCH,
            ModeTrigger.OFFICIAL_RETRIEVAL_UNAVAILABLE,
            ModeTrigger.EXPLICIT_GENERAL_QUESTION,
            ModeTrigger.OPTIONAL_GENERAL_BACKGROUND,
        }:
            raise ValueError("Mode 2 requires an eligible General AI trigger")
        if self.citation_cards is not CitationCardPolicy.PROHIBITED:
            raise ValueError("Mode 2 cannot create citation cards")
        if (
            self.source_presentation
            is not SourcePresentationPolicy.NO_SOURCE_IDENTITY
        ):
            raise ValueError("Mode 2 cannot borrow source identity")
        expected_disclosure = (
            NO_OFFICIAL_DOCUMENTS_DISCLOSURE
            if self.trigger is ModeTrigger.HEALTHY_OFFICIAL_NO_MATCH
            else (
                OFFICIAL_SEARCH_UNAVAILABLE_DISCLOSURE
                if self.trigger is ModeTrigger.OFFICIAL_RETRIEVAL_UNAVAILABLE
                else None
            )
        )
        if self.required_disclosure != expected_disclosure:
            raise ValueError("Mode 2 disclosure does not match its evidence trigger")
        if self.official_claim_verification_required:
            raise ValueError("Mode 2 is not verified or presented as Mode 1")
        if self.legal_force_policy is not LegalForcePolicy.PROHIBITED:
            raise ValueError("Mode 2 cannot assert legal force")
        if self.prohibited_claims != _GENERAL_AI_PROHIBITIONS:
            raise ValueError("Mode 2 prohibited claims must remain complete")
        base = (
            ConfidenceLabel.LOW
            if self.trigger is ModeTrigger.OFFICIAL_RETRIEVAL_UNAVAILABLE
            else ConfidenceLabel.MEDIUM
        )
        _require_at_or_below(self.confidence_ceiling, base)

    def _validate_live(self) -> None:
        base = {
            ModeTrigger.OFFICIAL_LIVE_SOURCE: ConfidenceLabel.HIGH,
            ModeTrigger.CREDIBLE_LIVE_REPORTING: ConfidenceLabel.MEDIUM,
            ModeTrigger.UNVERIFIED_LIVE_SOURCE: ConfidenceLabel.UNKNOWN,
        }.get(self.trigger)
        if base is None:
            raise ValueError("Mode 3 requires a live-source trigger")
        if self.citation_cards is not CitationCardPolicy.PROHIBITED:
            raise ValueError("Mode 3 uses live links, not official citation cards")
        if (
            self.source_presentation
            is not SourcePresentationPolicy.LIVE_SOURCE_ATTRIBUTION
        ):
            raise ValueError("Mode 3 requires live source attribution")
        if self.required_disclosure is not None:
            raise ValueError("Live notices remain separate from source sections")
        if self.official_claim_verification_required:
            raise ValueError("Mode 3 is not verified or presented as Mode 1")
        if self.legal_force_policy is not LegalForcePolicy.PROHIBITED:
            raise ValueError("A live source cannot establish legal force")
        if self.prohibited_claims != _LIVE_PROHIBITIONS:
            raise ValueError("Mode 3 prohibited claims must remain complete")
        _require_at_or_below(self.confidence_ceiling, base)


class KnowledgeModeDecision(KnowledgeModeModel):
    schema_version: Literal["1"] = KNOWLEDGE_MODE_SCHEMA_VERSION
    policy_version: str = Field(
        default=KNOWLEDGE_MODE_POLICY_VERSION,
        min_length=1,
    )
    state: ModeSelectionState
    sections: tuple[KnowledgeModeSectionPolicy, ...]
    notices: tuple[ModeNotice, ...] = ()
    pending_lanes: tuple[ProvenanceClass, ...] = ()
    blocking_code: str | None = Field(
        default=None,
        pattern=r"^[A-Z][A-Z0-9_]{0,99}$",
    )

    @model_validator(mode="after")
    def validate_decision(self) -> Self:
        section_keys = tuple(section.section_key for section in self.sections)
        if len(set(section_keys)) != len(section_keys):
            raise ValueError("Knowledge-mode section keys must be unique")
        notice_codes = tuple(notice.code for notice in self.notices)
        if len(set(notice_codes)) != len(notice_codes):
            raise ValueError("Mode notices must be unique")
        if len(set(self.pending_lanes)) != len(self.pending_lanes):
            raise ValueError("Pending provenance lanes must be unique")
        waiting = self.state is ModeSelectionState.WAITING
        if waiting != bool(self.pending_lanes):
            raise ValueError("Only a waiting decision has pending lanes")
        expected_blocked = self.state is ModeSelectionState.NEEDS_DOCUMENT
        if expected_blocked != (self.blocking_code is not None):
            raise ValueError("Only a document-blocked decision has a blocking code")
        if expected_blocked and self.sections:
            raise ValueError("An unavailable selected document cannot produce content")
        if self.state is ModeSelectionState.READY and not self.sections:
            raise ValueError("A ready mode decision requires content")
        if (
            self.state is ModeSelectionState.EMPTY_BY_EVIDENCE
            and self.sections
        ):
            raise ValueError("An evidence-empty decision cannot contain sections")
        if self.state is ModeSelectionState.DEGRADED and not self.notices:
            raise ValueError("A degraded mode decision requires a safe notice")
        return self


_GENERAL_AI_PROHIBITIONS = (
    ProhibitedClaim.OFFICIAL_INTERPRETATION,
    ProhibitedClaim.SPECIFIC_LEGAL_APPLICABILITY,
    ProhibitedClaim.BINDING_OBLIGATION,
    ProhibitedClaim.FABRICATED_CITATION_IDENTITY,
)
_LIVE_PROHIBITIONS = (
    ProhibitedClaim.LEGAL_FORCE_FROM_LIVE_REPORTING,
    ProhibitedClaim.FABRICATED_CITATION_IDENTITY,
)
_CONFIDENCE_ORDER = {
    ConfidenceLabel.UNKNOWN: 0,
    ConfidenceLabel.LOW: 1,
    ConfidenceLabel.MEDIUM: 2,
    ConfidenceLabel.HIGH: 3,
}


def select_knowledge_modes(
    request: KnowledgeModeRequest,
) -> KnowledgeModeDecision:
    if (
        request.official_outcome
        is OfficialEvidenceOutcome.SELECTED_DOCUMENT_UNAVAILABLE
    ):
        return KnowledgeModeDecision(
            state=ModeSelectionState.NEEDS_DOCUMENT,
            sections=(),
            blocking_code="SELECTED_DOCUMENT_UNAVAILABLE",
        )

    sections: list[KnowledgeModeSectionPolicy] = []
    notices: list[ModeNotice] = []
    official = request.official_outcome
    live = request.live_outcome

    if official in {
        OfficialEvidenceOutcome.SUFFICIENT,
        OfficialEvidenceOutcome.PARTIAL,
    }:
        sections.append(_official_section(official, request.scope_state))

    live_found = live in {
        LiveEvidenceOutcome.FOUND_OFFICIAL,
        LiveEvidenceOutcome.FOUND_CREDIBLE_REPORTING,
        LiveEvidenceOutcome.FOUND_UNVERIFIED,
    }
    if live_found:
        sections.append(_live_section(live, request.scope_state))

    if official is OfficialEvidenceOutcome.UNAVAILABLE:
        notices.append(
            ModeNotice(
                code=ModeNoticeCode.OFFICIAL_SEARCH_UNAVAILABLE,
                text=OFFICIAL_SEARCH_UNAVAILABLE_DISCLOSURE,
            )
        )
    if live is LiveEvidenceOutcome.HEALTHY_NO_MATCH:
        notices.append(
            ModeNotice(
                code=ModeNoticeCode.NO_VERIFIED_LIVE_UPDATES,
                text=NO_VERIFIED_LIVE_UPDATES_NOTICE,
            )
        )
    elif live is LiveEvidenceOutcome.UNAVAILABLE:
        notices.append(
            ModeNotice(
                code=ModeNoticeCode.LIVE_REFRESH_UNAVAILABLE,
                text=LIVE_REFRESH_UNAVAILABLE_NOTICE,
            )
        )

    general_trigger = _general_trigger(request, live_found=live_found)
    if general_trigger is not None:
        sections.append(_general_section(general_trigger, request.scope_state))

    pending = (
        official is OfficialEvidenceOutcome.PENDING
        or live is LiveEvidenceOutcome.PENDING
    )
    pending_lanes = tuple(
        lane
        for is_pending, lane in (
            (
                official is OfficialEvidenceOutcome.PENDING,
                ProvenanceClass.INTERNAL_REGULATORY_CORPUS,
            ),
            (
                live is LiveEvidenceOutcome.PENDING,
                ProvenanceClass.LIVE_WEB_SOURCES,
            ),
        )
        if is_pending
    )
    degraded = (
        official is OfficialEvidenceOutcome.UNAVAILABLE
        or live is LiveEvidenceOutcome.UNAVAILABLE
    )
    state = (
        ModeSelectionState.WAITING
        if pending
        else (
            ModeSelectionState.DEGRADED
            if degraded
            else (
                ModeSelectionState.READY
                if sections
                else ModeSelectionState.EMPTY_BY_EVIDENCE
            )
        )
    )
    return KnowledgeModeDecision(
        state=state,
        sections=tuple(sections),
        notices=tuple(notices),
        pending_lanes=pending_lanes,
    )


def knowledge_mode_decision_json(decision: KnowledgeModeDecision) -> str:
    return json.dumps(
        decision.model_dump(mode="json"),
        ensure_ascii=False,
        separators=(",", ":"),
        sort_keys=True,
    )


def _general_trigger(
    request: KnowledgeModeRequest,
    *,
    live_found: bool,
) -> ModeTrigger | None:
    official = request.official_outcome
    if request.explicit_general_question:
        return ModeTrigger.EXPLICIT_GENERAL_QUESTION
    if official is OfficialEvidenceOutcome.PENDING:
        return None
    if official is OfficialEvidenceOutcome.HEALTHY_NO_MATCH:
        if (
            request.live_outcome is LiveEvidenceOutcome.PENDING
            and not request.include_general_background
        ):
            return None
        if live_found and not request.include_general_background:
            return None
        return ModeTrigger.HEALTHY_OFFICIAL_NO_MATCH
    if official is OfficialEvidenceOutcome.UNAVAILABLE:
        if not request.qualified_general_fallback_allowed:
            return None
        if live_found and not request.include_general_background:
            return None
        return ModeTrigger.OFFICIAL_RETRIEVAL_UNAVAILABLE
    if request.include_general_background:
        return ModeTrigger.OPTIONAL_GENERAL_BACKGROUND
    return None


def _official_section(
    outcome: OfficialEvidenceOutcome,
    scope: ScopeResolutionState,
) -> KnowledgeModeSectionPolicy:
    trigger = (
        ModeTrigger.SUFFICIENT_OFFICIAL_EVIDENCE
        if outcome is OfficialEvidenceOutcome.SUFFICIENT
        else ModeTrigger.PARTIAL_OFFICIAL_EVIDENCE
    )
    base = (
        ConfidenceLabel.HIGH
        if outcome is OfficialEvidenceOutcome.SUFFICIENT
        else ConfidenceLabel.MEDIUM
    )
    return KnowledgeModeSectionPolicy(
        section_key="official",
        mode=KnowledgeMode.GROUNDED_REGULATORY,
        trigger=trigger,
        provenance_lane=ProvenanceClass.INTERNAL_REGULATORY_CORPUS,
        confidence_ceiling=_apply_scope_ceiling(base, scope),
        citation_cards=CitationCardPolicy.REQUIRED,
        source_presentation=SourcePresentationPolicy.OFFICIAL_CITATIONS,
        official_claim_verification_required=True,
        legal_force_policy=LegalForcePolicy.VERIFIED_OFFICIAL_STATUS_ONLY,
        prohibited_claims=(ProhibitedClaim.UNSUPPORTED_MATERIAL_FACT,),
        reason_code=(
            "MODE_1_OFFICIAL_EVIDENCE"
            if outcome is OfficialEvidenceOutcome.SUFFICIENT
            else "MODE_1_PARTIAL_OFFICIAL_EVIDENCE"
        ),
    )


def _general_section(
    trigger: ModeTrigger,
    scope: ScopeResolutionState,
) -> KnowledgeModeSectionPolicy:
    base = (
        ConfidenceLabel.LOW
        if trigger is ModeTrigger.OFFICIAL_RETRIEVAL_UNAVAILABLE
        else ConfidenceLabel.MEDIUM
    )
    disclosure = (
        NO_OFFICIAL_DOCUMENTS_DISCLOSURE
        if trigger is ModeTrigger.HEALTHY_OFFICIAL_NO_MATCH
        else (
            OFFICIAL_SEARCH_UNAVAILABLE_DISCLOSURE
            if trigger is ModeTrigger.OFFICIAL_RETRIEVAL_UNAVAILABLE
            else None
        )
    )
    return KnowledgeModeSectionPolicy(
        section_key="general",
        mode=KnowledgeMode.GENERAL_AI,
        trigger=trigger,
        provenance_lane=ProvenanceClass.GENERAL_AI_KNOWLEDGE,
        confidence_ceiling=_apply_scope_ceiling(base, scope),
        citation_cards=CitationCardPolicy.PROHIBITED,
        source_presentation=SourcePresentationPolicy.NO_SOURCE_IDENTITY,
        required_disclosure=disclosure,
        official_claim_verification_required=False,
        legal_force_policy=LegalForcePolicy.PROHIBITED,
        prohibited_claims=_GENERAL_AI_PROHIBITIONS,
        reason_code={
            ModeTrigger.HEALTHY_OFFICIAL_NO_MATCH: (
                "MODE_2_HEALTHY_OFFICIAL_NO_MATCH"
            ),
            ModeTrigger.OFFICIAL_RETRIEVAL_UNAVAILABLE: (
                "MODE_2_OFFICIAL_RETRIEVAL_UNAVAILABLE"
            ),
            ModeTrigger.EXPLICIT_GENERAL_QUESTION: (
                "MODE_2_EXPLICIT_GENERAL_QUESTION"
            ),
            ModeTrigger.OPTIONAL_GENERAL_BACKGROUND: (
                "MODE_2_OPTIONAL_GENERAL_BACKGROUND"
            ),
        }[trigger],
    )


def _live_section(
    outcome: LiveEvidenceOutcome,
    scope: ScopeResolutionState,
) -> KnowledgeModeSectionPolicy:
    trigger, base, reason_code = {
        LiveEvidenceOutcome.FOUND_OFFICIAL: (
            ModeTrigger.OFFICIAL_LIVE_SOURCE,
            ConfidenceLabel.HIGH,
            "MODE_3_OFFICIAL_LIVE_SOURCE",
        ),
        LiveEvidenceOutcome.FOUND_CREDIBLE_REPORTING: (
            ModeTrigger.CREDIBLE_LIVE_REPORTING,
            ConfidenceLabel.MEDIUM,
            "MODE_3_CREDIBLE_LIVE_REPORTING",
        ),
        LiveEvidenceOutcome.FOUND_UNVERIFIED: (
            ModeTrigger.UNVERIFIED_LIVE_SOURCE,
            ConfidenceLabel.UNKNOWN,
            "MODE_3_UNVERIFIED_LIVE_SOURCE",
        ),
    }[outcome]
    return KnowledgeModeSectionPolicy(
        section_key="live",
        mode=KnowledgeMode.LIVE_INTELLIGENCE,
        trigger=trigger,
        provenance_lane=ProvenanceClass.LIVE_WEB_SOURCES,
        confidence_ceiling=_apply_scope_ceiling(base, scope),
        citation_cards=CitationCardPolicy.PROHIBITED,
        source_presentation=SourcePresentationPolicy.LIVE_SOURCE_ATTRIBUTION,
        official_claim_verification_required=False,
        legal_force_policy=LegalForcePolicy.PROHIBITED,
        prohibited_claims=_LIVE_PROHIBITIONS,
        reason_code=reason_code,
    )


def _apply_scope_ceiling(
    base: ConfidenceLabel,
    scope: ScopeResolutionState,
) -> ConfidenceLabel:
    scope_ceiling = {
        ScopeResolutionState.RESOLVED: ConfidenceLabel.HIGH,
        ScopeResolutionState.BOUNDED_ASSUMPTION: ConfidenceLabel.MEDIUM,
        ScopeResolutionState.MATERIAL_UNRESOLVED: ConfidenceLabel.UNKNOWN,
        ScopeResolutionState.LEGAL_STATUS_UNRESOLVED: ConfidenceLabel.UNKNOWN,
    }[scope]
    return min(
        (base, scope_ceiling),
        key=lambda item: _CONFIDENCE_ORDER[item],
    )


def _require_at_or_below(
    value: ConfidenceLabel,
    maximum: ConfidenceLabel,
) -> None:
    if _CONFIDENCE_ORDER[value] > _CONFIDENCE_ORDER[maximum]:
        raise ValueError("Knowledge-mode confidence exceeds its frozen ceiling")
