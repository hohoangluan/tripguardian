import io
import urllib.parse

import pytest
from cryptography.fernet import Fernet
from PIL import Image

from accounts import CALENDAR_SCOPE, TERMS_VERSION, Accounts, AuthError, GoogleError, safe_next

pytestmark = pytest.mark.pg


class FakeGoogle:
    """Google stand-in: the code handed to exchange() names the claims it returns."""
    def __init__(self):
        self.revoked, self.users = [], {}

    def auth_url(self, state, challenge, scopes, offline=False):
        return "https://google.test/auth?" + urllib.parse.urlencode(
            {"state": state, "scope": " ".join(scopes), "offline": offline, "challenge": challenge})

    def exchange(self, code, verifier):
        if code == "bad":
            raise GoogleError("invalid_grant")
        sub, _, extra = code.partition("+")
        tokens = {"id_token": sub, "scope": "openid email profile"}
        if extra == "calendar":
            tokens |= {"refresh_token": "refresh-" + sub, "scope": "openid email profile " + CALENDAR_SCOPE}
        return tokens

    def verify(self, id_token):
        return {"sub": id_token, "email": f"{id_token}@example.com", "email_verified": True, "name": "Lan Anh",
                "picture": "https://lh3.example/p.jpg"}

    def revoke(self, token):
        self.revoked.append(token)


@pytest.fixture
def accounts(pg_url, tmp_path):
    from psycopg.rows import dict_row
    from psycopg_pool import ConnectionPool
    pool = ConnectionPool(pg_url, min_size=1, max_size=4, kwargs={"row_factory": dict_row}, open=True)
    yield Accounts(pool, FakeGoogle(), tmp_path / "avatars", Fernet.generate_key().decode())
    pool.close()


def login(accounts, sub="g-1", next_path="/app/trips"):
    state, url = accounts.start("login", next_path)
    assert "state=" + state in url and "calendar" not in url
    return accounts.callback(state, sub)


def test_google_login_creates_one_user_and_a_session(accounts):
    out = login(accounts)
    assert out["purpose"] == "login" and out["next"] == "/app/trips"
    user, refreshed = accounts.user_for(out["token"])
    assert user["role"] == "user" and not refreshed
    again, _ = accounts.user_for(login(accounts)["token"])
    assert again["id"] == user["id"]
    me = accounts.me(user["id"])
    assert me["email"] == "g-1@example.com" and me["name"] == "Lan Anh" and me["needs_consent"]
    assert me["avatar"] == "https://lh3.example/p.jpg"


def test_state_is_single_use_and_next_stays_on_site(accounts):
    state, _ = accounts.start("login", "https://evil.example/x")
    assert accounts.callback(state, "g-2")["next"] == "/app"
    with pytest.raises(AuthError):
        accounts.callback(state, "g-2")
    with pytest.raises(AuthError):
        accounts.callback("never-issued", "g-2")
    assert safe_next("//evil.example") == "/app" and safe_next("/app/today?stop=1") == "/app/today?stop=1"


def test_failed_exchange_is_an_auth_error(accounts):
    state, _ = accounts.start("login", "/app")
    with pytest.raises(AuthError):
        accounts.callback(state, "bad")


def test_logout_and_unknown_tokens(accounts):
    token = login(accounts)["token"]
    accounts.logout(token)
    assert accounts.user_for(token) == (None, False)
    assert accounts.user_for("x" * 200) == (None, False)


def test_session_slides_after_an_hour_idle(accounts):
    token = login(accounts)["token"]
    with accounts.pool.connection() as conn:
        conn.execute("UPDATE auth_sessions SET last_seen_at = now() - interval '2 hours', "
                     "expires_at = now() + interval '1 day'")
    _, refreshed = accounts.user_for(token)
    assert refreshed
    with accounts.pool.connection() as conn:
        left = conn.execute("SELECT expires_at - now() AS left FROM auth_sessions").fetchone()["left"]
    assert left.days >= 29


def test_consent_records_version_and_time(accounts):
    uid = accounts.user_for(login(accounts)["token"])[0]["id"]
    with pytest.raises(ValueError):
        accounts.consent(uid, "old")
    me = accounts.consent(uid, TERMS_VERSION)
    assert not me["needs_consent"] and me["consents"]["terms"]["version"] == TERMS_VERSION


def test_profile_fields_are_optional_and_validated(accounts):
    uid = accounts.user_for(login(accounts)["token"])[0]["id"]
    me = accounts.update(uid, {"display_name": " Lan ", "home_city": "Hồ Chí Minh", "usual_mobility": "motorbike",
                               "usual_companions": "partner"})
    assert (me["name"], me["home_city"], me["usual_mobility"], me["usual_companions"]) == \
        ("Lan", "Hồ Chí Minh", "motorbike", "partner")
    assert accounts.update(uid, {"home_city": ""})["home_city"] is None
    for bad in ({"usual_mobility": "rocket"}, {"role": "admin"}, {}, {"home_city": 5}):
        with pytest.raises(ValueError):
            accounts.update(uid, bad)


def _image(fmt, size=(640, 400)):
    buf = io.BytesIO()
    Image.new("RGB", size, (200, 120, 80)).save(buf, fmt)
    return buf.getvalue()


def test_avatar_is_reencoded_square_webp(accounts):
    uid = accounts.user_for(login(accounts)["token"])[0]["id"]
    me = accounts.set_avatar(uid, _image("PNG"))
    key = me["avatar"].rsplit("/", 1)[1]
    with Image.open(accounts.avatar_path(key)) as img:
        assert img.format == "WEBP" and img.size == (256, 256)
    second = accounts.set_avatar(uid, _image("JPEG")).get("avatar").rsplit("/", 1)[1]
    with pytest.raises(KeyError):
        accounts.avatar_path(key)  # the replaced file is gone
    assert accounts.avatar_path(second).exists()
    for bad in (b"not an image", _image("GIF"), b""):
        with pytest.raises(ValueError):
            accounts.set_avatar(uid, bad)
    with pytest.raises(KeyError):
        accounts.avatar_path("../../etc/passwd")


