from datetime import UTC, date, datetime

from backend.core.models import DigestResponse, EventSummary, SummaryPayload

SAMPLE_DIGEST = DigestResponse(
    digest_date=date(2026, 6, 20),
    event_count=3,
    events=[
        EventSummary(
            id=101,
            title="MNRE monthly policy and regulatory update: renewable procurement notes",
            issuing_body="Ministry of New and Renewable Energy",
            jurisdiction="central",
            issue_date=date(2026, 6, 18),
            event_type="NEW",
            topic_tags=["solar", "RPO/REC", "tariff"],
            raw_summary="Digest-parser item awaiting primary-document extraction.",
            source_url="https://mnre.gov.in/en/monthly-updates/",
            detected_at=datetime(2026, 6, 20, 1, 30, tzinfo=UTC),
            summary=SummaryPayload(
                plain_english_summary=(
                    "A new central renewable-energy update has been detected from the MNRE "
                    "digest spine."
                ),
                why_it_matters=(
                    "This is the first layer of the pipeline; the primary PDF will become "
                    "the grounded source for analysis after storage and extraction are configured."
                ),
                affected_segments=["solar", "renewable procurement"],
                important_dates=["2026-06-18"],
                action_required="monitor",
                confidence="medium",
                evidence_quotes=[],
            ),
        ),
        EventSummary(
            id=102,
            title="CERC order watch: tariff and open-access category flagged",
            issuing_body="Central Electricity Regulatory Commission",
            jurisdiction="central",
            issue_date=date(2026, 6, 17),
            event_type="CHANGED",
            topic_tags=["tariff", "open access", "transmission"],
            raw_summary="Conditional re-check found a changed candidate document.",
            source_url="https://cercind.gov.in/",
            detected_at=datetime(2026, 6, 20, 1, 31, tzinfo=UTC),
            summary=SummaryPayload(
                plain_english_summary=(
                    "The detector has marked this candidate as changed based on version metadata."
                ),
                why_it_matters=(
                    "Changed regulatory documents need a visible review queue so users do "
                    "not rely on stale terms."
                ),
                affected_segments=["distribution companies", "open-access consumers"],
                important_dates=[],
                action_required="monitor",
                confidence="medium",
                evidence_quotes=[],
            ),
        ),
        EventSummary(
            id=103,
            title="Ministry of Power notification queue item",
            issuing_body="Ministry of Power",
            jurisdiction="central",
            issue_date=None,
            event_type="NEW",
            topic_tags=["storage", "transmission"],
            raw_summary="Source audit passed; full crawler awaits API and storage keys.",
            source_url="https://powermin.gov.in/en",
            detected_at=datetime(2026, 6, 20, 1, 32, tzinfo=UTC),
            summary=SummaryPayload(
                plain_english_summary=(
                    "The source is in the Tier-0 monitoring set and ready for daily discovery."
                ),
                why_it_matters=(
                    "Keeping source health visible reduces the chance of silent crawler failure."
                ),
                affected_segments=["grid planning", "storage"],
                important_dates=[],
                action_required="monitor",
                confidence="low",
                evidence_quotes=[],
            ),
        ),
    ],
)

SOURCES = [
    {
        "id": 1,
        "code": "mnre",
        "name": "Ministry of New & Renewable Energy",
        "jurisdiction": "central",
        "url": "https://mnre.gov.in/en/monthly-updates/",
        "crawler_type": "digest",
        "allowed_domains": ["mnre.gov.in", "cdnbbsr.s3waas.gov.in"],
        "enabled": True,
        "consecutive_failures": 0,
    },
    {
        "id": 2,
        "code": "cerc",
        "name": "Central Electricity Regulatory Commission",
        "jurisdiction": "central",
        "url": "https://cercind.gov.in/",
        "crawler_type": "agent",
        "allowed_domains": ["cercind.gov.in"],
        "enabled": True,
        "consecutive_failures": 0,
    },
    {
        "id": 3,
        "code": "mop",
        "name": "Ministry of Power",
        "jurisdiction": "central",
        "url": "https://powermin.gov.in/en",
        "crawler_type": "agent",
        "allowed_domains": ["powermin.gov.in"],
        "enabled": True,
        "consecutive_failures": 0,
    },
]
