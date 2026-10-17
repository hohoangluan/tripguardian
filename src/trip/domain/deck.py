"""Code-built questions, ordered by what the trip still needs."""

from typing import Literal
from datetime import timedelta

from ..infrastructure.catalog import Catalog
from ..infrastructure.settings import Settings
from .state import Draft, Frozen, Option, Tab, TripState
from .text import fold


class Deck(Frozen):
    kind: Literal["deck"] = "deck"
    tabs: tuple[Tab, ...] = ()
    left: int = 0
    total: int = 7
    agent: tuple[Tab, ...] = ()  # checked questions waiting behind the required tabs
    at: Literal["understand", "gate"] = "understand"
    ask: str | None = None  # the required topic the agent chose to ask now (ask_required)
    ask_question: str | None = None  # the agent's own words for that question; the topic's default text is the gate's

    @property
    def qid(self) -> str:
        return "deck"

    @property
    def text(self) -> str:
        return ""


# The order in which a card's options are kept when it shows only the best three of a group (the common answers
# first); an option the code guessed (prefilled) always comes first. Ids not listed keep their own order after these.
BEST = {"companions": ("partner", "friends", "parents", "kids", "solo", "baby", "pet", "coworkers"),
        "mobility": ("motorbike", "car_hired", "car_self", "walk"),
        "care": ("none", "steps", "vegetarian", "vegan", "motion_sick", "wheelchair", "pregnant", "height"),
        "budget": ("trip_total", "per_person", "unlimited", "per_day", "per_person_day"),
        "trip": ("start.default", "start.morning", "start.afternoon", "end.default", "end.midday", "end.afternoon"),
        "confirm.early": ("any", "no")}


def best(tab: Tab, keep: int = 3) -> Tab:
    """The tab with at most `keep` options per group (the part of the id before a dot: start, end, dates, ...), the
    prefilled ones first, then BEST. Other and Skip stay: the user types or skips anything not shown. A photo question
    keeps every variant: the stage shows them all."""
    if tab.visual:
        return tab
    rank = BEST.get(tab.qid, ())
    groups: dict[str, list[Option]] = {}
    for o in tab.options:
        if o.id not in ("other", "skip"):
            groups.setdefault(o.id.split(".")[0] if "." in o.id and tab.qid != "confirm.early" else "", []).append(o)
    kept = [o for opts in groups.values() for o in sorted(
        opts, key=lambda o: (not o.prefilled, rank.index(o.id) if o.id in rank else len(rank)))[:keep]]
    return tab.model_copy(update={"options": tuple(kept) + tuple(o for o in tab.options if o.id in ("other", "skip"))})


def exits() -> tuple[Option, ...]:
    return (Option(id="other", label="Khác, tự gõ"), Option(id="skip", label="Bỏ qua"))


