"""⑧ Curation (docs/P3_PLACE_DECISION.md §12): typed actions on the session state, the Session Profile they teach, and
the one question the rules may open (pattern, gap, rethink). Pure: apply() returns a new State."""

from collections import Counter
from functools import cache

from corpus.ontology import load
from corpus.serving import feature

from .cards import phrase
from .model import FIRM
from .session import Chip, Drop, Pending, SoftAdd, State

REASONS = ("far", "crowded", "pricey", "dislike", "visited")
PLACE_ACTIONS = {"select", "drop", "lock", "unlock", "swap", "relax", "wishlist"}


class ActionError(ValueError):
    """The action is malformed or does not fit the session; nothing changed."""


@cache
def _ontology():
    return load()


def _select(s: State, pid: str) -> None:
    if pid not in s.selected:
        s.selected.append(pid)
    s.dropped = [d for d in s.dropped if d.place_id != pid]
    s.wishlist = [w for w in s.wishlist if w != pid]


def _remove(s: State, pid: str) -> None:
    s.selected = [x for x in s.selected if x != pid]
    s.locked = [x for x in s.locked if x != pid]


def _feedback(s: State, reason: str | None, pid: str | None, cfg) -> None:
    p = s.profile
    if reason == "far":
        p.travel_mult = max(cfg.travel_mult_min, round(p.travel_mult * cfg.far_step, 3))
    elif reason == "crowded":
        p.crowd_tolerance = "avoid"
        if pid is None:  # a wish about the whole list, not one place: the crowded ones go, not only rank lower
            p.hide_crowded = True
    elif reason == "pricey":
        p.price_sensitivity = round(p.price_sensitivity + cfg.price_step, 3)
    elif reason == "visited" and pid and pid not in p.visited:
        p.visited.append(pid)


def apply(state: State, act: dict, known, alternatives: dict[str, list[str]], pending: Pending | None, cfg) -> State:
    t, pid = act.get("type"), act.get("place_id")
    if t in PLACE_ACTIONS and not (isinstance(pid, str) and known(pid)):
        raise ActionError(f"unknown place {pid!r}")
    s = state.model_copy(deep=True)
    if t != "answer":
        s.suggest_group = None
    if t == "select":
        _select(s, pid)
    elif t == "lock":
        _select(s, pid)
        if pid not in s.locked:
            s.locked.append(pid)
    elif t == "unlock":
        s.locked = [x for x in s.locked if x != pid]
    elif t == "drop":
        reason = act.get("reason")
        if reason not in (None, *REASONS):
            raise ActionError(f"unknown reason {reason!r}")
        _remove(s, pid)
        s.dropped = [d for d in s.dropped if d.place_id != pid] + [Drop(place_id=pid, reason=reason)]
        _feedback(s, reason, pid, cfg)
    elif t == "swap":
        w = act.get("with_id")
        if w not in alternatives.get(pid, []):
            raise ActionError(f"{w!r} is not an alternative of {pid!r}")
        _remove(s, pid)
        s.dropped = [d for d in s.dropped if d.place_id != pid] + [Drop(place_id=pid)]
        _select(s, w)
    elif t == "relax":
        f = act.get("feature")
        if not isinstance(f, str) or f not in _ontology().features:
            raise ActionError(f"unknown feature {f!r}")
        if (pid, f) not in s.relaxed:
            s.relaxed.append((pid, f))
    elif t == "wishlist":
        _remove(s, pid)
        if pid not in s.wishlist:
            s.wishlist.append(pid)
    elif t == "feedback":
        if act.get("reason") not in ("far", "crowded", "pricey"):
            raise ActionError(f"unknown feedback {act.get('reason')!r}")
        _feedback(s, act["reason"], None, cfg)
    elif t == "prefer":
        f, v, w = act.get("feature"), act.get("value"), act.get("weight")
        if not _ontology().valid(f, v) or w not in (1, -1):
            raise ActionError(f"bad preference {f!r}={v!r} weight {w!r}")
        s.profile.soft = [x for x in s.profile.soft if (x.feature, x.value) != (f, v)] + [SoftAdd(feature=f, value=v, weight=w)]
    elif t == "note":
        phrase_ = (act.get("phrase") or "").strip()
        if not phrase_:
            raise ActionError("empty note")
        s.unmapped.append(phrase_[:120])
    elif t == "answer":
        qid, chip = act.get("qid"), act.get("chip")
        if not pending or qid != pending.qid or chip not in [c.id for c in pending.chips]:
            raise ActionError(f"no open question {qid!r} with chip {chip!r}")
        s.answered.append(qid)
        if qid.startswith("pattern:") and chip == "yes":
            f, v = qid[len("pattern:"):].split("=", 1)
            s.profile.soft.append(SoftAdd(feature=f, value=v, weight=-1))
        elif qid.startswith("gap:") and chip == "similar":
            s.suggest_group = pending.data.get("group")
    else:
        raise ActionError(f"unknown action {t!r}")
    s.last = t
    return s


def pending(state: State, by_id: dict, si, feas: dict, first_shortlist: int, group_of: dict[str, str], cfg) -> Pending | None:
    """The one question the rules open now, most important first: pattern, rethink, gap."""
    avoided = {(w.feature, w.value) for w in si.soft_weights if w.weight < 0}
    avoided |= {(x.feature, x.value) for x in state.profile.soft if x.weight < 0}
    counts = Counter()
    for d in state.dropped:
        r = by_id.get(d.place_id)
        if not r or d.reason == "visited":
            continue
        for fid, order in cfg.polarity.items():
            f = feature(r, fid)
            if f and f["status"] in FIRM and f["value"] == order[-1]:
                counts[(fid, order[-1])] += 1
    for (fid, v), n in sorted(counts.items(), key=lambda x: (-x[1], x[0])):
        qid = f"pattern:{fid}={v}"
        if n >= cfg.pattern_min and qid not in state.answered and (fid, v) not in avoided:
            return Pending(qid=qid, text=f"Mấy nơi bạn bỏ đều có điểm “{phrase(fid, v, cfg)}”. Bạn muốn tránh kiểu nơi này?",
                           reason=f"{n} nơi bạn bỏ có chung điểm này",
                           chips=[Chip(id="yes", label="Đúng, tránh giúp mình"), Chip(id="no", label="Không phải")])
    if (len(state.dropped) >= cfg.rethink_drops and len(state.dropped) * 2 >= first_shortlist
            and "rethink" not in state.answered):
        return Pending(qid="rethink", text="Bạn đã bỏ khá nhiều gợi ý. Mình hỏi lại một chút về mục đích chuyến đi nhé?",
                       reason="Gợi ý có vẻ chưa đúng gu của bạn",
                       chips=[Chip(id="back", label="Hỏi lại giúp mình"), Chip(id="stay", label="Không, mình tự chọn tiếp")])
    slack = feas.get("slack")
    qid = f"gap:{len(state.dropped)}"
    if state.last == "drop" and slack is not None and slack >= cfg.gap_min and qid not in state.answered:
        return Pending(qid=qid, text=f"Bỏ nơi này, chuyến còn dư khoảng {slack} phút. Bạn muốn làm gì?",
                       reason="Thời gian trống sau khi bỏ",
                       chips=[Chip(id="similar", label="Gợi ý nơi tương tự"), Chip(id="free", label="Để thời gian tự do")],
                       data={"group": group_of.get(state.dropped[-1].place_id)})
    return None
