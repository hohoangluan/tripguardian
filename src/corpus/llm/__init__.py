"""LLM roles and tasks: every prompt and model setting lives here (roles.py, tasks.py)."""

from .roles import EXTRACTOR, JUDGE, Role
from .tasks import PLACE_FILTER, PLACE_QC, VIDEO_FILTER, Task

__all__ = ["EXTRACTOR", "JUDGE", "PLACE_FILTER", "PLACE_QC", "Role", "Task", "VIDEO_FILTER"]
