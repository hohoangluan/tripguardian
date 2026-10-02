from plan_fixtures import all_days, day_ctx, decision, flat_travel, rec

from planning.backup import backups
from planning.route import order_day

AT = (11.94, 108.45)
WET = {"weather_exposed": "present"}
DRY = {"weather_exposed": "sheltered"}


def near(pid, step=1, **kw):
    """A record step x ~300 m from AT."""
    return rec(pid, AT[0] + step * 0.002, AT[1] + step * 0.002, **kw)


def pool_of(*ids, for_=None, reason="next_best"):
    return [{"id": i, "name": i, "for": for_, "reason": reason} for i in ids]


def run(day_recs, pool_recs, pool, *, rain=None, hard=(), roles=None, prefs=None, start_node=None, travel=None):
    """Backups of one day holding day_recs, with pool as the Decision's backup_pool."""
    cx = day_ctx(day_recs, rain=rain, roles=roles, prefs=prefs, start_node=start_node,
                 extra_nodes=["h"] if start_node else (), travel=travel)
    r = order_day(sorted(cx.places), cx)
    d = decision([x["id"] for x in day_recs], roles=roles, hard=hard)
    d["backup_pool"] = pool
    return backups([cx], [r], d, {x["id"]: x for x in [*day_recs, *pool_recs]})


def test_an_exposed_place_on_a_rainy_day_gets_a_sheltered_one_of_its_kind_nearby():
    out = run([near("a", 0, features=WET, group="garden")],
              [near("dry", 1, features=DRY, group="garden"), near("wet", 1, features=WET, group="garden"),
               near("unknown", 1, group="garden"), near("other", 1, features=DRY, group="cafe")],
              pool_of("dry", "wet", "unknown", "other"), rain=0.8)["places"]
    assert [(p["place_id"], p["reasons"]) for p in out] == [("a", ["rain"])]
    assert [x["id"] for x in out[0]["alternatives"]] == ["dry"]
    assert out[0]["text"] == "ngoài trời vào ngày dự báo mưa" and out[0]["none_text"] is None


def test_the_same_place_on_a_dry_or_unknown_day_is_not_sensitive():
    for rain in (0.2, None):
        assert run([near("a", 0, features=WET)], [], [], rain=rain)["places"] == []


def test_a_backup_the_decision_kept_for_this_place_comes_before_a_closer_one_of_the_same_kind():
    out = run([near("a", 0, status="UNCERTAIN", group="cafe")],
              [near("close", 1, group="cafe"), near("mine", 3, group="other")],
              pool_of("close") + pool_of("mine", for_="a", reason="same_kind"))["places"]
    assert out[0]["reasons"] == ["hours_uncertain"]
    assert [(x["id"], x["for_this"]) for x in out[0]["alternatives"]] == [("mine", True), ("close", False)]


def test_replacements_that_are_far_shaky_closed_steep_unknown_or_already_confirmed_are_left_out():
    hard = [{"feature": "steep_or_stairs", "op": "ne", "value": "present", "unknown_policy": "exclude"}]
    out = run([near("a", 0, status="OUTDATED", group="g"), near("b", 5, group="g")],
              [near("far", 100, group="g"), near("shaky", 1, group="g", status="UNCERTAIN"),
               near("closed", 1, group="g", hours={**all_days(), "mon": []}),
               near("steep", 1, group="g", features={"steep_or_stairs": "present"}),
               rec("nocoord", None, None, group="g")],
              pool_of("far", "shaky", "closed", "steep", "nocoord", "ghost", "b"), hard=hard)["places"]
    assert [(p["place_id"], p["alternatives"], p["none_text"]) for p in out] == [
        ("a", [], "Không có phương án thay.")]


def test_a_visit_ending_close_to_closing_time_is_sensitive():
    tight = near("a", 0, hours=all_days("08:00", "08:20"), visit=(10, 15, 20))
    assert run([tight], [], [])["places"][0]["reasons"] == ["near_close"]


def test_a_place_far_from_where_the_day_starts_is_sensitive():
    out = run([near("a", 0)], [], [], start_node="h", travel=flat_travel(["h", "a"], 50))["places"]
    assert out[0]["reasons"] == ["far"]


def test_on_a_delay_the_least_wanted_selected_stop_goes_first_never_an_anchor():
    out = run([near("a", 0), near("b", 1), near("c", 2)], [], [], roles={"a": "anchor"}, prefs={"b": 1.0, "c": 0.0})
    assert out["on_delay"] == [{"day": 1, "place_id": "c", "name": "c"}]
    only_fixed = run([near("a", 0), near("b", 1)], [], [], roles={"a": "anchor", "b": "locked"})
    assert only_fixed["on_delay"] == []
