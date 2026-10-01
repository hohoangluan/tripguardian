"""Model roles and tasks: every prompt and model setting lives here (roles.py, tasks.py; asr.py = the local ASR role)."""

from .roles import EXTRACTOR, EXTRACTOR_EXTRA, JUDGE, Endpoint, Role
from .tasks import ASR_CHECK, PLACE_FILTER, PLACE_QC, PLACE_VIDEO_FILTER, PLACE_VIDEO_VERIFY, REVIEW_OBSERVE, REVIEW_VERIFY, VIDEO_FILTER, Task

__all__ = ["ASR_CHECK", "Endpoint", "EXTRACTOR", "EXTRACTOR_EXTRA", "JUDGE", "PLACE_FILTER", "PLACE_QC", "PLACE_VIDEO_FILTER", "PLACE_VIDEO_VERIFY", "REVIEW_OBSERVE", "REVIEW_VERIFY", "Role", "Task", "VIDEO_FILTER"]
