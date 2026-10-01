"""A person's decisions on review items: data/review/decisions.jsonl, append-only; the latest per item wins.

Decisions are labels (docs/specs/CORPUS_SPEC.md §7): they never edit crawled values. The crawl reads them:
video_filter / place_filter keep/drop overrides the model; retry puts an item back into the next crawl.
"""

import json

from ..crawl.common.files import append_jsonl, data_dir, now

ACTIONS = {
    "video_filter": ("keep", "drop"),
    "place_filter": ("keep", "drop"),
    "video_comments": ("retry", "accept"),
    "place_qc": ("accept", "disable"),
    "place_reviews": ("retry", "accept"),
    "place_verify": ("keep", "drop"),  # id = "<video_id>@<fid>": is this video evidence for this place?
}


def _file():
    return data_dir() / "review" / "decisions.jsonl"


def _all() -> list[dict]:
    f = _file()
    return [json.loads(l) for l in f.read_text(encoding="utf-8").splitlines()] if f.exists() else []


def decide(kind: str, id: str, decision: str, note: str = "") -> dict:
    if decision not in ACTIONS.get(kind, ()):
        raise ValueError(f"{kind}: action must be one of {ACTIONS.get(kind)}")
    rec = {"at": now(), "kind": kind, "id": id, "decision": decision, "note": note}
    append_jsonl(_file(), rec)
    return rec


def latest(kind: str) -> dict[str, dict]:
    out: dict[str, dict] = {}
    for rec in _all():
        if rec["kind"] == kind:
            out[rec["id"]] = rec
    return out


def decisions(kind: str) -> dict[str, str]:
    """id -> latest decision for one kind of item."""
    return {id: rec["decision"] for id, rec in latest(kind).items()}


def retry_ids(kind: str, fetched_at: dict[str, str] | None = None) -> set[str]:
    """Items a person asked to crawl again and that were not fetched since (fetched_at: id -> ISO time)."""
    fetched_at = fetched_at or {}
    return {id for id, rec in latest(kind).items()
            if rec["decision"] == "retry" and fetched_at.get(id, "") < rec["at"]}
