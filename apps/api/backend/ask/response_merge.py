from __future__ import annotations

import hashlib
import json
from collections import defaultdict
from enum import StrEnum
from typing import Literal, Self

from pydantic import Field, field_validator, model_validator

from backend.ask.decision.models import (
    ConfidenceLabel,
    KnowledgeMode,
    ResponseStrategy,
)
from backend.ask.orchestration.contracts import SectionTerminalState
from backend.ask.response_contracts import (
    RESPONSE_CONTRACT_SCHEMA_VERSION,
    ResponseCardEnvelope,
    ResponseConfidenceSnapshot,
    ResponseContractModel,
    StructuredResponseEnvelope,
    StructuredResponseSection,
)

RESPONSE_MERGE_SCHEMA_VERSION = "1"
RESPONSE_MERGE_POLICY_VERSION = "ask-ai-response-merge-v1"


class MergeConflictKind(StrEnum):
    TITLE = "title"
    STRATEGY = "strategy"
    CARD_IDENTITY = "card_identity"


class SectionMergeContribution(ResponseContractModel):
    contribution_id: str = Field(min_length=1, max_length=200)
    atomic_question_id: str = Field(min_length=1, max_length=200)
    atomic_question_order: int = Field(ge=0)
    blueprint_order: int = Field(ge=0)
    section: StructuredResponseSection

    @field_validator("contribution_id", "atomic_question_id")
    @classmethod
    def normalize_identity(cls, value: str) -> str:
        normalized = value.strip()
        if not normalized:
            raise ValueError("Merge contribution identities cannot be blank")
        return normalized


class SectionMergeRequest(ResponseContractModel):
    schema_version: Literal["1"] = RESPONSE_MERGE_SCHEMA_VERSION
    policy_version: Literal["ask-ai-response-merge-v1"] = RESPONSE_MERGE_POLICY_VERSION
    response_id: str = Field(min_length=1, max_length=200)
    response_strategy: ResponseStrategy
    compatibility_summary: str = Field(min_length=1, max_length=50_000)
    overall_confidence: ResponseConfidenceSnapshot
    assumptions: tuple[str, ...] = ()
    gaps: tuple[str, ...] = ()
    contributions: tuple[SectionMergeContribution, ...] = Field(min_length=1)

    @model_validator(mode="after")
    def validate_request(self) -> Self:
        contribution_ids = tuple(item.contribution_id for item in self.contributions)
        if len(contribution_ids) != len(set(contribution_ids)):
            raise ValueError("Merge contribution IDs must be unique")
        question_orders: dict[str, int] = {}
        for item in self.contributions:
            prior = question_orders.setdefault(
                item.atomic_question_id,
                item.atomic_question_order,
            )
            if prior != item.atomic_question_order:
                raise ValueError("Atomic question order must be stable")
        if set(question_orders.values()) != set(range(len(question_orders))):
            raise ValueError("Atomic question order must be contiguous")
        return self


class SectionMergeResult(ResponseContractModel):
    schema_version: Literal["1"] = RESPONSE_MERGE_SCHEMA_VERSION
    policy_version: Literal["ask-ai-response-merge-v1"] = RESPONSE_MERGE_POLICY_VERSION
    response: StructuredResponseEnvelope
    exact_duplicate_count: int = Field(ge=0)
    conflict_count: int = Field(ge=0)
    conflict_kinds: tuple[MergeConflictKind, ...] = ()


def merge_response_sections(request: SectionMergeRequest) -> SectionMergeResult:
    safe = SectionMergeRequest.model_validate(request.model_dump(mode="python"))
    groups: dict[tuple[str, str, KnowledgeMode], list[SectionMergeContribution]] = (
        defaultdict(list)
    )
    for item in safe.contributions:
        groups[
            (
                item.atomic_question_id,
                item.section.section_key,
                item.section.knowledge_mode,
            )
        ].append(item)

    ordered_groups = sorted(
        groups.items(),
        key=lambda entry: (
            min(item.atomic_question_order for item in entry[1]),
            min(item.blueprint_order for item in entry[1]),
            _mode_rank(entry[0][2]),
            entry[0][1],
            entry[0][0],
        ),
    )
    key_counts: dict[str, int] = defaultdict(int)
    for (_, section_key, _), _items in ordered_groups:
        key_counts[section_key] += 1

    sections: list[StructuredResponseSection] = []
    duplicate_count = 0
    conflicts: set[MergeConflictKind] = set()
    conflict_count = 0
    for order, (group_key, contributions) in enumerate(ordered_groups):
        section, duplicates, section_conflicts = _merge_group(
            group_key=group_key,
            contributions=contributions,
            order=order,
            key_collision=key_counts[group_key[1]] > 1,
        )
        sections.append(section)
        duplicate_count += duplicates
        conflicts.update(section_conflicts)
        conflict_count += len(section_conflicts)

    response = StructuredResponseEnvelope(
        schema_version=RESPONSE_CONTRACT_SCHEMA_VERSION,
        policy_version=safe.policy_version,
        response_id=safe.response_id,
        response_strategy=safe.response_strategy,
        sections=tuple(sections),
        overall_confidence=safe.overall_confidence,
        compatibility_summary=safe.compatibility_summary,
        assumptions=_ordered_unique(safe.assumptions),
        gaps=_ordered_unique(safe.gaps),
    )
    response = StructuredResponseEnvelope.model_validate_json(
        response.model_dump_json()
    )
    return SectionMergeResult(
        response=response,
        exact_duplicate_count=duplicate_count,
        conflict_count=conflict_count,
        conflict_kinds=tuple(sorted(conflicts, key=lambda item: item.value)),
    )


