"""Travel times between the points of one trip: one OSRM matrix, short legs walked, a labelled rough fallback.

Every number here is an estimate. When OSRM is down the whole matrix is rough (source "rough"); a single pair OSRM
has no road for is rough too and is counted in rough_pairs.
"""

import math
from dataclasses import dataclass, field

from live import Unavailable

from .settings import Settings


def km(a: tuple[float, float], b: tuple[float, float]) -> float:
    la1, lo1, la2, lo2 = map(math.radians, (*a, *b))
    h = math.sin((la2 - la1) / 2) ** 2 + math.cos(la1) * math.cos(la2) * math.sin((lo2 - lo1) / 2) ** 2
    return 2 * 6371 * math.asin(math.sqrt(h))


@dataclass
class Travel:
    ids: list[str]
    legs: list[list[tuple[int, str]]]   # legs[i][j] = (minutes, mode)
    source: str                         # osrm | rough
    fetched_at: str | None
    rough_pairs: int = 0
    index: dict = field(init=False)

    def __post_init__(self):
        self.index = {pid: i for i, pid in enumerate(self.ids)}

    def leg(self, a: str, b: str) -> tuple[int, str]:
        """(minutes, mode) from node a to node b; staying put costs nothing."""
        if a == b:
            return 0, "none"
        return self.legs[self.index[a]][self.index[b]]


def rough_minutes(distance_km: float, mobility: str | None, cfg: Settings) -> int:
    speed = cfg.rough_speed_kmh[mobility or "motorbike"]
    return max(1, round(distance_km * cfg.road_factor / speed * 60))


def walk_minutes(distance_km: float, cfg: Settings) -> int:
    return max(1, math.ceil(distance_km * cfg.road_factor / cfg.walk_kmh * 60))


def build_travel(nodes: dict, mobility: str | None, cfg: Settings, live_cfg, matrix_fn,
                 arrive_extra: dict | None = None) -> Travel:
    """nodes: id -> (lat, lng). matrix_fn(points, mode, live_cfg) is live.travel_matrix. arrive_extra: node id -> minutes
    it costs to arrive there by vehicle (parking); a walked leg never pays it. A trip with no vehicle ("walk") walks
    every leg: source "walk", the matrix is not asked."""
    ids = list(nodes)
    points = [nodes[i] for i in ids]
    arrive_extra = arrive_extra or {}
    source, fetched_at, minutes = "rough", None, None
    walk_km = cfg.car_walk_km if mobility == "car" else cfg.walk_km
    if mobility == "walk":
        source = "walk"
    elif len(points) >= 2:
        try:
            m = matrix_fn(points, mobility, live_cfg)
            source, fetched_at, minutes = m["source"], m["fetched_at"], m["minutes"]
        except Unavailable:
            pass
    rough_pairs = 0
    legs = []
    for i, a in enumerate(points):
        row = []
        for j, b in enumerate(points):
            d = km(a, b)
            if i == j:
                row.append((0, "none"))
            elif mobility == "walk" or d < walk_km:
                row.append((walk_minutes(d, cfg), "walk"))
            elif minutes is not None and minutes[i][j] is not None:
                row.append((minutes[i][j] + arrive_extra.get(ids[j], 0), mobility or "motorbike"))
            else:
                row.append((rough_minutes(d, mobility, cfg) + arrive_extra.get(ids[j], 0), mobility or "motorbike"))
                rough_pairs += 1 if minutes is not None else 0
        legs.append(row)
    return Travel(ids, legs, source, fetched_at, rough_pairs)
