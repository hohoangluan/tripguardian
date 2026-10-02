"""Question bank, tier-1 rules and question value (docs/TRIP_UNDERSTANDING.md §7-8, Project_Context.md §12.2).

Every chip carries the updates it writes, so answering a chip never needs the model.
"""

from __future__ import annotations

from datetime import timedelta
from typing import Literal

from .catalog import Catalog
from .coverage import Coverage, admissible, coverage
from .settings import Settings
from .state import (EFFORT_SIGNALS, OTHER_SIGNALS, Anchor, Base, Draft, Frozen, Hard, SoftKey, TripState,
                    apply_drafts, ontology, pending_signals)


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
    chips: tuple[Chip, ...] = ()
    multi: bool = False
    single_rows: tuple[str, ...] = ()  # rows of a multi question where only one chip may be on
    cost: float = 1.0
    tier: int = 3
    input: Literal["none", "text", "date", "place"] = "none"
    input_field: str | None = None
    exits: bool = True  # shows "Không chắc" / "Bỏ qua"
    exit_drafts: tuple[Draft, ...] = ()  # written when the user picks an exit
    custom: bool = False  # written by the agent; a chip answer goes back through the agent as text


def d(field: str, value=None, op: str = "set", inferred: bool = False) -> Draft:
    return Draft(field=field, op=op, value=value, inferred=inferred)


def soft(key: str) -> Draft:
    return d("soft", (key, "love"), "add", inferred=True)


WHO = {
    "solo": ("Một mình", (d("companions", "solo", "add"),)),
    "partner": ("Người yêu, vợ chồng", (d("companions", "partner", "add"), soft("couples=suitable"))),
    "friends": ("Bạn bè", (d("companions", "friends", "add"), soft("groups=suitable"))),
    "kids": ("Có trẻ nhỏ", (d("companions", "kids", "add"), d("signal", "kids", "add", True), soft("kids=suitable"))),
    "parents": ("Bố mẹ, người lớn tuổi",
                (d("companions", "parents", "add"), d("signal", "elderly", "add", True), soft("elderly=suitable"))),
}
VEHICLE = {"motorbike": "Xe máy", "car": "Ô tô riêng", "ride": "Grab, taxi"}
# The common ways into Đà Lạt. The corpus holds none of them (it holds places visitors go to), so these are text
# that Planning geocodes; the question also takes free text for anything else.
ENTRY_POINTS = (
    ("bus_station", "Bến xe Liên tỉnh Đà Lạt"),
    ("airport", "Sân bay Liên Khương"),
    ("own_vehicle", "Tự lái, vào từ đèo Prenn"),
)
PURPOSE = {
    "relax": ("Nghỉ ngơi, thư giãn", (d("pace", "slow", inferred=True), soft("long_stay_chill=present"),
                                      soft("noise=quiet"))),
    "bond": ("Gắn kết người đi cùng", ()),
    "photo": ("Chụp ảnh", (soft("photo_spot=present"), soft("scenic_view=present"))),
    "food_culture": ("Ẩm thực, văn hóa", (soft("local_specialty_food=present"), soft("heritage_architecture=present"),
                                          soft("cultural_show=present"))),
    "nature": ("Thiên nhiên", (soft("nature=present"), soft("scenic_view=present"))),
    "explore": ("Khám phá nhiều nơi", (d("pace", "packed", inferred=True),)),
    "adventure": ("Trải nghiệm mạnh", (soft("adventure_activity=present"), soft("hiking=present"))),
}
VIBE = (("scenic_view=present", "View đồi núi"), ("cloud_hunting=present", "Săn mây"),
        ("nature=present", "Thiên nhiên, thác, rừng"), ("flower_garden=present", "Vườn hoa"),
        ("photo_spot=present", "Chụp ảnh đẹp"), ("long_stay_chill=present", "Ngồi lâu, chill"),
        ("pick_your_own=present", "Hái dâu, trái cây"), ("animals=present", "Có thú để chơi"),
        ("hiking=present", "Leo núi, trekking"), ("heritage_architecture=present", "Kiến trúc, di tích"),
        ("local_specialty_food=present", "Món đặc sản"), ("live_music=present", "Nhạc sống"))
