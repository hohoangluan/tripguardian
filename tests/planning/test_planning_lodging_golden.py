"""Golden lodging variants of the sample trip (docs/specs/PLANNING_SPEC.md §Test).
UPDATE_GOLDEN=1 python -m pytest tests/planning/test_planning_lodging_golden.py"""

import json
import os
from pathlib import Path

from plan_fixtures import CFG, SOUTH, FakeLive, fake_matrix, fixed_sun, no_geocode, sample_trip

from planning.variants import build_lodging_variants

GOLDEN = Path(__file__).parent / "golden" / "lodging_sample_trip.json"


def test_the_lodging_variants_of_the_sample_trip_match_the_golden_file():
    d, recs = sample_trip(budget=2_000_000, days=3)
    lodging_fn = lambda *a: [{"id": "h0", "name": "Homestay Nam", "lat": SOUTH[0], "lng": SOUTH[1], "rating": 4.6,
                             "reviews": 30, "price_vnd": 350000, "amenities": ["wifi"]}]
    out = build_lodging_variants(d, recs, cfg=CFG, live_cfg=FakeLive(), geocode_fn=no_geocode, matrix_fn=fake_matrix,
                                 sun_fn=fixed_sun, lodging_fn=lodging_fn)
    if os.environ.get("UPDATE_GOLDEN"):
        GOLDEN.parent.mkdir(exist_ok=True)
        GOLDEN.write_text(json.dumps(out, ensure_ascii=False, indent=1, sort_keys=True) + "\n", encoding="utf-8")
    assert out == json.loads(GOLDEN.read_text(encoding="utf-8"))
