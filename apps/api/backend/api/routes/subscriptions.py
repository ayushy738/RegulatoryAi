from fastapi import APIRouter

from backend.api.deps import OptionalUserDep, UserDep
from backend.core.models import SubscriptionSettings
from backend.core.repository import DEMO_USER_ID, get_subscription, update_subscription

router = APIRouter(prefix="/subscriptions", tags=["subscriptions"])


@router.get("", response_model=SubscriptionSettings)
async def get_subscriptions(user: OptionalUserDep) -> SubscriptionSettings:
    return get_subscription(user.id if user else DEMO_USER_ID)


@router.put("", response_model=SubscriptionSettings)
async def update_subscriptions(
    payload: SubscriptionSettings,
    user: UserDep,
) -> SubscriptionSettings:
    return update_subscription(user.id, payload)
