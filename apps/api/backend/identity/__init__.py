"""First-party identity infrastructure.

The package is intentionally not wired into the active Supabase authentication path.
"""

from backend.identity.enums import AuditOutcome, IdentityUserStatus
from backend.identity.models import IdentityBase

__all__ = ["AuditOutcome", "IdentityBase", "IdentityUserStatus"]
