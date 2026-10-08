"""Weather facts per day: Open-Meteo within its forecast horizon, config/climate.yaml (rain probability only) beyond it."""

from datetime import date as _date

from ..settings import Settings
from .climate import climate
from .open_meteo import forecast, in_range

__all__ = ["weather"]


def weather(lat: float, lng: float, dates: list[str], cfg: Settings, today_fn=_date.today) -> dict:
    """{"YYYY-MM-DD": {"rain_prob": 0..1 | None, "source": "open-meteo" | "climate", "fetched_at", and from Open-Meteo
    also "rain_mm", "gust_kmh", "storm"}}.

    May raise live.Unavailable when a date inside the forecast horizon cannot be fetched; dates beyond it never
    touch the network. An empty dates list needs neither.
    """
    if not dates:
        return {}
    near = in_range(dates, today_fn())
    far = sorted(set(dates) - set(near))
    out = forecast(lat, lng, near, cfg) if near else {}
    out.update(climate(far) if far else {})
    return out
