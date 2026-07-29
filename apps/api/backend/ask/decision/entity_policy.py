from __future__ import annotations

import re
import unicodedata
from collections.abc import Iterable
from difflib import SequenceMatcher
from enum import StrEnum
from typing import Self

from pydantic import Field, field_validator, model_validator

from backend.ask.decision.models import DecisionModel, EntityClass, EntityDecision

ENTITY_EXACT_CONFIDENCE = 1.00
ENTITY_ALIAS_CONFIDENCE = 0.95
ENTITY_REINFORCED_CONFIDENCE = 0.85
ENTITY_FUZZY_CONFIDENCE = 0.70
ENTITY_FAVORED_CONFIDENCE = 0.50
ENTITY_UNRESOLVED_CONFIDENCE = 0.49
ENTITY_HIGH_RISK_CONFIDENCE = 0.85
ENTITY_FUZZY_SIMILARITY = 0.72

ENTITY_RESOLUTION_ORDER = (
    "exact_canonical",
    "exact_alias",
    "exact_glossary",
    "interaction_context",
    "conversation_scope",
    "jurisdiction_context",
    "fuzzy_assumption",
    "clarification",
)


class EntityAliasKind(StrEnum):
    APPROVED_ALIAS = "approved_alias"
    ACRONYM = "acronym"
    FORMER_NAME = "former_name"
    REGULATION_FAMILY = "regulation_family"
    REGULATOR_ASSOCIATION = "regulator_association"


RESOLVING_ALIAS_KINDS = frozenset(
    {
        EntityAliasKind.APPROVED_ALIAS,
        EntityAliasKind.ACRONYM,
        EntityAliasKind.FORMER_NAME,
    }
)


class EntityResolutionRisk(StrEnum):
    GENERAL = "general"
    OBLIGATION = "obligation"
    DEADLINE = "deadline"
    CURRENT_STATUS = "current_status"
    AMENDMENT = "amendment"


class EntityResolutionStatus(StrEnum):
    RESOLVED = "resolved"
    ASSUMED = "assumed"
    CLARIFICATION_REQUIRED = "clarification_required"


class EntityAlias(DecisionModel):
    value: str = Field(min_length=1)
    kind: EntityAliasKind
    jurisdiction: str

    @field_validator("value", "jurisdiction")
    @classmethod
    def reject_blank_text(cls, value: str) -> str:
        normalized = value.strip()
        if not normalized:
            raise ValueError("Entity alias text cannot be blank")
        return normalized


class GlossaryTerm(DecisionModel):
    term: str = Field(min_length=1)
    definition: str = Field(min_length=1)
    jurisdiction: str

    @field_validator("term", "definition", "jurisdiction")
    @classmethod
    def reject_blank_text(cls, value: str) -> str:
        normalized = value.strip()
        if not normalized:
            raise ValueError("Glossary text cannot be blank")
        return normalized


class EntityCatalogEntry(DecisionModel):
    canonical_id: str = Field(pattern=r"^[a-z0-9][a-z0-9._:-]{0,199}$")
    canonical_name: str = Field(min_length=1)
    entity_class: EntityClass
    jurisdiction: str
    aliases: tuple[EntityAlias, ...] = ()
    glossary_terms: tuple[GlossaryTerm, ...] = ()
    workspace_priority: int = Field(default=50, ge=0, le=100)
    provenance_kind: str = Field(min_length=1)
    provenance_ref: str = Field(min_length=1)

    @field_validator(
        "canonical_name",
        "jurisdiction",
        "provenance_kind",
        "provenance_ref",
    )
    @classmethod
    def reject_blank_text(cls, value: str) -> str:
        normalized = value.strip()
        if not normalized:
            raise ValueError("Entity catalog text cannot be blank")
        return normalized

    @model_validator(mode="after")
    def validate_unique_terms(self) -> Self:
        alias_keys = [
            (_normalize(alias.value), _normalize(alias.jurisdiction))
            for alias in self.aliases
        ]
        glossary_keys = [
            (_normalize(term.term), _normalize(term.jurisdiction))
            for term in self.glossary_terms
        ]
        if len(alias_keys) != len(set(alias_keys)):
            raise ValueError("Entity aliases must be unique within a jurisdiction")
        if len(glossary_keys) != len(set(glossary_keys)):
            raise ValueError("Glossary terms must be unique within a jurisdiction")
        return self


