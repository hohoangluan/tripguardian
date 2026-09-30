import asyncio
import json

from corpus.crawl.gmaps import qc

CFG = {"area": [11.78, 108.30, 12.12, 108.66], "gmaps": {"min_reviews_per_place": 30}}
PLACE = {"fid": "0x1:0x2", "name": "Thác Datanla", "category": "Điểm thu hút khách du lịch", "address": "Đèo Prenn, Đà Lạt",
         "rating": "4,4 sao", "review_count": "25.363 bài đánh giá", "lat": 11.90, "lng": 108.45, "hours": ["Thứ Hai 07:00–17:00"],
         "fetched_at": "2026-09-29T07:00:00+00:00"}


def _reviews(n, text="Đẹp lắm"):
    return [{"review_id": f"r{i}", "text": text, "rating": "5 sao", "published_text": "1 tuần trước"} for i in range(n)]


def test_checks_clean_place_has_no_issues():
    assert qc.checks(PLACE, _reviews(30), CFG) == []


def test_checks_flag_short_truncated_missing_and_outside():
    place = {**PLACE, "address": None, "lat": 10.93, "lng": 106.77}
    issues = qc.checks(place, _reviews(5, "Quán ngon nhưng …"), CFG)
    assert "missing:address" in issues and "out_of_area" in issues
    assert "reviews_short:5/30" in issues and "truncated_reviews:5" in issues


def test_checks_small_place_needs_only_its_reviews():
    assert qc.checks({**PLACE, "review_count": "4 bài đánh giá"}, _reviews(4), CFG) == []


def test_run_writes_one_result_per_place_and_skips_checked(tmp_path, monkeypatch):
    monkeypatch.setenv("DATA_DIR", str(tmp_path))
    monkeypatch.setattr(qc, "load_config", lambda city: ("Đà Lạt", CFG))
    d = tmp_path / "gmaps" / "places" / "0x1_0x2"
    d.mkdir(parents=True)
    (d / "place.json").write_text(json.dumps(PLACE, ensure_ascii=False), encoding="utf-8")
    (d / "reviews.json").write_text(json.dumps(_reviews(30), ensure_ascii=False), encoding="utf-8")
    calls = []

    async def judge(client, model, place, reviews, city):
        calls.append(place["fid"])
        return {"tourism_relevant": True, "relevance_reason": "waterfall", "in_city": True, "category_ok": True,
                "bad_reviews": [], "field_issues": [], "verdict": "ok"}

    monkeypatch.setattr(qc, "judge", judge)
    monkeypatch.setattr(qc, "_client", lambda: (None, "gemma-test"))
    summary = asyncio.run(qc.run("dalat"))
    out = json.loads((tmp_path / "gmaps" / "qc" / "0x1_0x2.json").read_text(encoding="utf-8"))
    assert out["checks"] == [] and out["llm"]["verdict"] == "ok" and out["model"] == "gemma-test"
    assert out["fetched_at"] == PLACE["fetched_at"] and summary["places"] == 1 and summary["verdict"] == {"ok": 1}
    asyncio.run(qc.run("dalat"))
    assert calls == ["0x1:0x2"]  # unchanged place is not judged again
