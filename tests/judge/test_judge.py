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
    monkeypatch.setattr(audit, "SAMPLE_STEPS", (3, 6))
    rows = [_row(i, "steep_or_stairs", "present") for i in range(10)] + [_row(100 + i, "food_quality", "good")
                                                                          for i in range(10)]
    picked = audit.select(rows, ONT, {})
    assert sum(r[3]["feature"] == "steep_or_stairs" for r in picked) == 10
    assert sum(r[3]["feature"] == "food_quality" for r in picked) == 3


def _labelled(rows, correct: int, wrong: int) -> dict:
    from corpus.review import label_key
    keys = [label_key(r[3]["source_id"], r[3]["feature"], r[3]["value"], r[3]["span"]["quote"]) for r in rows]
    return {k: "correct" if i < correct else "wrong" for i, k in enumerate(keys[:correct + wrong])}


def test_select_pulls_a_failing_sampled_stratum_whole():
    rows = [_row(i, "food_quality", "good") for i in range(40)]
    assert len(audit.select(rows, ONT, _labelled(rows, 0, 30))) == 10  # precision 0: the other 10 all get checked


def test_select_grows_an_undecided_sample_and_stops_a_passed_one():
    rows = [_row(i, "food_quality", "good") for i in range(300)]
    assert len(audit.select(rows, ONT, _labelled(rows, 27, 3))) == 30  # 90% on 30 is undecided: grow to 60
    assert len(audit.select(rows, ONT, _labelled(rows, 92, 8))) == 0  # Wilson lower 0.85: passed
    assert len(audit.select(rows, ONT, _labelled(rows, 85, 15))) == 200  # undecided at the last step: check all


def test_read_all_takes_every_unlabelled_claim_even_of_a_passed_stratum(monkeypatch):
    rows = [_row(i, "food_quality", "good") for i in range(300)]
    done = _labelled(rows, 92, 8)  # passed: a sampled audit reads nothing more
    monkeypatch.setenv("JUDGE_READ_ALL", "1")
    assert audit.read_all() and len(audit.select(rows, ONT, done, read_all=True)) == 200
    monkeypatch.setenv("JUDGE_READ_ALL", "0")
    assert not audit.read_all()


def test_pool_spreads_calls_over_endpoints_within_their_slots():
    import asyncio
    busy, peak, used = {"a": 0, "b": 0}, {"a": 0, "b": 0}, []

    async def call(pool):
        async with pool.take() as (client, model):
            busy[client] += 1
            peak[client] = max(peak[client], busy[client])
            used.append(client)
            await asyncio.sleep(0.01)
            busy[client] -= 1

    async def main():
        pool = audit.Pool([("a", "m", 2), ("b", "m", 1)])
        await asyncio.gather(*(call(pool) for _ in range(9)))

    asyncio.run(main())
    assert peak == {"a": 2, "b": 1} and used.count("a") > used.count("b") > 0


def test_also_lan_only_on_a_uit_gemma_run(monkeypatch):
    monkeypatch.setenv("JUDGE_ALSO_LAN", "1")
    monkeypatch.delenv("EXTRACTOR_ON_UIT", raising=False)
    assert not audit.also_lan()  # the run is on the LAN host already
    monkeypatch.setenv("EXTRACTOR_ON_UIT", "1")
    assert audit.also_lan()


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


def test_second_look_takes_only_first_look_judge_unsure():
    from corpus.review import label_key
    rows = [_row(i, "food_quality", "good") for i in range(4)]
    keys = [label_key(r[3]["source_id"], "food_quality", "good", r[3]["span"]["quote"]) for r in rows]
    records = {keys[0]: {"label": "unsure", "by": "judge:cx/gpt-5.6-sol"},
               keys[1]: {"label": "unsure", "by": "judge:cx/gpt-6-astra", "look": 2},
               keys[2]: {"label": "unsure"},  # a person's unsure stands
               keys[3]: {"label": "wrong", "by": "judge:cx/gpt-5.6-sol"}}
    assert [r[3]["id"] for r in audit.unsure_rows(rows + rows[:1], records)] == ["x0"]


def test_aggregate_drops_a_claim_still_unsure_on_the_second_look():
    from corpus.aggregate.place import usable
    from corpus.review import label_key
    o = _row(1, "food_quality", "good")[3]
    k = label_key(o["source_id"], "food_quality", "good", o["span"]["quote"])
    feat = ONT.features["food_quality"]
    assert usable(o, feat, {k: "unsure"})
    assert not usable(o, feat, {k: "unsure_again"})
    assert not usable(o, feat, {k: "wrong"})


def test_first_reader_correct_stands_and_the_judge_reads_the_rest(monkeypatch):
    rows = [_row(i, "food_quality", "good") for i in range(3)]
    asked, written = [], []

    async def fake_ask(task, client, model, images=(), **fields):
        asked.append((task.role.name, fields["items"].count("</i")))
        if task.role.name == "judge_first":
            return {"items": [{"ref": "i1", "verdict": "correct", "reason": "r"},
                              {"ref": "i2", "verdict": "wrong", "reason": "r"}]}  # i3 left out
        return {"items": [{"ref": "i1", "verdict": "correct", "reason": "r"},
                          {"ref": "i2", "verdict": "wrong", "reason": "r"}]}

    monkeypatch.setattr(audit, "ask", fake_ask)
    monkeypatch.setattr(audit, "evidence", lambda st, o, source: {"text": "t", "date": None, "rating": None, "image": None})
    monkeypatch.setattr(audit, "place_info", lambda st: {"category": "c", "address": "a"})
    monkeypatch.setattr(audit, "judge_label", lambda o, st, source, verdict, note, by, ph, look=1: written.append((o["id"], verdict, by)))
    import asyncio
    clients = {n: (None, n) for n in ("judge", "judge_first", "judge_strong")}
    sems = {n: audit.Pool([(*clients[n], 1)]) for n in clients}
    got = asyncio.run(audit.audit_chunk(rows, ONT, "Đà Lạt", clients, sems))
    assert asked == [("judge_first", 3), ("judge", 2)]  # the Judge reads the wrong one and the missing one
    assert written == [("x0", "correct", "judge:judge_first"), ("x1", "correct", "judge:judge"), ("x2", "wrong", "judge:judge")]
    assert got["correct"] == 2 and got["wrong"] == 1 and got["missing"] == 0


