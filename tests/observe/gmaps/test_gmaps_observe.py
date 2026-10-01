import asyncio
import json
import re

from corpus.observe.gmaps import extract
from corpus.ontology import load

FETCHED = "2026-09-30T08:00:00+00:00"
DIR = "0xF_0x1"


def review(i, text, author, details=(), rating=None, published="2 tuần trước"):
    return {"review_id": f"R{i}", "text": text, "author_hash": author, "details": list(details), "rating": rating,
            "published_text": published, "likes": 0, "photos": 0, "author_meta": ""}


def setup(tmp_path, monkeypatch, reviews, qc=None, place=None):
    monkeypatch.setenv("DATA_DIR", str(tmp_path))
    d = tmp_path / "gmaps" / "places" / DIR
    d.mkdir(parents=True)
    (d / "place.json").write_text(json.dumps({"fid": "0xF:0x1", "name": "Quán A", "category": "Quán cà phê",
                                              "fetched_at": FETCHED, **(place or {})}), encoding="utf-8")
    (d / "reviews.json").write_text(json.dumps(reviews, ensure_ascii=False), encoding="utf-8")
    if qc:
        (tmp_path / "gmaps" / "qc").mkdir(parents=True)
        (tmp_path / "gmaps" / "qc" / f"{DIR}.json").write_text(json.dumps(qc), encoding="utf-8")
    monkeypatch.setattr(extract, "load_config", lambda city: ("Đà Lạt", {}))
    async def providers():
        return [(None, "gemma-test", 4)]

    monkeypatch.setattr(extract, "_providers", providers)
    calls = []

    async def fake_ask(client, model, city, place, ontology_text, reviews_text, note=""):
        calls.append({"reviews": reviews_text, "note": note})
        items = []
        for ref, text in re.findall(r"^(r\d+): (.*)$", reviews_text, re.M):
            obs = [{"feature": "scenic_view", "value": "present", "quote": "view đẹp", "time_of_day": "unknown",
                    "day_type": "unknown", "weather": "unknown"}] if "view đẹp" in text else []
            items.append({"ref": ref, "observations": obs, "proposed": []})
        return {"reviews": items}

    monkeypatch.setattr(extract, "ask_batch", fake_ask)

    async def fake_verify(client, model, place, passage, claim):
        return {"verdict": "supports", "reason": ""}

    monkeypatch.setattr(extract, "verify_claim", fake_verify)
    return calls, tmp_path / "gmaps" / "observations" / f"{DIR}.json"


REVIEWS = [
    review(1, "Quán có view đẹp, cuối tuần đông", "a1", ["Đã đến vào\nCuối tuần", "Độ ồn\nRất yên tĩnh"], "5 sao"),
    review(2, "", "a2", ["Đồ ăn: 1"], "1 sao", "3 tháng trước"),
    review(3, "Được rồi", "a3"),
    review(4, "Liên hệ 0909 để đặt tour giá rẻ nhất", "a4"),
]
QC = {"llm": {"bad_reviews": [{"review_id": "R4", "problem": "spam"}]}}


def test_observe_writes_details_and_llm_observations(tmp_path, monkeypatch):
    calls, out = setup(tmp_path, monkeypatch, REVIEWS, QC)
    asyncio.run(extract.run("dalat"))
    res = json.loads(out.read_text(encoding="utf-8"))
    got = [(o["id"], o["feature"], o["value"], o["source_type"], o["context"]["day_type"], o["observed_at"])
           for o in res["observations"]]
    assert got == [
        ("gmaps:R1:0", "noise", "quiet", "gmaps_details", "weekend", "2026-09-16"),
        ("gmaps:R2:0", "food_quality", "poor", "gmaps_details", "unknown", "2026-07-02"),
        ("gmaps:R1:1", "scenic_view", "present", "gmaps_review", "weekend", "2026-09-16"),
    ]
    assert res["observations"][2]["span"] == {"quote": "view đẹp", "field": "text", "start_s": None, "end_s": None}
    assert res["observations"][0]["span"]["quote"] == "Độ ồn\nRất yên tĩnh"
    assert res["place_fid"] == "0xF:0x1" and res["as_of"] == "2026-09-30" and res["ontology_version"] == load().version
    assert res["ratings"] == [{"author": "a1", "observed_at": "2026-09-16", "stars": 5},
                              {"author": "a2", "observed_at": "2026-07-02", "stars": 1}]
    assert len(calls) == 1 and "r1: Quán có view đẹp" in calls[0]["reviews"]
    assert "Liên hệ" not in calls[0]["reviews"] and "Được rồi" not in calls[0]["reviews"]
    assert res["stats"]["to_llm"] == 1