class EntityResolutionRequest(DecisionModel):
    mention: str = Field(min_length=1)
    active_jurisdiction: str | None = None
    interaction_entity_ids: tuple[str, ...] = ()
    conversation_entity_ids: tuple[str, ...] = ()
    context_terms: tuple[str, ...] = ()
    risk: EntityResolutionRisk = EntityResolutionRisk.GENERAL

    @field_validator("mention")
    @classmethod
    def reject_blank_mention(cls, value: str) -> str:
        normalized = value.strip()
        if not normalized:
            raise ValueError("Entity mention cannot be blank")
        return normalized

    @field_validator("active_jurisdiction")
    @classmethod
    def normalize_optional_jurisdiction(cls, value: str | None) -> str | None:
        if value is None:
            return None
        normalized = value.strip()
        if not normalized:
            raise ValueError("Active jurisdiction cannot be blank")
        return normalized

    @field_validator("context_terms")
    @classmethod
    def normalize_context_terms(cls, values: tuple[str, ...]) -> tuple[str, ...]:
        normalized = tuple(value.strip() for value in values)
        if any(not value for value in normalized):
            raise ValueError("Context terms cannot be blank")
        return normalized

    @model_validator(mode="after")
    def validate_distinct_scope_ids(self) -> Self:
        if len(set(self.interaction_entity_ids)) != len(self.interaction_entity_ids):
            raise ValueError("Interaction entity IDs must be unique")
        if len(set(self.conversation_entity_ids)) != len(self.conversation_entity_ids):
            raise ValueError("Conversation entity IDs must be unique")
        return self


class EntityResolution(DecisionModel):
    status: EntityResolutionStatus
    match_rule: str
    selected: EntityDecision | None = None
    candidates: tuple[EntityDecision, ...] = ()
    query_expansion: tuple[str, ...] = ()
    clarification_question: str | None = None
    required_confidence: float = Field(ge=0, le=1)
    direct_answer_allowed: bool

    @model_validator(mode="after")
    def validate_terminal_shape(self) -> Self:
        if self.status is EntityResolutionStatus.CLARIFICATION_REQUIRED:
            if self.clarification_question is None:
                raise ValueError("Clarification results require one focused question")
            if self.direct_answer_allowed:
                raise ValueError("Clarification cannot permit a direct answer")
        elif self.selected is None:
            raise ValueError("Resolved entity results require a selected entity")
        return self


