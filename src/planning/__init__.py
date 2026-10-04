"""Planning & Validation: confirmed places -> checked itineraries (docs/PLANNING.md).

python -m planning build <decision_output.json>
python -m planning variants <decision_output.json> [--weather forecast.json]
python -m planning lodging <decision_output.json> [--weather forecast.json]
python -m planning serve [--port 8768]
"""

from .build import build_plan, render_text
from .engine import Engine
from .server import run as run_server
from .settings import Settings
from .settings import load as load_settings
from .variants import build_lodging_variants, build_variants, render_lodging_variants, render_variants

__all__ = ["Engine", "Settings", "build_lodging_variants", "build_plan", "build_variants", "load_settings",
          "render_lodging_variants", "render_text", "render_variants", "run_server"]
