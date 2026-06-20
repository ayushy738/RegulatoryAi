from backend.core.models import DetectResult, ExtractedDoc


def detect(extracted: ExtractedDoc) -> DetectResult:
    """Classify document changes.

    This is intentionally narrow until DB state is wired: first persisted version
    becomes NEW; later DB-backed logic will compare URL, file_hash, and content_hash.
    """

    return DetectResult(
        document_id=0,
        version_id=0,
        event_type="NEW",
        is_new_event=True,
    )