def resolve_entity(
    request: EntityResolutionRequest,
    catalog: Iterable[EntityCatalogEntry],
) -> EntityResolution:
    entries = tuple(catalog)
    _validate_catalog(entries)
    required_confidence = (
        ENTITY_FAVORED_CONFIDENCE
        if request.risk is EntityResolutionRisk.GENERAL
        else ENTITY_HIGH_RISK_CONFIDENCE
    )
    mention = _normalize(request.mention)

    canonical_matches = tuple(
        entry
        for entry in entries
        if mention in {_normalize(entry.canonical_id), _normalize(entry.canonical_name)}
    )
    canonical_result = _unique_exact_result(
        request,
        canonical_matches,
        confidence=ENTITY_EXACT_CONFIDENCE,
        match_rule="exact_canonical",
        required_confidence=required_confidence,
    )
    if canonical_result is not None:
        return canonical_result

    alias_matches = tuple(
        entry
        for entry in entries
        if any(
            alias.kind in RESOLVING_ALIAS_KINDS
            and _normalize(alias.value) == mention
            and _term_jurisdiction_compatible(
                request.active_jurisdiction,
                alias.jurisdiction,
            )
            for alias in entry.aliases
        )
    )
    alias_result = _unique_exact_result(
        request,
        alias_matches,
        confidence=ENTITY_ALIAS_CONFIDENCE,
        match_rule="exact_alias",
        required_confidence=required_confidence,
    )
    if alias_result is not None:
        return alias_result

    glossary_matches = tuple(
        entry
        for entry in entries
        if any(
            _normalize(term.term) == mention
            and _term_jurisdiction_compatible(
                request.active_jurisdiction,
                term.jurisdiction,
            )
            for term in entry.glossary_terms
        )
    )
    reinforced_glossary = _jurisdiction_matches(request, glossary_matches)
    if not reinforced_glossary:
        reinforced_glossary = _context_reinforced_candidates(
            request,
            glossary_matches,
        )
    glossary_result = _unique_exact_result(
        request,
        reinforced_glossary,
        confidence=ENTITY_REINFORCED_CONFIDENCE,
        match_rule="exact_glossary",
        required_confidence=required_confidence,
    )
    if glossary_result is not None:
        return glossary_result
    if len(glossary_matches) == 1 and not _has_context(request):
        return _selected_result(
            request,
            glossary_matches[0],
            confidence=ENTITY_FUZZY_CONFIDENCE,
            match_rule="exact_glossary",
            required_confidence=required_confidence,
            assumed=True,
        )

    interaction_matches = _scope_matches(
        entries,
        request.interaction_entity_ids,
        (*canonical_matches, *alias_matches, *glossary_matches),
    )
    if len(interaction_matches) == 1:
        return _selected_result(
            request,
            interaction_matches[0],
            confidence=ENTITY_REINFORCED_CONFIDENCE,
            match_rule="interaction_context",
            required_confidence=required_confidence,
            assumed=True,
        )

    conversation_matches = _scope_matches(
        entries,
        request.conversation_entity_ids,
        (*canonical_matches, *alias_matches, *glossary_matches),
    )
    if len(conversation_matches) == 1:
        return _selected_result(
            request,
            conversation_matches[0],
            confidence=ENTITY_REINFORCED_CONFIDENCE,
            match_rule="conversation_scope",
            required_confidence=required_confidence,
            assumed=True,
        )

    contextual_matches = _contextual_matches(
        request,
        entries,
        (*canonical_matches, *alias_matches, *glossary_matches),
    )
    if len(contextual_matches) == 1:
        return _selected_result(
            request,
            contextual_matches[0],
            confidence=ENTITY_FUZZY_CONFIDENCE,
            match_rule="jurisdiction_context",
            required_confidence=required_confidence,
            assumed=True,
        )

    ambiguous_exact = _deduplicate_entries(
        (*canonical_matches, *alias_matches, *glossary_matches)
    )
    if ambiguous_exact:
        if request.active_jurisdiction is not None:
            compatible_ambiguous = _jurisdiction_matches(
                request,
                ambiguous_exact,
            )
            if not compatible_ambiguous:
                return _clarification_result(
                    request,
                    ambiguous_exact,
                    required_confidence=required_confidence,
                )
            ambiguous_exact = compatible_ambiguous
        favored = _favored_candidate(ambiguous_exact)
        if favored is not None:
            return _selected_result(
                request,
                favored,
                confidence=ENTITY_FAVORED_CONFIDENCE,
                match_rule="jurisdiction_context",
                required_confidence=required_confidence,
                assumed=True,
                candidates=ambiguous_exact,
            )
        return _clarification_result(
            request,
            ambiguous_exact,
            required_confidence=required_confidence,
        )

    fuzzy_matches = _fuzzy_matches(request, entries)
    if len(fuzzy_matches) == 1:
        return _selected_result(
            request,
            fuzzy_matches[0],
            confidence=ENTITY_FUZZY_CONFIDENCE,
            match_rule="fuzzy_assumption",
            required_confidence=required_confidence,
            assumed=True,
        )
    if fuzzy_matches:
        return _clarification_result(
            request,
            fuzzy_matches,
            required_confidence=required_confidence,
        )
    return _clarification_result(
        request,
        (),
        required_confidence=required_confidence,
    )


def _unique_exact_result(
    request: EntityResolutionRequest,
    candidates: tuple[EntityCatalogEntry, ...],
    *,
    confidence: float,
    match_rule: str,
    required_confidence: float,
) -> EntityResolution | None:
    candidates = _deduplicate_entries(candidates)
    compatible = _jurisdiction_matches(request, candidates)
    if request.active_jurisdiction is not None:
        if not compatible:
            return None
        candidates = compatible
    if len(candidates) != 1:
        return None
    return _selected_result(
        request,
        candidates[0],
        confidence=confidence,
        match_rule=match_rule,
        required_confidence=required_confidence,
        assumed=False,
    )


def _selected_result(
    request: EntityResolutionRequest,
    entry: EntityCatalogEntry,
    *,
    confidence: float,
    match_rule: str,
    required_confidence: float,
    assumed: bool,
    candidates: tuple[EntityCatalogEntry, ...] = (),
) -> EntityResolution:
    decision = _decision(
        request.mention,
        entry,
        confidence=confidence,
        assumed=assumed,
        reason=_reason(match_rule, entry),
    )
    direct_answer_allowed = confidence >= required_confidence
    status = (
        EntityResolutionStatus.ASSUMED
        if assumed
        else EntityResolutionStatus.RESOLVED
    )
    if not direct_answer_allowed:
        return _clarification_result(
            request,
            candidates or (entry,),
            required_confidence=required_confidence,
            selected=decision,
            match_rule=match_rule,
        )
    return EntityResolution(
        status=status,
        match_rule=match_rule,
        selected=decision,
        candidates=tuple(
            _decision(
                request.mention,
                candidate,
                confidence=confidence,
                assumed=True,
                reason=_reason(match_rule, candidate),
            )
            for candidate in candidates
        ),
        query_expansion=_query_expansion(request, entry),
        required_confidence=required_confidence,
        direct_answer_allowed=True,
    )


