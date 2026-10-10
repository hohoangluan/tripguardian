"""Copy the small evidence files the report cites out of the gitignored data/ into submission/evidence/, so the
judges can read them on GitHub. Only aggregates and synthetic runs go in: no reviews, no user sessions, no accounts.

Each copy keeps its path under data/ (data/decision/eval.json -> submission/evidence/data/decision/eval.json).
MANIFEST.md lists every file with its sha256, the source mtime and the command that regenerates it; counts.json holds
the corpus-layer counts the report quotes, read from files too large or too private to publish.

Usage (from the repo root):
    python3 submission/tools/collect_evidence.py [--tests]
--tests also runs pytest and keeps its last lines in evidence/tests/pytest.txt (~90 s).
"""
import hashlib
import json
import shutil
import subprocess
import sys
from datetime import datetime, timezone
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
OUT = ROOT / "submission" / "evidence"

# source (relative to the repo root) -> command that regenerates it
FILES = {
    "data/decision/eval.json": "python -m decision evaluate",
    "data/planning/eval.json": "python -m planning evaluate",
    "data/journey_sim/report.json": "python scripts/journey_sim.py",
    "data/bench/offline-20261007/summary.csv": "python -m bench run",
    "data/bench/offline-20261007/runs.csv": "python -m bench run",
    "data/bench/offline-20261007/fields.csv": "python -m bench run",
    "data/bench/live-20261007/summary.csv": "python -m bench run --live",
    "data/bench/live-20261007/runs.csv": "python -m bench run --live",
    "data/bench/live-20261007/fields.csv": "python -m bench run --live",
    "data/intel/summary.json": "python -m corpus aggregate",
    "data/gmaps/observe_summary.json": "python -m corpus build (observe step)",
}


def sha256(p: Path) -> str:
    return hashlib.sha256(p.read_bytes()).hexdigest()


def mtime(p: Path) -> str:
    return datetime.fromtimestamp(p.stat().st_mtime, timezone.utc).strftime("%Y-%m-%d %H:%M UTC")


def counts() -> dict:
    serving = json.loads((ROOT / "data/serving/places.json").read_text())
    snapshot = ROOT / "web/public/data/snapshot.json"
    labels = ROOT / "data/review/judge_labels.jsonl"
    return {
        "serving": {"source": "data/serving/places.json", "built_at": serving["built_at"], "summary": serving["summary"],
                    "records": len(serving["records"])},
        "intel_places": {"source": "data/intel/places/*.json", "files": len(list((ROOT / "data/intel/places").glob("*.json")))},
        "web_snapshot_places": {"source": "web/public/data/snapshot.json",
                                "places": len(json.loads(snapshot.read_text()).get("places", [])) if snapshot.exists() else None},
        "judge_labels": {"source": "data/review/judge_labels.jsonl",
                         "lines": sum(1 for _ in labels.open()) if labels.exists() else None},
    }


def run_tests() -> str:
    cmd = [str(ROOT / ".venv/bin/python"), "-m", "pytest", "-q", "-p", "no:cacheprovider"]
    r = subprocess.run(cmd, cwd=ROOT, capture_output=True, text=True)
    tail = "\n".join(r.stdout.splitlines()[-40:])
    return f"$ {' '.join(cmd[1:])}  (exit {r.returncode}, {datetime.now(timezone.utc):%Y-%m-%d %H:%M UTC})\n\n{tail}\n"


def main(tests: bool) -> None:
    rows = []
    for rel, cmd in FILES.items():
        src = ROOT / rel
        if not src.exists():
            print(f"warning: {rel} missing, skipped")
            continue
        dst = OUT / rel
        dst.parent.mkdir(parents=True, exist_ok=True)
        shutil.copy2(src, dst)
        rows.append(f"| `{rel}` | {src.stat().st_size:,} | {mtime(src)} | `{sha256(src)[:16]}` | `{cmd}` |")
    (OUT / "counts.json").write_text(json.dumps(counts(), ensure_ascii=False, indent=1) + "\n")
    if tests:
        (OUT / "tests").mkdir(exist_ok=True)
        (OUT / "tests" / "pytest.txt").write_text(run_tests())
    (OUT / "MANIFEST.md").write_text(
        "# Bằng chứng số liệu\n\n"
        "Sinh bằng `python3 submission/tools/collect_evidence.py`. `data/` không nằm trong repo (dung lượng, review của "
        "người thật); đây là bản sao các file tổng hợp mà báo cáo trích. Toàn bộ dữ liệu: gói Drive trong `README.md`.\n\n"
        "| File | Byte | Sửa lần cuối (nguồn) | sha256 (16 ký tự đầu) | Lệnh sinh lại |\n|---|---|---|---|---|\n"
        + "\n".join(rows)
        + "\n\n`counts.json`: số địa điểm theo từng tầng (serving, intel, snapshot web) và số nhãn Judge, đếm từ file gốc.\n"
        + ("`tests/pytest.txt`: phần cuối kết quả `pytest -q`.\n" if tests else ""))
    print(f"{len(rows)} files -> {OUT.relative_to(ROOT)}")


if __name__ == "__main__":
    main("--tests" in sys.argv[1:])