def test_calendar_grant_stores_encrypted_token_for_the_same_google_account(accounts):
    uid = accounts.user_for(login(accounts, "g-7")["token"])[0]["id"]
    state, url = accounts.start("calendar", "/app/plan", uid)
    assert urllib.parse.quote(CALENDAR_SCOPE, safe="") in url
    accounts.callback(state, "g-7+calendar")
    assert accounts.calendar_token(uid) == "refresh-g-7"
    with accounts.pool.connection() as conn:
        stored = bytes(conn.execute("SELECT refresh_token_enc FROM calendar_links").fetchone()["refresh_token_enc"])
    assert b"refresh-g-7" not in stored
    state, _ = accounts.start("calendar", "/app/plan", uid)
    with pytest.raises(AuthError):
        accounts.callback(state, "g-other+calendar")
    accounts.unlink_calendar(uid)
    assert accounts.calendar_token(uid) is None and accounts.google.revoked == ["refresh-g-7"]


def test_delete_account_removes_personal_data_and_keeps_anonymous_rows(accounts):
    token = login(accounts, "g-9")["token"]
    uid = accounts.user_for(token)[0]["id"]
    accounts.set_avatar(uid, _image("PNG"))
    with accounts.pool.connection() as conn:
        conn.execute("INSERT INTO journeys (id, user_id, stage, revision, envelope) VALUES ('abc', %s, 'trip', 0, '{}')",
                     (uid,))
        conn.execute("INSERT INTO events (user_id, source, name) VALUES (%s, 'server', 'trip.turn')", (uid,))
    accounts.delete(uid)
    assert accounts.user_for(token) == (None, False)
    with accounts.pool.connection() as conn:
        user = conn.execute("SELECT * FROM users WHERE id = %s", (uid,)).fetchone()
        assert user["deleted_at"] and user["email"] is None and user["google_sub"] is None
        assert conn.execute("SELECT user_id FROM journeys").fetchone()["user_id"] is None
        assert conn.execute("SELECT count(*) AS n FROM events WHERE user_id IS NULL").fetchone()["n"] == 1
        assert conn.execute("SELECT count(*) AS n FROM profiles").fetchone()["n"] == 0
    assert not any((accounts.avatars).glob("*.webp"))
    fresh = accounts.user_for(login(accounts, "g-9")["token"])[0]["id"]
    assert fresh != uid  # signing in again starts a new account


def test_saved_places_belong_to_the_account_newest_first_and_merge_once(accounts):
    a = accounts.user_for(login(accounts, "g-a")["token"])[0]["id"]
    b = accounts.user_for(login(accounts, "g-b")["token"])[0]["id"]
    assert accounts.saved(a) == []
    p1, p2, p3 = "0x1:0xa", "0x2:0xb", "0x3:0xc"
    assert accounts.save_places(a, [p1]) == [p1]
    assert accounts.save_places(a, [p2]) == [p2, p1]  # a new heart is the newest
    assert accounts.save_places(a, [p3, p1]) == [p3, p2, p1]  # a browser's local list merged: p1 kept once
    assert accounts.saved(b) == []  # another account sees nothing
    assert accounts.unsave_place(a, p2) == [p3, p1]
    assert accounts.unsave_place(a, "0x9:0xz") == [p3, p1]  # not saved: nothing to do
    for bad in ([], ["../x"], [1], "0x1:0xa", ["x" * 200]):
        with pytest.raises(ValueError):
            accounts.save_places(a, bad)
    with pytest.raises(ValueError):
        accounts.unsave_place(a, "a b")
    accounts.delete(a)
    assert accounts.saved(a) == []  # personal: goes with the account


# --- guests (docs/ACCOUNTS.md §Khách) -------------------------------------------------------------------------------

def test_guest_is_a_role_with_no_identity_and_a_one_day_session(accounts):
    token = accounts.guest("agent")
    user, refreshed = accounts.user_for(token)
    assert user["role"] == "guest" and not refreshed
    me = accounts.me(user["id"])
    assert me["role"] == "guest" and me["email"] is None and me["needs_consent"] is False
    with accounts.pool.connection() as conn:
        left = conn.execute("SELECT extract(epoch FROM expires_at - now()) AS s FROM auth_sessions").fetchone()["s"]
        assert 0 < left <= 86400


def test_guest_session_does_not_slide(accounts):
    token = accounts.guest()
    with accounts.pool.connection() as conn:
        conn.execute("UPDATE auth_sessions SET last_seen_at = now() - interval '2 hours'")
    assert accounts.user_for(token)[1] is False
    with accounts.pool.connection() as conn:
        left = conn.execute("SELECT extract(epoch FROM expires_at - now()) AS s FROM auth_sessions").fetchone()["s"]
        assert left <= 86400


def test_each_guest_is_its_own_user(accounts):
    a, b = accounts.user_for(accounts.guest())[0], accounts.user_for(accounts.guest())[0]
    assert a["id"] != b["id"]


def test_remembering_choices_is_its_own_consent_and_can_be_withdrawn(accounts):
    uid = accounts.user_for(login(accounts)["token"])[0]["id"]
    assert accounts.me(uid)["consents"].get("patterns") is None
    assert accounts.set_patterns(uid, True)["consents"]["patterns"] is True
    assert accounts.set_patterns(uid, False)["consents"]["patterns"] is False
    with pytest.raises(ValueError):
        accounts.set_patterns(uid, "yes")
