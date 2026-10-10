"""The deterministic quiz bank: every draft parses, every card has an out."""

from trip.domain import values
from trip.domain.questions import OTHER_CHIP, foundation_ok, quiz_queue, review_card
from trip.domain.state import TripState
from trip.infrastructure.catalog import Catalog


def check_drafts(catalog, drafts):
    for dr in drafts:
        if dr.field == "soft":
            key, weight = dr.value
            values.parse("soft", f"{key}:{weight}", catalog)
        elif dr.field == "hard":
            v = dict(dr.value)
            values.parse("hard", f"{v['feature']}{'!=' if v['op'] == 'ne' else '='}{v['value']}", catalog)
        elif dr.field in ("anchor_pick", "anchor_priority", "signal_handled", "pending"):
            pass  # structural (index, priority, kinds): applied in test_phases
        elif dr.op == "remove":
            pass
        else:
            values.parse(dr.field, str(dr.value), catalog)


def test_every_quiz_card_has_an_other_chip_and_exits(catalog, cfg):
    for q in quiz_queue(TripState(), catalog, cfg):
        if q.qid != "dates":
            assert q.exits is True, q.qid
        if q.input in ("geo", "lodging", "transit"):  # the card's own search box is the typed answer
            continue
        assert any(c.id == OTHER_CHIP for c in q.chips), q.qid
        for c in q.chips:
            check_drafts(catalog, c.drafts)


def test_every_chip_draft_parses(catalog, cfg):
    for q in quiz_queue(TripState(), catalog, cfg):
        for c in q.chips:
            check_drafts(catalog, c.drafts)
        check_drafts(catalog, q.exit_drafts)


def test_queue_is_safety_first_then_fixed_order(catalog, cfg):
    qids = [q.qid for q in quiz_queue(TripState(), catalog, cfg)]
    assert qids[:6] == ["days", "companions", "arrival", "mobility", "dates", "lodging"]
    assert qids.index("purpose") < qids.index("crowd") < qids.index("pace") < qids.index("budget")
    assert "max_leg" not in qids and "times" not in qids


def test_known_fields_leave_the_queue(catalog, cfg):
    from trip.domain.state import Evidence, Update, apply, settle
    st = TripState()
    ev = Evidence(turn=0, tool="test")
    st = settle(apply(st, Update(field="days", value=3, source="user", confidence="high", evidence=ev)))
    qids = [q.qid for q in quiz_queue(st, catalog, cfg)]
    assert "days" not in qids and "companions" in qids


def test_foundation_needs_days_who_ride_and_when(catalog, cfg):
    from trip.domain.state import Evidence, Update, apply, settle
    st = TripState()
    assert not foundation_ok(st)
    ev = Evidence(turn=0, tool="test")
    for field, value in (("days", 3), ("companions", "partner"), ("mobility", "car"), ("month", 12)):
        if field == "companions":
            st = settle(apply(st, Update(field=field, op="add", value=value, source="user", confidence="high",
                                         evidence=ev)))
        else:
            st = settle(apply(st, Update(field=field, value=value, source="user", confidence="high", evidence=ev)))
    assert foundation_ok(st)


def test_review_card(catalog, cfg):
    review = review_card()
    assert review.qid == "review" and review.input == "text"
    assert "show" in {c.id for c in review.chips}


def test_dates_card_has_no_exits_undecided_is_the_only_way_past(catalog, cfg):
    from trip.domain.questions import dates_q
    q = dates_q()
    assert q.exits is False and q.input == "date"
    assert {c.id for c in q.chips} == {"undecided", "other"}


def test_empty_catalog_still_offers_a_quiz_without_vibe(cfg):
    catalog = Catalog.from_records([], n_min=1)
    qids = [q.qid for q in quiz_queue(TripState(), catalog, cfg)]
    assert "days" in qids and "vibe" not in qids  # vibe needs enough evidence; the rest does not
