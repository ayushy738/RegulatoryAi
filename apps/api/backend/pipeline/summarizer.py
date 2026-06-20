from backend.core.config import settings
from backend.core.llm import get_llm_client
from backend.core.models import ExtractedDoc, SummaryPayload

SUMMARY_SYSTEM = (
    "You summarize Indian energy regulatory updates. Return strict JSON with: "
    "plain_english_summary, why_it_matters, affected_segments, important_dates, "
    "action_required, confidence, evidence_quotes. Do not invent dates, "
    "obligations, section numbers, or penalties."
)


def summarize(extracted: ExtractedDoc) -> SummaryPayload:
    context = (
        f"Title: {extracted.fetched.discovered.title}\n"
        f"Source: {extracted.fetched.discovered.source_url}\n"
        f"Text excerpt:\n{extracted.text[:6000]}"
    )
    model = settings.llm_model_summary or "offline-demo"
    payload = get_llm_client().complete_json(SUMMARY_SYSTEM, context, model)
    return SummaryPayload.model_validate(payload)
