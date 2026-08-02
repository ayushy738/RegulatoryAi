from __future__ import annotations

import asyncio
import hashlib
import json
from datetime import UTC, datetime, timedelta

import pytest
from pydantic import ValidationError

from backend.ask.decision.models import ConfidenceLabel
from backend.ask.live_intelligence import (
    APPROVED_OFFICIAL_PUBLISHERS,
    LIVE_SECTION_DISCLOSURE,
    LiveAdmissionReason,
    LiveCacheRecord,
    LiveCapabilityResult,
    LiveConnectorSecurityProfile,
    LiveEntitlementState,
    LiveLicenseClass,
    LivePolicySnapshot,
    LiveProviderApproval,
    LiveProviderClass,
    LiveProviderFamily,
    LiveProviderItem,
    LiveProviderPayload,
    LiveProviderState,
    LiveRegistryEntry,
    LiveRetentionMode,
    LiveRetrievalRequest,
    LiveSourceType,
    LiveTimeWindow,
    LiveTrustRank,
    LiveWindowKind,
    default_live_policy_snapshot,
    execute_live_intelligence,
    live_cache_key,
    live_cache_ttl_seconds,
    live_result_json,
    stale_cache_allowed,
    stale_cache_fallback,
)
from backend.ask.orchestration.contracts import (
    CapabilityScope,
    CapabilityTerminalState,
    EvidenceUnitPayload,
    KnowledgeMode,
    ProvenanceClass,
)

NOW = datetime(2026, 8, 1, 12, tzinfo=UTC)
HOST = "cercind.gov.in"
ENTRY_ID = f"official:{HOST}"
PUBLISHER = APPROVED_OFFICIAL_PUBLISHERS[HOST]


class _Connector:
    def __init__(
        self,
        responses: list[object],
        *,
        provider_id: str = "official-direct",
        family: LiveProviderFamily = LiveProviderFamily.OFFICIAL_DIRECT,
        delay: float = 0,
    ) -> None:
        self.provider_id = provider_id
        self.family = family
        self.security_profile = LiveConnectorSecurityProfile()
        self.responses = list(responses)
        self.delay = delay
        self.calls = 0

    async def retrieve(self, request: LiveRetrievalRequest) -> str:
        self.calls += 1
        if self.delay:
            await asyncio.sleep(self.delay)
        response = self.responses[min(self.calls - 1, len(self.responses) - 1)]
        if isinstance(response, Exception):
            raise response
        return response  # type: ignore[return-value]


async def _no_wait(_: float) -> None:
    return None


def _scope() -> CapabilityScope:
    return CapabilityScope(
        atomic_question_ids=("question-1",),
        section_keys=("live",),
        entity_ids=("regulator:cerc",),
        jurisdiction="India",
        time_scope="current",
    )


def _policy(*, enabled: bool = True) -> LivePolicySnapshot:
    return default_live_policy_snapshot(enable_official_direct=enabled)


def _request(
    *,
    policy: LivePolicySnapshot | None = None,
    window: LiveTimeWindow | None = None,
    selected: tuple[str, ...] = ("official-direct",),
    searches: int = 0,
    burst: int = 0,
    timeout_ms: int = 8_000,
) -> LiveRetrievalRequest:
    return LiveRetrievalRequest(
        policy=policy or _policy(),
        query="latest CERC consultation",
        scope=_scope(),
        window=window or LiveTimeWindow(kind=LiveWindowKind.NEWS),
        now=NOW,
        selected_provider_ids=selected,
        user_searches_last_minute=searches,
        user_burst_in_flight=burst,
        timeout_ms=timeout_ms,
    )


def _item(
    *,
    evidence_id: str = "live-1",
    published: datetime | None = None,
    retrieved: datetime = NOW,
    source_type: LiveSourceType = LiveSourceType.OFFICIAL_CURRENT_NOTICE,
    canonical_url: str = f"https://{HOST}/notice/1",
    original_url: str | None = None,
    publisher: str = PUBLISHER,
    entry_id: str = ENTRY_ID,
    license_class: LiveLicenseClass = LiveLicenseClass.OFFICIAL_PUBLIC,
    excerpt: str = "CERC published a current consultation notice.",
    closes: datetime | None = None,
    publication_time_unavailable: bool = False,
    content_sha256: str | None = None,
) -> LiveProviderItem:
    return LiveProviderItem(
        evidence_id=evidence_id,
        registry_entry_id=entry_id,
        canonical_url=canonical_url,
        original_url=original_url or canonical_url,
        publisher=publisher,
        title="Current consultation notice",
        source_type=source_type,
        license_class=license_class,
        publication_at=(published if published is not None else NOW - timedelta(days=1)),
        publication_time_unavailable=publication_time_unavailable,
        retrieved_at=retrieved,
        consultation_closes_at=closes,
        excerpt=excerpt,
        content_sha256=content_sha256 or hashlib.sha256(excerpt.encode()).hexdigest(),
        event_fingerprint="cerc|consultation|2026-08-01",
    )


