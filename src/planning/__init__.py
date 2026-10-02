"""Planning & Validation: confirmed places -> a checked itinerary (docs/specs/PLANNING_SPEC.md).

python -m planning build <decision_output.json>
"""

from .build import build_plan, render_text
from .settings import Settings
from .settings import load as load_settings

__all__ = ["Settings", "build_plan", "load_settings", "render_text"]
