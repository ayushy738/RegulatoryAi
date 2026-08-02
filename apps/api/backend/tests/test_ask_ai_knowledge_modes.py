from __future__ import annotations

import json
from typing import Any

import pytest
from pydantic import ValidationError

from backend.ask.decision.models import ConfidenceLabel, KnowledgeMode
from backend.ask.knowledge_modes import (
    KNOWLEDGE_MODE_POLICY_VERSION,
    LIVE_REFRESH_UNAVAILABLE_NOTICE,
    NO_OFFICIAL_DOCUMENTS_DISCLOSURE,
    NO_VERIFIED_LIVE_UPDATES_NOTICE,
    OFFICIAL_SEARCH_UNAVAILABLE_DISCLOSURE,
    CitationCardPolicy,
    KnowledgeModeDecision,
    KnowledgeModeRequest,
    KnowledgeModeSectionPolicy,
    LegalForcePolicy,
    LiveEvidenceOutcome,
    ModeNotice,
    ModeNoticeCode,
    ModeSelectionState,
    ModeTrigger,
    OfficialEvidenceOutcome,
    ProhibitedClaim,
    ScopeResolutionState,
    SourcePresentationPolicy,
    knowledge_mode_decision_json,
    select_knowledge_modes,
)
from backend.ask.orchestration.contracts import ProvenanceClass


def _request(
    *,
    official: OfficialEvidenceOutcome = OfficialEvidenceOutcome.SUFFICIENT,
    live: LiveEvidenceOutcome = LiveEvidenceOutcome.NOT_REQUESTED,
    explicit_general: bool = False,
    general_background: bool = False,
    qualified_fallback: bool = False,
    scope: ScopeResolutionState = ScopeResolutionState.RESOLVED,
) -> KnowledgeModeRequest:
    return KnowledgeModeRequest(
        official_outcome=official,
        live_outcome=live,
        explicit_general_question=explicit_general,
        include_general_background=general_background,
        qualified_general_fallback_allowed=qualified_fallback,
        scope_state=scope,
    )