SOFT_LABEL = dict(VIBE) | {
    "noise=quiet": "Yên tĩnh", "crowd=low": "Ít người", "scenic_view=present": "Có view",
    "cozy_decor=present": "Không gian ấm cúng", "drink_quality=good": "Đồ uống ngon", "food_quality=good": "Đồ ăn ngon",
    "cultural_show=present": "Biểu diễn văn hóa", "long_stay_chill=present": "Ngồi lâu được",
}
HARD_LABEL = {"steep_or_stairs": "tránh dốc và bậc thang", "long_walk": "không phải đi bộ xa",
              "vegetarian_options": "có món chay"}
WEEKDAY = ("mon", "tue", "wed", "thu", "fri", "sat", "sun")

READY = Question(qid="ready", group="I", tier=0, exits=False,
                 text="Mình đã hiểu đủ để tìm chỗ hợp với chuyến này. Xem gợi ý nhé? Bạn vẫn sửa được mọi dòng bên cạnh.",
                 chips=(Chip(id="show", label="Xem gợi ý"),))


# ---------- tier 1 ----------

def frame(state: TripState) -> Question:
    text = "Kể mình nghe chuyến đi bạn đang tính: đi mấy ngày, với ai, muốn trải nghiệm gì. Gõ tự nhiên, hoặc chọn nhanh bên dưới."
    if state.meta.start_with in ("saved", "must", "itinerary"):
        text += " Có sẵn nơi muốn đến thì dán tên hoặc link vào ô, mỗi dòng một nơi."
    chips = tuple(Chip(id=f"days:{n}", label=f"{n} ngày", row="Số ngày", drafts=(d("days", n),)) for n in (2, 3, 4, 5))
    chips += tuple(Chip(id=f"who:{k}", label=label, row="Đi với ai", drafts=dr) for k, (label, dr) in WHO.items())
    chips += tuple(Chip(id=f"mobility:{k}", label=label, row="Đi lại bằng", drafts=(d("mobility", k),))
                   for k, label in VEHICLE.items())
    return Question(qid="frame", group="A", tier=1, multi=True, single_rows=("Số ngày", "Đi lại bằng"), input="text",
                    exits=False, text=text, reason="Ba điều này quyết định nơi nào hợp và lịch có đi kịp không.",
                    chips=chips)


def days_q() -> Question:
    return Question(qid="days", group="A", tier=1, text="Chuyến này bạn đi mấy ngày?",
                    reason="Số ngày quyết định đi được bao nhiêu nơi.",
                    chips=tuple(Chip(id=f"days:{n}", label=f"{n} ngày", drafts=(d("days", n),)) for n in (1, 2, 3, 4, 5)))


def companions_q() -> Question:
    return Question(qid="companions", group="B", tier=1, multi=True, text="Bạn đi cùng ai?",
                    reason="Đi cùng ai đổi mạnh nơi nào hợp.",
                    chips=tuple(Chip(id=f"who:{k}", label=label, drafts=dr) for k, (label, dr) in WHO.items()))


def mobility_q() -> Question:
    return Question(qid="mobility", group="A", tier=1, text="Bạn đi lại trong Đà Lạt bằng gì?",
                    reason="Để ước lượng thời gian giữa các nơi.",
                    chips=tuple(Chip(id=f"mobility:{k}", label=label, drafts=(d("mobility", k),))
                                for k, label in VEHICLE.items()))


def dates_q() -> Question:
    return Question(qid="dates", group="A", tier=1, input="date", input_field="start_date", exits=False,
                    text="Bạn đi từ ngày nào?", reason="Để kiểm tra giờ mở cửa đúng ngày bạn đi.",
                    chips=(Chip(id="undecided", label="Chưa chốt ngày", drafts=(d("start_date", op="remove"),)),))


