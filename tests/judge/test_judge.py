import importlib

from corpus.judge.dedup import candidates, merges
from corpus.observe.tiktok.extract import author_of, owner_account
from corpus.ontology import load

ONT = load()
audit = importlib.import_module("corpus.judge.audit")
dedup_mod = importlib.import_module("corpus.judge.dedup")


def test_owner_account_matches_the_place_name_not_a_creator():
    assert owner_account("vuondauhoanganh", "Vườn dâu Hoàng Anh")
    assert owner_account("tiemcaphemountainchill", "Mountain Chill Tiệm Cà Phê - Đà Lạt")
    assert not owner_account("dalatbinhthuongthoi", "Cầu La Bá")
    assert not owner_account("tiendalatrongchoi", "Hồ Xuân Hương")
    v = {"author_id": None, "video_url": "https://www.tiktok.com/@vuondauhoanganh/video/1"}
    assert author_of(v, {"fid": "F", "name": "Vườn dâu Hoàng Anh"}) == "tiktok:owner:F"
    assert author_of({"author_id": "abc"}, {"fid": "F", "name": "Hồ Xuân Hương"}) == "tiktok:abc"


def _row(i, feature, value, source="gmaps", place="P"):
    o = {"id": f"x{i}", "place_fid": place, "feature": feature, "value": value, "source_type": "gmaps_review",
         "source_id": f"s{i}", "span": {"quote": f"q{i}"}}
    return (source, place, {"place_fid": place, "place_name": place}, o)


def test_select_takes_risky_features_whole_and_samples_the_rest(monkeypatch):
    monkeypatch.setattr(audit, "SAMPLE", 3)
    rows = [_row(i, "steep_or_stairs", "present") for i in range(10)] + [_row(100 + i, "food_quality", "good")
                                                                          for i in range(10)]
    picked = audit.select(rows, ONT, {})
    assert sum(r[3]["feature"] == "steep_or_stairs" for r in picked) == 10
    assert sum(r[3]["feature"] == "food_quality" for r in picked) == 3


def test_select_pulls_a_failing_sampled_stratum_whole(monkeypatch):
    from corpus.review import label_key
    rows = [_row(i, "food_quality", "good") for i in range(40)]
    done = {label_key(r[3]["source_id"], "food_quality", "good", r[3]["span"]["quote"]): "wrong" for r in rows[:25]}
    assert len(audit.select(rows, ONT, done)) == 15  # 25 labelled, precision 0: the other 15 all get checked


def test_chunks_keep_strong_items_apart():
    rows = [_row(1, "kids", "suitable"), _row(2, "kids", "unsuitable"), _row(3, "steep_or_stairs", "present")]
    parts = audit.chunks(rows, ONT)
    assert [[r[3]["id"] for r in p] for p in parts] == [["x2", "x3"], ["x1"]]


def test_stale_wrong_judge_labels_are_asked_again():
    recs = {"k1": {"label": "wrong", "by": "judge:m", "ph": "old"}, "k2": {"label": "wrong", "by": "judge:m",
            "ph": audit.OBS_AUDIT.prompt_hash}, "k3": {"label": "wrong"}, "k4": {"label": "correct", "by": "judge:m"}}
    assert audit.current(recs) == {"k2": "wrong", "k3": "wrong", "k4": "correct"}


def test_dedup_candidates_need_close_pins_and_shared_name():
    a = {"fid": "a", "name": "Woody Classic Bar", "lat": 11.94, "lng": 108.43}
    b = {"fid": "b", "name": "Woody Classic Bar (Billiards)", "lat": 11.9401, "lng": 108.4301}
    c = {"fid": "c", "name": "Clover Spa Massage", "lat": 11.9402, "lng": 108.4302}
    d = {"fid": "d", "name": "Charm Spa Massage", "lat": 11.9403, "lng": 108.4303}
    pairs = [(x["fid"], y["fid"]) for x, y, _ in candidates([a, b, c, d])]
    assert pairs == [("a", "b")]


def test_merges_resolve_chains(monkeypatch):
    import json
    strong = {"relation": "same_place"}
    recs = {"a|b": {"decision": "same_place", "note": json.dumps({"canonical": "a", "model": "m", "strong": strong})},
            "b|c": {"decision": "same_place", "note": json.dumps({"canonical": "b", "model": "m", "strong": strong})},
            "d|e": {"decision": "part_of", "note": "{}"},
            "f|g": {"decision": "same_place", "note": json.dumps({"canonical": "f", "model": "m"})}}
    monkeypatch.setattr(dedup_mod, "decision_records", lambda kind: recs)
    m = merges()
    assert m.get("b") == "a" and m.get("c") == "a" and "d" not in m
    assert "g" not in m  # one Judge alone does not merge


def test_closure_needs_the_strong_judge(monkeypatch):
    import json
    st = importlib.import_module("corpus.judge.status")
    recs = {"x": {"decision": "closed", "note": json.dumps({"model": "m", "strong": {"status": "closed"}})},
            "y": {"decision": "closed", "note": json.dumps({"model": "m"})},
            "z": {"decision": "changed", "note": json.dumps({"model": "m", "strong": {"status": "open"}})},
            "w": {"decision": "closed", "note": ""}}
    monkeypatch.setattr(st, "decision_records", lambda kind: recs)
    assert st.verdicts() == {"x": "closed", "y": "unclear", "z": "unclear", "w": "closed"}


def test_status_reopens_a_judge_verdict_whose_reports_are_gone(tmp_path, monkeypatch):
    import asyncio
    import json
    st = importlib.import_module("corpus.judge.status")
    monkeypatch.setenv("DATA_DIR", str(tmp_path))
    obs = tmp_path / "gmaps" / "observations"
    obs.mkdir(parents=True)
    for fid in ("A", "B"):
        (obs / f"{fid}.json").write_text(json.dumps({"place_fid": fid, "observations": []}), encoding="utf-8")
    recs = {"A": {"decision": "unclear", "note": json.dumps({"model": "m"})},
            "B": {"decision": "closed", "note": ""}}  # a person's decision
    decided = []
    monkeypatch.setattr(st, "decision_records", lambda kind: recs)
    monkeypatch.setattr(st, "decide", lambda kind, id, d, note="": decided.append((id, d)))
    monkeypatch.setattr(st, "load_config", lambda city: ("Đà Lạt", {}))
    monkeypatch.setattr(type(st.PLACE_STATUS.role), "client",
                        lambda self: (type("C", (), {"with_options": lambda s, **k: s})(), "m"))
    summary = asyncio.run(st.run("dalat"))
    assert decided == [("A", "open")] and summary["status"] == {"open": 1}