def _merge_group(
    *,
    group_key: tuple[str, str, KnowledgeMode],
    contributions: list[SectionMergeContribution],
    order: int,
    key_collision: bool,
) -> tuple[StructuredResponseSection, int, set[MergeConflictKind]]:
    question_id, base_key, mode = group_key
    ordered = sorted(
        contributions,
        key=lambda item: (item.blueprint_order, item.contribution_id),
    )
    conflicts: set[MergeConflictKind] = set()
    titles = sorted({item.section.title for item in ordered})
    strategies = sorted({item.section.strategy for item in ordered}, key=lambda item: item.value)
    if len(titles) > 1:
        conflicts.add(MergeConflictKind.TITLE)
    if len(strategies) > 1:
        conflicts.add(MergeConflictKind.STRATEGY)

    section_key = (
        _bounded_identity(base_key, f"{question_id}:{mode.value}")
        if key_collision
        else base_key
    )
    section_id = _stable_id("section", question_id, base_key, mode.value)
    cards, duplicates, card_conflict = _merge_cards(
        ordered,
        section_id,
        {item.section.section_id for item in ordered},
    )
    if card_conflict:
        conflicts.add(MergeConflictKind.CARD_IDENTITY)

    gaps = _ordered_unique(
        item
        for contribution in ordered
        for item in contribution.section.gaps
    )
    conflict_gaps = []
    if MergeConflictKind.TITLE in conflicts:
        conflict_gaps.append("Conflicting section titles retained: " + " | ".join(titles))
    if MergeConflictKind.STRATEGY in conflicts:
        conflict_gaps.append(
            "Conflicting section strategies retained: "
            + " | ".join(item.value for item in strategies)
        )
    if MergeConflictKind.CARD_IDENTITY in conflicts:
        conflict_gaps.append("Conflicting card identities were retained as separate variants.")

    claims = _ordered_unique(
        item for contribution in ordered for item in contribution.section.claim_ids
    )
    sources = _ordered_unique(
        item for contribution in ordered for item in contribution.section.source_ids
    )
    assumptions = _ordered_unique(
        item for contribution in ordered for item in contribution.section.assumptions
    )
    confidence = _weakest_confidence(
        tuple(item.section.confidence for item in ordered)
    )
    states = tuple(item.section.state for item in ordered)
    state = _merged_state(states)
    if state is SectionTerminalState.DEGRADED and any(
        item not in {
            SectionTerminalState.READY,
            SectionTerminalState.READY_WITHOUT_SYNTHESIS,
            SectionTerminalState.DEGRADED,
        }
        for item in states
    ):
        conflict_gaps.append(
            "A supporting contribution did not complete; ready content was preserved."
        )
    section = StructuredResponseSection(
        schema_version=RESPONSE_CONTRACT_SCHEMA_VERSION,
        section_id=section_id,
        section_key=section_key,
        order=order,
        strategy=strategies[0],
        title=titles[0],
        state=state,
        knowledge_mode=mode,
        provenance_class=ordered[0].section.provenance_class,
        confidence=confidence,
        claim_ids=claims,
        source_ids=sources,
        assumptions=assumptions,
        gaps=(*gaps, *conflict_gaps),
        cards=cards,
    )
    return section, duplicates, conflicts


