from fastapi import APIRouter

from backend.api.deps import UserDep
from backend.core.models import SubscriptionSettings
from backend.core.repository import get_subscription, update_subscription

router = APIRouter(prefix="/subscriptions", tags=["subscriptions"])


@router.get("", response_model=SubscriptionSettings)
async def get_subscriptions(user: UserDep) -> SubscriptionSettings:
    return get_subscription(user.id)


@router.put("", response_model=SubscriptionSettings)
async def update_subscriptions(
    payload: SubscriptionSettings,
    user: UserDep,
) -> SubscriptionSettings:
    return update_subscription(user.id, payload)
