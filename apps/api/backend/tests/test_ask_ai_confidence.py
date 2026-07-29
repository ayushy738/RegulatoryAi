from __future__ import annotations

import json

import pytest
from pydantic import ValidationError

from backend.ask.confidence import (
    CONFIDENCE_POLICY_VERSION,
    DIMENSION_WEIGHTS,
    PENALTY_POINTS,
    ClaimConfidenceInput,
    ConfidenceCalculationRequest,
    ConfidenceCalculationResult,
    ConfidenceDimensions,
    ConfidencePenalty,
    HardUnknownCondition,
    HighGateFailure,
    SectionConfidenceInput,
    StrictConfidenceReason,
    calculate_confidence,
)
from backend.ask.decision.models import ConfidenceLabel, KnowledgeMode
from backend.ask.knowledge_modes import (
    CitationCardPolicy,
    KnowledgeModeSectionPolicy,
    LegalForcePolicy,
    ModeTrigger,
    ProhibitedClaim,
    SourcePresentationPolicy,
)
from backend.ask.orchestration.contracts import ProvenanceClass


def _policy(
    section_key: str = "section-1",
    *,
    mode: KnowledgeMode = KnowledgeMode.GROUNDED_REGULATORY,
    ceiling: ConfidenceLabel = ConfidenceLabel.HIGH,
) -> KnowledgeModeSectionPolicy:
    if mode is KnowledgeMode.GROUNDED_REGULATORY:
        return KnowledgeModeSectionPolicy(
            section_key=section_key,
            mode=mode,
            trigger=ModeTrigger.SUFFICIENT_OFFICIAL_EVIDENCE,
            provenance_lane=ProvenanceClass.INTERNAL_REGULATORY_CORPUS,
            confidence_ceiling=ceiling,
            citation_cards=CitationCardPolicy.REQUIRED,
            source_presentation=SourcePresentationPolicy.OFFICIAL_CITATIONS,
            official_claim_verification_required=True,
            legal_force_policy=LegalForcePolicy.VERIFIED_OFFICIAL_STATUS_ONLY,
            prohibited_claims=(
                ProhibitedClaim.UNSUPPORTED_MATERIAL_FACT,
            ),
            reason_code="TEST_MODE_1",
        )
    if mode is KnowledgeMode.GENERAL_AI:
        return KnowledgeModeSectionPolicy(
            section_key=section_key,
            mode=mode,
            trigger=ModeTrigger.EXPLICIT_GENERAL_QUESTION,
            provenance_lane=ProvenanceClass.GENERAL_AI_KNOWLEDGE,
            confidence_ceiling=ceiling,
            citation_cards=CitationCardPolicy.PROHIBITED,
            source_presentation=SourcePresentationPolicy.NO_SOURCE_IDENTITY,
            official_claim_verification_required=False,
            legal_force_policy=LegalForcePolicy.PROHIBITED,
            prohibited_claims=(
                ProhibitedClaim.OFFICIAL_INTERPRETATION,
                ProhibitedClaim.SPECIFIC_LEGAL_APPLICABILITY,
                ProhibitedClaim.BINDING_OBLIGATION,
                ProhibitedClaim.FABRICATED_CITATION_IDENTITY,
            ),
            reason_code="TEST_MODE_2",
        )
    return KnowledgeModeSectionPolicy(
        section_key=section_key,
        mode=mode,
        trigger=(
            ModeTrigger.OFFICIAL_LIVE_SOURCE
            if ceiling is ConfidenceLabel.HIGH
            else (
                ModeTrigger.CREDIBLE_LIVE_REPORTING
                if ceiling in {ConfidenceLabel.MEDIUM, ConfidenceLabel.LOW}
                else ModeTrigger.UNVERIFIED_LIVE_SOURCE
            )
        ),
        provenance_lane=ProvenanceClass.LIVE_WEB_SOURCES,
        confidence_ceiling=ceiling,
        citation_cards=CitationCardPolicy.PROHIBITED,
        source_presentation=SourcePresentationPolicy.LIVE_SOURCE_ATTRIBUTION,
        official_claim_verification_required=False,
        legal_force_policy=LegalForcePolicy.PROHIBITED,
        prohibited_claims=(
            ProhibitedClaim.LEGAL_FORCE_FROM_LIVE_REPORTING,
            ProhibitedClaim.FABRICATED_CITATION_IDENTITY,
        ),
        reason_code="TEST_MODE_3",
    )


