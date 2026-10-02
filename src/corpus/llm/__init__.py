"""Model roles and tasks: every prompt and model setting lives here (roles.py, tasks.py; asr.py = the local ASR role)."""

from .roles import AGENT, EXTRACTOR, JUDGE, Role
from .tasks import (ASR_CHECK, DECISION_TURN, PLACE_FILTER, PLACE_QC, PLACE_VIDEO_FILTER, PHOTO_OBSERVE, PHOTO_VERIFY,
                    PLACE_VIDEO_VERIFY, REVIEW_OBSERVE, REVIEW_VERIFY,
                    TRIP_TURN, VIDEO_FILTER, VIDEO_OBSERVE, VIDEO_VERIFY, Task)

__all__ = ["AGENT", "ASR_CHECK", "DECISION_TURN", "EXTRACTOR", "JUDGE", "PLACE_FILTER", "PLACE_QC", "PLACE_VIDEO_FILTER", "PHOTO_OBSERVE", "PHOTO_VERIFY", "PLACE_VIDEO_VERIFY",
           "REVIEW_OBSERVE", "REVIEW_VERIFY", "Role", "TRIP_TURN", "Task", "VIDEO_FILTER", "VIDEO_OBSERVE", "VIDEO_VERIFY"]
