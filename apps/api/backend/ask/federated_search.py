from __future__ import annotations

import base64
import hashlib
import json
from collections.abc import Callable
from contextlib import AbstractContextManager
from dataclasses import dataclass
from datetime import UTC, date, datetime
from difflib import SequenceMatcher
from enum import StrEnum
from typing import Literal, Self
from urllib.parse import quote
from uuid import UUID

from pydantic import Field, field_validator, model_validator
from sqlalchemy import text
from sqlalchemy.orm import Session

from backend.ask.decision.entity_policy import EntityCatalogEntry
from backend.ask.decision.models import DecisionModel
from backend.ask.entity_lookup import EntityCatalogRepository
from backend.core.db import session_scope

SEARCH_SCHEMA_VERSION = "1"
SEARCH_POLICY_VERSION = "ask-ai-federated-search-v1"
_EPOCH = datetime(1970, 1, 1, tzinfo=UTC)


class SearchGroup(StrEnum):
    BEST_MATCH = "best_match"
    ENTITIES = "entities"
    OFFICIAL_REGULATIONS = "official_regulations"
    OFFICIAL_DOCUMENTS = "official_documents"
    AMENDMENTS = "amendments"
    CONSULTATIONS = "consultations"
    DEADLINES = "deadlines"
    PREVIOUS_RESEARCH = "previous_research"


SEARCHABLE_GROUPS = tuple(
    group for group in SearchGroup if group is not SearchGroup.BEST_MATCH
)
RESPONSE_GROUP_ORDER = tuple(SearchGroup)


class SearchResultType(StrEnum):
    ENTITY = "entity"
    OFFICIAL_REGULATION = "official_regulation"
    OFFICIAL_DOCUMENT = "official_document"
    AMENDMENT = "amendment"
    CONSULTATION = "consultation"
    DEADLINE = "deadline"
    PREVIOUS_RESEARCH = "previous_research"


class SearchGroupStatus(StrEnum):
    COMPLETE = "complete"
    NO_MATCH = "no_match"
    NOT_REQUESTED = "not_requested"
    UNAVAILABLE = "unavailable"


class SearchCorrectionKind(StrEnum):
    ACRONYM_EXPANSION = "acronym_expansion"
    SPELLING = "spelling"


class SearchFilters(DecisionModel):
    provenance: Literal[
        "internal_regulatory_corpus", "owned_research"
    ] | None = None
    jurisdiction: str | None = Field(default=None, max_length=200)
    regulator: str | None = Field(default=None, max_length=300)
    document_type: str | None = Field(default=None, max_length=200)
    entity_class: str | None = Field(default=None, max_length=100)
    status: str | None = Field(default=None, max_length=100)
    stakeholder: str | None = Field(default=None, max_length=300)
    topic: str | None = Field(default=None, max_length=300)
    lifecycle: Literal["current", "superseded", "draft"] | None = None
    date_from: date | None = None
    date_to: date | None = None

    @field_validator(
        "jurisdiction",
        "regulator",
        "document_type",
        "entity_class",
        "status",
        "stakeholder",
        "topic",
    )
    @classmethod
    def normalize_text(cls, value: str | None) -> str | None:
        if value is None:
            return None
        normalized = " ".join(value.split())
        if not normalized:
            raise ValueError("Search filters cannot be blank")
        return normalized

    @model_validator(mode="after")
    def validate_range(self) -> Self:
        if (
            self.date_from is not None
            and self.date_to is not None
            and self.date_from > self.date_to
        ):
            raise ValueError("Search date range cannot be reversed")
        return self


class FederatedSearchRequest(DecisionModel):
    schema_version: Literal["1"] = SEARCH_SCHEMA_VERSION
    query: str = Field(min_length=1, max_length=500)
    correction_mode: Literal["auto", "original"] = "auto"
    filters: SearchFilters = Field(default_factory=SearchFilters)
    group: SearchGroup | None = None
    cursor: str | None = Field(default=None, max_length=2_000)
    limit: int = Field(default=5, ge=1, le=20)

    @field_validator("query")
    @classmethod
    def normalize_query(cls, value: str) -> str:
        normalized = " ".join(value.split())
        if not normalized:
            raise ValueError("Search query cannot be blank")
        return normalized

    @model_validator(mode="after")
    def validate_page(self) -> Self:
        if self.group is SearchGroup.BEST_MATCH:
            raise ValueError("Best Match is derived and cannot be paged")
        if self.cursor is not None and self.group is None:
            raise ValueError("A search cursor requires its result group")
        return self


