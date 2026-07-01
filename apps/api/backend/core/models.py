from datetime import date, datetime
from typing import Any, Literal

from pydantic import BaseModel, Field, HttpUrl

DatePrecision = Literal["day", "month", "year", "unknown"]
Jurisdiction = Literal["central", "state"]
EventType = Literal["NEW", "CHANGED", "REPLACEMENT", "DUPLICATE"]
CandidateClassification = Literal[
    "REGULATORY_DOCUMENT",
    "TENDER_DOCUMENT",
    "CONSULTATION_DOCUMENT",
    "ORDER",
    "NOTIFICATION",
    "CIRCULAR",
    "POLICY_UPDATE",
    "GUIDELINE",
    "AMENDMENT",
    "HOMEPAGE",
    "LISTING_PAGE",
    "ARCHIVE_PAGE",
    "CATEGORY_PAGE",
    "SEARCH_PAGE",
    "NAVIGATION_PAGE",
    "INDEX_DOCUMENT",
]
FreshnessClassification = Literal["CURRENT", "RECENT", "HISTORICAL", "ARCHIVAL"]
DeadlineType = Literal[
    "CONSULTATION_DEADLINE",
    "HEARING_DATE",
    "TENDER_SUBMISSION_DEADLINE",
    "COMPLIANCE_DEADLINE",
    "IMPLEMENTATION_DATE",
    "PUBLICATION_DATE",
    "UNKNOWN_DATE",
]
SignificanceCategory = Literal["LOW", "MEDIUM", "HIGH", "CRITICAL"]
ActionabilityClassification = Literal["ACTIONABLE", "INFORMATIONAL", "REFERENCE_ONLY"]
EventQualityCategory = Literal["REJECT", "WEAK", "GOOD", "EXCELLENT"]
ChangeType = Literal[
    "NEW_DOCUMENT",
    "UPDATED_DOCUMENT",
    "AMENDMENT",
    "CORRIGENDUM",
    "ADDENDUM",
    "DEADLINE_CHANGE",
    "TENDER_UPDATE",
    "CONSULTATION_UPDATE",
    "POLICY_UPDATE",
    "WITHDRAWAL",
    "REISSUED_DOCUMENT",
    "NO_MATERIAL_CHANGE",
]


class DiscoveredDoc(BaseModel):
    """Output of agent_scraper / digest_parser."""

    source_code: str
    title: str
    source_url: str
    issuing_body: str | None = None
    issue_date: date | None = None
    issue_date_precision: DatePrecision = "unknown"
    doc_type: str | None = None
    jurisdiction: Jurisdiction | None = None
    raw_summary: str | None = None
    candidate_key: str | None = None
    source_record_id: str | None = None
    published_at: datetime | None = None


class FetchedFile(BaseModel):
    """Output of downloader."""

    discovered: DiscoveredDoc
    file_hash: str
    raw_file_path: str
    http_status: int
    etag: str | None = None
    last_modified: str | None = None
    content_type: str | None = None


class ExtractedDoc(BaseModel):
    """Output of extractor."""

    fetched: FetchedFile
    text: str
    content_hash: str
    page_count: int
    needs_ocr: bool
    text_path: str
    classification: CandidateClassification | None = None
    quality_score: float = 0.0
    evidence_excerpt: str | None = None


class CandidateQuality(BaseModel):
    classification: CandidateClassification
    is_valid_event_source: bool
    confidence: float
    reason_code: str
    explanation: str


class DiscoveryAuditRecord(BaseModel):
    source_code: str
    source_url: str
    title: str | None = None
    classification: CandidateClassification
    is_valid_event_source: bool
    confidence: float
    reason_code: str
    primary_url: str | None = None
    content_length: int = 0
    content_hash: str | None = None
    metadata: dict[str, Any] = Field(default_factory=dict)


