import pytest

from companion import Calendar, CalendarError, Companion, load_settings
from test_companion import NOW, PLAN, RECORDS

pytestmark = pytest.mark.pg
UID = "a" * 32


class FakeApi:
    """Google Calendar stand-in shared by every token; fail_on names an op that raises once."""
    log, events, calendars, fail_on = [], {}, [], None

    def __init__(self, token):
        assert token == "access-1"

    def create_calendar(self, summary):
        FakeApi.calendars.append(summary)
        return "cal-1"

    def delete_calendar(self, cid):
        FakeApi.log.append(("delete_calendar", cid))

    def insert(self, cid, event):
        if FakeApi.fail_on == "insert" and len([x for x in FakeApi.log if x[0] == "insert"]) == 1:
            raise CalendarError("calendar 500")
        eid = f"ev{len(FakeApi.events) + 1}"
        FakeApi.events[eid] = event
        FakeApi.log.append(("insert", event["summary"]))
        return {"id": eid, "etag": "e"}

    def patch(self, cid, eid, event):
        FakeApi.events[eid] = event
        FakeApi.log.append(("patch", event["summary"]))
        return {"id": eid, "etag": "e2"}

    def delete(self, cid, eid):
        FakeApi.events.pop(eid, None)
        FakeApi.log.append(("delete", eid))


class FakeGoogle:
    def access_token(self, refresh):
        return "access-1"


class FakeAccounts:
    google = FakeGoogle()
    linked = True
    unlinked = False

    def calendar_token(self, uid):
        return "refresh-1" if self.linked else None

    def unlink_calendar(self, uid):
        self.unlinked = True


@pytest.fixture
def cal(pg_url):
    from psycopg.rows import dict_row
    from psycopg_pool import ConnectionPool
    FakeApi.log, FakeApi.events, FakeApi.calendars, FakeApi.fail_on = [], {}, [], None
    with ConnectionPool(pg_url, min_size=1, max_size=4, kwargs={"row_factory": dict_row}, open=True) as pool:
        with pool.connection() as conn:
            conn.execute("INSERT INTO users (id) VALUES (%s)", (UID,))
        comp = Companion(pool, RECORDS, load_settings(), now=lambda: NOW)
        comp.sync("j00000000001", UID, PLAN)
        yield Calendar(pool, FakeAccounts(), comp.records, "https://app.test", FakeApi), comp


def test_first_preview_creates_a_calendar_and_one_event_per_stop_without_reminders(cal):
    c, _ = cal
    p = c.preview("j00000000001", UID, PLAN)
    assert p["state"] == "none" and p["calendar"] == {"create": True, "summary": "TripGuardian · Đà Lạt 12–13/11"}
    assert [ch["op"] for ch in p["changes"]] == ["create"] * 3
    ev = p["changes"][0]["after"]
    assert ev["reminders"] == {"useDefault": False, "overrides": []} and ev["start"]["dateTime"].startswith("2026-11-12T14:00")
    assert "https://app.test/app/today?stop=" in ev["description"]
    out = c.apply("j00000000001", UID, PLAN, p["preview_hash"])
    assert out["applied"] == 3 and out["state"] == "synced" and FakeApi.calendars == [p["calendar"]["summary"]]
    again = c.preview("j00000000001", UID, PLAN)
    assert again["state"] == "synced" and again["changes"] == [] and not again["calendar"]["create"]


def test_an_old_preview_is_refused(cal):
    c, comp = cal
    old = c.preview("j00000000001", UID, PLAN)
    comp.sync("j00000000001", UID, {**PLAN, "itinerary": PLAN["itinerary"][:1]})
    out = c.apply("j00000000001", UID, PLAN, old["preview_hash"])
    assert out["stale"] and out["preview"]["preview_hash"] != old["preview_hash"] and FakeApi.log == []


def test_a_new_plan_drifts_and_the_diff_updates_and_deletes(cal):
    c, comp = cal
    c.apply("j00000000001", UID, PLAN, c.preview("j00000000001", UID, PLAN)["preview_hash"])
    moved = {**PLAN, "itinerary": [{**PLAN["itinerary"][0], "items": [
        {"kind": "visit", "start": "15:00", "end": "16:00", "place_id": "here", "name": "Here"},
        {"kind": "visit", "start": "17:30", "end": "18:30", "place_id": "planned_b", "name": "B"}]},
        {**PLAN["itinerary"][1], "items": []}]}
    comp.sync("j00000000001", UID, moved)
    p = c.preview("j00000000001", UID, moved)
    assert p["state"] == "drifted" and sorted(ch["op"] for ch in p["changes"]) == ["delete", "update"]
    FakeApi.log.clear()
    c.apply("j00000000001", UID, moved, p["preview_hash"])
    assert sorted(x[0] for x in FakeApi.log) == ["delete", "patch"]


def test_a_failure_midway_keeps_what_was_applied_and_reports_the_rest(cal):
    c, _ = cal
    FakeApi.fail_on = "insert"
    p = c.preview("j00000000001", UID, PLAN)
    out = c.apply("j00000000001", UID, PLAN, p["preview_hash"])
    assert out["applied"] == 1 and out["failed"]["error"] == "calendar 500" and len(out["not_done"]) == 2
    assert out["state"] == "drifted"
    FakeApi.fail_on = None
    left = c.preview("j00000000001", UID, PLAN)
    assert [ch["op"] for ch in left["changes"]] == ["create", "create"]  # nothing retried on its own; the user asks again


def test_disconnect_deletes_calendars_only_when_asked(cal):
    c, _ = cal
    c.apply("j00000000001", UID, PLAN, c.preview("j00000000001", UID, PLAN)["preview_hash"])
    assert c.disconnect(UID, delete_calendar=False) == {"disconnected": True, "calendars_deleted": 0}
    assert ("delete_calendar", "cal-1") not in FakeApi.log and c.accounts.unlinked
    c.accounts.linked = True
    c.apply("j00000000001", UID, PLAN, c.preview("j00000000001", UID, PLAN)["preview_hash"])
    assert c.disconnect(UID, delete_calendar=True)["calendars_deleted"] == 1


def test_not_connected_cannot_apply(cal):
    c, _ = cal
    c.accounts.linked = False
    p = c.preview("j00000000001", UID, PLAN)
    assert p["connected"] is False
    with pytest.raises(CalendarError):
        c.apply("j00000000001", UID, PLAN, p["preview_hash"])
