"""Typed journey requests and persisted envelopes; modules own business payload validation."""

from typing import Literal, Protocol, Callable

from pydantic import BaseModel, ConfigDict, Field, model_validator

Stage = Literal["trip", "decision", "planning"]
Operation = Literal["turn", "act", "advance", "back", "confirm", "recommend"]
Emit = Callable[[str, dict], None]


class Conflict(ValueError):
    """A stale revision, a reused request_id, or a journey another writer changed first (HTTP 409)."""


class Request(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True)
    request_id: str = Field(min_length=1, max_length=128, pattern=r"^[a-zA-Z0-9_-]+$")
    stage: Stage
    operation: Operation
    expected_revision: int = Field(ge=0, strict=True)
    payload: dict = Field(default_factory=dict)

    @model_validator(mode="after")
    def validate_payload(self):
        if self.operation in {"advance", "back", "confirm", "recommend"} and self.payload:
            raise ValueError(f"{self.operation} does not accept a client supplied payload")
        return self


class Journey(BaseModel):
    model_config = ConfigDict(extra="forbid")
    id: str = Field(pattern=r"^[0-9a-f]{12}$")
    user_id: str | None = Field(None, pattern=r"^[0-9a-f]{32}$")  # the account that owns it (uuid hex)
    stage: Stage = "trip"
    revision: int = 0
    sessions: dict[Stage, str] = Field(default_factory=dict)
    outputs: dict[Stage, dict] = Field(default_factory=dict)
    snapshots: dict[Stage, dict] = Field(default_factory=dict)
    receipts: dict[str, dict] = Field(default_factory=dict)


class JourneyView(BaseModel):
    model_config = ConfigDict(extra="forbid")
    id: str = Field(pattern=r"^[0-9a-f]{12}$")
    stage: Stage
    revision: int = Field(ge=0)
    sessions: dict[Stage, str]
    outputs: dict[Stage, dict]
    result: dict


class ModuleTools(Protocol):
    def create(self, payload: dict) -> dict: ...
    def load(self, sid: str) -> dict: ...
    def apply(self, sid: str, operation: str, payload: dict, emit: Emit) -> dict: ...
    def snapshot(self, sid: str) -> dict: ...
    def restore(self, snapshot: dict) -> None: ...
