"""⑩ Decision Output (docs/PLACE_DECISION.md §15): the input of Planning & Validation."""

from .cards import warning_text


def build(s, res, cfg) -> dict:
    st, si = s.state, s.search_input
    anchors = {a.place_id for a in si.anchors}
    relaxed: dict[str, list[str]] = {}
    for p, f in st.relaxed:
        relaxed.setdefault(p, []).append(f)
    confirmed = []
    for pid in st.selected:
        c = res.cands.get(pid)
        if c is None:
            continue
        confirmed.append({"id": pid, "name": c.name,
                          "role": "anchor" if pid in anchors else "locked" if pid in st.locked else "selected",
                          "visit": c.rec["operation"].get("visit_minutes"),
                          "flags": [f["text"] for f in c.flags] + [warning_text(w, cfg) for w in c.warnings],
                          "relaxed": relaxed.get(pid, [])})
    backup, seen = [], set(st.selected)
    for pid in st.selected:
        for alt in res.alternatives.get(pid, []):
            if alt not in seen:
                seen.add(alt)
                backup.append({"id": alt, "name": res.cands[alt].name, "for": pid, "reason": "same_kind"})
    for g in res.view["groups"]:
        for x in g["cards"]:
            if x["id"] in seen or not x["top"]:  # the best fits only, not every place the user scrolled past
                continue
            seen.add(x["id"])
            codes = [f["code"] for f in res.cands[x["id"]].flags if f["code"] in ("rain", "crowded")]
            backup.append({"id": x["id"], "name": x["name"], "for": None,
                           "reason": f"context:{codes[0]}" if codes else "next_best"})
    return {"confirmed": confirmed, "backup_pool": backup, "wishlist": res.view["wishlist"],
            "trip_context": si.model_dump(mode="json"), "decision_log": list(s.log),
            "feasibility": res.view["feasibility"]}