def _clarification_result(
    request: EntityResolutionRequest,
    candidates: tuple[EntityCatalogEntry, ...],
    *,
    required_confidence: float,
    selected: EntityDecision | None = None,
    match_rule: str = "clarification",
) -> EntityResolution:
    decisions = tuple(
        _decision(
            request.mention,
            entry,
            confidence=ENTITY_UNRESOLVED_CONFIDENCE,
            assumed=False,
            reason="Material ambiguity remains.",
        )
        for entry in candidates
    )
    names = tuple(entry.canonical_name for entry in candidates[:3])
    if names:
        choices = " or ".join(names)
        question = f"Which did you mean by '{request.mention}': {choices}?"
    else:
        question = (
            f"Which regulatory entity or jurisdiction do you mean by "
            f"'{request.mention}'?"
        )
    return EntityResolution(
        status=EntityResolutionStatus.CLARIFICATION_REQUIRED,
        match_rule=match_rule,
        selected=selected,
        candidates=decisions,
        clarification_question=question,
        required_confidence=required_confidence,
        direct_answer_allowed=False,
    )


def _decision(
    mention: str,
    entry: EntityCatalogEntry,
    *,
    confidence: float,
    assumed: bool,
    reason: str,
) -> EntityDecision:
    return EntityDecision(
        mention=mention,
        canonical_id=entry.canonical_id,
        canonical_name=entry.canonical_name,
        entity_class=entry.entity_class,
        aliases=tuple(alias.value for alias in entry.aliases),
        jurisdiction=entry.jurisdiction,
        confidence=confidence,
        assumed=assumed,
        reason=reason,
    )


def _scope_matches(
    entries: tuple[EntityCatalogEntry, ...],
    entity_ids: tuple[str, ...],
    prior_candidates: tuple[EntityCatalogEntry, ...],
) -> tuple[EntityCatalogEntry, ...]:
    if not entity_ids:
        return ()
    source = _deduplicate_entries(prior_candidates) or entries
    allowed = set(entity_ids)
    return tuple(entry for entry in source if entry.canonical_id in allowed)


def _contextual_matches(
    request: EntityResolutionRequest,
    entries: tuple[EntityCatalogEntry, ...],
    prior_candidates: tuple[EntityCatalogEntry, ...],
) -> tuple[EntityCatalogEntry, ...]:
    source = _deduplicate_entries(prior_candidates) or entries
    compatible = _jurisdiction_matches(request, source)
    if request.active_jurisdiction is not None:
        if not compatible:
            return ()
        source = compatible
    context = {_normalize(term) for term in request.context_terms}
    if not context:
        return ()
    matches = []
    for entry in source:
        labels = _entry_labels(entry, request.active_jurisdiction)
        if any(
            context_term in label or label in context_term
            for context_term in context
            for label in labels
        ):
            matches.append(entry)
    return tuple(matches)


def _fuzzy_matches(
    request: EntityResolutionRequest,
    entries: tuple[EntityCatalogEntry, ...],
) -> tuple[EntityCatalogEntry, ...]:
    mention = _normalize(request.mention)
    scored: list[tuple[float, EntityCatalogEntry]] = []
    compatible = _jurisdiction_matches(request, entries)
    if request.active_jurisdiction is not None and not compatible:
        return ()
    source = compatible or entries
    for entry in source:
        score = max(
            SequenceMatcher(None, mention, label).ratio()
            for label in _entry_labels(entry, request.active_jurisdiction)
        )
        if score >= ENTITY_FUZZY_SIMILARITY:
            scored.append((score, entry))
    scored.sort(key=lambda item: (-item[0], -item[1].workspace_priority, item[1].canonical_id))
    if not scored:
        return ()
    top_score = scored[0][0]
    return tuple(entry for score, entry in scored if top_score - score < 0.10)


def _favored_candidate(
    candidates: tuple[EntityCatalogEntry, ...],
) -> EntityCatalogEntry | None:
    ordered = sorted(
        candidates,
        key=lambda entry: (-entry.workspace_priority, entry.canonical_id),
    )
    if len(ordered) < 2:
        return None
    if ordered[0].workspace_priority - ordered[1].workspace_priority < 20:
        return None
    return ordered[0]


