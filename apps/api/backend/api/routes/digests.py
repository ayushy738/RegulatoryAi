from datetime import date

from fastapi import APIRouter

from backend.api.deps import UserDep
from backend.core.models import DigestResponse
from backend.core.sample_data import SAMPLE_DIGEST

router = APIRouter(prefix="/digests", tags=["digests"])


@router.get("/latest", response_model=DigestResponse)
async def latest_digest(user: UserDep) -> DigestResponse:
    return SAMPLE_DIGEST


@router.get("/{digest_date}", response_model=DigestResponse)
async def digest_by_date(digest_date: date, user: UserDep) -> DigestResponse:
    return SAMPLE_DIGEST.model_copy(update={"digest_date": digest_date})
