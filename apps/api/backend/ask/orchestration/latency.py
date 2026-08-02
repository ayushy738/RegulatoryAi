from __future__ import annotations

import json
import math
import time
from collections.abc import Callable
from dataclasses import dataclass
from enum import StrEnum
from types import MappingProxyType
from typing import Literal

from pydantic import Field, field_validator, model_validator

from backend.ask.decision.plan_policy import PlanClass
from backend.ask.orchestration.contracts import (
    ApprovedWorkPlanPayload,
    ArtifactEnvelope,
    ArtifactKind,
    ContractModel,
    LatencyProfileName,
    OrchestratorCapability,
    ParticipationClass,
    SectionTerminalState,
)
from backend.ask.orchestration.state_machine import (
    SECTION_TERMINAL_STATES,
    OrchestrationState,
    SectionNode,
)

LATENCY_POLICY_SCHEMA_VERSION = "1"
LATENCY_POLICY_VERSION = "ask-ai-latency-v1"


class OptionalWorkClass(StrEnum):
    FOLLOW_UPS = "follow_ups"
    RELATED_ENTITY_EXPANSION = "related_entity_expansion"
    NON_PRIMARY_NEWS = "non_primary_news"
    TIMELINE_ENRICHMENT = "timeline_enrichment"
    REPLACEABLE_GRAPH_ENRICHMENT = "replaceable_graph_enrichment"
    NARRATIVE_POLISH = "narrative_polish"
    SURPLUS_EVIDENCE = "surplus_evidence"


OPTIONAL_WORK_STOP_ORDER = tuple(OptionalWorkClass)


class BudgetStopReason(StrEnum):
    OPTIONAL_CUTOFF = "optional_cutoff"
    SOFT_CUTOFF = "soft_cutoff"
    HARD_CUTOFF = "hard_cutoff"


class LatencyProfile(ContractModel):
    schema_version: Literal["1"] = LATENCY_POLICY_SCHEMA_VERSION
    policy_version: str = Field(default=LATENCY_POLICY_VERSION, min_length=1)
    name: LatencyProfileName
    first_result_target_ms: int = Field(gt=0)
    core_result_target_ms: int = Field(gt=0)
    soft_cutoff_ms: int = Field(gt=0)
    hard_cutoff_ms: int = Field(gt=0)
    verification_reserve_ms: int = Field(gt=0)
    optional_stop_order: tuple[OptionalWorkClass, ...] = (
        OPTIONAL_WORK_STOP_ORDER
    )

    @field_validator("optional_stop_order")
    @classmethod
    def validate_optional_stop_order(
        cls,
        value: tuple[OptionalWorkClass, ...],
    ) -> tuple[OptionalWorkClass, ...]:
        if value != OPTIONAL_WORK_STOP_ORDER:
            raise ValueError("Optional work must use the frozen stopping order")
        return value

    @model_validator(mode="after")
    def validate_boundaries(self) -> LatencyProfile:
        if not (
            self.first_result_target_ms
            <= self.core_result_target_ms
            <= self.soft_cutoff_ms
            < self.hard_cutoff_ms
        ):
            raise ValueError("Latency profile boundaries must be monotonic")
        if self.verification_reserve_ms >= self.hard_cutoff_ms:
            raise ValueError("Verification reserve must fit before the hard cutoff")
        if self.soft_cutoff_ms > self.verification_reserve_starts_at_ms:
            raise ValueError(
                "Optional work cannot borrow the verification reserve"
            )
        return self

    @property
    def verification_reserve_starts_at_ms(self) -> int:
        return self.hard_cutoff_ms - self.verification_reserve_ms

    @property
    def optional_admission_deadline_ms(self) -> int:
        return min(
            self.soft_cutoff_ms,
            self.verification_reserve_starts_at_ms,
        )