def test_observe_is_cached_until_reviews_change(tmp_path, monkeypatch):
    calls, out = setup(tmp_path, monkeypatch, REVIEWS)
    asyncio.run(extract.run("dalat"))
    asyncio.run(extract.run("dalat"))
    assert len(calls) == 1
    reviews_file = tmp_path / "gmaps" / "places" / DIR / "reviews.json"
    reviews_file.write_text(json.dumps(REVIEWS + [review(5, "Một quán khác có view đẹp", "a5")]), encoding="utf-8")
    asyncio.run(extract.run("dalat"))
    assert len(calls) == 2


def test_many_reviews_are_split_into_batches(tmp_path, monkeypatch):
    calls, out = setup(tmp_path, monkeypatch, [review(i, f"Review số {i} có view đẹp", f"a{i}") for i in range(16)])
    asyncio.run(extract.run("dalat"))
    assert len(calls) == 2
    assert len(json.loads(out.read_text(encoding="utf-8"))["observations"]) == 16


def test_failed_single_review_retries_once_then_logs_and_writes_nothing(tmp_path, monkeypatch):
    calls, out = setup(tmp_path, monkeypatch, REVIEWS, QC)  # QC drops R4: one review goes to the model

    async def broken(client, model, city, place, ontology_text, reviews_text, note=""):
        calls.append({"reviews": reviews_text, "note": note})
        raise ValueError("not json")

    monkeypatch.setattr(extract, "ask_batch", broken)
    summary = asyncio.run(extract.run("dalat"))
    assert len(calls) == 2 and calls[0]["note"] == "" and "rejected" in calls[1]["note"]
    assert not out.exists()
    errors = (tmp_path / "gmaps" / "observe_errors.jsonl").read_text(encoding="utf-8").splitlines()
    assert len(errors) == 1 and DIR in errors[0]
    assert summary["status"] == {"failed": 1}


def test_failed_batch_is_split_in_halves(tmp_path, monkeypatch):
    calls, out = setup(tmp_path, monkeypatch, [review(i, f"Review số {i} có view đẹp", f"a{i}") for i in range(4)])
    ok = extract.ask_batch

    async def big_fails(client, model, city, place, ontology_text, reviews_text, note=""):
        if reviews_text.count("\n") >= 2:  # 3+ reviews: the model loops on whitespace and is cut
            calls.append({"reviews": reviews_text, "note": note})
            raise ValueError("Expecting ',' delimiter")
        return await ok(client, model, city, place, ontology_text, reviews_text, note)

    monkeypatch.setattr(extract, "ask_batch", big_fails)
    asyncio.run(extract.run("dalat"))
    res = json.loads(out.read_text(encoding="utf-8"))
    assert sorted(o["source_id"] for o in res["observations"]) == ["R0", "R1", "R2", "R3"]
    assert len(calls) == 3  # one failed 4-review call, then two 2-review calls


def test_observation_schema_puts_quote_last():
    from corpus.llm import REVIEW_OBSERVE
    obs = REVIEW_OBSERVE.schema["properties"]["reviews"]["items"]["properties"]["observations"]["items"]
    assert list(obs["properties"])[-1] == "quote" and obs["required"][-1] == "quote"


def test_limit_takes_first_places(tmp_path, monkeypatch):
    calls, out = setup(tmp_path, monkeypatch, REVIEWS)
    summary = asyncio.run(extract.run("dalat", limit=0))
    assert summary["places"] == 0 and not out.exists()


def add_place(tmp_path, dir_name, reviews):
    d = tmp_path / "gmaps" / "places" / dir_name
    d.mkdir(parents=True)
    (d / "place.json").write_text(json.dumps({"fid": dir_name.replace("_", ":"), "name": "B", "category": "Quán",
                                              "fetched_at": FETCHED}), encoding="utf-8")
    (d / "reviews.json").write_text(json.dumps(reviews, ensure_ascii=False), encoding="utf-8")