class SearchCorrection(DecisionModel):
    kind: SearchCorrectionKind
    original_query: str = Field(min_length=1)
    suggested_query: str = Field(min_length=1)
    reversible: Literal[True] = True

    @model_validator(mode="after")
    def validate_change(self) -> Self:
        if self.original_query.casefold() == self.suggested_query.casefold():
            raise ValueError("Search correction must change the query")
        return self


class SearchItem(DecisionModel):
    result_id: str = Field(pattern=r"^[a-z_]+:[A-Za-z0-9._:-]+$")
    result_type: SearchResultType
    title: str = Field(min_length=1, max_length=1_000)
    subtitle: str = Field(min_length=1, max_length=2_000)
    why_matched: str = Field(min_length=1, max_length=2_000)
    provenance: Literal["internal_regulatory_corpus", "owned_research"]
    relevance: int = Field(ge=0, le=1_000)
    route: str = Field(
        min_length=1,
        max_length=2_000,
        pattern=r"^/[A-Za-z0-9/?=&%._:-]+$",
    )


_GROUP_TYPES = {
    SearchGroup.ENTITIES: SearchResultType.ENTITY,
    SearchGroup.OFFICIAL_REGULATIONS: SearchResultType.OFFICIAL_REGULATION,
    SearchGroup.OFFICIAL_DOCUMENTS: SearchResultType.OFFICIAL_DOCUMENT,
    SearchGroup.AMENDMENTS: SearchResultType.AMENDMENT,
    SearchGroup.CONSULTATIONS: SearchResultType.CONSULTATION,
    SearchGroup.DEADLINES: SearchResultType.DEADLINE,
    SearchGroup.PREVIOUS_RESEARCH: SearchResultType.PREVIOUS_RESEARCH,
}


class SearchResultGroup(DecisionModel):
    group: SearchGroup
    status: SearchGroupStatus
    items: tuple[SearchItem, ...] = ()
    next_cursor: str | None = None

    @model_validator(mode="after")
    def validate_group(self) -> Self:
        if self.group is SearchGroup.BEST_MATCH:
            if len(self.items) > 1 or self.next_cursor is not None:
                raise ValueError("Best Match permits one item and no cursor")
        elif any(
            item.result_type is not _GROUP_TYPES[self.group]
            for item in self.items
        ):
            raise ValueError("Search item type does not match its group")
        if self.status is SearchGroupStatus.COMPLETE and not self.items:
            raise ValueError("Complete search groups require results")
        if self.status is not SearchGroupStatus.COMPLETE and (
            self.items or self.next_cursor is not None
        ):
            raise ValueError("Non-complete groups cannot contain results")
        if tuple(item.relevance for item in self.items) != tuple(
            sorted((item.relevance for item in self.items), reverse=True)
        ):
            raise ValueError("Search results must be relevance ordered")
        ids = tuple(item.result_id for item in self.items)
        if len(set(ids)) != len(ids):
            raise ValueError("Search results must be unique")
        return self


class FederatedSearchResponse(DecisionModel):
    schema_version: Literal["1"] = SEARCH_SCHEMA_VERSION
    policy_version: Literal["ask-ai-federated-search-v1"] = (
        SEARCH_POLICY_VERSION
    )
    original_query: str = Field(min_length=1)
    applied_query: str = Field(min_length=1)
    filters: SearchFilters
    correction: SearchCorrection | None = None
    groups: tuple[SearchResultGroup, ...]

    @model_validator(mode="after")
    def validate_response(self) -> Self:
        if tuple(group.group for group in self.groups) != RESPONSE_GROUP_ORDER:
            raise ValueError("Search groups require canonical order")
        if self.correction is None:
            if self.original_query != self.applied_query:
                raise ValueError("Changed query requires correction metadata")
        elif (
            self.correction.original_query != self.original_query
            or self.correction.suggested_query != self.applied_query
        ):
            raise ValueError("Correction does not match query state")
        return self


@dataclass(frozen=True)
class SearchRow:
    stable_id: str
    title: str
    subtitle: str
    why_matched: str
    relevance: int
    sort_at: datetime


@dataclass(frozen=True)
class SearchPage:
    items: tuple[SearchRow, ...]
    has_more: bool


@dataclass(frozen=True)
class SearchCursor:
    relevance: int
    sort_at: datetime
    stable_id: str