def _dimensions(
    value: float = 100,
    **updates: float,
) -> ConfidenceDimensions:
    values = {
        "evidence_authority": value,
        "retrieval_relevance": value,
        "claim_coverage": value,
        "source_agreement": value,
        "freshness_status_validity": value,
        "scope_resolution": value,
    }
    values.update(updates)
    return ConfidenceDimensions(**values)


def _claim(
    claim_id: str = "claim-1",
    *,
    section_key: str = "section-1",
    dimensions: ConfidenceDimensions | None = None,
    mode: KnowledgeMode = KnowledgeMode.GROUNDED_REGULATORY,
    ceiling: ConfidenceLabel = ConfidenceLabel.HIGH,
    penalties: tuple[ConfidencePenalty, ...] = (),
    hard_unknowns: tuple[HardUnknownCondition, ...] = (),
    authoritative: bool = True,
    freshness_fit: bool = True,
    critical_ceiling: ConfidenceLabel = ConfidenceLabel.HIGH,
) -> ClaimConfidenceInput:
    return ClaimConfidenceInput(
        claim_id=claim_id,
        section_policy=_policy(
            section_key,
            mode=mode,
            ceiling=ceiling,
        ),
        dimensions=dimensions or _dimensions(),
        penalties=penalties,
        hard_unknowns=hard_unknowns,
        authoritative_evidence=authoritative,
        freshness_meets_query=freshness_fit,
        critical_input_ceiling=critical_ceiling,
    )


def _section(
    section_key: str = "section-1",
    claim_ids: tuple[str, ...] = ("claim-1",),
    *,
    importance: float = 1,
    critical: bool = True,
) -> SectionConfidenceInput:
    return SectionConfidenceInput(
        section_key=section_key,
        claim_ids=claim_ids,
        importance_weight=importance,
        critical=critical,
    )


def _request(
    *claims: ClaimConfidenceInput,
    sections: tuple[SectionConfidenceInput, ...] | None = None,
    strict: tuple[StrictConfidenceReason, ...] = (),
) -> ConfidenceCalculationRequest:
    actual_claims = claims or (_claim(),)
    return ConfidenceCalculationRequest(
        claims=actual_claims,
        sections=sections or (_section(),),
        strict_reasons=strict,
    )


def _claim_result(
    claim: ClaimConfidenceInput,
) -> ConfidenceCalculationResult:
    return calculate_confidence(
        _request(
            claim,
            sections=(
                _section(
                    claim.section_policy.section_key,
                    (claim.claim_id,),
                ),
            ),
        )
    )


def test_frozen_dimension_weights_sum_to_one_and_apply_exactly() -> None:
    assert {key: float(value) for key, value in DIMENSION_WEIGHTS.items()} == {
        "evidence_authority": 0.25,
        "retrieval_relevance": 0.15,
        "claim_coverage": 0.20,
        "source_agreement": 0.15,
        "freshness_status_validity": 0.15,
        "scope_resolution": 0.10,
    }
    assert sum(DIMENSION_WEIGHTS.values()) == 1

    expected = {
        "evidence_authority": 25,
        "retrieval_relevance": 15,
        "claim_coverage": 20,
        "source_agreement": 15,
        "freshness_status_validity": 15,
        "scope_resolution": 10,
    }
    for field, score in expected.items():
        dimensions = _dimensions(0, **{field: 100})
        result = _claim_result(
            _claim(dimensions=dimensions, authoritative=False)
        )
        assert result.claims[0].base_score == score


