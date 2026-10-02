"""OSRM on this machine: a duration matrix and the shape of one route.

The matrix is cached mode-free (roads do not care about the vehicle); the mode factor is applied on the way out.
"""

from ..cache import get as cache_get
from ..cache import put as cache_put
from ..http import Unavailable, get_json
from ..settings import Settings

Point = tuple[float, float]  # (lat, lng)


def _coords(points: list[Point]) -> str:
    return ";".join(f"{lng:.6f},{lat:.6f}" for lat, lng in points)  # OSRM reads lng,lat


def _factor(mode: str | None, cfg: Settings) -> float:
    return float(cfg.mode_factor.get(mode or "motorbike", 1.0))


def _rounded(points: list[Point]) -> list[list[float]]:
    return [[round(lat, 6), round(lng, 6)] for lat, lng in points]


def travel_matrix(points: list[Point], mode: str | None, cfg: Settings) -> dict:
    """{"minutes": [[int | None]], "source", "fetched_at"}. None is a pair OSRM found no road for."""
    if len(points) < 2:
        raise ValueError("travel_matrix needs at least two points")
    payload = {"kind": "table", "profile": cfg.osrm_profile, "points": _rounded(points)}
    hit = cache_get("osrm", payload, cfg.ttl_s["osrm"])
    if hit is None:
        url = f"{cfg.osrm_url}/table/v1/{cfg.osrm_profile}/{_coords(points)}?annotations=duration"
        doc = get_json(url, cfg.user_agent, cfg.timeout_s)
        if doc.get("code") != "Ok" or not doc.get("durations"):
            raise Unavailable(f"osrm table: code={doc.get('code')!r}")
        hit = cache_put("osrm", payload, doc["durations"], "osrm")
    f, secs = _factor(mode, cfg), hit["value"]
    minutes = [[0 if i == j else (None if secs[i][j] is None else max(1, round(secs[i][j] * f / 60)))
                for j in range(len(points))] for i in range(len(points))]
    return {"minutes": minutes, "source": hit["source"], "fetched_at": hit["fetched_at"]}