class SearchRepository:
    def __init__(self, database_session: Session) -> None:
        self._session = database_session

    def search(
        self,
        *,
        group: SearchGroup,
        user_id: UUID,
        query: str,
        original_query: str,
        filters: SearchFilters,
        limit: int,
        cursor: SearchCursor | None,
    ) -> SearchPage:
        expected_provenance = (
            "owned_research"
            if group is SearchGroup.PREVIOUS_RESEARCH
            else "internal_regulatory_corpus"
        )
        if (
            filters.provenance is not None
            and filters.provenance != expected_provenance
        ):
            return SearchPage(items=(), has_more=False)
        with self._session.begin_nested():
            rows = list(
                self._session.execute(
                    text(_SEARCH_SQL[group]),
                    {
                        "user_id": user_id,
                        "query": query,
                        "original_query": original_query,
                        "jurisdiction": filters.jurisdiction,
                        "regulator": filters.regulator,
                        "document_type": filters.document_type,
                        "entity_class": filters.entity_class,
                        "status": filters.status,
                        "stakeholder": filters.stakeholder,
                        "topic": filters.topic,
                        "lifecycle": filters.lifecycle,
                        "date_from": filters.date_from,
                        "date_to": filters.date_to,
                        "cursor_relevance": (
                            cursor.relevance if cursor is not None else None
                        ),
                        "cursor_sort_at": (
                            cursor.sort_at if cursor is not None else None
                        ),
                        "cursor_stable_id": (
                            cursor.stable_id if cursor is not None else None
                        ),
                        "query_limit": limit + 1,
                    },
                ).mappings()
            )
        retained = rows[:limit]
        return SearchPage(
            items=tuple(
                SearchRow(
                    stable_id=str(row["stable_id"]),
                    title=row["title"],
                    subtitle=row["subtitle"],
                    why_matched=row["why_matched"],
                    relevance=int(row["relevance"]),
                    sort_at=row["sort_at"] or _EPOCH,
                )
                for row in retained
            ),
            has_more=len(rows) > limit,
        )


SessionScopeFactory = Callable[[], AbstractContextManager[Session]]
SearchRepositoryFactory = Callable[[Session], SearchRepository]
EntityCatalogRepositoryFactory = Callable[[Session], EntityCatalogRepository]


class FederatedSearchUnavailable(RuntimeError):
    pass


class FederatedSearchCursorError(ValueError):
    pass


class FederatedSearchService:
    def __init__(
        self,
        session_scope_factory: SessionScopeFactory = session_scope,
        repository_factory: SearchRepositoryFactory = SearchRepository,
        catalog_repository_factory: EntityCatalogRepositoryFactory = (
            EntityCatalogRepository
        ),
    ) -> None:
        self._session_scope_factory = session_scope_factory
        self._repository_factory = repository_factory
        self._catalog_repository_factory = catalog_repository_factory

    def search(
        self,
        *,
        user_id: UUID,
        request: FederatedSearchRequest,
    ) -> FederatedSearchResponse:
        filter_key = _filter_key(request)
        cursor = _decode_cursor(
            request.cursor,
            expected_group=request.group,
            expected_filter_key=filter_key,
        )
        requested = (
            (request.group,) if request.group is not None else SEARCHABLE_GROUPS
        )
        pages: dict[SearchGroup, SearchPage] = {}
        unavailable: set[SearchGroup] = set()
        try:
            with self._session_scope_factory() as database_session:
                repository = self._repository_factory(database_session)
                try:
                    catalog = self._catalog_repository_factory(
                        database_session
                    ).list_entries()
                except Exception:
                    catalog = ()
                suggested_correction = _correction(request.query, catalog)
                correction = (
                    suggested_correction
                    if request.correction_mode == "auto"
                    else None
                )
                applied_query = (
                    correction.suggested_query
                    if correction is not None
                    else request.query
                )
                for group in requested:
                    try:
                        pages[group] = repository.search(
                            group=group,
                            user_id=user_id,
                            query=applied_query,
                            original_query=request.query,
                            filters=request.filters,
                            limit=request.limit,
                            cursor=(
                                cursor
                                if group is request.group
                                else None
                            ),
                        )
                    except Exception:
                        unavailable.add(group)
        except Exception:
            raise FederatedSearchUnavailable(
                "Federated search is unavailable"
            ) from None
        if unavailable == set(requested):
            raise FederatedSearchUnavailable(
                "Federated search is unavailable"
            )
        groups: list[SearchResultGroup] = []
        all_items: list[SearchItem] = []
        for group in SEARCHABLE_GROUPS:
            page = pages.get(group)
            if page is None:
                groups.append(
                    SearchResultGroup(
                        group=group,
                        status=(
                            SearchGroupStatus.UNAVAILABLE
                            if group in unavailable
                            else SearchGroupStatus.NOT_REQUESTED
                        ),
                    )
                )
                continue
            items = tuple(_public_item(group, row) for row in page.items)
            all_items.extend(items)
            groups.append(
                SearchResultGroup(
                    group=group,
                    status=(
                        SearchGroupStatus.COMPLETE
                        if items
                        else SearchGroupStatus.NO_MATCH
                    ),
                    items=items,
                    next_cursor=(
                        _encode_cursor(group, filter_key, page.items[-1])
                        if page.has_more and page.items
                        else None
                    ),
                )
            )
        best = max(
            all_items,
            key=lambda item: (item.relevance, item.result_id),
            default=None,
        )
        return FederatedSearchResponse(
            original_query=request.query,
            applied_query=applied_query,
            filters=request.filters,
            correction=correction,
            groups=(
                SearchResultGroup(
                    group=SearchGroup.BEST_MATCH,
                    status=(
                        SearchGroupStatus.COMPLETE
                        if best is not None
                        else (
                            SearchGroupStatus.UNAVAILABLE
                            if unavailable
                            else SearchGroupStatus.NO_MATCH
                        )
                    ),
                    items=(best,) if best is not None else (),
                ),
                *groups,
            ),
        )