class DeadlineIntelligence(BaseModel):
    raw_date: str
    normalized_date: date | None = None
    deadline_type: DeadlineType
    confidence: float
    evidence_snippet: str


class EventIntelligence(BaseModel):
    event_allowed: bool
    rejection_reason: str | None = None
    freshness: FreshnessClassification
    freshness_reason: str
    is_index_document: bool = False
    significance_score: int
    significance_category: SignificanceCategory
    actionability: ActionabilityClassification
    affected_parties: list[str] = Field(default_factory=list)
    required_action: str | None = None
    action_deadline: str | None = None
    consequence_if_ignored: str | None = None
    deadlines: list[DeadlineIntelligence] = Field(default_factory=list)
    title_quality_score: int
    document_quality_score: int
    date_confidence_score: int
    quality_score: int
    quality_category: EventQualityCategory
    reasons: list[str] = Field(default_factory=list)


class PriorVersionReference(BaseModel):
    document_id: int | None = None
    version_id: int | None = None
    title: str | None = None
    source_url: str | None = None
    content_hash: str | None = None
    text: str | None = None
    similarity_score: float | None = None
    reference_type: Literal["same_url", "related_document", "none"] = "none"


class DeadlineChange(BaseModel):
    deadline_type: DeadlineType
    change: Literal["ADDED", "REMOVED", "EXTENDED", "SHORTENED", "UNCHANGED"]
    old_date: date | None = None
    new_date: date | None = None
    confidence: float
    evidence: str


class RegulatoryChange(BaseModel):
    change_type: ChangeType
    is_material: bool
    confidence: float
    evidence: str
    prior_version_reference: PriorVersionReference | None = None
    previous_state: str | None = None
    new_state: str | None = None
    why_it_matters: str
    affected_parties: list[str] = Field(default_factory=list)
    deadline_changes: list[DeadlineChange] = Field(default_factory=list)
    similarity_score: float | None = None
    reasons: list[str] = Field(default_factory=list)


class DetectResult(BaseModel):
    """Output of detector."""

    document_id: int
    version_id: int
    event_type: EventType
    is_new_event: bool


class SummaryPayload(BaseModel):
    plain_english_summary: str
    why_it_matters: str
    affected_segments: list[str] = Field(default_factory=list)
    important_dates: list[str] = Field(default_factory=list)
    action_required: Literal["none", "monitor", "urgent"] = "monitor"
    confidence: Literal["high", "medium", "low"] = "medium"
    evidence_quotes: list[dict[str, Any]] = Field(default_factory=list)
    deadline_details: list[dict[str, Any]] = Field(default_factory=list)
    intelligence: dict[str, Any] = Field(default_factory=dict)
    change_details: dict[str, Any] = Field(default_factory=dict)


class EventSummary(BaseModel):
    id: int
    title: str
    issuing_body: str | None = None
    jurisdiction: Jurisdiction | None = None
    issue_date: date | None = None
    event_type: EventType
    topic_tags: list[str] = Field(default_factory=list)
    raw_summary: str | None = None
    summary: SummaryPayload | None = None
    source_url: HttpUrl | str
    detected_at: datetime
    is_read: bool = False
    is_bookmarked: bool = False


class DigestResponse(BaseModel):
    digest_date: date
    event_count: int
    events: list[EventSummary]


class ChatRequest(BaseModel):
    message: str = Field(min_length=1, max_length=4000)
    event_id: int | None = None


class ChatResponse(BaseModel):
    reply: str
    event_id: int | None = None
    model: str
    intent: str | None = None
    citations: list[dict[str, Any]] = Field(default_factory=list)
    related_questions: list[str] = Field(default_factory=list)


class SubscriptionSettings(BaseModel):
    jurisdictions: list[Jurisdiction] = Field(default_factory=list)
    source_ids: list[int] = Field(default_factory=list)
    topics: list[str] = Field(default_factory=list)
    email_enabled: bool = True
    frequency: Literal["daily", "instant"] = "daily"


