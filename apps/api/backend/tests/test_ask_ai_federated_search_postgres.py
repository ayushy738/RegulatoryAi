from __future__ import annotations

from pathlib import Path
from uuid import uuid4

from sqlalchemy import text
from sqlalchemy.orm import Session

from backend.ask.federated_search import (
    FederatedSearchRequest,
    FederatedSearchService,
    SearchGroup,
)
from backend.core.migrations import apply_pending_migrations
from backend.tests.ask_ai_postgres import POSTGRES_MARK, insert_auth_user

pytestmark = POSTGRES_MARK

MIGRATIONS_DIR = Path(__file__).parents[1] / "migrations"


def _seed(engine, user_id) -> None:
    with engine.begin() as connection:
        insert_auth_user(connection, user_id)
        connection.execute(
            text(
                """
                insert into public.regulatory_entity_catalog (
                  canonical_id, canonical_name, entity_class, jurisdiction,
                  workspace_priority, provenance_kind, provenance_ref
                ) values (
                  'in.central.dsm', 'Deviation Settlement Mechanism',
                  'regulatory_concept', 'India/Central', 90,
                  'curated_catalog', 'fixture:dsm'
                )
                """
            )
        )
        connection.execute(
            text(
                """
                insert into public.regulatory_entity_aliases (
                  canonical_id, alias, alias_kind, jurisdiction,
                  provenance_kind, provenance_ref
                ) values (
                  'in.central.dsm', 'DSM', 'acronym', 'India/Central',
                  'curated_catalog', 'fixture:dsm'
                )
                """
            )
        )
        rows = connection.execute(
            text(
                """
                insert into public.documents (
                  url_hash, source_url, title, issuing_body, jurisdiction,
                  issue_date, doc_type
                ) values
                  (
                    'dsm-regulation', 'https://example.test/regulation',
                    'DSM Regulations', 'CERC', 'central', date '2026-01-01',
                    'REGULATION'
                  ),
                  (
                    'dsm-procedure', 'https://example.test/procedure',
                    'DSM Operating Procedure', 'CERC', 'central',
                    date '2026-02-01', 'PROCEDURE'
                  ),
                  (
                    'dsm-consultation', 'https://example.test/consultation',
                    'DSM Consultation Paper', 'CERC', 'central',
                    date '2026-03-01', 'CONSULTATION'
                  )
                returning id, url_hash
                """
            )
        ).mappings()
        document_ids = {row["url_hash"]: row["id"] for row in rows}
        version_id = connection.execute(
            text(
                """
                insert into public.document_versions (document_id, file_hash)
                values (:document_id, 'dsm-version') returning id
                """
            ),
            {"document_id": document_ids["dsm-regulation"]},
        ).scalar_one()
        connection.execute(
            text(
                """
                insert into public.events (
                  document_id, version_id, event_type, topic_tags
                ) values (
                  :document_id, :version_id, 'NEW',
                  array['settlement', 'DSM']
                )
                """
            ),
            {
                "document_id": document_ids["dsm-regulation"],
                "version_id": version_id,
            },
        )
        connection.execute(
            text(
                """
                insert into public.regulatory_graph_stakeholders (
                  document_id, document_version_id, stakeholder,
                  normalized_stakeholder, confidence
                ) values (
                  :document_id, :version_id, 'Generators',
                  'generators', 0.9
                )
                """
            ),
            {
                "document_id": document_ids["dsm-regulation"],
                "version_id": version_id,
            },
        )
        family_id = connection.execute(
            text(
                """
                insert into public.document_families (
                  canonical_title, issuer, document_type
                ) values ('DSM Regulations', 'CERC', 'REGULATION')
                returning family_id
                """
            )
        ).scalar_one()
        registry_id = connection.execute(
            text(
                """
                insert into public.document_version_registry (
                  family_id, document_id, document_version_id,
                  version_label, publication_date, amendment_number,
                  amendment_label
                ) values (
                  :family_id, :document_id, :version_id,
                  'DSM Amendment 1', date '2026-04-01', 1,
                  'DSM First Amendment'
                ) returning registry_version_id
                """
            ),
            {
                "family_id": family_id,
                "document_id": document_ids["dsm-regulation"],
                "version_id": version_id,
            },
        ).scalar_one()
        connection.execute(
            text(
                """
                insert into public.deadline_history (
                  family_id, registry_version_id, document_id,
                  document_version_id, deadline_type, deadline_date,
                  raw_date, extracted_from, confidence
                ) values (
                  :family_id, :registry_id, :document_id, :version_id,
                  'DSM comments deadline', date '2026-08-15',
                  '15 August 2026', 'DSM Regulations section 4', 0.9
                )
                """
            ),
            {
                "family_id": family_id,
                "registry_id": registry_id,
                "document_id": document_ids["dsm-regulation"],
                "version_id": version_id,
            },
        )
        session_id = uuid4()
        connection.execute(
            text(
                """
                insert into public.chat_sessions (
                  id, user_id, title, primary_entity, primary_topic
                ) values (
                  :session_id, :user_id, 'DSM prior research',
                  'DSM', 'amendment'
                )
                """
            ),
            {"session_id": session_id, "user_id": user_id},
        )


