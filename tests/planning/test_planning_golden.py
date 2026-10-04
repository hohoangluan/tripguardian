"""Golden variants of a sample trip (docs/PLANNING.md §Test). A change to the algorithm that moves them must
update the file on purpose: UPDATE_GOLDEN=1 python -m pytest tests/planning/test_planning_golden.py"""

import json
import os
from pathlib import Path

from plan_fixtures import CFG, SOUTH, FakeLive, fake_matrix, fixed_sun, no_geocode, sample_trip, spot

from planning.variants import build_variants

GOLDEN = Path(__file__).parent / "golden" / "variants_wet_south.json"


def test_the_variants_of_the_sample_trip_match_the_golden_file():
    d, recs = sample_trip(leave_at="20:00", budget=1_500_000)
    recs[4:7] = [spot(f"s{i + 1}", SOUTH, i, features={"weather_exposed": "present"}) for i in range(3)]
    weather = {"2026-12-12": {"rain_prob": 0.2, "source": "open-meteo", "fetched_at": "t"},
               "2026-12-13": {"rain_prob": 0.8, "source": "open-meteo", "fetched_at": "t"}}
    out = build_variants(d, recs, cfg=CFG, live_cfg=FakeLive(), geocode_fn=no_geocode, matrix_fn=fake_matrix,
                         sun_fn=fixed_sun, weather=weather)
    if os.environ.get("UPDATE_GOLDEN"):
        GOLDEN.parent.mkdir(exist_ok=True)
        GOLDEN.write_text(json.dumps(out, ensure_ascii=False, indent=1, sort_keys=True) + "\n", encoding="utf-8")
    assert out == json.loads(GOLDEN.read_text(encoding="utf-8"))