@pytest.mark.parametrize(
    (
        "mode_request",
        "state",
        "modes",
        "triggers",
        "ceilings",
        "notice_codes",
    ),
    [
        (
            _request(),
            ModeSelectionState.READY,
            (KnowledgeMode.GROUNDED_REGULATORY,),
            (ModeTrigger.SUFFICIENT_OFFICIAL_EVIDENCE,),
            (ConfidenceLabel.HIGH,),
            (),
        ),
        (
            _request(official=OfficialEvidenceOutcome.PARTIAL),
            ModeSelectionState.READY,
            (KnowledgeMode.GROUNDED_REGULATORY,),
            (ModeTrigger.PARTIAL_OFFICIAL_EVIDENCE,),
            (ConfidenceLabel.MEDIUM,),
            (),
        ),
        (
            _request(official=OfficialEvidenceOutcome.HEALTHY_NO_MATCH),
            ModeSelectionState.READY,
            (KnowledgeMode.GENERAL_AI,),
            (ModeTrigger.HEALTHY_OFFICIAL_NO_MATCH,),
            (ConfidenceLabel.MEDIUM,),
            (),
        ),
        (
            _request(official=OfficialEvidenceOutcome.UNAVAILABLE),
            ModeSelectionState.DEGRADED,
            (),
            (),
            (),
            (ModeNoticeCode.OFFICIAL_SEARCH_UNAVAILABLE,),
        ),
        (
            _request(
                official=OfficialEvidenceOutcome.UNAVAILABLE,
                qualified_fallback=True,
            ),
            ModeSelectionState.DEGRADED,
            (KnowledgeMode.GENERAL_AI,),
            (ModeTrigger.OFFICIAL_RETRIEVAL_UNAVAILABLE,),
            (ConfidenceLabel.LOW,),
            (ModeNoticeCode.OFFICIAL_SEARCH_UNAVAILABLE,),
        ),
        (
            _request(
                official=OfficialEvidenceOutcome.NOT_REQUIRED,
                explicit_general=True,
            ),
            ModeSelectionState.READY,
            (KnowledgeMode.GENERAL_AI,),
            (ModeTrigger.EXPLICIT_GENERAL_QUESTION,),
            (ConfidenceLabel.MEDIUM,),
            (),
        ),
        (
            _request(live=LiveEvidenceOutcome.FOUND_OFFICIAL),
            ModeSelectionState.READY,
            (
                KnowledgeMode.GROUNDED_REGULATORY,
                KnowledgeMode.LIVE_INTELLIGENCE,
            ),
            (
                ModeTrigger.SUFFICIENT_OFFICIAL_EVIDENCE,
                ModeTrigger.OFFICIAL_LIVE_SOURCE,
            ),
            (ConfidenceLabel.HIGH, ConfidenceLabel.HIGH),
            (),
        ),
        (
            _request(
                official=OfficialEvidenceOutcome.HEALTHY_NO_MATCH,
                live=LiveEvidenceOutcome.FOUND_CREDIBLE_REPORTING,
            ),
            ModeSelectionState.READY,
            (KnowledgeMode.LIVE_INTELLIGENCE,),
            (ModeTrigger.CREDIBLE_LIVE_REPORTING,),
            (ConfidenceLabel.MEDIUM,),
            (),
        ),
        (
            _request(
                official=OfficialEvidenceOutcome.HEALTHY_NO_MATCH,
                live=LiveEvidenceOutcome.FOUND_CREDIBLE_REPORTING,
                general_background=True,
            ),
            ModeSelectionState.READY,
            (
                KnowledgeMode.LIVE_INTELLIGENCE,
                KnowledgeMode.GENERAL_AI,
            ),
            (
                ModeTrigger.CREDIBLE_LIVE_REPORTING,
                ModeTrigger.HEALTHY_OFFICIAL_NO_MATCH,
            ),
            (ConfidenceLabel.MEDIUM, ConfidenceLabel.MEDIUM),
            (),
        ),
        (
            _request(live=LiveEvidenceOutcome.HEALTHY_NO_MATCH),
            ModeSelectionState.READY,
            (KnowledgeMode.GROUNDED_REGULATORY,),
            (ModeTrigger.SUFFICIENT_OFFICIAL_EVIDENCE,),
            (ConfidenceLabel.HIGH,),
            (ModeNoticeCode.NO_VERIFIED_LIVE_UPDATES,),
        ),
        (
            _request(
                official=OfficialEvidenceOutcome.HEALTHY_NO_MATCH,
                live=LiveEvidenceOutcome.HEALTHY_NO_MATCH,
            ),
            ModeSelectionState.READY,
            (KnowledgeMode.GENERAL_AI,),
            (ModeTrigger.HEALTHY_OFFICIAL_NO_MATCH,),
            (ConfidenceLabel.MEDIUM,),
            (ModeNoticeCode.NO_VERIFIED_LIVE_UPDATES,),
        ),
        (
            _request(
                official=OfficialEvidenceOutcome.UNAVAILABLE,
                live=LiveEvidenceOutcome.FOUND_CREDIBLE_REPORTING,
            ),
            ModeSelectionState.DEGRADED,
            (KnowledgeMode.LIVE_INTELLIGENCE,),
            (ModeTrigger.CREDIBLE_LIVE_REPORTING,),
            (ConfidenceLabel.MEDIUM,),
            (ModeNoticeCode.OFFICIAL_SEARCH_UNAVAILABLE,),
        ),
        (
            _request(
                official=OfficialEvidenceOutcome.NOT_REQUIRED,
                live=LiveEvidenceOutcome.HEALTHY_NO_MATCH,
            ),
            ModeSelectionState.EMPTY_BY_EVIDENCE,
            (),
            (),
            (),
            (ModeNoticeCode.NO_VERIFIED_LIVE_UPDATES,),
        ),
        (
            _request(
                live=LiveEvidenceOutcome.FOUND_UNVERIFIED,
            ),
            ModeSelectionState.READY,
            (
                KnowledgeMode.GROUNDED_REGULATORY,
                KnowledgeMode.LIVE_INTELLIGENCE,
            ),
            (
                ModeTrigger.SUFFICIENT_OFFICIAL_EVIDENCE,
                ModeTrigger.UNVERIFIED_LIVE_SOURCE,
            ),
            (ConfidenceLabel.HIGH, ConfidenceLabel.UNKNOWN),
            (),
        ),
    ],
)
def test_frozen_mode_matrix(
    mode_request: KnowledgeModeRequest,
    state: ModeSelectionState,
    modes: tuple[KnowledgeMode, ...],
    triggers: tuple[ModeTrigger, ...],
    ceilings: tuple[ConfidenceLabel, ...],
    notice_codes: tuple[ModeNoticeCode, ...],
) -> None:
    decision = select_knowledge_modes(mode_request)

    assert decision.state is state
    assert tuple(section.mode for section in decision.sections) == modes
    assert tuple(section.trigger for section in decision.sections) == triggers
    assert tuple(
        section.confidence_ceiling for section in decision.sections
    ) == ceilings
    assert tuple(notice.code for notice in decision.notices) == notice_codes


