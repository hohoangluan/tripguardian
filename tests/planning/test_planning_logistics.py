"""Logistics lookups through Planning (the owner of Live Context): geo, lodging by name, transit with a background
crawl. Every source is faked: no network."""

import threading

import pytest
from plan_fixtures import rec

import live
from planning.logistics import Logistics, matches

LIVE = live.load_settings()
FLIGHT = {"mode": "plane", "carrier": "Vietjet", "depart_at": "2026-11-12T06:30", "arrive_at": "2026-11-12T07:25",
          "from_point": "Tân Sơn Nhất", "to_point": "Liên Khương", "price_vnd": 994781, "source": "google_flights",
          "fetched_at": "2026-10-08T00:00:00+00:00"}
PLANE = {"mode": "plane", "from": "SGN", "to": "DLI", "date": "2026-11-12"}


def stay(pid, name, lat=11.94, lng=108.44):
    r = rec(pid, lat, lng, group="stay", name=name)
    r["identity"]["address"] = "Phường 1, Đà Lạt"
    return r


def geo_rows(q):
    return [{"text": "Ana Mandara Villas", "address": "Lê Lai", "province": "Lâm Đồng", "lat": 11.93, "lng": 108.42,
             "source": "photon", "fetched_at": "x"},
            {"text": f"{q} street", "address": "", "province": "Lâm Đồng", "lat": 11.9, "lng": 108.4,
             "source": "photon", "fetched_at": "x"}]


def make(**kw):
    records = [stay("s1", "Ana Mandara Villas Dalat"), stay("s2", "Dalat Palace"), rec("c1", 11.9, 108.4, name="Ana Cafe")]
    seen = [{"id": "l1", "name": "Ana Homestay", "lat": 11.95, "lng": 108.45, "rating": 4.7, "address": None},
            {"id": "s1", "name": "Ana Mandara Villas Dalat", "lat": 11.94, "lng": 108.44, "rating": 4.6}]
    return Logistics(records, LIVE, geosearch_fn=kw.get("geo", geo_rows), seen_fn=lambda: seen,
                     flights_fn=kw.get("flights"), buses_fn=kw.get("buses"), background=kw.get("background", False),
                     listed_fn=kw.get("listed", lambda: []))


def test_a_typed_name_matches_word_starts_without_accents():
    assert matches("ana man", "Ana Mandara Villas") and matches("da lat", "Đà Lạt Palace")
    assert not matches("mandara ana x", "Ana Mandara")


def test_lodging_suggest_lists_our_own_first_then_addresses_without_duplicates():
    rows = make().lodging_suggest("ana")
    assert [(r["kind"], r.get("id"), r["text"]) for r in rows] == [
        ("corpus", "s1", "Ana Mandara Villas Dalat"), ("live", "l1", "Ana Homestay"),
        ("address", None, "Ana Mandara Villas"), ("address", None, "ana street")]
    assert rows[1]["rating"] == 4.7 and rows[0]["address"] == "Phường 1, Đà Lạt"
    assert make().lodging_suggest("a") == []
    assert all(r["text"] != "Ana Cafe" for r in rows)  # not a lodging


def test_a_failing_geosearch_still_returns_our_own_rows():
    def down(q):
        raise live.Unavailable("photon and nominatim down")

    rows = make(geo=down).lodging_suggest("ana")
    assert [r["kind"] for r in rows] == ["corpus", "live"]
    assert make(geo=down).geo("Bến Thành") == []


def test_a_cached_route_is_ready_at_once():
    calls = []

    def flights(a, b, day, fetch):
        calls.append(fetch)
        return [FLIGHT]

    out = make(flights=flights).transit(PLANE)
    assert out["status"] == "ready" and out["trips"] == [FLIGHT] and calls == [False]
    assert "SGN%20to%20DLI%20on%202026-11-12" in out["book_url"]


def test_a_miss_crawls_once_in_the_background_then_is_ready():
    gate, cache, fetches = threading.Event(), {}, []

    def flights(a, b, day, fetch):
        if not fetch:
            return cache.get((a, b, day))
        fetches.append(1)
        gate.wait(2)
        cache[(a, b, day)] = [FLIGHT]
        return cache[(a, b, day)]

    lg = make(flights=flights, background=True)
    assert lg.transit(PLANE)["status"] == "pending"
    assert lg.transit(PLANE)["status"] == "pending"  # a second poll does not start a second crawl
    gate.set()
    for _ in range(100):
        if lg.transit(PLANE)["status"] == "ready":
            break
        threading.Event().wait(0.02)
    assert lg.transit(PLANE)["trips"] == [FLIGHT] and len(fetches) == 1


def test_a_failed_crawl_is_unavailable_with_the_booking_page_and_no_trip():
    def flights(a, b, day, fetch):
        if fetch:
            raise live.Unavailable("captcha")
        return None

    lg = make(flights=flights)
    out = lg.transit(PLANE)
    assert out["status"] == "unavailable" and out["trips"] == [] and out["book_url"]
    assert lg.transit(PLANE)["status"] == "unavailable"  # not retried by every poll


def test_a_coach_takes_the_origin_point_when_given_and_knows_its_direction():
    seen = []

    def buses(origin, day, way, fetch):
        seen.append((origin, way))
        return []

    lg = make(buses=buses)
    inbound = lg.transit({"mode": "bus", "from": "Hồ Chí Minh", "to": "Lâm Đồng", "date": "2026-11-12",
                          "lat": "10.77", "lng": "106.70"})
    lg.transit({"mode": "bus", "from": "Lâm Đồng", "to": "Hồ Chí Minh", "date": "2026-11-14"})
    assert seen == [((10.77, 106.70), "inbound"), ("Hồ Chí Minh", "outbound")]
    assert inbound["status"] == "ready" and "-129t23991.html?date=12-11-2026" in inbound["book_url"]


