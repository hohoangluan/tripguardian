"""One candidate place and what each Place Decision step found about it."""

from dataclasses import dataclass, field

from corpus.serving import feature

FIRM = ("VERIFIED", "OUTDATED")


def role_of(rec: dict) -> str | None:
    """experience | meal | None (a place no plan can use, e.g. a scooter rental)."""
    u = rec.get("usable_as") or []
    return "experience" if "experience" in u else "meal" if "meal" in u else None


def value(rec: dict, fid: str) -> str | None:
    """Top value of an ontology feature, or None without evidence."""
    f = feature(rec, fid)
    return f["value"] if f else None


def day_visit(rec: dict, cfg) -> dict | None:
    """Minutes one visit takes on a day of the trip ({short, typical, long, source}), or None without an estimate.
    A served estimate can be a stay (a night at a camping ground: 3-18 h) or a whole day: a group in
    cfg.day_visit.by_group gets that fixed visit and keeps the served range as `stay`; any other estimate is capped
    at typical_max / long_max. Cards, feasibility and Decision Output all use this, so Planning gets the same."""
    vm = rec["operation"].get("visit_minutes")
    if not vm:
        return None
    rule = cfg.day_visit
    fixed = rule["by_group"].get(rec["identity"].get("category_group"))
    if fixed:
        short, typical, long = fixed
        return {**vm, "short": short, "typical": typical, "long": long, "source": "day_visit",
                "stay": {"short": vm["short"], "long": vm["long"]}}
    typical, long = min(vm["typical"], rule["typical_max"]), min(vm["long"], rule["long_max"])
    if (typical, long) == (vm["typical"], vm["long"]):
        return vm
    return {**vm, "short": min(vm["short"], typical), "typical": typical, "long": max(long, typical),
            "source": "day_visit"}


@dataclass
class Cand:
    rec: dict
    role: str  # experience | meal
    keep: bool = False  # anchor, chosen or locked: never dropped silently
    missing: bool = False  # kept place that has no serving record
    status: str = "main"  # main | unverified | excluded
    checks: list[dict] = field(default_factory=list)  # {kind, feature, value, op, result, reason, policy}
    warnings: list[str] = field(default_factory=list)  # codes, see cards.WARNING
    fit: float = 0.0
    crowd: float = 0.0  # 0..1: how strongly authors found it crowded or a long wait (fit.crowd_evidence)
    crowd_warn: bool = False  # crowded is the place's settled value, or (trip avoids crowds) Google shows it busy
    flags: list[dict] = field(default_factory=list)  # {code, text, sid}
    km: float | None = None
    minutes: int | None = None
    center: str = ""
    parts: dict = field(default_factory=dict)
    score: float = 0.0
    stars: float | None = None  # 0..5 fit to this trip (rank.stars); None when the trip names no taste
    matches: list[tuple] = field(default_factory=list)  # (feature, value, contribution, n)

    @property
    def id(self) -> str:
        return self.rec["id"]

    @property
    def name(self) -> str:
        return self.rec["identity"].get("name") or self.rec["id"]
