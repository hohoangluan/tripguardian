"""Model roles and tasks: every prompt and model setting lives here (roles.py, tasks.py; asr.py = the local ASR role)."""

from .roles import AGENT, EXTRACTOR, JUDGE, JUDGE_FIRST, JUDGE_STRONG, TTS, USER_SIM, Role
from .tasks import (ASR_CHECK, INSIGHT_CLUSTER, OFFICIAL_OBSERVE, DECISION_TURN, OBS_AUDIT, OBS_AUDIT_FIRST, OBS_AUDIT_GEMMA, OBS_AUDIT_STRONG, PLACE_FILTER, PLACE_POI_MATCH, PLACE_QC, PLACE_STATUS, PLACE_STATUS_STRONG, PLACE_VIDEO_FILTER, PHOTO_OBSERVE, PHOTO_RANK, PHOTO_VERIFY,
                    PLACE_VIDEO_VERIFY, PLANNING_TURN, REVIEW_OBSERVE, REVIEW_QC, REVIEW_VERIFY, SAME_PLACE, SAME_PLACE_STRONG,
                    USER_SIM_BRIEF, USER_SIM_REPLY, VIDEO_FILTER, VIDEO_OBSERVE, VIDEO_VERIFY, OutOfQuota, Task)

__all__ = ["transcribe_file", "AGENT", "ASR_CHECK", "INSIGHT_CLUSTER", "OFFICIAL_OBSERVE", "DECISION_TURN", "EXTRACTOR", "JUDGE", "JUDGE_FIRST", "JUDGE_STRONG", "OBS_AUDIT", "OBS_AUDIT_FIRST", "OBS_AUDIT_GEMMA", "OBS_AUDIT_STRONG",
           "PLACE_STATUS", "PLACE_STATUS_STRONG", "REVIEW_QC", "SAME_PLACE", "SAME_PLACE_STRONG", "PLACE_FILTER", "PLACE_POI_MATCH", "PLACE_QC", "PLACE_VIDEO_FILTER", "PHOTO_OBSERVE", "PHOTO_RANK", "PHOTO_VERIFY", "PLACE_VIDEO_VERIFY",
            "PLANNING_TURN", "REVIEW_OBSERVE", "REVIEW_VERIFY", "Role", "TTS", "Task", "USER_SIM", "USER_SIM_BRIEF", "USER_SIM_REPLY", "VIDEO_FILTER", "VIDEO_OBSERVE", "VIDEO_VERIFY", "OutOfQuota"]


def transcribe_file(path) -> str:
    """Plain text of a 16 kHz mono wav from the local ASR role; "" when the clip holds no speech (VAD first, so
    silence or noise is never decoded into words)."""
    from . import asr  # heavy (torch, ChunkFormer): imported when something is transcribed

    if not asr.speech(asr.read(path)):
        return ""
    return " ".join(seg["text"] for seg in asr.transcribe(path) if seg["text"])