class UserUpdatePayload(BaseModel):
    role: Literal["user", "admin"]


class SourcePayload(BaseModel):
    code: str
    name: str
    jurisdiction: Jurisdiction = "central"
    url: str
    crawler_type: Literal["digest", "agent", "static"] = "agent"
    allowed_domains: list[str] = Field(default_factory=list)
    hint: str | None = None
    enabled: bool = True


class SourceUpdatePayload(BaseModel):
    code: str | None = None
    name: str | None = None
    jurisdiction: Jurisdiction | None = None
    url: str | None = None
    crawler_type: Literal["digest", "agent", "static"] | None = None
    allowed_domains: list[str] | None = None
    hint: str | None = None
    enabled: bool | None = None


class SourcePagePayload(BaseModel):
    name: str
    url: str
    page_type: str
    priority: int = 100
    enabled: bool = True


class SourcePageUpdatePayload(BaseModel):
    name: str | None = None
    url: str | None = None
    page_type: str | None = None
    priority: int | None = None
    enabled: bool | None = None


class CrawlTriggerResponse(BaseModel):
    status: str
    sources_attempted: int
    pages_attempted: int
    sources_succeeded: int
    pages_succeeded: int
    docs_found: int
    primary_docs_found: int
    new_events: int
    checkpoints_advanced: int = 0
    notification_message_id: str | None = None
    errors: list[dict[str, Any]] = Field(default_factory=list)


class SourceAnalyticsResponse(BaseModel):
    source: dict[str, Any]
    pages_total: int
    pages_enabled: int
    documents_total: int
    events_total: int
    discovery_candidates: int
    discovery_accepted: int
    discovery_rejected: int
    rejection_reasons: dict[str, int] = Field(default_factory=dict)
    classifications: dict[str, int] = Field(default_factory=dict)
    latest_run: dict[str, Any] | None = None


class IntelligenceDeadline(BaseModel):
    document_id: int
    title: str
    issuer: str | None = None
    deadline_type: str
    deadline_date: date | None = None
    raw_date: str | None = None
    days_remaining: int | None = None
    stakeholders_affected: list[str] = Field(default_factory=list)
    source_url: str
    confidence: float
    evidence: str | None = None


class IntelligenceObligation(BaseModel):
    document_id: int
    title: str
    issuer: str | None = None
    obligation: str
    stakeholder: str
    deadline_date: date | None = None
    deadline_type: str | None = None
    confidence: float
    evidence: str | None = None
    source_url: str


class StakeholderObligationGroup(BaseModel):
    stakeholder: str
    obligations: list[IntelligenceObligation] = Field(default_factory=list)


class IntelligenceDocumentRef(BaseModel):
    document_id: int
    title: str
    issuer: str | None = None
    source_url: str
    document_type: str
    confidence: float = 0.0
    evidence: str | None = None


class StakeholderIntelligence(BaseModel):
    stakeholder: str
    impact_summary: str
    compliance_summary: str
    action_summary: str
    regulations: list[IntelligenceDocumentRef] = Field(default_factory=list)
    consultations: list[IntelligenceDocumentRef] = Field(default_factory=list)
    obligations: list[IntelligenceObligation] = Field(default_factory=list)
    deadlines: list[IntelligenceDeadline] = Field(default_factory=list)
    tenders: list[IntelligenceDocumentRef] = Field(default_factory=list)
    counts: dict[str, int] = Field(default_factory=dict)


class IntelligenceReadinessReport(BaseModel):
    active_deadlines: list[IntelligenceDeadline] = Field(default_factory=list)
    stakeholder_obligations: list[StakeholderObligationGroup] = Field(default_factory=list)
    regulatory_impacts: list[StakeholderIntelligence] = Field(default_factory=list)
    consultation_tracking: list[IntelligenceDocumentRef] = Field(default_factory=list)
    status: str
    notes: list[str] = Field(default_factory=list)
