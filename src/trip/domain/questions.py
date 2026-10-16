"""Deterministic quiz bank for the quiz phase (docs/TRIP_UNDERSTANDING.md §5).

Every chip carries the updates it writes (Draft), so answering a chip never needs
the model: the engine applies the drafts and moves to the next question. The chat
phase (agent loop) covers everything free-form; this bank only asks what is still
unknown, in a fixed order, safety first.

Every quiz card ends with an "other" chip (the user types instead of picking) and
the standard exits (skip / unsure). A typed answer never writes directly: it goes
through the other-gate (prepass, then Clef OTHER_CLARITY), and lands in the chat
phase with `pending_other` when unclear.
"""

from __future__ import annotations

from datetime import timedelta

from ..infrastructure.catalog import Catalog
from ..infrastructure.settings import Settings
from .card import Chip, Question
from .coverage import coverage
from .rental import rental_params
from .state import (EFFORT_SIGNALS, OTHER_SIGNALS, Anchor, Base, Draft, Hard, SoftKey, TripState, apply_drafts,
                    ontology, pending_signals)

# ---------- card ids the engine routes on ----------

OFFER_QID = "offer_quiz"  # the F transition card: quiz / keep chatting / show now
REVIEW_QID = "review"     # the review card after the quiz queue is empty
OTHER_CHIP = "other"      # "Khác, tự gõ": the answer comes as typed text
TO_QUIZ, STAY_CHAT = "to_quiz", "stay_chat"

# quiz qid -> TripState field a typed answer may fill directly (None: typed text
# always goes to the chat phase). "stay_times" fills checkin_at and/or checkout_at.
QUIZ_FIELD: dict[str, str | None] = {
    "days": "days", "nights": "nights", "companions": "companions", "mobility": "mobility", "dates": "start_date",
    "purpose": "purpose", "vibe": "soft", "crowd": "crowd_tolerance", "pace": "pace",
    "budget": "budget_vnd", "novelty": "novelty", "arrival": "arrival_mode", "stay_times": "checkin_at",
    "origin": None, "inbound": None, "outbound": None, "lodging": None,  # picked from a search: typed text goes to the chat
    "c_effort": None, "c_other": None, "anchor_priority": None, "care": None,
}

FIELD_LABEL = {"days": "số ngày", "nights": "số đêm", "companions": "người đi cùng", "mobility": "phương tiện di chuyển",
               "start_date": "ngày đi", "purpose": "mục đích chuyến đi", "soft": "sở thích",
               "crowd_tolerance": "độ đông", "pace": "nhịp độ", "budget_vnd": "ngân sách", "novelty": "đi chỗ quen hay thử cái mới",
               "arrival_mode": "cách tới Đà Lạt", "checkin_at": "giờ nhận phòng và trả phòng", "unmapped": "ý này"}


def pending_fields(qid: str) -> list[str]:
    """TripState fields whose change resolves the pending quiz card (other-gate)."""
    if qid in QUIZ_FIELD:
        if qid == "stay_times":
            return ["checkin_at", "checkout_at"]
        if qid in ("origin", "lodging"):
            return [qid, "lodging_booked"] if qid == "lodging" else [qid]
        if qid in ("inbound", "outbound"):
            return [qid]
        if qid == "dates":
            return ["start_date", "month", "month_part"]
        return [QUIZ_FIELD[qid]] if QUIZ_FIELD[qid] else []
    if qid in ("c_effort", "c_other", "care"):
        return ["signal", "hard", "unmapped"]
    if qid.startswith("policy:"):
        return ["hard"]
    if qid.startswith("anchor:"):
        return ["anchor"]
    if qid.startswith("closed:"):
        return ["start_date", "anchor"]
    if qid == "anchor_priority":
        return ["anchor"]
    return []

# policy:<feature>, anchor:<i> and closed:<i> are safety cards with their own flow.
SAFETY_PREFIXES = ("policy:", "anchor:", "closed:")