def test_transport_error_is_not_split_and_other_places_finish(tmp_path, monkeypatch):
    import httpx
    import openai
    calls, out = setup(tmp_path, monkeypatch, [review(i, f"Review số {i} có view đẹp", f"a{i}") for i in range(4)])
    add_place(tmp_path, "0xG_0x2", [review(9, "Quán khác cũng có view đẹp", "z")])
    ok, a_calls = extract.ask_batch, []

    async def down_for_a(client, model, city, place, ontology_text, reviews_text, note=""):
        if place["name"] == "Quán A":
            a_calls.append(reviews_text)
            raise openai.APIConnectionError(request=httpx.Request("POST", "http://llm"))
        return await ok(client, model, city, place, ontology_text, reviews_text, note)

    monkeypatch.setattr(extract, "ask_batch", down_for_a)
    summary = asyncio.run(extract.run("dalat"))
    assert len(a_calls) == 1  # no halves, no retries: splitting cannot fix the network
    assert summary["status"] == {"failed": 1, "done": 1}
    assert "APIConnectionError" in (tmp_path / "gmaps" / "observe_errors.jsonl").read_text(encoding="utf-8")


def test_error_without_message_is_logged_and_run_finishes(tmp_path, monkeypatch):
    calls, out = setup(tmp_path, monkeypatch, REVIEWS, QC)
    add_place(tmp_path, "0xG_0x2", [review(9, "Quán khác cũng có view đẹp", "z")])
    ok = extract.ask_batch

    async def timeout_for_a(client, model, city, place, ontology_text, reviews_text, note=""):
        if place["name"] == "Quán A":
            raise asyncio.TimeoutError()
        return await ok(client, model, city, place, ontology_text, reviews_text, note)

    monkeypatch.setattr(extract, "ask_batch", timeout_for_a)
    summary = asyncio.run(extract.run("dalat"))
    assert summary["status"] == {"failed": 1, "done": 1}
    assert "TimeoutError" in (tmp_path / "gmaps" / "observe_errors.jsonl").read_text(encoding="utf-8")
    assert (tmp_path / "gmaps" / "observe_summary.json").exists()


def test_qc_run_after_observe_redoes_the_place(tmp_path, monkeypatch):
    calls, out = setup(tmp_path, monkeypatch, REVIEWS)
    asyncio.run(extract.run("dalat"))
    assert "Liên hệ" in calls[0]["reviews"]
    (tmp_path / "gmaps" / "qc").mkdir(parents=True)
    (tmp_path / "gmaps" / "qc" / f"{DIR}.json").write_text(json.dumps(QC), encoding="utf-8")
    asyncio.run(extract.run("dalat"))
    assert len(calls) == 2 and "Liên hệ" not in calls[1]["reviews"]


def test_failed_rerun_removes_the_outdated_file(tmp_path, monkeypatch):
    calls, out = setup(tmp_path, monkeypatch, REVIEWS, QC)
    asyncio.run(extract.run("dalat"))
    assert out.exists()
    (tmp_path / "gmaps" / "places" / DIR / "reviews.json").write_text(
        json.dumps(REVIEWS + [review(5, "Một quán khác có view đẹp", "a5")]), encoding="utf-8")

    async def broken(client, model, city, place, ontology_text, reviews_text, note=""):
        raise ValueError("not json")

    monkeypatch.setattr(extract, "ask_batch", broken)
    asyncio.run(extract.run("dalat"))
    assert not out.exists()


def test_attributes_and_place_facts(tmp_path, monkeypatch):
    calls, out = setup(tmp_path, monkeypatch, [], place={
        "attributes": ["Phù hợp cho trẻ em", "Không có lối vào cho xe lăn", "Có nhà vệ sinh"],
        "popular_times": [["Mức độ đông là 40% lúc 09 giờ."]] + [[]] * 6,
        "price": "Khoảng giá, 1-100.000 ₫/người, 9 người đã báo cáo"})
    asyncio.run(extract.run("dalat"))
    res = json.loads(out.read_text(encoding="utf-8"))
    got = [(o["id"], o["feature"], o["value"], o["source_type"], o["author"], o["span"]["field"], o["observed_at"])
           for o in res["observations"]]
    assert got == [("gmaps:attr:0", "kids", "suitable", "gmaps_attribute", "gmaps:attributes", "attributes", "2026-09-30"),
                   ("gmaps:attr:1", "wheelchair", "unsuitable", "gmaps_attribute", "gmaps:attributes", "attributes",
                    "2026-09-30")]
    assert res["place_facts"] == {"popular_times": {"sun": {"9": 40}},
                                  "price": {"min_vnd": 1, "max_vnd": 100000, "per": "person", "reports": 9}}
    assert calls == []


