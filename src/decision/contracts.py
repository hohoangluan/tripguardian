"""Public typed Decision Output; Planning accepts this rather than model-created places."""

from typing import Literal

from pydantic import BaseModel, ConfigDict, Field

from trip import SearchInput


class ConfirmedPlace(BaseModel):
    model_config = ConfigDict(extra="forbid")
    id: str = Field(min_length=1)
    name: str
    role: Literal["anchor", "locked", "selected"]
    visit: dict | None
    flags: list[str]
    relaxed: list[str]


class BackupPlace(BaseModel):
    model_config = ConfigDict(extra="forbid")
    id: str = Field(min_length=1)
    name: str
    for_place: str | None = Field(alias="for")
    reason: str


class DecisionOutput(BaseModel):
    model_config = ConfigDict(extra="forbid")
    confirmed: list[ConfirmedPlace]
    backup_pool: list[BackupPlace]
    wishlist: list[dict]
    trip_context: SearchInput
    decision_log: list[dict]
    feasibility: dict
