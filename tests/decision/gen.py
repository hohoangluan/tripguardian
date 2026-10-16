"""Seeded random serving records and Decision sessions for the equivalence test: wide on purpose (missing fields,
UNCERTAIN values, conflicts, contexts, overrides, kept places without a role or a record)."""

import random

from fixtures import ALL_DAY, MONDAY, ONT, feat, fit_entry, hard, love, si, srec

from decision.session import Drop, Profile, Session, SoftAdd, State

GROUPS = [("cafe", ("experience", "meal", "backup")), ("restaurant", ("meal",)), ("nature", ("experience",)),
          ("attraction", ("experience", "backup")), ("bar", ("experience",)), ("other", ()), ("rental", ()),
          ("stay", ())]  # lodging: config/category_defaults.yaml gives it usable_as []
FIDS = ["steep_or_stairs", "scenic_view", "cozy_decor", "crowd", "long_walk", "kids_play_area", "rest_benches",
        "toilet_available", "weather_exposed", "setting", "rough_road_access", "stroller_access", "food_quality",
        "alcohol_required", "wine_tasting_available"]
WHO = ["kids", "parents", "pregnant", "wheelchair"]


def _value(rng, fid):
    vals = list(ONT.features[fid].values)
    v = rng.choice(vals)
    status = rng.choice(["VERIFIED", "VERIFIED", "OUTDATED", "UNCERTAIN"])
    dist = {v: rng.randint(1, 5)}
    if rng.random() < 0.3:
        dist[rng.choice(vals)] = rng.randint(1, 3)
    ctx = {}
    if rng.random() < 0.3:
        ctx = {"time_of_day=morning": {rng.choice(vals): 2}, "day_type=weekend": {}}
    return feat(v, n=rng.randint(1, 6), status=status, dist=dist, by_context=ctx, rate=rng.random() / 5,
                agreement=round(rng.uniform(0.4, 1.0), 2))


def records(seed: int, n: int = 60) -> list[dict]:
    rng = random.Random(seed)
    out = []
    for i in range(n):
        group, usable = rng.choice(GROUPS)
        feats = {f: _value(rng, f) for f in rng.sample(FIDS, rng.randint(0, 6))}
        hours = None if rng.random() < 0.15 else (
            ALL_DAY if rng.random() < 0.7 else {d: [["08:00", "17:00"]] for d in rng.sample(list(ALL_DAY), 3)})
        crowd = None if rng.random() < 0.5 else {dt: {b: rng.randint(10, 100) for b in ("morning", "noon", "afternoon", "evening")}
                                                 for dt in ("weekday", "weekend")}
        price = None if rng.random() < 0.5 else {"min_vnd": rng.choice([None, 30000, 80000]), "max_vnd": rng.choice([None, 150000])}
        details = None
        if rng.random() < 0.4:
            details = {"fit": {w: fit_entry(rng.choice(["good", "bad", "conditional"]),
                                            status=rng.choice(["VERIFIED", "UNCERTAIN"]), reasons=["r1", "r2"])
                               for w in rng.sample(WHO, 2)}}
        lat = None if rng.random() < 0.05 else 11.9 + rng.random() / 10
        r = srec(f"P{i:03d}", group=group, usable=usable, features=feats, hours=hours,
                 hours_status=rng.choice(["VERIFIED", "VERIFIED", "OUTDATED"]), crowd_by_time=crowd, price=price,
                 voices=rng.randint(0, 200), dup=rng.choice([None, None, 1, 2]), lat=lat,
                 lng=108.4 + rng.random() / 10, area=rng.choice(["area-1", "area-2", "area-3", None]), details=details)
        out.append(r)
    return out


