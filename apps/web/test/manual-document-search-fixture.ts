import type {
  AskManualDocumentSearchResponse,
} from "../lib/ask-ai-manual-search";

export function manualDocumentSearchFixture(): AskManualDocumentSearchResponse {
  return {
    schema_version: "1",
    policy_version: "ask-ai-manual-document-search-v1",
    status: "complete",
    as_of: "2026-07-27",
    items: [
      {
        result_id: "document:10:20",
        document_id: 10,
        registry_version_id: 20,
        document_version_id: 30,
        family_id: 40,
        title: "DSM Regulations 2026",
        issuer: "CERC",
        document_number: "CERC/DSM/2026",
        document_type: "REGULATION",
        jurisdiction: "central",
        issue_date: "2026-01-01",
        publication_date: "2026-01-01",
        effective_date: "2026-02-01",
        family_title: "Deviation Settlement Mechanism Regulations",
        version_label: "Version 2",
        status: "current",
        metadata_state: "complete",
        why_matched: "Official within-document text matched.",
        relevance: 900,
        source_url: "https://example.test/dsm",
        route: "/browse?document=10&version=20",
        within_document_matches: [
          {
            chunk_id: 50,
            page_number: 4,
            section_title: "Applicability",
            excerpt:
              "The deviation charge applies to interstate generators.",
          },
        ],
      },
    ],
    next_cursor: "next-manual-page",
  };
}
