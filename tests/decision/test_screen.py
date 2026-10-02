from fixtures import feat, hard, si, srec

from decision.model import Cand
from decision.screen import closed_all_days, hard_result, screen
from decision.settings import default
from decision.trip_days import trip_days

CFG = default()


def h(feature, value, op="ne", policy="exclude"):
    return si(hard_filters=[hard(feature, value, op, policy)]).hard_filters[0]


def test_ne_uses_fail_closed_check():
    assert hard_result(srec("A", features={"steep_or_stairs": "absent"}), h("steep_or_stairs", "present"))[0] == "pass"
    assert hard_result(srec("A", features={"steep_or_stairs": "present"}), h("steep_or_stairs", "present"))[0] == "fail"
    assert hard_result(srec("A"), h("steep_or_stairs", "present"))[0] == "unknown"


def test_eq_needs_a_firm_undisputed_value():
    ok = srec("A", features={"setting": "indoor"})
    disputed = srec("B", features={"setting": feat("indoor", dist={"indoor": 3, "outdoor": 1})})
    assert hard_result(ok, h("setting", "indoor", "eq"))[0] == "pass"
    assert hard_result(disputed, h("setting", "indoor", "eq"))[0] == "unknown"
    assert hard_result(srec("C", features={"setting": "outdoor"}), h("setting", "indoor", "eq"))[0] == "fail"


def test_uncertain_value_passes_with_warning_only_outside_safety_groups():
    noise = srec("A", features={"noise": feat("quiet", status="UNCERTAIN")})
    steep = srec("B", features={"steep_or_stairs": feat("absent", status="UNCERTAIN")})
    assert hard_result(noise, h("noise", "loud")) == ("pass", "uncertain_value")
    assert hard_result(steep, h("steep_or_stairs", "present")) == ("unknown", None)


def test_closed_every_trip_day_is_physical_and_needs_known_weekdays():
    mon_tue_closed = {"wed": [["08:00", "17:00"]]}
    days = trip_days(si(context={"days": 2}).context, CFG)  # Monday, Tuesday
    assert closed_all_days(srec("A", hours=mon_tue_closed), days)
    no_dates = trip_days(si(context={"start_date": None, "month": 12}).context, CFG)
    assert not closed_all_days(srec("A", hours=mon_tue_closed), no_dates)
    assert not closed_all_days(srec("A", hours=mon_tue_closed, hours_status="OUTDATED"), days)


def test_screen_statuses_relax_and_warnings():
    s = si(hard_filters=[hard("steep_or_stairs", "present"), hard("noise", "loud")])
    days = trip_days(s.context, CFG)
    good = Cand(srec("G", features={"steep_or_stairs": "absent", "noise": feat("quiet", status="UNCERTAIN")}), "experience")
    bad = Cand(srec("X", features={"steep_or_stairs": "present", "noise": "quiet"}), "experience")
    unk = Cand(srec("U", features={"noise": "quiet"}, hours=None), "experience")
    for c in (good, bad, unk):
        screen(c, s, days, set())
    assert (good.status, bad.status, unk.status) == ("main", "excluded", "unverified")
    assert "uncertain_value:noise" in good.warnings and "hours_unknown" in unk.warnings
    screen(bad, s, days, {("X", "steep_or_stairs")})
    assert bad.status == "main" and [c["feature"] for c in bad.checks if c["kind"] == "hard"] == ["noise"]