def test_gemma_audit_reads_every_claim_once_and_its_unsure_is_final(monkeypatch):
    rows = [_row(i, "food_quality", "good") for i in range(3)]
    asked, written = [], []

    async def fake_ask(task, client, model, images=(), **fields):
        asked.append((task.role.name, "claim: " in fields["items"]))
        return {"items": [{"ref": "<i1>", "doubt": "d", "verdict": "correct"},
                          {"ref": "i2", "doubt": "d", "verdict": "unsure"},
                          {"ref": "i3", "doubt": "d", "verdict": "wrong"}]}

    monkeypatch.setattr(audit, "ask", fake_ask)
    monkeypatch.setattr(audit, "evidence", lambda st, o, source: {"text": "t", "date": None, "rating": None, "image": None})
    monkeypatch.setattr(audit, "place_info", lambda st: {"category": "c", "address": "a"})
    monkeypatch.setattr(audit, "judge_label", lambda o, st, source, verdict, note, by, ph, look=1:
                        written.append((o["id"], verdict, look, ph)))
    import asyncio
    clients = {"extractor": (None, "gemma")}
    sems = {"extractor": audit.Pool([(*clients["extractor"], 1)])}
    got = asyncio.run(audit.audit_chunk(rows, ONT, "Đà Lạt", clients, sems))
    ph = audit.OBS_AUDIT_GEMMA.prompt_hash
    assert asked == [("extractor", True)]  # one strict reader, items carry their claim sentence
    assert written == [("x0", "correct", 1, ph), ("x1", "unsure", 2, ph), ("x2", "wrong", 1, ph)]
    assert got["missing"] == 0


def test_gemma_wrong_and_unsure_stand_on_gemma_and_go_back_to_the_codex_judge():
    ph = audit.OBS_AUDIT_GEMMA.prompt_hash
    recs = {"k1": {"label": "wrong", "by": "judge:gemma-4-26b", "ph": ph},
            "k2": {"label": "unsure", "by": "judge:gemma-4-26b", "ph": ph, "look": 2},
            "k3": {"label": "correct", "by": "judge:gemma-4-26b", "ph": ph}}
    assert audit.current(recs, local=True) == {"k1": "wrong", "k2": "unsure", "k3": "correct"}
    assert audit.current(recs) == {"k3": "correct"}


def test_claim_text_picks_the_value_part_of_the_hint():
    assert audit.claim_text(ONT.features["food_quality"], "mixed") == "nơi này: bình thường"  # no claims: the hint part
    assert audit.claim_text(ONT.features["booking_needed"], "yes") == ONT.features["booking_needed"].claims["yes"]


def test_gemma_correct_on_a_picture_waits_for_the_strong_judge(monkeypatch):
    rows = [("gmaps_photo",) + _row(0, "setting", "outdoor")[1:]]

    async def fake_ask(task, client, model, images=(), **fields):
        return {"items": [{"ref": "i1", "doubt": "d", "verdict": "correct"}]}

    written = []
    monkeypatch.setattr(audit, "ask", fake_ask)
    monkeypatch.setattr(audit, "evidence", lambda st, o, source: {"text": "t", "date": None, "rating": None, "image": None})
    monkeypatch.setattr(audit, "place_info", lambda st: {"category": "c", "address": "a"})
    monkeypatch.setattr(audit, "judge_label", lambda o, st, source, verdict, note, by, ph, look=1:
                        written.append((verdict, look)))
    import asyncio
    asyncio.run(audit.audit_chunk(rows, ONT, "Đà Lạt", {"extractor": (None, "g")}, {"extractor": audit.Pool([(None, "g", 1)])}))
    assert written == [("unsure", 1)]  # kept like an unlabelled claim; the second look reads it when sol is back


def test_gemma_never_relabels_or_hides_a_codex_label(monkeypatch):
    old = {"label": "wrong", "by": "judge:cx/gpt-5.6-sol", "ph": "old"}
    assert audit.current({"k": old}, local=True) == {"k": "wrong"}  # not asked again on Gemma
    lab = importlib.import_module("corpus.review.labels")
    recs = [{"key": "k", "id": "x", "label": "wrong", "by": "judge:cx/gpt-5.6-sol"},
            {"key": "k", "id": "x", "label": "unsure", "by": "judge:gemma-4-26b"},
            {"key": "g", "id": "y", "label": "wrong", "by": "judge:gemma-4-26b"},
            {"key": "g", "id": "y", "label": "correct", "by": "judge:cx/gpt-6.1-sol"}]
    monkeypatch.setattr(lab, "_all", lambda: recs)
    monkeypatch.setattr(lab, "_rows", lambda: [])
    got = lab.latest()
    assert got["k"]["by"] == "judge:cx/gpt-5.6-sol" and got["g"]["by"] == "judge:cx/gpt-6.1-sol"
