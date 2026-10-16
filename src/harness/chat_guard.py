"""Admission of free text and attack screening of structured turn values before module execution."""

import json
from typing import Callable

from agents import screen_input

REFUSAL = "Xin lỗi, mình chỉ hỗ trợ câu hỏi du lịch an toàn và hợp pháp."
INVALID = "Tin nhắn hoặc đường dẫn chưa hợp lệ. Bạn gửi lại yêu cầu du lịch ngắn gọn nhé."


def admit(safety: Callable[[str, str], str | None], payload: dict, current: dict, stage: str,
          review_text: bool = True) -> str | None:
    # Text in value may become the user message on a free-text card; image bytes are validated by Trip instead.
    texts = []
    stack = [v for k, v in payload.items() if not (k == "value" and payload.get("kind") == "image")]
    count = 0
    while stack:
        value = stack.pop()
        count += 1
        if count > 1000:
            return INVALID
        if isinstance(value, dict):
            stack.extend(value.values())
        elif isinstance(value, (list, tuple)):
            stack.extend(value)
        elif isinstance(value, str) and value.strip():
            try:
                decoded = json.loads(value)
            except (ValueError, RecursionError):
                decoded = None
            if isinstance(decoded, (dict, list, str)) and decoded != value:
                stack.append(decoded)
            verdict = screen_input(value)
            if verdict in {"attack", "off_topic"}:
                return REFUSAL
            if verdict == "invalid":
                return INVALID
    if not review_text:
        return None
    for name, value in payload.items():
        if not isinstance(value, str) or not value.strip() or name == "value" and payload.get("kind") == "image":
            continue
        if name == "text":
            texts.append(value)
        elif name == "value" and payload.get("kind") == "answer":
            card = current.get("card") or {}
            structured = str(payload.get("qid", "")).startswith("vibe:") or (
                card.get("qid") == payload.get("qid") and card.get("input") in {"geo", "lodging", "transit"})
            if not structured:
                texts.append(value)
    if not texts:
        return None
    transcript = [{"role": t.get("role"), "text": str(t.get("text") or "")[:600]}
                  for t in current.get("transcript", [])[-6:]]
    view = current.get("view") or {}
    context = {"stage": stage, "transcript": transcript, "card": current.get("card"), "pending": view.get("pending")}
    return safety("\n".join(texts), json.dumps(context, ensure_ascii=False, default=str))