def is_quiz(qid: str) -> bool:
    """Whether this card id belongs to the quiz phase (offer/review excluded)."""
    return qid in QUIZ_FIELD or qid in ("c_effort", "c_other", "anchor_priority", "care") \
        or qid.startswith(SAFETY_PREFIXES)


def foundation_ok(state: TripState) -> bool:
    """The chat phase gathered enough to offer the quiz: the trip foundation plus
    no open health hint (safety questions come first inside the quiz instead)."""
    return state.days.known and state.companions.known and state.mobility.known \
        and (state.start_date.known or state.month.known) and not pending_signals(state)


def d(field: str, value=None, op: str = "set", inferred: bool = False) -> Draft:
    return Draft(field=field, op=op, value=value, inferred=inferred)


def soft(key: str) -> Draft:
    return d("soft", (key, "love"), "add", inferred=True)


def other_chip() -> Chip:
    return Chip(id=OTHER_CHIP, label="Khác, tự gõ")


def with_other(q: Question) -> Question:
    """Every quiz card lets the user type instead of picking."""
    if any(c.id == OTHER_CHIP for c in q.chips):
        return q
    return q.model_copy(update={"chips": q.chips + (other_chip(),)})


WHO = {
    "solo": ("Một mình", (d("companions", "solo", "add"),)),
    "partner": ("Người yêu, vợ chồng", (d("companions", "partner", "add"), soft("couples=suitable"))),
    "friends": ("Bạn bè", (d("companions", "friends", "add"), soft("groups=suitable"))),
    "kids": ("Có trẻ nhỏ", (d("companions", "kids", "add"), d("signal", "kids", "add", True), soft("kids=suitable"))),
    "parents": ("Bố mẹ, người lớn tuổi",
                (d("companions", "parents", "add"), d("signal", "elderly", "add", True), soft("elderly=suitable"),
                 d("hard", {"feature": "fit.parents", "op": "ne", "value": "bad"}, "add"))),
    # a companion with a limit of its own: the place must not be known to be bad for them (hard, unknown stays unverified)
    "baby": ("Có em bé", (d("companions", "baby", "add"), d("hard", {"feature": "fit.baby", "op": "ne", "value": "bad"}, "add"))),
    "pet": ("Có thú cưng", (d("companions", "pet", "add"), d("hard", {"feature": "pets", "op": "ne", "value": "not_allowed"}, "add"))),
    "coworkers": ("Đồng nghiệp", (d("companions", "coworkers", "add"),)),
}
VEHICLE = {"motorbike": "Xe máy", "car": "Ô tô riêng"}
# A trip that arrives by coach or plane has no vehicle of its own: it rents one in the city, or walks around the area.
RENTAL_VEHICLE = {"motorbike": "Thuê xe máy", "car": "Thuê ô tô", "walk": "Không thuê, chỉ đi bộ quanh khu"}
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


# ---------- transition + review cards (engine-built, not part of the queue) ----------

def review_card() -> Question:
    """After the quiz queue is empty: an open chat box to adjust or add anything."""
    return Question(qid=REVIEW_QID, group="I", tier=0, custom=True, input="text", exits=False,
                    text="Bạn muốn chỉnh gì thêm, hay có nơi cụ thể nào phải đến không?",
                    reason="Xem lại bản hiểu nhu cầu bên cạnh rồi chốt.",
                    chips=(Chip(id="show", label="Xong, xem gợi ý"),))


# ---------- safety first ----------

