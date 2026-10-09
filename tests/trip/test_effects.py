from trip.domain.card import Chip, Question
from trip.domain.state import Draft, TripState, apply_drafts
from trip.domain.understanding import chip_effects, matching

QUIET = Draft(field="soft", op="add", value=("noise=quiet", "love"), inferred=True)


def q(*chips):
    return Question(qid="test", group="A", tier=2, text="?", chips=chips)


def test_each_chip_says_how_many_matching_places_it_adds_or_removes(catalog):
    st = TripState()
    assert matching(st, catalog) == len(catalog.places)
    fx = chip_effects(st, q(Chip(id="quiet", label="Yên tĩnh", drafts=(QUIET,)), Chip(id="any", label="Sao cũng được")),
                      catalog)
    assert fx == {"quiet": 6 - len(catalog.places)}


def test_a_chip_that_changes_nothing_has_no_effect(catalog):
    st = TripState()
    liked = chip_effects(st, q(Chip(id="quiet", label="Yên tĩnh", drafts=(QUIET,))), catalog)
    after = apply_drafts(st, (QUIET,), 1, tool="chip:test:quiet")
    assert chip_effects(after, q(Chip(id="again", label="Yên tĩnh", drafts=(QUIET,))), catalog) == {}
    assert liked["quiet"] < 0
