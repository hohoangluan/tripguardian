"""Validate persisted claims without changing their identity, provenance or ontology version."""

from datetime import date
import math
from typing import Any

from pydantic import BaseModel, ConfigDict, Field, field_validator


class Detail(BaseModel):
    model_config = ConfigDict(extra="allow", strict=True, allow_inf_nan=False)
    amount_vnd: int | float | None = Field(default=None, ge=0)
    min_people: int | None = Field(default=None, ge=0)
    months: list[int] = Field(default_factory=list)
    days: list[str] = Field(default_factory=list)
    hour: str | None = None
    audience: str | None = None
    unit: str | None = None
    who: str | None = None
    verdict: str | None = None


class Rating(BaseModel):
    model_config = ConfigDict(extra="allow", strict=True, allow_inf_nan=False)
    stars: float | int = Field(ge=1, le=5)
    observed_at: str | None = None


class Proposed(BaseModel):
    model_config = ConfigDict(extra="allow", strict=True)
    label: str = Field(min_length=1)
    author: str | None = None


class Span(BaseModel):
    model_config = ConfigDict(extra="allow", strict=True, allow_inf_nan=False)
    quote: str
    field: str
    start_s: float | int | None = None
    end_s: float | int | None = None


class Claim(BaseModel):
    model_config = ConfigDict(extra="allow", strict=True)
    id: str = Field(min_length=1)
    place_fid: str = Field(min_length=1)
    feature: str = Field(min_length=1)
    value: str
    context: dict[str, str] = Field(default_factory=dict)
    source_type: str = Field(min_length=1)
    source_id: str = Field(min_length=1)
    author: str | None = None
    observed_at: str | None = None
    span: Span
    extractor: str = Field(min_length=1)
    ontology_version: int | str | None = None
    detail: Detail | None = None

    @field_validator("observed_at")
    @classmethod
    def valid_date(cls, value):
        if value is not None:
            date.fromisoformat(value + "-01" if len(value) == 7 else value)
        return value


class Document(BaseModel):
    model_config = ConfigDict(extra="allow", strict=True)
    place_fid: str = Field(min_length=1)
    place_name: str | None = None
    as_of: str
    ontology_version: int | str | None = None
    observations: list[Any] = Field(default_factory=list)
    details: list[Any] = Field(default_factory=list)
    ratings: list[Any] = Field(default_factory=list)
    proposed: list[Any] = Field(default_factory=list)
    place: dict[str, Any] = Field(default_factory=dict)
    place_facts: dict[str, Any] = Field(default_factory=dict)
    voices: int = Field(default=0, ge=0)
    voices_targeted: int = Field(default=0, ge=0)

    @field_validator("place")
    @classmethod
    def valid_identity(cls, value):
        for key in ("fid", "name", "category", "address", "url"):
            if value.get(key) is not None and not isinstance(value[key], str):
                raise ValueError(f"invalid identity {key}")
        for key, limit in (("lat", 90), ("lng", 180)):
            coordinate = value.get(key)
            if coordinate is not None and (type(coordinate) not in (int, float) or not math.isfinite(coordinate) or abs(coordinate) > limit):
                raise ValueError(f"invalid identity {key}")
        return value

    @field_validator("place_facts")
    @classmethod
    def valid_facts(cls, value):
        for key in ("hours", "popular_times", "price", "tickets", "tickets_vnd", "time_spent"):
            if value.get(key) is not None and not isinstance(value[key], dict):
                raise ValueError(f"invalid fact {key}")
        spent = value.get("time_spent")
        if spent is not None and any(type(spent.get(k)) not in (int, float) or not math.isfinite(spent[k])
                                     for k in ("min_minutes", "max_minutes")):
            raise ValueError("invalid duration")
        if value.get("closure") is not None and not isinstance(value["closure"], str):
            raise ValueError("invalid closure")
        return value

    @field_validator("as_of")
    @classmethod
    def valid_date(cls, value):
        date.fromisoformat(value)
        return value