def _public_item(group: SearchGroup, row: SearchRow) -> SearchItem:
    result_type = _GROUP_TYPES[group]
    route = {
        SearchGroup.ENTITIES: f"/ask?entity={quote(row.stable_id, safe='')}",
        SearchGroup.PREVIOUS_RESEARCH: (
            f"/ask?session={quote(row.stable_id, safe='')}"
        ),
        SearchGroup.AMENDMENTS: (
            f"/browse?version={quote(row.stable_id, safe='')}"
        ),
        SearchGroup.DEADLINES: (
            f"/deadlines?deadline={quote(row.stable_id, safe='')}"
        ),
    }.get(group, f"/browse?document={quote(row.stable_id, safe='')}")
    return SearchItem(
        result_id=f"{result_type.value}:{row.stable_id}",
        result_type=result_type,
        title=row.title,
        subtitle=row.subtitle,
        why_matched=row.why_matched,
        provenance=(
            "owned_research"
            if group is SearchGroup.PREVIOUS_RESEARCH
            else "internal_regulatory_corpus"
        ),
        relevance=row.relevance,
        route=route,
    )


def _correction(
    query: str,
    catalog: tuple[EntityCatalogEntry, ...],
) -> SearchCorrection | None:
    normalized = query.casefold()
    for entry in catalog:
        if any(
            alias.value.casefold() == normalized for alias in entry.aliases
        ) and entry.canonical_name.casefold() != normalized:
            return SearchCorrection(
                kind=SearchCorrectionKind.ACRONYM_EXPANSION,
                original_query=query,
                suggested_query=entry.canonical_name,
            )
    if len(normalized) < 4:
        return None
    candidates = tuple(
        (entry.canonical_name, entry.canonical_name.casefold())
        for entry in catalog
    )
    match = max(
        candidates,
        key=lambda item: SequenceMatcher(None, normalized, item[1]).ratio(),
        default=None,
    )
    if match is None:
        return None
    ratio = SequenceMatcher(None, normalized, match[1]).ratio()
    if ratio < 0.82 or match[1] == normalized:
        return None
    return SearchCorrection(
        kind=SearchCorrectionKind.SPELLING,
        original_query=query,
        suggested_query=match[0],
    )


def _filter_key(request: FederatedSearchRequest) -> str:
    value = {
        "query": request.query.casefold(),
        "correction_mode": request.correction_mode,
        "filters": request.filters.model_dump(mode="json"),
    }
    return hashlib.sha256(
        json.dumps(value, sort_keys=True, separators=(",", ":")).encode()
    ).hexdigest()