def test_qc_flagged_review_gives_no_details_or_rating(tmp_path, monkeypatch):
    bad = review(7, "Liên hệ 0909 để đặt tour giá rẻ nhất", "spam", ["Độ ồn\nRất ồn, khó nghe"], "1 sao")
    calls, out = setup(tmp_path, monkeypatch, [bad], {"llm": {"bad_reviews": [{"review_id": "R7", "problem": "spam"}]}})
    asyncio.run(extract.run("dalat"))
    res = json.loads(out.read_text(encoding="utf-8"))
    assert res["observations"] == [] and res["ratings"] == []


def test_span_check_keeps_only_supported(tmp_path, monkeypatch):
    calls, out = setup(tmp_path, monkeypatch, [review(1, "Quán có view đẹp, lối vào hẻm dốc, mấy chị hông chặt chém", "a")])

    async def ask(client, model, city, place, ontology_text, reviews_text, note=""):
        def ob(f, v, q):
            return {"feature": f, "value": v, "quote": q, "time_of_day": "unknown", "day_type": "unknown",
                    "weather": "unknown"}
        return {"reviews": [{"ref": "r1", "proposed": [], "observations": [
            ob("scenic_view", "present", "view đẹp"), ob("steep_or_stairs", "present", "hẻm dốc"),
            ob("tourist_trap", "present", "hông chặt chém")]}]}

    checked = []

    async def verify(client, model, place, passage, claim):
        checked.append((passage, claim))
        trap = load().features["tourist_trap"].claims["present"]
        return {"verdict": "contradicts" if claim.startswith(trap) else "supports", "reason": ""}

    monkeypatch.setattr(extract, "ask_batch", ask)
    monkeypatch.setattr(extract, "verify_claim", verify)
    asyncio.run(extract.run("dalat"))
    res = json.loads(out.read_text(encoding="utf-8"))
    assert [o["feature"] for o in res["observations"]] == ["scenic_view", "steep_or_stairs"]
    assert len(checked) == 2 and "hông chặt chém" in checked[0][0]  # scenic_view is not span-checked
    assert res["stats"]["dropped"] == {"span_check_contradicts": 1}


def test_span_check_bad_answer_drops_the_observation(tmp_path, monkeypatch):
    calls, out = setup(tmp_path, monkeypatch, [review(1, "Lối vào hẻm dốc khá cao", "a")])

    async def ask(client, model, city, place, ontology_text, reviews_text, note=""):
        return {"reviews": [{"ref": "r1", "proposed": [], "observations": [
            {"feature": "steep_or_stairs", "value": "present", "quote": "hẻm dốc", "time_of_day": "unknown",
             "day_type": "unknown", "weather": "unknown"}]}]}

    async def verify(client, model, place, passage, claim):
        raise ValueError("not json")

    monkeypatch.setattr(extract, "ask_batch", ask)
    monkeypatch.setattr(extract, "verify_claim", verify)
    asyncio.run(extract.run("dalat"))
    res = json.loads(out.read_text(encoding="utf-8"))
    assert res["observations"] == [] and res["stats"]["dropped"] == {"span_check_error": 1}


def test_ontology_hint_change_redoes_cached_place(tmp_path, monkeypatch):
    import dataclasses
    calls, out = setup(tmp_path, monkeypatch, REVIEWS, QC)
    asyncio.run(extract.run("dalat"))
    ont = load()
    f = ont.features["crowd"]
    changed = dataclasses.replace(ont, features={**ont.features, "crowd": dataclasses.replace(f, hint=f.hint + "!")})
    monkeypatch.setattr(extract, "load_ontology", lambda: changed)
    asyncio.run(extract.run("dalat"))
    assert len(calls) == 2


