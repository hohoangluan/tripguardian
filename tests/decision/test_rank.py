from types import SimpleNamespace

from fixtures import feat, love, si, srec

from decision.model import Cand
from decision.rank import conf, preference, score, wants
from decision.settings import default

CFG = default()


def prof(**kw):
    return SimpleNamespace(**{"soft": [], "visited": [], "price_sensitivity": 0.0, **kw})


def test_conf_scales_with_authors_agreement_and_status():
    assert conf(feat("present", n=3)) == 1.0
    assert conf(feat("present", n=1)) == 1 / 3
    assert conf(feat("present", n=3, status="UNCERTAIN", agreement=0.8)) == 0.4


def test_preference_matches_context_and_counts_missing_wanted_features():
    s = si(soft_weights=[love("crowd", "low", context={"time_of_day": "morning"}), love("scenic_view")])
    rec = srec("A", features={"crowd": feat("high", by_context={"time_of_day=morning": {"low": 3, "high": 1}})})
    pref, unc, matches = preference(rec, wants(s, prof()))
    assert pref == 0.5 and unc == 0.5 and matches[0][:2] == ("crowd", "low")


def test_avoid_weight_is_negative_and_profile_soft_counts():
    s = si(soft_weights=[love("live_music", weight=-1)])
    p = prof(soft=[SimpleNamespace(feature="scenic_view", value="present", weight=1)])
    pref, _, _ = preference(srec("A", features={"live_music": "present", "scenic_view": "present"}), wants(s, p))
    assert pref == 0.0


def test_score_parts_novelty_experience_price():
    a = Cand(srec("A", voices=100, price={"min_vnd": 300000, "max_vnd": 300000}), "experience")
    b = Cand(srec("B", voices=10), "experience")
    a.fit = b.fit = 1.0
    s = si(context={"experience": "first"}, novelty={"level": "new", "visited": ["A"]})
    score([a, b], s, prof(price_sensitivity=1.0), CFG)
    assert a.parts["nov"] == -1.0 and b.parts["nov"] == 0.0
    assert a.parts["pop"] == 1.0 and b.parts["pop"] == 0.0 and a.parts["exp"] == 1.0
    assert a.parts["price"] == -1.0
    assert a.score == round(sum(CFG.weights[k] * v for k, v in a.parts.items()), 4)
