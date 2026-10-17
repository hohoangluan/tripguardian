"""Logistics lookups through Planning (the owner of Live Context): geo, lodging by name. Every source is faked: no
network."""

from plan_fixtures import rec

import live
from planning.logistics import Logistics, matches

LIVE = live.load_settings()


def stay(pid, name, lat=11.94, lng=108.44, voices=10):
    r = rec(pid, lat, lng, group="stay", name=name)
    r["identity"]["address"] = "Phường 1, Đà Lạt"
    r["provenance"] = {"voices": voices, "rating_trend": {"recent_mean": 4.6}}
    return r


def geo_rows(q):
    return [{"text": "Ana Mandara Villas", "address": "Lê Lai", "province": "Lâm Đồng", "lat": 11.93, "lng": 108.42,
             "source": "photon", "fetched_at": "x"},
            {"text": f"{q} street", "address": "", "province": "Lâm Đồng", "lat": 11.9, "lng": 108.4,
             "source": "photon", "fetched_at": "x"}]


def make(**kw):
    records = [stay("s1", "Ana Mandara Villas Dalat"), stay("s3", "Ana Homestay", voices=40), stay("s2", "Dalat Palace"),
               rec("c1", 11.9, 108.4, name="Ana Cafe")]
    return Logistics(records, LIVE, geosearch_fn=kw.get("geo", geo_rows))


def test_a_typed_name_matches_word_starts_without_accents():
    assert matches("ana man", "Ana Mandara Villas") and matches("da lat", "Đà Lạt Palace")
    assert not matches("mandara ana x", "Ana Mandara")


def test_lodging_suggest_lists_only_our_own_most_reviewed_first_never_geosearch_addresses():
    rows = make().lodging_suggest("ana")
    assert [(r["kind"], r.get("id"), r["text"]) for r in rows] == [
        ("corpus", "s3", "Ana Homestay"), ("corpus", "s1", "Ana Mandara Villas Dalat")]
    assert rows[0]["rating"] == 4.6 and rows[1]["address"] == "Phường 1, Đà Lạt"
    assert make().lodging_suggest("a") == []
    assert all(r["text"] != "Ana Cafe" for r in rows)  # not a lodging


def test_a_failing_geosearch_gives_no_origin_rows():
    def down(q):
        raise live.Unavailable("photon and nominatim down")

    assert make(geo=down).geo("Bến Thành") == []


def test_lodging_suggest_top_gives_the_best_stays_as_cards_without_a_query():
    lg = make()
    rows = lg.lodging_suggest("", top=5)
    ids = [r["id"] for r in rows]
    assert set(ids) <= {"s1", "s2", "s3"} and all(r["kind"] == "corpus" for r in rows)
    assert all({"price_vnd", "category", "area", "reviews", "lat", "lng"} <= set(r) for r in rows)
    assert lg.lodging_suggest("", top=0) == [] and len(lg.lodging_suggest("", top=1)) <= 1