def test_a_province_with_no_coach_region_is_unavailable_without_a_crawl():
    def buses(origin, day, way, fetch):
        assert not fetch, "no crawl"
        raise live.Unavailable(f"vexere: no coach region named {origin!r}")  # what live.buses says

    lg = make(buses=buses)
    out = lg.transit({"mode": "bus", "from": "Atlantis", "to": "Lâm Đồng", "date": "2026-11-12"})
    assert out == {"status": "unavailable", "trips": [], "book_url": None}


@pytest.mark.parametrize("params", [{**PLANE, "mode": "boat"}, {**PLANE, "date": "12/11"}, {**PLANE, "from": "Sài Gòn"},
                                    {**PLANE, "to": ""}])
def test_malformed_transit_params_are_refused(params):
    with pytest.raises(ValueError):
        make().transit(params)


CRAWLED = [{"id": "f1", "name": "Khách Sạn Dalat Palace", "lat": 11.937, "lng": 108.438, "rating": 4.6, "reviews": 900,
            "address": "2 Trần Phú"},
           {"id": "f2", "name": "Dalat Palace Golf Club Villa", "lat": 11.95, "lng": 108.45, "rating": 4.1,
            "reviews": 40, "address": None},
           {"id": "f3", "name": "Huong Anh Dalat Palace", "lat": 11.93, "lng": 108.43, "rating": 4.0, "reviews": 30,
            "address": None}]


def test_a_hotel_typed_in_full_is_found_in_the_crawled_lodging_list_without_the_network():
    def offline(q):
        raise live.Unavailable("no network in this test")

    lg = Logistics([rec("m", 11.9425, 108.4371, name="Chợ Đà Lạt")], LIVE, geosearch_fn=offline,
                   seen_fn=lambda: [], listed_fn=lambda: CRAWLED, background=False)
    hit = lg.resolve("Dalat Palace Heritage Hotel")         # OSM has no such name; the crawled list does
    assert (hit["lat"], hit["lng"], hit["label"]) == (11.937, 108.438, "Khách Sạn Dalat Palace")
    near = lg.resolve("homestay gần chợ Đà Lạt")              # no lodging named so: the market it is near
    assert (near["lat"], near["lng"], near["label"]) == (11.9425, 108.4371, "Chợ Đà Lạt")
    assert lg.resolve("homestay") is None and lg.resolve("Đà Lạt") is None   # names nothing: geocoding decides
    rows = lg.lodging_suggest("dalat palace her")
    assert rows[0]["id"] == "f1" and {r["kind"] for r in rows} == {"live"}


# ---------- /rentals ----------

HUB = {"bus": (11.9276, 108.4446), "plane": (11.7502, 108.3672)}


def shop(pid, lat, lng, name=None, hours="open"):
    r = rec(pid, lat, lng, group="rental", name=name or pid, hours=hours)
    r["identity"]["address"] = "Đà Lạt"
    return r


def rentals_of(*shops):
    return Logistics([*shops, rec("c1", 11.94, 108.45, name="Cafe")], LIVE, background=False)


def test_rentals_near_the_bus_station_are_nearest_first_and_only_rental_places():
    out = rentals_of(shop("far", 11.96, 108.44), shop("near", 11.9280, 108.4450), shop("mid", 11.9300, 108.4470)).rentals(
        {"mode": "bus"})
    assert out["status"] == "ready" and out["hub"]["text"] == "Bến xe Liên tỉnh Đà Lạt"
    assert [p["id"] for p in out["points"]] == ["near", "mid", "far"]
    assert out["points"][0]["km"] < out["points"][1]["km"] and out["points"][0]["near_hub"]
    assert not out["points"][2]["near_hub"] and "Cafe" not in {p["name"] for p in out["points"]}
    assert out["points"][0]["maps_url"].startswith("https://www.google.com/maps/search/")


def test_no_rental_near_the_airport_says_so_and_lists_the_nearest_in_town_with_their_distance():
    out = rentals_of(shop("town", 11.9500, 108.4400)).rentals({"mode": "plane"})
    assert out["status"] == "ready" and out["hub"]["text"] == "Sân bay Liên Khương"
    (p,) = out["points"]
    assert not p["near_hub"] and p["km"] > 15


def test_a_corpus_with_no_rental_place_gives_none_not_a_made_up_shop():
    out = rentals_of().rentals({"mode": "bus"})
    assert out == {"status": "none", "hub": out["hub"], "points": []}


def test_rentals_can_be_measured_from_a_picked_point_and_reject_bad_input():
    out = rentals_of(shop("a", 11.9500, 108.4400), shop("b", 11.9700, 108.4600)).rentals(
        {"mode": "bus", "lat": "11.9701", "lng": "108.4601"})
    assert [p["id"] for p in out["points"]] == ["b", "a"]
    with pytest.raises(ValueError):
        rentals_of().rentals({"mode": "car"})
    with pytest.raises(ValueError):
        rentals_of().rentals({"mode": "bus", "lat": "x", "lng": "1"})


def test_an_approximate_address_keeps_its_flag_and_kind_in_the_lodging_list():
    def geo(q):
        return [{"text": q, "address": "Hẻm 55/13 Đường 18B, Bình Hưng Hòa", "province": "Thành phố Hồ Chí Minh",
                 "lat": 10.75, "lng": 106.59, "kind": "street", "approx": True, "source": "photon", "fetched_at": "x"}]

    (row,) = make(geo=geo).lodging_suggest("55/13/19 đường 18b")
    assert row["kind"] == "address" and row["approx"] is True and row["geo_kind"] == "street"
    assert (row["text"], row["lat"], row["lng"]) == ("55/13/19 đường 18b", 10.75, 106.59)