@pytest.mark.parametrize(
    ("penalty", "points"),
    [
        (ConfidencePenalty.UNRESOLVED_MATERIAL_CONTRADICTION, 25),
        (ConfidencePenalty.STALE_FOR_CURRENT_QUERY, 20),
        (ConfidencePenalty.REQUIRED_EVIDENCE_CAPABILITY_UNAVAILABLE, 15),
        (ConfidencePenalty.INFERRED_LEGAL_APPLICABILITY, 10),
        (ConfidencePenalty.SINGLE_SOURCE_HIGH_IMPACT_CLAIM, 10),
        (ConfidencePenalty.INFERRED_MATERIAL_DATE_TYPE, 5),
    ],
)
def test_each_frozen_penalty_is_additive(
    penalty: ConfidencePenalty,
    points: int,
) -> None:
    result = _claim_result(_claim(penalties=(penalty,)))

    assert PENALTY_POINTS[penalty] == points
    assert result.claims[0].penalty_points == points
    assert result.claims[0].final_score == 100 - points


def test_all_penalties_apply_and_score_is_bounded_at_zero() -> None:
    penalties = tuple(ConfidencePenalty)
    result = _claim_result(
        _claim(dimensions=_dimensions(40), penalties=penalties)
    )

    assert result.claims[0].penalty_points == 85
    assert result.claims[0].final_score == 0
    assert result.claims[0].numeric_label is ConfidenceLabel.UNKNOWN


@pytest.mark.parametrize(
    ("score", "label"),
    [
        (0, ConfidenceLabel.UNKNOWN),
        (34.999, ConfidenceLabel.UNKNOWN),
        (35, ConfidenceLabel.LOW),
        (59.999, ConfidenceLabel.LOW),
        (60, ConfidenceLabel.MEDIUM),
        (79.999, ConfidenceLabel.MEDIUM),
        (80, ConfidenceLabel.HIGH),
        (100, ConfidenceLabel.HIGH),
    ],
)
def test_exact_numeric_label_boundaries(
    score: float,
    label: ConfidenceLabel,
) -> None:
    result = _claim_result(
        _claim(dimensions=_dimensions(score), authoritative=True)
    )

    assert result.claims[0].final_score == score
    assert result.claims[0].numeric_label is label


def test_complete_high_gates_produce_high_confidence() -> None:
    result = _claim_result(_claim())

    assert result.claims[0].final_label is ConfidenceLabel.HIGH
    assert result.claims[0].high_gate_failures == ()


@pytest.mark.parametrize(
    ("claim", "failure"),
    [
        (
            _claim(authoritative=False),
            HighGateFailure.AUTHORITATIVE_EVIDENCE_REQUIRED,
        ),
        (
            _claim(dimensions=_dimensions(claim_coverage=84.99)),
            HighGateFailure.COVERAGE_BELOW_85,
        ),
        (
            _claim(dimensions=_dimensions(scope_resolution=84.99)),
            HighGateFailure.SCOPE_RESOLUTION_BELOW_85,
        ),
        (
            _claim(
                penalties=(
                    ConfidencePenalty.UNRESOLVED_MATERIAL_CONTRADICTION,
                )
            ),
            HighGateFailure.UNRESOLVED_CONTRADICTION,
        ),
        (
            _claim(freshness_fit=False),
            HighGateFailure.FRESHNESS_NOT_FIT,
        ),
        (
            _claim(
                penalties=(ConfidencePenalty.STALE_FOR_CURRENT_QUERY,),
                freshness_fit=True,
            ),
            HighGateFailure.FRESHNESS_NOT_FIT,
        ),
    ],
)
def test_mandatory_high_gates_are_recorded_and_prevent_high(
    claim: ClaimConfidenceInput,
    failure: HighGateFailure,
) -> None:
    result = _claim_result(claim)

    assert failure in result.claims[0].high_gate_failures
    assert result.claims[0].final_label is not ConfidenceLabel.HIGH


@pytest.mark.parametrize("condition", list(HardUnknownCondition))
def test_every_hard_unknown_overrides_a_perfect_numeric_score(
    condition: HardUnknownCondition,
) -> None:
    result = _claim_result(_claim(hard_unknowns=(condition,)))

    assert result.claims[0].final_score == 100
    assert result.claims[0].numeric_label is ConfidenceLabel.HIGH
    assert result.claims[0].final_label is ConfidenceLabel.UNKNOWN