def c_effort(state: TripState) -> Question:
    kinds = {s.kind for s in pending_signals(state)}
    who = "người lớn tuổi" if kinds & {"elderly", "knee"} else "trẻ nhỏ" if "kids" in kinds else "người trong nhóm"
    handled = d("signal_handled", tuple(sorted(EFFORT_SIGNALS)))
    steep = d("hard", {"feature": "steep_or_stairs", "op": "ne", "value": "present"}, "add")
    walk = d("hard", {"feature": "long_walk", "op": "ne", "value": "present"}, "add")
    return with_other(Question(
        qid="c_effort", group="C", tier=1,
        text="Để tránh chỗ phải leo dốc: trong nhóm có ai ngại đi bộ xa hoặc lên nhiều bậc thang không? Bạn có thể bỏ qua.",
        reason=f"Đi cùng {who}, chỗ nhiều bậc dễ làm mệt cả buổi.",
        chips=(Chip(id="steep", label="Tránh dốc, bậc thang", drafts=(steep, handled)),
               Chip(id="walk", label="Không đi bộ xa", drafts=(walk, handled)),
               Chip(id="both", label="Tránh cả hai", drafts=(steep, walk, handled)),
               Chip(id="fine", label="Đi lại bình thường", drafts=(handled,))),
        exit_drafts=(handled,)))


def c_other(state: TripState) -> Question:
    kinds = {s.kind for s in pending_signals(state)}
    chips = []
    if "vegetarian" in kinds:
        chips.append(Chip(id="veg", label="Cần quán có món chay", drafts=(
            d("hard", {"feature": "vegetarian_options", "op": "eq", "value": "yes"}, "add"),
            d("signal_handled", ("vegetarian",)))))
    if "vegan" in kinds:
        chips.append(Chip(id="vegan", label="Cần món thuần chay", drafts=(
            d("hard", {"feature": "vegan_options", "op": "eq", "value": "yes", "scope": "eating"}, "add"),
            d("signal_handled", ("vegan",)))))
    if "motion_sick" in kinds:
        chips.append(Chip(id="pass", label="Tránh đường đèo dài", drafts=(
            d("unmapped", "tránh đường đèo dài (say xe)", "add"), d("signal_handled", ("motion_sick",)))))
    if "height" in kinds:
        chips.append(Chip(id="height", label="Tránh chỗ cao, cầu kính", drafts=(
            d("unmapped", "tránh chỗ cao, cầu kính", "add"), d("signal_handled", ("height",)))))
    handled = d("signal_handled", tuple(sorted(OTHER_SIGNALS)))
    chips.append(Chip(id="none", label="Không cần lọc", drafts=(handled,)))
    return with_other(Question(qid="c_other", group="C", tier=1, multi=True, text="Mình nên lưu ý gì để chuyến đi dễ chịu hơn?",
                               reason="Bạn vừa nhắc tới sức khỏe hoặc ăn uống; chọn để mình lọc đúng.", chips=tuple(chips),
                               exit_drafts=(handled,)))


def strictest(state: TripState) -> list[Draft]:
    """What Next writes for a health / body / diet hint nobody answered: the strictest choice of its card, as a guess
    the user can remove on the ticket. It only ever adds a limit, so no physical constraint is loosened."""
    kinds = {s.kind for s in pending_signals(state)}
    out: list[Draft] = []
    if kinds & EFFORT_SIGNALS:
        out += next(c.drafts for c in c_effort(state).chips if c.id == "both")
    if kinds & OTHER_SIGNALS:
        out += [dr for c in c_other(state).chips if c.id not in ("none", OTHER_CHIP) for dr in c.drafts]
    return [dr.model_copy(update={"inferred": True}) for dr in out]


def policy_q(h: Hard, catalog: Catalog, cfg: Settings, activities=None) -> Question:
    cov = coverage(h, catalog.places, cfg.enough, activities)
    label = HARD_LABEL.get(h.feature, h.feature)
    known = f"chỉ {cov.passed} nơi xác minh được" if cov.passed else "chưa nơi nào xác minh được"
    exclude, flag = d("hard_policy", (h.feature, "exclude")), d("hard_policy", (h.feature, "flag"))
    return with_other(Question(qid=f"policy:{h.feature}", group="C", tier=1,
                               text=f"Để {label}: {known}, {cov.unknown} nơi chưa có thông tin. Bạn muốn?",
                               reason="Mình không coi nơi chưa có thông tin là an toàn.",
                               chips=(Chip(id="exclude", label="Chỉ nơi đã xác minh", drafts=(exclude,)),
                                      Chip(id="flag", label="Xem cả nơi chưa rõ, gắn cờ", drafts=(flag,))),
                               exit_drafts=(exclude,)))


