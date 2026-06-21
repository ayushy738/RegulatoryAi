from fastapi import APIRouter, HTTPException

from backend.core.repository import get_system_document, list_system_documents

router = APIRouter(prefix="/meta", tags=["meta"])


@router.get("/docs")
async def docs_index() -> list[dict[str, str]]:
    return list_system_documents()


@router.get("/docs/{slug}")
async def docs_detail(slug: str) -> dict[str, str]:
    document = get_system_document(slug)
    if document:
        return document
    raise HTTPException(status_code=404, detail="Document not found")
