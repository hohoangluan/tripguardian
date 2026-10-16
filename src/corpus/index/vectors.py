"""Offline vectors, one file pair per place and per source (docs/CORPUS.md §Chỉ mục ngữ nghĩa):

  data/gmaps/photo_vectors/<fid_dir>.npy + .json   Maps photos (SigLIP2)
  data/tiktok/frame_vectors/<fid_dir>.npy + .json  keyframes of videos about this place alone (SigLIP2), deduped
  data/intel/span_vectors/<fid_dir>.npy + .json    each gated observation span (bge-m3)

Only places of the serving file are embedded. A file is kept while its key (model id + the inputs) is unchanged, so a
second run costs nothing. One process per GPU of config `gpus`; places are split between them."""

from __future__ import annotations

import hashlib
import json
import multiprocessing as mp
import time
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path

import numpy as np

from ..crawl.common.files import data_dir, safe_name
from .embedder import Embedder, config

KINDS = ("photos", "frames", "spans")
OUT = {"photos": ("gmaps", "photo_vectors"), "frames": ("tiktok", "frame_vectors"), "spans": ("intel", "span_vectors")}


def serving_ids(data: Path) -> list[str]:
    return [r["id"] for r in json.loads((data / "serving" / "places.json").read_text(encoding="utf-8"))["records"]]


def _json(p: Path):
    try:
        return json.loads(p.read_text(encoding="utf-8"))
    except (OSError, ValueError):
        return None


def photo_inputs(data: Path, pid: str) -> list[dict]:
    d = data / "gmaps" / "places" / safe_name(pid)
    doc = _json(d / "photos.json") or {}
    return [{"file": str((d / p["file"]).relative_to(data)), "photo_id": p.get("photo_id"), "source": "gmaps",
             "author_hash": p.get("author_hash"), "owner": bool(p.get("owner")), "month": p.get("month")}
            for p in doc.get("photos", []) if not p.get("stale") and (d / p["file"]).exists()]  # stale = cover only


def frame_inputs(data: Path, pid: str) -> list[dict]:
    """Frames of the videos whose frames were read for this place alone (an observation with source_type
    tiktok_frame): a video about several places says nothing visual about one of them."""
    doc = _json(data / "tiktok" / "observations" / f"{safe_name(pid)}.json") or {}
    videos: dict[str, dict] = {}
    for o in doc.get("observations", []):
        if o.get("source_type") == "tiktok_frame":
            videos.setdefault(o["source_id"], o)
    out = []
    for vid, o in sorted(videos.items()):
        frames = data / "tiktok" / "videos" / vid / "frames"
        for f in sorted(frames.glob("f*.jpg")) if frames.is_dir() else ():
            author = o.get("author") or ""
            out.append({"file": str(f.relative_to(data)), "photo_id": f"{vid}/{f.stem}", "source": "tiktok",
                        "author_hash": author, "owner": author.startswith("tiktok:owner:"),
                        "month": (o.get("observed_at") or "")[:7] or None})
    return out


def span_inputs(data: Path, pid: str) -> list[dict]:
    """One item per distinct quote: a review sentence backing three features is embedded once."""
    by_quote: dict[str, dict] = {}
    for src in ("gmaps", "tiktok", "official"):
        doc = _json(data / src / "observations" / f"{safe_name(pid)}.json") or {}
        for o in doc.get("observations", []):
            q = ((o.get("span") or {}).get("quote") or "").strip()[:400]
            if not q:
                continue
            it = by_quote.setdefault(q, {"observation_id": o["id"], "observations": [], "features": [], "quote": q,
                                          "source": o.get("source_type")})
            if o["id"] not in it["observations"]:
                it["observations"].append(o["id"])
                it["features"].append(f"{o['feature']}={o['value']}")
    return list(by_quote.values())


INPUTS = {"photos": photo_inputs, "frames": frame_inputs, "spans": span_inputs}


def key(model: str, items: list[dict]) -> str:
    raw = json.dumps([model, [i.get("file") or i.get("observation_id") for i in items],
                      [i.get("quote") for i in items]], ensure_ascii=False)
    return hashlib.sha256(raw.encode()).hexdigest()[:20]


def out_paths(data: Path, kind: str, pid: str) -> tuple[Path, Path]:
    d = data.joinpath(*OUT[kind])
    return d / f"{safe_name(pid)}.npy", d / f"{safe_name(pid)}.json"


def todo(data: Path, kind: str, ids: list[str], model: str) -> list[tuple[str, list[dict], str]]:
    out = []
    for pid in ids:
        items = INPUTS[kind](data, pid)
        if not items:
            continue
        k = key(model, items)
        _, meta = out_paths(data, kind, pid)
        if (_json(meta) or {}).get("key") != k:
            out.append((pid, items, k))
    return out


