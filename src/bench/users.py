"""Simulated users: the chip-only tapper's mapping table and the fixed-form baseline (docs/P2_TRIP_UNDERSTANDING.md §16)."""

from functools import cache

from trip import SearchInput, TripState, compile_search_input

from .hidden import HiddenTrip

# The fixed form: one field per row, filled from the truth; a blank row stays blank. turns = len(FORM).
FORM = ("days", "dates", "companions", "people", "mobility", "base", "pace", "crowd_tolerance", "novelty", "budget_vnd",
        "loves", "avoids", "health_limits", "anchors")

CROWD_CHIP = {"avoid": "avoid", "ok_if_worth": "ok", "fine": "fine"}
EFFORT_CHIP = {"steep": "steep", "walk": "walk", "both": "both", "none": "fine"}
SKIPPED = ("max_leg", "entry_exit", "times")        # fields a hidden trip has no opinion on
TASTE = ("purpose", "pace", "crowd_tolerance", "budget_vnd", "novelty")


def budget_bucket(v: int | None) -> int | None:
    """The budget card's buckets: <=300k, <=700k, <=1.5M, above (what each chip writes is its bucket's top)."""
    if v is None:
        return None
    return 0 if v <= 300_000 else 1 if v <= 700_000 else 2 if v <= 1_500_000 else 3


BUDGET_CHIP = {0: "low", 1: "mid", 2: "high", 3: "high"}


class Tap:
    """One answer: show, or chips (+ an input value). unmapped: the table did not know this card."""

    def __init__(self, kind: str, chips: list[str] = (), value: str | None = None, unmapped: bool = False):
        self.kind, self.chips, self.value, self.unmapped = kind, list(chips), value, unmapped

    @property
    def exit(self) -> bool:
        return self.kind == "answer" and any(c in ("skip", "unsure") for c in self.chips)


def skip(card: dict, unmapped: bool = False) -> Tap:
    if card.get("exits"):
        return Tap("answer", ["skip"], unmapped=unmapped)
    ids = [c["id"] for c in card["chips"]]
    if "show" in ids:
        return Tap("show", unmapped=unmapped)
    return Tap("answer", ids[:1], unmapped=unmapped)


def tap(card: dict, t: HiddenTrip, understanding: dict) -> Tap:
    """The chip a person with this truth taps. Chip ids follow the Trip question bank's conventions."""
    q = card["qid"]
    have = [c["id"] for c in card["chips"]]

    def chips(*ids):
        hit = [i for i in ids if i in have]
        return Tap("answer", hit) if hit else skip(card)

    if q == "frame":
        return Tap("answer", [i for i in (f"days:{t.days}", *(f"who:{w}" for w in t.companions), f"mobility:{t.mobility}")
                              if i in have])
    if q == "days":
        return chips(f"days:{t.days}")
    if q == "companions":
        return chips(*(f"who:{w}" for w in t.companions))
    if q == "mobility":
        return chips(f"mobility:{t.mobility}")
    if q == "dates":
        if t.dates.kind == "start_date":
            return Tap("answer", [], value=t.dates.start_date.isoformat())
        return chips("undecided")
    if q == "c_effort":
        return chips(EFFORT_CHIP[t.effort or "none"])
    if q == "c_other":
        want = [c for c, s in (("veg", "vegetarian"), ("pass", "motion_sick"), ("height", "height")) if s in t.signals]
        return chips(*want) if any(c in have for c in want) else chips("none")
    if q.startswith("policy:"):
        return chips("exclude")
    if q.startswith("anchor:"):
        return chips(*[a.place_id for a in t.anchors if a.place_id in have] or ["none"])
    if q.startswith("closed:"):
        return chips("keep")
    if q == "purpose":
        return chips(t.purpose) if t.purpose else skip(card)
    if q == "vibe":
        hit = [k for k in t.loves if k in have]
        return Tap("answer", hit) if hit else skip(card)
    if q == "crowd":
        return chips(CROWD_CHIP[t.crowd_tolerance]) if t.crowd_tolerance else skip(card)
    if q == "pace":
        return chips(t.pace) if t.pace else skip(card)
    if q == "budget":
        return chips(BUDGET_CHIP[budget_bucket(t.budget_vnd)]) if t.budget_vnd else skip(card)
    if q == "novelty":
        return chips(t.novelty) if t.novelty else skip(card)
    if q == "base":
        return Tap("answer", [], value=t.base) if t.base else skip(card)
    if q == "anchor_priority":
        return skip(card)                     # the tapper has no anchors: it cannot paste a link
    if q in SKIPPED:
        return skip(card)
    if q == "show_first":
        said = {k for k in TASTE if understanding.get(k)}
        return Tap("answer", ["more"]) if any(getattr(t, k) is not None and k not in said for k in TASTE) else Tap("show")
    if q == "ready":
        return Tap("show")
    return skip(card, unmapped=True)


# ---------- the fixed-form baseline ----------

@cache
def ontology_version() -> int:
    return compile_search_input(TripState()).ontology_version


def form_search_input(t: HiddenTrip) -> dict:
    """The fixed form filled from the truth, as the Search Input Decision reads. No inference, no defaults."""
    def soft(key: str, weight: int) -> dict:
        feature, _, value = key.partition("=")
        return {"feature": feature, "value": value, "context": None, "weight": weight, "source": "user"}

    unknowns = ([] if t.dates.kind != "undecided" else ["dates"]) + ["purpose"] + \
        [f for f in ("base", "pace", "budget_vnd") if getattr(t, f) is None]
    si = {
        "ontology_version": ontology_version(),
        "context": {"start_date": t.dates.start_date.isoformat() if t.dates.start_date else None, "month": t.dates.month,
                    "days": t.days, "base": {"place_id": None, "text": t.base} if t.base else None,
                    "entry_point": None, "exit_point": None, "mobility": t.mobility,
                    "companions": sorted(t.companions), "people": t.people, "checkin_at": None, "checkout_at": None,
                    "day_end": None, "budget_vnd": t.budget_vnd, "experience": t.experience},
        "hard_filters": [{**h.model_dump(), "unknown_policy": "exclude"} for h in t.hard],
        "anchors": [{"place_id": a.place_id, "priority": a.priority} for a in t.anchors],
        "soft_weights": [soft(k, 1) for k in t.loves] + [soft(k, -1) for k in t.avoids],
        "pace": {"level": t.pace, "max_leg_min": None, "crowd_tolerance": t.crowd_tolerance},
        "novelty": {"level": t.novelty, "visited": []},
        "unknowns": unknowns,
        "unmapped": [],
    }
    return SearchInput.model_validate(si).model_dump(mode="json")
