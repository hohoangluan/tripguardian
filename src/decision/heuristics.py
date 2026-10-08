"""Exact, single-place commands; any unconsumed intent remains an LLM task."""

from trip import squash


def exact_command(text: str, aliases: dict[str, dict]) -> list[dict] | None:
    command, _, name = squash(text).partition(' ')
    operation = {'chon': 'select', 'them': 'select', 'bo': 'drop', 'khoa': 'lock'}.get(command)
    if not operation or not name:
        return None
    matches = {place['id'] for place in aliases.values() if squash(place['name']) == name}
    if len(matches) != 1:
        return None
    return [{'type': operation, 'place_id': next(iter(matches))}]