def anchor_pick(i: int, a: Anchor, catalog: Catalog) -> Question:
    chips = tuple(Chip(id=pid, label=catalog.by_id[pid].name, drafts=(d("anchor_pick", (i, pid)),))
                  for pid in a.candidates if pid in catalog.by_id)
    none = d("anchor_pick", (i, None))
    return with_other(Question(qid=f"anchor:{i}", group="E", tier=1, text=f"“{a.text}” là nơi nào?",
                               reason="Tên này khớp nhiều nơi; mình không đoán.",
                               chips=chips + (Chip(id="none", label="Không phải nơi nào ở đây", drafts=(none,)),),
                               exit_drafts=(none,)))


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
            return with_other(Question(qid=f"closed:{i}", group="E", tier=1, exits=False,
                                       text=f"{c.name} đóng cửa ngày {when} trong chuyến của bạn. Bạn muốn?",
                                       reason="Theo giờ mở cửa trên Google Maps.",
                                       chips=(Chip(id="redate", label="Đổi ngày đi",
                                                   drafts=(d("start_date", op="remove", inferred=True),)),
                                              Chip(id="drop", label="Bỏ nơi này", drafts=(d("anchor", i, "remove"),)),
                                              Chip(id="keep", label="Vẫn giữ, xếp vào ngày khác"))))
    return None


def safety_queue(state: TripState, catalog: Catalog, cfg: Settings) -> list[Question]:
    """Open safety items, in the order they must be answered. Skipped ones (asked)
    never come back."""
    done = set(state.meta.asked)
    out: list[Question] = []
    pending = {s.kind for s in pending_signals(state)}
    if pending & EFFORT_SIGNALS and "c_effort" not in done:
        out.append(c_effort(state))
    if pending & OTHER_SIGNALS and "c_other" not in done:
        out.append(c_other(state))
    for h in state.hard:
        if h.unknown_policy is None and f"policy:{h.feature}" not in done:
            cov = coverage(h, catalog.places, cfg.enough, state.activities)
            if cov.level != "enough":
                out.append(policy_q(h, catalog, cfg, state.activities))
    for i, a in enumerate(state.anchors):
        if a.state == "choose" and f"anchor:{i}" not in done:
            out.append(anchor_pick(i, a, catalog))
    if (q := closed_conflict(state, catalog)) is not None:
        out.append(q)
    return out


# ---------- foundation ----------

def days_q() -> Question:
    def chip(n: int) -> Chip:
        label = "Đi về trong ngày" if n == 1 else f"{n} ngày {n - 1} đêm"
        return Chip(id=f"days:{n}", label=label, drafts=(d("days", n), d("nights", n - 1)))
    return with_other(Question(
        qid="days", group="A", tier=1, text="Bạn định đi mấy ngày mấy đêm?",
        reason="Ngày đầu tính từ lúc bạn tới, ngày cuối đến lúc bạn về: “3 ngày 2 đêm” là 3 buổi đi chơi và 2 đêm ngủ lại. "
               "Mình chia số nơi mỗi ngày và tính tiền phòng theo đó.",
        chips=tuple(chip(n) for n in (1, 2, 3, 4, 5, 7, 14))))