def test_healthy_no_match_uses_exact_no_documents_disclosure() -> None:
    decision = select_knowledge_modes(
        _request(official=OfficialEvidenceOutcome.HEALTHY_NO_MATCH)
    )

    assert decision.sections[0].required_disclosure == (
        NO_OFFICIAL_DOCUMENTS_DISCLOSURE
    )
    assert "temporarily unavailable" not in (
        decision.sections[0].required_disclosure or ""
    )


def test_retrieval_outage_never_claims_no_documents_exist() -> None:
    decision = select_knowledge_modes(
        _request(
            official=OfficialEvidenceOutcome.UNAVAILABLE,
            qualified_fallback=True,
        )
    )

    assert decision.sections[0].required_disclosure == (
        OFFICIAL_SEARCH_UNAVAILABLE_DISCLOSURE
    )
    assert NO_OFFICIAL_DOCUMENTS_DISCLOSURE not in (
        decision.sections[0].required_disclosure or ""
    )
    assert decision.notices[0].text == OFFICIAL_SEARCH_UNAVAILABLE_DISCLOSURE


def test_explicit_general_question_does_not_claim_an_official_search_ran() -> None:
    decision = select_knowledge_modes(
        _request(
            official=OfficialEvidenceOutcome.NOT_REQUIRED,
            explicit_general=True,
        )
    )

    section = decision.sections[0]
    assert section.mode is KnowledgeMode.GENERAL_AI
    assert section.required_disclosure is None
    assert section.reason_code == "MODE_2_EXPLICIT_GENERAL_QUESTION"


def test_pending_official_search_cannot_activate_general_ai_fallback() -> None:
    decision = select_knowledge_modes(
        _request(
            official=OfficialEvidenceOutcome.PENDING,
            general_background=True,
        )
    )

    assert decision.state is ModeSelectionState.WAITING
    assert decision.sections == ()
    assert decision.pending_lanes == (
        ProvenanceClass.INTERNAL_REGULATORY_CORPUS,
    )


def test_independent_live_section_can_be_ready_while_official_search_waits() -> None:
    decision = select_knowledge_modes(
        _request(
            official=OfficialEvidenceOutcome.PENDING,
            live=LiveEvidenceOutcome.FOUND_CREDIBLE_REPORTING,
            general_background=True,
        )
    )

    assert decision.state is ModeSelectionState.WAITING
    assert tuple(section.mode for section in decision.sections) == (
        KnowledgeMode.LIVE_INTELLIGENCE,
    )
    assert decision.pending_lanes == (
        ProvenanceClass.INTERNAL_REGULATORY_CORPUS,
    )


def test_selected_document_unavailable_requires_document_without_pretending() -> None:
    decision = select_knowledge_modes(
        _request(
            official=OfficialEvidenceOutcome.SELECTED_DOCUMENT_UNAVAILABLE,
        )
    )

    assert decision.state is ModeSelectionState.NEEDS_DOCUMENT
    assert decision.sections == ()
    assert decision.blocking_code == "SELECTED_DOCUMENT_UNAVAILABLE"