def _raw(
    state: LiveProviderState,
    *items: LiveProviderItem,
    provider_id: str = "official-direct",
    safe_code: str | None = None,
) -> str:
    return LiveProviderPayload(
        provider_id=provider_id,
        state=state,
        items=items,
        safe_code=safe_code,
    ).model_dump_json()


def _execute(
    connector: _Connector,
    *,
    request: LiveRetrievalRequest | None = None,
    connectors: dict[str, _Connector] | None = None,
) -> LiveCapabilityResult:
    return asyncio.run(
        execute_live_intelligence(
            request or _request(),
            connectors=connectors or {connector.provider_id: connector},
            retry_sleeper=_no_wait,
        )
    )


def test_default_policy_freezes_all_b005_official_hosts_and_disabled_connectors() -> None:
    policy = default_live_policy_snapshot()

    assert {item.exact_host for item in policy.registry_entries} == set(
        APPROVED_OFFICIAL_PUBLISHERS
    )
    assert {item.family for item in policy.providers} == {
        LiveProviderFamily.OFFICIAL_DIRECT,
        LiveProviderFamily.PARALLEL_SOURCE_RETAINING,
    }
    assert all(not item.enabled for item in policy.providers)
    assert policy.approval_id == "RAA-B005-2026-001"


def test_admitted_official_item_retains_exact_live_provenance_and_ceiling() -> None:
    connector = _Connector([_raw(LiveProviderState.SATISFIED, _item())])

    result = _execute(connector)

    assert result.state is CapabilityTerminalState.SATISFIED
    assert result.disclosure == LIVE_SECTION_DISCLOSURE
    assert result.registry_version == "b005-official-registry-v1"
    assert result.entitlement_version == "b005-entitlements-v1"
    assert len(result.evidence) == 1
    admitted = result.evidence[0]
    assert admitted.trust_rank is LiveTrustRank.L1
    assert admitted.confidence_ceiling is ConfidenceLabel.HIGH
    assert admitted.ui_badge == "Official live source"
    assert admitted.publisher == PUBLISHER
    assert admitted.publication_at == NOW - timedelta(days=1)
    assert admitted.retrieved_at == NOW
    artifact = admitted.artifact
    assert artifact.provenance is not None
    assert artifact.provenance.provenance_class is ProvenanceClass.LIVE_WEB_SOURCES
    assert artifact.provenance.knowledge_mode is KnowledgeMode.LIVE_INTELLIGENCE
    assert isinstance(artifact.payload, EvidenceUnitPayload)
    assert artifact.payload.locator == f"https://{HOST}/notice/1"
    assert "LIVE_SOURCE_NOT_LEGAL_FORCE" in artifact.warnings
    assert "UNTRUSTED_LIVE_CONTENT" in artifact.warnings
    assert all("internal" not in value for value in artifact.ancestry)


@pytest.mark.parametrize(
    ("url", "expected_reason"),
    [
        ("http://cercind.gov.in/notice/1", LiveAdmissionReason.URL_NOT_ADMISSIBLE),
        (
            "https://attacker.cercind.gov.in/notice/1",
            LiveAdmissionReason.URL_NOT_ADMISSIBLE,
        ),
        (
            "https://user:secret@cercind.gov.in/notice/1",
            LiveAdmissionReason.URL_NOT_ADMISSIBLE,
        ),
        ("https://127.0.0.1/notice/1", LiveAdmissionReason.URL_NOT_ADMISSIBLE),
        (
            "https://cercind.gov.in/notice/1?api_key=secret",
            LiveAdmissionReason.URL_NOT_ADMISSIBLE,
        ),
    ],
)
def test_url_admission_is_exact_https_and_ssrf_safe(
    url: str,
    expected_reason: LiveAdmissionReason,
) -> None:
    connector = _Connector(
        [_raw(LiveProviderState.SATISFIED, _item(canonical_url=url))]
    )

    result = _execute(connector)

    assert result.state is CapabilityTerminalState.INVALID_OUTPUT
    assert result.safe_code == "LIVE_OUTPUT_INVALID"
    assert result.rejected[0].reason is expected_reason
    assert not result.evidence


