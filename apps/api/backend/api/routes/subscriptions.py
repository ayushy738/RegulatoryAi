from fastapi import APIRouter

from backend.api.deps import UserDep
from backend.core.models import SubscriptionSettings

router = APIRouter(prefix="/subscriptions", tags=["subscriptions"])

DEFAULT_SUBSCRIPTION = SubscriptionSettings(
    jurisdictions=["central"],
    topics=["solar", "tariff", "open access", "RPO/REC", "storage", "transmission"],
    email_enabled=True,
    frequency="daily",
)


@router.get("", response_model=SubscriptionSettings)
async def get_subscriptions(user: UserDep) -> SubscriptionSettings:
    return DEFAULT_SUBSCRIPTION


@router.put("", response_model=SubscriptionSettings)
async def update_subscriptions(
    payload: SubscriptionSettings,
    user: UserDep,
) -> SubscriptionSettings:
    return payload
