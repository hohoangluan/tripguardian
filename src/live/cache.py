"""Per-request cache for live context: data/live/<source>/<key>.json, each entry carrying its own provenance.

Nothing here reads or writes corpus data. The cache is the only thing src/live ever writes.
"""

import hashlib
import json
import os
import tempfile
from datetime import UTC, datetime
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]


def data_dir() -> Path:
    d = Path(os.environ.get("DATA_DIR", "data"))
    return d if d.is_absolute() else ROOT / d


def base_dir() -> Path:
    return data_dir() / "live"


def key(payload: dict) -> str:
    raw = json.dumps(payload, sort_keys=True, ensure_ascii=False, separators=(",", ":"))
    return hashlib.sha256(raw.encode("utf-8")).hexdigest()[:32]


def _path(source: str, payload: dict) -> Path:
    return base_dir() / source / f"{key(payload)}.json"


def now() -> str:
    return datetime.now(UTC).isoformat(timespec="seconds")


def get(source: str, payload: dict, ttl_s: int) -> dict | None:
    """The stored entry while it is still fresh, else None. A missing, unreadable or malformed file is a miss."""
    p = _path(source, payload)
    try:
        entry = json.loads(p.read_text(encoding="utf-8"))
        age = (datetime.now(UTC) - datetime.fromisoformat(entry["fetched_at"])).total_seconds()
    except (OSError, ValueError, KeyError, TypeError):
        return None
    return None if age > ttl_s else entry


def put(source: str, payload: dict, value, label: str) -> dict:
    """Write one entry atomically and return it, so callers use the same shape on a hit and on a miss.

    The cache is best effort: when the disk write fails (on Windows os.replace fails while a reader holds the target),
    the value that was just fetched is still returned and only the caching is lost.
    """
    entry = {"source": label, "fetched_at": now(), "value": value}
    p = _path(source, payload)
    tmp = None
    try:
        p.parent.mkdir(parents=True, exist_ok=True)
        fd, tmp = tempfile.mkstemp(dir=p.parent, prefix=p.stem + ".", suffix=".tmp")  # one temp file per writer
        with os.fdopen(fd, "w", encoding="utf-8") as f:
            f.write(json.dumps(entry, ensure_ascii=False))
        os.replace(tmp, p)
    except OSError:
        if tmp is not None:
            Path(tmp).unlink(missing_ok=True)
    return entry


def entries(source: str) -> list[dict]:
    """Every readable entry of one source, any age (a lodging's name and point outlive its price)."""
    out = []
    for p in sorted((base_dir() / source).glob("*.json")):
        try:
            entry = json.loads(p.read_text(encoding="utf-8"))
        except (OSError, ValueError):
            continue
        if isinstance(entry, dict) and "value" in entry:
            out.append(entry)
    return out
