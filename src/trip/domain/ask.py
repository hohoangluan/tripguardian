"""Post-check the agent's proposed questions before offering any writes to a user."""

import re
from hashlib import sha256

from pydantic import ValidationError

from . import values
from .coverage import admissible
from .deck import Option, Tab, exits
from .guard import record_fact
from .readiness import missing
from .state import SCALARS, Draft, SoftKey, TripState, apply_drafts, ontology
from .taste_bank import fixed
from .understanding import matching, to_taste


# liked_groups value -> the corpus category groups that show it
KIND_CATEGORIES = {"nature": {"nature", "garden_farm", "camping"}, "sights": {"museum", "religious", "attraction", "amusement"},
                   "chill": {"cafe"}, "meal": {"restaurant", "dessert"}}


def check(questions, state: TripState, catalog, cfg, looks=None) -> tuple[Tab, ...]:
    required_fields = {"start_date": "trip", "days": "trip", "checkin_at": "trip", "checkout_at": "trip",
                       "companions": "companions", "people": "companions", "mobility": "mobility", "driver": "mobility",
                       "care": "care", "pace": "pace", "budget_vnd": "budget", "budget_scope": "budget",
                       "budget_unlimited": "budget", "lodging": "lodging"}
    needed = {k for k, _ in missing(state, cfg.required)}
    identifiers = set(SCALARS) | set(ontology().features) | {"signal", "hard", "soft", "frame", "unmapped"}

    def leaky(text):
        return any(re.search(r"(?<!\w)" + re.escape(f) + r"(?!\w)", text, re.I) for f in identifiers)

    out, visual_seen = [], set()
    for q in list(questions)[:3]:
        if not isinstance(q, dict):
            continue
        question, header, why = (str(q.get(k) or "").strip() for k in ("question", "header", "why"))
        qid = "agent." + sha256(question.encode("utf-8")).hexdigest()[:12]
        if not question or len(question) > 90 or len(header) > 12 or any(leaky(t) for t in (question, header, why)):
            continue
        if qid in state.meta.declined or question in state.meta.declined:
            continue
        if q.get("visual"):
            from . import drill
            topic = visual_topic(q, state)
            if topic in visual_seen:
                continue
            visual_seen.add(topic)
            pending = next((d for d in state.drills if d.topic == topic and d.status == "pending" and d.tab is None), None)
            if pending is None:
                continue
            options = drill.choose(q.get("options") or [], topic, state, catalog, looks, cfg)
            if options:
                out.append(Tab(qid=f"drill.{topic}", kind="drill", header=header, question=question,
                               why=why or f'Vì bạn nói “{pending.quote}”.', visual=True, multi=bool(q.get("multi")),
                               options=tuple(options) + exits()))
            continue
        options, pools, redundant = [], [], False
        for j, o in enumerate(q.get("options") or ()):
            try:
                # the model picks the readings (the writes); their words are the app's, never the model's
                if (bank := fixed(o["writes"])) is None:
                    continue
                label, description = bank
                writes, after = [], state
                for raw in o["writes"]:
                    f = raw["field"]
                    current = getattr(state, f, None)
                    if f == "soft":
                        key, _ = values.split_weight(str(raw["value"]))
                        current = state.soft.get(key)
                    if (getattr(current, "known", False) and current.source == "user") or f in state.meta.declined \
                            or required_fields.get(f) in needed:
                        redundant = True
                        break
                    if f == "hard" or f not in ("soft", "liked_groups", "purpose", "pace", "novelty", "crowd_tolerance",
                                               "mobility", "companions", "people", "max_leg_min", "day_end"):
                        raise ValueError("unsupported agent option")
                    op, value = raw.get("op", "set"), raw["value"]
                    if op == "remove":
                        raise ValueError("agent options cannot remove requirements")
                    # Parsing and guard validation share the same boundary as record_fact. The option is a
                    # future user choice; its own label supplies preview evidence, never a claimed user fact.
                    after, note = record_fact(after, f, op, str(value), label, "inferred", label,
                                              state.meta.turn, catalog)
                    if note.startswith("refused:"):
                        raise ValueError(note)
                    parsed = values.parse(f, str(value), catalog)
                    writes.append(Draft(field=f, op=op, value=parsed))
                if redundant:
                    break
                if not writes:
                    continue
                after = apply_drafts(state, writes, state.meta.turn, tool="ask:preview")
                count = matching(after, catalog)
                if not count:
                    continue
                fits = to_taste(after)
                pools.append(frozenset(c.id for c in catalog.places
                                      if admissible(c, after.hard, after.activities.get(c.id)) and fits(c)))
                options.append(Option(id=f"o{j}", label=label,
                                      description=description or f"Ưu tiên {label.lower()} khi chọn nơi cho bạn.",
                                      writes=tuple(writes), count=count))
            except (ValueError, TypeError, KeyError, ValidationError):
                continue
        if redundant or len(options) < 2 or len(set(pools)) < 2:
            continue
        out.append(Tab(qid=qid, kind="agent", header=header, question=question, why=why,
                       multi=bool(q.get("multi")), options=tuple(options) + exits()))
    return tuple(out)


def with_photos(tab: Tab, state: TripState, catalog, looks) -> Tab:
    """A question whose options are tastes shows a real place for each: a photo asks better than words. Only when every
    option gets its own place with a photo; otherwise the question stays in words. Same photos on every rebuild."""
    if looks is None or tab.kind != "agent" or tab.visual:
        return tab
    options, used = [], set()
    for o in tab.options:
        if o.id in ("other", "skip"):
            options.append(o)
            continue
        if len(o.writes) != 1 or o.writes[0].field not in ("soft", "liked_groups"):
            return tab  # a pace, a crowd limit, a purpose has no place to show: that question stays in words
        wanted = []
        if o.writes[0].field == "liked_groups":  # a kind of place: any place of that kind shows it
            cats = KIND_CATEGORIES.get(str(o.writes[0].value[0]))
            if not cats:
                return tab
            fits = [c for c in catalog.places if c.category_group in cats
                    and admissible(c, state.hard, state.activities.get(c.id))]
        else:
            try:
                key = SoftKey.parse(o.writes[0].value[0])
            except ValueError:
                return tab
            fits = [c for c in catalog.places if c.value(key.feature) == key.value
                    and admissible(c, state.hard, state.activities.get(c.id))]
            # the place shown also has what the user already asked for ("săn mây"), when any does: a photo of a grill
            # shop under "ngồi cà phê chờ mây" would answer a different question
            wanted = [SoftKey.parse(k) for k, f in state.soft.items() if f.value == "love" and f.source == "user"]
        both = [c for c in fits if all(c.value(w.feature) == w.value for w in wanted)]
        places = sorted(both or fits, key=lambda c: (-c.weight, c.id))
        pick = next(((c.id, photo) for c in places[:15] if c.id not in used and (photo := looks.best_photo(c.id))), None)
        if pick is None:
            return tab
        used.add(pick[0])
        options.append(o.model_copy(update={"photo": pick}))
    return tab.model_copy(update={"visual": True, "options": tuple(options)})


def visual_topic(question: dict, state: TripState) -> str | None:
    explicit = question.get("topic")
    return next((d.topic for d in state.drills
                 if d.topic == explicit or (not explicit and d.topic in str(question.get("question", "")).casefold())), None)
