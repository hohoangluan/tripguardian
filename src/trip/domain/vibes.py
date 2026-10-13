"""Looks the user wants ("vibe retro", a photo): the cards that clarify them and what an answer writes (docs/
TRIP_UNDERSTANDING.md §18). The agent only names the look and its visible signs; every place and photo on these cards
comes from corpus.index (infrastructure.looks). Answers write the Trip State without a model call."""

from __future__ import annotations

import json

from .card import Chip, Question
from .state import TripState, Vibe, VibeKind, WebSource
from .text import fold, squash

MAX_CUES, MAX_CUE_LEN, MAX_CUE_WORDS = 8, 40, 7
# the kind of place a look is about -> category groups (config/category_defaults.yaml): "quán retro" is not a retro spa
SCOPES = {"cafe": {"cafe", "bar", "dessert"}, "food": {"restaurant", "dessert", "cafe"},
          "nature": {"nature", "garden_farm", "camping"}, "sights": {"museum", "religious", "attraction", "market", "amusement"}}
VIBE_PLACES = 60  # places a vibe ranks first


def media_url(file: str) -> str:
    """data-relative photo path -> the web's /media URL (web/server.mjs)."""
    for src, prefix in (("gmaps/places/", "/media/gmaps/"), ("tiktok/videos/", "/media/tiktok/")):
        if file.startswith(src):
            return prefix + file[len(src):]
    return "/media/" + file


def clean_cues(raw, text_names: set[str] = frozenset()) -> tuple[str, ...]:
    """Short visible signs, deduped; a place name or an overlong phrase is dropped. Raises when none is left."""
    out: list[str] = []
    for c in raw if isinstance(raw, (list, tuple)) else ():
        c = " ".join(str(c).split()).strip(" .,;").lower()
        if not 2 <= len(c) <= MAX_CUE_LEN or len(c.split()) > MAX_CUE_WORDS or fold(c) in text_names:
            continue
        if fold(c) not in {fold(x) for x in out}:
            out.append(c)
    if not out:
        raise ValueError("no usable cue: give short visible signs (2-5 words each)")
    return tuple(out[:MAX_CUES])


def qid(i: int) -> str:
    return f"vibe:{i}"


def index_of(q: str) -> int | None:
    head, _, n = q.partition(":")
    return int(n) if head == "vibe" and n.isdigit() else None


def put(state: TripState, i: int | None, vibe: Vibe) -> tuple[TripState, int]:
    """Replace vibe i, or add it (i None). Its phrase leaves the unmapped wishes: it is understood now."""
    vibes = list(state.vibes)
    if i is None:
        vibes.append(vibe)
        i = len(vibes) - 1
    else:
        vibes[i] = vibe
    phrase = squash(vibe.phrase)
    unmapped = tuple(u for u in state.unmapped if not (phrase and (phrase in squash(u.phrase) or squash(u.phrase) in phrase)))
    return state.model_copy(update={"vibes": tuple(vibes), "unmapped": unmapped}), i


def _kind_view(k: VibeKind, name) -> dict:
    return {"id": k.id, "label": k.label, "style": k.style, "count": len(k.places),
            "places": [{"id": p, "name": name(p)} for p in k.places[:3]],
            "photos": [{"place_id": p, "name": name(p), "url": media_url(f)} for p, f in k.photos]}


def cues_card(i: int, v: Vibe, preview: list[VibeKind], matched: int, total: int, name, say: str = "") -> Question:
    """guess_confirm: the signs the agent read the look as, editable, with the kinds they lead to."""
    return Question(
        qid=qid(i), group="G", tier=2, input="cues", custom=True, exits=True,
        text=say or f"Mình hiểu “{v.phrase}” qua mấy dấu hiệu dưới đây. Đúng ý bạn chưa? Bỏ cái không muốn, thêm cái còn thiếu.",
        reason="Mình tìm nơi theo dấu hiệu nhìn thấy được, không theo chữ.",
        params={"vibe": i, "phrase": v.phrase, "cues": list(v.cues), "removed": list(v.removed), "matched": matched,
                "total": total, "kinds": [_kind_view(k, name) for k in preview],
                "sources": [s.model_dump() for s in v.sources], "image": v.image})


def kinds_card(i: int, v: Vibe, name) -> Question:
    """image_choice: the look's kinds as real photos of real places; several may be picked."""
    return Question(
        qid=qid(i), group="G", tier=2, input="kinds", multi=True, custom=True, exits=True,
        text=f"“{v.phrase}” ở Đà Lạt có mấy kiểu khá khác nhau. Bạn nghiêng về kiểu nào? Chọn nhiều được.",
        reason="Mỗi kiểu ra một nhóm nơi khác hẳn nhau.",
        chips=tuple(Chip(id=k.id, label=k.label) for k in v.offered),
        params={"vibe": i, "phrase": v.phrase, "kinds": [_kind_view(k, name) for k in v.offered],
                "chosen": list(v.chosen), "image": v.image})


def pick_card(i: int, v: Vibe, pid: str, photo: str | None, name) -> Question:
    """place_pick: the user's photo looks like one corpus place."""
    return Question(
        qid=qid(i), group="E", tier=2, input="photo_pick", custom=True, exits=True,
        text=f"Ảnh bạn gửi giống {name(pid)}. Có phải nơi này không?",
        reason="Mình so ảnh của bạn với ảnh thật của các nơi trong dữ liệu.",
        chips=(Chip(id="yes", label="Đúng nơi này"), Chip(id="no", label="Không phải")),
        params={"vibe": i, "place": {"id": pid, "name": name(pid), "photo": media_url(photo) if photo else None},
                "cues": list(v.cues)})


def read_cues(raw: str | None) -> tuple[tuple[str, ...], tuple[str, ...]]:
    """The cues card's answer: [{label, removed}] -> (kept, removed)."""
    try:
        items = json.loads(raw or "[]")
    except ValueError as e:
        raise ValueError("cues are not JSON") from e
    if not isinstance(items, list):
        raise ValueError("cues are not a list")
    kept = [x.get("label") for x in items if isinstance(x, dict) and not x.get("removed")]
    gone = [x.get("label") for x in items if isinstance(x, dict) and x.get("removed")]
    keep = clean_cues(kept)
    try:
        removed = clean_cues(gone)
    except ValueError:
        removed = ()
    return keep, removed


def choose(v: Vibe, ids: list[str]) -> Vibe:
    """Kinds picked on the photo card -> the places they hold, interleaved so each kind is near the top. No kind
    ("Không kiểu nào giống") keeps the look unknown, not disliked: it ranks nothing."""
    chosen = [k for k in v.offered if k.id in ids]
    if not chosen:
        return v.model_copy(update={"status": "none", "chosen": (), "places": ()})
    places: list[str] = []
    for row in range(max(len(k.places) for k in chosen)):
        for k in chosen:
            if row < len(k.places) and k.places[row] not in places:
                places.append(k.places[row])
    return v.model_copy(update={"status": "done", "chosen": tuple(k.id for k in chosen), "places": tuple(places[:VIBE_PLACES])})


def sources_of(found: list[dict]) -> tuple[WebSource, ...]:
    seen, out = set(), []
    for s in found:
        if s.get("url") and s["url"] not in seen:
            seen.add(s["url"])
            out.append(WebSource(url=s["url"], title=s.get("title") or s.get("domain") or s["url"], domain=s.get("domain") or ""))
    return tuple(out[:6])
