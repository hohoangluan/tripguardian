"""Public accounts API: Google sign-in, sessions, profile, avatar, deletion, Calendar link, saved items and recent
opens (docs/ACCOUNTS.md)."""

from .library import Library
from .google import CALENDAR_SCOPE, GoogleClient, GoogleError
from .service import AVATAR_MAX_BYTES, GUEST_HOURS, LEAVE_GRACE_S, TERMS_VERSION, Accounts, AuthError, safe_next

__all__ = ["AVATAR_MAX_BYTES", "CALENDAR_SCOPE", "GUEST_HOURS", "LEAVE_GRACE_S", "TERMS_VERSION", "Accounts", "AuthError",
           "GoogleClient", "GoogleError", "Library", "safe_next"]
