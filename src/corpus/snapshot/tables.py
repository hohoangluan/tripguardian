"""Serving records -> the snapshot tables (docs/superpowers/specs/2026-10-13-corpus-snapshot-design.md §5). Pure: no
I/O. Derived columns repeat the per-place formulas of decision / requirements, which corpus cannot import;
tests/snapshot/test_tables.py checks each copy against its original."""

import orjson
import pyarrow as pa

from ..categories import group as category_group
from ..ontology import load as load_ontology
from ..serving.groups import signature
from ..serving.record import feature

DAYS = ("mon", "tue", "wed", "thu", "fri", "sat", "sun")  # decision.trip_days.DAYS
DAYTIME = ("morning", "noon", "afternoon", "evening")     # decision.fit.DAYTIME
STATUS_W = {"VERIFIED": 1.0, "OUTDATED": 0.7, "UNCERTAIN": 0.5}  # decision.rank.STATUS_W
FULL_N = 3                                                 # decision.rank.FULL_N

_STR, _LIST = pa.string(), pa.list_(pa.string())
CROWD_COLS = [f"crowd_{dt}_{b}" for dt in ("weekday", "weekend") for b in DAYTIME]
PLACES_SCHEMA = pa.schema([
    ("id", _STR), ("name", _STR), ("status", _STR), ("kind", _STR), ("category", _STR), ("category_group", _STR),
    ("area", _STR), ("address", _STR), ("lat", pa.float64()), ("lng", pa.float64()), ("usable_as", _LIST),
    ("role", _STR), ("activity", _STR), ("category_for", _STR), ("is_stay", pa.bool_()),
    ("near_duplicate_group", pa.int64()), ("voices", pa.int32()), ("price_mid_vnd", pa.float64()),
    ("hours_status", _STR), ("has_hours_value", pa.bool_()), ("open_mask", pa.uint8()),
    *[(c, pa.int16()) for c in CROWD_COLS], ("has_crowd", pa.bool_()), ("signature", _LIST)])
FEATURES_SCHEMA = pa.schema([("place_id", _STR), ("fid", _STR), ("value", _STR), ("status", _STR), ("n", pa.int32()),
                             ("conf", pa.float64()), ("dist_values", _LIST)])
CTX_SCHEMA = pa.schema([("place_id", _STR), ("fid", _STR), ("ctx_key", _STR), ("top", _STR)])
VERDICT_SCHEMA = pa.schema([("place_id", _STR), ("who", _STR), ("value", _STR), ("status", _STR)])
RECORDS_SCHEMA = pa.schema([("id", _STR), ("json", _STR)])
VIDEOS_SCHEMA = pa.schema([("video_id", _STR), ("place_id", _STR)])


def _role_of(rec: dict) -> str | None:  # decision.model.role_of
    u = rec.get("usable_as") or []
    return "experience" if "experience" in u else "meal" if "meal" in u else None


def _category_for(rec: dict) -> str | None:  # requirements.checks.category_for
    ident = rec.get("identity") or {}
    group = ident.get("category_group")
    if group and group not in {"other", "x"}:
        return group
    category = ident.get("category")
    derived = category_group(category)["id"] if category and category != "x" else None
    return derived if derived != "other" else None


def _activity(rec: dict, role: str | None) -> str | None:  # requirements.checks.activity_for(rec, None, role)
    group = _category_for(rec)
    usable = rec.get("usable_as") or []
    if group == "cafe":
        return "coffee"
    if role == "meal" or ("meal" in usable and "experience" not in usable) or group in {"restaurant", "dessert", "food_vendor"}:
        return "eating"
    if group == "bar":
        return "drinking"
    if group == "stay":
        return "accommodation"
    if group == "rental":
        return "travel"
    if group or role == "experience" or "experience" in usable:
        return "sightseeing"
    return None


def _final_role(rec: dict) -> str | None:  # decision.pipeline.run without an activities override
    role = _role_of(rec)
    act = _activity(rec, role)
    if role and act == "eating":
        return "meal"
    if role and act:
        return "experience"
    return role


