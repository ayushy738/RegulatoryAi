from __future__ import annotations

from collections.abc import Iterator
from contextlib import contextmanager
from datetime import UTC, datetime
from pathlib import Path
from uuid import UUID, uuid4

import pytest
from sqlalchemy import text
from sqlalchemy.engine import Engine
from sqlalchemy.orm import Session

from backend.ask.citation_persistence import (
    CitationPersistenceConflict,
    CitationPersistenceError,
    PersistedEvidenceReference,
    VerifiedClaimPersistenceRequest,
)
from backend.ask.claim_verification import (
    AtomicPropositionJudgment,
    ClaimPublicationMode,
    ClaimSpan,
    ClaimSupportOutcome,
    ClaimVerificationAttempt,
    ClaimVerificationResult,
    ClaimVerificationState,
    ClaimVerifierIdentity,
    EvidenceIdentitySnapshot,
    EvidenceSpan,
)
from backend.ask.orchestration.contracts import (
    ArtifactEnvelope,
    ArtifactProducer,
    CandidateClaimPayload,
    CapabilityScope,
    CapabilityTerminalState,
    ContentDerivation,
    KnowledgeMode,
    OrchestratorCapability,
    ProvenanceClass,
    ProvenanceLineage,
    SourceIdentity,
    TimeDimension,
    TransformationStep,
    VerificationResultPayload,
    VerificationStatus,
)
from backend.ask.persistence import AskPersistenceService
from backend.ask.schemas import AskCitationDetailResponse
from backend.core.migrations import apply_pending_migrations, discover_migrations
from backend.tests.ask_ai_postgres import POSTGRES_MARK, insert_auth_user

pytestmark = POSTGRES_MARK

MIGRATIONS_DIR = Path(__file__).parents[1] / "migrations"
MIGRATION = MIGRATIONS_DIR / "0035_ask_ai_citation_verification.sql"
README = MIGRATIONS_DIR / "README.md"
NOW = datetime(2026, 8, 1, 10, 0, tzinfo=UTC)
CLAIM_KEY = "claim:official:filing-deadline"
EVIDENCE_KEY = "evidence:official:filing-deadline"
CLAIM_TEXT = "The filing is required by 31 July 2026."


@contextmanager
def _session_scope(engine: Engine) -> Iterator[Session]:
    session = Session(bind=engine)
    try:
        yield session
        session.commit()
    except Exception:
        session.rollback()
        raise
    finally:
        session.close()


def _service(engine: Engine) -> AskPersistenceService:
    return AskPersistenceService(lambda: _session_scope(engine))


def _scope() -> CapabilityScope:
    return CapabilityScope(
        atomic_question_ids=("question-1",),
        section_keys=("official",),
        entity_ids=("entity-1",),
        jurisdiction="India",
        time_scope="current",
        date_semantics=(TimeDimension.EFFECTIVE,),
    )


