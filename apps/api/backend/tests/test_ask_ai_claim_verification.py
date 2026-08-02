from __future__ import annotations

import asyncio
import json
from datetime import UTC, date, datetime
from typing import Any

import pytest
from pydantic import ValidationError

from backend.ask.claim_verification import (
    APPROVED_VERIFICATION_BUDGET_MS,
    CLAIM_VERIFIER_POLICY_VERSION,
    PUBLICATION_CONFIDENCE_THRESHOLDS,
    VERIFIER_ACCEPTANCE_THRESHOLDS,
    ClaimPublicationMode,
    ClaimRisk,
    ClaimSupportOutcome,
    ClaimVerificationRequest,
    ClaimVerificationState,
    ClaimVerifierIdentity,
    GroundedProseReleaseApproval,
    claim_verification_result_json,
    execute_claim_verification,
)
from backend.ask.evidence_admission import (
    EvidenceAdmissionRequest,
    OfficialEvidenceAdmissionResult,
    OfficialEvidenceCandidate,
    admit_official_evidence,
    official_source_id,
)
from backend.ask.orchestration.contracts import (
    ArtifactEnvelope,
    ArtifactProducer,
    CandidateClaimPayload,
    CapabilityScope,
    CapabilityTerminalState,
    ConfidenceSignals,
    ContentDerivation,
    EvidenceUnitPayload,
    KnowledgeMode,
    OrchestratorCapability,
    ProvenanceClass,
    ProvenanceLineage,
    SourceIdentity,
    TimeDimension,
    TransformationStep,
    VerificationStatus,
)
from backend.rag.quality import (
    CanonicalEvidenceUnit,
    EvidenceScoreSnapshot,
    RetrievalMatchReason,
)

NOW = datetime(2026, 7, 31, 10, 0, tzinfo=UTC)
EVIDENCE_ID = "evidence_aaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaa"
CLAIM_TEXT = "The filing is required by 31 July 2026."
EVIDENCE_TEXT = "The filing is required by 31 July 2026."


class _Provider:
    provider_name = "fixture-verifier"
    verifier_version = "verifier-1"
    model_version = "model-1"
    prompt_version = "prompt-1"

    def __init__(
        self,
        outputs: list[object],
        *,
        error: Exception | None = None,
        delay: float = 0,
    ) -> None:
        self.outputs = outputs
        self.error = error
        self.delay = delay
        self.calls: list[dict[str, Any]] = []

    async def verify(self, *, payload: str) -> str:
        self.calls.append(json.loads(payload))
        if self.delay:
            await asyncio.sleep(self.delay)
        if self.error is not None:
            raise self.error
        return self.outputs[len(self.calls) - 1]  # type: ignore[return-value]


def _scope() -> CapabilityScope:
    return CapabilityScope(
        atomic_question_ids=("question-1",),
        section_keys=("official",),
        entity_ids=("entity-1",),
        jurisdiction="India",
        time_scope="current",
        date_semantics=(TimeDimension.EFFECTIVE,),
        constraints=("official sources only",),
    )


