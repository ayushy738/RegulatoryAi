from datetime import date

from fastapi import APIRouter

from backend.api.deps import OptionalUserDep
from backend.core.models import DigestResponse
from backend.core.repository import DEMO_USER_ID
from backend.core.repository import digest_by_date as get_digest_by_date
from backend.core.repository import latest_digest as get_latest_digest

router = APIRouter(prefix="/digests", tags=["digests"])


@router.get("/latest", response_model=DigestResponse)
async def latest_digest(user: OptionalUserDep) -> DigestResponse:
    return get_latest_digest(user.id if user else DEMO_USER_ID)


@router.get("/{digest_date}", response_model=DigestResponse)
async def digest_by_date(digest_date: date, user: OptionalUserDep) -> DigestResponse:
    return get_digest_by_date(digest_date, user.id if user else DEMO_USER_ID)