def _candidate_claim() -> ArtifactEnvelope:
    source = SourceIdentity(
        source_id="document-1",
        provenance_class=ProvenanceClass.INTERNAL_REGULATORY_CORPUS,
        title="Filing Regulation",
        uri="https://official.example/filing",
        issuer_or_publisher="Regulator",
        issue_at=NOW,
    )
    return ArtifactEnvelope(
        artifact_id=CLAIM_KEY,
        producer=ArtifactProducer.RESPONSE_COMPOSER,
        scope=_scope(),
        payload=CandidateClaimPayload(
            claim_text=CLAIM_TEXT,
            material=True,
            supporting_artifact_ids=(EVIDENCE_KEY,),
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
                    input_artifact_ids=(EVIDENCE_KEY,),
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
        ancestry=(EVIDENCE_KEY, "plan-1"),
        capability_status=CapabilityTerminalState.SATISFIED,
    )


def _verification() -> ClaimVerificationResult:
    evidence_text = CLAIM_TEXT
    judgment = AtomicPropositionJudgment(
        proposition_id="prop-1",
        claim_span=ClaimSpan(start=0, end=len(CLAIM_TEXT), text=CLAIM_TEXT),
        outcome=ClaimSupportOutcome.SUPPORTED,
        confidence=0.97,
        evidence_ids=(EVIDENCE_KEY,),
        support_spans=(
            EvidenceSpan(
                evidence_id=EVIDENCE_KEY,
                start=0,
                end=len(evidence_text),
                text=evidence_text,
            ),
        ),
    )
    verification_artifact = ArtifactEnvelope(
        artifact_id=f"verification:{CLAIM_KEY}",
        producer=ArtifactProducer.CITATION_VERIFIER,
        scope=_scope(),
        payload=VerificationResultPayload(
            target_artifact_id=CLAIM_KEY,
            target_kind="candidate_claim",
            status=VerificationStatus.SUPPORTED,
            supported_boundary=CLAIM_TEXT,
            reasons=("CLAIM_VERIFIER_SUPPORTED",),
        ),
        ancestry=(CLAIM_KEY, EVIDENCE_KEY),
        capability_status=CapabilityTerminalState.SATISFIED,
    )
    return ClaimVerificationResult(
        claim_id=CLAIM_KEY,
        final_claim_text=CLAIM_TEXT,
        state=ClaimVerificationState.SATISFIED,
        outcome=ClaimSupportOutcome.SUPPORTED,
        confidence=0.97,
        publication_mode=ClaimPublicationMode.EVIDENCE_ONLY,
        evidence_snapshots=(
            EvidenceIdentitySnapshot(
                evidence_id=EVIDENCE_KEY,
                source_id="document-1",
                document_id=1,
                chunk_id=1,
                locator="chunk 1",
                excerpt_sha256="a" * 64,
                jurisdiction="India",
                source_status="current",
            ),
        ),
        attempts=(
            ClaimVerificationAttempt(
                attempt=0,
                claim_text=CLAIM_TEXT,
                evidence_ids=(EVIDENCE_KEY,),
                propositions=(judgment,),
                outcome=ClaimSupportOutcome.SUPPORTED,
                confidence=0.97,
                reason_codes=("PROPOSITION_1_SUPPORTED",),
            ),
        ),
        verifier_identity=ClaimVerifierIdentity(
            provider="fixture-verifier",
            verifier_version="verifier-1",
            model_version="model-1",
            prompt_version="prompt-1",
        ),
        verification_artifact=verification_artifact,
        latency_ms=125,
        terminal_reason="CLAIM_VERIFIER_RELEASE_NOT_APPROVED",
    )


def _insert_response_foundation(engine: Engine) -> dict[str, UUID]:
    owner_id = uuid4()
    session_id = uuid4()
    user_message_id = uuid4()
    assistant_message_id = uuid4()
    run_id = uuid4()
    section_id = uuid4()
    source_id = uuid4()
    with engine.begin() as connection:
        insert_auth_user(connection, owner_id)
    service = _service(engine)
    service.create_session(user_id=owner_id, session_id=session_id)
    placeholder = service.create_turn_placeholder(
        session_id=session_id,
        user_id=owner_id,
        user_message_id=user_message_id,
        assistant_message_id=assistant_message_id,
        content="When is the filing due?",
    )
    with engine.begin() as connection:
        document_id = connection.execute(
            text(
                """
                insert into public.documents (
                  url_hash, source_url, title, issuing_body, jurisdiction,
                  issue_date, doc_type
                ) values (
                  :url_hash, 'https://official.example/filing',
                  'Filing Regulation', 'Regulator', 'central',
                  date '2026-07-01', 'REGULATION'
                ) returning id
                """
            ),
            {"url_hash": f"citation-{run_id}"},
        ).scalar_one()
        version_id = connection.execute(
            text(
                """
                insert into public.document_versions (document_id, file_hash)
                values (:document_id, :file_hash) returning id
                """
            ),
            {"document_id": document_id, "file_hash": f"version-{run_id}"},
        ).scalar_one()
        family_id = connection.execute(
            text(
                """
                insert into public.document_families (
                  canonical_title, issuer, document_type, latest_version_id
                ) values (
                  'Filing Regulation', 'Regulator', 'REGULATION', :version_id
                ) returning family_id
                """
            ),
            {"version_id": version_id},
        ).scalar_one()
        connection.execute(
            text(
                """
                insert into public.document_version_registry (
                  family_id, document_id, document_version_id,
                  publication_date, issue_date, effective_date
                ) values (
                  :family_id, :document_id, :version_id,
                  date '2026-07-01', date '2026-07-01', date '2026-07-15'
                )
                """
            ),
            {
                "family_id": family_id,
                "document_id": document_id,
                "version_id": version_id,
            },
        )
        chunk_id = connection.execute(
            text(
                """
                insert into public.document_chunks (
                  document_id, version_id, family_id, chunk_index, text
                ) values (
                  :document_id, :version_id, :family_id, 0, :evidence
                ) returning id
                """
            ),
            {
                "document_id": document_id,
                "version_id": version_id,
                "family_id": family_id,
                "evidence": CLAIM_TEXT,
            },
        ).scalar_one()
        connection.execute(
            text(
                """
                update public.chat_messages
                set content = :content, status = 'completed'
                where id = :assistant_id
                """
            ),
            {
                "assistant_id": placeholder.assistant_message.id,
                "content": CLAIM_TEXT,
            },
        )
        connection.execute(
            text(
                """
                insert into public.ask_runs (
                  id, session_id, user_id, user_message_id,
                  assistant_message_id, response_version, status,
                  knowledge_mode_summary, created_at, updated_at
                ) values (
                  :run_id, :session_id, :user_id, :user_message_id,
                  :assistant_message_id, 1, 'completed',
                  jsonb_build_object('official', true), :now, :now
                )
                """
            ),
            {
                "run_id": run_id,
                "session_id": session_id,
                "user_id": owner_id,
                "user_message_id": placeholder.user_message.id,
                "assistant_message_id": placeholder.assistant_message.id,
                "now": NOW,
            },
        )
        connection.execute(
            text(
                """
                insert into public.ask_sections (
                  id, run_id, session_id, user_id, response_version, ordinal,
                  section_type, status, knowledge_mode, content,
                  card_schema_version, created_at, updated_at
                ) values (
                  :section_id, :run_id, :session_id, :user_id, 1, 0,
                  'direct_answer', 'completed', 'official', '{}'::jsonb,
                  '1', :now, :now
                )
                """
            ),
            {
                "section_id": section_id,
                "run_id": run_id,
                "session_id": session_id,
                "user_id": owner_id,
                "now": NOW,
            },
        )
        connection.execute(
            text(
                """
                insert into public.ask_sources (
                  id, run_id, session_id, user_id, ordinal, source_key,
                  source_class, source_type, document_id, document_version_id,
                  chunk_id, title_snapshot, url_snapshot, issuer_snapshot,
                  jurisdiction_snapshot, retrieved_at, evidence_snapshot,
                  locator_snapshot, content_hash, metadata, created_at
                ) values (
                  :source_id, :run_id, :session_id, :user_id, 0, :source_key,
                  'official', 'regulation', :document_id, :version_id,
                  :chunk_id, 'Filing Regulation',
                  'https://official.example/filing', 'Regulator', 'India',
                  :now, :evidence, 'chunk 1', :content_hash, '{}'::jsonb, :now
                )
                """
            ),
            {
                "source_id": source_id,
                "run_id": run_id,
                "session_id": session_id,
                "user_id": owner_id,
                "source_key": EVIDENCE_KEY,
                "document_id": document_id,
                "version_id": version_id,
                "chunk_id": chunk_id,
                "now": NOW,
                "evidence": CLAIM_TEXT,
                "content_hash": "a" * 64,
            },
        )
    return {
        "owner_id": owner_id,
        "session_id": session_id,
        "message_id": assistant_message_id,
        "run_id": run_id,
        "section_id": section_id,
        "source_id": source_id,
    }


def _request(ids: dict[str, UUID]) -> VerifiedClaimPersistenceRequest:
    return VerifiedClaimPersistenceRequest(
        run_id=ids["run_id"],
        section_id=ids["section_id"],
        session_id=ids["session_id"],
        user_id=ids["owner_id"],
        claim_id=uuid4(),
        claim_ordinal=0,
        candidate_claim=_candidate_claim(),
        verification=_verification(),
        evidence_references=(
            PersistedEvidenceReference(
                citation_id=uuid4(),
                source_id=ids["source_id"],
                evidence_id=EVIDENCE_KEY,
                ordinal=0,
                marker="[1]",
            ),
        ),
        composer_model="composer-model",
        composer_policy_version="composer-policy-1",
        composer_prompt_version="composer-prompt-1",
        confidence_result={"label": "medium", "score": 72},
    )


def test_0035_is_ordered_additive_and_documents_retained_rollback() -> None:
    migrations = discover_migrations(MIGRATIONS_DIR)
    sql = " ".join(MIGRATION.read_text(encoding="utf-8").lower().split())
    readme = " ".join(README.read_text(encoding="utf-8").lower().split())

    assert migrations[-1].filename == "0035_ask_ai_citation_verification.sql"
    assert "drop table" not in sql
    assert "drop column" not in sql
    assert "claim_key" in sql
    assert "evidence_key" in sql
    assert "verifier_prompt_version" in sql
    assert "rollback disables the v2 api/writer" in readme


def test_0035_backfills_existing_claim_and_evidence_identity(
    postgres_engine: Engine,
) -> None:
    apply_pending_migrations(postgres_engine, MIGRATIONS_DIR, through="0034")
    ids = _insert_response_foundation(postgres_engine)
    claim_id = uuid4()
    citation_id = uuid4()
    with postgres_engine.begin() as connection:
        connection.execute(
            text(
                """
                insert into public.ask_claims (
                  id, run_id, section_id, session_id, user_id, ordinal,
                  knowledge_mode, claim_text, support_status
                ) values (
                  :claim_id, :run_id, :section_id, :session_id, :user_id, 0,
                  'official', 'Legacy claim', 'pending'
                )
                """
            ),
            {**ids, "claim_id": claim_id, "user_id": ids["owner_id"]},
        )
        connection.execute(
            text(
                """
                insert into public.ask_citations (
                  id, run_id, claim_id, source_id, session_id, user_id,
                  ordinal, claim_knowledge_mode, source_class, citation_kind,
                  evidence_snapshot
                ) values (
                  :citation_id, :run_id, :claim_id, :source_id, :session_id,
                  :user_id, 0, 'official', 'official', 'official_citation',
                  :evidence
                )
                """
            ),
            {
                **ids,
                "claim_id": claim_id,
                "citation_id": citation_id,
                "user_id": ids["owner_id"],
                "evidence": CLAIM_TEXT,
            },
        )

    applied = apply_pending_migrations(
        postgres_engine,
        MIGRATIONS_DIR,
        through="0035",
    )

    assert applied[-1].version == "0035"
    with postgres_engine.connect() as connection:
        row = connection.execute(
            text(
                """
                select claim.claim_key, citation.evidence_key
                from public.ask_claims claim
                join public.ask_citations citation on citation.claim_id = claim.id
                where claim.id = :claim_id
                """
            ),
            {"claim_id": claim_id},
        ).mappings().one()
    assert row["claim_key"] == str(claim_id)
    assert row["evidence_key"] == EVIDENCE_KEY


def test_verified_claim_persists_atomically_restores_and_is_idempotent(
    postgres_engine: Engine,
) -> None:
    apply_pending_migrations(postgres_engine, MIGRATIONS_DIR, through="0035")
    ids = _insert_response_foundation(postgres_engine)
    request = _request(ids)
    service = _service(postgres_engine)

    first = service.persist_verified_claim(request)
    repeated = service.persist_verified_claim(request)
    detail = service.get_citation_detail(
        assistant_message_public_id=ids["message_id"],
        citation_id=request.evidence_references[0].citation_id,
        user_id=ids["owner_id"],
    )

    assert repeated == first
    assert detail is not None
    assert detail.claim_key == CLAIM_KEY
    assert detail.evidence_key == EVIDENCE_KEY
    assert detail.source.evidence_snapshot == CLAIM_TEXT
    assert detail.source.locator_snapshot == "chunk 1"
    assert detail.verifier_provider == "fixture-verifier"
    assert detail.verifier_version == "verifier-1"
    assert detail.verifier_model == "model-1"
    assert detail.verifier_prompt_version == "prompt-1"
    assert detail.verifier_policy_version == "ask-ai-claim-verifier-v1"
    assert detail.current_source_status.value == "current"
    response = AskCitationDetailResponse.from_domain(detail)
    assert response.verification is not None
    assert response.verification.outcome == "supported"
    assert response.verification.evidence_ids == [EVIDENCE_KEY]
    assert response.provenance is not None
    assert response.confidence_result == {"label": "medium", "score": 72}
    assert service.get_citation_detail(
        assistant_message_public_id=ids["message_id"],
        citation_id=request.evidence_references[0].citation_id,
        user_id=uuid4(),
    ) is None

    changed = request.model_copy(
        update={
            "verification": request.verification.model_copy(
                update={"final_claim_text": "Different claim"}
            )
        }
    )
    with pytest.raises(CitationPersistenceConflict):
        service.persist_verified_claim(changed)


def test_missing_owned_source_rolls_back_claim_and_citations(
    postgres_engine: Engine,
) -> None:
    apply_pending_migrations(postgres_engine, MIGRATIONS_DIR, through="0035")
    ids = _insert_response_foundation(postgres_engine)
    request = _request(ids)
    invalid_reference = request.evidence_references[0].model_copy(
        update={"source_id": uuid4()}
    )
    request = request.model_copy(
        update={"evidence_references": (invalid_reference,)}
    )

    with pytest.raises(CitationPersistenceError):
        _service(postgres_engine).persist_verified_claim(request)

    with postgres_engine.connect() as connection:
        count = connection.execute(
            text(
                """
                select count(*)
                from public.ask_claims
                where claim_key = :claim_key
                """
            ),
            {"claim_key": CLAIM_KEY},
        ).scalar_one()
    assert count == 0
