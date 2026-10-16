"""Refine broad tastes with variants selected from real corpus photos."""

import re
import unicodedata
from math import isfinite

from .coverage import admissible
from .state import Draft, Drill, Option, SoftKey, TripState
from .text import fold

TOPICS = ("săn mây", "ngắm đồi", "cà phê", "chill", "chụp ảnh", "thiên nhiên", "cắm trại", "ăn uống", "về đêm", "tâm linh")
SPECIFIC = re.compile(r"\b(vintage|retro|có (?:nhiều )?(?:sách|view)|sách cũ|view\s+\w+|kiểu hàn|nhà gỗ|rừng thông)\b")
FEATURES = {"săn mây": ("cloud_hunting",), "ngắm đồi": ("scenic_view",), "chill": ("scenic_view", "cozy_decor"),
            "chụp ảnh": ("photo_spot", "scenic_view"), "thiên nhiên": ("nature",), "cắm trại": ("camping",),
            "về đêm": ("live_music", "night_market", "bar")}
# how people say a topic without its name: "ăn cho đã" is the food photo card, "chợ đêm" the evening one
ALIASES = {"ăn uống": ("ẩm thực", "ăn ngon", "ăn cho đã", "ăn vặt", "quán ăn", "đồ ăn", "đồ nướng", "món ngon", "nhà hàng"),
           "về đêm": ("chợ đêm", "phố đêm", "đi chơi đêm", "nightlife"),
           "cà phê": ("cafe", "coffee")}
CANONICAL = {a: t for t, names in ALIASES.items() for a in names} | {t: t for t in TOPICS}
HEARD = re.compile("|".join(re.escape(t) for t in sorted(CANONICAL, key=len, reverse=True)))
GROUPS = {"cà phê": {"cafe"}, "ăn uống": {"restaurant", "dessert", "market"}, "tâm linh": {"religious"},
          "thiên nhiên": {"nature", "garden_farm", "camping"}, "cắm trại": {"camping"},
          "về đêm": {"bar", "market"}, "chill": {"cafe", "nature"}}


def topics(text: str) -> list[str]:
    text = unicodedata.normalize("NFC", text).casefold()
    found = []
    for clause in re.split(r"[,;.!?\n]|\b(?:và|rồi|sau đó|nhưng)\b", text):
        if SPECIFIC.search(clause) or re.search(r"\b(homestay|khách sạn|chỗ ở|resort|hostel|hotel|dorm)\b", clause):
            continue
        for match in HEARD.finditer(clause):
            topic = CANONICAL[match[0]]
            if re.search(r"\b(?:không|chẳng|tránh)(?:\s+(?:muốn|thích|đi|ngồi))*\s*$", clause[:match.start()]):
                continue
            if topic not in found:
                found.append(topic)
    return found


def note(state: TripState, text: str, turn: int) -> TripState:
    known = {d.topic for d in state.drills}
    added = [Drill(topic=t, quote=t, turn=turn) for t in topics(text) if t not in known]
    return state.model_copy(update={"drills": (*state.drills, *added[:max(0, 3 - len(state.drills))])})


def finish(state: TripState, topic: str, status: str) -> TripState:
    return state.model_copy(update={"drills": tuple(d.model_copy(update={"status": status})
                                                    if d.topic == topic and d.status == "pending" else d
                                                    for d in state.drills)})


def skip(state: TripState, topic: str) -> TripState:
    return finish(state, topic, "skipped")


def refresh(state: TripState, catalog, cfg) -> TripState:
    """Recheck saved pools against current hard limits without searching or building a second tab."""
    drills = []
    for d in state.drills:
        if d.status != "pending" or d.tab is None or not d.tab.visual:
            drills.append(d)
            continue
        options = []
        for o in d.tab.options:
            if o.id in ("other", "skip"):
                continue
            places = tuple(pid for pid in o.places if pid in catalog.by_id
                           and admissible(catalog.by_id[pid], state.hard, state.activities.get(pid)))
            if len(places) < cfg.drill_min or not o.photo or o.photo[0] not in places:
                continue
            if any(w.field == "soft" and (cur := state.soft.get(w.value[0])) is not None
                   and cur.source == "user" and cur.known and cur.value != w.value[1] for w in o.writes):
                continue
            options.append(o.model_copy(update={"places": places, "count": len(places)}))
        from .deck import exits
        drills.append(d.model_copy(update={"status": "none"}) if len(options) < 2 else
                      d.model_copy(update={"tab": d.tab.model_copy(update={"options": tuple(options) + exits()})}))
    return state.model_copy(update={"drills": tuple(drills)})


