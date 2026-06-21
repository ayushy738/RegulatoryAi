from functools import cached_property

from backend.core.config import settings


class SupabaseStorage:
    """Small wrapper around Supabase Storage using the service-role key."""

    @cached_property
    def client(self):
        settings.require_supabase_storage()
        from supabase import create_client

        return create_client(settings.supabase_project_url, settings.supabase_service_role_key)

    def put_bytes(self, key: str, data: bytes, content_type: str) -> str:
        response = self.client.storage.from_(settings.supabase_storage_bucket).upload(
            key,
            data,
            {"content-type": content_type, "upsert": "true"},
        )
        if hasattr(response, "error") and response.error:
            raise RuntimeError(str(response.error))
        return key

    def get_bytes(self, key: str) -> bytes:
        return self.client.storage.from_(settings.supabase_storage_bucket).download(key)

    def signed_url(self, key: str, expires_s: int = 3600) -> str:
        response = self.client.storage.from_(settings.supabase_storage_bucket).create_signed_url(
            key,
            expires_s,
        )
        if isinstance(response, dict):
            return response["signedURL"]
        return response.signed_url


storage = SupabaseStorage()