def _encode_cursor(
    group: SearchGroup,
    filter_key: str,
    row: SearchRow,
) -> str:
    value = {
        "v": 1,
        "g": group.value,
        "f": filter_key,
        "r": row.relevance,
        "t": row.sort_at.isoformat(),
        "i": row.stable_id,
    }
    return base64.urlsafe_b64encode(
        json.dumps(value, separators=(",", ":")).encode()
    ).decode()


def _decode_cursor(
    cursor: str | None,
    *,
    expected_group: SearchGroup | None,
    expected_filter_key: str,
) -> SearchCursor | None:
    if cursor is None:
        return None
    try:
        value = json.loads(base64.urlsafe_b64decode(cursor.encode()))
        if (
            value.get("v") != 1
            or value.get("g") != expected_group.value
            or value.get("f") != expected_filter_key
        ):
            raise ValueError
        sort_at = datetime.fromisoformat(value["t"])
        relevance = int(value["r"])
        stable_id = str(value["i"])
        if (
            sort_at.tzinfo is None
            or not 0 <= relevance <= 1000
            or not stable_id
        ):
            raise ValueError
    except (AttributeError, KeyError, TypeError, ValueError, json.JSONDecodeError):
        raise FederatedSearchCursorError(
            "Invalid federated search cursor"
        ) from None
    return SearchCursor(relevance, sort_at, stable_id)


_CURSOR_SQL = """
and (
  cast(:cursor_relevance as integer) is null
  or relevance < :cursor_relevance
  or (
    relevance = :cursor_relevance
    and (
      sort_at < :cursor_sort_at
      or (
        sort_at = :cursor_sort_at
        and stable_id < :cursor_stable_id
      )
    )
  )
)
order by relevance desc, sort_at desc, stable_id desc
limit :query_limit
"""

_ENTITY_SQL = """
with search_query as (
  select (
    plainto_tsquery('simple', :query)
    || plainto_tsquery('simple', :original_query)
  ) value, lower(:query) exact
),
ranked as (
  select entity.canonical_id stable_id, entity.canonical_name title,
    entity.entity_class || ' · ' || entity.jurisdiction subtitle,
    case when lower(entity.canonical_name) = search_query.exact
      then 'Exact canonical entity name matched.'
      when exists (
        select 1 from public.regulatory_entity_aliases alias
        where alias.canonical_id = entity.canonical_id
          and lower(alias.alias) = search_query.exact
      ) then 'Approved entity alias or acronym matched.'
      else 'Canonical entity metadata matched the search terms.'
    end why_matched,
    case when lower(entity.canonical_name) = search_query.exact then 1000
      when exists (
        select 1 from public.regulatory_entity_aliases alias
        where alias.canonical_id = entity.canonical_id
          and lower(alias.alias) = search_query.exact
      ) then 950 else 700 end relevance,
    entity.updated_at sort_at
  from public.regulatory_entity_catalog entity cross join search_query
  where (
    (
      setweight(
        to_tsvector('simple', coalesce(entity.canonical_name, '')), 'A'
      )
      || setweight(
        to_tsvector('simple', coalesce(entity.entity_class, '')), 'B'
      )
      || setweight(
        to_tsvector('simple', coalesce(entity.jurisdiction, '')), 'B'
      )
    ) @@ search_query.value
    or exists (
      select 1 from public.regulatory_entity_aliases alias
      where alias.canonical_id = entity.canonical_id
        and (
          setweight(
            to_tsvector('simple', coalesce(alias.alias, '')), 'A'
          )
          || setweight(
            to_tsvector('simple', coalesce(alias.jurisdiction, '')), 'B'
          )
        ) @@ search_query.value
    )
  )
  and (cast(:jurisdiction as text) is null
    or entity.jurisdiction ilike '%' || :jurisdiction || '%')
  and (cast(:entity_class as text) is null
    or entity.entity_class = :entity_class)
  and (cast(:status as text) is null
    or entity.metadata ->> 'status' ilike '%' || :status || '%')
  and (cast(:stakeholder as text) is null
    or (
      entity.entity_class = 'stakeholder'
      and entity.canonical_name ilike '%' || :stakeholder || '%'
    ))
  and (cast(:topic as text) is null
    or entity.metadata::text ilike '%' || :topic || '%')
  and (cast(:lifecycle as text) is null
    or lower(entity.metadata ->> 'lifecycle') = lower(:lifecycle))
  and (cast(:date_from as date) is null
    or entity.updated_at::date >= :date_from)
  and (cast(:date_to as date) is null
    or entity.updated_at::date <= :date_to)
)
select * from ranked where true
""" + _CURSOR_SQL