def confirm_tabs(state: TripState, catalog: Catalog, cfg: Settings) -> tuple[Tab, ...]:
    if state.meta.soft_skips >= 2 or state.meta.rushed:
        return ()
    out = []
    done = set(state.meta.asked) | set(state.meta.declined)

    def add(qid, header, question, options, why="", multi=False):
        if qid not in done:
            out.append(Tab(qid=qid, kind="confirm", header=header, question=question, why=why,
                           multi=multi, options=tuple(options) + exits()))

    def write(field, value, op="set"):
        return Draft(field=field, value=value, op=op)

    loves = {k for k, f in state.soft.items() if f.value == "love"}
    early = any(k.split("=")[0] in ("cloud_hunting", "sunrise_view") for k in loves)
    early |= any("bình minh" in (e.quote or "").lower() for k in loves for e in state.soft[k].evidence)
    known_early = any(d.start and d.start <= "05:30" for d in state.frame.days) or any(
        p.period == "sunrise" for p in state.frame.periods) or (state.frame.day_start.value or "24:00") <= "05:30"
    if early and not known_early:
        period = write("frame.periods", {"period": "sunrise"}, "add")
        def day_label(i):
            if not state.start_date.known:
                return f"Ngày {i + 1}"
            day = state.start_date.value + timedelta(days=i)
            return f"{'CN' if day.weekday() == 6 else 'T' + str(day.weekday() + 2)} {day:%d/%m}"
        options = [Option(id=f"day.{i}", label=day_label(i), description="Mình dành buổi sớm ngày này để săn mây, ngắm bình minh.", writes=(
            write("frame.days", {"index": i, "start": "05:30"}, "add"), period))
                   for i in range(state.days.value or 0)]
        options += [Option(id="any", label="Ngày nào cũng được", description="Mình dành buổi sớm ngày thứ hai, hoặc ngày đầu nếu chỉ đi một ngày.", writes=(
            write("frame.days", {"index": 1 if (state.days.value or 1) > 1 else 0, "start": "05:30"}, "add"), period)),
                    Option(id="no", label="Không dậy sớm", description="Mình giữ giờ bắt đầu ngày như hiện tại.")]
        quotes = tuple(dict.fromkeys(e.quote for k in loves for e in state.soft[k].evidence
                                    if e.quote and (k.split("=")[0] in ("cloud_hunting", "sunrise_view")
                                                    or "bình minh" in e.quote.lower())))
        why = "Vì bạn nói “" + "”, “".join(quotes) + "”." if quotes else "Để dành buổi sớm cho sở thích bạn đã chọn."
        add("confirm.early", "Dậy sớm", "Cần có mặt khoảng 5:30. Bạn dậy sớm được ngày nào?", options, why)
    evening = any(k.split("=")[0] in ("live_music", "night_market", "bar", "sunset_view") for k in loves)
    evening |= any(word in (e.quote or "").lower() for k in loves for e in state.soft[k].evidence
                   for word in ("chợ đêm", "bar", "spa tối"))
    if evening and not state.day_end.known and not any(p.period == "evening" for p in state.frame.periods):
        why = "Để dành thời gian đi chơi tối."
        if state.mobility.value == "motorbike":
            why += " Đi xe máy cần lưu ý đường tối và đường đèo."
        add("confirm.evening", "Buổi tối", "Tối đi tới khoảng mấy giờ?", [
            Option(id=key, label=label, description=f"Mình xếp lịch đi chơi tối kết thúc trước {clock}.", writes=(write("day_end", clock),
                   write("frame.periods", {"period": "evening"}, "add")))
            for key, label, clock in (("20", "20h", "20:00"), ("22", "22h", "22:00"), ("late", "Khuya", "23:59"))], why)
    kinds = {s.kind for s in state.signals}
    if ((state.companions.value or set()) & {"kids", "baby", "parents"} or kinds & {"kids", "elderly", "pregnant"}) \
            and not any(b.kind in ("rest", "nap") for b in state.frame.busy):
        add("confirm.nap", "Nghỉ trưa", "Có cần về chỗ ở nghỉ trưa không?", [
            Option(id="yes", label="Có, 12h–14h", description="Mình chừa 12h–14h mỗi ngày để bạn nghỉ ở chỗ ở.", writes=(write("frame.busy", {
                "label": "nghỉ trưa", "kind": "rest", "where": "lodging", "start": "12:00", "end": "14:00", "on": "all"}, "add"),)),
            Option(id="no", label="Không", description="Mình không thêm giờ về chỗ ở nghỉ trưa.")])
    must = [(i, a) for i, a in enumerate(state.anchors) if a.priority == "must"]
    per_day = cfg.pace_per_day.get(state.pace.value or "normal", cfg.pace_per_day["normal"])
    if state.days.known and len(must) > state.days.value * per_day:
        add("confirm.priority", "Ưu tiên", "Nếu không đủ giờ, giữ nơi nào trước?", [
            Option(id=f"anchor.{i}", label=a.text[:40], description="Giữ nơi này bắt buộc; các nơi còn lại có thể đổi nếu thiếu giờ.", writes=tuple(
                write("anchor_priority", (j, "must" if j == i else "want")) for j, _ in must)) for i, a in must],
            f"Nhịp này khoảng {per_day} nơi mỗi ngày.")
    arrive = state.frame.arrive.value
    if arrive and arrive.at[11:] < "07:00" and not any(d.index == 0 and d.start for d in state.frame.days):
        add("confirm.arrive", "Lúc tới", f"Tới {arrive.at[11:]}: nghỉ trước hay đi luôn?", [
            Option(id="rest", label="Nghỉ trước", description="Mình bắt đầu lịch ngày đầu từ 08:00, sau giờ bạn sẵn sàng.", writes=(write("frame.days", {"index": 0, "start": "08:00"}, "add"),)),
            Option(id="go", label="Đi luôn", description="Mình giữ giờ bắt đầu sau khi bạn tới và có đủ giờ chuẩn bị.")])
    no_far = any("khong di xa" in fold(u.phrase) for u in state.unmapped)
    if ("motion_sick" in kinds or no_far) and not state.max_leg_min.known:
        add("confirm.drive", "Đường đi", "Mỗi chặng tối đa bao lâu?", [
            Option(id=str(n), label=f"{n} phút", description=f"Mình chỉ ghép các nơi cách nhau tối đa {n} phút đi xe.", writes=(write("max_leg_min", n),)) for n in (15, 30)] + [
            Option(id="none", label="Không sao", description="Mình không thêm giới hạn thời gian mỗi chặng.")])
    return tuple(out)


