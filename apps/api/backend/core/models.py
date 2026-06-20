from datetime import date, datetime
from typing import Any, Literal

from pydantic import BaseModel, Field, HttpUrl

DatePrecision = Literal["day", "month", "year", "unknown"]
Jurisdiction = Literal["central", "state"]
EventType = Literal["NEW", "CHANGED", "REPLACEMENT", "DUPLICATE"]


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


class FetchedFile(BaseModel):
    """Output of downloader."""

    discovered: DiscoveredDoc
    file_hash: str
    raw_file_path: str
    http_status: int
    etag: str | None = None
    last_modified: str | None = None


class ExtractedDoc(BaseModel):
    """Output of extractor."""

    fetched: FetchedFile
    text: str
    content_hash: str
    page_count: int
    needs_ocr: bool
    text_path: str


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


class SubscriptionSettings(BaseModel):
    jurisdictions: list[Jurisdiction] = Field(default_factory=list)
    source_ids: list[int] = Field(default_factory=list)
    topics: list[str] = Field(default_factory=list)
    email_enabled: bool = True
    frequency: Literal["daily", "instant"] = "daily"