def c_effort(state: TripState) -> Question:
    kinds = {s.kind for s in pending_signals(state)}
    who = "người lớn tuổi" if kinds & {"elderly", "knee"} else "trẻ nhỏ" if "kids" in kinds else "người trong nhóm"
    handled = d("signal_handled", tuple(sorted(EFFORT_SIGNALS)))
    steep = d("hard", {"feature": "steep_or_stairs", "op": "ne", "value": "present"}, "add")
    walk = d("hard", {"feature": "long_walk", "op": "ne", "value": "present"}, "add")
    return Question(
        qid="c_effort", group="C", tier=1,
        text="Để tránh chỗ phải leo dốc: trong nhóm có ai ngại đi bộ xa hoặc lên nhiều bậc thang không? Bạn có thể bỏ qua.",
        reason=f"Đi cùng {who}, chỗ nhiều bậc dễ làm mệt cả buổi.",
        chips=(Chip(id="steep", label="Tránh dốc, bậc thang", drafts=(steep, handled)),
               Chip(id="walk", label="Không đi bộ xa", drafts=(walk, handled)),
               Chip(id="both", label="Tránh cả hai", drafts=(steep, walk, handled)),
               Chip(id="fine", label="Đi lại bình thường", drafts=(handled,))),
        exit_drafts=(handled,))


def c_other(state: TripState) -> Question:
    kinds = {s.kind for s in pending_signals(state)}
    chips = []
    if "vegetarian" in kinds:
        chips.append(Chip(id="veg", label="Cần quán có món chay", drafts=(
            d("hard", {"feature": "vegetarian_options", "op": "eq", "value": "yes"}, "add"),
            d("signal_handled", ("vegetarian",)))))
    if "motion_sick" in kinds:
        chips.append(Chip(id="pass", label="Tránh đường đèo dài", drafts=(
            d("unmapped", "tránh đường đèo dài (say xe)", "add"), d("signal_handled", ("motion_sick",)))))
    if "height" in kinds:
        chips.append(Chip(id="height", label="Tránh chỗ cao, cầu kính", drafts=(
            d("unmapped", "tránh chỗ cao, cầu kính", "add"), d("signal_handled", ("height",)))))
    handled = d("signal_handled", tuple(sorted(OTHER_SIGNALS)))
    chips.append(Chip(id="none", label="Không cần lọc", drafts=(handled,)))
    return Question(qid="c_other", group="C", tier=1, multi=True, text="Mình nên lưu ý gì để chuyến đi dễ chịu hơn?",
                    reason="Bạn vừa nhắc tới sức khỏe hoặc ăn uống; chọn để mình lọc đúng.", chips=tuple(chips),
                    exit_drafts=(handled,))


def policy_q(h: Hard, cov: Coverage) -> Question:
    label = HARD_LABEL.get(h.feature, h.feature)
    known = f"chỉ {cov.passed} nơi xác minh được" if cov.passed else "chưa nơi nào xác minh được"
    exclude, flag = d("hard_policy", (h.feature, "exclude")), d("hard_policy", (h.feature, "flag"))
    return Question(qid=f"policy:{h.feature}", group="C", tier=1,
                    text=f"Để {label}: {known}, {cov.unknown} nơi chưa có thông tin. Bạn muốn?",
                    reason="Mình không coi nơi chưa có thông tin là an toàn.",
                    chips=(Chip(id="exclude", label="Chỉ nơi đã xác minh", drafts=(exclude,)),
                           Chip(id="flag", label="Xem cả nơi chưa rõ, gắn cờ", drafts=(flag,))),
                    exit_drafts=(exclude,))


def anchor_pick(i: int, a: Anchor, catalog: Catalog) -> Question:
    chips = tuple(Chip(id=pid, label=catalog.by_id[pid].name, drafts=(d("anchor_pick", (i, pid)),))
                  for pid in a.candidates if pid in catalog.by_id)
    none = d("anchor_pick", (i, None))
    return Question(qid=f"anchor:{i}", group="E", tier=1, text=f"“{a.text}” là nơi nào?",
                    reason="Tên này khớp nhiều nơi; mình không đoán.",
                    chips=chips + (Chip(id="none", label="Không phải nơi nào ở đây", drafts=(none,)),),
                    exit_drafts=(none,))