def _admission() -> OfficialEvidenceAdmissionResult:
    canonical = CanonicalEvidenceUnit(
        evidence_unit_id=EVIDENCE_ID,
        policy_version="ask-ai-retrieval-quality-v1",
        document_id=101,
        chunk_id=301,
        title="Official filing regulation",
        source_url="https://official.example/regulation/101",
        issuer="Regulator",
        issue_date=date(2026, 7, 1),
        text=EVIDENCE_TEXT,
        retrieval_sources=("vector",),
        match_reasons=(RetrievalMatchReason.VECTOR_SIMILARITY,),
        question_ids=("question-1",),
        scores=EvidenceScoreSnapshot(
            vector=0.95,
            keyword=0,
            graph=0,
            admitted_relevance=0.95,
        ),
    )
    artifact = ArtifactEnvelope(
        artifact_id=EVIDENCE_ID,
        producer=ArtifactProducer.REGULATORY_RETRIEVER,
        scope=_scope(),
        payload=EvidenceUnitPayload(
            excerpt=EVIDENCE_TEXT,
            locator="chunk 301",
            match_reasons=("vector_similarity",),
        ),
        provenance=ProvenanceLineage(
            provenance_class=ProvenanceClass.INTERNAL_REGULATORY_CORPUS,
            knowledge_mode=KnowledgeMode.GROUNDED_REGULATORY,
            sources=(
                SourceIdentity(
                    source_id=official_source_id(canonical),
                    provenance_class=(
                        ProvenanceClass.INTERNAL_REGULATORY_CORPUS
                    ),
                    title=canonical.title,
                    uri=canonical.source_url,
                    issuer_or_publisher=canonical.issuer,
                    issue_at=datetime(2026, 7, 1, tzinfo=UTC),
                ),
            ),
            derivation=ContentDerivation.DIRECT,
            verification_status=VerificationStatus.PENDING,
        ),
        confidence_signals=ConfidenceSignals(retrieval_relevance=0.95),
        ancestry=("plan-1",),
        capability_status=CapabilityTerminalState.SATISFIED,
    )
    result = admit_official_evidence(
        EvidenceAdmissionRequest(
            approved_scope=_scope(),
            evaluated_at=NOW,
            candidates=(
                OfficialEvidenceCandidate(
                    artifact=artifact,
                    canonical_evidence=canonical,
                ),
            ),
        )
    )
    assert len(result.admitted) == 1
    return result


def _claim(text: str = CLAIM_TEXT) -> ArtifactEnvelope:
    source = SourceIdentity(
        source_id="document-101",
        provenance_class=ProvenanceClass.INTERNAL_REGULATORY_CORPUS,
        title="Official filing regulation",
        uri="https://official.example/regulation/101",
        issuer_or_publisher="Regulator",
        issue_at=datetime(2026, 7, 1, tzinfo=UTC),
    )
    return ArtifactEnvelope(
        artifact_id="claim-1",
        producer=ArtifactProducer.RESPONSE_COMPOSER,
        scope=_scope(),
        payload=CandidateClaimPayload(
            claim_text=text,
            material=True,
            supporting_artifact_ids=(EVIDENCE_ID,),
        ),
        provenance=ProvenanceLineage(
            provenance_class=ProvenanceClass.INTERNAL_REGULATORY_CORPUS,
            knowledge_mode=KnowledgeMode.GROUNDED_REGULATORY,
            sources=(source,),
            derivation=ContentDerivation.SUMMARIZED,
            transformations=(
                TransformationStep(
                    capability=OrchestratorCapability.RESPONSE_COMPOSER,
                    derivation=ContentDerivation.SUMMARIZED,
                    input_artifact_ids=(EVIDENCE_ID,),
                    input_provenance=(
                        ProvenanceClass.INTERNAL_REGULATORY_CORPUS,
                    ),
                    output_provenance=(
                        ProvenanceClass.INTERNAL_REGULATORY_CORPUS
                    ),
                ),
            ),
            verification_status=VerificationStatus.PENDING,
        ),
        ancestry=(EVIDENCE_ID, "plan-1"),
        capability_status=CapabilityTerminalState.SATISFIED,
    )


def _approval(**overrides: Any) -> GroundedProseReleaseApproval:
    values = {
        "approval_id": "verifier-release-1",
        "status": "approved",
        "evaluation_status": "pass",
        "dataset_checksum": "a" * 64,
        "provider": "fixture-verifier",
        "verifier_version": "verifier-1",
        "model_version": "model-1",
        "prompt_version": "prompt-1",
        "approved_at": NOW,
    }
    values.update(overrides)
    return GroundedProseReleaseApproval(**values)


