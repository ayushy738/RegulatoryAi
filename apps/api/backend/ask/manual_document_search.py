from __future__ import annotations

import base64
import hashlib
import json
from collections.abc import Callable
from contextlib import AbstractContextManager
from dataclasses import dataclass
from datetime import UTC, date, datetime
from typing import Literal, Self
from urllib.parse import quote

from pydantic import Field, field_validator, model_validator
from sqlalchemy import text
from sqlalchemy.orm import Session

from backend.ask.decision.models import DecisionModel
from backend.core.db import session_scope

MANUAL_SEARCH_SCHEMA_VERSION = "1"
MANUAL_SEARCH_POLICY_VERSION = "ask-ai-manual-document-search-v1"
_MIN_DATE = date(1, 1, 1)


class ManualDocumentSearchRequest(DecisionModel):
    schema_version: Literal["1"] = MANUAL_SEARCH_SCHEMA_VERSION
    document_id: int | None = Field(default=None, gt=0)
    registry_version_id: int | None = Field(default=None, gt=0)
    query: str | None = Field(default=None, max_length=500)
    exact_phrase: bool = False
    title: str | None = Field(default=None, max_length=500)
    issuer: str | None = Field(default=None, max_length=300)
    document_number: str | None = Field(default=None, max_length=300)
    document_type: str | None = Field(default=None, max_length=200)
    family: str | None = Field(default=None, max_length=500)
    version: str | None = Field(default=None, max_length=300)
    status: Literal["current", "superseded", "draft"] | None = None
    issued_from: date | None = None
    issued_to: date | None = None
    effective_from: date | None = None
    effective_to: date | None = None
    within_document: str | None = Field(default=None, max_length=500)
    cursor: str | None = Field(default=None, max_length=2_000)
    limit: int = Field(default=20, ge=1, le=50)

    @field_validator(
        "query",
        "title",
        "issuer",
        "document_number",
        "document_type",
        "family",
        "version",
        "within_document",
    )
    @classmethod
    def normalize_text(cls, value: str | None) -> str | None:
        if value is None:
            return None
        normalized = " ".join(value.split())
        if not normalized:
            raise ValueError("Manual search text cannot be blank")
        return normalized

    @model_validator(mode="after")
    def validate_search(self) -> Self:
        if self.exact_phrase and self.query is None:
            raise ValueError("Exact phrase mode requires a query")
        if (
            self.issued_from is not None
            and self.issued_to is not None
            and self.issued_from > self.issued_to
        ):
            raise ValueError("Issue date range cannot be reversed")
        if (
            self.effective_from is not None
            and self.effective_to is not None
            and self.effective_from > self.effective_to
        ):
            raise ValueError("Effective date range cannot be reversed")
        criteria = (
            self.document_id,
            self.registry_version_id,
            self.query,
            self.title,
            self.issuer,
            self.document_number,
            self.document_type,
            self.family,
            self.version,
            self.status,
            self.issued_from,
            self.issued_to,
            self.effective_from,
            self.effective_to,
            self.within_document,
        )
        if not any(value is not None for value in criteria):
            raise ValueError("Manual search requires at least one criterion")
        return self


class WithinDocumentMatch(DecisionModel):
    chunk_id: int = Field(gt=0)
    page_number: int | None = Field(default=None, ge=1)
    section_title: str | None = Field(default=None, max_length=500)
    excerpt: str = Field(min_length=1, max_length=800)


class ManualDocumentSearchItem(DecisionModel):
    result_id: str = Field(pattern=r"^document:[1-9][0-9]*(:[1-9][0-9]*)?$")
    document_id: int = Field(gt=0)
    registry_version_id: int | None = Field(default=None, gt=0)
    document_version_id: int | None = Field(default=None, gt=0)
    family_id: int | None = Field(default=None, gt=0)
    title: str = Field(min_length=1, max_length=1_000)
    issuer: str | None = Field(default=None, max_length=500)
    document_number: str | None = Field(default=None, max_length=500)
    document_type: str | None = Field(default=None, max_length=300)
    jurisdiction: str | None = Field(default=None, max_length=200)
    issue_date: date | None = None
    publication_date: date | None = None
    effective_date: date | None = None
    family_title: str | None = Field(default=None, max_length=1_000)
    version_label: str | None = Field(default=None, max_length=500)
    status: Literal["current", "superseded", "draft", "not_established"]
    metadata_state: Literal["complete", "partial"]
    why_matched: str = Field(min_length=1, max_length=1_000)
    relevance: int = Field(ge=0, le=1_000)
    source_url: str = Field(
        max_length=2_000,
        pattern=r"^https?://[^\s]+$",
    )
    route: str = Field(
        min_length=1,
        max_length=2_000,
        pattern=r"^/[A-Za-z0-9/?=&%._:-]+$",
    )
    within_document_matches: tuple[WithinDocumentMatch, ...] = ()

    @model_validator(mode="after")
    def validate_identity(self) -> Self:
        suffix = (
            f":{self.registry_version_id}"
            if self.registry_version_id is not None
            else ""
        )
        if self.result_id != f"document:{self.document_id}{suffix}":
            raise ValueError("Manual result identity does not match its document")
        if self.metadata_state == "complete" and (
            self.issuer is None
            or self.document_type is None
            or self.issue_date is None
        ):
            raise ValueError("Complete document metadata requires core fields")
        return self