def test_negative_claim_is_sent_as_its_own_statement_with_the_quote(tmp_path, monkeypatch):
    calls, out = setup(tmp_path, monkeypatch, [review(1, "Có bậc thang cao, xe lăn không vào được", "a")])

    async def ask(client, model, city, place, ontology_text, reviews_text, note=""):
        return {"reviews": [{"ref": "r1", "proposed": [], "observations": [
            {"feature": "wheelchair", "value": "unsuitable", "quote": "xe lăn không vào được", "time_of_day": "unknown",
             "day_type": "unknown", "weather": "unknown"}]}]}

    claims = []

    async def verify(client, model, place, passage, claim):
        claims.append(claim)
        return {"verdict": "supports", "reason": ""}

    monkeypatch.setattr(extract, "ask_batch", ask)
    monkeypatch.setattr(extract, "verify_claim", verify)
    asyncio.run(extract.run("dalat"))
    assert claims == [f'{load().features["wheelchair"].claims["unsuitable"]} (quote: "xe lăn không vào được")']
    assert [o["value"] for o in json.loads(out.read_text(encoding="utf-8"))["observations"]] == ["unsuitable"]


def test_non_dict_verify_answer_drops_only_the_observation(tmp_path, monkeypatch):
    calls, out = setup(tmp_path, monkeypatch, [review(1, "Lối vào hẻm dốc khá cao", "a")])

    async def ask(client, model, city, place, ontology_text, reviews_text, note=""):
        return {"reviews": [{"ref": "r1", "proposed": [], "observations": [
            {"feature": "steep_or_stairs", "value": "present", "quote": "hẻm dốc", "time_of_day": "unknown",
             "day_type": "unknown", "weather": "unknown"}]}]}

    async def verify(client, model, place, passage, claim):
        return ["supports"]

    monkeypatch.setattr(extract, "ask_batch", ask)
    monkeypatch.setattr(extract, "verify_claim", verify)
    summary = asyncio.run(extract.run("dalat"))
    assert summary["status"] == {"done": 1}
    assert json.loads(out.read_text(encoding="utf-8"))["stats"]["dropped"] == {"span_check_error": 1}


def test_span_check_setting_change_redoes_cached_place(tmp_path, monkeypatch):
    import dataclasses
    calls, out = setup(tmp_path, monkeypatch, REVIEWS, QC)
    asyncio.run(extract.run("dalat"))
    ont = load()
    f = ont.features["crowd"]
    changed = dataclasses.replace(ont, features={**ont.features, "crowd": dataclasses.replace(
        f, span_check=True, claims={v: v for v in f.values})})
    monkeypatch.setattr(extract, "load_ontology", lambda: changed)
    asyncio.run(extract.run("dalat"))
    assert len(calls) == 2


def test_endpoints_share_one_queue_of_slots(tmp_path, monkeypatch):
    calls, out = setup(tmp_path, monkeypatch, [review(i, f"Review số {i} có view đẹp", f"a{i}") for i in range(30)])
    used = []
    ok = extract.ask_batch

    async def ask(client, model, city, place, ontology_text, reviews_text, note=""):
        used.append(model)
        await asyncio.sleep(0.01)
        return await ok(client, model, city, place, ontology_text, reviews_text, note)

    async def providers():
        return [("a", "gemma-a", 1), ("b", "gemma-b", 1)]

    monkeypatch.setattr(extract, "ask_batch", ask)
    monkeypatch.setattr(extract, "_providers", providers)
    asyncio.run(extract.run("dalat"))
    assert set(used) == {"gemma-a", "gemma-b"}
    res = json.loads(out.read_text(encoding="utf-8"))
    assert len(res["observations"]) == 30 and res["model"] == "gemma-a,gemma-b"


def test_unreachable_endpoint_is_left_out(monkeypatch):
    class Bad:
        class chat:
            class completions:
                @staticmethod
                async def create(**kw):
                    return "<html>moved</html>"  # off campus: the UIT proxy answers with a redirect page

    class Good:
        class chat:
            class completions:
                @staticmethod
                async def create(**kw):
                    return type("R", (), {"choices": [object()]})()

    assert asyncio.run(extract.healthy(Bad(), "m")) is False
    assert asyncio.run(extract.healthy(Good(), "m")) is True


def test_no_reachable_endpoint_stops(tmp_path, monkeypatch):
    import pytest
    calls, out = setup(tmp_path, monkeypatch, REVIEWS)

    async def none():
        return []

    monkeypatch.setattr(extract, "_providers", none)
    with pytest.raises(SystemExit, match="no LLM endpoint"):
        asyncio.run(extract.run("dalat"))


def test_slots_without_rpm_do_not_wait():
    import time
    slots = extract.Slots([("c", "uit", 4)])

    async def go():
        t = time.monotonic()
        for _ in range(4):
            async with slots.take():
                pass
        return time.monotonic() - t

    assert asyncio.run(go()) < 0.05
