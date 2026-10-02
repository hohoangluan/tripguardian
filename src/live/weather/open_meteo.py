"""Open-Meteo daily forecast: rain probability for dates within its 16-day horizon."""

from datetime import date, timedelta

from ..cache import get as cache_get
from ..cache import put as cache_put
from ..http import get_json
from ..settings import Settings

FORECAST_DAYS = 16


def in_range(dates: list[str], today: date) -> list[str]:
    last = (today + timedelta(days=FORECAST_DAYS - 1)).isoformat()
    return sorted(d for d in dates if today.isoformat() <= d <= last)


def forecast(lat: float, lng: float, dates: list[str], cfg: Settings) -> dict:
    """{"YYYY-MM-DD": {"rain_prob", "source": "open-meteo", "fetched_at"}}; dates must already be in_range."""
    if not dates:
        return {}
    start, end = min(dates), max(dates)
    payload = {"kind": "forecast", "lat": round(lat, 4), "lng": round(lng, 4), "start": start, "end": end}
    hit = cache_get("weather", payload, cfg.ttl_s["weather"])
    if hit is None:
        url = (f"{cfg.open_meteo_url}?latitude={lat:.4f}&longitude={lng:.4f}"
               f"&daily=precipitation_probability_max&timezone=Asia%2FBangkok&start_date={start}&end_date={end}")
        doc = get_json(url, cfg.user_agent, cfg.timeout_s)
        daily = doc.get("daily") or {}
        by_date = dict(zip(daily.get("time", []), daily.get("precipitation_probability_max", [])))
        hit = cache_put("weather", payload, by_date, "open-meteo")
    by_date = hit["value"]
    return {d: {"rain_prob": by_date[d] / 100 if by_date.get(d) is not None else None,
               "source": hit["source"], "fetched_at": hit["fetched_at"]} for d in dates}
