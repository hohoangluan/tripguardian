"""Trip Understanding benchmark: hidden trips, simulated users, scores (docs/plans/BENCH.md).

python -m bench generate --seed 1 [--briefs --live]
python -m bench run [--styles tapper,baseline,brief] [--only t01,t02] [--live]
"""

from .generate import generate, quotas
from .hidden import HiddenTrip, load
from .run import run

__all__ = ["HiddenTrip", "generate", "load", "quotas", "run"]
