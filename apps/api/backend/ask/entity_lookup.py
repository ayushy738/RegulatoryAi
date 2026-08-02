from __future__ import annotations

from collections.abc import Callable
from contextlib import AbstractContextManager
from typing import Literal, Self
from urllib.parse import quote

from pydantic import Field, field_validator, model_validator
from sqlalchemy import text
from sqlalchemy.orm import Session

from backend.ask.decision.entity_policy import (
    EntityAlias,
    EntityAliasKind,
    EntityCatalogEntry,
    EntityResolutionRequest,
    EntityResolutionStatus,
    GlossaryTerm,
    resolve_entity,
)
from backend.ask.decision.models import (
    DECISION_POLICY_VERSION,
    DecisionModel,
    EntityClass,
    EntityDecision,
)
from backend.core.db import session_scope

ENTITY_LOOKUP_SCHEMA_VERSION = "1"
ENTITY_INTELLIGENCE_SURFACE = "entity_intelligence_page"


class EntityLookupRequest(DecisionModel):
    schema_version: Literal["1"] = ENTITY_LOOKUP_SCHEMA_VERSION
    mention: str = Field(min_length=1, max_length=200)
    active_jurisdiction: str | None = Field(default=None, max_length=200)

    @field_validator("mention")
    @classmethod
    def normalize_mention(cls, value: str) -> str:
        normalized = value.strip()
        if not normalized:
            raise ValueError("Entity mention cannot be blank")
        return normalized

    @field_validator("active_jurisdiction")
    @classmethod
    def normalize_jurisdiction(cls, value: str | None) -> str | None:
        if value is None:
            return None
        normalized = value.strip()
        if not normalized:
            raise ValueError("Active jurisdiction cannot be blank")
        return normalized


class EntityLookupCandidate(DecisionModel):
    canonical_id: str = Field(pattern=r"^[a-z0-9][a-z0-9._:-]{0,199}$")
    canonical_name: str = Field(min_length=1)
    entity_class: EntityClass
    jurisdiction: str = Field(min_length=1)
    aliases: tuple[str, ...]
    confidence: float = Field(ge=0, le=1)
    assumed: bool
    match_reason: str = Field(min_length=1)
    entity_route: str = Field(min_length=1)

    @model_validator(mode="after")
    def validate_route(self) -> Self:
        if self.entity_route != entity_intelligence_route(self.canonical_id):
            raise ValueError("Entity route must use canonical identity")
        if len(set(self.aliases)) != len(self.aliases):
            raise ValueError("Entity aliases must be unique")
        return self


class EntityLookupResponse(DecisionModel):
    schema_version: Literal["1"] = ENTITY_LOOKUP_SCHEMA_VERSION
    policy_version: Literal["ask-ai-decision-v1"] = DECISION_POLICY_VERSION
    status: Literal["resolved", "ambiguous", "no_match"]
    mention: str = Field(min_length=1)
    match_rule: str = Field(min_length=1)
    selected: EntityLookupCandidate | None = None
    candidates: tuple[EntityLookupCandidate, ...] = ()
    clarification_question: str | None = None
    surface: Literal["entity_intelligence_page"] | None = None

    @model_validator(mode="after")
    def validate_outcome(self) -> Self:
        candidate_ids = tuple(item.canonical_id for item in self.candidates)
        if len(set(candidate_ids)) != len(candidate_ids):
            raise ValueError("Entity lookup candidates must be unique")
        if self.status == "resolved":
            valid = (
                self.selected is not None
                and self.surface == ENTITY_INTELLIGENCE_SURFACE
                and self.clarification_question is None
            )
        elif self.status == "ambiguous":
            valid = (
                self.selected is None
                and bool(self.candidates)
                and self.surface is None
                and self.clarification_question is not None
            )
        else:
            valid = (
                self.selected is None
                and not self.candidates
                and self.surface is None
                and self.clarification_question is not None
            )
        if not valid:
            raise ValueError("Entity lookup outcome shape is inconsistent")
        return self


class EntityLookupUnavailable(RuntimeError):
    pass