@pytest.mark.parametrize(
    ("scope", "expected"),
    [
        (ScopeResolutionState.RESOLVED, ConfidenceLabel.HIGH),
        (ScopeResolutionState.BOUNDED_ASSUMPTION, ConfidenceLabel.MEDIUM),
        (ScopeResolutionState.MATERIAL_UNRESOLVED, ConfidenceLabel.UNKNOWN),
        (ScopeResolutionState.LEGAL_STATUS_UNRESOLVED, ConfidenceLabel.UNKNOWN),
    ],
)
def test_scope_resolution_applies_a_hard_mode_ceiling(
    scope: ScopeResolutionState,
    expected: ConfidenceLabel,
) -> None:
    decision = select_knowledge_modes(_request(scope=scope))

    assert decision.sections[0].confidence_ceiling is expected


def test_mode_1_requires_official_lane_citations_and_verification() -> None:
    section = select_knowledge_modes(_request()).sections[0]

    assert section.provenance_lane is (
        ProvenanceClass.INTERNAL_REGULATORY_CORPUS
    )
    assert section.citation_cards is CitationCardPolicy.REQUIRED
    assert section.source_presentation is (
        SourcePresentationPolicy.OFFICIAL_CITATIONS
    )
    assert section.official_claim_verification_required is True
    assert section.legal_force_policy is (
        LegalForcePolicy.VERIFIED_OFFICIAL_STATUS_ONLY
    )
    assert section.prohibited_claims == (
        ProhibitedClaim.UNSUPPORTED_MATERIAL_FACT,
    )


def test_mode_2_has_no_source_identity_or_legal_authority() -> None:
    section = select_knowledge_modes(
        _request(official=OfficialEvidenceOutcome.HEALTHY_NO_MATCH)
    ).sections[0]

    assert section.provenance_lane is ProvenanceClass.GENERAL_AI_KNOWLEDGE
    assert section.citation_cards is CitationCardPolicy.PROHIBITED
    assert section.source_presentation is (
        SourcePresentationPolicy.NO_SOURCE_IDENTITY
    )
    assert section.official_claim_verification_required is False
    assert section.legal_force_policy is LegalForcePolicy.PROHIBITED
    assert set(section.prohibited_claims) == {
        ProhibitedClaim.OFFICIAL_INTERPRETATION,
        ProhibitedClaim.SPECIFIC_LEGAL_APPLICABILITY,
        ProhibitedClaim.BINDING_OBLIGATION,
        ProhibitedClaim.FABRICATED_CITATION_IDENTITY,
    }


@pytest.mark.parametrize(
    ("live", "ceiling"),
    [
        (LiveEvidenceOutcome.FOUND_OFFICIAL, ConfidenceLabel.HIGH),
        (
            LiveEvidenceOutcome.FOUND_CREDIBLE_REPORTING,
            ConfidenceLabel.MEDIUM,
        ),
        (LiveEvidenceOutcome.FOUND_UNVERIFIED, ConfidenceLabel.UNKNOWN),
    ],
)
def test_mode_3_requires_attribution_but_never_establishes_legal_force(
    live: LiveEvidenceOutcome,
    ceiling: ConfidenceLabel,
) -> None:
    section = select_knowledge_modes(_request(live=live)).sections[1]

    assert section.mode is KnowledgeMode.LIVE_INTELLIGENCE
    assert section.provenance_lane is ProvenanceClass.LIVE_WEB_SOURCES
    assert section.citation_cards is CitationCardPolicy.PROHIBITED
    assert section.source_presentation is (
        SourcePresentationPolicy.LIVE_SOURCE_ATTRIBUTION
    )
    assert section.confidence_ceiling is ceiling
    assert section.legal_force_policy is LegalForcePolicy.PROHIBITED
    assert ProhibitedClaim.LEGAL_FORCE_FROM_LIVE_REPORTING in (
        section.prohibited_claims
    )


