from __future__ import annotations

import asyncio
import hashlib
import ipaddress
import json
from collections.abc import Awaitable, Callable, Mapping
from datetime import UTC, datetime, time, timedelta
from enum import StrEnum
from types import MappingProxyType
from typing import Literal, Protocol, Self
from urllib.parse import parse_qsl, urlsplit
from zoneinfo import ZoneInfo, ZoneInfoNotFoundError

from pydantic import BaseModel, ConfigDict, Field, field_validator, model_validator

from backend.ask.decision.models import ConfidenceLabel
from backend.ask.orchestration.contracts import (
    ArtifactEnvelope,
    ArtifactProducer,
    CapabilityScope,
    CapabilityTerminalState,
    ConfidenceSignals,
    ContentDerivation,
    EvidenceUnitPayload,
    KnowledgeMode,
    ProvenanceClass,
    ProvenanceLineage,
    SourceIdentity,
    VerificationStatus,
)

LIVE_INTELLIGENCE_SCHEMA_VERSION = "1"
LIVE_INTELLIGENCE_POLICY_VERSION = "ask-ai-live-intelligence-v1"
LIVE_INTELLIGENCE_APPROVAL_ID = "RAA-B005-2026-001"
LIVE_SECTION_DISCLOSURE = (
    "Live sources provide current context and do not by themselves establish "
    "legal force or applicability."
)
MAX_LIVE_ITEMS_PER_PROVIDER = 100
MAX_LIVE_EXCERPT_CHARS = 500
MAX_LIVE_PROVIDER_RESPONSE_CHARS = 1_000_000
MAX_LIVE_BRANCHES = 8
MAX_USER_SEARCHES_PER_MINUTE = 10
MAX_USER_BURST = 3
_NON_RETRYABLE_PROVIDER_CODES = frozenset(
    {
        "LIVE_PROVIDER_AUTH_FAILED",
        "LIVE_PROVIDER_ENTITLEMENT_FAILED",
        "LIVE_PROVIDER_ROBOTS_DENIED",
        "LIVE_PROVIDER_PERMANENT_FAILURE",
        "LIVE_PROVIDER_RATE_LIMITED",
    }
)

APPROVED_OFFICIAL_PUBLISHERS: Mapping[str, str] = MappingProxyType(
    {
        "egazette.nic.in": "Gazette of India",
        "powermin.gov.in": "Ministry of Power",
        "cercind.gov.in": "Central Electricity Regulatory Commission",
        "cea.nic.in": "Central Electricity Authority",
        "mnre.gov.in": "Ministry of New and Renewable Energy",
        "pib.gov.in": "Press Information Bureau",
        "seci.co.in": "Solar Energy Corporation of India",
        "grid-india.in": "Grid Controller of India",
    }
)


class LiveProviderFamily(StrEnum):
    OFFICIAL_DIRECT = "official_direct"
    PARALLEL_SOURCE_RETAINING = "parallel_source_retaining"
    REUTERS = "reuters"
    DOW_JONES_FACTIVA = "dow_jones_factiva"


class LiveProviderClass(StrEnum):
    OFFICIAL_DIRECT = "official_direct"
    SOURCE_RETAINING_RESEARCH = "source_retaining_research"
    LICENSED_COMMERCIAL_NEWS = "licensed_commercial_news"


class LiveSourceType(StrEnum):
    OPERATIVE_OFFICIAL = "operative_official"
    OFFICIAL_CURRENT_NOTICE = "official_current_notice"
    OFFICIAL_DRAFT_OR_CONSULTATION = "official_draft_or_consultation"
    LICENSED_NEWS = "licensed_news"
    ESTABLISHED_PRESS = "established_press"
    INDUSTRY_ANNOUNCEMENT = "industry_announcement"


class LiveTrustRank(StrEnum):
    L1 = "L1"
    L2 = "L2"
    L3 = "L3"
    L4 = "L4"
    L5 = "L5"


class LiveLicenseClass(StrEnum):
    OFFICIAL_PUBLIC = "official_public"
    ENTERPRISE_LICENSED = "enterprise_licensed"
    FIRST_PARTY_PUBLIC = "first_party_public"


class LiveEntitlementState(StrEnum):
    ACTIVE = "active"
    UNCLEAR = "unclear"
    EXPIRED = "expired"
    REVOKED = "revoked"


class LiveRetentionMode(StrEnum):
    METADATA_ONLY = "metadata_only"
    EXCERPT = "excerpt"
    FULL_TEXT = "full_text"


class LiveWindowKind(StrEnum):
    TODAY = "today"
    BREAKING = "breaking"
    NEWS = "news"
    RECENT = "recent"
    BOUNDED = "bounded"
    OPEN_CONSULTATION = "open_consultation"
    RECENTLY_CLOSED_CONSULTATION = "recently_closed_consultation"


class LiveProviderState(StrEnum):
    SATISFIED = "satisfied"
    NO_MATCH = "no_match"
    TIMED_OUT = "timed_out"
    UNAVAILABLE = "unavailable"
    INVALID_OUTPUT = "invalid_output"


class LiveAdmissionReason(StrEnum):
    PROVIDER_NOT_APPROVED = "provider_not_approved"
    PROVIDER_IDENTITY_MISMATCH = "provider_identity_mismatch"
    CONNECTOR_SECURITY_INVALID = "connector_security_invalid"
    ENTITLEMENT_INACTIVE = "entitlement_inactive"
    REGISTRY_ENTRY_INACTIVE = "registry_entry_inactive"
    SOURCE_NOT_APPROVED = "source_not_approved"
    SOURCE_TYPE_NOT_APPROVED = "source_type_not_approved"
    LICENSE_MISMATCH = "license_mismatch"
    URL_NOT_ADMISSIBLE = "url_not_admissible"
    PUBLISHER_MISMATCH = "publisher_mismatch"
    PUBLICATION_TIME_MISSING = "publication_time_missing"
    PUBLICATION_TIME_IN_FUTURE = "publication_time_in_future"
    OUTSIDE_TIME_WINDOW = "outside_time_window"
    CONSULTATION_STATUS_MISMATCH = "consultation_status_mismatch"
    RETRIEVAL_TIME_INVALID = "retrieval_time_invalid"
    CONTENT_HASH_MISMATCH = "content_hash_mismatch"
    RETENTION_NOT_PERMITTED = "retention_not_permitted"
    DUPLICATE = "duplicate"