def closed_conflict(state: TripState, catalog: Catalog) -> Question | None:
    start, days = state.start_date.value, state.days.value or 1
    if start is None:
        return None
    for i, a in enumerate(state.anchors):
        c = catalog.by_id.get(a.place_id or "")
        if a.state != "matched" or c is None or c.hours is None or f"closed:{i}" in state.meta.asked:
            continue
        closed = [day for k in range(days) if (day := start + timedelta(k)) and c.hours.get(WEEKDAY[day.weekday()]) == ()]
        if closed:
            when = ", ".join(x.strftime("%d/%m") for x in closed)
            return Question(qid=f"closed:{i}", group="E", tier=1, exits=False,
                            text=f"{c.name} đóng cửa ngày {when} trong chuyến của bạn. Bạn muốn?",
                            reason="Theo giờ mở cửa trên Google Maps.",
                            chips=(Chip(id="redate", label="Đổi ngày đi", drafts=(d("start_date", op="remove", inferred=True),)),
                                   Chip(id="drop", label="Bỏ nơi này", drafts=(d("anchor", i, "remove"),)),
                                   Chip(id="keep", label="Vẫn giữ, xếp vào ngày khác")))
    return None


def required(state: TripState, catalog: Catalog, cfg: Settings) -> Question | None:
    """Tier 1: safety, blocking fields, ambiguous anchors, real conflicts. The guard forces these."""
    skipped, asked = state.meta.skipped, state.meta.asked
    pending = {s.kind for s in pending_signals(state)}
    if pending & EFFORT_SIGNALS:
        return c_effort(state)
    if pending & OTHER_SIGNALS:
        return c_other(state)
    for h in state.hard:
        if h.unknown_policy is None:
            cov = coverage(h, catalog.places, cfg.enough)
            if cov.level != "enough":
                return policy_q(h, cov)
    for i, a in enumerate(state.anchors):
        if a.state == "choose":
            return anchor_pick(i, a, catalog)
    if "frame" not in asked and not (state.days.known and state.companions.known and state.mobility.known):
        return frame(state)
    for field, build in (("days", days_q), ("companions", companions_q), ("mobility", mobility_q)):
        if not getattr(state, field).known and field not in skipped:
            return build()
    if not (state.start_date.known or state.month.known or state.start_date.status == "skipped" or "dates" in skipped):
        return dates_q()
    return closed_conflict(state, catalog)


# ---------- tier 2-3 ----------

def purpose_q() -> Question:
    return Question(qid="purpose", group="G", tier=2, text="Chuyến này chủ yếu để làm gì?",
                    reason="Biết mục đích, mình chọn đúng kiểu nơi hơn.",
                    chips=tuple(Chip(id=k, label=label, drafts=(d("purpose", k),) + dr)
                                for k, (label, dr) in PURPOSE.items()))


def vibe_q(catalog: Catalog, cfg: Settings) -> Question | None:
    chips = tuple(Chip(id=key, label=label, drafts=(d("soft", (key, "love"), "add"),))
                  for key, label in VIBE if catalog.count(key) >= cfg.top_k)
    if len(chips) < 2:
        return None
    return Question(qid="vibe", group="G", multi=True, cost=1.2, chips=chips,
                    text="Bạn muốn có những khoảnh khắc nào? Chọn bao nhiêu cũng được.",
                    reason="Chỉ hiện những kiểu mình có đủ đánh giá để kiểm.")


def clarify_q(state: TripState) -> Question | None:
    if not state.meta.pending:
        return None
    a = state.meta.pending[0]
    done = d("pending", a.phrase, "remove")
    return Question(qid=f"clarify:{a.phrase}", group="I", tier=2, multi=True,
                    text=f"“{a.phrase}” với bạn là gì? Chọn những ý đúng.",
                    reason="Mỗi người hiểu từ này một kiểu, mình hỏi để không đoán sai.",
                    chips=tuple(Chip(id=f"k{i}", label=SOFT_LABEL.get(k, k), drafts=(d("soft", (k, "love"), "add"), done))
                                for i, k in enumerate(a.keys)),
                    exit_drafts=(done,))