def sessions(seed: int, recs: list[dict], n: int) -> list[Session]:
    rng = random.Random(seed)
    ids = [r["id"] for r in recs]
    out = []
    for k in range(n):
        hf = []
        for f in rng.sample(FIDS, rng.randint(0, 3)):
            hf.append(hard(f, rng.choice(list(ONT.features[f].values)), op=rng.choice(["ne", "ne", "eq"]),
                           policy=rng.choice(["exclude", "flag"])))
        if rng.random() < 0.2:
            hf.append(hard(f"fit.{rng.choice(WHO)}", "bad"))
        if rng.random() < 0.25:
            hf.append(hard("venue_category", "bar", op=rng.choice(["ne", "eq"]), policy=rng.choice(["exclude", "flag"])))
        if rng.random() < 0.25:
            hf.append(hard("activity", rng.choice(["alcohol_consumption", "alcohol_consumption", "eating", "coffee", "drinking"]),
                           op=rng.choice(["ne", "eq"]), policy=rng.choice(["exclude", "flag"])))
        sw = [love(f, rng.choice(list(ONT.features[f].values)), weight=rng.choice([1, 1, -1]),
                   context=rng.choice([None, {"time_of_day": "morning"}]))
              for f in rng.sample(FIDS, rng.randint(0, 4))]
        anchors = [{"place_id": p, "priority": rng.choice(["must", "want"])} for p in rng.sample(ids, rng.randint(0, 2))]
        if rng.random() < 0.2:
            anchors.append({"place_id": "MISSING1", "priority": "must"})
        stays = [r["id"] for r in recs if r["identity"]["category_group"] == "stay"]
        if stays and rng.random() < 0.3:  # a lodging named as an anchor must never become a suggestion
            anchors.append({"place_id": rng.choice(stays), "priority": "must"})
        meals = [r["id"] for r in recs if "meal" in r["usable_as"]]
        wish = {"dishes": [{"dish": f"món {j}", "quote": f"món {j}",
                            "place_ids": rng.sample(meals, min(len(meals), rng.randint(0, 4)))}
                           for j in range(rng.randint(0, 2))],
                "kinds": [{"kind": f"kiểu {j}", "quote": f"kiểu {j}", "place_ids": rng.sample(ids, rng.randint(0, 5))}
                          for j in range(rng.randint(0, 2))],
                "like": [{"place_id": rng.choice(ids), "but": [], "quote": "giống"}] if rng.random() < 0.3 else []}
        vibes = [{"phrase": "look", "places": rng.sample(ids, rng.randint(1, 4))}] if rng.random() < 0.3 else []
        search = si(hard_filters=hf, soft_weights=sw, anchors=anchors, wishes=wish, vibes=vibes,
                    liked_groups=rng.sample(["nature", "sights", "chill", "meal"], rng.randint(0, 2)),
                    context={"purpose": rng.choice([None, "relax", "photo", "food_culture", "bond"]),
                             "companions": rng.sample(["kids", "parents"], rng.randint(0, 2)),
                             "days": rng.choice([1, 2, 3]),
                             "start_date": rng.choice([MONDAY.isoformat(), None]),
                             "month": rng.choice([None, 6, 12])},
                    pace={"level": rng.choice(["slow", "normal", "packed"]),
                          "crowd_tolerance": rng.choice([None, "avoid"])},
                    novelty={"level": rng.choice([None, "new", "familiar"]), "visited": rng.sample(ids, 2)})
        profile = Profile(travel_mult=rng.choice([1.0, 1.0, 0.7, 1.5]),
                          crowd_tolerance=rng.choice([None, "avoid", "ok_if_worth", "fine"]),
                          price_sensitivity=rng.choice([0.0, 0.0, 0.5, 1.0]),
                          soft=[SoftAdd(feature=f, value=rng.choice(list(ONT.features[f].values)),
                                        weight=rng.choice([1, -1])) for f in rng.sample(FIDS, rng.randint(0, 2))],
                          visited=rng.sample(ids, rng.randint(0, 2)))
        st = State(selected=rng.sample(ids, rng.randint(0, 3)),
                   dropped=[Drop(place_id=p, reason=None) for p in rng.sample(ids, rng.randint(0, 2))],
                   wishlist=rng.sample(ids, rng.randint(0, 1)),
                   relaxed=[(p, hf[0]["feature"]) for p in rng.sample(ids, 1)] if hf else [],
                   activities={p: rng.choice(["eating", "coffee", "sightseeing"]) for p in rng.sample(ids, rng.randint(0, 2))},
                   profile=profile)
        out.append(Session(id=f"{k:012d}", search_input=search, state=st))
    return out
