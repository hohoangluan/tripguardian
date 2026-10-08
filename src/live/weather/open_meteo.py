"""Open-Meteo daily forecast within its 16-day horizon: rain probability and amount, wind gusts, thunderstorm."""

from datetime import date, timedelta

from ..cache import get as cache_get
from ..cache import put as cache_put
from ..http import get_json
from ..settings import Settings

FORECAST_DAYS = 16
THUNDERSTORM = (95, 96, 99)   # WMO weather codes
DAILY = "precipitation_probability_max,precipitation_sum,wind_gusts_10m_max,weather_code"


def in_range(dates: list[str], today: date) -> list[str]:
    last = (today + timedelta(days=FORECAST_DAYS - 1)).isoformat()
    return sorted(d for d in dates if today.isoformat() <= d <= last)


def forecast(lat: float, lng: float, dates: list[str], cfg: Settings) -> dict:
    """{"YYYY-MM-DD": {"rain_prob", "rain_mm", "gust_kmh", "storm", "source": "open-meteo", "fetched_at"}}; dates must
    already be in_range. A figure Open-Meteo did not give is None; nothing is filled in."""
    if not dates:
        return {}
    start, end = min(dates), max(dates)
    payload = {"kind": "forecast2", "lat": round(lat, 4), "lng": round(lng, 4), "start": start, "end": end}
    hit = cache_get("weather", payload, cfg.ttl_s["weather"])
    if hit is None:
        url = (f"{cfg.open_meteo_url}?latitude={lat:.4f}&longitude={lng:.4f}"
               f"&daily={DAILY}&timezone=Asia%2FBangkok&start_date={start}&end_date={end}")
        doc = get_json(url, cfg.user_agent, cfg.timeout_s)
        daily = doc.get("daily") or {}
        col = {k: dict(zip(daily.get("time", []), daily.get(name) or []))
               for k, name in (("prob", "precipitation_probability_max"), ("mm", "precipitation_sum"),
                               ("gust", "wind_gusts_10m_max"), ("code", "weather_code"))}
        hit = cache_put("weather", payload, {d: {k: c.get(d) for k, c in col.items()} for d in daily.get("time", [])},
                        "open-meteo")
    out = {}
    for d in dates:
        v = (hit["value"] or {}).get(d) or {}
        out[d] = {"rain_prob": v["prob"] / 100 if v.get("prob") is not None else None, "rain_mm": v.get("mm"),
                  "gust_kmh": v.get("gust"), "storm": v["code"] in THUNDERSTORM if v.get("code") is not None else None,
                  "source": hit["source"], "fetched_at": hit["fetched_at"]}
    return out