def show_first_q() -> Question:
    return Question(qid="show_first", group="I", tier=2, exits=False,
                    text="Bạn muốn xem vài gợi ý trước rồi chỉnh tiếp không?",
                    chips=(Chip(id="show", label="Xem gợi ý"), Chip(id="more", label="Hỏi tiếp")))


def bank(state: TripState, catalog: Catalog, cfg: Settings) -> list[Question]:
    done = set(state.meta.asked) | state.meta.skipped
    out: list[Question] = []

    def want(qid: str, cond: bool) -> bool:
        return cond and qid not in done

    if want("purpose", not state.purpose.known):
        out.append(purpose_q())
    experience = ontology().features
    has_wish = any(f.value == "love" and experience[SoftKey.parse(k).feature].group == "experience"
                   for k, f in state.soft.items())
    if want("vibe", not has_wish) and (q := vibe_q(catalog, cfg)):
        out.append(q)
    if want("crowd", not state.crowd_tolerance.known):
        out.append(Question(qid="crowd", group="F", text="Chỗ đông người thì sao?",
                            reason="Nhiều nơi đẹp nhưng rất đông vào giờ cao điểm.", chips=(
                Chip(id="avoid", label="Tránh chỗ đông", drafts=(d("crowd_tolerance", "avoid"),
                                                                 d("soft", ("crowd=low", "love"), "add"))),
                Chip(id="ok", label="Chấp nhận nếu đáng", drafts=(d("crowd_tolerance", "ok_if_worth"),)),
                Chip(id="fine", label="Không ngại", drafts=(d("crowd_tolerance", "fine"),)))))
    if want("pace", not state.pace.known):
        out.append(Question(qid="pace", group="F", text="Mỗi ngày bạn muốn đi thế nào?",
                            reason="Để xếp số nơi mỗi ngày vừa sức.", chips=(
                Chip(id="slow", label="Thong thả, ít nơi", drafts=(d("pace", "slow"),)),
                Chip(id="normal", label="Vừa phải", drafts=(d("pace", "normal"),)),
                Chip(id="packed", label="Đi được nhiều", drafts=(d("pace", "packed"),)))))
    if want("max_leg", not state.max_leg_min.known):
        out.append(Question(qid="max_leg", group="F", text="Một chặng di chuyển tối đa bao lâu thì bạn vẫn thấy ổn?",
                            reason="Đà Lạt đường đèo, nơi xa có thể mất cả tiếng.",
                            chips=tuple(Chip(id=str(m), label=f"Dưới {m} phút", drafts=(d("max_leg_min", m),))
                                        for m in (15, 30, 60))))
    if want("budget", not state.budget_vnd.known):
        out.append(Question(qid="budget", group="D", cost=2.0,
                            text="Mức chi cho ăn uống và vé, mỗi người mỗi ngày khoảng bao nhiêu? Bạn có thể bỏ qua.",
                            reason="Để tránh nơi vượt mức bạn muốn chi.", chips=(
                Chip(id="low", label="Dưới 300 nghìn", drafts=(d("budget_vnd", 300_000),)),
                Chip(id="mid", label="300–700 nghìn", drafts=(d("budget_vnd", 700_000),)),
                Chip(id="high", label="Trên 700 nghìn", drafts=(d("budget_vnd", 1_500_000),)))))
    if want("novelty", state.meta.experience == "returning" and not state.novelty.known):
        out.append(Question(qid="novelty", group="H", text="Lần này bạn muốn quay lại chỗ quen hay thử cái mới?",
                            reason="Để bớt những nơi bạn đã đi.", chips=(
                Chip(id="familiar", label="Theo gu quen", drafts=(d("novelty", "familiar"),)),
                Chip(id="new", label="Thử cái mới", drafts=(d("novelty", "new"),)),
                Chip(id="mix", label="Trộn cả hai", drafts=(d("novelty", "mix"),)))))
    matched = [(i, a) for i, a in enumerate(state.anchors) if a.state == "matched"]
    if want("base", not state.base.known and (len(matched) >= 2 or state.max_leg_min.known)):
        out.append(Question(qid="base", group="A", cost=1.5, input="place", input_field="base",
                            text="Bạn ở khu nào? Chọn một nơi gần chỗ ở.", reason="Để tính đường đi mỗi ngày."))
    if want("entry_exit", state.days.known and not (state.entry_point.known and state.exit_point.known)):
        out.append(Question(
            qid="entry_exit", group="A", cost=1.5, multi=True, input="text", input_field="entry_point",
            single_rows=("Tới Đà Lạt bằng", "Rời Đà Lạt từ"),
            text="Bạn tới Đà Lạt từ đâu, và rời từ đâu?",
            reason="Để ngày đầu và ngày cuối tính đúng đoạn từ nơi bạn xuống xe.",
            chips=tuple(Chip(id=f"in:{key}", label=label, row="Tới Đà Lạt bằng",
                             drafts=(d("entry_point", Base(text=label)),))
                        for key, label in ENTRY_POINTS)
                  + tuple(Chip(id=f"out:{key}", label=label, row="Rời Đà Lạt từ",
                               drafts=(d("exit_point", Base(text=label)),))
                          for key, label in ENTRY_POINTS)))
    if want("times", state.days.known and not state.arrive_at.known):
        out.append(Question(qid="times", group="A", multi=True, single_rows=("Ngày đầu tới lúc", "Ngày cuối rời lúc"),
                            text="Ngày đầu bạn tới lúc nào, ngày cuối rời Đà Lạt lúc nào?",
                            reason="Để không xếp lịch trùng giờ xe.",
                            chips=tuple(Chip(id=f"arrive:{h}", label=f"{h}h", row="Ngày đầu tới lúc",
                                             drafts=(d("arrive_at", f"{h:02d}:00"),)) for h in (7, 9, 12, 15))
                            + tuple(Chip(id=f"leave:{h}", label=f"{h}h", row="Ngày cuối rời lúc",
                                         drafts=(d("leave_at", f"{h:02d}:00"),)) for h in (12, 15, 19))))
    if want("anchor_priority", len(matched) >= 2 and all(a.priority == "must" for _, a in matched)):
        out.append(Question(qid="anchor_priority", group="E", multi=True, cost=1.2,
                            text="Nếu không đủ thời gian, nơi nào có thể bỏ trước?",
                            reason="Để biết nơi nào phải giữ bằng mọi giá.",
                            chips=tuple(Chip(id=f"a{i}", label=catalog.by_id[a.place_id].name,
                                             drafts=(d("anchor_priority", (i, "want")),))
                                        for i, a in matched if a.place_id in catalog.by_id)))
    return out