class LiveModel(BaseModel):
    model_config = ConfigDict(
        extra="forbid",
        frozen=True,
        strict=True,
        str_strip_whitespace=True,
    )


class LiveRegistryEntry(LiveModel):
    entry_id: str = Field(min_length=1, max_length=200)
    exact_host: str = Field(min_length=1, max_length=253)
    publisher: str = Field(min_length=1, max_length=300)
    jurisdiction: str | None = Field(default=None, max_length=200)
    allowed_source_types: tuple[LiveSourceType, ...] = Field(min_length=1)
    allowed_provider_families: tuple[LiveProviderFamily, ...] = Field(min_length=1)
    license_class: LiveLicenseClass
    active: bool = True

    @field_validator("exact_host")
    @classmethod
    def normalize_host(cls, value: str) -> str:
        host = value.strip().rstrip(".").lower()
        if not host or "://" in host or "/" in host or "@" in host:
            raise ValueError("Registry host must be one exact hostname")
        _reject_ip_or_local_host(host)
        return host

    @model_validator(mode="after")
    def validate_entry(self) -> Self:
        if len(set(self.allowed_source_types)) != len(self.allowed_source_types):
            raise ValueError("Registry source types must be unique")
        if len(set(self.allowed_provider_families)) != len(
            self.allowed_provider_families
        ):
            raise ValueError("Registry provider families must be unique")
        if self.license_class is LiveLicenseClass.OFFICIAL_PUBLIC and any(
            item
            not in {
                LiveSourceType.OPERATIVE_OFFICIAL,
                LiveSourceType.OFFICIAL_CURRENT_NOTICE,
                LiveSourceType.OFFICIAL_DRAFT_OR_CONSULTATION,
            }
            for item in self.allowed_source_types
        ):
            raise ValueError("Official registry entries require official source types")
        return self


class LiveProviderApproval(LiveModel):
    provider_id: str = Field(min_length=1, max_length=200)
    family: LiveProviderFamily
    provider_class: LiveProviderClass
    entitlement_state: LiveEntitlementState
    retention_mode: LiveRetentionMode
    attribution_text: str = Field(min_length=1, max_length=500)
    allowed_registry_entry_ids: tuple[str, ...] = Field(min_length=1)
    max_requests_per_second: int = Field(ge=1, le=10)
    max_concurrency: int = Field(ge=1, le=20)
    enabled: bool = False

    @model_validator(mode="after")
    def validate_provider_limits(self) -> Self:
        if len(set(self.allowed_registry_entry_ids)) != len(
            self.allowed_registry_entry_ids
        ):
            raise ValueError("Provider registry entries must be unique")
        expected_class = {
            LiveProviderFamily.OFFICIAL_DIRECT: LiveProviderClass.OFFICIAL_DIRECT,
            LiveProviderFamily.PARALLEL_SOURCE_RETAINING: (
                LiveProviderClass.SOURCE_RETAINING_RESEARCH
            ),
            LiveProviderFamily.REUTERS: LiveProviderClass.LICENSED_COMMERCIAL_NEWS,
            LiveProviderFamily.DOW_JONES_FACTIVA: (
                LiveProviderClass.LICENSED_COMMERCIAL_NEWS
            ),
        }[self.family]
        if self.provider_class is not expected_class:
            raise ValueError("Provider family and class do not agree")
        if self.family is LiveProviderFamily.OFFICIAL_DIRECT:
            if self.max_requests_per_second > 5 or self.max_concurrency > 10:
                raise ValueError("Official provider exceeds B-005 host limits")
            if self.retention_mode is not LiveRetentionMode.EXCERPT:
                raise ValueError("Official direct retrieval retains bounded excerpts")
        elif self.provider_class is LiveProviderClass.LICENSED_COMMERCIAL_NEWS:
            if self.retention_mode is LiveRetentionMode.FULL_TEXT:
                raise ValueError("Commercial full-text retention requires a new approval")
        return self


class LivePolicySnapshot(LiveModel):
    schema_version: Literal["1"] = LIVE_INTELLIGENCE_SCHEMA_VERSION
    policy_version: Literal["ask-ai-live-intelligence-v1"] = (
        LIVE_INTELLIGENCE_POLICY_VERSION
    )
    approval_id: Literal["RAA-B005-2026-001"] = LIVE_INTELLIGENCE_APPROVAL_ID
    registry_version: str = Field(min_length=1, max_length=200)
    entitlement_version: str = Field(min_length=1, max_length=200)
    registry_entries: tuple[LiveRegistryEntry, ...] = Field(min_length=1)
    providers: tuple[LiveProviderApproval, ...] = Field(min_length=1)

    @model_validator(mode="after")
    def validate_snapshot(self) -> Self:
        entries = {item.entry_id: item for item in self.registry_entries}
        if len(entries) != len(self.registry_entries):
            raise ValueError("Registry entry IDs must be unique")
        provider_ids = {item.provider_id for item in self.providers}
        if len(provider_ids) != len(self.providers):
            raise ValueError("Provider IDs must be unique")
        for provider in self.providers:
            for entry_id in provider.allowed_registry_entry_ids:
                entry = entries.get(entry_id)
                if entry is None:
                    raise ValueError("Provider references an unknown registry entry")
                if provider.family not in entry.allowed_provider_families:
                    raise ValueError("Provider family is not approved for registry entry")
        return self

    def registry(self) -> Mapping[str, LiveRegistryEntry]:
        return MappingProxyType({item.entry_id: item for item in self.registry_entries})

    def provider_registry(self) -> Mapping[str, LiveProviderApproval]:
        return MappingProxyType({item.provider_id: item for item in self.providers})