def care_q() -> Question:
    """Asked once, right after "who goes": anything about health, injury, diet or allergy that should shape the trip.
    One open card instead of a follow-up card per hint: each chip carries its own limit (the same drafts the
    c_effort / c_other cards write) and marks its signal handled, so a chosen chip needs no second question. Allergy has
    no verified feature in the data: it is kept as a note the user is reminded of, never as a filter. "Không có" writes
    nothing; a hint typed in the box goes through the same rules as in chat."""
    steep = d("hard", {"feature": "steep_or_stairs", "op": "ne", "value": "present"}, "add")
    walk = d("hard", {"feature": "long_walk", "op": "ne", "value": "present"}, "add")
    veg = d("hard", {"feature": "vegetarian_options", "op": "eq", "value": "yes"}, "add")
    vegan = d("hard", {"feature": "vegan_options", "op": "eq", "value": "yes", "scope": "eating"}, "add")
    chips = (
        Chip(id="none", label="Không có gì cần lưu ý"),
        Chip(id="knee", label="Đau chân, khó đi bộ hoặc leo bậc",
             drafts=(d("signal", "knee", "add"), steep, walk, d("signal_handled", ("knee",)))),
        Chip(id="wheelchair", label="Có người dùng xe lăn",
             drafts=(d("signal", "wheelchair", "add"), d("hard", {"feature": "fit.wheelchair", "op": "ne", "value": "bad"}, "add"))),
        Chip(id="pregnant", label="Có người đang mang thai",
             drafts=(d("signal", "pregnant", "add"), steep, walk, d("hard", {"feature": "fit.pregnant", "op": "ne", "value": "bad"}, "add"),
                     d("signal_handled", ("pregnant",)))),
        Chip(id="veg", label="Ăn chay", drafts=(d("signal", "vegetarian", "add"), veg, d("signal_handled", ("vegetarian",)))),
        Chip(id="vegan", label="Ăn thuần chay", drafts=(d("signal", "vegan", "add"), vegan, d("signal_handled", ("vegan",)))),
        Chip(id="allergy", label="Dị ứng hoặc kiêng một số món",
             drafts=(d("unmapped", "dị ứng hoặc kiêng món: dữ liệu chưa kiểm được từng chất, bạn hỏi quán trước khi gọi", "add"),)),
        Chip(id="motion", label="Say xe, ngại đường đèo dài",
             drafts=(d("signal", "motion_sick", "add"), d("unmapped", "tránh đường đèo dài (say xe)", "add"),
                     d("signal_handled", ("motion_sick",)))),
        Chip(id="height", label="Sợ độ cao",
             drafts=(d("signal", "height", "add"), d("unmapped", "tránh chỗ cao, cầu kính", "add"),
                     d("signal_handled", ("height",)))))
    return Question(qid="care", group="C", tier=1, multi=True,
                    text="Trong nhóm có ai cần mình lưu ý gì không? Ví dụ sức khỏe, chấn thương, ăn chay hay dị ứng.",
                    reason="Chọn một lần là đủ. Mình sẽ tránh xếp vào chỗ không hợp ngay từ đầu và không hỏi lại từng mục.",
                    chips=chips + (other_chip(),))


def companions_q() -> Question:
    return with_other(Question(qid="companions", group="B", tier=1, multi=True, text="Bạn đi cùng ai?",
                               reason="Đi với trẻ nhỏ, bố mẹ hay người yêu cần những chỗ rất khác nhau.",
                               chips=tuple(Chip(id=f"who:{k}", label=label, drafts=dr)
                                           for k, (label, dr) in WHO.items())))


def mobility_q(arrival: str | None = None, entry: Base | None = None) -> Question:
    """How the trip gets around the city. Arriving by coach or plane (`arrival`), the card is the rental guide: rental
    points near the station / airport (`input` "rental", `params` for /rentals; measured from `entry` when it has a
    point), and the chips say whether to rent a motorbike, rent a car, or not rent and only walk the area."""
    if arrival not in ("bus", "plane"):
        return with_other(Question(qid="mobility", group="A", tier=1, text="Bạn đi lại trong Đà Lạt bằng gì?",
                                   reason="Xe máy và ô tô đi được những đường khác nhau; mình dùng để ước lượng thời gian giữa các nơi.",
                                   chips=tuple(Chip(id=f"mobility:{k}", label=label, drafts=(d("mobility", k),))
                                               for k, label in VEHICLE.items())))
    return with_other(Question(
        qid="mobility", group="A", tier=1, input="rental", params=rental_params(arrival, entry),
        text="Bạn tới Đà Lạt bằng " + ("xe khách" if arrival == "bus" else "máy bay") + ", vậy trong thành phố bạn đi lại bằng gì?",
        reason="Đi xe máy là cách dễ nhất để đi nhiều nơi; mình gợi ý điểm thuê gần nơi bạn xuống. Không thuê xe thì chỉ đi bộ quanh khu.",
        chips=tuple(Chip(id=f"mobility:{k}", label=label, drafts=(d("mobility", k),)) for k, label in RENTAL_VEHICLE.items())))