_DOCUMENT_SQL = """
with search_query as (
  select (
    plainto_tsquery('simple', :query)
    || plainto_tsquery('simple', :original_query)
  ) value, lower(:query) exact
),
ranked as (
  select document.id::text stable_id, document.title,
    coalesce(document.issuing_body, 'Issuer not established') || ' · '
      || coalesce(document.doc_type, 'Document type not established') subtitle,
    case when lower(document.title) = search_query.exact
      then 'Exact official document title matched.'
      else 'Official document metadata matched the search terms.'
    end why_matched,
    case when lower(document.title) = search_query.exact then 900 else 650 end
      relevance,
    document.created_at sort_at,
    lower(coalesce(document.doc_type, '')) normalized_type,
    lower(document.title) normalized_title
  from public.documents document cross join search_query
  where (
    setweight(
      to_tsvector('simple', coalesce(document.title, '')), 'A'
    )
    || setweight(
      to_tsvector('simple', coalesce(document.issuing_body, '')), 'B'
    )
    || setweight(
      to_tsvector('simple', coalesce(document.doc_type, '')), 'B'
    )
  ) @@ search_query.value
  and (cast(:jurisdiction as text) is null
    or document.jurisdiction::text = lower(:jurisdiction))
  and (cast(:regulator as text) is null
    or document.issuing_body ilike '%' || :regulator || '%')
  and (cast(:document_type as text) is null
    or document.doc_type ilike '%' || :document_type || '%')
  and (cast(:date_from as date) is null or document.issue_date >= :date_from)
  and (cast(:date_to as date) is null or document.issue_date <= :date_to)
  and (cast(:status as text) is null or exists (
    select 1 from public.events event
    where event.document_id = document.id
      and lower(event.event_type::text) = lower(:status)
  ))
  and (cast(:stakeholder as text) is null or exists (
    select 1 from public.regulatory_graph_stakeholders stakeholder
    where stakeholder.document_id = document.id
      and stakeholder.stakeholder ilike '%' || :stakeholder || '%'
  ))
  and (cast(:topic as text) is null or exists (
    select 1 from public.events event,
      unnest(event.topic_tags) topic_tag
    where event.document_id = document.id
      and topic_tag ilike '%' || :topic || '%'
  ))
  and (
    cast(:lifecycle as text) is null
    or (
      :lifecycle = 'current'
      and not exists (
        select 1 from public.document_version_registry state
        where state.document_id = document.id
          and state.superseded_by_registry_version_id is not null
      )
    )
    or (
      :lifecycle = 'superseded'
      and exists (
        select 1 from public.document_version_registry state
        where state.document_id = document.id
          and state.superseded_by_registry_version_id is not null
      )
    )
    or (
      :lifecycle = 'draft'
      and (
        document.doc_type ilike '%draft%'
        or document.title ilike '%draft%'
      )
    )
  )
)
select stable_id, title, subtitle, why_matched, relevance, sort_at
from ranked where {filter}
""" + _CURSOR_SQL