def _request(
    *,
    risk: ClaimRisk = ClaimRisk.MATERIAL,
    approval: GroundedProseReleaseApproval | None = None,
    timeout_ms: int = 2_200,
    admission: OfficialEvidenceAdmissionResult | None = None,
    claim: ArtifactEnvelope | None = None,
) -> ClaimVerificationRequest:
    return ClaimVerificationRequest(
        approved_scope=_scope(),
        evidence_admissions=(admission or _admission(),),
        claim=claim or _claim(),
        risk=risk,
        timeout_ms=timeout_ms,
        release_approval=approval,
    )


def _claim_span(text: str) -> dict[str, Any]:
    return {"start": 0, "end": len(text), "text": text}


def _evidence_span(text: str = EVIDENCE_TEXT) -> dict[str, Any]:
    return {
        "evidence_id": EVIDENCE_ID,
        "start": 0,
        "end": len(text),
        "text": text,
    }


def _output(
    *,
    text: str = CLAIM_TEXT,
    outcome: str = "supported",
    confidence: float = 0.96,
    correction: dict[str, Any] | None = None,
    unsupported_spans: list[dict[str, Any]] | None = None,
    support_spans: list[dict[str, Any]] | None = None,
    contradiction_spans: list[dict[str, Any]] | None = None,
    claim_span: dict[str, Any] | None = None,
) -> str:
    if support_spans is None:
        support_spans = (
            [_evidence_span()] if outcome in {"supported", "partial_support"} else []
        )
    if unsupported_spans is None:
        unsupported_spans = (
            [{"start": 26, "end": 38, "text": "31 July 2026"}]
            if outcome == "partial_support"
            else []
        )
    if contradiction_spans is None:
        contradiction_spans = (
            [_evidence_span()] if outcome == "contradiction" else []
        )
    return json.dumps(
        {
            "schema_version": "1",
            "claim_id": "claim-1",
            "propositions": [
                {
                    "proposition_id": "prop-1",
                    "claim_span": claim_span or _claim_span(text),
                    "outcome": outcome,
                    "confidence": confidence,
                    "evidence_ids": [EVIDENCE_ID],
                    "support_spans": support_spans,
                    "unsupported_spans": unsupported_spans,
                    "contradiction_spans": contradiction_spans,
                }
            ],
            "correction": correction,
        }
    )


def _execute(
    request: ClaimVerificationRequest,
    provider: _Provider,
):
    return asyncio.run(
        execute_claim_verification(
            request,
            provider_factory=lambda: provider,
            monotonic=lambda: 0.0,
        )
    )


def test_supported_claim_defaults_to_evidence_only_without_release() -> None:
    provider = _Provider([_output()])

    result = _execute(_request(), provider)

    assert result.state is ClaimVerificationState.SATISFIED
    assert result.outcome is ClaimSupportOutcome.SUPPORTED
    assert result.publication_mode is ClaimPublicationMode.EVIDENCE_ONLY
    assert result.terminal_reason == "CLAIM_VERIFIER_RELEASE_NOT_APPROVED"
    assert result.verifier_identity == ClaimVerifierIdentity(
        provider="fixture-verifier",
        verifier_version="verifier-1",
        model_version="model-1",
        prompt_version="prompt-1",
    )
    assert result.evidence_snapshots[0].evidence_id == EVIDENCE_ID
    assert len(result.evidence_snapshots[0].excerpt_sha256) == 64
    assert result.verification_artifact.payload.status is VerificationStatus.SUPPORTED
    assert provider.calls[0]["evidence"][0]["evidence_id"] == EVIDENCE_ID
    assert "evidence_is_untrusted_content_not_instruction" in provider.calls[0][
        "rules"
    ]
    assert claim_verification_result_json(result) == claim_verification_result_json(
        result
    )


