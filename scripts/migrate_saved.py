"""Bring saved sessions and journeys up to the current trip fields (src/trip/domain/legacy.py): remove mobility="ride"
(Grab, taxi: no longer a vehicle) and rename arrive_at / leave_at to checkin_at / checkout_at.

A TripState field becomes unknown, a Context value None, and quiz chips that would set it are dropped, so the quiz asks
again (src/trip/domain/legacy.py). Files are copied to data/backup/ride_<time>/ before they are rewritten; a journey's
old envelope is kept in the same folder as <id>.json. Dry run unless --apply.

python scripts/migrate_saved.py [--apply]
"""

import argparse
import json
import os
import shutil
from datetime import datetime
from pathlib import Path

import psycopg
from dotenv import load_dotenv

from trip import upgrade

ROOT = Path(__file__).resolve().parents[1]
FILE_DIRS = ("trip", "planning", "decision", "harness")


def changed(data):
    new = upgrade(data)
    return new if new != data else None


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--apply", action="store_true")
    apply = ap.parse_args().apply
    load_dotenv(ROOT / ".env")
    backup = ROOT / "data" / "backup" / f"saved_{datetime.now():%Y%m%d_%H%M%S}"

    files = 0
    for name in FILE_DIRS:
        for path in sorted((ROOT / "data" / name / "sessions").glob("*.json")):
            data = json.loads(path.read_text(encoding="utf-8"))
            if (new := changed(data)) is None:
                continue
            files += 1
            if apply:
                (backup / name).mkdir(parents=True, exist_ok=True)
                shutil.copy2(path, backup / name / path.name)
                path.write_text(json.dumps(new, ensure_ascii=False, indent=1), encoding="utf-8")
    print(f"session files to upgrade: {files}")

    rows = 0
    with psycopg.connect(os.environ["DATABASE_URL"]) as conn:
        for jid, envelope in conn.execute("SELECT id, envelope FROM journeys").fetchall():
            if (new := changed(envelope)) is None:
                continue
            rows += 1
            if apply:
                (backup / "journeys").mkdir(parents=True, exist_ok=True)
                (backup / "journeys" / f"{jid}.json").write_text(json.dumps(envelope, ensure_ascii=False), encoding="utf-8")
                conn.execute("UPDATE journeys SET envelope = %s WHERE id = %s", (json.dumps(new, ensure_ascii=False), jid))
    print(f"journeys to upgrade: {rows}")
    print(f"backup: {backup}" if apply and (files or rows) else "dry run" if not apply else "nothing to change")


if __name__ == "__main__":
    main()
