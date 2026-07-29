from __future__ import annotations

from datetime import UTC, date, datetime
from pathlib import Path

from sqlalchemy import text
from sqlalchemy.orm import Session

from backend.ask.manual_document_search import (
    ManualDocumentSearchRequest,
    ManualDocumentSearchService,
)
from backend.core.migrations import apply_pending_migrations
from backend.tests.ask_ai_postgres import POSTGRES_MARK

pytestmark = POSTGRES_MARK

MIGRATIONS_DIR = Path(__file__).parents[1] / "migrations"
NOW = datetime(2026, 7, 27, 12, tzinfo=UTC)


def _seed(engine) -> dict[str, int]:
    with engine.begin() as connection:
        family_id = connection.execute(
            text(
                """
                insert into public.document_families (
                  canonical_title, issuer, document_type
                ) values (
                  'Deviation Settlement Mechanism Regulations',
                  'CERC', 'REGULATION'
                ) returning family_id
                """
            )
        ).scalar_one()
        documents = connection.execute(
            text(
                """
                insert into public.documents (
                  url_hash, source_url, title, issuing_body, jurisdiction,
                  issue_date, doc_type
                ) values
                  (
                    'manual-current', 'https://example.test/current',
                    'DSM Regulations 2026', 'CERC', 'central',
                    date '2026-01-01', 'REGULATION'
                  ),
                  (
                    'manual-superseded', 'https://example.test/superseded',
                    'DSM Regulations 2024', 'CERC', 'central',
                    date '2024-01-01', 'REGULATION'
                  ),
                  (
                    'manual-draft', 'https://example.test/draft',
                    'Draft DSM Procedure', 'CERC', 'central',
                    date '2026-06-01', 'DRAFT PROCEDURE'
                  )
                returning id, url_hash
                """
            )
        ).mappings()
        document_ids = {row["url_hash"]: row["id"] for row in documents}
        version_ids: dict[str, int] = {}
        for name, document_id in document_ids.items():
            version_ids[name] = connection.execute(
                text(
                    """
                    insert into public.document_versions (
                      document_id, file_hash
                    ) values (:document_id, :file_hash) returning id
                    """
                ),
                {
                    "document_id": document_id,
                    "file_hash": f"version-{name}",
                },
            ).scalar_one()
        registry_ids: dict[str, int] = {}
        registry_rows = {
            "manual-current": (
                "Version 2",
                date(2026, 1, 1),
                date(2026, 2, 1),
                "CERC/DSM/2026",
            ),
            "manual-superseded": (
                "Version 1",
                date(2024, 1, 1),
                date(2024, 2, 1),
                "CERC/DSM/2024",
            ),
            "manual-draft": (
                "Draft Version",
                date(2026, 6, 1),
                date(2027, 1, 1),
                "CERC/DSM/DRAFT",
            ),
        }
        for name, (
            version_label,
            publication_date,
            effective_date,
            reference,
        ) in registry_rows.items():
            registry_ids[name] = connection.execute(
                text(
                    """
                    insert into public.document_version_registry (
                      family_id, document_id, document_version_id,
                      version_label, publication_date, issue_date,
                      effective_date, referenced_instrument
                    ) values (
                      :family_id, :document_id, :version_id,
                      :version_label, :publication_date, :publication_date,
                      :effective_date, :reference
                    ) returning registry_version_id
                    """
                ),
                {
                    "family_id": family_id,
                    "document_id": document_ids[name],
                    "version_id": version_ids[name],
                    "version_label": version_label,
                    "publication_date": publication_date,
                    "effective_date": effective_date,
                    "reference": reference,
                },
            ).scalar_one()
        connection.execute(
            text(
                """
                update public.document_version_registry
                set superseded_by_registry_version_id = :current
                where registry_version_id = :superseded
                """
            ),
            {
                "current": registry_ids["manual-current"],
                "superseded": registry_ids["manual-superseded"],
            },
        )
        chunks = {
            "manual-current": (
                "Deviation charge applies to interstate generators.",
                4,
                "Applicability",
            ),
            "manual-superseded": (
                "Historical deviation charge methodology.",
                8,
                "Historical methodology",
            ),
            "manual-draft": (
                "Proposed deviation charge consultation text.",
                2,
                "Draft scope",
            ),
        }
        for name, (content, page, section) in chunks.items():
            connection.execute(
                text(
                    """
                    insert into public.document_chunks (
                      document_id, version_id, family_id, chunk_index,
                      text, page_number, section_title
                    ) values (
                      :document_id, :version_id, :family_id, 0,
                      :content, :page, :section
                    )
                    """
                ),
                {
                    "document_id": document_ids[name],
                    "version_id": version_ids[name],
                    "family_id": family_id,
                    "content": content,
                    "page": page,
                    "section": section,
                },
            )
    return {
        **document_ids,
        "family_id": family_id,
    }