@pytest.mark.parametrize(
    ("window", "published", "closes", "accepted"),
    [
        (LiveTimeWindow(kind=LiveWindowKind.TODAY), NOW - timedelta(hours=1), None, True),
        (LiveTimeWindow(kind=LiveWindowKind.TODAY), NOW - timedelta(days=1), None, False),
        (LiveTimeWindow(kind=LiveWindowKind.BREAKING), NOW - timedelta(hours=72), None, True),
        (LiveTimeWindow(kind=LiveWindowKind.BREAKING), NOW - timedelta(hours=73), None, False),
        (LiveTimeWindow(kind=LiveWindowKind.NEWS), NOW - timedelta(days=30), None, True),
        (LiveTimeWindow(kind=LiveWindowKind.NEWS), NOW - timedelta(days=31), None, False),
        (LiveTimeWindow(kind=LiveWindowKind.RECENT), NOW - timedelta(days=90), None, True),
        (
            LiveTimeWindow(
                kind=LiveWindowKind.BOUNDED,
                start_at=NOW - timedelta(days=10),
                end_at=NOW - timedelta(days=5),
            ),
            NOW - timedelta(days=7),
            None,
            True,
        ),
        (
            LiveTimeWindow(kind=LiveWindowKind.OPEN_CONSULTATION),
            NOW - timedelta(days=5),
            NOW + timedelta(days=1),
            True,
        ),
        (
            LiveTimeWindow(kind=LiveWindowKind.RECENTLY_CLOSED_CONSULTATION),
            NOW - timedelta(days=20),
            NOW - timedelta(days=1),
            True,
        ),
    ],
)
def test_fixed_clock_time_windows(
    window: LiveTimeWindow,
    published: datetime,
    closes: datetime | None,
    accepted: bool,
) -> None:
    source_type = (
        LiveSourceType.OFFICIAL_DRAFT_OR_CONSULTATION
        if closes is not None
        else LiveSourceType.OFFICIAL_CURRENT_NOTICE
    )
    connector = _Connector(
        [
            _raw(
                LiveProviderState.SATISFIED,
                _item(published=published, closes=closes, source_type=source_type),
            )
        ]
    )

    result = _execute(connector, request=_request(window=window))

    assert bool(result.evidence) is accepted
    if not accepted:
        assert result.rejected[0].reason is LiveAdmissionReason.OUTSIDE_TIME_WINDOW


def test_missing_future_and_tampered_publication_evidence_fail_closed() -> None:
    missing = _item(
        published=NOW - timedelta(days=1),
    ).model_copy(
        update={"publication_at": None, "publication_time_unavailable": True}
    )
    future = _item(evidence_id="live-2", published=NOW + timedelta(seconds=1))
    tampered = _item(evidence_id="live-3", content_sha256="0" * 64)
    connector = _Connector(
        [_raw(LiveProviderState.SATISFIED, missing, future, tampered)]
    )

    result = _execute(connector)

    assert result.state is CapabilityTerminalState.INVALID_OUTPUT
    assert tuple(item.reason for item in result.rejected) == (
        LiveAdmissionReason.PUBLICATION_TIME_MISSING,
        LiveAdmissionReason.PUBLICATION_TIME_IN_FUTURE,
        LiveAdmissionReason.CONTENT_HASH_MISMATCH,
    )