@pytest.mark.parametrize(
    ("mode", "ceiling"),
    [
        (KnowledgeMode.GROUNDED_REGULATORY, ConfidenceLabel.HIGH),
        (KnowledgeMode.GROUNDED_REGULATORY, ConfidenceLabel.MEDIUM),
        (KnowledgeMode.GENERAL_AI, ConfidenceLabel.MEDIUM),
        (KnowledgeMode.GENERAL_AI, ConfidenceLabel.LOW),
        (KnowledgeMode.LIVE_INTELLIGENCE, ConfidenceLabel.HIGH),
        (KnowledgeMode.LIVE_INTELLIGENCE, ConfidenceLabel.MEDIUM),
        (KnowledgeMode.LIVE_INTELLIGENCE, ConfidenceLabel.UNKNOWN),
    ],
)
def test_mode_and_evidence_ceiling_caps_label_not_numeric_score(
    mode: KnowledgeMode,
    ceiling: ConfidenceLabel,
) -> None:
    result = _claim_result(_claim(mode=mode, ceiling=ceiling))

    assert result.claims[0].final_score == 100
    assert result.claims[0].applied_ceiling is ceiling
    assert result.claims[0].final_label is ceiling


def test_weakest_critical_input_ceiling_cannot_be_upgraded() -> None:
    result = _claim_result(
        _claim(critical_ceiling=ConfidenceLabel.LOW)
    )

    assert result.claims[0].applied_ceiling is ConfidenceLabel.LOW
    assert result.claims[0].final_label is ConfidenceLabel.LOW


def test_section_uses_70_percent_coverage_mean_and_30_percent_lowest_claim() -> None:
    high = _claim(
        dimensions=_dimensions(100, claim_coverage=100),
    )
    medium = _claim(
        "claim-2",
        dimensions=_dimensions(
            60,
            evidence_authority=68,
            claim_coverage=50,
        ),
    )
    result = calculate_confidence(
        _request(
            high,
            medium,
            sections=(_section(claim_ids=("claim-1", "claim-2")),),
        )
    )

    section = result.sections[0]
    assert section.coverage_weighted_mean == pytest.approx(86.6666666667)
    assert section.lowest_claim_score == 60
    assert section.score == pytest.approx(78.6666666667)
    assert section.label is ConfidenceLabel.MEDIUM


def test_zero_total_claim_coverage_makes_section_unknown() -> None:
    first = _claim(dimensions=_dimensions(80, claim_coverage=0))
    second = _claim(
        "claim-2",
        dimensions=_dimensions(80, claim_coverage=0),
    )
    result = calculate_confidence(
        _request(
            first,
            second,
            sections=(_section(claim_ids=("claim-1", "claim-2")),),
        )
    )

    assert result.sections[0].coverage_weighted_mean == 0
    assert result.sections[0].score == pytest.approx(19.2)
    assert result.sections[0].label is ConfidenceLabel.UNKNOWN


def test_section_label_cannot_exceed_weakest_material_claim() -> None:
    high = _claim()
    capped = _claim(
        "claim-2",
        dimensions=_dimensions(79),
    )
    result = calculate_confidence(
        _request(
            high,
            capped,
            sections=(_section(claim_ids=("claim-1", "claim-2")),),
        )
    )

    assert result.sections[0].score > 80
    assert result.sections[0].label is ConfidenceLabel.MEDIUM


def test_overall_uses_importance_mean_and_lowest_critical_section() -> None:
    high = _claim(section_key="section-high")
    medium = _claim(
        "claim-2",
        section_key="section-medium",
        dimensions=_dimensions(60),
    )
    sections = (
        _section("section-high", ("claim-1",), importance=3),
        _section("section-medium", ("claim-2",), importance=1),
    )
    result = calculate_confidence(_request(high, medium, sections=sections))

    assert result.overall.importance_weighted_mean == 90
    assert result.overall.lowest_critical_section_score == 60
    assert result.overall.score == 81
    assert result.overall.label is ConfidenceLabel.MEDIUM