def _service(engine) -> FederatedSearchService:
    return FederatedSearchService(
        session_scope_factory=lambda: Session(engine)
    )


def test_postgres_search_groups_canonical_sources_and_owned_research(
    postgres_engine,
) -> None:
    apply_pending_migrations(postgres_engine, MIGRATIONS_DIR, through="0033")
    user_id = uuid4()
    _seed(postgres_engine, user_id)

    response = _service(postgres_engine).search(
        user_id=user_id,
        request=FederatedSearchRequest(query="DSM", limit=10),
    )

    groups = {group.group: group for group in response.groups}
    assert groups[SearchGroup.BEST_MATCH].items[0].result_id == (
        "entity:in.central.dsm"
    )
    assert groups[SearchGroup.ENTITIES].status == "complete"
    assert groups[SearchGroup.OFFICIAL_REGULATIONS].status == "complete"
    assert groups[SearchGroup.OFFICIAL_DOCUMENTS].status == "complete"
    assert groups[SearchGroup.AMENDMENTS].status == "complete"
    assert groups[SearchGroup.CONSULTATIONS].status == "complete"
    assert groups[SearchGroup.DEADLINES].status == "complete"
    assert groups[SearchGroup.PREVIOUS_RESEARCH].status == "complete"
    assert response.correction is not None
    assert response.correction.reversible is True


def test_previous_research_is_owner_isolated_and_filters_are_applied(
    postgres_engine,
) -> None:
    apply_pending_migrations(postgres_engine, MIGRATIONS_DIR, through="0033")
    owner_id = uuid4()
    other_id = uuid4()
    _seed(postgres_engine, owner_id)
    with postgres_engine.begin() as connection:
        insert_auth_user(connection, other_id)

    other = _service(postgres_engine).search(
        user_id=other_id,
        request=FederatedSearchRequest(
            query="DSM",
            group=SearchGroup.PREVIOUS_RESEARCH,
        ),
    )
    filtered = _service(postgres_engine).search(
        user_id=owner_id,
        request=FederatedSearchRequest(
            query="DSM",
            group=SearchGroup.ENTITIES,
            filters={
                "jurisdiction": "another",
            },
        ),
    )

    assert other.groups[-1].status == "no_match"
    assert filtered.groups[1].status == "no_match"


def test_postgres_search_applies_structured_and_provenance_filters(
    postgres_engine,
) -> None:
    apply_pending_migrations(postgres_engine, MIGRATIONS_DIR, through="0033")
    owner_id = uuid4()
    _seed(postgres_engine, owner_id)

    regulation = _service(postgres_engine).search(
        user_id=owner_id,
        request=FederatedSearchRequest(
            query="DSM",
            group=SearchGroup.OFFICIAL_REGULATIONS,
            filters={
                "provenance": "internal_regulatory_corpus",
                "status": "NEW",
                "stakeholder": "generator",
                "topic": "settlement",
                "lifecycle": "current",
            },
        ),
    )
    excluded_research = _service(postgres_engine).search(
        user_id=owner_id,
        request=FederatedSearchRequest(
            query="DSM",
            group=SearchGroup.PREVIOUS_RESEARCH,
            filters={"provenance": "internal_regulatory_corpus"},
        ),
    )

    assert regulation.groups[2].status == "complete"
    assert excluded_research.groups[-1].status == "no_match"


def test_postgres_group_cursor_is_stable_across_relevance_ties(
    postgres_engine,
) -> None:
    apply_pending_migrations(postgres_engine, MIGRATIONS_DIR, through="0033")
    owner_id = uuid4()
    _seed(postgres_engine, owner_id)
    with postgres_engine.begin() as connection:
        connection.execute(
            text(
                """
                insert into public.documents (
                  url_hash, source_url, title, issuing_body, jurisdiction,
                  issue_date, doc_type
                ) values (
                  'dsm-regulation-second',
                  'https://example.test/regulation-second',
                  'DSM Balancing Regulations', 'CERC', 'central',
                  date '2026-05-01', 'REGULATION'
                )
                """
            )
        )

    service = _service(postgres_engine)
    first = service.search(
        user_id=owner_id,
        request=FederatedSearchRequest(
            query="DSM",
            group=SearchGroup.OFFICIAL_REGULATIONS,
            limit=1,
        ),
    )
    first_group = first.groups[2]
    assert first_group.next_cursor is not None
    second = service.search(
        user_id=owner_id,
        request=FederatedSearchRequest(
            query="DSM",
            group=SearchGroup.OFFICIAL_REGULATIONS,
            cursor=first_group.next_cursor,
            limit=1,
        ),
    )

    assert second.groups[2].status == "complete"
    assert first_group.items[0].result_id != second.groups[2].items[0].result_id
