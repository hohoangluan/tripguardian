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


def known_for(rec: dict) -> dict | None:
    """The one thing the place is known for ({text, n}), from its serving details; None without it."""
    h = ((rec.get("details") or {}).get("known_for") or {}).get("headline")
    return {"text": h["text"], "n": h["n"]} if h else None


def cost_total(rec: dict) -> dict | None:
    """What a visit costs one person ({base, with_extras} in VND), from its serving details; None without it."""
    t = ((rec.get("details") or {}).get("cost") or {}).get("total_vnd")
    return {"base": t["base"], "with_extras": t["with_extras"]} if t else None


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
    flags: list[dict] = field(default_factory=list)  # {code, text, sid}
    km: float | None = None
    minutes: int | None = None
    center: str = ""
    parts: dict = field(default_factory=dict)
    score: float = 0.0
    matches: list[tuple] = field(default_factory=list)  # (feature, value, contribution, n)
    wishes: list[tuple] = field(default_factory=list)  # (key, kind, label, contribution): decision.wishes.lift hits
    dish_source: dict = field(default_factory=dict)  # dish -> best menu source; a Cand outlives runs while its table does

    @property
    def id(self) -> str:
        return self.rec["id"]

    @property
    def name(self) -> str:
        return self.rec["identity"].get("name") or self.rec["id"]