def test_strict_intent_caps_overall_at_lowest_material_claim() -> None:
    critical = _claim(section_key="core")
    background = _claim(
        "claim-2",
        section_key="background",
        dimensions=_dimensions(60),
    )
    sections = (
        _section("core", ("claim-1",), importance=100),
        _section(
            "background",
            ("claim-2",),
            importance=1,
            critical=False,
        ),
    )
    ordinary = calculate_confidence(
        _request(critical, background, sections=sections)
    )
    strict = calculate_confidence(
        _request(
            critical,
            background,
            sections=sections,
            strict=(StrictConfidenceReason.COMPLIANCE,),
        )
    )

    assert ordinary.overall.label is ConfidenceLabel.HIGH
    assert strict.overall.label is ConfidenceLabel.MEDIUM


def test_multi_mode_sections_keep_separate_visible_labels() -> None:
    official = _claim(section_key="official")
    general = _claim(
        "claim-2",
        section_key="general",
        mode=KnowledgeMode.GENERAL_AI,
        ceiling=ConfidenceLabel.MEDIUM,
    )
    live = _claim(
        "claim-3",
        section_key="live",
        mode=KnowledgeMode.LIVE_INTELLIGENCE,
        ceiling=ConfidenceLabel.MEDIUM,
    )
    sections = (
        _section("official", ("claim-1",)),
        _section("general", ("claim-2",), critical=False),
        _section("live", ("claim-3",), critical=False),
    )
    result = calculate_confidence(
        _request(official, general, live, sections=sections)
    )

    assert tuple((item.mode, item.label) for item in result.sections) == (
        (KnowledgeMode.GROUNDED_REGULATORY, ConfidenceLabel.HIGH),
        (KnowledgeMode.GENERAL_AI, ConfidenceLabel.MEDIUM),
        (KnowledgeMode.LIVE_INTELLIGENCE, ConfidenceLabel.MEDIUM),
    )


def test_request_rejects_duplicate_unassigned_cross_section_and_no_critical_graphs() -> None:
    first = _claim()
    duplicate = _claim()
    with pytest.raises(ValidationError):
        _request(first, duplicate)
    with pytest.raises(ValidationError):
        _request(
            first,
            sections=(_section(claim_ids=("unknown",)),),
        )
    with pytest.raises(ValidationError):
        _request(
            first,
            sections=(
                _section("other-section", ("claim-1",)),
            ),
        )
    with pytest.raises(ValidationError):
        _request(
            first,
            sections=(_section(critical=False),),
        )


def test_request_rejects_duplicate_conditions_nonfinite_values_and_extra_fields() -> None:
    with pytest.raises(ValidationError):
        _claim(
            penalties=(
                ConfidencePenalty.INFERRED_MATERIAL_DATE_TYPE,
                ConfidencePenalty.INFERRED_MATERIAL_DATE_TYPE,
            )
        )
    with pytest.raises(ValidationError):
        _dimensions(float("nan"))
    with pytest.raises(ValidationError):
        ConfidenceCalculationRequest.model_validate(
            {**_request().model_dump(mode="python"), "unexpected": True}
        )


def test_nested_model_copy_bypass_is_revalidated_at_calculation_boundary() -> None:
    claim = _claim()
    invalid_dimensions = claim.dimensions.model_copy(
        update={"evidence_authority": float("nan")}
    )
    bypassed_claim = claim.model_copy(
        update={"dimensions": invalid_dimensions}
    )
    bypassed = _request().model_copy(update={"claims": (bypassed_claim,)})

    with pytest.raises(ValidationError):
        calculate_confidence(bypassed)


def test_calculation_is_deterministic_serializable_and_input_immutable() -> None:
    request = _request()
    before = request.model_dump(mode="json")

    first = calculate_confidence(request)
    second = calculate_confidence(request)

    assert first == second
    assert request.model_dump(mode="json") == before
    assert first.policy_version == CONFIDENCE_POLICY_VERSION
    assert json.loads(first.model_dump_json()) == first.model_dump(mode="json")
    with pytest.raises(ValidationError):
        ConfidenceCalculationResult.model_validate(
            {**first.model_dump(mode="python"), "unexpected": True}
        )