def _conf(f: dict) -> float:  # decision.rank.conf; derived effort features have n = 0, agreement None: no confidence
    if f["confidence"]["agreement"] is None:
        return 0.0
    return f["confidence"]["agreement"] * min(1.0, f["n"] / FULL_N) * STATUS_W[f["status"]]


def _price_mid(rec: dict) -> float | None:  # decision.rank._price_norm before / price_ref_vnd
    p = rec["operation"].get("price_per_person")
    if not p:
        return None
    v = p["value"]
    lo = v.get("min_vnd") or 0
    return (lo + (v.get("max_vnd") or lo)) / 2


def _table(rows: list[dict], schema: pa.Schema) -> pa.Table:
    return pa.Table.from_pylist(rows, schema=schema)


def tables(records: list[dict], intel: list[dict] | None = None, videos: dict[str, str] | None = None) -> dict[str, pa.Table]:
    ont = load_ontology()
    places, feats, ctx, verdicts, recs = [], [], [], [], []
    for r in records:
        ident, op = r["identity"], r["operation"]
        hours, crowd = op.get("hours"), op.get("crowd_by_time")
        role = _final_role(r)
        row = {"id": r["id"], "name": ident.get("name") or r["id"], "status": r["status"], "kind": ident.get("kind"),
               "category": ident.get("category"), "category_group": ident.get("category_group"),
               "area": ident.get("area"), "address": ident.get("address"),
               "lat": None if ident.get("lat") is None else float(ident["lat"]),
               "lng": None if ident.get("lng") is None else float(ident["lng"]),
               "usable_as": list(r.get("usable_as") or []), "role": role,
               "activity": _activity(r, role), "category_for": _category_for(r),
               "is_stay": ident.get("category_group") == "stay",
               "near_duplicate_group": r.get("near_duplicate_group"),
               "voices": (r.get("provenance") or {}).get("voices") or 0, "price_mid_vnd": _price_mid(r),
               "hours_status": hours["status"] if hours else None,
               "has_hours_value": bool(hours and hours.get("value")),
               "open_mask": sum(1 << i for i, d in enumerate(DAYS) if hours and (hours.get("value") or {}).get(d)),
               "has_crowd": bool(crowd),
               "signature": sorted(f"{fid}={v}" for fid, v in signature(r))}
        for dt in ("weekday", "weekend"):
            for b in DAYTIME:
                row[f"crowd_{dt}_{b}"] = ((crowd or {}).get(dt) or {}).get(b)
        places.append(row)
        for fid in ont.features:
            f = feature(r, fid)
            if f is None:
                continue
            feats.append({"place_id": r["id"], "fid": fid, "value": f["value"], "status": f["status"], "n": f["n"],
                          "conf": _conf(f), "dist_values": list(f["distribution"])})
            for key, d in (f.get("by_context") or {}).items():
                if d:
                    ctx.append({"place_id": r["id"], "fid": fid, "ctx_key": key, "top": max(d, key=d.get)})
        for who in ((r.get("details") or {}).get("fit") or {}):
            f = feature(r, f"fit.{who}")
            if f is not None:
                feats.append({"place_id": r["id"], "fid": f"fit.{who}", "value": f["value"], "status": f["status"],
                              "n": None, "conf": None, "dist_values": list(f["distribution"])})
                verdicts.append({"place_id": r["id"], "who": who, "value": f["value"], "status": f["status"]})
        recs.append({"id": r["id"], "json": orjson.dumps(r).decode()})
    return {"places": _table(places, PLACES_SCHEMA), "features": _table(feats, FEATURES_SCHEMA),
            "feature_ctx": _table(ctx, CTX_SCHEMA), "fit_verdicts": _table(verdicts, VERDICT_SCHEMA),
            "records": _table(recs, RECORDS_SCHEMA),
            "intel": _table([{"id": i["place_fid"], "json": orjson.dumps(i).decode()} for i in intel or []], RECORDS_SCHEMA),
            "videos": _table([{"video_id": k, "place_id": v} for k, v in sorted((videos or {}).items())], VIDEOS_SCHEMA)}
