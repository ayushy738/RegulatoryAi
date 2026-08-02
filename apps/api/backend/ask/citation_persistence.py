from __future__ import annotations

import json
from dataclasses import dataclass
from enum import StrEnum
from typing import Any, Literal, Self
from uuid import UUID

from pydantic import BaseModel, ConfigDict, Field, model_validator
from sqlalchemy import text
from sqlalchemy.orm import Session

from backend.ask.claim_verification import (
    CLAIM_VERIFIER_POLICY_VERSION,
    ClaimSupportOutcome,
    ClaimVerificationResult,
)
from backend.ask.models import AskSource
from backend.ask.orchestration.contracts import (
    ArtifactEnvelope,
    CandidateClaimPayload,
    KnowledgeMode,
    ProvenanceClass,
)

CITATION_PERSISTENCE_SCHEMA_VERSION = "1"
CITATION_PERSISTENCE_POLICY_VERSION = "ask-ai-citation-persistence-v1"


class CitationPersistenceError(RuntimeError):
    """The verified claim cannot be attached to the owned response snapshot."""


class CitationPersistenceConflict(CitationPersistenceError):
    """A stable persistence identity already contains different content."""


class CurrentSourceStatus(StrEnum):
    CURRENT = "current"
    SUPERSEDED = "superseded"
    AVAILABLE_UNCLASSIFIED = "available_unclassified"
    NOT_APPLICABLE = "not_applicable"


class CitationPersistenceModel(BaseModel):
    model_config = ConfigDict(
        extra="forbid",
        frozen=True,
        strict=True,
        str_strip_whitespace=True,
    )


class PersistedEvidenceReference(CitationPersistenceModel):
    citation_id: UUID
    source_id: UUID
    evidence_id: str = Field(min_length=1, max_length=500)
    ordinal: int = Field(ge=0)
    marker: str | None = Field(default=None, max_length=100)


class VerifiedClaimPersistenceRequest(CitationPersistenceModel):
    schema_version: Literal["1"] = CITATION_PERSISTENCE_SCHEMA_VERSION
    policy_version: Literal["ask-ai-citation-persistence-v1"] = (
        CITATION_PERSISTENCE_POLICY_VERSION
    )
    run_id: UUID
    section_id: UUID
    session_id: UUID
    user_id: UUID
    claim_id: UUID
    claim_ordinal: int = Field(ge=0)
    candidate_claim: ArtifactEnvelope
    verification: ClaimVerificationResult
    evidence_references: tuple[PersistedEvidenceReference, ...] = Field(
        min_length=1,
    )
    composer_model: str | None = Field(default=None, max_length=200)
    composer_policy_version: str | None = Field(default=None, max_length=200)
    composer_prompt_version: str | None = Field(default=None, max_length=200)
    confidence_result: dict[str, Any] | None = None

    @model_validator(mode="after")
    def validate_exact_identity(self) -> Self:
        payload = self.candidate_claim.payload
        lineage = self.candidate_claim.provenance
        if not isinstance(payload, CandidateClaimPayload) or not payload.material:
            raise ValueError("Persistence requires one material Candidate Claim")
        if (
            lineage is None
            or lineage.knowledge_mode is not KnowledgeMode.GROUNDED_REGULATORY
            or lineage.provenance_class
            is not ProvenanceClass.INTERNAL_REGULATORY_CORPUS
        ):
            raise ValueError("Citation persistence requires official provenance")
        if self.verification.policy_version != CLAIM_VERIFIER_POLICY_VERSION:
            raise ValueError("Citation persistence requires the current verifier policy")
        if self.verification.claim_id != self.candidate_claim.artifact_id:
            raise ValueError("Verification and Candidate Claim identity differ")
        verification_payload = self.verification.verification_artifact.payload
        if verification_payload.target_artifact_id != self.candidate_claim.artifact_id:
            raise ValueError("Verification artifact targets another claim")
        references = self.evidence_references
        if tuple(item.ordinal for item in references) != tuple(range(len(references))):
            raise ValueError("Citation ordinals must be contiguous and ordered")
        if len({item.citation_id for item in references}) != len(references):
            raise ValueError("Citation identities must be unique")
        if len({item.evidence_id for item in references}) != len(references):
            raise ValueError("Evidence identities must be unique")
        expected = payload.supporting_artifact_ids
        actual = tuple(item.evidence_id for item in references)
        if actual != expected:
            raise ValueError("Citation order must match Candidate Claim evidence order")
        snapshot_ids = tuple(
            item.evidence_id for item in self.verification.evidence_snapshots
        )
        if snapshot_ids != expected:
            raise ValueError("Verifier snapshots must match citation evidence order")
        return self