class LiveTimeWindow(LiveModel):
    kind: LiveWindowKind
    user_timezone: str = "Asia/Kolkata"
    start_at: datetime | None = None
    end_at: datetime | None = None

    @model_validator(mode="after")
    def validate_window(self) -> Self:
        try:
            ZoneInfo(self.user_timezone)
        except ZoneInfoNotFoundError as exc:
            raise ValueError("Live window requires an IANA timezone") from exc
        if any(
            value is not None and value.utcoffset() is None
            for value in (self.start_at, self.end_at)
        ):
            raise ValueError("Live window boundaries must be timezone-aware")
        if self.kind is LiveWindowKind.BOUNDED:
            if self.start_at is None or self.end_at is None:
                raise ValueError("Bounded live windows require both boundaries")
            if self.end_at <= self.start_at:
                raise ValueError("Bounded live window is empty or reversed")
        elif self.start_at is not None or self.end_at is not None:
            raise ValueError("Named live windows derive their own boundaries")
        return self


class LiveRetrievalRequest(LiveModel):
    schema_version: Literal["1"] = LIVE_INTELLIGENCE_SCHEMA_VERSION
    policy: LivePolicySnapshot
    query: str = Field(min_length=1, max_length=20_000)
    scope: CapabilityScope
    window: LiveTimeWindow
    now: datetime
    selected_provider_ids: tuple[str, ...] = Field(min_length=1, max_length=8)
    user_searches_last_minute: int = Field(default=0, ge=0)
    user_burst_in_flight: int = Field(default=0, ge=0)
    timeout_ms: int = Field(default=8_000, ge=1, le=30_000)

    @field_validator("query")
    @classmethod
    def normalize_query(cls, value: str) -> str:
        normalized = value.strip()
        if not normalized:
            raise ValueError("Live query cannot be blank")
        return normalized

    @model_validator(mode="after")
    def validate_request(self) -> Self:
        if self.now.utcoffset() is None:
            raise ValueError("Live execution clock must be timezone-aware")
        if len(set(self.selected_provider_ids)) != len(self.selected_provider_ids):
            raise ValueError("Selected live providers must be unique")
        approved = self.policy.provider_registry()
        if any(item not in approved for item in self.selected_provider_ids):
            raise ValueError("Selected live provider is not in the policy snapshot")
        return self


class LiveProviderItem(LiveModel):
    evidence_id: str = Field(min_length=1, max_length=500)
    registry_entry_id: str = Field(min_length=1, max_length=200)
    canonical_url: str = Field(min_length=1, max_length=4_000)
    original_url: str = Field(min_length=1, max_length=4_000)
    publisher: str = Field(min_length=1, max_length=300)
    title: str = Field(min_length=1, max_length=1_000)
    source_type: LiveSourceType
    license_class: LiveLicenseClass
    publication_at: datetime | None = None
    publication_time_unavailable: bool = False
    retrieved_at: datetime
    consultation_closes_at: datetime | None = None
    excerpt: str = Field(min_length=1, max_length=MAX_LIVE_EXCERPT_CHARS)
    content_sha256: str = Field(pattern=r"^[0-9a-f]{64}$")
    event_fingerprint: str | None = Field(default=None, max_length=500)
    byline: str | None = Field(default=None, max_length=300)

    @model_validator(mode="after")
    def validate_item(self) -> Self:
        timestamps = (
            self.publication_at,
            self.retrieved_at,
            self.consultation_closes_at,
        )
        if any(value is not None and value.utcoffset() is None for value in timestamps):
            raise ValueError("Live timestamps must be timezone-aware")
        if (self.publication_at is None) == (not self.publication_time_unavailable):
            raise ValueError("Publication time requires one explicit known/unknown state")
        return self


class LiveProviderPayload(LiveModel):
    schema_version: Literal["1"] = LIVE_INTELLIGENCE_SCHEMA_VERSION
    provider_id: str = Field(min_length=1, max_length=200)
    state: LiveProviderState
    items: tuple[LiveProviderItem, ...] = Field(max_length=MAX_LIVE_ITEMS_PER_PROVIDER)
    safe_code: str | None = Field(
        default=None,
        pattern=r"^[A-Z][A-Z0-9_]{0,99}$",
    )

    @model_validator(mode="after")
    def validate_payload(self) -> Self:
        if self.state is LiveProviderState.SATISFIED:
            if not self.items or self.safe_code is not None:
                raise ValueError("Satisfied live provider output requires items only")
        elif self.state is LiveProviderState.NO_MATCH:
            if self.items or self.safe_code is not None:
                raise ValueError("Healthy no-match contains no items or error")
        elif self.items or self.safe_code is None:
            raise ValueError("Failed live provider output requires one safe code")
        ids = tuple(item.evidence_id for item in self.items)
        if len(set(ids)) != len(ids):
            raise ValueError("Provider evidence identities must be unique")
        return self


class LiveConnectorSecurityProfile(LiveModel):
    tls_certificate_validation: Literal[True] = True
    dns_reresolution_before_connect: Literal[True] = True
    robots_enforcement: Literal[True] = True
    safe_text_extraction: Literal[True] = True
    access_control_bypass: Literal[False] = False
    max_response_bytes: int = Field(default=2_000_000, ge=1, le=2_000_000)
    max_redirects: int = Field(default=5, ge=0, le=5)
    connect_timeout_ms: int = Field(default=3_000, ge=1, le=3_000)
    hard_timeout_ms: int = Field(default=8_000, ge=1, le=30_000)
    allowed_content_types: tuple[str, ...] = (
        "text/html",
        "text/plain",
        "application/json",
        "application/rss+xml",
        "application/atom+xml",
    )

    @field_validator("allowed_content_types")
    @classmethod
    def validate_content_types(cls, value: tuple[str, ...]) -> tuple[str, ...]:
        approved = {
            "text/html",
            "text/plain",
            "application/json",
            "application/rss+xml",
            "application/atom+xml",
        }
        if not value or len(set(value)) != len(value) or not set(value) <= approved:
            raise ValueError("Connector content types must use the approved allowlist")
        return value


class LiveConnector(Protocol):
    provider_id: str
    family: LiveProviderFamily
    security_profile: LiveConnectorSecurityProfile

    async def retrieve(self, request: LiveRetrievalRequest) -> str: ...


