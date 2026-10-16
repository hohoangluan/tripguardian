"""Trip Understanding's wishes as place lifts (docs/PLACE_DECISION.md §8 `wish`). A wish only lifts the places that
meet it: it never pushes one down or out, and screening runs before it."""

from collections.abc import Callable, Iterable, Mapping
from dataclasses import dataclass

from corpus.serving import similarity

SAID = ("dish", "kind", "vibe", "like")  # the user said it; group and purpose only lean


@dataclass(frozen=True)
class Wish:
    key: str  # "dish:bánh căn", "kind:karaoke", "vibe:0", "like:<id>", "group:chill", "purpose:relax"
    kind: str  # dish | kind | vibe | like | group | purpose
    label: str  # the user's words, the reference's name ("" when it has none), or a group / purpose id
    a: float  # how much meeting it lifts (config wish.a)
    places: Mapping[str, float] | None = None  # id -> strength 0..1; None: every place of `group`
    group: str | None = None  # display group it is about (group, purpose)
    role: str | None = None  # only places of this role; None: every place it lists


def ranked(ids: Iterable[str]) -> dict[str, float]:
    """1 for the first place down to 0.5 for the last; a repeated id keeps its first rank."""
    ids = list(dict.fromkeys(ids))
    n = max(1, len(ids) - 1)
    return {pid: 1.0 - 0.5 * i / n for i, pid in enumerate(ids)}


def build(si, rows: Iterable[dict], cfg, sigs: Mapping | None = None,
          firm: Callable[[str, str], set[str]] | None = None,
          name: Callable[[str], str | None] = lambda pid: None) -> tuple[Wish, ...]:
    """rows: every place as {id, identity.category_group, usable_as} (a record, or Region.light), read only for
    "giống X". sigs: id -> signature (Region.sigs). firm(feature, value): ids whose served value is that, VERIFIED or
    OUTDATED. A wish no place meets is left out: it would lift nothing."""
    a, out, seen = cfg.wish["a"], [], set()

    def add(w: Wish) -> None:  # a dish / kind said twice is one wish; each photo look and each reference is its own
        k = w.key if w.kind in ("vibe", "like") else (w.kind, w.label.casefold())
        if k not in seen and (w.places is None or w.places):
            seen.add(k)
            out.append(w)

    for d in si.wishes.dishes:
        add(Wish(f"dish:{d.dish}", "dish", d.dish, a["dish"], ranked(d.place_ids)))  # wherever it is listed
    for k in si.wishes.kinds:
        add(Wish(f"kind:{k.kind}", "kind", k.kind, a["kind"], dict.fromkeys(k.place_ids, 1.0)))
    for i, v in enumerate(si.vibes):
        add(Wish(f"vibe:{i}", "vibe", v.phrase, a["vibe"], ranked(v.places)))
    if si.wishes.like:
        rows = list(rows)
        by = {r["id"]: r for r in rows}
        for lk in si.wishes.like:
            ref = by.get(lk.place_id)
            if ref is None:
                continue
            near = {r["id"]: s for r in rows
                    if r["id"] != ref["id"] and (s := similarity(ref, r, sigs)) >= cfg.wish["like_min"]}
            add(Wish(f"like:{lk.place_id}", "like", name(lk.place_id) or "", a["like"], near))  # "": never a raw id
    for g in si.liked_groups:
        add(Wish(f"group:{g}", "group", g, a["group"], group=g))
    purpose = si.context.purpose
    lean = cfg.wish["purpose"].get(purpose or "")
    if lean and "group" in lean:
        add(Wish(f"purpose:{purpose}", "purpose", purpose, a["purpose"], group=lean["group"]))
    elif lean and firm is not None:
        add(Wish(f"purpose:{purpose}", "purpose", purpose, a["purpose"],
                 dict.fromkeys(sorted(firm(lean["feature"], lean.get("value", "present"))), 1.0)))
    return tuple(out)


def strength(w: Wish, pid: str, role: str | None, group: str | None) -> float:
    if w.role is not None and role != w.role:
        return 0.0
    if w.places is not None:
        return w.places.get(pid, 0.0)
    return 1.0 if group == w.group else 0.0


def lift(ws, pid: str, role: str | None, group: str | None) -> tuple[float, list[tuple[str, str, str, float]]]:
    """(1 − Π(1 − a·strength), hits best first). Same multiplication order as decision.frame._wish."""
    keep, hits = 1.0, []
    for w in ws:
        s = strength(w, pid, role, group)
        keep *= 1 - w.a * s
        if s > 0:
            hits.append((w.key, w.kind, w.label, round(w.a * s, 4)))
    return 1 - keep, sorted(hits, key=lambda h: (-h[3], h[0]))
