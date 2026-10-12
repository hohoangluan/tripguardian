"""Public typed Decision Output; Planning accepts this rather than model-created places."""

from typing import Annotated, Literal

from pydantic import BaseModel, ConfigDict, Field, model_validator

from trip import MAX_TRIP_DAYS, SearchInput


class ConfirmedPlace(BaseModel):
    model_config = ConfigDict(extra="forbid")
    id: str = Field(min_length=1)
    name: str
    role: Literal["anchor", "locked", "selected"]
    visit: dict | None
    flags: list[str]
    relaxed: list[str]
    utility: float | None = Field(default=None, allow_inf_nan=False)
    utility_source: str | None = None


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
    chunk_assignments: dict[str, Annotated[int, Field(strict=True, ge=0)]] = Field(default_factory=dict)

    @model_validator(mode="after")
    def validate_chunks(self):
        if self.chunk_assignments:
            if set(self.chunk_assignments) != {p.id for p in self.confirmed}:
                raise ValueError("chunk assignments must cover exactly the confirmed places")
            n_days = self.trip_context.context.days or MAX_TRIP_DAYS
            if any(k >= (n_days + 6) // 7 for k in self.chunk_assignments.values()):
                raise ValueError("chunk outside trip duration")
        return self