def test_licensed_and_industry_ranks_never_gain_official_authority() -> None:
    entries = (
        LiveRegistryEntry(
            entry_id="licensed:reuters",
            exact_host="reuters.example",
            publisher="Reuters",
            allowed_source_types=(LiveSourceType.LICENSED_NEWS,),
            allowed_provider_families=(LiveProviderFamily.REUTERS,),
            license_class=LiveLicenseClass.ENTERPRISE_LICENSED,
        ),
        LiveRegistryEntry(
            entry_id="industry:grid-company",
            exact_host="news.grid-company.example",
            publisher="Grid Company",
            allowed_source_types=(LiveSourceType.INDUSTRY_ANNOUNCEMENT,),
            allowed_provider_families=(
                LiveProviderFamily.PARALLEL_SOURCE_RETAINING,
            ),
            license_class=LiveLicenseClass.FIRST_PARTY_PUBLIC,
        ),
    )
    providers = (
        LiveProviderApproval(
            provider_id="reuters-live",
            family=LiveProviderFamily.REUTERS,
            provider_class=LiveProviderClass.LICENSED_COMMERCIAL_NEWS,
            entitlement_state=LiveEntitlementState.ACTIVE,
            retention_mode=LiveRetentionMode.EXCERPT,
            attribution_text="Reuters",
            allowed_registry_entry_ids=("licensed:reuters",),
            max_requests_per_second=10,
            max_concurrency=20,
            enabled=True,
        ),
        LiveProviderApproval(
            provider_id="parallel-industry",
            family=LiveProviderFamily.PARALLEL_SOURCE_RETAINING,
            provider_class=LiveProviderClass.SOURCE_RETAINING_RESEARCH,
            entitlement_state=LiveEntitlementState.ACTIVE,
            retention_mode=LiveRetentionMode.EXCERPT,
            attribution_text="Source-retaining retrieval via Parallel.ai",
            allowed_registry_entry_ids=("industry:grid-company",),
            max_requests_per_second=10,
            max_concurrency=20,
            enabled=True,
        ),
    )
    policy = LivePolicySnapshot(
        registry_version="custom-registry-1",
        entitlement_version="custom-entitlement-1",
        registry_entries=entries,
        providers=providers,
    )
    reuters_item = _item(
        evidence_id="wire-1",
        canonical_url="https://reuters.example/story/1",
        publisher="Reuters",
        entry_id="licensed:reuters",
        source_type=LiveSourceType.LICENSED_NEWS,
        license_class=LiveLicenseClass.ENTERPRISE_LICENSED,
    )
    industry_item = _item(
        evidence_id="industry-1",
        canonical_url="https://news.grid-company.example/update/1",
        publisher="Grid Company",
        entry_id="industry:grid-company",
        source_type=LiveSourceType.INDUSTRY_ANNOUNCEMENT,
        license_class=LiveLicenseClass.FIRST_PARTY_PUBLIC,
        excerpt="Grid Company announced an operational update.",
    )
    reuters = _Connector(
        [_raw(LiveProviderState.SATISFIED, reuters_item, provider_id="reuters-live")],
        provider_id="reuters-live",
        family=LiveProviderFamily.REUTERS,
    )
    industry = _Connector(
        [
            _raw(
                LiveProviderState.SATISFIED,
                industry_item,
                provider_id="parallel-industry",
            )
        ],
        provider_id="parallel-industry",
        family=LiveProviderFamily.PARALLEL_SOURCE_RETAINING,
    )

    result = _execute(
        reuters,
        request=_request(
            policy=policy,
            selected=("reuters-live", "parallel-industry"),
        ),
        connectors={"reuters-live": reuters, "parallel-industry": industry},
    )

    assert result.state is CapabilityTerminalState.SATISFIED
    assert tuple(item.trust_rank for item in result.evidence) == (
        LiveTrustRank.L3,
        LiveTrustRank.L5,
    )
    assert tuple(item.confidence_ceiling for item in result.evidence) == (
        ConfidenceLabel.MEDIUM,
        ConfidenceLabel.LOW,
    )
    assert all(
        item.artifact.provenance is not None
        and item.artifact.provenance.provenance_class
        is ProvenanceClass.LIVE_WEB_SOURCES
        for item in result.evidence
    )


def test_inactive_entitlement_and_user_limits_make_zero_provider_calls() -> None:
    disabled_policy = default_live_policy_snapshot(enable_parallel=False)
    connector = _Connector(
        [_raw(LiveProviderState.NO_MATCH)],
        provider_id="parallel-live",
        family=LiveProviderFamily.PARALLEL_SOURCE_RETAINING,
    )
    entitlement = _execute(
        connector,
        request=_request(policy=disabled_policy, selected=("parallel-live",)),
    )
    rate_limited_connector = _Connector([_raw(LiveProviderState.NO_MATCH)])
    rate_limited = _execute(
        rate_limited_connector,
        request=_request(searches=10),
    )

    assert entitlement.state is CapabilityTerminalState.UNAVAILABLE
    assert entitlement.provider_outcomes[0].safe_code == "LIVE_PROVIDER_DISABLED"
    assert connector.calls == 0
    assert rate_limited.state is CapabilityTerminalState.UNAVAILABLE
    assert rate_limited.safe_code == "LIVE_RATE_LIMITED"
    assert rate_limited_connector.calls == 0


