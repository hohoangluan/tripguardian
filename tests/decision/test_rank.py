from types import SimpleNamespace

from fixtures import feat, love, si, srec

from decision.model import Cand
from decision.fit import crowd_evidence
from decision.rank import STRONG_N, conf, fit_level, preference, score, strength, wants
from decision.settings import default

CFG = default()


def prof(**kw):
    return SimpleNamespace(**{"soft": [], "visited": [], "price_sensitivity": 0.0, "crowd_tolerance": None, **kw})


def test_conf_scales_with_authors_on_a_log_scale_agreement_and_status():
    assert conf(feat("present", n=STRONG_N)) == 1.0 and conf(feat("present", n=300)) == 1.0
    assert 0.35 < conf(feat("present", n=3)) < 0.45 < conf(feat("present", n=10)) < 1.0
    conflict = feat("present", n=STRONG_N, status="UNCERTAIN", agreement=0.8)
    conflict["reason"] = "conflict"
    assert conf(conflict) == 0.4
    # an undisputed value whose extractor precision is only unmeasured: many authors settle it
    assert conf(feat("present", n=STRONG_N, status="UNCERTAIN")) == 1.0
    assert conf(feat("present", n=1, status="UNCERTAIN")) < strength(1)


def test_an_experience_few_authors_mention_is_not_what_the_place_is_about():
    assert conf(feat("present", n=STRONG_N, rate=0.003), experience=True) == 0.1
    assert conf(feat("present", n=STRONG_N, rate=0.003)) == 1.0  # not an experience: the share does not matter


def test_strong_evidence_outranks_a_few_mentions():
    """Bug D-3: "Săn mây, 3 người nhắc" (3 of 618 authors) ranked above "Săn mây, 83 người nhắc"."""
    s = si(soft_weights=[love("cloud_hunting"), love("scenic_view")])
    weak = srec("WEAK", features={"cloud_hunting": feat("present", n=3, rate=0.005), "scenic_view": feat("present", n=72)})
    strong = srec("STRONG", features={"cloud_hunting": feat("present", n=83, rate=0.158),
                                      "scenic_view": feat("present", n=89, status="UNCERTAIN")})
    (pw, uw, _), (ps, us, _) = (preference(r, wants(s, prof())) for r in (weak, strong))
    assert ps > pw + 0.3 and us == uw == 0.0


def test_preference_matches_context_and_counts_missing_wanted_features():
    s = si(soft_weights=[love("crowd", "low", context={"time_of_day": "morning"}), love("scenic_view")])
    rec = srec("A", features={"crowd": feat("high", n=STRONG_N,
                                            by_context={"time_of_day=morning": {"low": 3, "high": 1}})})
    pref, unc, matches = preference(rec, wants(s, prof()))
    assert pref == 0.5 and unc == 0.5 and matches[0][:2] == ("crowd", "low")


def test_avoiding_crowds_lowers_a_place_by_how_strongly_authors_found_it_crowded():
    """Bug D-2: crowd_tolerance=avoid barely moved a place 38 authors called crowded."""
    busy = srec("BUSY", features={"crowd": feat("high", n=38, dist={"high": 33, "low": 3, "medium": 2})})
    some = srec("SOME", features={"crowd": feat("low", n=15, status="UNCERTAIN", dist={"low": 8, "high": 6, "medium": 1})})
    calm = srec("CALM", features={"crowd": feat("low", n=20)})
    queue = srec("QUEUE", features={"wait_time": feat("long", n=25)})
    assert crowd_evidence(busy)[1] and crowd_evidence(queue)[1] and not crowd_evidence(some)[1]
    assert crowd_evidence(calm) == (0.0, False)
    cands = [Cand(r, "experience") for r in (busy, some, calm, queue)]
    for c in cands:
        c.fit = 1.0
        c.crowd, c.crowd_warn = crowd_evidence(c.rec)
    score(cands, si(pace={"crowd_tolerance": "avoid"}), prof(), CFG)
    by = {c.id: c.score for c in cands}
    assert by["CALM"] > by["SOME"] > by["BUSY"] and by["CALM"] - by["BUSY"] > 0.7 and by["QUEUE"] < by["SOME"]
    score(cands, si(), prof(), CFG)  # crowds are fine for this trip: no penalty
    assert len({c.parts["crowd"] for c in cands}) == 1


def test_liked_group_counts_in_the_score():
    cafe, hill = Cand(srec("CAFE"), "experience"), Cand(srec("HILL", group="nature"), "experience")
    cafe.fit = hill.fit = 1.0
    score([cafe, hill], si(liked_groups=["chill"]), prof(), CFG)
    assert cafe.parts["like"] == 1.0 and hill.parts["like"] == 0.0 and cafe.score > hill.score


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


def _stars(cands, s, **kw):
    for c in cands:
        c.fit = kw.get("fit", 1.0)
    score(cands, s, prof(), CFG)


def test_stars_are_absolute_to_the_trips_ceiling_not_the_list():
    s = si(soft_weights=[love("scenic_view")], liked_groups=["chill"])
    perfect = srec("P", features={"scenic_view": feat("present", n=STRONG_N)})
    alone, crowd = Cand(perfect, "experience"), [Cand(perfect, "experience"), Cand(srec("Q", group="nature"), "experience")]
    _stars([alone], s)
    _stars(crowd, s)
    # ctx 1 + pref 2 + like 0.5 is the whole ceiling: a perfect match is 5 stars, with or without better neighbours
    assert alone.stars == crowd[0].stars == 5.0
    assert crowd[1].stars < 5.0


def test_stars_keep_their_fraction_and_never_go_below_zero():
    s = si(soft_weights=[love("scenic_view")])
    mid = Cand(srec("M", features={"scenic_view": feat("present", n=STRONG_N)}), "experience")
    bad = Cand(srec("B", price={"min_vnd": 300000, "max_vnd": 300000}), "experience")
    mid.fit = 0.5
    bad.fit = 0.0
    score([mid, bad], s, prof(price_sensitivity=1.0, crowd_tolerance="avoid"), CFG)
    assert 0 < mid.stars < 5 and mid.stars * 2 != int(mid.stars * 2)  # not snapped to a half step
    assert bad.score < 0 and bad.stars == 0.0


def test_stars_are_unknown_when_the_trip_names_no_taste():
    c = Cand(srec("A"), "experience")
    _stars([c], si())
    assert c.stars is None


def test_fit_level_names_the_star_band():
    assert [fit_level(x, CFG) for x in (5.0, 4.5, 3.9, 2.0, 0.5)] == ["Rất hợp", "Rất hợp", "Hợp", "Khá hợp", "Tạm được"]
    assert fit_level(None, CFG) is None
