from plan_fixtures import CFG, decision, rec

from planning.places import build_places
from planning.traits import exposure, kind_group, preference


def place(r):
    (p,), _ = build_places(decision([r["id"]]), {r["id"]: r}, CFG)
    return p


def test_weather_exposed_decides_exposure_and_setting_fills_in_when_it_is_missing():
    assert exposure(place(rec("a", 1, 1, features={"weather_exposed": "present"}))) == "exposed"
    shelter = rec("b", 1, 1, features={"weather_exposed": "sheltered", "setting": "outdoor"})
    assert exposure(place(shelter)) == "sheltered"
    assert exposure(place(rec("c", 1, 1, features={"setting": "outdoor"}))) == "exposed"
    assert exposure(place(rec("d", 1, 1, features={"setting": "indoor"}))) == "sheltered"


def test_a_place_with_no_weather_evidence_is_not_guessed():
    assert exposure(place(rec("a", 1, 1))) is None
    assert exposure(place(rec("b", 1, 1, features={"setting": "both"}))) is None


def test_preference_adds_the_positive_weights_the_place_matches():
    p = place(rec("a", 1, 1, features={"scenic_view": "present", "photo_spot": "present"}))
    ws = [{"feature": "scenic_view", "value": "present", "context": None, "weight": 1.0},
          {"feature": "photo_spot", "value": "present", "context": None, "weight": 0.5},
          {"feature": "nature", "value": "present", "context": None, "weight": 0.8},          # no evidence: 0
          {"feature": "photo_spot", "value": "present", "context": None, "weight": -1.0}]     # avoidance is not a want
    assert preference(p, ws) == 1.5
    assert preference(p, []) == 0.0


def test_kind_group_is_the_category_group():
    assert kind_group(place(rec("a", 1, 1, group="cafe"))) == "cafe"