def test_no_match_failure_and_bounded_retry_remain_distinct() -> None:
    no_match_connector = _Connector([_raw(LiveProviderState.NO_MATCH)])
    no_match = _execute(no_match_connector)
    unavailable_connector = _Connector(
        [
            _raw(
                LiveProviderState.UNAVAILABLE,
                safe_code="LIVE_PROVIDER_UNAVAILABLE",
            )
        ]
    )
    unavailable = _execute(unavailable_connector)

    assert no_match.state is CapabilityTerminalState.NO_MATCH
    assert no_match.safe_code is None
    assert no_match_connector.calls == 1
    assert unavailable.state is CapabilityTerminalState.UNAVAILABLE
    assert unavailable.safe_code == "LIVE_PROVIDERS_UNAVAILABLE"
    assert unavailable_connector.calls == 3
    assert unavailable.provider_outcomes[0].attempts == 3


def test_provider_identity_and_malformed_output_are_invalid_not_no_match() -> None:
    mismatch = _Connector(
        [_raw(LiveProviderState.NO_MATCH, provider_id="another-provider")]
    )
    malformed = _Connector(["not-json"])

    mismatch_result = _execute(mismatch)
    malformed_result = _execute(malformed)

    assert mismatch_result.state is CapabilityTerminalState.INVALID_OUTPUT
    assert mismatch_result.provider_outcomes[0].safe_code == (
        "LIVE_PROVIDER_IDENTITY_INVALID"
    )
    assert malformed_result.state is CapabilityTerminalState.INVALID_OUTPUT
    assert malformed_result.provider_outcomes[0].safe_code == (
        "LIVE_PROVIDER_OUTPUT_INVALID"
    )


def test_exact_duplicates_render_once_and_retain_underlying_identity() -> None:
    first = _item(evidence_id="live-1")
    second = _item(evidence_id="live-2")
    connector = _Connector(
        [_raw(LiveProviderState.SATISFIED, first, second)]
    )

    result = _execute(connector)

    assert result.state is CapabilityTerminalState.SATISFIED
    assert len(result.evidence) == 1
    assert result.evidence[0].duplicate_source_ids == ("live-2",)
    assert result.evidence[0].artifact.provenance is not None
    assert len(result.evidence[0].artifact.provenance.sources) == 2
    assert result.rejected[-1].reason is LiveAdmissionReason.DUPLICATE


def test_cache_key_ttls_stale_rules_and_serialization_are_deterministic() -> None:
    request = _request()
    connector = _Connector([_raw(LiveProviderState.SATISFIED, _item())])
    result = _execute(connector, request=request)
    key = live_cache_key(request)
    record = LiveCacheRecord(
        cache_key=key,
        stored_at=NOW - timedelta(hours=1),
        expires_at=NOW - timedelta(minutes=45),
        result=result,
    )

    assert key == live_cache_key(request)
    assert live_cache_ttl_seconds(rank=LiveTrustRank.L1) == 900
    assert live_cache_ttl_seconds(rank=LiveTrustRank.L3) == 600
    assert live_cache_ttl_seconds(state=CapabilityTerminalState.NO_MATCH) == 300
    assert live_cache_ttl_seconds(state=CapabilityTerminalState.UNAVAILABLE) == 30
    assert live_cache_ttl_seconds(historical_context=True) == 86_400
    assert stale_cache_allowed(record, request=request)
    stale = stale_cache_fallback(record, request=request)
    assert stale is not None
    assert stale.state is CapabilityTerminalState.PARTIAL
    assert stale.evidence[0].confidence_ceiling is ConfidenceLabel.LOW
    assert stale.evidence[0].ui_badge == "Stale cached live source"
    assert stale.evidence[0].retrieved_at == result.evidence[0].retrieved_at
    assert "STALE_CACHED_LIVE_SOURCE" in stale.evidence[0].artifact.warnings
    assert not stale_cache_allowed(
        record,
        request=_request(window=LiveTimeWindow(kind=LiveWindowKind.BREAKING)),
    )
    assert json.loads(live_result_json(result)) == result.model_dump(mode="json")


