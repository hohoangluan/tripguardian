"""Accounts in Postgres: Google sign-in, cookie sessions (only the token hash is stored), profile, avatar, deletion,
and the encrypted Calendar refresh token (docs/ACCOUNTS.md)."""

import base64
import re
import hashlib
import io
import hmac
import secrets
import uuid
from datetime import datetime, timezone
from pathlib import Path

from psycopg.types.json import Jsonb

from .google import CALENDAR_SCOPE, LOGIN_SCOPES, GoogleClient, GoogleError

SESSION_DAYS = 30
SLIDE_AFTER_S = 3600  # a session seen again after this long gets 30 fresh days
GUEST_HOURS = 24  # a guest session lives this long after the last visit; then the guest and their trips are deleted
LEAVE_GRACE_S = 45  # a guest whose page closed is deleted after this long, unless the same guest comes back (a reload)
STATE_MINUTES = 10
TERMS_VERSION = "2026-10-09"
PROFILE_FIELDS = {"display_name": 60, "home_city": 80, "usual_mobility": 40, "usual_companions": 40, "nickname": 24,
                  "bio": 160}
NICKNAME = re.compile(r"[a-z0-9._]{3,24}")  # how friends find each other (users.nickname is unique)
MOBILITY = {"motorbike", "car", "walk"}  # trip.domain.state Vehicle
COMPANIONS = {"solo", "partner", "friends", "kids", "parents"}  # trip.domain.state Who
AVATAR_MAX_BYTES = 5 * 1024 * 1024
AVATAR_PX = 256
AVATAR_FORMATS = {"JPEG", "PNG", "WEBP"}
EMAIL = re.compile(r"[^@\s]{1,64}@[^@\s.]+(\.[^@\s.]+)+")
PASSWORD_MIN, PASSWORD_MAX = 8, 128
SCRYPT = {"n": 2 ** 14, "r": 8, "p": 1}


class AuthError(ValueError):
    """A sign-in that cannot finish (bad state, refused by Google, disabled account). purpose / next are set once
    the state was recognised, so the server can send the browser back where it came from."""
    purpose: str | None = None
    next: str = "/app"


def _hash(token: str) -> bytes:
    return hashlib.sha256(token.encode()).digest()


def _scrypt(password: str, salt: bytes, n: int, r: int, p: int) -> bytes:
    return hashlib.scrypt(password.encode(), salt=salt, n=n, r=r, p=p, dklen=32, maxmem=128 * n * r * 2)


def hash_password(password: str) -> str:
    salt = secrets.token_bytes(16)
    digest = _scrypt(password, salt, **SCRYPT)
    return "scrypt${n}${r}${p}$".format(**SCRYPT) + base64.b64encode(salt).decode() + "$" + base64.b64encode(digest).decode()


def check_password(password: str, stored: str | None) -> bool:
    """False for a missing or malformed hash too (a Google-only account has none)."""
    try:
        kind, n, r, p, salt, digest = (stored or "").split("$")
        want = base64.b64decode(digest)
        got = _scrypt(password, base64.b64decode(salt), int(n), int(r), int(p))
        return kind == "scrypt" and hmac.compare_digest(got, want)
    except (ValueError, TypeError):
        return False


