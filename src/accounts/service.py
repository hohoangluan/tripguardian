"""Accounts in Postgres: Google sign-in, cookie sessions (only the token hash is stored), profile, avatar, deletion,
and the encrypted Calendar refresh token (docs/ACCOUNTS.md)."""

import base64
import hashlib
import io
import re
import secrets
import uuid
from datetime import datetime, timedelta, UTC
from pathlib import Path

from psycopg.types.json import Jsonb

from .google import CALENDAR_SCOPE, LOGIN_SCOPES, GoogleClient, GoogleError

SESSION_DAYS = 30
GUEST_DAYS = 1  # a guest session never slides: the trial lasts a day
SLIDE_AFTER_S = 3600  # a session seen again after this long gets 30 fresh days
STATE_MINUTES = 10
TERMS_VERSION = "2026-10-09"
PROFILE_FIELDS = {"display_name": 60, "home_city": 80, "usual_mobility": 40, "usual_companions": 40}
MOBILITY = {"motorbike", "car"}  # trip.domain.state Vehicle
COMPANIONS = {"solo", "partner", "friends", "kids", "parents"}  # trip.domain.state Who
AVATAR_MAX_BYTES = 5 * 1024 * 1024
AVATAR_PX = 256
AVATAR_FORMATS = {"JPEG", "PNG", "WEBP"}
PLACE_ID = re.compile(r"[A-Za-z0-9_:.-]{1,128}")  # a serving record id ("0x…:0x…"); never shown unescaped
SAVED_MAX = 500  # places kept per account; the oldest go first


class AuthError(ValueError):
    """A sign-in that cannot finish (bad state, refused by Google, disabled account). purpose / next are set once
    the state was recognised, so the server can send the browser back where it came from."""
    purpose: str | None = None
    next: str = "/app"


def _hash(token: str) -> bytes:
    return hashlib.sha256(token.encode()).digest()


def safe_next(path: str | None) -> str:
    """Only a path on this site: never a scheme, a host or a protocol-relative URL."""
    if not path or not path.startswith("/") or path.startswith("//") or "\\" in path or any(c < " " for c in path):
        return "/app"
    return path[:500]


