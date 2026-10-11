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

    @property
    def id(self) -> str:
        return self.rec["id"]

    @property
    def name(self) -> str:
        return self.rec["identity"].get("name") or self.rec["id"]
