"""The card the user answers: a question with chips, an open text box, or the "ready" prompt.

Cards are written by the agent (agent/tools.py); the engine only stores and sends them.
"""

from __future__ import annotations

from typing import Literal

from .state import Draft, Frozen


class Chip(Frozen):
    id: str
    label: str
    row: str | None = None
    drafts: tuple[Draft, ...] = ()


class Question(Frozen):
    qid: str
    group: str
    text: str
    reason: str = ""
    placeholder: str = ""  # an example answer for the text box, written for this question (empty: the screen's default)
    chips: tuple[Chip, ...] = ()
    multi: bool = False
    single_rows: tuple[str, ...] = ()  # rows of a multi question where only one chip may be on
    cost: float = 1.0
    tier: int = 3
    input: Literal["none", "text", "date", "place", "geo", "transit", "lodging", "rental"] = "none"
    input_field: str | None = None
    params: dict = {}  # what the screen needs to fill the input (transit: mode, from, to, date; rental: mode, lat?, lng?, text?)
    exits: bool = True  # shows "Không chắc" / "Bỏ qua"
    exit_drafts: tuple[Draft, ...] = ()  # written when the user picks an exit
    custom: bool = False  # written by the agent; a chip answer goes back through the agent as text


OPENING = Question(qid="frame", group="A", tier=1, input="text", exits=False, custom=True,
                   text="Kể mình nghe về chuyến Đà Lạt mơ ước sắp tới của bạn: đi mấy ngày, với ai, đi lại bằng gì, "
                        "muốn trải nghiệm điều gì. Cứ gõ tự nhiên như đang kể cho bạn bè.",
                   reason="Mình hỏi tiếp dựa trên điều bạn kể.")


def conversation_card() -> Question:
    """A free-text continuation: the agent asked nothing the user must answer."""
    return Question(qid="conversation", group="I", tier=0, custom=True, input="text", exits=False, text="")
