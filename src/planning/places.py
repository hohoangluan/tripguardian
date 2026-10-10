"""Decision Output + serving records -> the places Planning can schedule, and the points a trip starts and ends at.

A confirmed place that cannot be scheduled (no record, no coordinates, no visit time) is reported as Unplaced with
its reason; nothing is filled in to make it fit.
"""

from corpus.serving import feature
from live import Unavailable

from .model import Place, Point, Unplaced
from .settings import Settings, to_min


def parse_hours(value: dict) -> dict:
    """Serving hours ({"mon": [["09:00", "21:00"]], ...}) -> {"mon": [(540, 1260)]}. A close at or before the open
    runs past midnight: 18:00-02:00 becomes (1080, 1560)."""
    out = {}
    for day, spans in value.items():
        ivs = []
        for a, b in spans:
            o, c = to_min(a), to_min(b)
            ivs.append((o, c if c > o else c + 1440))
        out[day] = sorted(ivs)
    return out


def _intersect(a: list, b: list) -> list:
    out = []
    for o1, c1 in a:
        for o2, c2 in b:
            o, c = max(o1, o2), min(c1, c2)
            if o < c:
                out.append((o, c))
    return sorted(out)


def hours_vary(hours: dict | None) -> bool:
    """True when the days of the week do not all have the same opening intervals."""
    if not hours:
        return False
    days = list(hours.values())
    return any(d != days[0] for d in days)


def windows_on(hours: dict | None, weekday: str | None) -> list | None:
    """Opening intervals on a weekday: [] = closed that day, None = not known (no hours, or the weekday is unknown
    and the open days share no common time), so the caller must not constrain on it. With the weekday unknown the
    hours every open day shares are used, so a place that opens late on some day is never planned for the morning."""
    if hours is None:
        return None
    if weekday is not None:
        return hours.get(weekday, [])
    open_days = [d for d in hours.values() if d]
    if not open_days:
        return [] if hours else None
    common = open_days[0]
    for d in open_days[1:]:
        common = _intersect(common, d)
    return common or None


def kind_of(rec: dict) -> str | None:
    """experience | meal | None (a place no plan can use)."""
    usable = rec.get("usable_as") or []
    return "experience" if "experience" in usable else "meal" if "meal" in usable else None


def cost_of(op: dict) -> int | None:
    """Per-person cost estimate in VND, from the entry fee when there is one, else the middle of the price range."""
    fee = op.get("entry_fee")
    if fee and fee.get("typical_vnd") is not None:
        return int(fee["typical_vnd"])
    price = (op.get("price_per_person") or {}).get("value")
    if price and price.get("min_vnd") is not None and price.get("max_vnd") is not None:
        return (int(price["min_vnd"]) + int(price["max_vnd"])) // 2
    return None


def day_visit(confirmed: dict, op: dict) -> dict:
    """Minutes of one visit on a day of the trip. Place Decision owns the rule (decision.day_visit: a camping
    ground's 3-18 h estimate counts the night, a day visit does not) and writes it into each confirmed place's
    `visit`; the record's own estimate is used only when the Decision Output has none."""
    v = confirmed.get("visit") or {}
    return v if all(v.get(k) is not None for k in ("short", "typical", "long")) else op["visit_minutes"]


def build_places(decision: dict, by_id: dict, cfg: Settings) -> tuple[list[Place], list[Unplaced]]:
    places, unplaced = [], []
    for c in decision["confirmed"]:
        pid = c["id"]
        name = c.get("name") or pid
        rec = by_id.get(pid)
        if rec is None:
            unplaced.append(Unplaced(pid, name, "no_record"))
            continue
        ident, op = rec["identity"], rec["operation"]
        kind = kind_of(rec)
        if kind is None:
            unplaced.append(Unplaced(pid, name, "not_plannable"))
        elif ident.get("lat") is None or ident.get("lng") is None:
            unplaced.append(Unplaced(pid, name, "no_coordinates"))
        elif not op.get("visit_minutes"):
            unplaced.append(Unplaced(pid, name, "no_visit_time"))
        else:
            hours = op.get("hours")
            places.append(Place(
                id=pid, name=ident.get("name") or name, kind=kind, role=c.get("role", "selected"),
                lat=float(ident["lat"]), lng=float(ident["lng"]), area=ident.get("area"),
                dup_group=rec.get("near_duplicate_group"),
                hours=parse_hours(hours["value"]) if hours else None,
                hours_status=hours["status"] if hours else None,
                visit=day_visit(c, op), cost_vnd=cost_of(op),
                pins=tuple(f for f in cfg.pins if (feature(rec, f) or {}).get("value") == "present"),
                flags=tuple(c.get("flags") or ()), relaxed=tuple(c.get("relaxed") or ()), rec=rec))
    return places, unplaced


def resolve_point(base: dict | None, by_id: dict, geocode) -> tuple[Point | None, str | None]:
    """A Base ({"place_id", "text", "lat"?, "lng"?}) -> a Point and None, or None and why not. A corpus place wins,
    then a point the user picked from a search (no geocoding); otherwise the text is geocoded.
    geocode(text) -> {"lat", "lng", "label", "source", "fetched_at"} | None, may raise Unavailable."""
    if not base:
        return None, "unknown"
    rec = by_id.get(base.get("place_id"))
    if rec and rec["identity"].get("lat") is not None and rec["identity"].get("lng") is not None:
        return Point(float(rec["identity"]["lat"]), float(rec["identity"]["lng"]),
                     rec["identity"].get("name") or base.get("text") or "", "corpus", None), None
    if base.get("lat") is not None and base.get("lng") is not None:
        return Point(float(base["lat"]), float(base["lng"]), base.get("text") or "", "user", None), None
    text = (base.get("text") or "").strip()
    if not text:
        return None, "unknown"
    try:
        hit = geocode(text)
    except Unavailable:
        return None, "geocode_unavailable"
    if hit is None:
        return None, "not_found"
    return Point(hit["lat"], hit["lng"], hit.get("label") or text, hit["source"], hit.get("fetched_at")), None