def build(state: TripState, catalog, looks, cfg) -> TripState:
    """Each pending drill without a card gets its photo card from the topic's variants in config/trip.yaml `drills`,
    matched to real corpus photos; a topic with fewer than two variants that have photos is closed as none. No model
    call. Without looks (or variants for the topic) the drill stays as it is."""
    from .deck import exits
    from .state import Tab
    drills = []
    for d in state.drills:
        spec = cfg.drills.get(d.topic)
        if d.status != "pending" or d.tab is not None or not spec or looks is None:
            drills.append(d)
            continue
        options = choose(spec["variants"], d.topic, state, catalog, looks, cfg)
        drills.append(d.model_copy(update={"tab": Tab(
            qid=f"drill.{d.topic}", kind="drill", header=spec["header"], question=spec["question"],
            why=f"Vì bạn nói “{d.quote}”.", visual=True, multi=True, options=tuple(options) + exits())})
                      if options else d.model_copy(update={"status": "none"}))
    return state.model_copy(update={"drills": tuple(drills)})


def adopt(state: TripState, built: TripState) -> TripState:
    """The cards `build` made (on the state before the agent's turn) moved onto the state after it."""
    done = {d.topic: d for d in built.drills}
    return state.model_copy(update={"drills": tuple(
        done.get(d.topic, d) if d.status == "pending" and d.tab is None else d for d in state.drills)})


def choose(variants, topic: str, state: TripState, catalog, looks, cfg) -> list[Option]:
    if looks is None or topic not in TOPICS:
        return []
    # the topic's places are scored once for everyone (the looks cache them); this user's hard limits only filter
    base = {p.id for p in catalog.places if p.category_group in GROUPS.get(topic, ())
            or any(p.value(f) == "present" for f in FEATURES.get(topic, ()))}
    within = {pid for pid in base if admissible(catalog.by_id[pid], state.hard, state.activities.get(pid))}
    if not within:
        return []
    ranked = []
    for index, v in enumerate(variants[:6]):
        try:
            label, cues = str(v["label"]).strip(), tuple(v["cues"])
            axis = v.get("axis", "place")
            if not label or len(label) > 40 or not cues or not all(isinstance(c, str) and c.strip() for c in cues):
                continue
            subtype = next((s for s in ("chua", "nha tho") if s in fold(" ".join((label, *cues)))), None)
            scores = {}
            for pid, score in looks.scored_by_cues(list(cues), base):
                if pid in within and isfinite(score) and (not subtype or subtype in fold(catalog.by_id[pid].category or "")):
                    scores[pid] = max(scores.get(pid, float("-inf")), score)
            hits = sorted(scores.items(), key=lambda hit: -hit[1])
            if len(hits) < cfg.drill_min or hits[0][1] < cfg.drill_score_min:
                continue
            reps = [pid for pid, score in hits if score >= cfg.drill_score_min]
            writes = []
            period = v.get("period")
            context = {"sunrise": "early_morning", "midday": "noon", "sunset": "afternoon",
                       "daytime": "morning"}.get(period, period)
            if axis not in ("place", "time"):
                continue
            if axis == "time":
                from .frame import Period
                period = Period(period=period, kinds=(topic,))
                writes.append(Draft(field="frame.periods", op="add", value=period.model_dump()))
            for raw in v.get("writes", ()):
                if raw["field"] != "soft" or raw.get("op") == "remove":
                    raise ValueError("drill options only write soft preferences")
                from .values import split_weight
                key, weight = split_weight(str(raw["value"]))
                key = SoftKey.parse(key)
                if axis == "time":
                    key = key.model_copy(update={"context": tuple(sorted((*[(k, val) for k, val in key.context
                                                                           if k != "time_of_day"],
                                                                         ("time_of_day", context))))})
                    key = SoftKey.model_validate(key.model_dump())
                if weight not in ("love", "avoid", "off"):
                    raise ValueError("invalid preference weight")
                current = state.soft.get(str(key))
                if current is not None and current.source == "user" and current.known and current.value != weight:
                    raise ValueError("drill cannot reverse a stated preference")
                writes.append(Draft(field="soft", op="add", value=(str(key), weight)))
            if not any(w.field == "soft" for w in writes):
                continue
            ranked.append((len(hits) * hits[0][1], index, label, cues, tuple(writes), hits, reps, axis))
        except (KeyError, TypeError, ValueError):
            continue
    out, used, chosen_axis = [], set(), None
    for _, index, label, cues, writes, hits, reps, axis in sorted(ranked, key=lambda item: (-item[0], item[1])):
        if chosen_axis is not None and axis != chosen_axis:
            continue
        for pid in reps:
            if pid not in used and (photo := looks.best_photo(pid)):
                out.append(Option(id=f"v{index}", label=label, writes=writes, count=len(hits), photo=(pid, photo),
                                  description=f"Ảnh thật tại {catalog.by_id[pid].name}"[:80], cues=cues,
                                  places=tuple(p for p, _ in hits)))
                used.add(pid)
                chosen_axis = axis
                break
    return out if len(out) >= 2 else []  # every variant with a real photo (at most six): the stage shows them all