def build(state: TripState, catalog: Catalog, cfg: Settings, agent=(), at="understand", ask: str | None = None,
          question: str | None = None) -> Deck:
    """The questions the trip still needs. On the Understand screen the deck shows ONE question: the required topic the
    agent chose (`ask`, in the agent's words `question`), else the agent's own follow-up or a pending drill, else a
    confirmation. The app never opens a required topic by itself there: the agent asks it when the talk reaches it,
    in words that fit the talk. The gate (read-back before planning) shows every missing topic at once, in the topic's
    default words."""
    from .drill import refresh
    from .required import tabs
    from .readiness import missing

    state = refresh(state, catalog, cfg)
    required = tabs(state, cfg)
    if at == "understand":
        required = tuple(t for t in required if t.qid not in state.meta.declined)
    from . import ask as asking  # not `ask`: that is the chosen topic
    checked = []
    for tab in agent:
        raw = {"question": tab.question, "header": tab.header, "why": tab.why, "multi": tab.multi, "options": []}
        for o in tab.options:
            if o.id in ("other", "skip"):
                continue
            writes = []
            for d in o.writes:
                value = f"{d.value[0]}:{d.value[1]}" if d.field == "soft" else str(d.value)
                writes.append({"field": d.field, "op": d.op, "value": value})
            raw["options"].append({"label": o.label, "description": o.description, "writes": writes})
        for fresh in asking.check([raw], state, catalog, cfg):
            # Preserve option ids when an intervening hard constraint removes an option.
            ids = {o.label: o.id for o in tab.options}
            checked.append(fresh.model_copy(update={"qid": tab.qid, "options": tuple(
                o.model_copy(update={"id": ids.get(o.label, o.id)}) for o in fresh.options)}))
    drills = tuple(d.tab for d in state.drills if d.status == "pending" and d.tab is not None)
    optional = () if state.meta.soft_skips >= 2 or state.meta.rushed else (
        drills + confirm_tabs(state, catalog, cfg) + tuple(t for t in checked if t.qid not in state.meta.declined
                                                and t.qid not in state.meta.asked))
    order = {"drill": 0, "confirm": 1, "agent": 2, "maybe": 3}
    optional = tuple(sorted(optional, key=lambda t: order[t.kind]))
    left = len(missing(state, cfg.required))
    if at == "gate":
        optional = tuple(t for t in optional if t.kind == "confirm")
        return Deck(tabs=required + optional[:max(0, cfg.max_tabs - len(required))], left=left, agent=tuple(agent), at=at)  # every missing required topic: one round trip
    question = (question or "").strip() or None
    chosen = [t.model_copy(update={"question": question}) if question else t for t in required if t.qid == ask]
    follow = [t for t in optional if t.kind in ("drill", "agent")]
    confirm = [t for t in optional if t.kind not in ("drill", "agent")]
    one = [best(t) for t in (chosen or follow or confirm)[:1]]
    return Deck(tabs=tuple(one), left=left, agent=tuple(agent), at=at, ask=ask if chosen else None,
                ask_question=question if chosen else None)