def shortlist(state: TripState, catalog: Catalog, cfg: Settings) -> list[str]:
    weights = []
    for key, f in state.soft.items():
        if f.value in ("love", "avoid"):
            weights.append((SoftKey.parse(key), 1 if f.value == "love" else -1))
    skip = set(state.visited) if state.novelty.value == "new" else set()
    scored = []
    for c in catalog.places:
        if c.id in skip or not admissible(c, state.hard):
            continue
        s = sum(w for k, w in weights if c.value(k.feature, k.context) == k.value)
        scored.append((-s, -c.weight, c.id))
    scored.sort()
    return [pid for *_, pid in scored[:cfg.top_k]]


def rank_questions(state: TripState, catalog: Catalog, cfg: Settings) -> list[tuple[Question, float]]:
    """impact = mean over chips of how much the top-K changes; score = impact / cost (docs/TRIP_UNDERSTANDING.md §8)."""
    now = set(shortlist(state, catalog, cfg))
    out = []
    for q in bank(state, catalog, cfg):
        chips = [c for c in q.chips if c.drafts]
        if not chips:
            out.append((q, 0.0))
            continue
        impact = 0.0
        for chip in chips:
            alt = set(shortlist(apply_drafts(state, chip.drafts, state.meta.turn, f"rank:{q.qid}"), catalog, cfg))
            union = now | alt
            impact += 1 - len(now & alt) / len(union) if union else 0.0
        out.append((q, impact / len(chips) / q.cost))
    return sorted(out, key=lambda x: -x[1])
