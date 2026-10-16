"""Chat admission by deterministic screening and static URL validation; no user text is executed.

Relevance is the Agent's call (CHAT_POLICY in its prompt), not a pre-classifier's: a model gate before the Agent cost
a round trip on every free-text turn and refused harmless questions about the assistant itself.
"""

from functools import cache
from pathlib import Path

import yaml
from pydantic import BaseModel, ConfigDict, Field

from corpus.llm import CHAT_POLICY

from .input_guard import screen_input, validate_public_url

REFUSAL = "Xin lỗi, mình chỉ hỗ trợ câu hỏi du lịch an toàn và hợp pháp."
INVALID = "Tin nhắn hoặc đường dẫn chưa hợp lệ. Bạn gửi lại yêu cầu du lịch ngắn gọn nhé."


class SafetySettings(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True)
    max_chars: int = Field(4000, ge=1, le=16000)


@cache
def settings() -> SafetySettings:
    path = Path(__file__).resolve().parents[2] / "config" / "security.yaml"
    return SafetySettings.model_validate(yaml.safe_load(path.read_text(encoding="utf-8"))["chat"])


class ChatSafety:
    def __init__(self, cfg: SafetySettings | None = None):
        self.cfg = cfg or settings()

    def __call__(self, text: str, context: str) -> str | None:
        screen = screen_input(text, context, self.cfg.max_chars)
        if screen == "invalid":
            return INVALID
        if screen in {"attack", "off_topic"}:
            return REFUSAL
        return None