class LiveRejectedItem(LiveModel):
    provider_id: str
    evidence_id: str | None
    reason: LiveAdmissionReason


class LiveProviderOutcome(LiveModel):
    provider_id: str
    state: LiveProviderState
    attempts: int = Field(ge=0, le=3)
    admitted_count: int = Field(ge=0)
    rejected_count: int = Field(ge=0)
    safe_code: str | None = None


class LiveAdmittedEvidence(LiveModel):
    evidence_id: str
    provider_id: str
    provider_family: LiveProviderFamily
    registry_entry_id: str
    trust_rank: LiveTrustRank
    confidence_ceiling: ConfidenceLabel
    ui_badge: str
    license_class: LiveLicenseClass
    canonical_url: str
    original_url: str
    publisher: str
    title: str
    source_type: LiveSourceType
    content_sha256: str = Field(pattern=r"^[0-9a-f]{64}$")
    publication_at: datetime
    retrieved_at: datetime
    event_fingerprint: str | None
    artifact: ArtifactEnvelope
    duplicate_source_ids: tuple[str, ...] = ()


class LiveCapabilityResult(LiveModel):
    schema_version: Literal["1"] = LIVE_INTELLIGENCE_SCHEMA_VERSION
    policy_version: Literal["ask-ai-live-intelligence-v1"] = (
        LIVE_INTELLIGENCE_POLICY_VERSION
    )
    approval_id: Literal["RAA-B005-2026-001"] = LIVE_INTELLIGENCE_APPROVAL_ID
    registry_version: str
    entitlement_version: str
    state: CapabilityTerminalState
    evidence: tuple[LiveAdmittedEvidence, ...] = ()
    rejected: tuple[LiveRejectedItem, ...] = ()
    provider_outcomes: tuple[LiveProviderOutcome, ...] = ()
    disclosure: str | None = None
    safe_code: str | None = None

    @model_validator(mode="after")
    def validate_result(self) -> Self:
        has_evidence = bool(self.evidence)
        if has_evidence:
            if self.state not in {
                CapabilityTerminalState.SATISFIED,
                CapabilityTerminalState.PARTIAL,
            }:
                raise ValueError("Live evidence requires Satisfied or Partial")
            if self.disclosure != LIVE_SECTION_DISCLOSURE or self.safe_code is not None:
                raise ValueError("Live evidence requires exact disclosure only")
        else:
            if self.state in {
                CapabilityTerminalState.SATISFIED,
                CapabilityTerminalState.PARTIAL,
            }:
                raise ValueError("Live success requires admitted evidence")
            if self.disclosure is not None:
                raise ValueError("Empty live results do not create a source section")
            if self.state is CapabilityTerminalState.NO_MATCH:
                if self.safe_code is not None:
                    raise ValueError("Healthy live no-match is not a failure")
            elif self.safe_code is None:
                raise ValueError("Failed live execution requires a safe code")
        return self


class LiveCacheRecord(LiveModel):
    cache_key: str = Field(pattern=r"^[0-9a-f]{64}$")
    stored_at: datetime
    expires_at: datetime
    result: LiveCapabilityResult

    @model_validator(mode="after")
    def validate_record(self) -> Self:
        if self.stored_at.utcoffset() is None or self.expires_at.utcoffset() is None:
            raise ValueError("Live cache timestamps must be timezone-aware")
        if self.expires_at <= self.stored_at:
            raise ValueError("Live cache expiry must follow storage")
        return self


RetrySleeper = Callable[[float], Awaitable[None]]


def default_live_policy_snapshot(
    *,
    registry_version: str = "b005-official-registry-v1",
    entitlement_version: str = "b005-entitlements-v1",
    enable_official_direct: bool = False,
    enable_parallel: bool = False,
) -> LivePolicySnapshot:
    entries = tuple(
        LiveRegistryEntry(
            entry_id=f"official:{host}",
            exact_host=host,
            publisher=publisher,
            jurisdiction="India",
            allowed_source_types=(
                LiveSourceType.OPERATIVE_OFFICIAL,
                LiveSourceType.OFFICIAL_CURRENT_NOTICE,
                LiveSourceType.OFFICIAL_DRAFT_OR_CONSULTATION,
            ),
            allowed_provider_families=(
                LiveProviderFamily.OFFICIAL_DIRECT,
                LiveProviderFamily.PARALLEL_SOURCE_RETAINING,
            ),
            license_class=LiveLicenseClass.OFFICIAL_PUBLIC,
        )
        for host, publisher in APPROVED_OFFICIAL_PUBLISHERS.items()
    )
    entry_ids = tuple(item.entry_id for item in entries)
    return LivePolicySnapshot(
        registry_version=registry_version,
        entitlement_version=entitlement_version,
        registry_entries=entries,
        providers=(
            LiveProviderApproval(
                provider_id="official-direct",
                family=LiveProviderFamily.OFFICIAL_DIRECT,
                provider_class=LiveProviderClass.OFFICIAL_DIRECT,
                entitlement_state=LiveEntitlementState.ACTIVE,
                retention_mode=LiveRetentionMode.EXCERPT,
                attribution_text="Official publisher",
                allowed_registry_entry_ids=entry_ids,
                max_requests_per_second=5,
                max_concurrency=10,
                enabled=enable_official_direct,
            ),
            LiveProviderApproval(
                provider_id="parallel-live",
                family=LiveProviderFamily.PARALLEL_SOURCE_RETAINING,
                provider_class=LiveProviderClass.SOURCE_RETAINING_RESEARCH,
                entitlement_state=(
                    LiveEntitlementState.ACTIVE
                    if enable_parallel
                    else LiveEntitlementState.UNCLEAR
                ),
                retention_mode=LiveRetentionMode.EXCERPT,
                attribution_text="Source-retaining retrieval via Parallel.ai",
                allowed_registry_entry_ids=entry_ids,
                max_requests_per_second=10,
                max_concurrency=20,
                enabled=enable_parallel,
            ),
        ),
    )


