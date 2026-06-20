import requests

from backend.core.config import settings
from backend.core.models import DiscoveredDoc, FetchedFile
from backend.core.storage import storage
from backend.core.utils import sha256_bytes


def download(discovered: DiscoveredDoc, data: bytes | None = None) -> FetchedFile:
    """Download a discovered document and store raw bytes when storage is configured."""

    status = 200
    etag = None
    last_modified = None
    payload = data
    if payload is None:
        response = requests.get(
            discovered.source_url,
            headers={"User-Agent": settings.crawl_user_agent},
            timeout=30,
        )
        status = response.status_code
        response.raise_for_status()
        payload = response.content
        etag = response.headers.get("etag")
        last_modified = response.headers.get("last-modified")

    file_hash = sha256_bytes(payload)
    extension = "pdf" if "pdf" in (discovered.doc_type or "").lower() else "bin"
    key = f"raw/{discovered.source_code}/{file_hash}.{extension}"
    if settings.supabase_service_role_key:
        storage.put_bytes(key, payload, "application/pdf")
    return FetchedFile(
        discovered=discovered,
        file_hash=file_hash,
        raw_file_path=key,
        http_status=status,
        etag=etag,
        last_modified=last_modified,
    )
