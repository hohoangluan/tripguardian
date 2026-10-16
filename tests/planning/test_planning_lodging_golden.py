"""Golden lodging variants of the sample trip (docs/PLANNING.md §Test).
UPDATE_GOLDEN=1 python -m pytest tests/planning/test_planning_lodging_golden.py"""

import json
import os
from pathlib import Path

from plan_fixtures import CENTRE, CFG, SOUTH, FakeLive, decision, fake_matrix, fixed_sun, no_geocode, sample_trip, spot, stay

from planning.variants import build_lodging_variants

GOLDEN = Path(__file__).parent / "golden" / "lodging_sample_trip.json"


def test_the_lodging_variants_of_the_sample_trip_match_the_golden_file():
    d, recs = sample_trip(budget=2_000_000, days=3)
    h0 = stay("h0", *SOUTH, name="Homestay Nam", rating=4.6, voices=30, price=280000)  # under the 300k cap
    out = build_lodging_variants(d, recs + [h0], cfg=CFG, live_cfg=FakeLive(), geocode_fn=no_geocode,
                                 matrix_fn=fake_matrix, sun_fn=fixed_sun)
    if os.environ.get("UPDATE_GOLDEN"):
        GOLDEN.parent.mkdir(exist_ok=True)
        GOLDEN.write_text(json.dumps(out, ensure_ascii=False, indent=1, sort_keys=True) + "\n", encoding="utf-8")
    assert out == json.loads(GOLDEN.read_text(encoding="utf-8"))


def test_overloaded_lodging_builder_keeps_real_candidates_and_their_prices():
    recs = [spot(f"p{i}", CENTRE, i % 7) for i in range(8)]
    d = decision([r["id"] for r in recs], days=1, leave_at="21:00")
    d["feasibility"] = {"status": "infeasible", "totals": {"needed": 1000, "available": 600},
                        "conflicts": [{"check": "time", "id": "time"}]}
    h0 = stay("h0", *SOUTH, name="Homestay thật", rating=4.6, voices=30, price=350000)
    out = build_lodging_variants(d, recs + [h0], cfg=CFG, live_cfg=FakeLive(), geocode_fn=no_geocode,
                                 matrix_fn=fake_matrix, sun_fn=fixed_sun)
    assert {d for v in out["variants"] for d in [v["id"], *v.get("merged", [])]} == {"fit", "travel", "cost"}
    assert any(c["id"] == "h0" and c["price_vnd"] == 350000 for c in out["lodging"]["candidates"])
