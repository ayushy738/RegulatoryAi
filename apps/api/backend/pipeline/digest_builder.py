from datetime import date

from backend.core.models import DigestResponse
from backend.core.sample_data import SAMPLE_DIGEST


def build_digest(run_date: date | None = None) -> DigestResponse:
    digest_date = run_date or date.today()
    return SAMPLE_DIGEST.model_copy(update={"digest_date": digest_date})