async def execute_live_intelligence(
    request: LiveRetrievalRequest,
    *,
    connectors: Mapping[str, LiveConnector],
    retry_sleeper: RetrySleeper = asyncio.sleep,
) -> LiveCapabilityResult:
    try:
        request = LiveRetrievalRequest.model_validate_json(
            request.model_dump_json()
        )
    except (TypeError, ValueError):
        policy = getattr(request, "policy", None)
        return LiveCapabilityResult(
            registry_version=(
                policy.registry_version
                if isinstance(policy, LivePolicySnapshot)
                else "invalid-registry"
            ),
            entitlement_version=(
                policy.entitlement_version
                if isinstance(policy, LivePolicySnapshot)
                else "invalid-entitlement"
            ),
            state=CapabilityTerminalState.INVALID_OUTPUT,
            safe_code="LIVE_REQUEST_INVALID",
        )
    if (
        request.user_searches_last_minute >= MAX_USER_SEARCHES_PER_MINUTE
        or request.user_burst_in_flight >= MAX_USER_BURST
    ):
        return _empty_result(
            request.policy,
            CapabilityTerminalState.UNAVAILABLE,
            "LIVE_RATE_LIMITED",
        )
    approvals = request.policy.provider_registry()
    selected: list[tuple[LiveProviderApproval, LiveConnector]] = []
    preflight_outcomes: list[LiveProviderOutcome] = []
    preflight_rejections: list[LiveRejectedItem] = []
    for provider_id in request.selected_provider_ids:
        approval = approvals[provider_id]
        connector = connectors.get(provider_id)
        if connector is None or not approval.enabled:
            preflight_outcomes.append(
                _provider_failure(provider_id, "LIVE_PROVIDER_DISABLED")
            )
            continue
        if approval.entitlement_state is not LiveEntitlementState.ACTIVE:
            preflight_outcomes.append(
                _provider_failure(provider_id, "LIVE_ENTITLEMENT_INACTIVE")
            )
            preflight_rejections.append(
                LiveRejectedItem(
                    provider_id=provider_id,
                    evidence_id=None,
                    reason=LiveAdmissionReason.ENTITLEMENT_INACTIVE,
                )
            )
            continue
        try:
            identity_matches = (
                connector.provider_id == provider_id
                and connector.family is approval.family
            )
        except Exception:
            identity_matches = False
        if not identity_matches:
            preflight_outcomes.append(
                _provider_failure(provider_id, "LIVE_PROVIDER_IDENTITY_INVALID")
            )
            preflight_rejections.append(
                LiveRejectedItem(
                    provider_id=provider_id,
                    evidence_id=None,
                    reason=LiveAdmissionReason.PROVIDER_IDENTITY_MISMATCH,
                )
            )
            continue
        try:
            LiveConnectorSecurityProfile.model_validate_json(
                connector.security_profile.model_dump_json()
            )
        except (AttributeError, TypeError, ValueError):
            preflight_outcomes.append(
                _provider_failure(provider_id, "LIVE_CONNECTOR_SECURITY_INVALID")
            )
            preflight_rejections.append(
                LiveRejectedItem(
                    provider_id=provider_id,
                    evidence_id=None,
                    reason=LiveAdmissionReason.CONNECTOR_SECURITY_INVALID,
                )
            )
            continue
        selected.append((approval, connector))

    runs = await asyncio.gather(
        *(
            _run_connector(
                request,
                approval,
                connector,
                retry_sleeper=retry_sleeper,
            )
            for approval, connector in selected
        )
    )
    registry = request.policy.registry()
    admitted: list[LiveAdmittedEvidence] = []
    rejected = list(preflight_rejections)
    outcomes = list(preflight_outcomes)
    for approval, payload, attempts in runs:
        if payload.state is not LiveProviderState.SATISFIED:
            outcomes.append(
                LiveProviderOutcome(
                    provider_id=approval.provider_id,
                    state=payload.state,
                    attempts=attempts,
                    admitted_count=0,
                    rejected_count=0,
                    safe_code=payload.safe_code,
                )
            )
            continue
        provider_admitted = 0
        provider_rejected = 0
        for item in payload.items:
            reason = _admission_failure(request, approval, registry, item)
            if reason is not None:
                provider_rejected += 1
                rejected.append(
                    LiveRejectedItem(
                        provider_id=approval.provider_id,
                        evidence_id=item.evidence_id,
                        reason=reason,
                    )
                )
                continue
            admitted.append(_admit(request, approval, registry[item.registry_entry_id], item))
            provider_admitted += 1
        outcomes.append(
            LiveProviderOutcome(
                provider_id=approval.provider_id,
                state=(
                    LiveProviderState.SATISFIED
                    if provider_admitted
                    else LiveProviderState.INVALID_OUTPUT
                ),
                attempts=attempts,
                admitted_count=provider_admitted,
                rejected_count=provider_rejected,
                safe_code=(None if provider_admitted else "LIVE_ITEMS_REJECTED"),
            )
        )

    deduplicated, duplicate_rejections = _deduplicate(admitted)
    rejected.extend(duplicate_rejections)
    if deduplicated:
        degraded = any(
            item.state
            not in {LiveProviderState.SATISFIED, LiveProviderState.NO_MATCH}
            or item.rejected_count
            for item in outcomes
        )
        return LiveCapabilityResult(
            registry_version=request.policy.registry_version,
            entitlement_version=request.policy.entitlement_version,
            state=(
                CapabilityTerminalState.PARTIAL
                if degraded
                else CapabilityTerminalState.SATISFIED
            ),
            evidence=tuple(deduplicated),
            rejected=tuple(rejected),
            provider_outcomes=tuple(outcomes),
            disclosure=LIVE_SECTION_DISCLOSURE,
        )
    if outcomes and all(item.state is LiveProviderState.NO_MATCH for item in outcomes):
        terminal = CapabilityTerminalState.NO_MATCH
        code = None
    elif outcomes and all(item.state is LiveProviderState.TIMED_OUT for item in outcomes):
        terminal = CapabilityTerminalState.TIMED_OUT
        code = "LIVE_ALL_PROVIDERS_TIMED_OUT"
    elif any(item.state is LiveProviderState.INVALID_OUTPUT for item in outcomes):
        terminal = CapabilityTerminalState.INVALID_OUTPUT
        code = "LIVE_OUTPUT_INVALID"
    else:
        terminal = CapabilityTerminalState.UNAVAILABLE
        code = "LIVE_PROVIDERS_UNAVAILABLE"
    return LiveCapabilityResult(
        registry_version=request.policy.registry_version,
        entitlement_version=request.policy.entitlement_version,
        state=terminal,
        rejected=tuple(rejected),
        provider_outcomes=tuple(outcomes),
        safe_code=code,
    )