def _service(engine) -> ManualDocumentSearchService:
    return ManualDocumentSearchService(
        session_scope_factory=lambda: Session(engine),
        clock=lambda: NOW,
    )


def test_postgres_manual_search_exact_phrase_filters_and_within_document(
    postgres_engine,
) -> None:
    apply_pending_migrations(postgres_engine, MIGRATIONS_DIR, through="0034")
    ids = _seed(postgres_engine)
    service = _service(postgres_engine)

    exact = service.search(
        ManualDocumentSearchRequest(
            query="deviation charge applies",
            exact_phrase=True,
            issuer="CERC",
            document_number="DSM/2026",
            document_type="REGULATION",
            family="Settlement Mechanism",
            version="Version 2",
            status="current",
            issued_from=date(2026, 1, 1),
            issued_to=date(2026, 12, 31),
            effective_from=date(2026, 2, 1),
            effective_to=date(2026, 2, 1),
            within_document="interstate generators",
        )
    )

    assert exact.status == "complete"
    assert exact.items[0].document_id == ids["manual-current"]
    assert exact.items[0].document_number == "CERC/DSM/2026"
    assert exact.items[0].status == "current"
    assert exact.items[0].within_document_matches[0].page_number == 4
    assert exact.items[0].within_document_matches[0].section_title == (
        "Applicability"
    )
    direct = service.search(
        ManualDocumentSearchRequest(
            document_id=exact.items[0].document_id,
            registry_version_id=exact.items[0].registry_version_id,
        )
    )
    assert direct.items[0].result_id == exact.items[0].result_id


def test_postgres_manual_search_lifecycle_no_match_and_filter_pages(
    postgres_engine,
) -> None:
    apply_pending_migrations(postgres_engine, MIGRATIONS_DIR, through="0034")
    _seed(postgres_engine)
    service = _service(postgres_engine)

    superseded = service.search(
        ManualDocumentSearchRequest(
            query="DSM",
            status="superseded",
        )
    )
    draft = service.search(
        ManualDocumentSearchRequest(
            title="Draft DSM",
            status="draft",
        )
    )
    missing = service.search(
        ManualDocumentSearchRequest(
            document_number="NOT-A-REAL-REFERENCE",
        )
    )

    assert superseded.items[0].status == "superseded"
    historical_direct = service.search(
        ManualDocumentSearchRequest(
            document_id=superseded.items[0].document_id,
            registry_version_id=superseded.items[0].registry_version_id,
        )
    )
    assert historical_direct.items[0].result_id == (
        superseded.items[0].result_id
    )
    assert draft.items[0].status == "draft"
    assert missing.status == "no_match"
    assert missing.items == ()


def test_postgres_manual_search_cursor_is_stable_and_filter_bound(
    postgres_engine,
) -> None:
    apply_pending_migrations(postgres_engine, MIGRATIONS_DIR, through="0034")
    _seed(postgres_engine)
    service = _service(postgres_engine)

    first = service.search(
        ManualDocumentSearchRequest(query="DSM", limit=1)
    )
    assert first.next_cursor is not None
    second = service.search(
        ManualDocumentSearchRequest(
            query="DSM",
            cursor=first.next_cursor,
            limit=1,
        )
    )

    assert second.status == "complete"
    assert first.items[0].result_id != second.items[0].result_id
    assert second.as_of == first.as_of