def _jurisdiction_matches(
    request: EntityResolutionRequest,
    entries: tuple[EntityCatalogEntry, ...],
) -> tuple[EntityCatalogEntry, ...]:
    if request.active_jurisdiction is None:
        return ()
    active = _normalize_jurisdiction(request.active_jurisdiction)
    return tuple(
        entry
        for entry in entries
        if _jurisdictions_compatible(
            active,
            _normalize_jurisdiction(entry.jurisdiction),
        )
    )


def _context_reinforced_candidates(
    request: EntityResolutionRequest,
    candidates: tuple[EntityCatalogEntry, ...],
) -> tuple[EntityCatalogEntry, ...]:
    context_ids = {
        *request.interaction_entity_ids,
        *request.conversation_entity_ids,
    }
    context_terms = {_normalize(term) for term in request.context_terms}
    return tuple(
        entry
        for entry in candidates
        if entry.canonical_id in context_ids
        or any(
            context_term in label or label in context_term
            for context_term in context_terms
            for label in _entry_labels(entry, request.active_jurisdiction)
        )
    )


def _jurisdictions_compatible(active: str, candidate: str) -> bool:
    if active == candidate or candidate == "global":
        return True
    return active.startswith(f"{candidate}/") or candidate.startswith(f"{active}/")


def _query_expansion(
    request: EntityResolutionRequest,
    entry: EntityCatalogEntry,
) -> tuple[str, ...]:
    return _stable_unique(
        (
            request.mention,
            entry.canonical_name,
            *(
                alias.value
                for alias in entry.aliases
                if _term_jurisdiction_compatible(
                    request.active_jurisdiction,
                    alias.jurisdiction,
                )
            ),
        )
    )


def _entry_labels(
    entry: EntityCatalogEntry,
    active_jurisdiction: str | None = None,
) -> tuple[str, ...]:
    return tuple(
        _normalize(value)
        for value in (
            entry.canonical_id,
            entry.canonical_name,
            *(
                alias.value
                for alias in entry.aliases
                if _term_jurisdiction_compatible(
                    active_jurisdiction,
                    alias.jurisdiction,
                )
            ),
            *(
                term.term
                for term in entry.glossary_terms
                if _term_jurisdiction_compatible(
                    active_jurisdiction,
                    term.jurisdiction,
                )
            ),
        )
    )


def _validate_catalog(entries: tuple[EntityCatalogEntry, ...]) -> None:
    ids = [entry.canonical_id for entry in entries]
    if len(ids) != len(set(ids)):
        raise ValueError("Entity catalog canonical IDs must be unique")
    natural_keys = [
        (_normalize(entry.canonical_name), _normalize(entry.jurisdiction))
        for entry in entries
    ]
    if len(natural_keys) != len(set(natural_keys)):
        raise ValueError(
            "Entity catalog canonical names must be unique within a jurisdiction"
        )


def _deduplicate_entries(
    entries: Iterable[EntityCatalogEntry],
) -> tuple[EntityCatalogEntry, ...]:
    by_id: dict[str, EntityCatalogEntry] = {}
    for entry in entries:
        by_id.setdefault(entry.canonical_id, entry)
    return tuple(by_id.values())


def _stable_unique(values: Iterable[str]) -> tuple[str, ...]:
    unique: dict[str, str] = {}
    for value in values:
        unique.setdefault(_normalize(value), value)
    return tuple(unique.values())


def _has_context(request: EntityResolutionRequest) -> bool:
    return bool(
        request.active_jurisdiction
        or request.context_terms
        or request.interaction_entity_ids
        or request.conversation_entity_ids
    )


def _term_jurisdiction_compatible(
    active_jurisdiction: str | None,
    term_jurisdiction: str,
) -> bool:
    if active_jurisdiction is None:
        return True
    return _jurisdictions_compatible(
        _normalize_jurisdiction(active_jurisdiction),
        _normalize_jurisdiction(term_jurisdiction),
    )


def _reason(match_rule: str, entry: EntityCatalogEntry) -> str:
    return (
        f"Resolved by {match_rule.replace('_', ' ')} to "
        f"{entry.canonical_name} in {entry.jurisdiction}."
    )


def _normalize(value: str) -> str:
    normalized = unicodedata.normalize("NFKC", value).casefold().strip()
    return re.sub(r"[\W_]+", " ", normalized, flags=re.UNICODE).strip()


def _normalize_jurisdiction(value: str) -> str:
    normalized = unicodedata.normalize("NFKC", value).casefold().strip()
    return "/".join(
        _normalize(segment)
        for segment in re.split(r"\s*/\s*", normalized)
        if _normalize(segment)
    )
