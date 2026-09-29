"""Plain-file storage under DATA_DIR: atomic writes, append-only logs. Nothing here deletes."""

import hashlib
import json
import os
import re
import unicodedata
from datetime import UTC, datetime
from pathlib import Path

import yaml
from dotenv import load_dotenv

ROOT = Path(__file__).resolve().parents[3]


def data_dir() -> Path:
    load_dotenv(ROOT / ".env")
    d = Path(os.environ.get("DATA_DIR", "data"))
    return d if d.is_absolute() else ROOT / d


def now() -> str:
    return datetime.now(UTC).isoformat(timespec="seconds")


def write_bytes(path: Path, data: bytes) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    tmp = path.with_name(path.name + ".tmp")
    tmp.write_bytes(data)
    os.replace(tmp, path)


def write_json(path: Path, obj) -> None:
    write_bytes(path, json.dumps(obj, ensure_ascii=False, indent=1).encode("utf-8"))


def append_jsonl(path: Path, obj) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("a", encoding="utf-8") as f:
        f.write(json.dumps(obj, ensure_ascii=False) + "\n")


def log_error(source_dir: Path, id: str, stage: str, err: BaseException) -> None:
    msg = str(err).split("\n", 1)[0]  # Playwright appends a call log that carries session cookies
    append_jsonl(source_dir / "errors.jsonl", {"at": now(), "id": id, "stage": stage, "error": f"{type(err).__name__}: {msg}"})


def slug(text: str) -> str:
    s = unicodedata.normalize("NFD", text.replace("đ", "d").replace("Đ", "D"))
    s = "".join(c for c in s if not unicodedata.combining(c)).lower()
    return re.sub(r"[^a-z0-9]+", "-", s).strip("-")


def safe_name(id: str) -> str:
    return id.replace(":", "_")  # ":" is not allowed in Windows paths


def author_hash(id: str) -> str:
    return hashlib.sha256(id.encode()).hexdigest()[:16]


def load_config(city: str) -> tuple[str, dict]:
    cities = yaml.safe_load((ROOT / "config" / "cities.yaml").read_text(encoding="utf-8"))
    if city not in cities:
        raise SystemExit(f"unknown city {city!r}; known: {', '.join(cities)}")
    return cities[city], yaml.safe_load((ROOT / "config" / "queries.yaml").read_text(encoding="utf-8"))
