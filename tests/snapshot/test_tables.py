import orjson
import pyarrow as pa

from fixtures import feat, fit_entry, srec
from gen import records

from corpus.snapshot import tables
from decision.model import role_of
from decision.rank import _price_norm, conf
from decision.settings import default
from requirements import activity_for, category_for

CFG = default()


def by_id(t: pa.Table) -> dict:
    return {r["id"]: r for r in t.to_pylist()}


def test_places_columns_match_the_per_place_functions():
    for seed in range(5):
        recs = records(seed)
        p = by_id(tables(recs)["places"])
        for r in recs:
            row = p[r["id"]]
            role = role_of(r)
            act = activity_for(r, None, role)
            if role and act == "eating":
                role = "meal"
            elif role and act:
                role = "experience"
            assert row["role"] == role
            assert row["activity"] == (activity_for(r, None, role) if role else activity_for(r, None, None))
            assert row["category_for"] == category_for(r)
            price = r["operation"].get("price_per_person")
            assert (row["price_mid_vnd"] is None) == (not price)
            if price:
                assert min(1.0, row["price_mid_vnd"] / CFG.price_ref_vnd) == _price_norm(r, CFG)


def test_features_rows_carry_reference_conf_and_fit_rows():
    r = srec("A", features={"scenic_view": feat("present", n=2, agreement=0.8, status="OUTDATED")},
             details={"fit": {"kids": fit_entry("bad")}})
    f = tables([r])["features"].to_pylist()
    sv = next(x for x in f if x["fid"] == "scenic_view")
    assert sv["conf"] == conf(r["experience"]["scenic_view"]) and sv["dist_values"] == ["present"]
    kid = next(x for x in f if x["fid"] == "fit.kids")
    assert kid["value"] == "bad" and kid["conf"] is None


def test_feature_ctx_keeps_first_max_and_skips_empty():
    v = feat("present", by_context={"time_of_day=morning": {"absent": 2, "present": 2}, "day_type=weekend": {}})
    r = srec("A", features={"scenic_view": v})
    ctx = tables([r])["feature_ctx"].to_pylist()
    assert ctx == [{"place_id": "A", "fid": "scenic_view", "ctx_key": "time_of_day=morning", "top": "absent"}]


def test_open_mask_and_crowd_columns():
    r = srec("A", hours={"mon": [["08:00", "17:00"]], "tue": []},
             crowd_by_time={"weekday": {"morning": 90}, "peak": {"day": "mon", "hour": 9, "pct": 100}})
    row = tables([r])["places"].to_pylist()[0]
    assert row["open_mask"] == 0b0000001 and row["has_hours_value"] is True
    assert row["crowd_weekday_morning"] == 90 and row["crowd_weekend_noon"] is None and row["has_crowd"] is True


def test_records_table_roundtrips_json():
    recs = records(1)
    t = by_id(tables(recs)["records"])
    for r in recs:
        assert orjson.loads(t[r["id"]]["json"]) == orjson.loads(orjson.dumps(r))


def test_tables_tolerate_missing_fields():
    r = srec("A", hours=None, lat=None)
    r.pop("details", None)
    r["operation"].pop("crowd_by_time")
    out = tables([r])
    row = out["places"].to_pylist()[0]
    assert row["lat"] is None and row["hours_status"] is None and row["has_crowd"] is False


def test_conf_of_a_derived_feature_without_agreement_is_zero():
    f = feat("high", n=0)
    f["confidence"] = {"independent_sources": 0, "agreement": None, "freshness_days": None, "source_types": []}
    r = srec("A", features={"long_walk": f})
    assert tables([r])["features"].to_pylist()[0]["conf"] == 0.0
