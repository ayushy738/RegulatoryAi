from fastapi import APIRouter, Query

from backend.api.deps import UserDep
from backend.core.intelligence_repository import (
    get_stakeholder_intelligence,
    intelligence_readiness_report,
    list_intelligence_deadlines,
    list_obligation_groups,
    list_stakeholder_intelligence,
)
from backend.core.models import (
    IntelligenceDeadline,
    IntelligenceReadinessReport,
    StakeholderIntelligence,
    StakeholderObligationGroup,
)

router = APIRouter(prefix="/intelligence", tags=["intelligence"])


@router.get("/deadlines", response_model=list[IntelligenceDeadline])
async def active_deadlines(
    user: UserDep,
    issuer: str | None = None,
    deadline_type: str | None = None,
    stakeholder: str | None = None,
    status: str = Query(default="active", pattern="^(active|historical|all)$"),
    limit: int = Query(default=100, ge=1, le=500),
) -> list[IntelligenceDeadline]:
    del user
    return list_intelligence_deadlines(
        issuer=issuer,
        deadline_type=deadline_type,
        stakeholder=stakeholder,
        status=status,
        limit=limit,
    )


@router.get("/obligations", response_model=list[StakeholderObligationGroup])
async def obligations(
    user: UserDep,
    stakeholder: str | None = None,
    issuer: str | None = None,
    limit: int = Query(default=200, ge=1, le=500),
) -> list[StakeholderObligationGroup]:
    del user
    return list_obligation_groups(stakeholder=stakeholder, issuer=issuer, limit=limit)


@router.get("/stakeholders", response_model=list[StakeholderIntelligence])
async def stakeholders(user: UserDep) -> list[StakeholderIntelligence]:
    del user
    return list_stakeholder_intelligence()


@router.get("/stakeholders/{stakeholder_slug}", response_model=StakeholderIntelligence)
async def stakeholder_detail(
    stakeholder_slug: str,
    user: UserDep,
) -> StakeholderIntelligence:
    del user
    return get_stakeholder_intelligence(stakeholder_slug)


@router.get("/readiness", response_model=IntelligenceReadinessReport)
async def readiness(user: UserDep) -> IntelligenceReadinessReport:
    del user
    return intelligence_readiness_report()
