"""web/scripts/export_snapshot.py: the details block of a serving record reaches the snapshot small and with the words
behind each entry."""

import importlib.util
import json
from pathlib import Path

SCRIPT = Path(__file__).resolve().parents[2] / "web" / "scripts" / "export_snapshot.py"
spec = importlib.util.spec_from_file_location("export_snapshot", SCRIPT)
exp = importlib.util.module_from_spec(spec)
spec.loader.exec_module(exp)

QUOTES = {f"q{i}": {"text": f"lời {i}", "date": "2026-09-01", "source": "gmaps_review"} for i in range(4)}


def test_lists_are_cut_and_evidence_ids_become_quotes():
    block = {"order": [{"text": f"món {i}", "n": 2, "evidence": ["q0", "q1", "q2", "gone"]} for i in range(8)],
             "timing": {"best_months": [11, 12, 1, 2, 3, 4, 5], "last_entry": {"time": "16:00", "source": "official"}},
             "fit": {"baby": {"value": "bad", "reasons": ["bậc thang"], "evidence": ["q3"]}}}
    out = exp.slim_details(block, QUOTES)
    assert len(out["order"]) == 5 and out["order"][0]["quotes"] == [QUOTES["q0"], QUOTES["q1"]]
    assert "evidence" not in out["order"][0] and out["timing"]["best_months"] == [11, 12, 1, 2, 3, 4, 5]  # numbers whole
    assert out["fit"]["baby"]["quotes"] == [QUOTES["q3"]] and out["fit"]["baby"]["reasons"] == ["bậc thang"]


def test_a_block_with_nothing_to_show_is_left_out():
    empty = {"known_for": {"headline": None, "more": []}, "order": [], "cost": None, "fit": {},
             "timing": {"best_time": {"items": []}, "avoid_time": {"items": []}, "best_months": [], "avoid_months": [],
                        "schedule": [], "last_entry": None}, "relations": {"quieter": [], "busier": []},
             "walk_to_night_market_min": None}
    assert not exp.has_details(empty)
    assert exp.has_details({**empty, "walk_to_night_market_min": 7}) and exp.has_details({**empty, "order": [{"text": "x"}]})


def test_quotes_come_from_every_source_folder(tmp_path, monkeypatch):
    monkeypatch.setattr(exp, "DATA", tmp_path)
    for sub, oid in (("gmaps", "gmaps:R1:d0"), ("tiktok", "tiktok:v1:d0"), ("official", "official:F:d0")):
        d = tmp_path / sub / "observations"
        d.mkdir(parents=True)
        (d / "0xF_0x1.json").write_text(json.dumps({"observations": [], "details": [{
            "id": oid, "source_type": "x", "observed_at": "2026-09-01", "span": {"quote": "vé 50k", "field": "text"}}]}),
            encoding="utf-8")
    got = exp.evidence_quotes("0xF:0x1")
    assert set(got) == {"gmaps:R1:d0", "tiktok:v1:d0", "official:F:d0"} and got["gmaps:R1:d0"]["text"] == "vé 50k"
