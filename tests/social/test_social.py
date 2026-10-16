import pytest

from accounts import Library
from social import Social

pytestmark = pytest.mark.pg

A, B, C, G = "a" * 32, "b" * 32, "c" * 32, "d" * 32


@pytest.fixture
def pool(pg_url):
    from psycopg.rows import dict_row
    from psycopg_pool import ConnectionPool
    pool = ConnectionPool(pg_url, min_size=1, max_size=4, kwargs={"row_factory": dict_row}, open=True)
    with pool.connection() as conn:
        conn.execute("INSERT INTO users (id, nickname, display_name) VALUES (%s, 'an.nguyen', 'An'), "
                     "(%s, 'binh', 'Bình'), (%s, NULL, 'Chưa đặt')", (A, B, C))
        conn.execute("INSERT INTO users (id, kind) VALUES (%s, 'guest')", (G,))
    yield pool
    pool.close()


def test_a_request_found_by_nickname_becomes_mutual_when_accepted(pool):
    s = Social(pool)
    assert [u["nickname"] for u in s.search(B, "@an")] == ["an.nguyen"]
    assert s.search(B, "a") == []  # too short
    assert s.search(B, "an")[0]["relation"] == "none"
    out = s.request(B, A)
    assert [u["id"] for u in out["outgoing"]] == [A] and out["friends"] == []
    assert [u["id"] for u in s.friends(A)["incoming"]] == [B]
    assert s.search(A, "bin")[0]["relation"] == "received"
    assert [u["id"] for u in s.accept(A, B)["friends"]] == [B]
    assert s.search(B, "an")[0]["relation"] == "friend"


def test_crossed_requests_accept_each_other_and_remove_ends_it(pool):
    s = Social(pool)
    s.request(A, B)
    assert [u["id"] for u in s.request(B, A)["friends"]] == [A]
    assert s.remove(A, B) == {"friends": [], "incoming": [], "outgoing": []}


def test_no_nickname_no_guest_no_self(pool):
    s = Social(pool)
    with pytest.raises(ValueError):
        s.request(C, A)  # the caller has no nickname: nobody would know who asked
    with pytest.raises(KeyError):
        s.request(A, C)  # cannot be found without a nickname
    with pytest.raises(KeyError):
        s.request(A, G)
    with pytest.raises(ValueError):
        s.request(A, A)
    with pytest.raises(KeyError):
        s.accept(A, B)  # nothing to accept


def test_presence_is_for_friends_only(pool):
    s = Social(pool)
    s.touch(A)
    assert s.search(B, "an")[0]["online"] is False
    s.request(B, A)
    s.accept(A, B)
    assert s.friends(B)["friends"][0]["online"] is True
    with pool.connection() as conn:
        conn.execute("UPDATE users SET last_active_at = now() - interval '10 minutes' WHERE id = %s", (A,))
    assert s.friends(B)["friends"][0]["online"] is False


def test_messages_need_friends_count_unread_and_carry_a_trip(pool):
    s = Social(pool)
    with pytest.raises(KeyError):
        s.send(A, B, "chào")
    s.request(A, B)
    s.accept(B, A)
    s.send(A, B, "chào")
    sent = s.send(A, B, "", "0123456789ab")
    with pytest.raises(ValueError):
        s.send(A, B, "   ")
    with pytest.raises(ValueError):
        s.send(A, B, "x" * 2001)
    assert s.friends(B)["friends"][0]["unread"] == 2
    thread = s.thread(B, A)
    assert [(m["mine"], m["body"], m["journey"]) for m in thread] == [(False, "chào", None), (False, "", "0123456789ab")]
    assert s.friends(B)["friends"][0]["unread"] == 0
    assert s.thread(B, A, after=thread[0]["id"])[0]["id"] == sent["id"]
    assert s.shared(B, sent["id"]) == (A, "0123456789ab", None)
    with pytest.raises(KeyError):
        s.shared(A, sent["id"])  # only the recipient takes it
    s.imported(sent["id"], "ba9876543210")
    assert s.shared(B, sent["id"])[2] == "ba9876543210"


def test_typing_shows_to_the_friend_only_for_a_few_seconds(pool, monkeypatch):
    import social.service as svc
    s = Social(pool)
    with pytest.raises(KeyError):
        s.typing(A, B)  # not friends yet
    s.request(A, B)
    s.accept(B, A)
    assert not s.is_typing(B, A)
    s.typing(A, B)
    assert s.is_typing(B, A) and not s.is_typing(A, B)  # B sees A typing, not the other way round
    s.typing(A, B, on=False)
    assert not s.is_typing(B, A)
    s.typing(A, B)
    later = svc.time.monotonic() + svc.TYPING_S + 1
    monkeypatch.setattr(svc.time, "monotonic", lambda: later)
    assert not s.is_typing(B, A)


def test_library_saves_items_and_reads_recent_opens_from_events(pool):
    lib = Library(pool)
    assert lib.save(A, "place", "0x31:0x2d", True)["saved"][0] | {"at": None} == {"kind": "place", "id": "0x31:0x2d", "at": None}
    lib.save(A, "theme", "cloud", True)
    lib.save(A, "theme", "cloud", True)
    assert [i["id"] for i in lib.read(A)["saved"]] == ["cloud", "0x31:0x2d"]
    assert [i["id"] for i in lib.save(A, "theme", "cloud", False)["saved"]] == ["0x31:0x2d"]
    for bad in (("trip", "x", True), ("theme", "Bad Id", True), ("place", "p", "yes")):
        with pytest.raises(ValueError):
            lib.save(A, *bad)
    with pool.connection() as conn:
        conn.execute("INSERT INTO events (at, user_id, source, name, props) VALUES "
                     "(now() - interval '2 hours', %s, 'client', 'detail_open', '{\"place_id\": \"p1\"}'), "
                     "(now() - interval '1 hour', %s, 'client', 'theme_open', '{\"theme\": \"lake\"}'), "
                     "(now(), %s, 'client', 'detail_open', '{\"place_id\": \"p1\"}'), "
                     "(now(), %s, 'client', 'detail_open', '{\"place_id\": \"other\"}')", (A, A, A, B))
    assert [(i["kind"], i["id"]) for i in lib.read(A)["recent"]] == [("place", "p1"), ("theme", "lake")]
