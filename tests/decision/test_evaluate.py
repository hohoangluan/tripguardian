from fixtures import feat, srec

from decision import evaluate as ev


def test_evaluate_counts_violations_unknowns_and_fill(monkeypatch):
    monkeypatch.setattr(ev, "trips", lambda: (2, [
        {"id": "flat", "role": "experience", "hard": {"steep_or_stairs": "present"}, "soft": {"scenic_view": 1.0}}]))
    safe = srec("S", group="nature", features={"steep_or_stairs": "absent", "scenic_view": "present"})
    disputed = srec("D", group="nature", features={"steep_or_stairs": feat("absent", dist={"absent": 3, "present": 1})})
    steep = srec("X", group="nature", features={"steep_or_stairs": "present"})
    meal = srec("M", features={"steep_or_stairs": "absent"}, usable=("meal",))
    res = ev.evaluate([safe, disputed, steep, meal])
    row = res["trips"][0]
    assert row["shortlist"] == ["S"] and (row["unverified"], row["excluded"]) == (1, 1)
    assert res["summary"]["violations"] == 0 and res["summary"]["unknown_in_main"] == 0
    assert res["summary"]["unfilled_trips"] == ["flat"] and res["summary"]["ms_max"] >= 0
    assert ev.violates(disputed, "steep_or_stairs", "present")


def test_search_input_from_hidden_trip():
    si = ev.search_input({"id": "x", "role": "meal", "hard": {"kids": "unsuitable"}, "soft": {"noise": 1.0}}, 7)
    assert si.hard_filters[0].feature == "kids" and si.soft_weights[0].value == "quiet"


def test_uncertain_pass_with_warning_is_counted_apart_from_unknown(monkeypatch):
    monkeypatch.setattr(ev, "trips", lambda: (1, [
        {"id": "quiet", "role": "experience", "hard": {"noise": "loud"}, "soft": {}}]))
    shaky = srec("U", group="nature", features={"noise": feat("quiet", status="UNCERTAIN")})
    row = ev.evaluate([shaky])["trips"][0]
    res = ev.evaluate([shaky])
    assert row["shortlist"] == ["U"] and row["unknown_in_main"] == [] and row["uncertain_in_main"] == ["U"]
    assert res["summary"]["unknown_in_main"] == 0 and res["summary"]["uncertain_in_main"] == 1