class ManualDocumentSearchResponse(DecisionModel):
    schema_version: Literal["1"] = MANUAL_SEARCH_SCHEMA_VERSION
    policy_version: Literal["ask-ai-manual-document-search-v1"] = (
        MANUAL_SEARCH_POLICY_VERSION
    )
    status: Literal["complete", "no_match"]
    as_of: date
    items: tuple[ManualDocumentSearchItem, ...]
    next_cursor: str | None = None

    @model_validator(mode="after")
    def validate_response(self) -> Self:
        if (self.status == "complete") != bool(self.items):
            raise ValueError("Manual search status must agree with its results")
        if self.status == "no_match" and self.next_cursor is not None:
            raise ValueError("No-match manual search cannot have a cursor")
        keys = tuple(
            (
                item.relevance,
                item.effective_date
                or item.publication_date
                or item.issue_date
                or _MIN_DATE,
                item.document_id,
                item.registry_version_id or 0,
            )
            for item in self.items
        )
        if keys != tuple(sorted(keys, reverse=True)):
            raise ValueError("Manual results require deterministic order")
        if len({item.result_id for item in self.items}) != len(self.items):
            raise ValueError("Manual results must be unique")
        return self


@dataclass(frozen=True)
class ManualSearchCursor:
    as_of: date
    relevance: int
    sort_date: date
    document_id: int
    registry_version_id: int


class ManualDocumentSearchCursorError(ValueError):
    pass


class ManualDocumentSearchUnavailable(RuntimeError):
    pass


class ManualDocumentSearchRepository:
    def __init__(self, database_session: Session) -> None:
        self._session = database_session

    def search(
        self,
        *,
        request: ManualDocumentSearchRequest,
        as_of: date,
        cursor: ManualSearchCursor | None,
    ) -> tuple[tuple[ManualDocumentSearchItem, ...], bool]:
        with self._session.begin_nested():
            rows = list(
                self._session.execute(
                    text(_MANUAL_DOCUMENT_SEARCH_SQL),
                    {
                        **request.model_dump(
                            mode="python",
                            exclude={"cursor", "limit", "schema_version"},
                        ),
                        "as_of": as_of,
                        "cursor_relevance": (
                            cursor.relevance if cursor is not None else None
                        ),
                        "cursor_sort_date": (
                            cursor.sort_date if cursor is not None else None
                        ),
                        "cursor_document_id": (
                            cursor.document_id if cursor is not None else None
                        ),
                        "cursor_registry_version_id": (
                            cursor.registry_version_id
                            if cursor is not None
                            else None
                        ),
                        "query_limit": request.limit + 1,
                    },
                ).mappings()
            )
        retained = rows[: request.limit]
        return (
            tuple(_item_from_row(row) for row in retained),
            len(rows) > request.limit,
        )


SessionScopeFactory = Callable[[], AbstractContextManager[Session]]
RepositoryFactory = Callable[[Session], ManualDocumentSearchRepository]
Clock = Callable[[], datetime]


class ManualDocumentSearchService:
    def __init__(
        self,
        session_scope_factory: SessionScopeFactory = session_scope,
        repository_factory: RepositoryFactory = ManualDocumentSearchRepository,
        clock: Clock = lambda: datetime.now(UTC),
    ) -> None:
        self._session_scope_factory = session_scope_factory
        self._repository_factory = repository_factory
        self._clock = clock

    def search(
        self,
        request: ManualDocumentSearchRequest,
    ) -> ManualDocumentSearchResponse:
        filter_key = _filter_key(request)
        cursor = _decode_cursor(request.cursor, filter_key)
        if cursor is not None:
            as_of = cursor.as_of
        else:
            now = self._clock()
            if now.tzinfo is None:
                raise ManualDocumentSearchUnavailable(
                    "Manual document search is unavailable"
                )
            as_of = now.astimezone(UTC).date()
        try:
            with self._session_scope_factory() as database_session:
                items, has_more = self._repository_factory(
                    database_session
                ).search(request=request, as_of=as_of, cursor=cursor)
        except Exception:
            raise ManualDocumentSearchUnavailable(
                "Manual document search is unavailable"
            ) from None
        return ManualDocumentSearchResponse(
            status="complete" if items else "no_match",
            as_of=as_of,
            items=items,
            next_cursor=(
                _encode_cursor(filter_key, as_of, items[-1])
                if has_more and items
                else None
            ),
        )