def test_live_no_match_and_outage_use_different_frozen_notices() -> None:
    no_match = select_knowledge_modes(
        _request(live=LiveEvidenceOutcome.HEALTHY_NO_MATCH)
    )
    unavailable = select_knowledge_modes(
        _request(live=LiveEvidenceOutcome.UNAVAILABLE)
    )

    assert no_match.notices == (
        ModeNotice(
            code=ModeNoticeCode.NO_VERIFIED_LIVE_UPDATES,
            text=NO_VERIFIED_LIVE_UPDATES_NOTICE,
        ),
    )
    assert unavailable.notices == (
        ModeNotice(
            code=ModeNoticeCode.LIVE_REFRESH_UNAVAILABLE,
            text=LIVE_REFRESH_UNAVAILABLE_NOTICE,
        ),
    )
    assert no_match.state is ModeSelectionState.READY
    assert unavailable.state is ModeSelectionState.DEGRADED


@pytest.mark.parametrize(
    "mutation",
    [
        {"provenance_lane": ProvenanceClass.LIVE_WEB_SOURCES},
        {"citation_cards": CitationCardPolicy.PROHIBITED},
        {"official_claim_verification_required": False},
        {"legal_force_policy": LegalForcePolicy.PROHIBITED},
        {"confidence_ceiling": ConfidenceLabel.HIGH},
    ],
)
def test_section_contract_rejects_mode_1_policy_drift(
    mutation: dict[str, Any],
) -> None:
    section = select_knowledge_modes(
        _request(official=OfficialEvidenceOutcome.PARTIAL)
    ).sections[0]
    values = section.model_dump()
    values.update(mutation)

    with pytest.raises(ValidationError):
        KnowledgeModeSectionPolicy(**values)


@pytest.mark.parametrize(
    "mutation",
    [
        {"required_disclosure": None},
        {"citation_cards": CitationCardPolicy.REQUIRED},
        {"source_presentation": SourcePresentationPolicy.OFFICIAL_CITATIONS},
        {
            "legal_force_policy": (
                LegalForcePolicy.VERIFIED_OFFICIAL_STATUS_ONLY
            )
        },
        {"confidence_ceiling": ConfidenceLabel.HIGH},
        {"prohibited_claims": ()},
    ],
)
def test_section_contract_rejects_mode_2_policy_drift(
    mutation: dict[str, Any],
) -> None:
    section = select_knowledge_modes(
        _request(official=OfficialEvidenceOutcome.HEALTHY_NO_MATCH)
    ).sections[0]
    values = section.model_dump()
    values.update(mutation)

    with pytest.raises(ValidationError):
        KnowledgeModeSectionPolicy(**values)


@pytest.mark.parametrize(
    "mutation",
    [
        {"provenance_lane": ProvenanceClass.INTERNAL_REGULATORY_CORPUS},
        {"citation_cards": CitationCardPolicy.REQUIRED},
        {"source_presentation": SourcePresentationPolicy.OFFICIAL_CITATIONS},
        {
            "legal_force_policy": (
                LegalForcePolicy.VERIFIED_OFFICIAL_STATUS_ONLY
            )
        },
        {"confidence_ceiling": ConfidenceLabel.HIGH},
    ],
)
def test_section_contract_rejects_reporting_mode_3_policy_drift(
    mutation: dict[str, Any],
) -> None:
    section = select_knowledge_modes(
        _request(live=LiveEvidenceOutcome.FOUND_CREDIBLE_REPORTING)
    ).sections[1]
    values = section.model_dump()
    values.update(mutation)

    with pytest.raises(ValidationError):
        KnowledgeModeSectionPolicy(**values)


@pytest.mark.parametrize(
    "kwargs",
    [
        {
            "official": OfficialEvidenceOutcome.SUFFICIENT,
            "explicit_general": True,
        },
        {
            "official": OfficialEvidenceOutcome.HEALTHY_NO_MATCH,
            "qualified_fallback": True,
        },
        {
            "official": OfficialEvidenceOutcome.SELECTED_DOCUMENT_UNAVAILABLE,
            "live": LiveEvidenceOutcome.FOUND_OFFICIAL,
        },
        {
            "official": OfficialEvidenceOutcome.NOT_REQUIRED,
        },
    ],
)
def test_invalid_mode_requests_fail_closed(kwargs: dict[str, Any]) -> None:
    with pytest.raises(ValidationError):
        _request(**kwargs)


