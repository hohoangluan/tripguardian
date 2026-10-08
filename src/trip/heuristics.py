"""Skip reasoning only when a deterministic rule covers the whole utterance."""

import re

from .prepass import Prepass
from .questions import Question
from .text import squash

FILLER = {'minh', 'toi', 'nhe', 'nha', 'thoi', 'a', 'chac', 'la', 'cu', 'di'}
EXITS = {'bo qua': 'skip', 'khong chac': 'unsure'}


def _core(s: str) -> str:
    return ' '.join(w for w in squash(s).split() if w not in FILLER)


def chip_echo(text: str, card: Question | None) -> str | None:
    """The chip id whose label (or one comma part of it) the message repeats and nothing more; None otherwise.
    A card the agent wrote has no chip values, so it is left to the agent; a card with a text box reads typing as text."""
    if card is None or card.custom or card.input == 'text':
        return None
    said = _core(text)
    if not said:
        return None
    if card.exits and said in EXITS:
        return EXITS[said]
    hits = {c.id for c in card.chips for part in [c.label, *c.label.split(',')] if _core(part) == said}
    return hits.pop() if len(hits) == 1 else None


def simple_frame(text: str, pre: Prepass) -> bool:
    if not pre.proposals or pre.ambiguous:
        return False
    if any(p.field not in {'days', 'people', 'mobility'} or p.inferred for p in pre.proposals):
        return False
    remaining = squash(text)
    for proposal in pre.proposals:
        quote = squash(proposal.quote)
        remaining, count = re.subn(r'(?<!\w)' + re.escape(quote) + r'(?!\w)', ' ', remaining, count=1)
        if not count:
            return False
    return all(word in {'minh', 'toi', 'di', 'voi', 'bang', 'trong', 'va'} for word in remaining.split())