def _item_from_row(row: object) -> ManualDocumentSearchItem:
    values = row
    registry_version_id = values["registry_version_id"]
    document_id = int(values["document_id"])
    result_id = f"document:{document_id}"
    route = f"/browse?document={document_id}"
    if registry_version_id is not None:
        result_id += f":{registry_version_id}"
        route += f"&version={quote(str(registry_version_id), safe='')}"
    match = (
        (
            WithinDocumentMatch(
                chunk_id=int(values["chunk_id"]),
                page_number=values["page_number"],
                section_title=values["section_title"],
                excerpt=values["excerpt"],
            ),
        )
        if values["chunk_id"] is not None
        else ()
    )
    return ManualDocumentSearchItem(
        result_id=result_id,
        document_id=document_id,
        registry_version_id=registry_version_id,
        document_version_id=values["document_version_id"],
        family_id=values["family_id"],
        title=values["title"],
        issuer=values["issuer"],
        document_number=values["document_number"],
        document_type=values["document_type"],
        jurisdiction=values["jurisdiction"],
        issue_date=values["issue_date"],
        publication_date=values["publication_date"],
        effective_date=values["effective_date"],
        family_title=values["family_title"],
        version_label=values["version_label"],
        status=values["status"],
        metadata_state=(
            "complete"
            if (
                values["issuer"] is not None
                and values["document_type"] is not None
                and values["issue_date"] is not None
            )
            else "partial"
        ),
        why_matched=values["why_matched"],
        relevance=int(values["relevance"]),
        source_url=values["source_url"],
        route=route,
        within_document_matches=match,
    )


def _filter_key(request: ManualDocumentSearchRequest) -> str:
    value = request.model_dump(
        mode="json",
        exclude={"cursor", "limit", "schema_version"},
    )
    return hashlib.sha256(
        json.dumps(value, sort_keys=True, separators=(",", ":")).encode()
    ).hexdigest()


def _encode_cursor(
    filter_key: str,
    as_of: date,
    item: ManualDocumentSearchItem,
) -> str:
    value = {
        "v": 1,
        "f": filter_key,
        "a": as_of.isoformat(),
        "r": item.relevance,
        "t": (
            item.effective_date
            or item.publication_date
            or item.issue_date
            or _MIN_DATE
        ).isoformat(),
        "d": item.document_id,
        "x": item.registry_version_id or 0,
    }
    return base64.urlsafe_b64encode(
        json.dumps(value, separators=(",", ":")).encode()
    ).decode()


def _decode_cursor(
    cursor: str | None,
    expected_filter_key: str,
) -> ManualSearchCursor | None:
    if cursor is None:
        return None
    try:
        value = json.loads(base64.urlsafe_b64decode(cursor.encode()))
        result = ManualSearchCursor(
            as_of=date.fromisoformat(value["a"]),
            relevance=int(value["r"]),
            sort_date=date.fromisoformat(value["t"]),
            document_id=int(value["d"]),
            registry_version_id=int(value["x"]),
        )
        if (
            value.get("v") != 1
            or value.get("f") != expected_filter_key
            or not 0 <= result.relevance <= 1_000
            or result.document_id <= 0
            or result.registry_version_id < 0
        ):
            raise ValueError
    except (
        KeyError,
        TypeError,
        ValueError,
        json.JSONDecodeError,
    ):
        raise ManualDocumentSearchCursorError(
            "Invalid manual document search cursor"
        ) from None
    return result


