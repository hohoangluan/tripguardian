"""Intent metadata; evidence stays attached to the trip's hard and soft values."""

from functools import cache
from typing import Literal

from pydantic import BaseModel, ConfigDict, Field, model_validator

from corpus import load_ontology

Scope = Literal["all", "eating", "drinking", "sightseeing", "accommodation", "travel"]
Activity = Literal["eating", "coffee", "drinking", "tasting", "wine_tasting", "alcohol_consumption",
                   "sightseeing", "photography", "walking", "nightlife", "accommodation", "travel"]
ACTIVITIES = frozenset(Activity.__args__)


@cache
def ontology():
    return load_ontology()


def valid_condition(feature: str, value: str) -> bool:
    if feature == "venue_category":
        return value == "bar"
    if feature == "activity":
        return value in ACTIVITIES
    return ontology().valid(feature, value)


class RequirementIntent(BaseModel):
    model_config = ConfigDict(frozen=True, extra="forbid")
    meaning: str | None = None
    scope: Scope | None = None
    subject: Literal["traveler", "group", "member", "unspecified"] = "unspecified"
    subject_count: int | None = Field(default=None, ge=1, le=20)
    ambiguity: str | None = None


class Requirement(RequirementIntent):
    feature: str
    op: Literal["eq", "ne"]
    value: str
    strength: Literal["mandatory", "preference"] = "mandatory"

    @model_validator(mode="after")
    def _condition(self):
        if not valid_condition(self.feature, self.value):
            raise ValueError(f"unknown requirement {self.feature}={self.value}")
        if self.strength == "mandatory" and self.ambiguity:
            raise ValueError("clarify ambiguity before recording a mandatory requirement")
        if self.feature in {"venue_category", "activity"} and self.scope not in (None, "all"):
            raise ValueError("venue and activity restrictions must use scope all")
        from .checks import scope_for
        canonical = scope_for(self.feature)
        if canonical != "all" and self.scope not in (None, canonical):
            raise ValueError(f"{self.feature} must use scope {canonical}")
        f = ontology().features.get(self.feature)
        if f and f.group in {"effort", "suitability"} and self.scope not in (None, "all"):
            raise ValueError("access and safety requirements must apply to every visit")
        return self