def dates_q() -> Question:
    return with_other(Question(qid="dates", group="A", tier=1, input="date", input_field="start_date",
                               text="Bạn dự định đi từ ngày nào?", reason="Mình kiểm tra giờ mở cửa và thời tiết đúng những ngày bạn đi. Chưa chốt cũng được.",
                               chips=(Chip(id="undecided", label="Chưa chốt ngày", drafts=(d("start_date", op="remove"),)),)))


# ---------- tastes ----------

def purpose_q() -> Question:
    return with_other(Question(qid="purpose", group="G", tier=2, multi=True,
                               text="Chuyến này bạn muốn gì nhất? Chọn bao nhiêu cũng được.",
                               reason="Biết mục đích, mình chọn đúng kiểu nơi: nghỉ ngơi thì ít nơi và thong thả, khám phá thì nhiều nơi hơn.",
                               chips=tuple(Chip(id=k, label=label, drafts=(d("purpose", k),) + dr)
                                           for k, (label, dr) in PURPOSE.items())))


def vibe_q(catalog: Catalog, cfg: Settings) -> Question | None:
    chips = tuple(Chip(id=key, label=label, drafts=(d("soft", (key, "love"), "add"),))
                  for key, label in VIBE if catalog.count(key) >= cfg.top_k)
    if len(chips) < 2:
        return None
    return with_other(Question(qid="vibe", group="G", multi=True, chips=chips,
                               text="Bạn thích những khoảnh khắc nào? Chọn bao nhiêu cũng được.",
                               reason="Chỉ hiện những kiểu mình có đủ đánh giá để kiểm."))


def crowd_q() -> Question:
    return with_other(Question(qid="crowd", group="F", text="Bạn thấy chỗ đông người thế nào?",
                               reason="Nhiều nơi đẹp rất đông vào giờ cao điểm; nếu bạn ngại, mình tránh hoặc xếp vào giờ vắng hơn.", chips=(
        Chip(id="avoid", label="Tránh chỗ đông", drafts=(d("crowd_tolerance", "avoid"),
                                                         d("soft", ("crowd=low", "love"), "add"))),
        Chip(id="ok", label="Chấp nhận nếu đáng", drafts=(d("crowd_tolerance", "ok_if_worth"),)),
        Chip(id="fine", label="Không ngại", drafts=(d("crowd_tolerance", "fine"),)))))


def pace_q() -> Question:
    return with_other(Question(qid="pace", group="F", text="Mỗi ngày bạn muốn đi thư thả hay đi được nhiều nơi?",
                               reason="Mình xếp số nơi mỗi ngày vừa sức theo lựa chọn này.", chips=(
        Chip(id="slow", label="Thong thả, ít nơi", drafts=(d("pace", "slow"),)),
        Chip(id="normal", label="Vừa phải", drafts=(d("pace", "normal"),)),
        Chip(id="packed", label="Đi được nhiều", drafts=(d("pace", "packed"),)))))


def budget_q() -> Question:
    return with_other(Question(qid="budget", group="D",
                               text="Mỗi người mỗi ngày bạn dự chi khoảng bao nhiêu cho ăn uống và vé? Bỏ qua cũng được.",
                               reason="Để tránh gợi ý nơi vượt mức bạn muốn chi. Tiền phòng mình tính riêng.", chips=(
        Chip(id="low", label="Dưới 300 nghìn", drafts=(d("budget_vnd", 300_000),)),
        Chip(id="mid", label="300–700 nghìn", drafts=(d("budget_vnd", 700_000),)),
        Chip(id="high", label="Trên 700 nghìn", drafts=(d("budget_vnd", 1_500_000),)))))