_DOCUMENT_VECTOR = """
(
  setweight(to_tsvector('simple', coalesce(document.title, '')), 'A')
  || setweight(
    to_tsvector('simple', coalesce(document.issuing_body, '')), 'B'
  )
  || setweight(to_tsvector('simple', coalesce(document.doc_type, '')), 'B')
)
"""
_FAMILY_VECTOR = """
(
  setweight(to_tsvector('simple', coalesce(family.canonical_title, '')), 'A')
  || setweight(to_tsvector('simple', coalesce(family.issuer, '')), 'B')
  || setweight(
    to_tsvector('simple', coalesce(family.document_type, '')), 'B'
  )
)
"""
_VERSION_VECTOR = """
(
  setweight(
    to_tsvector('simple', coalesce(registry.version_label, '')), 'A'
  )
  || setweight(
    to_tsvector('simple', coalesce(registry.amendment_label, '')), 'A'
  )
  || setweight(
    to_tsvector('simple', coalesce(registry.referenced_instrument, '')), 'B'
  )
  || setweight(
    to_tsvector('simple', coalesce(registry.referenced_notification, '')), 'B'
  )
)
"""

_MANUAL_DOCUMENT_SEARCH_SQL = f"""
with search_input as (
  select
    case when cast(:query as text) is null then null
      else websearch_to_tsquery('simple', :query)
    end query_terms
),
candidate_rows as (
  select
    document.id document_id,
    registry.registry_version_id,
    registry.document_version_id,
    family.family_id,
    document.title,
    document.issuing_body issuer,
    coalesce(
      registry.referenced_instrument,
      registry.referenced_notification
    ) document_number,
    document.doc_type document_type,
    document.jurisdiction::text jurisdiction,
    coalesce(registry.issue_date, document.issue_date) issue_date,
    registry.publication_date,
    registry.effective_date,
    family.canonical_title family_title,
    registry.version_label,
    document.source_url,
    case
      when registry.registry_version_id is null then 'not_established'
      when registry.superseded_by_registry_version_id is not null
        then 'superseded'
      when registry.publication_date > :as_of
        or registry.effective_date > :as_of
        or registry.version_label ilike '%draft%'
        or document.doc_type ilike '%draft%'
        or document.title ilike '%draft%'
        then 'draft'
      else 'current'
    end status,
    case
      when cast(:query as text) is null then 500
      when lower(document.title) = lower(:query) then 1000
      when cast(:exact_phrase as boolean) and (
        strpos(
          lower(
            document.title || ' '
            || coalesce(document.issuing_body, '') || ' '
            || coalesce(document.doc_type, '') || ' '
            || coalesce(family.canonical_title, '') || ' '
            || coalesce(registry.version_label, '') || ' '
            || coalesce(registry.referenced_instrument, '') || ' '
            || coalesce(registry.referenced_notification, '')
          ),
          lower(:query)
        ) > 0
      ) then 900
      when chunk_match.chunk_id is not null then 800
      else 700
    end relevance,
    case
      when cast(:query as text) is null
        then 'Exact manual document filters matched.'
      when lower(document.title) = lower(:query)
        then 'Exact official document title matched.'
      when chunk_match.chunk_id is not null
        then 'Official within-document text matched.'
      when cast(:exact_phrase as boolean)
        then 'Exact official document metadata phrase matched.'
      else 'Official document, family, or version metadata matched.'
    end why_matched,
    coalesce(
      registry.effective_date,
      registry.publication_date,
      registry.issue_date,
      document.issue_date,
      date '0001-01-01'
    ) sort_date,
    chunk_match.chunk_id,
    chunk_match.page_number,
    chunk_match.section_title,
    chunk_match.excerpt
  from public.documents document
  left join lateral (
    select candidate.*
    from public.document_version_registry candidate
    where candidate.document_id = document.id
      and (
        cast(:registry_version_id as bigint) is null
        or candidate.registry_version_id = :registry_version_id
      )
      and (
        cast(:version as text) is null
        or strpos(
          lower(
            coalesce(candidate.version_label, '') || ' '
            || coalesce(candidate.amendment_label, '') || ' '
            || coalesce(candidate.referenced_instrument, '') || ' '
            || coalesce(candidate.referenced_notification, '')
          ),
          lower(:version)
        ) > 0
      )
    order by
      coalesce(
        candidate.publication_date,
        candidate.issue_date,
        candidate.effective_date,
        date '0001-01-01'
      ) desc,
      candidate.registry_version_id desc
    limit 1
  ) registry on true
  left join public.document_family_assignments assignment
    on assignment.document_id = document.id
  left join public.document_families family
    on family.family_id = coalesce(registry.family_id, assignment.family_id)
  cross join search_input
  left join lateral (
    select
      chunk.id chunk_id,
      chunk.page_number,
      chunk.section_title,
      left(regexp_replace(chunk.text, '\\s+', ' ', 'g'), 800) excerpt
    from public.document_chunks chunk
    where chunk.document_id = document.id
      and (
        registry.document_version_id is null
        or chunk.version_id = registry.document_version_id
      )
      and (
        (
          cast(:within_document as text) is not null
          and strpos(lower(chunk.text), lower(:within_document)) > 0
        )
        or (
          cast(:within_document as text) is null
          and cast(:query as text) is not null
          and (
            (
              cast(:exact_phrase as boolean)
              and strpos(lower(chunk.text), lower(:query)) > 0
            )
            or (
              not cast(:exact_phrase as boolean)
              and chunk.search_vector
                @@ websearch_to_tsquery('english', :query)
            )
          )
        )
      )
    order by chunk.page_number nulls last, chunk.chunk_index, chunk.id
    limit 1
  ) chunk_match on true
  where (
    cast(:document_id as bigint) is null
    or document.id = :document_id
  )
  and (
    cast(:registry_version_id as bigint) is null
    or registry.registry_version_id = :registry_version_id
  )
  and (
    cast(:version as text) is null
    or registry.registry_version_id is not null
  )
  and (
    cast(:query as text) is null
    or (
      cast(:exact_phrase as boolean)
      and (
        strpos(
          lower(
            document.title || ' '
            || coalesce(document.issuing_body, '') || ' '
            || coalesce(document.doc_type, '') || ' '
            || coalesce(family.canonical_title, '') || ' '
            || coalesce(registry.version_label, '') || ' '
            || coalesce(registry.referenced_instrument, '') || ' '
            || coalesce(registry.referenced_notification, '')
          ),
          lower(:query)
        ) > 0
        or exists (
          select 1 from public.document_chunks query_chunk
          where query_chunk.document_id = document.id
            and (
              registry.document_version_id is null
              or query_chunk.version_id = registry.document_version_id
            )
            and strpos(lower(query_chunk.text), lower(:query)) > 0
        )
      )
    )
    or (
      not cast(:exact_phrase as boolean)
      and (
        {_DOCUMENT_VECTOR} @@ search_input.query_terms
        or {_FAMILY_VECTOR} @@ search_input.query_terms
        or {_VERSION_VECTOR} @@ search_input.query_terms
        or exists (
          select 1 from public.document_chunks query_chunk
          where query_chunk.document_id = document.id
            and (
              registry.document_version_id is null
              or query_chunk.version_id = registry.document_version_id
            )
            and query_chunk.search_vector
              @@ websearch_to_tsquery('english', :query)
        )
      )
    )
  )
  and (
    cast(:title as text) is null
    or strpos(lower(document.title), lower(:title)) > 0
  )
  and (
    cast(:issuer as text) is null
    or strpos(lower(coalesce(document.issuing_body, '')), lower(:issuer)) > 0
  )
  and (
    cast(:document_number as text) is null
    or (
      strpos(
        lower(
          coalesce(registry.referenced_instrument, '') || ' '
          || coalesce(registry.referenced_notification, '')
        ),
        lower(:document_number)
      ) > 0
      or strpos(lower(document.title), lower(:document_number)) > 0
    )
  )
  and (
    cast(:document_type as text) is null
    or strpos(lower(coalesce(document.doc_type, '')), lower(:document_type)) > 0
  )
  and (
    cast(:family as text) is null
    or strpos(
      lower(coalesce(family.canonical_title, '')),
      lower(:family)
    ) > 0
  )
  and (
    cast(:issued_from as date) is null
    or coalesce(registry.issue_date, document.issue_date) >= :issued_from
  )
  and (
    cast(:issued_to as date) is null
    or coalesce(registry.issue_date, document.issue_date) <= :issued_to
  )
  and (
    cast(:effective_from as date) is null
    or registry.effective_date >= :effective_from
  )
  and (
    cast(:effective_to as date) is null
    or registry.effective_date <= :effective_to
  )
  and (
    cast(:within_document as text) is null
    or chunk_match.chunk_id is not null
  )
),
filtered as (
  select * from candidate_rows
  where cast(:status as text) is null or status = :status
)
select * from filtered
where (
  cast(:cursor_relevance as integer) is null
  or relevance < :cursor_relevance
  or (
    relevance = :cursor_relevance
    and (
      sort_date < :cursor_sort_date
      or (
        sort_date = :cursor_sort_date
        and (
          document_id < :cursor_document_id
          or (
            document_id = :cursor_document_id
            and coalesce(registry_version_id, 0)
              < :cursor_registry_version_id
          )
        )
      )
    )
  )
)
order by
  relevance desc,
  sort_date desc,
  document_id desc,
  coalesce(registry_version_id, 0) desc
limit :query_limit
"""
