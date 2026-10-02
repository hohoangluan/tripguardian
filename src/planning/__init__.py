"""Planning & Validation: confirmed places -> checked itineraries (docs/specs/PLANNING_SPEC.md).

python -m planning build <decision_output.json>
python -m planning variants <decision_output.json> [--weather forecast.json]
"""

from .build import build_plan, render_text
from .settings import Settings
from .settings import load as load_settings
from .variants import build_variants, render_variants

__all__ = ["Settings", "build_plan", "build_variants", "load_settings", "render_text", "render_variants"]