def live_cache_key(request: LiveRetrievalRequest) -> str:
    payload = {
        "provider_ids": request.selected_provider_ids,
        "query": " ".join(request.query.casefold().split()),
        "window": request.window.model_dump(mode="json"),
        "jurisdiction": request.scope.jurisdiction,
        "registry_version": request.policy.registry_version,
        "entitlement_version": request.policy.entitlement_version,
        "policy_version": request.policy.policy_version,
    }
    encoded = json.dumps(
        payload,
        ensure_ascii=False,
        separators=(",", ":"),
        sort_keys=True,
    ).encode("utf-8")
    return hashlib.sha256(encoded).hexdigest()


def live_cache_ttl_seconds(
    *,
    rank: LiveTrustRank | None = None,
    state: CapabilityTerminalState | None = None,
    historical_context: bool = False,
) -> int:
    if historical_context:
        return 86_400
    if state is CapabilityTerminalState.NO_MATCH:
        return 300
    if state in {
        CapabilityTerminalState.UNAVAILABLE,
        CapabilityTerminalState.TIMED_OUT,
        CapabilityTerminalState.INVALID_OUTPUT,
    }:
        return 30
    if rank in {LiveTrustRank.L3, LiveTrustRank.L4}:
        return 600
    return 900


def stale_cache_allowed(
    record: LiveCacheRecord,
    *,
    request: LiveRetrievalRequest,
) -> bool:
    return (
        record.expires_at < request.now
        and bool(record.result.evidence)
        and request.window.kind
        not in {LiveWindowKind.TODAY, LiveWindowKind.BREAKING}
    )


def stale_cache_fallback(
    record: LiveCacheRecord,
    *,
    request: LiveRetrievalRequest,
) -> LiveCapabilityResult | None:
    if not stale_cache_allowed(record, request=request):
        return None
    stale_evidence = tuple(
        item.model_copy(
            update={
                "confidence_ceiling": ConfidenceLabel.LOW,
                "ui_badge": "Stale cached live source",
                "artifact": item.artifact.model_copy(
                    update={
                        "confidence_signals": item.artifact.confidence_signals.model_copy(
                            update={
                                "critical_input_ceiling": 0.5,
                                "freshness_validity": 0.0,
                                "reasons": ("LIVE_STALE_CACHE",),
                            }
                        )
                        if item.artifact.confidence_signals is not None
                        else None,
                        "warnings": tuple(
                            dict.fromkeys(
                                (*item.artifact.warnings, "STALE_CACHED_LIVE_SOURCE")
                            )
                        ),
                    }
                ),
            }
        )
        for item in record.result.evidence
    )
    fallback = record.result.model_copy(
        update={
            "state": CapabilityTerminalState.PARTIAL,
            "evidence": stale_evidence,
            "provider_outcomes": tuple(
                item.model_copy(update={"safe_code": "LIVE_STALE_CACHE_FALLBACK"})
                for item in record.result.provider_outcomes
            ),
        }
    )
    return LiveCapabilityResult.model_validate_json(fallback.model_dump_json())


def live_result_json(result: LiveCapabilityResult) -> str:
    return json.dumps(
        result.model_dump(mode="json"),
        ensure_ascii=False,
        separators=(",", ":"),
        sort_keys=True,
    )


async def _run_connector(
    request: LiveRetrievalRequest,
    approval: LiveProviderApproval,
    connector: LiveConnector,
    *,
    retry_sleeper: RetrySleeper,
) -> tuple[LiveProviderApproval, LiveProviderPayload, int]:
    for attempt in range(1, 4):
        try:
            raw = await asyncio.wait_for(
                connector.retrieve(request),
                timeout=request.timeout_ms / 1000,
            )
            if not isinstance(raw, str) or len(raw) > MAX_LIVE_PROVIDER_RESPONSE_CHARS:
                payload = _failed_payload(
                    approval.provider_id,
                    LiveProviderState.INVALID_OUTPUT,
                    "LIVE_PROVIDER_OUTPUT_INVALID",
                )
            else:
                try:
                    payload = LiveProviderPayload.model_validate_json(raw)
                except (TypeError, ValueError):
                    payload = _failed_payload(
                        approval.provider_id,
                        LiveProviderState.INVALID_OUTPUT,
                        "LIVE_PROVIDER_OUTPUT_INVALID",
                    )
            if payload.provider_id != approval.provider_id:
                return (
                    approval,
                    _failed_payload(
                        approval.provider_id,
                        LiveProviderState.INVALID_OUTPUT,
                        "LIVE_PROVIDER_IDENTITY_INVALID",
                    ),
                    attempt,
                )
            if payload.safe_code in _NON_RETRYABLE_PROVIDER_CODES:
                return approval, payload, attempt
            if payload.state not in {
                LiveProviderState.TIMED_OUT,
                LiveProviderState.UNAVAILABLE,
            } or attempt == 3:
                return approval, payload, attempt
        except TimeoutError:
            payload = _failed_payload(
                approval.provider_id,
                LiveProviderState.TIMED_OUT,
                "LIVE_PROVIDER_TIMED_OUT",
            )
            if attempt == 3:
                return approval, payload, attempt
        except Exception:
            payload = _failed_payload(
                approval.provider_id,
                LiveProviderState.UNAVAILABLE,
                "LIVE_PROVIDER_UNAVAILABLE",
            )
            if attempt == 3:
                return approval, payload, attempt
        await retry_sleeper(0.05 * (2 ** (attempt - 1)))
    raise AssertionError("bounded retry loop did not return")


