"""LangGraph state for one free-text Trip turn. TripState stays the domain truth; this only carries turn scratch."""

from typing import Any


try:
    from typing import TypedDict
except ImportError:  # Python <3.12 fallback, project requires >=3.12
    from typing_extensions import TypedDict  # type: ignore


class TextTurn(TypedDict, total=False):
    session: Any
    inp: Any
    emit: Any
    chips: Any
    text: str
    turn: int
    before: Any
    previous: Any
    state: Any
    held: Any
    pre: Any
    simple: bool
    req: Any
    ranked: Any
    fields: dict
    heard: str
    compared: list
    streamed: list
    plan: Any
    error: str | None
    question: Any
    say: str
    log: list