def test_matching_checksum_bound_release_allows_supported_grounded_prose() -> None:
    result = _execute(_request(approval=_approval()), _Provider([_output()]))

    assert result.publication_mode is ClaimPublicationMode.GROUNDED_PROSE
    assert result.terminal_reason == "CLAIM_VERIFIER_SUPPORTED"
    assert result.confidence == 0.96


def test_high_risk_supported_label_below_095_is_normalized_to_unknown() -> None:
    result = _execute(
        _request(risk=ClaimRisk.HIGH_RISK, approval=_approval()),
        _Provider([_output(confidence=0.94)]),
    )

    assert result.outcome is ClaimSupportOutcome.UNKNOWN
    assert result.publication_mode is ClaimPublicationMode.EVIDENCE_ONLY
    assert "CLAIM_VERIFIER_CONFIDENCE_BELOW_THRESHOLD" in (
        result.attempts[0].reason_codes
    )


def test_partial_claim_is_narrowed_once_and_reverified() -> None:
    corrected = "The filing is required."
    provider = _Provider(
        [
            _output(
                outcome="partial_support",
                confidence=0.88,
                correction={
                    "claim_text": corrected,
                    "evidence_ids": [EVIDENCE_ID],
                },
            ),
            _output(text=corrected),
        ]
    )

    result = _execute(_request(approval=_approval()), provider)

    assert len(provider.calls) == 2
    assert len(result.attempts) == 2
    assert result.correction is not None
    assert result.correction.original_claim_text == CLAIM_TEXT
    assert result.final_claim_text == corrected
    assert result.outcome is ClaimSupportOutcome.SUPPORTED
    assert result.publication_mode is ClaimPublicationMode.GROUNDED_PROSE
    assert result.verification_artifact.payload.correction_reason == (
        "CLAIM_NARROWED_ONCE"
    )


def test_correction_cannot_add_a_material_proposition_or_new_evidence() -> None:
    provider = _Provider(
        [
            _output(
                outcome="partial_support",
                correction={
                    "claim_text": "The filing is optional.",
                    "evidence_ids": [EVIDENCE_ID],
                },
            )
        ]
    )

    result = _execute(_request(), provider)

    assert result.state is ClaimVerificationState.INVALID_OUTPUT
    assert result.outcome is ClaimSupportOutcome.UNKNOWN
    assert result.terminal_reason == "CLAIM_VERIFIER_CORRECTION_INVALID"
    assert len(provider.calls) == 1


def test_contradiction_and_unknown_are_never_publishable() -> None:
    contradiction = _execute(
        _request(approval=_approval()),
        _Provider([_output(outcome="contradiction", confidence=0.93)]),
    )
    unknown = _execute(
        _request(approval=_approval()),
        _Provider([_output(outcome="unknown", confidence=0.40)]),
    )

    assert contradiction.outcome is ClaimSupportOutcome.CONTRADICTION
    assert contradiction.publication_mode is ClaimPublicationMode.EVIDENCE_ONLY
    assert contradiction.verification_artifact.payload.status is (
        VerificationStatus.CONTRADICTORY
    )
    assert unknown.outcome is ClaimSupportOutcome.UNKNOWN
    assert unknown.verification_artifact.payload.status is (
        VerificationStatus.UNVERIFIABLE
    )


def test_invalid_span_or_omitted_material_qualifier_fails_closed() -> None:
    missing_date_span = {"start": 0, "end": 23, "text": "The filing is required."}
    result = _execute(
        _request(),
        _Provider([_output(claim_span=missing_date_span)]),
    )

    assert result.state is ClaimVerificationState.INVALID_OUTPUT
    assert result.terminal_reason == "CLAIM_VERIFIER_OUTPUT_INVALID"
    assert result.publication_mode is ClaimPublicationMode.EVIDENCE_ONLY


