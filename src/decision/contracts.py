"""Public typed Decision Output; Planning accepts this rather than model-created places."""

from typing import Annotated, Literal

from pydantic import BaseModel, ConfigDict, Field, model_validator

from trip import MAX_TRIP_DAYS, SearchInput
from corpus.releases import Binding
from corpus.retrieval import EvidenceHit


class EvidenceInput(BaseModel):
    model_config = ConfigDict(extra="forbid")
    place: str = Field(min_length=1, max_length=100)
    feature: str = Field(min_length=1, max_length=100)
    context: dict[str, str] | None = None


class PlaceEvidence(BaseModel):
    model_config = ConfigDict(extra="forbid")
    corpus_binding: Binding | None
    place_id: str
    feature: str
    value: str | None
    status: str
    reason: Literal["available", "missing_feature", "unverified_feature", "index_unavailable", "no_served_span",
                    "legacy_lineage_unavailable"]
    items: list[EvidenceHit] = Field(default_factory=list)


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


class LodgingChoice(BaseModel):
    """Where every day starts and ends, picked at Lựa chọn (corpus `stay` record or a searched point)."""
    model_config = ConfigDict(extra="forbid")
    kind: Literal["corpus", "live", "address"]
    id: str | None = None
    text: str = Field(min_length=1)
    lat: float = Field(allow_inf_nan=False)
    lng: float = Field(allow_inf_nan=False)
    price_vnd: int | None = None


class DecisionOutput(BaseModel):
    model_config = ConfigDict(extra="forbid")
    corpus_binding: Binding | None = None
    confirmed: list[ConfirmedPlace]
    backup_pool: list[BackupPlace]
    wishlist: list[dict]
    trip_context: SearchInput
    decision_log: list[dict]
    feasibility: dict
    chunk_assignments: dict[str, Annotated[int, Field(strict=True, ge=0)]] = Field(default_factory=dict)
    lodging: LodgingChoice | None = None

    @model_validator(mode="after")
    def validate_chunks(self):
        if self.corpus_binding != self.trip_context.corpus_binding:
            raise ValueError("Decision and Search Input corpus binding mismatch")
        if self.chunk_assignments:
            if set(self.chunk_assignments) != {p.id for p in self.confirmed}:
                raise ValueError("chunk assignments must cover exactly the confirmed places")
            n_days = self.trip_context.context.days or MAX_TRIP_DAYS
            if any(k >= (n_days + 6) // 7 for k in self.chunk_assignments.values()):
                raise ValueError("chunk outside trip duration")
        return self