def _dedup(vecs: np.ndarray, items: list[dict], limit: float) -> tuple[np.ndarray, list[dict]]:
    """Frames of one video this similar to an earlier kept frame are dropped."""
    keep: list[int] = []
    for i, it in enumerate(items):
        vid = it["photo_id"].split("/")[0]
        if any(items[j]["photo_id"].split("/")[0] == vid and float(vecs[i] @ vecs[j]) >= limit for j in keep):
            continue
        keep.append(i)
    return vecs[keep], [items[i] for i in keep]


def _write(data: Path, kind: str, pid: str, k: str, model: str, vecs: np.ndarray, items: list[dict]) -> None:
    npy, meta = out_paths(data, kind, pid)
    npy.parent.mkdir(parents=True, exist_ok=True)
    np.save(npy, vecs.astype(np.float16))
    meta.write_text(json.dumps({"key": k, "model": model, "place_id": pid, "items": items}, ensure_ascii=False),
                    encoding="utf-8")


def _worker(rank: int, gpu: int, kind: str, jobs: list, data: str, cfg: dict, q) -> None:
    from PIL import Image
    data_p = Path(data)
    emb = Embedder(device=f"cuda:{gpu}", cfg=cfg)
    model = emb.text_model_id if kind == "spans" else emb.image_model_id
    batch = cfg["embedder"]["text_batch" if kind == "spans" else "batch"]
    pool = ThreadPoolExecutor(8)

    def load(it):
        try:
            im = Image.open(data_p / it["file"])
            im.draft("RGB", (768, 768))
            return im.convert("RGB")
        except OSError:
            return None

    for pid, items, k in jobs:
        try:
            if kind == "spans":
                vecs = np.concatenate([emb.text([i["quote"] for i in items[s:s + batch]])
                                       for s in range(0, len(items), batch)])
                kept = items
            else:
                ims = list(pool.map(load, items))
                kept = [it for it, im in zip(items, ims) if im is not None]
                ims = [im for im in ims if im is not None]
                if not ims:
                    q.put((rank, pid, 0, "no readable image"))
                    continue
                vecs = np.concatenate([emb.image(ims[s:s + batch]) for s in range(0, len(ims), batch)])
                if kind == "frames":
                    vecs, kept = _dedup(vecs, kept, cfg["frame_dedup"])
            _write(data_p, kind, pid, k, model, vecs, kept)
            q.put((rank, pid, len(kept), None))
        except Exception as e:  # one bad place must not stop the GPU's share
            q.put((rank, pid, 0, f"{type(e).__name__}: {e}"))
    q.put((rank, None, 0, "done"))


def run(kinds: tuple[str, ...] = KINDS, ids: list[str] | None = None, gpus: list[int] | None = None) -> dict:
    data = data_dir()
    cfg = config()
    gpus = gpus if gpus is not None else cfg["gpus"]
    ids = ids if ids is not None else serving_ids(data)
    summary = {}
    for kind in kinds:
        model = cfg["embedder"]["text_model" if kind == "spans" else "image_model"]
        jobs = todo(data, kind, ids, model)
        print(f"[index] {kind}: {len(jobs)} places to embed of {len(ids)}", flush=True)
        if not jobs:
            summary[kind] = 0
            continue
        jobs.sort(key=lambda j: -len(j[1]))  # largest first, dealt round-robin so the GPUs finish together
        share = [jobs[i::len(gpus)] for i in range(len(gpus))]
        ctx = mp.get_context("spawn")
        q = ctx.Queue()
        procs = [ctx.Process(target=_worker, args=(r, g, kind, share[r], str(data), cfg, q)) for r, g in enumerate(gpus)
                 if share[r]]
        for p in procs:
            p.start()
        done, n, t0, errors = 0, 0, time.time(), []
        live = len(procs)
        while live:
            rank, pid, count, err = q.get()
            if pid is None:
                live -= 1
                continue
            done += 1
            n += count
            if err:
                errors.append({"place": pid, "error": err})
            if done % 100 == 0 or done == len(jobs):
                print(f"[index] {kind}: {done}/{len(jobs)} places, {n} vectors, {time.time() - t0:.0f}s", flush=True)
        for p in procs:
            p.join()
        if errors:
            (data / "intel").mkdir(parents=True, exist_ok=True)
            with (data / "intel" / "index_errors.jsonl").open("a", encoding="utf-8") as f:
                for e in errors:
                    f.write(json.dumps({"kind": kind, **e}, ensure_ascii=False) + "\n")
        summary[kind] = n
        print(f"[index] {kind}: {n} vectors, {len(errors)} errors", flush=True)
    return summary
