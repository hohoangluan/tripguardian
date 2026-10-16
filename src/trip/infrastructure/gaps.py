"""Count missing-data wishes without writing Place Intelligence."""

import json
import threading
from datetime import datetime, timezone
from pathlib import Path

from ..domain.text import squash

LOCK = threading.Lock()


def record(path: Path, phrase: str, kind: str) -> None:
    with LOCK:
        rows = [json.loads(line) for line in path.read_text(encoding="utf-8").splitlines() if line.strip()] if path.exists() else []
        row = next((r for r in rows if squash(r["phrase"]) == squash(phrase)), None)
        if row is None:
            row = {"phrase": phrase, "kind": kind, "count": 0}
            rows.append(row)
        row.update(count=row["count"] + 1, last_seen=datetime.now(timezone.utc).isoformat())
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text("".join(json.dumps(r, ensure_ascii=False) + "\n" for r in rows), encoding="utf-8")
