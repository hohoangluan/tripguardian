"""Friends, direct messages and presence in Postgres (docs/ACCOUNTS.md §Bạn bè).

A friendship starts as a request to someone found by nickname and becomes mutual when they accept. Only friends see
each other's online state and exchange messages; a message may carry one trip of the sender (the harness checks
ownership and makes the recipient's copy). Guests have no nickname, so they can neither be found nor send a request.
"""

import time

ONLINE_S = 180  # seen this recently = online
TOUCH_S = 60  # last_active_at is written at most this often
BODY_MAX = 2000
THREAD_MAX = 200
TYPING_S = 5  # a typing signal older than this is gone
SEARCH_MAX = 8

_CARD = ("u.id, u.nickname, u.display_name, u.bio, u.avatar_key, u.picture_url, "
         f"(u.last_active_at > now() - interval '{ONLINE_S} seconds') AS online")


def _card(row: dict) -> dict:
    return {"id": row["id"].hex, "nickname": row["nickname"], "name": row["display_name"] or row["nickname"] or "",
            "bio": row["bio"] or "", "online": bool(row["online"]),
            "avatar": f"/api/harness/avatars/{row['avatar_key']}" if row["avatar_key"] else row["picture_url"]}


def _uid(value) -> str:
    if not isinstance(value, str) or len(value) != 32 or any(c not in "0123456789abcdef" for c in value):
        raise KeyError("no such user")
    return value