FROZEN_LATENCY_PROFILES = MappingProxyType(
    {
        LatencyProfileName.FAST_EXACT: LatencyProfile(
            name=LatencyProfileName.FAST_EXACT,
            first_result_target_ms=1_000,
            core_result_target_ms=3_500,
            soft_cutoff_ms=5_000,
            hard_cutoff_ms=7_000,
            verification_reserve_ms=1_050,
        ),
        LatencyProfileName.FOCUSED_GROUNDED: LatencyProfile(
            name=LatencyProfileName.FOCUSED_GROUNDED,
            first_result_target_ms=1_500,
            core_result_target_ms=7_000,
            soft_cutoff_ms=10_000,
            hard_cutoff_ms=14_000,
            verification_reserve_ms=2_100,
        ),
        LatencyProfileName.LIVE_COMBINED: LatencyProfile(
            name=LatencyProfileName.LIVE_COMBINED,
            first_result_target_ms=1_500,
            core_result_target_ms=8_000,
            soft_cutoff_ms=12_000,
            hard_cutoff_ms=16_000,
            verification_reserve_ms=2_400,
        ),
        LatencyProfileName.DEEP_STRUCTURED: LatencyProfile(
            name=LatencyProfileName.DEEP_STRUCTURED,
            first_result_target_ms=2_000,
            core_result_target_ms=12_000,
            soft_cutoff_ms=18_000,
            hard_cutoff_ms=25_000,
            verification_reserve_ms=3_750,
        ),
        LatencyProfileName.COMPOSITE_RESEARCH: LatencyProfile(
            name=LatencyProfileName.COMPOSITE_RESEARCH,
            first_result_target_ms=2_000,
            core_result_target_ms=15_000,
            soft_cutoff_ms=22_000,
            hard_cutoff_ms=30_000,
            verification_reserve_ms=4_500,
        ),
    }
)

DECISION_PLAN_LATENCY_PROFILES = MappingProxyType(
    {
        PlanClass.FAST_EXACT: LatencyProfileName.FAST_EXACT,
        PlanClass.FOCUSED_GROUNDED: LatencyProfileName.FOCUSED_GROUNDED,
        PlanClass.LIVE_COMBINED: LatencyProfileName.LIVE_COMBINED,
        PlanClass.DEEP_RESEARCH: LatencyProfileName.DEEP_STRUCTURED,
        PlanClass.COMPOSITE: LatencyProfileName.COMPOSITE_RESEARCH,
    }
)


class BudgetCheckpoint(ContractModel):
    schema_version: Literal["1"] = LATENCY_POLICY_SCHEMA_VERSION
    policy_version: str = Field(default=LATENCY_POLICY_VERSION, min_length=1)
    profile: LatencyProfileName
    elapsed_ms: int = Field(ge=0)
    hard_remaining_ms: int = Field(ge=0)
    first_result_target_reached: bool
    core_result_target_reached: bool
    soft_cutoff_reached: bool
    verification_reserve_active: bool
    hard_cutoff_reached: bool
    optional_admission_open: bool


class LatencyBudgetError(RuntimeError):
    pass


@dataclass(frozen=True, slots=True)
class LatencyBudget:
    profile: LatencyProfile
    started_at: float
    clock: Callable[[], float] = time.perf_counter

    def __post_init__(self) -> None:
        if not math.isfinite(self.started_at):
            raise LatencyBudgetError("Latency budget start must be finite")
        self._read_clock()

    def checkpoint(self) -> BudgetCheckpoint:
        elapsed_seconds = self._read_clock() - self.started_at
        if elapsed_seconds < 0:
            raise LatencyBudgetError("Latency budget clock cannot regress")
        elapsed_ms = int(elapsed_seconds * 1_000)
        hard_remaining_ms = max(
            0,
            self.profile.hard_cutoff_ms - elapsed_ms,
        )
        hard_cutoff_reached = elapsed_ms >= self.profile.hard_cutoff_ms
        optional_admission_open = (
            elapsed_ms < self.profile.optional_admission_deadline_ms
        )
        return BudgetCheckpoint(
            profile=self.profile.name,
            elapsed_ms=elapsed_ms,
            hard_remaining_ms=hard_remaining_ms,
            first_result_target_reached=(
                elapsed_ms >= self.profile.first_result_target_ms
            ),
            core_result_target_reached=(
                elapsed_ms >= self.profile.core_result_target_ms
            ),
            soft_cutoff_reached=(
                elapsed_ms >= self.profile.soft_cutoff_ms
            ),
            verification_reserve_active=(
                elapsed_ms
                >= self.profile.verification_reserve_starts_at_ms
            ),
            hard_cutoff_reached=hard_cutoff_reached,
            optional_admission_open=(
                optional_admission_open and not hard_cutoff_reached
            ),
        )

    def stop_reason(
        self,
        participation: ParticipationClass,
        capability: OrchestratorCapability | None = None,
    ) -> BudgetStopReason | None:
        checkpoint = self.checkpoint()
        if checkpoint.hard_cutoff_reached:
            return BudgetStopReason.HARD_CUTOFF
        if capability is OrchestratorCapability.CITATION_VERIFIER:
            return None
        if (
            participation is ParticipationClass.OPTIONAL
            and not checkpoint.optional_admission_open
        ):
            return BudgetStopReason.OPTIONAL_CUTOFF
        if (
            participation is ParticipationClass.SUPPORTING
            and checkpoint.soft_cutoff_reached
        ):
            return BudgetStopReason.SOFT_CUTOFF
        return None

    def remaining_execution_seconds(
        self,
        participation: ParticipationClass,
        capability: OrchestratorCapability | None = None,
    ) -> float:
        checkpoint = self.checkpoint()
        if capability is OrchestratorCapability.CITATION_VERIFIER:
            deadline_ms = self.profile.hard_cutoff_ms
        elif participation is ParticipationClass.OPTIONAL:
            deadline_ms = self.profile.optional_admission_deadline_ms
        elif participation is ParticipationClass.SUPPORTING:
            deadline_ms = self.profile.soft_cutoff_ms
        else:
            deadline_ms = self.profile.hard_cutoff_ms
        return max(0.0, (deadline_ms - checkpoint.elapsed_ms) / 1_000)

    @staticmethod
    def deadline_stop_reason(
        participation: ParticipationClass,
        capability: OrchestratorCapability | None = None,
    ) -> BudgetStopReason:
        if capability is OrchestratorCapability.CITATION_VERIFIER:
            return BudgetStopReason.HARD_CUTOFF
        if participation is ParticipationClass.OPTIONAL:
            return BudgetStopReason.OPTIONAL_CUTOFF
        if participation is ParticipationClass.SUPPORTING:
            return BudgetStopReason.SOFT_CUTOFF
        return BudgetStopReason.HARD_CUTOFF

    def _read_clock(self) -> float:
        value = self.clock()
        if not math.isfinite(value):
            raise LatencyBudgetError("Latency budget clock must be finite")
        return value