def test_mode_notice_rejects_noncanonical_copy() -> None:
    with pytest.raises(ValidationError):
        ModeNotice(
            code=ModeNoticeCode.NO_VERIFIED_LIVE_UPDATES,
            text="No news.",
        )


def test_decision_allows_multiple_sections_in_one_mode_for_multi_part_work() -> None:
    section = select_knowledge_modes(_request()).sections[0]
    duplicate = section.model_copy(update={"section_key": "other-official"})

    decision = KnowledgeModeDecision(
        state=ModeSelectionState.READY,
        sections=(section, duplicate),
    )

    assert tuple(item.mode for item in decision.sections) == (
        KnowledgeMode.GROUNDED_REGULATORY,
        KnowledgeMode.GROUNDED_REGULATORY,
    )


def test_decision_rejects_duplicate_section_keys() -> None:
    section = select_knowledge_modes(_request()).sections[0]

    with pytest.raises(ValidationError):
        KnowledgeModeDecision(
            state=ModeSelectionState.READY,
            sections=(section, section),
        )


def test_live_pending_does_not_force_unrequested_general_background() -> None:
    decision = select_knowledge_modes(
        _request(
            official=OfficialEvidenceOutcome.HEALTHY_NO_MATCH,
            live=LiveEvidenceOutcome.PENDING,
        )
    )

    assert decision.state is ModeSelectionState.WAITING
    assert decision.sections == ()
    assert decision.pending_lanes == (ProvenanceClass.LIVE_WEB_SOURCES,)


def test_nonwaiting_decision_cannot_claim_pending_lanes() -> None:
    section = select_knowledge_modes(_request()).sections[0]

    with pytest.raises(ValidationError):
        KnowledgeModeDecision(
            state=ModeSelectionState.READY,
            sections=(section,),
            pending_lanes=(ProvenanceClass.LIVE_WEB_SOURCES,),
        )


def test_empty_and_degraded_state_contracts_fail_closed() -> None:
    section = select_knowledge_modes(_request()).sections[0]

    with pytest.raises(ValidationError):
        KnowledgeModeDecision(
            state=ModeSelectionState.EMPTY_BY_EVIDENCE,
            sections=(section,),
        )
    with pytest.raises(ValidationError):
        KnowledgeModeDecision(
            state=ModeSelectionState.DEGRADED,
            sections=(),
        )


def test_contracts_are_strict_frozen_and_extra_forbidden() -> None:
    request = _request()

    with pytest.raises(ValidationError):
        KnowledgeModeRequest(
            **request.model_dump(),
            unexpected=True,
        )
    with pytest.raises(ValidationError):
        KnowledgeModeRequest(
            official_outcome=OfficialEvidenceOutcome.SUFFICIENT,
            explicit_general_question=1,  # type: ignore[arg-type]
        )
    with pytest.raises(ValidationError):
        request.scope_state = ScopeResolutionState.MATERIAL_UNRESOLVED  # type: ignore[misc]


def test_decision_serialization_is_deterministic_and_versioned() -> None:
    request = _request(
        official=OfficialEvidenceOutcome.HEALTHY_NO_MATCH,
        live=LiveEvidenceOutcome.HEALTHY_NO_MATCH,
    )
    first = select_knowledge_modes(request)
    second = select_knowledge_modes(request)

    assert first == second
    assert first.policy_version == KNOWLEDGE_MODE_POLICY_VERSION
    assert knowledge_mode_decision_json(first) == knowledge_mode_decision_json(
        second
    )
    payload = json.loads(knowledge_mode_decision_json(first))
    assert payload["schema_version"] == "1"
    assert payload["sections"][0]["required_disclosure"] == (
        NO_OFFICIAL_DOCUMENTS_DISCLOSURE
    )
