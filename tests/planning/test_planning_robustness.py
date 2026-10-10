from plan_fixtures import day_ctx, rec

from planning.robustness import lost_places, robustness
from planning.route import order_day


def one_day(end, end_node=None, **kw):
    """One place, 10 minutes from the start: travel 08:00-08:10, visit 08:10-09:10 (typical 60), then a buffer."""
    cx = day_ctx([rec("a", 1, 1, **kw)], start_node="h", end_node=end_node, end=end, extra_nodes=["h"])
    return cx, order_day(["a"], cx)


def level(end, source="osrm", **kw):
    cx, r = one_day(end, **kw)
    return robustness([cx], [r], source)


def test_a_day_with_room_to_spare_is_solid():
    rob = level(1260)
    assert (rob["level"], rob["label"], rob["breaking"]) == ("solid", "Dư giờ", [])


def test_a_day_that_survives_the_small_delays_but_not_half_an_hour_late_is_feasible():
    rob = level(570)                                 # 09:30: +15, +20% visit, +25% travel fit; +30 does not
    assert rob["level"] == "feasible" and rob["breaking"] == ["late_30"]
    assert any("Nếu xuất phát trễ 30 phút: lỡ 1 nơi" in t for t in rob["reasons"])


def test_a_day_with_no_slack_is_fragile():
    rob = level(550)                                 # the visit ends exactly at the end of the day
    assert rob["level"] == "fragile" and "late_15" in rob["breaking"]


def test_the_buffer_absorbs_a_delay_before_the_way_back():
    cx, r = one_day(580, end_node="h")               # visit 08:10-09:10, buffer, back home 09:40 = the day's end
    assert lost_places(r.order, cx) == []
    assert robustness([cx], [r], "osrm")["breaking"] == ["late_30"]       # 15 minutes late still gets home in time


def test_a_rough_matrix_never_makes_a_plan_solid():
    rob = level(1260, source="rough")
    assert rob["level"] == "feasible" and any("ước tính theo khoảng cách" in t for t in rob["reasons"])


def test_exposed_places_on_a_rainy_day_are_lost_in_the_rain_scenario():
    cx = day_ctx([rec("a", 1, 1, features={"weather_exposed": "present"}), rec("b", 1, 1)], rain=0.8)
    rob = robustness([cx], [order_day(["a", "b"], cx)], "osrm")
    rain = next(s for s in rob["scenarios"] if s["id"] == "rain")
    assert rain["lost"] == ["a"] and rob["level"] == "feasible"


def test_without_a_forecast_the_rain_scenario_is_skipped_and_said_so():
    cx = day_ctx([rec("a", 1, 1, features={"weather_exposed": "present"})])
    rob = robustness([cx], [order_day(["a"], cx)], "osrm")
    assert rob["skipped"] == ["rain"] and "rain" not in [s["id"] for s in rob["scenarios"]]
    assert any("Chưa có dự báo thời tiết" in t for t in rob["reasons"])


def test_an_empty_day_loses_nothing_and_the_answer_does_not_change_between_runs():
    cx = day_ctx([rec("a", 1, 1)])
    empty = order_day([], cx)
    assert robustness([cx], [empty], "osrm")["level"] == "solid"
    cx2, r2 = one_day(570)
    assert robustness([cx2], [r2], "osrm") == robustness([cx2], [r2], "osrm")


def test_a_plan_that_never_travels_is_not_capped_by_a_rough_matrix():
    cx = day_ctx([rec("a", 1, 1)])                       # no start or end point: a visit and nothing else
    assert robustness([cx], [order_day(["a"], cx)], "rough")["level"] == "solid"