def latency_profile_for_plan_class(plan_class: PlanClass) -> LatencyProfile:
    return FROZEN_LATENCY_PROFILES[DECISION_PLAN_LATENCY_PROFILES[plan_class]]


def latency_budget_for_plan(
    approved_plan: ArtifactEnvelope,
    *,
    clock: Callable[[], float] = time.perf_counter,
    started_at: float | None = None,
) -> LatencyBudget:
    if not isinstance(approved_plan.payload, ApprovedWorkPlanPayload):
        raise LatencyBudgetError(
            "Latency budgets require an Approved Work Plan artifact"
        )
    return LatencyBudget(
        profile=FROZEN_LATENCY_PROFILES[approved_plan.payload.budget_profile],
        started_at=clock() if started_at is None else started_at,
        clock=clock,
    )


def apply_hard_cutoff_to_sections(
    state: OrchestrationState,
    budget: LatencyBudget,
) -> OrchestrationState:
    if not budget.checkpoint().hard_cutoff_reached:
        raise LatencyBudgetError(
            "Section hard-cutoff terminalization requires the hard boundary"
        )
    sections: list[SectionNode] = []
    for section in state.sections:
        if section.state in SECTION_TERMINAL_STATES:
            sections.append(section)
            continue
        has_useful_progress = bool(
            section.terminal_verification_claim_ids
        ) or any(
            artifact.payload.kind
            in {
                ArtifactKind.EVIDENCE_UNIT,
                ArtifactKind.STRUCTURED_FACT,
                ArtifactKind.TIMELINE_EVENT,
                ArtifactKind.GENERAL_KNOWLEDGE_UNIT,
            }
            and section.atomic_question_id
            in artifact.scope.atomic_question_ids
            and section.section_key in artifact.scope.section_keys
            for artifact in state.admitted_artifacts
        )
        target = (
            SectionTerminalState.DEGRADED
            if section.required or has_useful_progress
            else SectionTerminalState.OMITTED
        )
        sections.append(
            SectionNode(
                section_id=section.section_id,
                atomic_question_id=section.atomic_question_id,
                section_key=section.section_key,
                required=section.required,
                knowledge_mode=section.knowledge_mode,
                provenance_class=section.provenance_class,
                state=target,
                material_claim_ids=section.terminal_verification_claim_ids,
                terminal_verification_claim_ids=(
                    section.terminal_verification_claim_ids
                ),
            )
        )
    values = state.model_dump(mode="python")
    values["sections"] = tuple(sections)
    return OrchestrationState.model_validate(values)


def latency_profile_json(profile: LatencyProfile) -> str:
    return json.dumps(
        profile.model_dump(mode="json"),
        ensure_ascii=False,
        separators=(",", ":"),
        sort_keys=True,
    )


def budget_checkpoint_json(checkpoint: BudgetCheckpoint) -> str:
    return json.dumps(
        checkpoint.model_dump(mode="json"),
        ensure_ascii=False,
        separators=(",", ":"),
        sort_keys=True,
    )