_AMENDMENT_SQL = """
with search_query as (
  select (
    plainto_tsquery('simple', :query)
    || plainto_tsquery('simple', :original_query)
  ) value
),
ranked as (
  select registry.registry_version_id::text stable_id,
    coalesce(registry.amendment_label, registry.version_label, document.title)
      title,
    document.title || ' · '
      || coalesce(document.issuing_body, 'Issuer not established') subtitle,
    'Official amendment/version metadata matched the search terms.'
      why_matched,
    700 relevance, registry.created_at sort_at
  from public.document_version_registry registry
  join public.documents document on document.id = registry.document_id
  cross join search_query
  where registry.amendment_number is not null
  and (
    (
      setweight(
        to_tsvector('simple', coalesce(registry.version_label, '')), 'A'
      )
      || setweight(
        to_tsvector('simple', coalesce(registry.amendment_label, '')), 'A'
      )
      || setweight(
        to_tsvector(
          'simple', coalesce(registry.referenced_instrument, '')
        ), 'B'
      )
      || setweight(
        to_tsvector(
          'simple', coalesce(registry.referenced_notification, '')
        ), 'B'
      )
    ) @@ search_query.value
    or (
      setweight(
        to_tsvector('simple', coalesce(document.title, '')), 'A'
      )
      || setweight(
        to_tsvector('simple', coalesce(document.issuing_body, '')), 'B'
      )
      || setweight(
        to_tsvector('simple', coalesce(document.doc_type, '')), 'B'
      )
    ) @@ search_query.value
  )
  and (cast(:regulator as text) is null
    or document.issuing_body ilike '%' || :regulator || '%')
  and (cast(:date_from as date) is null
    or registry.publication_date >= :date_from)
  and (cast(:date_to as date) is null
    or registry.publication_date <= :date_to)
  and (cast(:jurisdiction as text) is null
    or document.jurisdiction::text = lower(:jurisdiction))
  and (cast(:document_type as text) is null
    or document.doc_type ilike '%' || :document_type || '%')
  and (cast(:status as text) is null or exists (
    select 1 from public.events event
    where event.document_id = document.id
      and lower(event.event_type::text) = lower(:status)
  ))
  and (cast(:stakeholder as text) is null or exists (
    select 1 from public.regulatory_graph_stakeholders stakeholder
    where stakeholder.document_id = document.id
      and stakeholder.stakeholder ilike '%' || :stakeholder || '%'
  ))
  and (cast(:topic as text) is null or exists (
    select 1 from public.events event,
      unnest(event.topic_tags) topic_tag
    where event.document_id = document.id
      and topic_tag ilike '%' || :topic || '%'
  ))
  and (
    cast(:lifecycle as text) is null
    or (
      :lifecycle = 'current'
      and registry.superseded_by_registry_version_id is null
    )
    or (
      :lifecycle = 'superseded'
      and registry.superseded_by_registry_version_id is not null
    )
    or (
      :lifecycle = 'draft'
      and (
        document.doc_type ilike '%draft%'
        or document.title ilike '%draft%'
      )
    )
  )
)
select * from ranked where true
""" + _CURSOR_SQL

_DEADLINE_SQL = """
with search_query as (
  select (
    plainto_tsquery('simple', :query)
    || plainto_tsquery('simple', :original_query)
  ) value
),
ranked as (
  select deadline.deadline_id::text stable_id, deadline.deadline_type title,
    coalesce(deadline.deadline_date::text, deadline.raw_date,
      'Date not established') || ' · ' || document.title subtitle,
    'Extracted official deadline metadata matched the search terms.'
      why_matched,
    675 relevance, deadline.created_at sort_at
  from public.deadline_history deadline
  join public.documents document on document.id = deadline.document_id
  cross join search_query
  where (
    (
      setweight(
        to_tsvector('simple', coalesce(deadline.deadline_type, '')), 'A'
      )
      || setweight(
        to_tsvector('simple', coalesce(deadline.raw_date, '')), 'B'
      )
      || setweight(
        to_tsvector('simple', coalesce(deadline.extracted_from, '')), 'C'
      )
    ) @@ search_query.value
    or (
      setweight(
        to_tsvector('simple', coalesce(document.title, '')), 'A'
      )
      || setweight(
        to_tsvector('simple', coalesce(document.issuing_body, '')), 'B'
      )
      || setweight(
        to_tsvector('simple', coalesce(document.doc_type, '')), 'B'
      )
    ) @@ search_query.value
  )
  and (cast(:regulator as text) is null
    or document.issuing_body ilike '%' || :regulator || '%')
  and (cast(:date_from as date) is null
    or deadline.deadline_date >= :date_from)
  and (cast(:date_to as date) is null
    or deadline.deadline_date <= :date_to)
  and (cast(:jurisdiction as text) is null
    or document.jurisdiction::text = lower(:jurisdiction))
  and (cast(:document_type as text) is null
    or document.doc_type ilike '%' || :document_type || '%')
  and (cast(:status as text) is null or exists (
    select 1 from public.events event
    where event.document_id = document.id
      and lower(event.event_type::text) = lower(:status)
  ))
  and (cast(:stakeholder as text) is null or exists (
    select 1 from public.regulatory_graph_stakeholders stakeholder
    where stakeholder.document_id = document.id
      and stakeholder.stakeholder ilike '%' || :stakeholder || '%'
  ))
  and (cast(:topic as text) is null or exists (
    select 1 from public.events event,
      unnest(event.topic_tags) topic_tag
    where event.document_id = document.id
      and topic_tag ilike '%' || :topic || '%'
  ))
  and (
    cast(:lifecycle as text) is null
    or (
      :lifecycle = 'current'
      and (
        deadline.registry_version_id is null
        or not exists (
          select 1 from public.document_version_registry state
          where state.registry_version_id = deadline.registry_version_id
            and state.superseded_by_registry_version_id is not null
        )
      )
    )
    or (
      :lifecycle = 'superseded'
      and exists (
        select 1 from public.document_version_registry state
        where state.registry_version_id = deadline.registry_version_id
          and state.superseded_by_registry_version_id is not null
      )
    )
    or (
      :lifecycle = 'draft'
      and (
        document.doc_type ilike '%draft%'
        or document.title ilike '%draft%'
      )
    )
  )
)
select * from ranked where true
""" + _CURSOR_SQL