def _merge_cards(
    contributions: list[SectionMergeContribution],
    section_id: str,
    source_section_ids: set[str],
) -> tuple[tuple[ResponseCardEnvelope, ...], int, bool]:
    candidates: list[tuple[int, int, str, ResponseCardEnvelope, str]] = []
    for contribution in contributions:
        for card in contribution.section.cards:
            fingerprint = _card_fingerprint(
                card,
                contribution.section.section_id,
            )
            candidates.append(
                (
                    contribution.blueprint_order,
                    card.order,
                    contribution.contribution_id,
                    card,
                    fingerprint,
                )
            )
    candidates.sort(key=lambda item: (item[0], item[1], item[2], item[4]))

    by_fingerprint: dict[str, tuple[int, int, str, ResponseCardEnvelope, str]] = {}
    identities: dict[str, set[str]] = defaultdict(set)
    duplicates = 0
    for candidate in candidates:
        card = candidate[3]
        fingerprint = candidate[4]
        identities[card.card_id].add(fingerprint)
        prior = by_fingerprint.get(fingerprint)
        if prior is None or card.card_id < prior[3].card_id:
            if prior is not None:
                duplicates += 1
            by_fingerprint[fingerprint] = candidate
        else:
            duplicates += 1
    card_conflict = any(len(items) > 1 for items in identities.values())

    selected = sorted(
        by_fingerprint.values(),
        key=lambda item: (item[0], item[1], item[3].card_type, item[4]),
    )
    output: list[ResponseCardEnvelope] = []
    for order, (_, _, _, card, fingerprint) in enumerate(selected):
        card_id = _stable_id("card", section_id, fingerprint)
        actions = [
            action.model_copy(
                update={
                    "target": (
                        section_id
                        if action.target in source_section_ids
                        else card_id
                        if action.target == card.card_id
                        else action.target
                    )
                }
            )
            for action in card.actions
        ]
        output.append(
            card.model_copy(
                update={"card_id": card_id, "order": order, "actions": tuple(actions)}
            )
        )
    return tuple(output), duplicates, card_conflict


def _card_fingerprint(card: ResponseCardEnvelope, section_id: str) -> str:
    payload = card.model_dump(mode="json")
    payload.pop("card_id", None)
    payload.pop("order", None)
    for action in payload["actions"]:
        if action["target"] == card.card_id:
            action["target"] = "$self_card"
        elif action["target"] == section_id:
            action["target"] = "$section"
    return hashlib.sha256(
        json.dumps(payload, sort_keys=True, separators=(",", ":")).encode("utf-8")
    ).hexdigest()


def _weakest_confidence(
    values: tuple[ResponseConfidenceSnapshot, ...],
) -> ResponseConfidenceSnapshot:
    label_rank = {
        ConfidenceLabel.UNKNOWN: 0,
        ConfidenceLabel.LOW: 1,
        ConfidenceLabel.MEDIUM: 2,
        ConfidenceLabel.HIGH: 3,
    }
    weakest = min(values, key=lambda item: (label_rank[item.label], item.score))
    reasons = _ordered_unique(item for value in values for item in value.reasons)
    return weakest.model_copy(update={"reasons": reasons})


def _state_rank(state: SectionTerminalState) -> int:
    return {
        SectionTerminalState.READY: 0,
        SectionTerminalState.READY_WITHOUT_SYNTHESIS: 1,
        SectionTerminalState.DEGRADED: 2,
        SectionTerminalState.EMPTY_BY_EVIDENCE: 3,
        SectionTerminalState.OMITTED: 4,
        SectionTerminalState.NEEDS_CLARIFICATION: 5,
        SectionTerminalState.CANCELLED: 6,
    }[state]


def _merged_state(states: tuple[SectionTerminalState, ...]) -> SectionTerminalState:
    usable = {
        SectionTerminalState.READY,
        SectionTerminalState.READY_WITHOUT_SYNTHESIS,
        SectionTerminalState.DEGRADED,
    }
    if any(item in usable for item in states):
        if all(item is SectionTerminalState.READY for item in states):
            return SectionTerminalState.READY
        if all(
            item in {
                SectionTerminalState.READY,
                SectionTerminalState.READY_WITHOUT_SYNTHESIS,
            }
            for item in states
        ):
            return SectionTerminalState.READY_WITHOUT_SYNTHESIS
        return SectionTerminalState.DEGRADED
    return max(states, key=_state_rank)


def _mode_rank(mode: KnowledgeMode) -> int:
    return {
        KnowledgeMode.GROUNDED_REGULATORY: 0,
        KnowledgeMode.LIVE_INTELLIGENCE: 1,
        KnowledgeMode.GENERAL_AI: 2,
    }[mode]


def _stable_id(prefix: str, *parts: str) -> str:
    digest = hashlib.sha256("\x1f".join(parts).encode("utf-8")).hexdigest()[:32]
    return f"{prefix}_{digest}"


def _bounded_identity(base: str, disambiguator: str) -> str:
    suffix = hashlib.sha256(disambiguator.encode("utf-8")).hexdigest()[:12]
    return f"{base[:186]}--{suffix}"


def _ordered_unique(values: object) -> tuple[str, ...]:
    return tuple(sorted(set(values)))  # type: ignore[arg-type]
