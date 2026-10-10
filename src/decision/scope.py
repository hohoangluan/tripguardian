"""replan_scope (docs/P3_PLACE_DECISION.md §14): the earliest step a change must re-run from, and what stays as is.
The pipeline re-runs everything (cheap); the scope explains the change and is what the table promises."""

STEPS = ("resolve", "screen", "fit", "rank", "diversify", "feasibility")
DROP_STEP = {"far": "fit", "crowded": "fit", "pricey": "rank", "visited": "rank"}
FEEDBACK_STEP = {"far": "fit", "crowded": "fit", "pricey": "rank"}


def _out(step: str | None) -> dict:
    return {"from": step, "keep": list(STEPS[:STEPS.index(step)]) if step else list(STEPS)}


def replan_scope(action: dict) -> dict:
    t = action.get("type")
    if t == "drop":
        return _out(DROP_STEP.get(action.get("reason"), "diversify"))
    if t == "feedback":
        return _out(FEEDBACK_STEP.get(action.get("reason"), "rank"))
    if t == "relax" or t == "undo":
        return _out("screen")
    if t == "prefer" or (t == "answer" and str(action.get("qid", "")).startswith("pattern:") and action.get("chip") == "yes"):
        return _out("rank")
    return _out("diversify")


def input_scope(old, new) -> dict:
    """Search Input changed (the user edited the understanding)."""
    a, b = old.context, new.context
    if old.anchors != new.anchors or a.base != b.base:
        return _out("resolve")
    if (old.hard_filters != new.hard_filters or (a.start_date, a.month, a.days, a.mobility)
            != (b.start_date, b.month, b.days, b.mobility)):
        return _out("screen")
    if old.soft_weights != new.soft_weights or old.novelty != new.novelty:
        return _out("rank")
    if old.pace != new.pace or old.model_dump() != new.model_dump():
        return _out("diversify")
    return _out(None)