class Accounts:
    def __init__(self, pool, google: GoogleClient, avatars: Path, token_key: str | None = None):
        self.pool, self.google, self.avatars = pool, google, avatars
        self._fernet = None
        if token_key:
            from cryptography.fernet import Fernet
            self._fernet = Fernet(token_key.encode())

    # --- sign-in ---------------------------------------------------------------------------------------------

    def start(self, purpose: str, next_path: str | None, user_id: str | None = None) -> tuple[str, str]:
        """(state, Google URL). The state row carries purpose, next and the PKCE verifier for the callback."""
        if purpose not in ("login", "calendar") or (purpose == "calendar" and not user_id):
            raise AuthError("bad purpose")
        state, verifier = secrets.token_urlsafe(24), secrets.token_urlsafe(48)
        challenge = base64.urlsafe_b64encode(hashlib.sha256(verifier.encode()).digest()).rstrip(b"=").decode()
        with self.pool.connection() as conn:
            conn.execute("DELETE FROM oauth_states WHERE expires_at < now()")
            conn.execute("INSERT INTO oauth_states (state, purpose, next, verifier, user_id, expires_at) "
                         "VALUES (%s, %s, %s, %s, %s, now() + make_interval(mins => %s))",
                         (state, purpose, safe_next(next_path), verifier, user_id, STATE_MINUTES))
        scopes = LOGIN_SCOPES + ((CALENDAR_SCOPE,) if purpose == "calendar" else ())
        return state, self.google.auth_url(state, challenge, scopes, offline=purpose == "calendar")

    def callback(self, state: str, code: str, user_agent: str = "") -> dict:
        """{purpose, next, token?}. Login makes a session; Calendar stores the refresh token for the state's user."""
        with self.pool.connection() as conn:
            row = conn.execute("DELETE FROM oauth_states WHERE state = %s AND expires_at > now() RETURNING *",
                               (state,)).fetchone()
        if not row:
            raise AuthError("expired or unknown state")
        try:
            return self._finish(row, code, user_agent)
        except AuthError as exc:
            exc.purpose, exc.next = row["purpose"], row["next"]
            raise

    def _finish(self, row: dict, code: str, user_agent: str) -> dict:
        try:
            tokens = self.google.exchange(code, row["verifier"])
            claims = self.google.verify(tokens["id_token"])
        except (GoogleError, KeyError) as exc:
            raise AuthError(str(exc)) from exc
        if not claims.get("email_verified", False):
            raise AuthError("unverified Google email")
        out = {"purpose": row["purpose"], "next": row["next"]}
        if row["purpose"] == "login":
            out["token"] = self.session(self._upsert(claims), user_agent)
            return out
        if not tokens.get("refresh_token") or CALENDAR_SCOPE not in tokens.get("scope", "").split():
            raise AuthError("Calendar permission was not granted")
        with self.pool.connection() as conn:
            owner = conn.execute("SELECT google_sub FROM users WHERE id = %s", (row["user_id"],)).fetchone()
        if not owner or owner["google_sub"] != claims["sub"]:
            raise AuthError("Calendar was granted by another Google account")
        self.link_calendar(str(row["user_id"]), tokens["refresh_token"], tokens["scope"].split())
        return out

    def _upsert(self, claims: dict) -> str:
        with self.pool.connection() as conn:
            row = conn.execute(
                "INSERT INTO users (google_sub, email, display_name, picture_url, last_login_at) "
                "VALUES (%s, %s, %s, %s, now()) ON CONFLICT (google_sub) DO UPDATE SET email = EXCLUDED.email, "
                "picture_url = EXCLUDED.picture_url, last_login_at = now(), "
                "display_name = coalesce(users.display_name, EXCLUDED.display_name) RETURNING id, status",
                (claims["sub"], claims.get("email"), (claims.get("name") or "")[:60] or None, claims.get("picture"))
            ).fetchone()
            if row["status"] != "active":
                raise AuthError("account is not active")
            conn.execute("INSERT INTO profiles (user_id) VALUES (%s) ON CONFLICT DO NOTHING", (row["id"],))
        return str(row["id"])

    def test_login(self, email: str, name: str, user_agent: str = "") -> str:
        """Only for the walk-through route that the server enables with TG_TEST_LOGIN on a non-https base URL."""
        return self.session(self._upsert({"sub": "test:" + email, "email": email, "name": name}), user_agent)

    def session(self, user_id: str, user_agent: str = "", days: int = SESSION_DAYS) -> str:
        token = secrets.token_urlsafe(32)
        with self.pool.connection() as conn:
            conn.execute("INSERT INTO auth_sessions (token_hash, user_id, expires_at, user_agent) "
                         "VALUES (%s, %s, now() + make_interval(days => %s), %s)",
                         (_hash(token), user_id, days, user_agent[:300]))
        return token

    def guest(self, user_agent: str = "") -> str:
        """A trial visitor: a new users row with role 'guest' (no email, no profile) and a one-day session. The row and
        everything it owns stay, so the Admin can still read what the guest did."""
        with self.pool.connection() as conn:
            row = conn.execute("INSERT INTO users (role, display_name, last_login_at) VALUES ('guest', 'Khách', now()) "
                               "RETURNING id").fetchone()
        return self.session(str(row["id"]), user_agent, GUEST_DAYS)

    def user_for(self, token: str | None) -> tuple[dict | None, bool]:
        """(user, refreshed): refreshed means the server should send the cookie again with 30 fresh days."""
        if not token or len(token) > 100:
            return None, False
        with self.pool.connection() as conn:
            row = conn.execute(
                "SELECT u.id, u.role, extract(epoch FROM now() - s.last_seen_at) AS idle FROM auth_sessions s "
                "JOIN users u ON u.id = s.user_id WHERE s.token_hash = %s AND s.expires_at > now() "
                "AND u.status = 'active' AND u.deleted_at IS NULL", (_hash(token),)).fetchone()
            if not row:
                return None, False
            refreshed = row["idle"] > SLIDE_AFTER_S and row["role"] != "guest"
            if refreshed:
                conn.execute("UPDATE auth_sessions SET last_seen_at = now(), "
                             "expires_at = now() + make_interval(days => %s) WHERE token_hash = %s",
                             (SESSION_DAYS, _hash(token)))
        return {"id": row["id"].hex, "role": row["role"]}, refreshed

    def logout(self, token: str | None) -> None:
        if token:
            with self.pool.connection() as conn:
                conn.execute("DELETE FROM auth_sessions WHERE token_hash = %s", (_hash(token),))

    # --- profile -----------------------------------------------------------------------------------------------

    def me(self, user_id: str) -> dict:
        with self.pool.connection() as conn:
            row = conn.execute(
                "SELECT u.id, u.email, u.display_name, u.picture_url, u.avatar_key, u.role, u.created_at, "
                "p.home_city, p.usual_mobility, p.usual_companions, p.consents, "
                "(c.user_id IS NOT NULL AND c.revoked_at IS NULL) AS calendar "
                "FROM users u LEFT JOIN profiles p ON p.user_id = u.id "
                "LEFT JOIN calendar_links c ON c.user_id = u.id WHERE u.id = %s", (user_id,)).fetchone()
        if not row:
            raise KeyError(user_id)
        consents = row["consents"] or {}
        return {"id": row["id"].hex, "email": row["email"], "name": row["display_name"] or "",
                "avatar": f"/api/harness/avatars/{row['avatar_key']}" if row["avatar_key"] else row["picture_url"],
                "role": row["role"], "home_city": row["home_city"], "usual_mobility": row["usual_mobility"],
                "usual_companions": row["usual_companions"], "consents": consents,
                "needs_consent": row["role"] != "guest" and (consents.get("terms") or {}).get("version") != TERMS_VERSION,
                "calendar": row["calendar"], "terms_version": TERMS_VERSION}

    def consent(self, user_id: str, version: str) -> dict:
        if version != TERMS_VERSION:
            raise ValueError("terms version is not current")
        stamp = {"version": version, "at": datetime.now(UTC).isoformat(timespec="seconds")}
        with self.pool.connection() as conn:
            conn.execute("UPDATE profiles SET consents = consents || %s, updated_at = now() WHERE user_id = %s",
                         (Jsonb({"terms": stamp, "privacy": stamp}), user_id))
        return self.me(user_id)

    def set_patterns(self, user_id: str, on: bool) -> dict:
        """Whether TripGuardian may remember this account's explicit choices across trips and use them to ask less
        (docs/P2_TRIP_UNDERSTANDING.md §17). Separate from the terms; the caller forgets what was learned when it is off."""
        if not isinstance(on, bool):
            raise ValueError("patterns must be true or false")
        with self.pool.connection() as conn:
            conn.execute("UPDATE profiles SET consents = consents || %s, updated_at = now() WHERE user_id = %s",
                         (Jsonb({"patterns": on}), user_id))
        return self.me(user_id)

    def update(self, user_id: str, patch: dict) -> dict:
        """Optional fields; null or "" clears one. Values are only a prior for Trip, never facts of a trip."""
        if not patch or set(patch) - set(PROFILE_FIELDS):
            raise ValueError("unknown profile field")
        clean = {}
        for key, value in patch.items():
            if value is not None and not isinstance(value, str):
                raise ValueError(f"{key} must be text")
            value = (value or "").strip() or None
            if value and len(value) > PROFILE_FIELDS[key]:
                raise ValueError(f"{key} is too long")
            if value and ((key == "usual_mobility" and value not in MOBILITY)
                          or (key == "usual_companions" and value not in COMPANIONS)):
                raise ValueError(f"bad {key}")
            clean[key] = value
        with self.pool.connection() as conn:
            if "display_name" in clean:
                conn.execute("UPDATE users SET display_name = %s WHERE id = %s", (clean.pop("display_name"), user_id))
            for key, value in clean.items():  # keys come from PROFILE_FIELDS only
                conn.execute(f"UPDATE profiles SET {key} = %s, updated_at = now() WHERE user_id = %s", (value, user_id))
        return self.me(user_id)

    def set_avatar(self, user_id: str, data: bytes) -> dict:
        """Decoded and re-encoded (square crop, 256 px WebP, no EXIF); the uploaded file itself is never kept."""
        from PIL import Image, ImageOps, UnidentifiedImageError
        if not data or len(data) > AVATAR_MAX_BYTES:
            raise ValueError("avatar must be at most 5 MB")
        try:
            with Image.open(io.BytesIO(data)) as img:
                if img.format not in AVATAR_FORMATS:
                    raise ValueError("avatar must be JPEG, PNG or WebP")
                img = ImageOps.exif_transpose(img).convert("RGB")
        except (UnidentifiedImageError, OSError, Image.DecompressionBombError) as exc:
            raise ValueError("avatar is not a readable image") from exc
        img = ImageOps.fit(img, (AVATAR_PX, AVATAR_PX), Image.Resampling.LANCZOS)
        key = uuid.uuid4().hex
        self.avatars.mkdir(parents=True, exist_ok=True)
        img.save(self.avatars / f"{key}.webp", "WEBP", quality=85)
        with self.pool.connection() as conn:
            old = conn.execute("SELECT avatar_key FROM users WHERE id = %s", (user_id,)).fetchone()
            conn.execute("UPDATE users SET avatar_key = %s WHERE id = %s", (key, user_id))
        if old and old["avatar_key"]:
            (self.avatars / f"{old['avatar_key']}.webp").unlink(missing_ok=True)
        return self.me(user_id)

    def avatar_path(self, key: str) -> Path:
        if len(key) != 32 or any(c not in "0123456789abcdef" for c in key):
            raise KeyError(key)
        path = self.avatars / f"{key}.webp"
        if not path.exists():
            raise KeyError(key)
        return path

    def delete(self, user_id: str) -> None:
        """Personal rows and files go; journeys, events, feedback, trips and notifications stay without a user."""
        token = self.calendar_token(user_id)
        if token:
            try:
                self.google.revoke(token)
            except GoogleError:
                pass  # the token is deleted here either way; Google expires an unused one
        with self.pool.connection() as conn:
            row = conn.execute("SELECT avatar_key FROM users WHERE id = %s", (user_id,)).fetchone()
            for table in ("profiles", "calendar_links", "push_subscriptions", "notification_prefs", "auth_sessions",
                          "oauth_states", "saved_places"):
                conn.execute(f"DELETE FROM {table} WHERE user_id = %s", (user_id,))
            for table in ("journeys", "events", "feedback", "trips", "notifications"):
                conn.execute(f"UPDATE {table} SET user_id = NULL WHERE user_id = %s", (user_id,))
            conn.execute("UPDATE users SET deleted_at = now(), status = 'deleted', email = NULL, display_name = NULL, "
                         "picture_url = NULL, google_sub = NULL, avatar_key = NULL WHERE id = %s", (user_id,))
        if row and row["avatar_key"]:
            (self.avatars / f"{row['avatar_key']}.webp").unlink(missing_ok=True)

    # --- saved places ("Đã lưu") -------------------------------------------------------------------------------

    def saved(self, user_id: str) -> list[str]:
        """Place ids, newest first."""
        with self.pool.connection() as conn:
            rows = conn.execute("SELECT place_id FROM saved_places WHERE user_id = %s ORDER BY saved_at DESC, place_id",
                                (user_id,)).fetchall()
        return [r["place_id"] for r in rows]

    def save_places(self, user_id: str, place_ids: list) -> list[str]:
        """Adds places (one heart, or a browser's old local list merged once); saving twice keeps the first time.
        Returns the whole list."""
        if not isinstance(place_ids, list) or not 1 <= len(place_ids) <= SAVED_MAX:
            raise ValueError(f"place_ids must be a list of 1 to {SAVED_MAX} ids")
        if not all(isinstance(p, str) and PLACE_ID.fullmatch(p) for p in place_ids):
            raise ValueError("bad place id")
        now = datetime.now(UTC)
        with self.pool.connection() as conn:
            for i, pid in enumerate(place_ids):  # the first id is the newest, as in the list the browser shows
                conn.execute("INSERT INTO saved_places (user_id, place_id, saved_at) VALUES (%s, %s, %s) "
                             "ON CONFLICT DO NOTHING", (user_id, pid, now - timedelta(microseconds=i)))
            conn.execute("DELETE FROM saved_places WHERE user_id = %s AND place_id NOT IN (SELECT place_id FROM "
                         "saved_places WHERE user_id = %s ORDER BY saved_at DESC LIMIT %s)", (user_id, user_id, SAVED_MAX))
        return self.saved(user_id)

    def unsave_place(self, user_id: str, place_id: str) -> list[str]:
        if not isinstance(place_id, str) or not PLACE_ID.fullmatch(place_id):
            raise ValueError("bad place id")
        with self.pool.connection() as conn:
            conn.execute("DELETE FROM saved_places WHERE user_id = %s AND place_id = %s", (user_id, place_id))
        return self.saved(user_id)

    # --- Calendar link -----------------------------------------------------------------------------------------

    def link_calendar(self, user_id: str, refresh_token: str, scopes: list[str]) -> None:
        if not self._fernet:
            raise RuntimeError("TOKEN_ENC_KEY is not set")
        with self.pool.connection() as conn:
            conn.execute("INSERT INTO calendar_links (user_id, refresh_token_enc, scopes) VALUES (%s, %s, %s) "
                         "ON CONFLICT (user_id) DO UPDATE SET refresh_token_enc = EXCLUDED.refresh_token_enc, "
                         "scopes = EXCLUDED.scopes, connected_at = now(), revoked_at = NULL",
                         (user_id, self._fernet.encrypt(refresh_token.encode()), scopes))

    def calendar_token(self, user_id: str) -> str | None:
        with self.pool.connection() as conn:
            row = conn.execute("SELECT refresh_token_enc FROM calendar_links WHERE user_id = %s AND revoked_at IS NULL",
                               (user_id,)).fetchone()
        if not row or not row["refresh_token_enc"] or not self._fernet:
            return None
        return self._fernet.decrypt(bytes(row["refresh_token_enc"])).decode()

    def unlink_calendar(self, user_id: str) -> None:
        token = self.calendar_token(user_id)
        if token:
            try:
                self.google.revoke(token)
            except GoogleError:
                pass
        with self.pool.connection() as conn:
            conn.execute("UPDATE calendar_links SET refresh_token_enc = NULL, revoked_at = now() WHERE user_id = %s",
                         (user_id,))
