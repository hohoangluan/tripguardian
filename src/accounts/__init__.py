"""Public accounts API: Google sign-in, sessions, profile, avatar, deletion, Calendar link (docs/ACCOUNTS.md)."""

from .google import CALENDAR_SCOPE, GoogleClient, GoogleError
from .service import AVATAR_MAX_BYTES, TERMS_VERSION, Accounts, AuthError, safe_next

__all__ = ["AVATAR_MAX_BYTES", "CALENDAR_SCOPE", "TERMS_VERSION", "Accounts", "AuthError", "GoogleClient",
           "GoogleError", "safe_next"]