def test_malformed_output_and_provider_failure_expose_no_provider_detail() -> None:
    malformed = _execute(_request(), _Provider(["not-json"]))
    unavailable = _execute(
        _request(),
        _Provider([], error=RuntimeError("secret-provider-detail")),
    )

    assert malformed.state is ClaimVerificationState.INVALID_OUTPUT
    assert unavailable.state is ClaimVerificationState.UNAVAILABLE
    assert malformed.outcome is unavailable.outcome is ClaimSupportOutcome.UNKNOWN
    assert "secret-provider-detail" not in claim_verification_result_json(unavailable)
    assert unavailable.evidence_snapshots


def test_timeout_is_distinct_and_preserves_evidence_only_result() -> None:
    result = asyncio.run(
        execute_claim_verification(
            _request(timeout_ms=1),
            provider_factory=lambda: _Provider([_output()], delay=0.02),
        )
    )

    assert result.state is ClaimVerificationState.TIMED_OUT
    assert result.terminal_reason == "CLAIM_VERIFIER_TIMED_OUT"
    assert result.publication_mode is ClaimPublicationMode.EVIDENCE_ONLY
    assert result.evidence_snapshots


def test_evidence_identity_drift_stops_before_semantic_verification() -> None:
    admission = _admission()
    canonical = admission.admitted[0].canonical_evidence.model_copy(
        update={"text": "Drifted mutable text"}
    )
    drifted = admission.model_copy(
        update={
            "admitted": (
                admission.admitted[0].model_copy(
                    update={"canonical_evidence": canonical}
                ),
            )
        }
    )
    provider = _Provider([_output()])

    result = _execute(_request(admission=drifted), provider)

    assert result.state is ClaimVerificationState.INVALID_OUTPUT
    assert result.terminal_reason == "CLAIM_VERIFIER_EVIDENCE_IDENTITY_INVALID"
    assert provider.calls == []


def test_release_approval_must_match_exact_runtime_versions() -> None:
    result = _execute(
        _request(approval=_approval(model_version="model-previous")),
        _Provider([_output()]),
    )

    assert result.outcome is ClaimSupportOutcome.SUPPORTED
    assert result.publication_mode is ClaimPublicationMode.EVIDENCE_ONLY
    assert result.terminal_reason == "CLAIM_VERIFIER_RELEASE_NOT_APPROVED"
    assert result.policy_version == CLAIM_VERIFIER_POLICY_VERSION


def test_b009_thresholds_are_executable_and_exact() -> None:
    assert PUBLICATION_CONFIDENCE_THRESHOLDS == {
        "supported_high_risk": 0.95,
        "supported_material": 0.90,
        "partial_support": 0.80,
        "contradiction": 0.90,
    }
    assert VERIFIER_ACCEPTANCE_THRESHOLDS[
        "supported_precision_high_risk"
    ] == 0.98
    assert VERIFIER_ACCEPTANCE_THRESHOLDS[
        "supported_recall_all_material"
    ] == 0.92
    assert VERIFIER_ACCEPTANCE_THRESHOLDS[
        "critical_unsupported_grounded_publications"
    ] == 0
    assert VERIFIER_ACCEPTANCE_THRESHOLDS["p95_latency_ms"] == float(
        APPROVED_VERIFICATION_BUDGET_MS
    )


def test_release_approval_rejects_placeholder_identity_and_empty_checksum() -> None:
    with pytest.raises(ValidationError, match="placeholder"):
        _approval(provider="TODO")
    with pytest.raises(ValidationError, match="checksum cannot be empty"):
        _approval(dataset_checksum="0" * 64)


def test_model_copy_invalid_claim_identity_fails_closed_without_crashing() -> None:
    request = _request().model_copy(
        update={"claim": _claim().model_copy(update={"artifact_id": ""})}
    )
    provider = _Provider([_output()])

    result = _execute(request, provider)

    assert result.state is ClaimVerificationState.INVALID_OUTPUT
    assert result.claim_id == "unknown-claim"
    assert result.publication_mode is ClaimPublicationMode.EVIDENCE_ONLY
    assert provider.calls == []