_DUMMY = hash_password("no-such-account")  # checked when the email is unknown, so timing does not tell who has an account


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
            # Google has confirmed this email. An account made with the same email and a password joins this Google
            # sign-in; its password is dropped and its sessions end, as nobody confirmed that password's owner.
            linked = conn.execute(
                "UPDATE users SET google_sub = %s, password_hash = NULL WHERE email = %s AND google_sub IS NULL "
                "AND password_hash IS NOT NULL AND kind = 'user' RETURNING id", (claims["sub"], claims.get("email"))).fetchone()
            if linked:
                conn.execute("DELETE FROM auth_sessions WHERE user_id = %s", (linked["id"],))
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

    def register(self, email: str, password: str, name: str = "", user_agent: str = "") -> str:
        """A new account from an email and a password; returns the session token. The email is not confirmed by mail:
        it is how this person signs in, nothing more. A taken email is refused (also one that signed in with Google)."""
        email = (email or "").strip().lower()
        name = (name or "").strip()
        if len(email) > 254 or not EMAIL.fullmatch(email):
            raise ValueError("email is not valid")
        if not PASSWORD_MIN <= len(password or "") <= PASSWORD_MAX:
            raise ValueError(f"password must have {PASSWORD_MIN}-{PASSWORD_MAX} characters")
        if len(name) > PROFILE_FIELDS["display_name"]:
            raise ValueError("name is too long")
        digest = hash_password(password)
        with self.pool.connection() as conn:
            row = conn.execute(
                "INSERT INTO users (email, password_hash, display_name, last_login_at) VALUES (%s, %s, %s, now()) "
                "ON CONFLICT (email) DO NOTHING RETURNING id", (email, digest, name or None)).fetchone()
            if not row:
                raise ValueError("email is taken")
            conn.execute("INSERT INTO profiles (user_id) VALUES (%s)", (row["id"],))
        return self.session(str(row["id"]), user_agent)

    def login_password(self, email: str, password: str, user_agent: str = "") -> str:
        """Session token for a right email and password; AuthError otherwise, with one message for every cause."""
        email = (email or "").strip().lower()
        with self.pool.connection() as conn:
            row = conn.execute("SELECT id, password_hash, status FROM users WHERE email = %s AND kind = 'user' "
                               "AND deleted_at IS NULL", (email,)).fetchone()
            ok = check_password(password or "", row["password_hash"] if row else _DUMMY)
            if not (row and ok and row["status"] == "active"):
                raise AuthError("wrong email or password")
            conn.execute("UPDATE users SET last_login_at = now() WHERE id = %s", (row["id"],))
        return self.session(str(row["id"]), user_agent)

    def test_login(self, email: str, name: str, user_agent: str = "") -> str:
        """Only for the walk-through route that the server enables with TG_TEST_LOGIN on a non-https base URL."""
        return self.session(self._upsert({"sub": "test:" + email, "email": email, "name": name}), user_agent)

    def session(self, user_id: str, user_agent: str = "", guest: bool = False) -> str:
        token = secrets.token_urlsafe(32)
        with self.pool.connection() as conn:
            conn.execute("INSERT INTO auth_sessions (token_hash, user_id, expires_at, user_agent) "
                         "VALUES (%s, %s, now() + make_interval(hours => %s), %s)",
                         (_hash(token), user_id, GUEST_HOURS if guest else SESSION_DAYS * 24, user_agent[:300]))
        return token

    def user_for(self, token: str | None) -> tuple[dict | None, bool]:
        """(user, refreshed): refreshed means the server should send the cookie again with fresh time
        (30 days; 24 hours for a guest). The user carries `guest`."""
        if not token or len(token) > 100:
            return None, False
        with self.pool.connection() as conn:
            row = conn.execute(
                "SELECT u.id, u.role, u.kind, s.leaving_at IS NOT NULL AS leaving, "
                "extract(epoch FROM now() - s.last_seen_at) AS idle FROM auth_sessions s "
                "JOIN users u ON u.id = s.user_id WHERE s.token_hash = %s AND s.expires_at > now() "
                "AND u.status = 'active' AND u.deleted_at IS NULL", (_hash(token),)).fetchone()
            if not row:
                return None, False
            guest = row["kind"] == "guest"
            if row["leaving"]:  # the page that was closing came back: same guest, nothing to delete
                conn.execute("UPDATE auth_sessions SET leaving_at = NULL WHERE token_hash = %s", (_hash(token),))
            refreshed = row["idle"] > SLIDE_AFTER_S
            if refreshed:
                conn.execute("UPDATE auth_sessions SET last_seen_at = now(), "
                             "expires_at = now() + make_interval(hours => %s) WHERE token_hash = %s",
                             (GUEST_HOURS if guest else SESSION_DAYS * 24, _hash(token)))
        return {"id": row["id"].hex, "role": row["role"], "guest": guest}, refreshed

    def logout(self, token: str | None) -> None:
        """Ends the session; a guest who leaves takes their trips with them (nobody could open them again)."""
        if token:
            with self.pool.connection() as conn:
                row = conn.execute("DELETE FROM auth_sessions WHERE token_hash = %s RETURNING user_id",
                                   (_hash(token),)).fetchone()
            if row:
                self.drop_guest(str(row["user_id"]))

    # --- guests -------------------------------------------------------------------------------------------------

    def guest(self, user_agent: str = "") -> str:
        """A visitor without an account: a real users row (kind 'guest', no email, no Google) with a 24-hour session,
        so every owner check keyed by user id works unchanged. Returns the session token."""
        self.purge_guests()
        with self.pool.connection() as conn:
            uid = conn.execute("INSERT INTO users (kind, last_login_at) VALUES ('guest', now()) RETURNING id").fetchone()["id"]
            conn.execute("INSERT INTO profiles (user_id) VALUES (%s)", (uid,))
        return self.session(str(uid), user_agent, guest=True)

    def leave(self, token: str | None) -> None:
        """The browser says this guest's page is closing: mark the session; `purge_leavers` deletes the guest soon
        unless a request from the same session (user_for) arrives first. Accounts are never marked."""
        if token and len(token) <= 100:
            with self.pool.connection() as conn:
                conn.execute("UPDATE auth_sessions s SET leaving_at = now() FROM users u "
                             "WHERE s.token_hash = %s AND u.id = s.user_id AND u.kind = 'guest'", (_hash(token),))

    def purge_leavers(self) -> int:
        """Deletes the guests whose page closed more than LEAVE_GRACE_S ago and who did not come back."""
        with self.pool.connection() as conn:
            ids = [r["id"] for r in conn.execute(
                "SELECT u.id FROM users u WHERE u.kind = 'guest' AND NOT EXISTS (SELECT 1 FROM auth_sessions s "
                "WHERE s.user_id = u.id AND (s.leaving_at IS NULL OR s.leaving_at > now() - make_interval(secs => %s))) "
                "AND EXISTS (SELECT 1 FROM auth_sessions s WHERE s.user_id = u.id)", (LEAVE_GRACE_S,)).fetchall()]
            self._drop(conn, ids)
        return len(ids)

    def drop_guest(self, user_id: str) -> bool:
        """Deletes one guest (False when the user is not a guest): the trips go; journeys, events and feedback stay
        without a user, as when an account is deleted."""
        with self.pool.connection() as conn:
            row = conn.execute("SELECT 1 FROM users WHERE id = %s AND kind = 'guest'", (user_id,)).fetchone()
            if row:
                self._drop(conn, [user_id])
        return bool(row)

    def purge_guests(self) -> int:
        """Deletes every guest whose sessions have all expired."""
        with self.pool.connection() as conn:
            ids = [r["id"] for r in conn.execute(
                "SELECT id FROM users u WHERE kind = 'guest' AND NOT EXISTS "
                "(SELECT 1 FROM auth_sessions s WHERE s.user_id = u.id AND s.expires_at > now())").fetchall()]
            self._drop(conn, ids)
        return len(ids)

    @staticmethod
    def _drop(conn, ids: list) -> None:
        if ids:
            conn.execute("DELETE FROM trips WHERE user_id = ANY(%s::uuid[])", (ids,))  # stops and check-ins go with them
            conn.execute("DELETE FROM users WHERE id = ANY(%s::uuid[])", (ids,))  # sessions, profile: cascade; the rest: SET NULL

    # --- profile -----------------------------------------------------------------------------------------------

    def me(self, user_id: str) -> dict:
        with self.pool.connection() as conn:
            row = conn.execute(
                "SELECT u.id, u.email, u.display_name, u.nickname, u.bio, u.picture_url, u.avatar_key, u.role, u.kind, u.created_at, "
                "p.home_city, p.usual_mobility, p.usual_companions, p.consents, "
                "(c.user_id IS NOT NULL AND c.revoked_at IS NULL) AS calendar "
                "FROM users u LEFT JOIN profiles p ON p.user_id = u.id "
                "LEFT JOIN calendar_links c ON c.user_id = u.id WHERE u.id = %s", (user_id,)).fetchone()
        if not row:
            raise KeyError(user_id)
        consents = row["consents"] or {}
        guest = row["kind"] == "guest"
        return {"id": row["id"].hex, "email": row["email"], "name": row["display_name"] or "", "guest": guest,
                "nickname": row["nickname"], "bio": row["bio"] or "",
                "avatar": f"/api/harness/avatars/{row['avatar_key']}" if row["avatar_key"] else row["picture_url"],
                "role": row["role"], "home_city": row["home_city"], "usual_mobility": row["usual_mobility"],
                "usual_companions": row["usual_companions"], "consents": consents,
                "needs_consent": not guest and (consents.get("terms") or {}).get("version") != TERMS_VERSION,
                "calendar": row["calendar"], "terms_version": TERMS_VERSION}

    def consent(self, user_id: str, version: str) -> dict:
        if version != TERMS_VERSION:
            raise ValueError("terms version is not current")
        stamp = {"version": version, "at": datetime.now(timezone.utc).isoformat(timespec="seconds")}
        with self.pool.connection() as conn:
            conn.execute("UPDATE profiles SET consents = consents || %s, updated_at = now() WHERE user_id = %s",
                         (Jsonb({"terms": stamp, "privacy": stamp}), user_id))
        return self.me(user_id)

    def update(self, user_id: str, patch: dict) -> dict:
        """Optional fields; null or "" clears one. Mobility and companions are only a prior for Trip, never facts of a
        trip; nickname and bio are what friends see."""
        if not patch or set(patch) - set(PROFILE_FIELDS):
            raise ValueError("unknown profile field")
        clean = {}
        for key, value in patch.items():
            if value is not None and not isinstance(value, str):
                raise ValueError(f"{key} must be text")
            value = (value or "").strip() or None
            if value and key == "nickname":
                value = value.lstrip("@").lower()
                if not NICKNAME.fullmatch(value):
                    raise ValueError("nickname: 3-24 of a-z, 0-9, dot, underscore")
            if value and len(value) > PROFILE_FIELDS[key]:
                raise ValueError(f"{key} is too long")
            if value and ((key == "usual_mobility" and value not in MOBILITY)
                          or (key == "usual_companions" and value not in COMPANIONS)):
                raise ValueError(f"bad {key}")
            clean[key] = value
        with self.pool.connection() as conn:
            for key in ("display_name", "nickname", "bio"):  # columns of users; the rest live in profiles
                if key in clean:
                    if key == "nickname" and clean[key] and conn.execute(
                            "SELECT 1 FROM users WHERE nickname = %s AND id <> %s", (clean[key], user_id)).fetchone():
                        raise ValueError("nickname is taken")
                    conn.execute(f"UPDATE users SET {key} = %s WHERE id = %s", (clean.pop(key), user_id))
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
        """Personal rows and files go (friends, messages and saved items too); journeys, events, feedback, trips and
        notifications stay without a user."""
        token = self.calendar_token(user_id)
        if token:
            try:
                self.google.revoke(token)
            except GoogleError:
                pass  # the token is deleted here either way; Google expires an unused one
        with self.pool.connection() as conn:
            row = conn.execute("SELECT avatar_key FROM users WHERE id = %s", (user_id,)).fetchone()
            for table in ("profiles", "calendar_links", "push_subscriptions", "notification_prefs", "auth_sessions",
                          "oauth_states", "saved_items"):
                conn.execute(f"DELETE FROM {table} WHERE user_id = %s", (user_id,))
            conn.execute("DELETE FROM friendships WHERE requester = %s OR addressee = %s", (user_id, user_id))
            conn.execute("DELETE FROM messages WHERE sender = %s OR recipient = %s", (user_id, user_id))
            for table in ("journeys", "events", "feedback", "trips", "notifications"):
                conn.execute(f"UPDATE {table} SET user_id = NULL WHERE user_id = %s", (user_id,))
            conn.execute("UPDATE users SET deleted_at = now(), status = 'deleted', email = NULL, display_name = NULL, "
                         "picture_url = NULL, google_sub = NULL, password_hash = NULL, avatar_key = NULL, nickname = NULL, bio = NULL WHERE id = %s", (user_id,))
        if row and row["avatar_key"]:
            (self.avatars / f"{row['avatar_key']}.webp").unlink(missing_ok=True)

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