def _admission_failure(
    request: LiveRetrievalRequest,
    approval: LiveProviderApproval,
    registry: Mapping[str, LiveRegistryEntry],
    item: LiveProviderItem,
) -> LiveAdmissionReason | None:
    entry = registry.get(item.registry_entry_id)
    if entry is None or item.registry_entry_id not in approval.allowed_registry_entry_ids:
        return LiveAdmissionReason.SOURCE_NOT_APPROVED
    if not entry.active:
        return LiveAdmissionReason.REGISTRY_ENTRY_INACTIVE
    if item.source_type not in entry.allowed_source_types:
        return LiveAdmissionReason.SOURCE_TYPE_NOT_APPROVED
    if item.license_class is not entry.license_class:
        return LiveAdmissionReason.LICENSE_MISMATCH
    if item.publisher.casefold() != entry.publisher.casefold():
        return LiveAdmissionReason.PUBLISHER_MISMATCH
    if not _urls_match_registry(item, entry):
        return LiveAdmissionReason.URL_NOT_ADMISSIBLE
    if item.publication_at is None:
        return LiveAdmissionReason.PUBLICATION_TIME_MISSING
    if item.publication_at > request.now:
        return LiveAdmissionReason.PUBLICATION_TIME_IN_FUTURE
    if item.retrieved_at > request.now or item.retrieved_at < item.publication_at:
        return LiveAdmissionReason.RETRIEVAL_TIME_INVALID
    if hashlib.sha256(item.excerpt.encode("utf-8")).hexdigest() != item.content_sha256:
        return LiveAdmissionReason.CONTENT_HASH_MISMATCH
    if (
        approval.retention_mode is LiveRetentionMode.METADATA_ONLY
        and item.excerpt.strip()
    ):
        return LiveAdmissionReason.RETENTION_NOT_PERMITTED
    if not _inside_window(item, request.window, request.now):
        return LiveAdmissionReason.OUTSIDE_TIME_WINDOW
    return None


def _inside_window(
    item: LiveProviderItem,
    window: LiveTimeWindow,
    now: datetime,
) -> bool:
    publication = item.publication_at
    if publication is None:
        return False
    now_utc = now.astimezone(UTC)
    publication_utc = publication.astimezone(UTC)
    if window.kind is LiveWindowKind.TODAY:
        timezone = ZoneInfo(window.user_timezone)
        local_now = now.astimezone(timezone)
        start = datetime.combine(local_now.date(), time.min, timezone)
        end = start + timedelta(days=1)
        return start.astimezone(UTC) <= publication_utc < end.astimezone(UTC)
    if window.kind is LiveWindowKind.BREAKING:
        return now_utc - timedelta(hours=72) <= publication_utc <= now_utc
    if window.kind is LiveWindowKind.NEWS:
        return now_utc - timedelta(days=30) <= publication_utc <= now_utc
    if window.kind is LiveWindowKind.RECENT:
        return now_utc - timedelta(days=90) <= publication_utc <= now_utc
    if window.kind is LiveWindowKind.BOUNDED:
        assert window.start_at is not None and window.end_at is not None
        return (
            window.start_at.astimezone(UTC)
            <= publication_utc
            < window.end_at.astimezone(UTC)
        )
    closes = item.consultation_closes_at
    if closes is None or item.source_type is not LiveSourceType.OFFICIAL_DRAFT_OR_CONSULTATION:
        return False
    closes_utc = closes.astimezone(UTC)
    if window.kind is LiveWindowKind.OPEN_CONSULTATION:
        return closes_utc > now_utc
    return now_utc - timedelta(days=90) <= closes_utc <= now_utc


def _admit(
    request: LiveRetrievalRequest,
    approval: LiveProviderApproval,
    entry: LiveRegistryEntry,
    item: LiveProviderItem,
) -> LiveAdmittedEvidence:
    rank = _trust_rank(item.source_type)
    source = SourceIdentity(
        source_id=item.evidence_id,
        provenance_class=ProvenanceClass.LIVE_WEB_SOURCES,
        title=item.title,
        uri=item.canonical_url,
        issuer_or_publisher=entry.publisher,
        publication_at=item.publication_at,
        retrieved_at=item.retrieved_at,
    )
    artifact = ArtifactEnvelope(
        artifact_id=f"live:{item.evidence_id}",
        producer=ArtifactProducer.NEWS_RETRIEVER,
        scope=request.scope,
        payload=EvidenceUnitPayload(
            excerpt=item.excerpt,
            locator=item.canonical_url,
            source_status=f"live:{rank.value}",
            match_reasons=("approved_live_source", "requested_time_window"),
        ),
        provenance=ProvenanceLineage(
            provenance_class=ProvenanceClass.LIVE_WEB_SOURCES,
            knowledge_mode=KnowledgeMode.LIVE_INTELLIGENCE,
            sources=(source,),
            derivation=ContentDerivation.DIRECT,
            verification_status=VerificationStatus.PENDING,
        ),
        confidence_signals=ConfidenceSignals(
            evidence_authority=_authority_score(rank),
            freshness_validity=1.0,
            scope_resolution=1.0,
            critical_input_ceiling=_authority_score(rank),
            reasons=(f"LIVE_TRUST_{rank.value}",),
        ),
        ancestry=(
            f"live-policy:{request.policy.policy_version}",
            f"live-registry:{request.policy.registry_version}",
            f"live-entitlement:{request.policy.entitlement_version}",
            f"live-provider:{approval.provider_id}",
        ),
        capability_status=CapabilityTerminalState.SATISFIED,
        warnings=("LIVE_SOURCE_NOT_LEGAL_FORCE", "UNTRUSTED_LIVE_CONTENT"),
    )
    return LiveAdmittedEvidence(
        evidence_id=item.evidence_id,
        provider_id=approval.provider_id,
        provider_family=approval.family,
        registry_entry_id=entry.entry_id,
        trust_rank=rank,
        confidence_ceiling=_confidence_ceiling(rank),
        ui_badge=_ui_badge(rank),
        license_class=item.license_class,
        canonical_url=item.canonical_url,
        original_url=item.original_url,
        publisher=item.publisher,
        title=item.title,
        source_type=item.source_type,
        content_sha256=item.content_sha256,
        publication_at=item.publication_at,
        retrieved_at=item.retrieved_at,
        event_fingerprint=item.event_fingerprint,
        artifact=artifact,
    )


