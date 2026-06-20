from io import BytesIO

import pdfplumber

from backend.core.config import settings
from backend.core.models import ExtractedDoc, FetchedFile
from backend.core.storage import storage
from backend.core.utils import sha256_normalized_text


def extract(fetched: FetchedFile, data: bytes | None = None) -> ExtractedDoc:
    """Extract normalized text from a downloaded PDF."""

    payload = data
    if payload is None:
        if not settings.supabase_service_role_key:
            raise RuntimeError("Extraction needs raw bytes or configured Supabase Storage.")
        payload = storage.get_bytes(fetched.raw_file_path)

    text_parts: list[str] = []
    page_count = 0
    with pdfplumber.open(BytesIO(payload)) as pdf:
        page_count = len(pdf.pages)
        for page in pdf.pages:
            text_parts.append(page.extract_text() or "")

    text = "\n\n".join(part for part in text_parts if part)
    needs_ocr = len(text.strip()) < 200
    content_hash = sha256_normalized_text(text)
    text_key = fetched.raw_file_path.replace("raw/", "text/", 1).rsplit(".", 1)[0] + ".txt"
    if settings.supabase_service_role_key:
        storage.put_bytes(text_key, text.encode("utf-8"), "text/plain; charset=utf-8")
    return ExtractedDoc(
        fetched=fetched,
        text=text,
        content_hash=content_hash,
        page_count=page_count,
        needs_ocr=needs_ocr,
        text_path=text_key,
    )