_SESSION_SQL = """
with search_query as (
  select (
    plainto_tsquery('simple', :query)
    || plainto_tsquery('simple', :original_query)
  ) value
),
matches as (
  select session.id stable_id, 500 relevance
  from public.chat_sessions session cross join search_query
  where session.user_id = :user_id
  and (
    setweight(
      to_tsvector('simple', coalesce(session.title, '')), 'A'
    )
    || setweight(
      to_tsvector('simple', coalesce(session.primary_entity, '')), 'B'
    )
    || setweight(
      to_tsvector('simple', coalesce(session.primary_topic, '')), 'C'
    )
  ) @@ search_query.value
  union all
  select message.session_id, 400
  from public.chat_messages message cross join search_query
  where message.user_id = :user_id and message.session_id is not null
    and to_tsvector('simple', message.content) @@ search_query.value
),
match_rank as (
  select stable_id, max(relevance)::integer relevance
  from matches group by stable_id
),
ranked as (
  select session.id::text stable_id, session.title,
    coalesce(session.primary_entity, 'Entity not established')
      || ' · Previous Research' subtitle,
    'Your previous research title or content matched the search terms.'
      why_matched,
    match_rank.relevance, session.updated_at sort_at
  from match_rank
  join public.chat_sessions session on session.id = match_rank.stable_id
  where session.user_id = :user_id and session.deleted_at is null
  and (cast(:jurisdiction as text) is null
    or session.scope_snapshot::text ilike '%' || :jurisdiction || '%')
  and (cast(:regulator as text) is null
    or session.scope_snapshot::text ilike '%' || :regulator || '%')
  and (cast(:document_type as text) is null
    or session.scope_snapshot::text ilike '%' || :document_type || '%')
  and (cast(:entity_class as text) is null
    or session.scope_snapshot::text ilike '%' || :entity_class || '%')
  and (cast(:status as text) is null
    or lower(session.status) = lower(:status))
  and (cast(:stakeholder as text) is null
    or session.scope_snapshot::text ilike '%' || :stakeholder || '%')
  and (cast(:topic as text) is null
    or session.primary_topic ilike '%' || :topic || '%')
  and (
    cast(:lifecycle as text) is null
    or (:lifecycle = 'current' and session.archived_at is null)
    or (:lifecycle = 'draft' and lower(session.status) = 'draft')
  )
  and (cast(:date_from as date) is null
    or session.updated_at::date >= :date_from)
  and (cast(:date_to as date) is null
    or session.updated_at::date <= :date_to)
)
select * from ranked where true
""" + _CURSOR_SQL

_SEARCH_SQL = {
    SearchGroup.ENTITIES: _ENTITY_SQL,
    SearchGroup.OFFICIAL_REGULATIONS: _DOCUMENT_SQL.format(
        filter=(
            "(normalized_type like '%regulation%' "
            "or normalized_type like '%rule%' "
            "or normalized_type like '%act%') "
            "and normalized_type not like '%consultation%'"
        )
    ),
    SearchGroup.OFFICIAL_DOCUMENTS: _DOCUMENT_SQL.format(
        filter=(
            "normalized_type not like '%regulation%' "
            "and normalized_type not like '%rule%' "
            "and normalized_type not like '%act%' "
            "and normalized_type not like '%consultation%' "
            "and normalized_title not like '%consultation%'"
        )
    ),
    SearchGroup.AMENDMENTS: _AMENDMENT_SQL,
    SearchGroup.CONSULTATIONS: _DOCUMENT_SQL.format(
        filter=(
            "(normalized_type like '%consultation%' "
            "or normalized_title like '%consultation%')"
        )
    ),
    SearchGroup.DEADLINES: _DEADLINE_SQL,
    SearchGroup.PREVIOUS_RESEARCH: _SESSION_SQL,
}