class Social:
    def __init__(self, pool):
        self.pool = pool
        self._typing: dict[tuple[str, str], float] = {}  # (who types, to whom) -> when; in memory, it only lives seconds

    def touch(self, user_id: str) -> None:
        """Marks the account as active now (online for friends); cheap when it was marked within a minute."""
        with self.pool.connection() as conn:
            conn.execute("UPDATE users SET last_active_at = now() WHERE id = %s AND (last_active_at IS NULL "
                         f"OR last_active_at < now() - interval '{TOUCH_S} seconds')", (user_id,))

    # --- people -------------------------------------------------------------------------------------------------

    def search(self, user_id: str, q: str) -> list[dict]:
        """Members whose nickname starts with q (at least 2 characters), each with how they relate to the caller."""
        q = (q or "").strip().lstrip("@").lower()
        if len(q) < 2 or len(q) > 24:
            return []
        pattern = q.replace("\\", "\\\\").replace("%", "\\%").replace("_", "\\_") + "%"
        with self.pool.connection() as conn:
            rows = conn.execute(
                f"SELECT {_CARD}, f.status, f.requester FROM users u LEFT JOIN friendships f ON "
                "(f.requester = u.id AND f.addressee = %s) OR (f.addressee = u.id AND f.requester = %s) "
                "WHERE u.nickname LIKE %s AND u.id <> %s AND u.kind = 'user' AND u.status = 'active' "
                "AND u.deleted_at IS NULL ORDER BY u.nickname LIMIT %s",
                (user_id, user_id, pattern, user_id, SEARCH_MAX)).fetchall()
        out = []
        for r in rows:
            relation = ("none" if r["status"] is None else "friend" if r["status"] == "accepted"
                        else "received" if r["requester"] == r["id"] else "sent")
            card = _card(r)
            if relation != "friend":
                card["online"] = False  # presence is for friends only
            out.append(card | {"relation": relation})
        return out

    def friends(self, user_id: str) -> dict:
        """Friends (online first, then by name) with unread counts, and the open requests both ways."""
        self.touch(user_id)
        with self.pool.connection() as conn:
            rows = conn.execute(
                f"SELECT {_CARD}, f.status, f.requester = %s AS mine, "
                "(SELECT count(*) FROM messages m WHERE m.sender = u.id AND m.recipient = %s AND m.read_at IS NULL) "
                "AS unread FROM friendships f JOIN users u ON u.id = CASE WHEN f.requester = %s THEN f.addressee "
                "ELSE f.requester END WHERE (f.requester = %s OR f.addressee = %s) AND u.status = 'active' "
                "AND u.deleted_at IS NULL ORDER BY online DESC, lower(coalesce(u.display_name, u.nickname))",
                (user_id, user_id, user_id, user_id, user_id)).fetchall()
        out = {"friends": [], "incoming": [], "outgoing": []}
        for r in rows:
            card = _card(r)
            if r["status"] == "accepted":
                out["friends"].append(card | {"unread": r["unread"]})
            else:
                card["online"] = False
                out["outgoing" if r["mine"] else "incoming"].append(card)
        return out

    def request(self, user_id: str, to: str) -> dict:
        """Asks `to` to be friends; a request they already sent the caller is accepted instead."""
        to = _uid(to)
        if to == user_id:
            raise ValueError("cannot befriend yourself")
        with self.pool.connection() as conn:
            me = conn.execute("SELECT nickname FROM users WHERE id = %s", (user_id,)).fetchone()
            if not me or not me["nickname"]:
                raise ValueError("choose a nickname first")
            if not conn.execute("SELECT 1 FROM users WHERE id = %s AND kind = 'user' AND status = 'active' "
                                "AND deleted_at IS NULL AND nickname IS NOT NULL", (to,)).fetchone():
                raise KeyError("no such user")
            back = conn.execute("UPDATE friendships SET status = 'accepted', accepted_at = now() WHERE requester = %s "
                                "AND addressee = %s AND status = 'pending' RETURNING 1", (to, user_id)).fetchone()
            if not back:
                conn.execute("INSERT INTO friendships (requester, addressee) SELECT %s, %s WHERE NOT EXISTS "
                             "(SELECT 1 FROM friendships WHERE requester = %s AND addressee = %s)",
                             (user_id, to, to, user_id))
        return self.friends(user_id)

    def accept(self, user_id: str, other: str) -> dict:
        with self.pool.connection() as conn:
            done = conn.execute("UPDATE friendships SET status = 'accepted', accepted_at = now() WHERE requester = %s "
                                "AND addressee = %s AND status = 'pending' RETURNING 1", (_uid(other), user_id)).fetchone()
        if not done:
            raise KeyError("no such request")
        return self.friends(user_id)

    def remove(self, user_id: str, other: str) -> dict:
        """Declines, cancels or ends a friendship; the messages stay for both until either account goes."""
        other = _uid(other)
        with self.pool.connection() as conn:
            conn.execute("DELETE FROM friendships WHERE (requester = %s AND addressee = %s) "
                         "OR (requester = %s AND addressee = %s)", (user_id, other, other, user_id))
        return self.friends(user_id)

    def _friends(self, conn, a: str, b: str) -> bool:
        return conn.execute("SELECT 1 FROM friendships WHERE status = 'accepted' AND ((requester = %s AND addressee = %s) "
                            "OR (requester = %s AND addressee = %s))", (a, b, b, a)).fetchone() is not None

    # --- messages -----------------------------------------------------------------------------------------------

    def thread(self, user_id: str, other: str, after: int = 0) -> list[dict]:
        """Messages with one friend, oldest first (the last THREAD_MAX, or those after id `after`); the ones the
        caller received are marked read."""
        other = _uid(other)
        with self.pool.connection() as conn:
            if not self._friends(conn, user_id, other):
                raise KeyError("not a friend")
            rows = conn.execute(
                "SELECT * FROM (SELECT id, sender, body, journey_id, imported_journey_id, sent_at, read_at FROM messages "
                "WHERE ((sender = %s AND recipient = %s) OR (sender = %s AND recipient = %s)) AND id > %s "
                "ORDER BY id DESC LIMIT %s) t ORDER BY id",
                (user_id, other, other, user_id, after, THREAD_MAX)).fetchall()
            conn.execute("UPDATE messages SET read_at = now() WHERE sender = %s AND recipient = %s AND read_at IS NULL",
                         (other, user_id))
        return [{"id": r["id"], "mine": r["sender"].hex == user_id, "body": r["body"], "journey": r["journey_id"],
                 "imported": r["imported_journey_id"], "at": r["sent_at"].isoformat(timespec="seconds"),
                 "read": r["read_at"] is not None} for r in rows]

    def send(self, user_id: str, other: str, body: str, journey_id: str | None = None) -> dict:
        """One message to a friend; journey_id must already be checked as the sender's own trip."""
        other = _uid(other)
        body = (body or "").strip() if isinstance(body, str) else None
        if body is None or len(body) > BODY_MAX:
            raise ValueError(f"message must be text of at most {BODY_MAX} characters")
        if not body and not journey_id:
            raise ValueError("empty message")
        with self.pool.connection() as conn:
            if not self._friends(conn, user_id, other):
                raise KeyError("not a friend")
            row = conn.execute("INSERT INTO messages (sender, recipient, body, journey_id) VALUES (%s, %s, %s, %s) "
                               "RETURNING id, sent_at", (user_id, other, body, journey_id)).fetchone()
        return {"id": row["id"], "mine": True, "body": body, "journey": journey_id, "imported": None,
                "at": row["sent_at"].isoformat(timespec="seconds"), "read": False}

    def typing(self, user_id: str, other: str, on: bool = True) -> None:
        """The caller is typing to a friend (or stopped): the friend's open chat shows "..." for a few seconds."""
        other = _uid(other)
        with self.pool.connection() as conn:
            if not self._friends(conn, user_id, other):
                raise KeyError("not a friend")
        if on:
            self._typing[(user_id, other)] = time.monotonic()
        else:
            self._typing.pop((user_id, other), None)

    def is_typing(self, user_id: str, other: str) -> bool:
        """Whether `other` is typing to the caller right now. Only friends can have set it, so no lookup."""
        at = self._typing.get((_uid(other), user_id))
        return at is not None and time.monotonic() - at < TYPING_S

    def shared(self, user_id: str, message_id: int) -> tuple[str, str, str | None]:
        """(sender, journey_id, already imported journey) of a trip sent to the caller; KeyError otherwise."""
        with self.pool.connection() as conn:
            row = conn.execute("SELECT sender, journey_id, imported_journey_id FROM messages WHERE id = %s "
                               "AND recipient = %s AND journey_id IS NOT NULL", (message_id, user_id)).fetchone()
        if not row:
            raise KeyError("no such shared trip")
        return row["sender"].hex, row["journey_id"], row["imported_journey_id"]

    def imported(self, message_id: int, journey_id: str) -> None:
        with self.pool.connection() as conn:
            conn.execute("UPDATE messages SET imported_journey_id = %s WHERE id = %s", (journey_id, message_id))