def test_auth_entitlement_robots_and_permanent_failures_are_not_retried() -> None:
    for code in (
        "LIVE_PROVIDER_AUTH_FAILED",
        "LIVE_PROVIDER_ENTITLEMENT_FAILED",
        "LIVE_PROVIDER_ROBOTS_DENIED",
        "LIVE_PROVIDER_PERMANENT_FAILURE",
        "LIVE_PROVIDER_RATE_LIMITED",
    ):
        connector = _Connector(
            [_raw(LiveProviderState.UNAVAILABLE, safe_code=code)]
        )

        result = _execute(connector)

        assert result.state is CapabilityTerminalState.UNAVAILABLE
        assert connector.calls == 1
        assert result.provider_outcomes[0].safe_code == code


def test_strict_contracts_reject_unapproved_provider_and_unsafe_policy_limits() -> None:
    with pytest.raises(ValidationError, match="not in the policy snapshot"):
        _request(selected=("unapproved",))
    with pytest.raises(ValidationError, match="host limits"):
        LiveProviderApproval(
            provider_id="unsafe-official",
            family=LiveProviderFamily.OFFICIAL_DIRECT,
            provider_class=LiveProviderClass.OFFICIAL_DIRECT,
            entitlement_state=LiveEntitlementState.ACTIVE,
            retention_mode=LiveRetentionMode.EXCERPT,
            attribution_text="Official publisher",
            allowed_registry_entry_ids=(ENTRY_ID,),
            max_requests_per_second=6,
            max_concurrency=10,
        )
    with pytest.raises(ValidationError):
        LiveProviderPayload.model_validate(
            {
                "schema_version": "1",
                "provider_id": "official-direct",
                "state": "no_match",
                "items": [],
                "safe_code": None,
                "raw_provider_error": "secret",
            }
        )


def test_model_copy_request_tampering_fails_closed_without_provider_access() -> None:
    connector = _Connector([_raw(LiveProviderState.NO_MATCH)])
    tampered = _request().model_copy(update={"now": datetime(2026, 8, 1, 12)})

    result = _execute(connector, request=tampered)

    assert result.state is CapabilityTerminalState.INVALID_OUTPUT
    assert result.safe_code == "LIVE_REQUEST_INVALID"
    assert connector.calls == 0


def test_connector_without_enforced_network_security_remains_disabled() -> None:
    connector = _Connector([_raw(LiveProviderState.NO_MATCH)])
    connector.security_profile = connector.security_profile.model_copy(
        update={"dns_reresolution_before_connect": False}
    )

    result = _execute(connector)

    assert result.state is CapabilityTerminalState.UNAVAILABLE
    assert result.provider_outcomes[0].safe_code == "LIVE_CONNECTOR_SECURITY_INVALID"
    assert result.rejected[0].reason is LiveAdmissionReason.CONNECTOR_SECURITY_INVALID
    assert connector.calls == 0


def test_timeout_is_bounded_and_provider_detail_never_enters_result() -> None:
    connector = _Connector(
        [_raw(LiveProviderState.NO_MATCH)],
        delay=0.02,
    )

    result = _execute(connector, request=_request(timeout_ms=1))

    assert result.state is CapabilityTerminalState.TIMED_OUT
    assert result.safe_code == "LIVE_ALL_PROVIDERS_TIMED_OUT"
    assert connector.calls == 3
    serialized = live_result_json(result)
    assert "Traceback" not in serialized
    assert "secret" not in serialized


def test_partial_provider_failure_preserves_independent_live_evidence() -> None:
    policy = _policy().model_copy(
        update={
            "providers": (
                *_policy().providers,
                _policy().providers[0].model_copy(
                    update={"provider_id": "official-secondary"}
                ),
            )
        }
    )
    request = _request(
        policy=LivePolicySnapshot.model_validate_json(policy.model_dump_json()),
        selected=("official-direct", "official-secondary"),
    )
    healthy = _Connector([_raw(LiveProviderState.SATISFIED, _item())])
    failed = _Connector(
        [
            _raw(
                LiveProviderState.UNAVAILABLE,
                provider_id="official-secondary",
                safe_code="LIVE_PROVIDER_UNAVAILABLE",
            )
        ],
        provider_id="official-secondary",
    )

    result = _execute(
        healthy,
        request=request,
        connectors={"official-direct": healthy, "official-secondary": failed},
    )

    assert result.state is CapabilityTerminalState.PARTIAL
    assert len(result.evidence) == 1
    assert result.disclosure == LIVE_SECTION_DISCLOSURE
    assert tuple(item.state for item in result.provider_outcomes) == (
        LiveProviderState.SATISFIED,
        LiveProviderState.UNAVAILABLE,
    )
