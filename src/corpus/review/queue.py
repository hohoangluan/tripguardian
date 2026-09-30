"""Items that need a person, built from the crawl files on every request (nothing cached)."""

import json

from ..crawl.common.files import data_dir, safe_name
from .decisions import ACTIONS, latest


def _read(p):
    return json.loads(p.read_text(encoding="utf-8"))


def _tiktok(city: str) -> list[dict]:
    root = data_dir() / "tiktok"
    lst = root / "list" / f"{city}.json"
    rows = {r["video_id"]: r for r in _read(lst)["items"]} if lst.exists() else {}
    items = []
    for f in sorted((root / "filter").glob("*.json")) if (root / "filter").exists() else []:
        if f.name == "summary.json":
            continue
        res = _read(f)
        rel = res["llm"]["relevance"]
        if rel == "yes":
            continue
        row = rows.get(res["video_id"], {})
        items.append({"kind": "video_filter", "id": res["video_id"], "source": "tiktok",
                      "title": res["desc"] or "(no caption)", "url": row.get("url"), "embed": res["video_id"],
                      "status": rel, "why": f"model: {rel} — {res['llm']['reason']}",
                      "details": {"hashtag": row.get("hashtags", []), "tìm thấy qua": row.get("queries", [])}})
    for f in sorted((root / "videos").glob("*/video.json")) if (root / "videos").exists() else []:
        doc = _read(f)
        if doc.get("comments_complete") is True or not (f.parent / "video.mp4").exists():
            continue
        got = len(doc["comments"]) + sum(len(c.get("replies", [])) for c in doc["comments"])
        why = ("crawl bằng code cũ, chưa kiểm tra đã lấy hết comment" if "comments_complete" not in doc
               else "sau 3 lần thử vẫn có danh sách comment chưa báo hết (has_more)")
        items.append({"kind": "video_comments", "id": doc["video_id"], "source": "tiktok",
                      "title": doc.get("caption") or "(no caption)", "url": doc.get("video_url"), "embed": doc["video_id"],
                      "status": "incomplete", "why": why,
                      "details": {"comment": f"{got} / {(doc.get('stats') or {}).get('commentCount')} TikTok báo",
                                  "lấy lúc": doc.get("fetched_at")}})
    return items


def _gmaps() -> list[dict]:
    root = data_dir() / "gmaps"
    items = []
    for f in sorted((root / "filter").glob("*.json")) if (root / "filter").exists() else []:
        if f.name == "summary.json":
            continue
        res = _read(f)
        rel = res["llm"]["relevance"]
        if rel != "yes":
            items.append({"kind": "place_filter", "id": res["fid"], "source": "gmaps", "title": res["name"],
                          "url": res.get("url"), "status": rel, "why": f"model: {rel} — {res['llm']['reason']}",
                          "details": {"loại": res.get("category")}})
    for f in sorted((root / "places").glob("*/place.json")) if (root / "places").exists() else []:
        p = _read(f)
        base = {"id": p["fid"], "source": "gmaps", "title": p.get("name") or p["fid"], "url": p.get("url")}
        info = {"loại": p.get("category"), "địa chỉ": p.get("address"), "rating": p.get("rating"),
                "số review": p.get("review_count"), "trạng thái": p.get("status")}
        qc_file = root / "qc" / f"{safe_name(p['fid'])}.json"
        if qc_file.exists():
            qc = _read(qc_file)
            llm = qc.get("llm")
            flags = []
            if not llm:
                flags.append(f"lỗi model: {qc.get('llm_error', 'không trả lời')}")
            else:
                if llm["verdict"] != "ok":
                    flags.append(f"verdict {llm['verdict']}")
                if not llm["tourism_relevant"]:
                    flags.append(f"không dành cho du khách: {llm['relevance_reason']}")
                if not llm["in_city"]:
                    flags.append("không thuộc thành phố")
            if flags:
                items.append({**base, "kind": "place_qc", "status": llm["verdict"] if llm else "error", "why": "; ".join(flags),
                              "details": {**info, "kiểm tra": qc.get("checks", []),
                                          "trường nghi sai": (llm or {}).get("field_issues", [])}})
        if p.get("reviews_complete") is False:
            n = len(_read(f.parent / "reviews.json"))
            items.append({**base, "kind": "place_reviews", "status": "incomplete",
                          "why": "danh sách review chưa báo hết thì đã dừng", "details": {**info, "review đã lưu": n}})
    return items


def queue(city: str, decided: bool = False) -> list[dict]:
    """Open items (decided=True: also the ones already decided, with their decision)."""
    items = _tiktok(city) + _gmaps()
    done = {kind: latest(kind) for kind in ACTIONS}
    out = []
    for it in items:
        rec = done[it["kind"]].get(it["id"])
        if rec and not decided:
            continue
        out.append({**it, "actions": list(ACTIONS[it["kind"]]), "decision": rec})
    return out
