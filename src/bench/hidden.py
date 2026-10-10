"""Hidden trips: the whole truth of one simulated traveller, in Trip State terms (docs/P2_TRIP_UNDERSTANDING.md §16)."""

from datetime import date
from pathlib import Path
from typing import Literal

import yaml
from pydantic import BaseModel, ConfigDict, Field, model_validator

ROOT = Path(__file__).resolve().parents[2]
TRIPS = ROOT / "config" / "bench_trips.yaml"

Who = Literal["solo", "partner", "friends", "kids", "parents"]
Vehicle = Literal["motorbike", "car"]
SignalKind = Literal["knee", "elderly", "kids", "wheelchair", "vegetarian", "motion_sick", "height"]
Effort = Literal["steep", "walk", "both", "none"]
EFFORT_SIGNALS = ("knee", "elderly", "kids", "wheelchair")
OPTIONAL = ("dates", "base", "purpose", "pace", "crowd_tolerance", "novelty", "budget_vnd")
EFFORT_HARD = {"steep": [("steep_or_stairs", "ne", "present")], "walk": [("long_walk", "ne", "present")],
               "both": [("steep_or_stairs", "ne", "present"), ("long_walk", "ne", "present")], "none": []}


class Strict(BaseModel):
    model_config = ConfigDict(extra="forbid")


class Dates(Strict):
    kind: Literal["start_date", "month", "undecided"]
    start_date: date | None = None
    month: int | None = Field(None, ge=1, le=12)

    @model_validator(mode="after")
    def _one(self):
        if (self.kind == "start_date") != (self.start_date is not None) or (self.kind == "month") != (self.month is not None):
            raise ValueError(f"dates {self.kind} needs exactly its own value")
        return self


class HardRule(Strict):
    feature: str
    op: Literal["ne", "eq"]
    value: str


class AnchorTruth(Strict):
    name: str
    place_id: str
    priority: Literal["must", "want"]


class HiddenTrip(Strict):
    id: str
    experience: Literal["first", "returning"]
    days: int = Field(ge=1, le=7)
    dates: Dates
    companions: list[Who] = Field(min_length=1)
    people: int = Field(ge=1, le=20)
    mobility: Vehicle
    base: str | None = None
    purpose: Literal["relax", "bond", "photo", "food_culture", "nature", "explore", "adventure"] | None = None
    pace: Literal["slow", "normal", "packed"] | None = None
    crowd_tolerance: Literal["avoid", "ok_if_worth", "fine"] | None = None
    novelty: Literal["familiar", "new", "mix"] | None = None
    budget_vnd: int | None = None          # per person per day
    loves: list[str] = Field(min_length=1, max_length=3)   # soft keys feature=value
    avoids: list[str] = Field(default_factory=list, max_length=2)
    signals: list[SignalKind] = Field(default_factory=list)
    effort: Effort | None = None           # the c_effort answer; None when no effort signal
    hard: list[HardRule] = Field(default_factory=list)
    anchors: list[AnchorTruth] = Field(default_factory=list, max_length=2)
    indifferent: list[str] = Field(default_factory=list)
    brief: str | None = None

    @model_validator(mode="after")
    def _consistent(self):
        for f in OPTIONAL:
            empty = self.dates.kind == "undecided" if f == "dates" else getattr(self, f) is None
            if empty != (f in self.indifferent):
                raise ValueError(f"{self.id}: {f} must be in indifferent exactly when it has no value")
        if "parents" in self.companions and "elderly" not in self.signals:
            raise ValueError(f"{self.id}: parents imply the elderly signal")
        if "kids" in self.companions and "kids" not in self.signals:
            raise ValueError(f"{self.id}: kids imply the kids signal")
        if (self.effort is None) == any(s in EFFORT_SIGNALS for s in self.signals):
            raise ValueError(f"{self.id}: effort is the answer to effort signals")
        if {(h.feature, h.op, h.value) for h in self.hard} != set(expected_hard(self.effort, self.signals)):
            raise ValueError(f"{self.id}: hard filters do not follow from the body signals")
        return self


def expected_hard(effort: str | None, signals) -> list[tuple[str, str, str]]:
    """What Trip's safety cards write for this body: c_effort chip -> effort filters, c_other veg -> vegetarian."""
    out = list(EFFORT_HARD[effort]) if effort else []
    if "vegetarian" in signals:
        out.append(("vegetarian_options", "eq", "yes"))
    return out


def load(path: Path = TRIPS) -> list[HiddenTrip]:
    raw = yaml.safe_load(path.read_text(encoding="utf-8"))
    return [HiddenTrip.model_validate(t) for t in raw["trips"]]


def save(trips: list[HiddenTrip], path: Path = TRIPS, header: str = "") -> None:
    body = yaml.safe_dump({"trips": [t.model_dump(mode="json", exclude_none=True) for t in trips]},
                          allow_unicode=True, sort_keys=False, width=120)
    path.write_text(header + body, encoding="utf-8")
