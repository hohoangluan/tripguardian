from corpus.aggregate import aggregate_place
from corpus.aggregate.details import cluster, place_details, tokens
from corpus.ontology import load
from corpus.review import label_key

ONT = load()
NONE = {"amount_vnd": None, "audience": None, "unit": None, "min_people": None, "months": [], "days": [], "hour": None,
        "who": None, "verdict": None}


def d(i, kind, text, author, source_type="gmaps_review", sample=None, tod="unknown", observed_at="2026-09-20", **detail):
    o = {"id": f"x:d{i}", "place_fid": "F", "feature": f"detail.{kind}", "value": text,
         "context": {"time_of_day": tod, "day_type": "unknown", "weather": "unknown"}, "source_type": source_type,
         "source_id": f"s{i}", "author": author, "observed_at": observed_at,
         "span": {"quote": f"q{i}", "field": "text", "start_s": None, "end_s": None}, "extractor": "t",
         "ontology_version": ONT.version, "detail": {**NONE, **detail}}
    if sample:
        o["sample"] = sample
    return o


def files(*details, **extra):
    return [{"place_fid": "F", "place_name": "P", "as_of": "2026-09-30", "ontology_version": ONT.version,
             "observations": [], "details": list(details), **extra}]


def test_tokens_drop_amounts_stopwords_and_case():
    assert tokens("Bánh căn trứng rất ngon 30k", frozenset({"rất"})) == frozenset({"bánh", "căn", "trứng", "ngon"})


def test_phrasings_of_one_thing_merge_into_one_cluster_named_by_its_most_typical_form():
    out = place_details(files(d(1, "order", "bánh căn trứng", "a"), d(2, "order", "Bánh căn trứng ngon", "b"),
                              d(3, "order", "bánh căn", "c"), d(4, "order", "mì Ý", "a")), ONT, {})["order"]
    assert [(c["text"], c["n"]) for c in out] == [("bánh căn trứng", 3), ("mì Ý", 1)]
    assert out[0]["members"] == ["x:d1", "x:d2", "x:d3"] and len(out[0]["evidence"]) == 3


def test_cluster_is_deterministic_and_compares_to_the_leader_only():
    items = [{"text": t, "tokens": frozenset(t.split()), "author": a, "id": a}
             for t, a in (("a b", "1"), ("b c", "2"), ("c d", "3"))]  # a chain a-b-c-d: no merging through the middle
    assert [[x["text"] for x in g] for g in cluster(items, 0.6)] == [["a b"], ["b c"], ["c d"]]
    assert cluster(items, 0.6) == cluster(list(reversed(items)), 0.6)


def test_one_author_counts_once_wrong_labels_and_skewed_samples_are_left_out():
    obs = [d(1, "order", "bánh căn", "a"), d(2, "order", "bánh căn", "a"), d(3, "order", "bánh căn", "b"),
           d(4, "known_for", "xích đu", "c", sample="extremes"), d(5, "fee", "xe điện", "c", sample="extremes",
                                                                     amount_vnd=40000),
           d(6, "order", "bánh căn", "e")]
    wrong = label_key("s3", "detail.order", "bánh căn", "q3")
    out = place_details(files(*obs), ONT, {wrong: "wrong", label_key("s6", "detail.order", "bánh căn", "q6"): "unsure_again"})
    assert out["order"][0]["n"] == 1 and out["order"][0]["members"] == ["x:d1", "x:d2"]
    assert "known_for" not in out and out["fee"][0]["n"] == 1  # known_for is an opinion kind, fee a fact


def test_official_source_alone_is_authority_and_only_for_kinds_a_business_can_state():
    out = place_details(files(d(1, "fee", "vé người lớn", "official:F", source_type="official_page", amount_vnd=50000,
                                audience="adult"), d(2, "avoid", "món đắt", "official:F", source_type="official_page")),
                        ONT, {})
    assert out["fee"][0]["authority"] is True and out["fee"][0]["n"] == 1 and "avoid" not in out
    assert place_details(files(d(1, "fee", "vé", "a", amount_vnd=50000)), ONT, {})["fee"][0]["authority"] is False


def test_fee_amount_is_the_median_of_one_number_per_author():
    out = place_details(files(d(1, "fee", "xe điện", "a", amount_vnd=40000, unit="item"),
                              d(2, "fee", "xe điện", "b", amount_vnd=50000, unit="item"),
                              d(3, "fee", "xe điện", "b", amount_vnd=50000, unit="item")), ONT, {})["fee"]
    assert out[0]["amount_vnd"] == 45000 and out[0]["unit"] == "item" and out[0]["n"] == 2


def test_fit_clusters_per_who_and_keeps_each_verdict_apart():
    out = place_details(files(d(1, "fit", "phải rọ mõm", "a", who="pet", verdict="conditional"),
                              d(2, "fit", "không cho chó vào", "b", who="pet", verdict="bad"),
                              d(3, "fit", "phải rọ mõm", "c", who="baby", verdict="bad")), ONT, {})["fit"]
    assert sorted((c["who"], c["text"], c["verdicts"]) for c in out) == [
        ("baby", "phải rọ mõm", {"bad": 1}), ("pet", "không cho chó vào", {"bad": 1}),
        ("pet", "phải rọ mõm", {"conditional": 1})]


def test_best_time_counts_time_of_day_months_and_days_by_author():
    out = place_details(files(d(1, "best_time", "đi sớm", "a", tod="early_morning", hour="06:00", months=[11]),
                              d(2, "best_time", "đi sớm", "b", tod="early_morning", hour="07:00"),
                              d(3, "schedule", "đêm nhạc", "a", days=["sat"])), ONT, {})
    c = out["best_time"][0]
    assert c["time_of_day"] == {"early_morning": 2} and c["months"] == {11: 1} and c["hours"] == ["06:00", "07:00"]
    assert out["schedule"][0]["days"] == {"sat": 1}


def test_aggregate_place_carries_details_and_official_facts():
    official = {"place_fid": "F", "place_name": "P", "as_of": "2026-09-30", "ontology_version": ONT.version,
                "source": "official", "observations": [], "details": [],
                "place_facts": {"tickets_vnd": {"adult": [50000], "child": [], "senior": [30000]}, "last_entry": "16:30"}}
    res = aggregate_place(files(d(1, "order", "bánh căn", "a")) + [official], ONT)
    assert res["details"]["order"][0]["text"] == "bánh căn"
    assert res["operation"]["tickets_vnd"]["senior"] == [30000] and res["operation"]["last_entry"] == "16:30"
    assert aggregate_place(files(), ONT)["details"] == {} and aggregate_place(files(), ONT)["operation"]["last_entry"] is None