def novelty_q() -> Question:
    return with_other(Question(qid="novelty", group="H", text="Lần này bạn muốn quay lại chỗ quen hay thử chỗ mới?",
                               reason="Nếu muốn thử mới, mình bớt những nơi bạn đã đi.", chips=(
        Chip(id="familiar", label="Theo gu quen", drafts=(d("novelty", "familiar"),)),
        Chip(id="new", label="Thử cái mới", drafts=(d("novelty", "new"),)),
        Chip(id="mix", label="Trộn cả hai", drafts=(d("novelty", "mix"),)))))


def stay_times_q() -> Question:
    """The hours the user wants the trip to start and end: lodging check-in on the first day, check-out on the last.
    Asked whether or not a lodging is booked; a skipped answer leaves the planner to suggest the hours."""
    return with_other(Question(
        qid="stay_times", group="A", multi=True, single_rows=("Ngày đầu bắt đầu đi lúc", "Ngày cuối phải xong lúc"),
        text="Ngày đầu bạn bắt đầu đi được từ mấy giờ, và ngày cuối cần xong lúc mấy giờ?",
        reason="Hai mốc này là quỹ thời gian thật của chuyến: giờ bạn tới hoặc nhận phòng, giờ trả phòng hoặc ra bến xe, sân bay. "
               "Chưa đặt chỗ ở cũng chọn được.",
        chips=tuple(Chip(id=f"checkin:{h}", label=f"{h}h", row="Ngày đầu bắt đầu đi lúc", drafts=(d("checkin_at", f"{h:02d}:00"),))
                    for h in (7, 9, 12, 14))
        + tuple(Chip(id=f"checkout:{h}", label=f"{h}h", row="Ngày cuối phải xong lúc", drafts=(d("checkout_at", f"{h:02d}:00"),))
                for h in (11, 12, 15, 18))))


def arrival_q(mobility_known: bool) -> Question:
    """How the trip reaches the city. Driving in also says the vehicle, unless it is already known."""
    own = ((Chip(id="self", label="Tự đi", drafts=(d("arrival_mode", "self"),)),) if mobility_known else tuple(
        Chip(id=f"self:{k}", label=f"Tự đi, {label.lower()}", drafts=(d("arrival_mode", "self"), d("mobility", k)))
        for k, label in VEHICLE.items()))
    return with_other(Question(
        qid="arrival", group="A", tier=1, text="Bạn tới Đà Lạt bằng gì?",
        reason="Đi xe khách hay máy bay thì ở Đà Lạt cần thuê xe hoặc gọi xe; tự đi thì dùng luôn xe của bạn.",
        chips=own + (Chip(id="bus", label="Xe khách", drafts=(d("arrival_mode", "bus"),)),
                     Chip(id="plane", label="Máy bay", drafts=(d("arrival_mode", "plane"),)))))


def origin_q() -> Question:
    return Question(qid="origin", group="A", tier=1, input="geo", text="Bạn xuất phát từ đâu?",
                    reason="Thường là nhà bạn. Trong chuyến, mỗi ngày bắt đầu và kết thúc ở chỗ ở.")


def lodging_q() -> Question:
    return Question(qid="lodging", group="A", tier=1, input="lodging", text="Bạn có nơi lưu trú nào chưa? Nếu có, hãy cho mình biết tên nhé.",
                    reason="Mỗi ngày bắt đầu và kết thúc ở chỗ ở, cả chuyến một chỗ. Chưa có thì bạn chọn ở bước Lựa chọn, đổi lúc nào cũng được.",
                    chips=(Chip(id="none", label="Chưa đặt chỗ ở", drafts=(d("lodging_booked", "no"),)),))


