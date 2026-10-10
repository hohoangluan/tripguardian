"""Editing a confirmed plan (docs/plans/OPEN_TASKS.md P-4): the trip keeps running on the confirmed plan until a
new one is confirmed, so Đang đi does not break while the user edits Lịch trình or goes back to Chọn nơi."""

from test_companion_routes import confirmed
from test_dispatch import run


def test_an_edit_after_confirm_keeps_the_confirmed_plan_for_today_until_the_next_confirm():
    h, v = confirmed()
    plan = v["outputs"]["planning"]
    v = run(h, v, "act", "edit-after-confirm", {"type": "pick_variant", "id": "v2"})
    assert v["outputs"]["planning"] == plan                                   # still the confirmed plan
    assert h.today(v["id"]) == {"plan_value": plan["value"], "day": None}     # Today still answers
    assert h.companion_act(v["id"], "checkin", {"place_id": "p"}) == {"ok": True}
    v = run(h, v, "back", "more-places")
    assert v["outputs"]["planning"] == plan and h.today(v["id"])["plan_value"] == plan["value"]
