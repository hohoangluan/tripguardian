from bench.latency import pct, queries, replicate, replicate_intel, tools_bench


def rec(i, area="area-1", dup=None):
    return {"id": f"P{i}", "identity": {"name": f"N{i}", "lat": 11.9, "lng": 108.4, "area": area},
            "near_duplicate_group": dup, "usable_as": ["experience"]}


def test_pct_reports_ms():
    p = pct([0.001, 0.002, 0.003, 0.004])
    assert p["n"] == 4 and p["max"] == 4.0 and p["p50"] in (2.0, 3.0)


def test_replicate_keeps_copies_apart():
    out = replicate([rec(1, dup=3), rec(2)], 3)
    assert len(out) == 6
    assert len({r["id"] for r in out}) == 6
    assert out[0]["id"] == "P1" and out[2]["id"] == "P1~1"
    assert out[2]["near_duplicate_group"] != out[0]["near_duplicate_group"]
    assert out[2]["identity"]["area"] != out[0]["identity"]["area"]
    assert out[2]["identity"]["lng"] > out[0]["identity"]["lng"]
    assert replicate([rec(1)], 1)[0] is not None


def test_tools_bench_times_search_places_on_a_catalog_from_a_region():
    import sys
    from pathlib import Path

    sys.path.insert(0, str(Path(__file__).parents[1] / "decision"))
    from fixtures import srec

    from corpus.snapshot import Region
    from trip import Catalog

    recs = [srec(f"P{i}", name=f"Quán cà phê thử nghiệm số {i}") for i in range(3)]
    intel = [{"place_fid": r["id"], "place_name": r["identity"]["name"], "identity": {"category": "Quán cà phê"},
              "estimates": {}, "operation": {"hours": None}, "features": {}} for r in recs]
    catalog = Catalog.from_snapshot(Region.from_records(replicate(recs, 2), replicate_intel(intel, 2)), n_min=1)
    assert len(catalog.places) == 6 and catalog.by_id["P1~1"].name == recs[1]["identity"]["name"]
    out = tools_bench(catalog, queries(recs)[:2])
    assert out["search_places"]["n"] == 40