def _deduplicate(
    evidence: list[LiveAdmittedEvidence],
) -> tuple[list[LiveAdmittedEvidence], list[LiveRejectedItem]]:
    retained: list[LiveAdmittedEvidence] = []
    rejected: list[LiveRejectedItem] = []
    identities: dict[str, int] = {}
    for item in evidence:
        keys = (
            f"url:{item.canonical_url.casefold()}",
            f"hash:{item.content_sha256}",
            "headline:"
            + " ".join(item.publisher.casefold().split())
            + "|"
            + " ".join(item.title.casefold().split()),
        )
        matching_indexes = {identities[key] for key in keys if key in identities}
        existing_index = min(matching_indexes) if matching_indexes else None
        if existing_index is None:
            index = len(retained)
            for key in keys:
                identities[key] = index
            retained.append(item)
            continue
        existing = retained[existing_index]
        existing_lineage = existing.artifact.provenance
        duplicate_lineage = item.artifact.provenance
        assert existing_lineage is not None and duplicate_lineage is not None
        merged_artifact = existing.artifact.model_copy(
            update={
                "provenance": existing_lineage.model_copy(
                    update={
                        "sources": (
                            *existing_lineage.sources,
                            *duplicate_lineage.sources,
                        )
                    }
                )
            }
        )
        retained[existing_index] = existing.model_copy(
            update={
                "artifact": merged_artifact,
                "duplicate_source_ids": (
                    *existing.duplicate_source_ids,
                    item.evidence_id,
                )
            }
        )
        for key in keys:
            identities[key] = existing_index
        rejected.append(
            LiveRejectedItem(
                provider_id=item.provider_id,
                evidence_id=item.evidence_id,
                reason=LiveAdmissionReason.DUPLICATE,
            )
        )
    return retained, rejected


def _urls_match_registry(item: LiveProviderItem, entry: LiveRegistryEntry) -> bool:
    try:
        return all(
            _safe_https_host(value) == entry.exact_host
            for value in (item.original_url, item.canonical_url)
        )
    except ValueError:
        return False


def _safe_https_host(value: str) -> str:
    parsed = urlsplit(value)
    if (
        parsed.scheme.lower() != "https"
        or not parsed.hostname
        or parsed.username is not None
        or parsed.password is not None
        or parsed.port not in {None, 443}
        or parsed.fragment
    ):
        raise ValueError("Live URL is not admissible")
    host = parsed.hostname.rstrip(".").lower()
    sensitive_query_names = {
        "access_token",
        "api_key",
        "apikey",
        "auth",
        "key",
        "password",
        "secret",
        "signature",
        "token",
    }
    if any(
        name.casefold() in sensitive_query_names
        for name, _ in parse_qsl(parsed.query, keep_blank_values=True)
    ):
        raise ValueError("Live URL contains credential-shaped query data")
    _reject_ip_or_local_host(host)
    return host


def _reject_ip_or_local_host(host: str) -> None:
    if host == "localhost" or host.endswith(".localhost") or "." not in host:
        raise ValueError("Local host is forbidden")
    try:
        ipaddress.ip_address(host.strip("[]"))
    except ValueError:
        return
    raise ValueError("IP-literal hosts are forbidden")


def _trust_rank(source_type: LiveSourceType) -> LiveTrustRank:
    return {
        LiveSourceType.OPERATIVE_OFFICIAL: LiveTrustRank.L1,
        LiveSourceType.OFFICIAL_CURRENT_NOTICE: LiveTrustRank.L1,
        LiveSourceType.OFFICIAL_DRAFT_OR_CONSULTATION: LiveTrustRank.L2,
        LiveSourceType.LICENSED_NEWS: LiveTrustRank.L3,
        LiveSourceType.ESTABLISHED_PRESS: LiveTrustRank.L4,
        LiveSourceType.INDUSTRY_ANNOUNCEMENT: LiveTrustRank.L5,
    }[source_type]


def _confidence_ceiling(rank: LiveTrustRank) -> ConfidenceLabel:
    return {
        LiveTrustRank.L1: ConfidenceLabel.HIGH,
        LiveTrustRank.L2: ConfidenceLabel.MEDIUM,
        LiveTrustRank.L3: ConfidenceLabel.MEDIUM,
        LiveTrustRank.L4: ConfidenceLabel.MEDIUM,
        LiveTrustRank.L5: ConfidenceLabel.LOW,
    }[rank]


def _authority_score(rank: LiveTrustRank) -> float:
    return {
        LiveTrustRank.L1: 0.9,
        LiveTrustRank.L2: 0.75,
        LiveTrustRank.L3: 0.7,
        LiveTrustRank.L4: 0.65,
        LiveTrustRank.L5: 0.5,
    }[rank]


def _ui_badge(rank: LiveTrustRank) -> str:
    return {
        LiveTrustRank.L1: "Official live source",
        LiveTrustRank.L2: "Official live source",
        LiveTrustRank.L3: "Licensed news",
        LiveTrustRank.L4: "Live news source",
        LiveTrustRank.L5: "Industry announcement",
    }[rank]


def _failed_payload(
    provider_id: str,
    state: LiveProviderState,
    code: str,
) -> LiveProviderPayload:
    return LiveProviderPayload(
        provider_id=provider_id,
        state=state,
        items=(),
        safe_code=code,
    )


def _provider_failure(provider_id: str, code: str) -> LiveProviderOutcome:
    return LiveProviderOutcome(
        provider_id=provider_id,
        state=LiveProviderState.UNAVAILABLE,
        attempts=0,
        admitted_count=0,
        rejected_count=0,
        safe_code=code,
    )


def _empty_result(
    policy: LivePolicySnapshot,
    state: CapabilityTerminalState,
    code: str | None,
) -> LiveCapabilityResult:
    return LiveCapabilityResult(
        registry_version=policy.registry_version,
        entitlement_version=policy.entitlement_version,
        state=state,
        safe_code=code,
    )
