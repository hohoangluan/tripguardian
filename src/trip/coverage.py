"""How many candidates the corpus can actually check for a hard filter (docs/TRIP_UNDERSTANDING.md §5.4)."""

from collections import Counter
from dataclasses import dataclass
from typing import Iterable, Literal

from .catalog import Candidate
from .state import Hard

Verdict = Literal["pass", "fail", "unknown"]


def verdict(c: Candidate, h: Hard) -> Verdict:
    v = c.value(h.feature)
    if v is None:
        return "unknown"
    return "pass" if (v == h.value) == (h.op == "eq") else "fail"


@dataclass(frozen=True)
class Coverage:
    passed: int
    failed: int
    unknown: int
    level: Literal["enough", "thin", "none"]


def coverage(h: Hard, places: Iterable[Candidate], enough: int) -> Coverage:
    n = Counter(verdict(c, h) for c in places)
    p = n["pass"]
    return Coverage(p, n["fail"], n["unknown"], "enough" if p >= enough else "thin" if p else "none")


def admissible(c: Candidate, hard: Iterable[Hard]) -> bool:
    """Fail-closed: a failing place is out; an unknown one is out unless the user chose to see it flagged."""
    for h in hard:
        v = verdict(c, h)
        if v == "fail" or (v == "unknown" and h.unknown_policy != "flag"):
            return False
    return True