class EntityCatalogRepository:
    def __init__(self, database_session: Session) -> None:
        self._database_session = database_session

    def list_entries(self) -> tuple[EntityCatalogEntry, ...]:
        rows = self._database_session.execute(
            text(
                """
                select
                  entity.canonical_id,
                  entity.canonical_name,
                  entity.entity_class,
                  entity.jurisdiction,
                  entity.workspace_priority,
                  entity.provenance_kind,
                  entity.provenance_ref,
                  coalesce(alias_set.items, '[]'::jsonb) as aliases,
                  coalesce(glossary_set.items, '[]'::jsonb) as glossary_terms
                from public.regulatory_entity_catalog entity
                left join lateral (
                  select jsonb_agg(
                    jsonb_build_object(
                      'value', alias.alias,
                      'kind', alias.alias_kind,
                      'jurisdiction', alias.jurisdiction
                    )
                    order by
                      alias.alias_kind,
                      alias.normalized_alias,
                      alias.alias_id
                  ) as items
                  from public.regulatory_entity_aliases alias
                  where alias.canonical_id = entity.canonical_id
                ) alias_set on true
                left join lateral (
                  select jsonb_agg(
                    jsonb_build_object(
                      'term', glossary.term,
                      'definition', glossary.definition,
                      'jurisdiction', glossary.jurisdiction
                    )
                    order by
                      glossary.normalized_term,
                      glossary.glossary_term_id
                  ) as items
                  from public.regulatory_glossary_terms glossary
                  where glossary.canonical_id = entity.canonical_id
                ) glossary_set on true
                order by entity.canonical_id
                """
            )
        ).mappings()
        return tuple(
            EntityCatalogEntry(
                canonical_id=row["canonical_id"],
                canonical_name=row["canonical_name"],
                entity_class=EntityClass(row["entity_class"]),
                jurisdiction=row["jurisdiction"],
                aliases=tuple(
                    EntityAlias(
                        value=item["value"],
                        kind=EntityAliasKind(item["kind"]),
                        jurisdiction=item["jurisdiction"],
                    )
                    for item in row["aliases"]
                ),
                glossary_terms=tuple(
                    GlossaryTerm(
                        term=item["term"],
                        definition=item["definition"],
                        jurisdiction=item["jurisdiction"],
                    )
                    for item in row["glossary_terms"]
                ),
                workspace_priority=row["workspace_priority"],
                provenance_kind=row["provenance_kind"],
                provenance_ref=row["provenance_ref"],
            )
            for row in rows
        )


SessionScopeFactory = Callable[[], AbstractContextManager[Session]]


class EntityLookupService:
    def __init__(
        self,
        session_scope_factory: SessionScopeFactory = session_scope,
    ) -> None:
        self._session_scope_factory = session_scope_factory

    def resolve(self, request: EntityLookupRequest) -> EntityLookupResponse:
        try:
            with self._session_scope_factory() as database_session:
                catalog = EntityCatalogRepository(
                    database_session
                ).list_entries()
            resolution = resolve_entity(
                EntityResolutionRequest(
                    mention=request.mention,
                    active_jurisdiction=request.active_jurisdiction,
                ),
                catalog,
            )
        except Exception:
            raise EntityLookupUnavailable(
                "Entity lookup is unavailable"
            ) from None
        if (
            resolution.status
            is EntityResolutionStatus.CLARIFICATION_REQUIRED
        ):
            candidates = tuple(
                _public_candidate(candidate)
                for candidate in resolution.candidates
            )
            return EntityLookupResponse(
                status="ambiguous" if candidates else "no_match",
                mention=request.mention,
                match_rule=resolution.match_rule,
                candidates=candidates,
                clarification_question=resolution.clarification_question,
            )
        assert resolution.selected is not None
        return EntityLookupResponse(
            status="resolved",
            mention=request.mention,
            match_rule=resolution.match_rule,
            selected=_public_candidate(resolution.selected),
            candidates=tuple(
                _public_candidate(candidate)
                for candidate in resolution.candidates
                if candidate.canonical_id
                != resolution.selected.canonical_id
            ),
            surface=ENTITY_INTELLIGENCE_SURFACE,
        )


def entity_intelligence_route(canonical_id: str) -> str:
    return f"/ask?entity={quote(canonical_id, safe='')}"


def _public_candidate(
    decision: EntityDecision,
) -> EntityLookupCandidate:
    if (
        decision.canonical_id is None
        or decision.canonical_name is None
        or decision.jurisdiction is None
        or decision.reason is None
    ):
        raise EntityLookupUnavailable("Entity candidate is incomplete")
    return EntityLookupCandidate(
        canonical_id=decision.canonical_id,
        canonical_name=decision.canonical_name,
        entity_class=decision.entity_class,
        jurisdiction=decision.jurisdiction,
        aliases=decision.aliases,
        confidence=decision.confidence,
        assumed=decision.assumed,
        match_reason=decision.reason,
        entity_route=entity_intelligence_route(decision.canonical_id),
    )