@dataclass(frozen=True, slots=True)
class PersistedVerifiedClaim:
    claim_id: UUID
    claim_key: str
    citation_ids: tuple[UUID, ...]
    evidence_keys: tuple[str, ...]


@dataclass(frozen=True, slots=True)
class PersistedCitationDetail:
    message_id: UUID
    response_version: int
    claim_id: UUID
    claim_key: str
    claim_ordinal: int
    claim_text: str
    support_status: str
    support_score: float | None
    citation_id: UUID
    evidence_key: str
    citation_ordinal: int
    marker: str | None
    verification_status: str
    verifier_provider: str | None
    verifier_version: str | None
    verifier_model: str | None
    verifier_prompt_version: str | None
    verifier_policy_version: str | None
    verification_latency_ms: int | None
    verifier_result: dict[str, Any] | None
    provenance: dict[str, Any] | None
    confidence_result: dict[str, Any] | None
    source: AskSource
    current_source_status: CurrentSourceStatus


class CitationPersistenceRepository:
    def __init__(self, session: Session) -> None:
        self._session = session

    def persist_verified_claim(
        self,
        request: VerifiedClaimPersistenceRequest,
    ) -> PersistedVerifiedClaim:
        request = VerifiedClaimPersistenceRequest.model_validate(
            request.model_dump(mode="python"),
            strict=True,
        )
        section = self._session.execute(
            text(
                """
                select section.knowledge_mode, section.response_version
                from public.ask_sections section
                join public.ask_runs run
                  on run.id = section.run_id
                 and run.session_id = section.session_id
                 and run.user_id = section.user_id
                 and run.response_version = section.response_version
                where section.id = :section_id
                  and section.run_id = :run_id
                  and section.session_id = :session_id
                  and section.user_id = :user_id
                  and section.knowledge_mode = 'official'
                for update of section
                """
            ),
            {
                "section_id": request.section_id,
                "run_id": request.run_id,
                "session_id": request.session_id,
                "user_id": request.user_id,
            },
        ).mappings().one_or_none()
        if section is None:
            raise CitationPersistenceError("Owned official response section not found")

        existing = self._existing(request)
        if existing is not None:
            return existing

        identity = request.verification.verifier_identity
        verification_json = json.dumps(
            request.verification.model_dump(mode="json"),
            ensure_ascii=False,
            separators=(",", ":"),
            sort_keys=True,
        )
        provenance_json = json.dumps(
            request.candidate_claim.provenance.model_dump(mode="json"),
            ensure_ascii=False,
            separators=(",", ":"),
            sort_keys=True,
        )
        confidence_json = (
            json.dumps(
                request.confidence_result,
                ensure_ascii=False,
                separators=(",", ":"),
                sort_keys=True,
            )
            if request.confidence_result is not None
            else None
        )
        claim_key = request.candidate_claim.artifact_id
        status = _stored_support_status(request.verification.outcome)
        common = {
            "run_id": request.run_id,
            "session_id": request.session_id,
            "user_id": request.user_id,
            "verifier_provider": identity.provider if identity else None,
            "verifier_version": identity.verifier_version if identity else None,
            "verifier_model": identity.model_version if identity else None,
            "verifier_prompt_version": identity.prompt_version if identity else None,
            "verifier_policy_version": request.verification.policy_version,
            "verification_latency_ms": request.verification.latency_ms,
            "verifier_result": verification_json,
        }
        inserted_claim = self._session.execute(
            text(
                """
                insert into public.ask_claims (
                  id, run_id, section_id, session_id, user_id, ordinal,
                  claim_key, knowledge_mode, claim_text, is_material,
                  support_status, support_score, model, policy_version,
                  prompt_version, verifier_provider, verifier_version,
                  verifier_model, verifier_prompt_version,
                  verifier_policy_version, verification_latency_ms,
                  verifier_result, provenance, confidence_result
                ) values (
                  :claim_id, :run_id, :section_id, :session_id, :user_id,
                  :claim_ordinal, :claim_key, 'official', :claim_text, true,
                  :support_status, :support_score, :composer_model,
                  :composer_policy_version, :composer_prompt_version,
                  :verifier_provider, :verifier_version, :verifier_model,
                  :verifier_prompt_version, :verifier_policy_version,
                  :verification_latency_ms, cast(:verifier_result as jsonb),
                  cast(:provenance as jsonb), cast(:confidence_result as jsonb)
                )
                returning id
                """
            ),
            {
                **common,
                "claim_id": request.claim_id,
                "section_id": request.section_id,
                "claim_ordinal": request.claim_ordinal,
                "claim_key": claim_key,
                "claim_text": request.verification.final_claim_text,
                "support_status": status,
                "support_score": request.verification.confidence,
                "composer_model": request.composer_model,
                "composer_policy_version": request.composer_policy_version,
                "composer_prompt_version": request.composer_prompt_version,
                "provenance": provenance_json,
                "confidence_result": confidence_json,
            },
        ).scalar_one()
        if inserted_claim != request.claim_id:
            raise CitationPersistenceError("Verified claim identity was not retained")

        for reference in request.evidence_references:
            inserted = self._session.execute(
                text(
                    """
                    insert into public.ask_citations (
                      id, run_id, claim_id, source_id, session_id, user_id,
                      ordinal, evidence_key, claim_knowledge_mode, source_class,
                      citation_kind, marker, evidence_snapshot,
                      locator_snapshot, support_score, verification_status,
                      verifier_provider, verifier_version, verifier_model,
                      verifier_prompt_version, verifier_policy_version,
                      verification_latency_ms, verifier_result, provenance
                    )
                    select
                      :citation_id, :run_id, :claim_id, source.id, :session_id,
                      :user_id, :ordinal, source.source_key, 'official',
                      'official', 'official_citation', :marker,
                      source.evidence_snapshot, source.locator_snapshot,
                      :support_score, :verification_status,
                      :verifier_provider, :verifier_version, :verifier_model,
                      :verifier_prompt_version, :verifier_policy_version,
                      :verification_latency_ms, cast(:verifier_result as jsonb),
                      cast(:provenance as jsonb)
                    from public.ask_sources source
                    where source.id = :source_id
                      and source.run_id = :run_id
                      and source.session_id = :session_id
                      and source.user_id = :user_id
                      and source.source_class = 'official'
                      and source.source_key = :evidence_key
                    returning id
                    """
                ),
                {
                    **common,
                    "citation_id": reference.citation_id,
                    "claim_id": request.claim_id,
                    "source_id": reference.source_id,
                    "ordinal": reference.ordinal,
                    "evidence_key": reference.evidence_id,
                    "marker": reference.marker,
                    "support_score": request.verification.confidence,
                    "verification_status": status,
                    "provenance": provenance_json,
                },
            ).scalar_one_or_none()
            if inserted != reference.citation_id:
                raise CitationPersistenceError(
                    "Owned citation source snapshot not found"
                )
        return PersistedVerifiedClaim(
            claim_id=request.claim_id,
            claim_key=claim_key,
            citation_ids=tuple(item.citation_id for item in request.evidence_references),
            evidence_keys=tuple(item.evidence_id for item in request.evidence_references),
        )

    def _existing(
        self,
        request: VerifiedClaimPersistenceRequest,
    ) -> PersistedVerifiedClaim | None:
        rows = list(
            self._session.execute(
                text(
                    """
                    select
                      claim.id as claim_id,
                      claim.claim_key,
                      claim.claim_text,
                      claim.support_status,
                      claim.support_score,
                      claim.verifier_result,
                      citation.id as citation_id,
                      citation.evidence_key,
                      citation.ordinal
                    from public.ask_claims claim
                    left join public.ask_citations citation
                      on citation.claim_id = claim.id
                     and citation.run_id = claim.run_id
                     and citation.session_id = claim.session_id
                     and citation.user_id = claim.user_id
                    where claim.run_id = :run_id
                      and claim.session_id = :session_id
                      and claim.user_id = :user_id
                      and (claim.id = :claim_id or claim.claim_key = :claim_key)
                    order by citation.ordinal
                    """
                ),
                {
                    "run_id": request.run_id,
                    "session_id": request.session_id,
                    "user_id": request.user_id,
                    "claim_id": request.claim_id,
                    "claim_key": request.candidate_claim.artifact_id,
                },
            ).mappings()
        )
        if not rows:
            return None
        first = rows[0]
        expected_result = request.verification.model_dump(mode="json")
        expected_citations = tuple(
            (item.citation_id, item.evidence_id, item.ordinal)
            for item in request.evidence_references
        )
        actual_citations = tuple(
            (row["citation_id"], row["evidence_key"], row["ordinal"])
            for row in rows
            if row["citation_id"] is not None
        )
        if (
            first["claim_id"] != request.claim_id
            or first["claim_key"] != request.candidate_claim.artifact_id
            or first["claim_text"] != request.verification.final_claim_text
            or first["support_status"]
            != _stored_support_status(request.verification.outcome)
            or (
                float(first["support_score"])
                if first["support_score"] is not None
                else None
            )
            != request.verification.confidence
            or dict(first["verifier_result"]) != expected_result
            or actual_citations != expected_citations
        ):
            raise CitationPersistenceConflict(
                "Verified claim identity already contains different content"
            )
        return PersistedVerifiedClaim(
            claim_id=request.claim_id,
            claim_key=request.candidate_claim.artifact_id,
            citation_ids=tuple(item[0] for item in actual_citations),
            evidence_keys=tuple(item[1] for item in actual_citations),
        )

    def get_owned_citation_detail(
        self,
        *,
        assistant_message_public_id: UUID,
        citation_id: UUID,
        user_id: UUID,
    ) -> PersistedCitationDetail | None:
        row = self._session.execute(
            text(
                """
                select
                  message.public_id as message_id,
                  run.response_version,
                  claim.id as claim_id,
                  claim.claim_key,
                  claim.ordinal as claim_ordinal,
                  claim.claim_text,
                  claim.support_status,
                  claim.support_score as claim_support_score,
                  citation.id as citation_id,
                  citation.evidence_key,
                  citation.ordinal as citation_ordinal,
                  citation.marker,
                  citation.verification_status,
                  citation.verifier_provider,
                  citation.verifier_version,
                  citation.verifier_model,
                  citation.verifier_prompt_version,
                  citation.verifier_policy_version,
                  citation.verification_latency_ms,
                  citation.verifier_result,
                  claim.provenance,
                  claim.confidence_result,
                  source.id as source_id,
                  source.ordinal as source_ordinal,
                  source.source_key,
                  source.source_class,
                  source.source_type,
                  source.document_id,
                  source.document_version_id,
                  source.chunk_id,
                  source.graph_reference,
                  source.title_snapshot,
                  source.url_snapshot,
                  source.issuer_snapshot,
                  source.publisher_snapshot,
                  source.jurisdiction_snapshot,
                  source.published_at,
                  source.retrieved_at,
                  source.evidence_snapshot,
                  source.locator_snapshot,
                  source.content_hash,
                  source.metadata,
                  source.created_at as source_created_at,
                  case
                    when source.source_class = 'live' then 'not_applicable'
                    when family.latest_version_id = source.document_version_id
                      and registry.superseded_by_registry_version_id is null
                      then 'current'
                    when registry.registry_version_id is not null
                      then 'superseded'
                    else 'available_unclassified'
                  end as current_source_status
                from public.chat_messages message
                join public.ask_runs run
                  on run.assistant_message_id = message.id
                 and run.session_id = message.session_id
                 and run.user_id = message.user_id
                 and run.response_version = message.response_version
                join public.ask_citations citation
                  on citation.run_id = run.id
                 and citation.session_id = run.session_id
                 and citation.user_id = run.user_id
                join public.ask_claims claim
                  on claim.id = citation.claim_id
                 and claim.run_id = citation.run_id
                 and claim.session_id = citation.session_id
                 and claim.user_id = citation.user_id
                join public.ask_sources source
                  on source.id = citation.source_id
                 and source.run_id = citation.run_id
                 and source.session_id = citation.session_id
                 and source.user_id = citation.user_id
                left join public.document_version_registry registry
                  on registry.document_version_id = source.document_version_id
                left join public.document_families family
                  on family.family_id = registry.family_id
                where message.public_id = :assistant_message_public_id
                  and message.user_id = :user_id
                  and message.role = 'assistant'
                  and citation.id = :citation_id
                """
            ),
            {
                "assistant_message_public_id": assistant_message_public_id,
                "citation_id": citation_id,
                "user_id": user_id,
            },
        ).mappings().one_or_none()
        if row is None:
            return None
        graph_reference = row["graph_reference"]
        verifier_result = row["verifier_result"]
        provenance = row["provenance"]
        confidence_result = row["confidence_result"]
        return PersistedCitationDetail(
            message_id=row["message_id"],
            response_version=row["response_version"],
            claim_id=row["claim_id"],
            claim_key=row["claim_key"],
            claim_ordinal=row["claim_ordinal"],
            claim_text=row["claim_text"],
            support_status=row["support_status"],
            support_score=(
                float(row["claim_support_score"])
                if row["claim_support_score"] is not None
                else None
            ),
            citation_id=row["citation_id"],
            evidence_key=row["evidence_key"],
            citation_ordinal=row["citation_ordinal"],
            marker=row["marker"],
            verification_status=row["verification_status"],
            verifier_provider=row["verifier_provider"],
            verifier_version=row["verifier_version"],
            verifier_model=row["verifier_model"],
            verifier_prompt_version=row["verifier_prompt_version"],
            verifier_policy_version=row["verifier_policy_version"],
            verification_latency_ms=row["verification_latency_ms"],
            verifier_result=(
                dict(verifier_result) if verifier_result is not None else None
            ),
            provenance=dict(provenance) if provenance is not None else None,
            confidence_result=(
                dict(confidence_result) if confidence_result is not None else None
            ),
            source=AskSource(
                id=row["source_id"],
                ordinal=row["source_ordinal"],
                source_key=row["source_key"],
                source_class=row["source_class"],
                source_type=row["source_type"],
                document_id=row["document_id"],
                document_version_id=row["document_version_id"],
                chunk_id=row["chunk_id"],
                graph_reference=(
                    dict(graph_reference) if graph_reference is not None else None
                ),
                title_snapshot=row["title_snapshot"],
                url_snapshot=row["url_snapshot"],
                issuer_snapshot=row["issuer_snapshot"],
                publisher_snapshot=row["publisher_snapshot"],
                jurisdiction_snapshot=row["jurisdiction_snapshot"],
                published_at=row["published_at"],
                retrieved_at=row["retrieved_at"],
                evidence_snapshot=row["evidence_snapshot"],
                locator_snapshot=row["locator_snapshot"],
                content_hash=row["content_hash"],
                metadata=dict(row["metadata"]),
                created_at=row["source_created_at"],
            ),
            current_source_status=CurrentSourceStatus(row["current_source_status"]),
        )


def _stored_support_status(outcome: ClaimSupportOutcome) -> str:
    return {
        ClaimSupportOutcome.SUPPORTED: "supported",
        ClaimSupportOutcome.PARTIAL_SUPPORT: "partially_supported",
        ClaimSupportOutcome.CONTRADICTION: "contradictory",
        ClaimSupportOutcome.UNKNOWN: "unverifiable",
    }[outcome]