def anchor_priority_q(state: TripState, catalog: Catalog) -> Question | None:
    matched = [(i, a) for i, a in enumerate(state.anchors)
               if a.state == "matched" and a.place_id in catalog.by_id]
    if len(matched) < 2 or not all(a.priority == "must" for _, a in matched):
        return None
    return with_other(Question(qid="anchor_priority", group="E", multi=True,
                               text="Nếu không đủ thời gian, nơi nào có thể bỏ trước?",
                               reason="Để biết nơi nào phải giữ bằng mọi giá.",
                               chips=tuple(Chip(id=f"a{i}", label=catalog.by_id[a.place_id].name,
                                                drafts=(d("anchor_priority", (i, "want")),)) for i, a in matched)))


def quiz_queue(state: TripState, catalog: Catalog, cfg: Settings) -> list[Question]:
    """Fixed order, safety first; known or already-asked questions are left out."""
    done = set(state.meta.asked)
    out = list(safety_queue(state, catalog, cfg))

    def want(qid: str, cond: bool) -> bool:
        return cond and qid not in done

    if want("days", not state.days.known):
        out.append(days_q())
    if want("companions", not state.companions.known):
        out.append(companions_q())
    if want("care", state.companions.known):
        out.append(care_q())
    if want("arrival", not state.arrival_mode.known):
        out.append(arrival_q(state.mobility.known))
    if want("origin", not state.origin.known):
        out.append(origin_q())
    if want("mobility", not state.mobility.known):
        out.append(mobility_q(state.arrival_mode.value, state.entry_point.value))
    if want("dates", not (state.start_date.known or state.month.known)):
        out.append(dates_q())
    if want("lodging", not state.lodging.known and state.lodging_booked.value != "no"):
        out.append(lodging_q())
    if want("stay_times", state.days.known and not (state.checkin_at.known or state.checkout_at.known)):
        out.append(stay_times_q())
    if want("purpose", not state.purpose.known):
        out.append(purpose_q())
    experience = ontology().features
    has_wish = any(f.value == "love" and experience[SoftKey.parse(k).feature].group == "experience"
                   for k, f in state.soft.items())
    if want("vibe", not has_wish) and (q := vibe_q(catalog, cfg)):
        out.append(q)
    if want("crowd", not state.crowd_tolerance.known):
        out.append(crowd_q())
    if want("pace", not state.pace.known):
        out.append(pace_q())
    if want("budget", not state.budget_vnd.known):
        out.append(budget_q())
    if want("novelty", state.meta.experience == "returning" and not state.novelty.known):
        out.append(novelty_q())
    if "anchor_priority" not in done and (q := anchor_priority_q(state, catalog)):
        out.append(q)
    return out


def find_quiz(qid: str, state: TripState, catalog: Catalog, cfg: Settings) -> Question | None:
    """Rebuild the quiz card with this id from the current state (cards are not
    stored across turns; the id is stable)."""
    return next((q for q in quiz_queue(state, catalog, cfg) if q.qid == qid), None)


def apply_chip(state: TripState, q: Question, ids: tuple[str, ...], turn: int) -> TripState:
    """What choosing these chips writes. Raises like apply_drafts on bad drafts."""
    drafts = [dr for c in q.chips if c.id in ids for dr in c.drafts]
    if q.qid == "purpose" and sum(dr.field == "purpose" for dr in drafts) > 1:
        # purpose is one value: the first pick is primary; the other picks still
        # count through their softs. Inferred pace drafts are dropped instead of
        # letting one arbitrary purpose decide the pace (pace_q asks later).
        seen_purpose = False
        kept = []
        for dr in drafts:
            if dr.field == "purpose":
                if seen_purpose:
                    continue
                seen_purpose = True
            elif dr.field == "pace" and dr.inferred:
                continue
            kept.append(dr)
        drafts = kept
    return apply_drafts(state, drafts, turn, tool=f"chip:{q.qid}")
