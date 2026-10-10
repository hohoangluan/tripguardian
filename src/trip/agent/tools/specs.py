"""What the Trip agent may call: spec dicts in OpenAI function format (single source of truth)."""

from typing import get_args

from ...domain.guard import FieldName

STOPPING = ("ask_choice", "ask_text", "open_quiz")
MAX_OPTIONS, MAX_OPTION_LEN = 6, 40
MAX_SENT_BACK = 2
# folded Vietnamese words that match almost every feature hint ("chó" folds to "cho" = "for")
STOP = {"cho", "co", "la", "va", "de", "o", "voi", "cua", "nhung", "khong", "mot", "cac", "nao", "duoc", "den", "trong",
        "nay", "thi", "muon", "thich", "choi", "di"}


def _fn(name: str, description: str, properties: dict, required: list[str]) -> dict:
    return {"type": "function", "function": {"name": name, "description": description, "parameters": {
        "type": "object", "properties": properties, "required": required, "additionalProperties": False}}}


SPECS = {
    "record_fact": _fn(
        "record_fact", "Write ONE fact about this trip that the user's latest message states or clearly implies. "
        "Call it once per fact. A refusal comes back as an error: fix the call or drop the fact.",
        {"field": {"type": "string", "enum": list(get_args(FieldName))},
         "op": {"type": "string", "enum": ["set", "add", "remove"]},
         "value": {"type": "string", "description": "In the format the instructions give for this field."},
         "quote": {"type": "string", "description": "The user's own words that support it, copied from the latest message."},
         "how": {"type": "string", "enum": ["said", "inferred"]}},
        ["field", "op", "value", "quote", "how"]),
    "resolve_relative_date": _fn(
        "resolve_relative_date", "Turn a relative date the user said (\"thứ 4 tuần sau\") into an ISO date.",
        {"expression": {"type": "string", "description": "The exact relative-date words from the user."}}, ["expression"]),
    "search_places": _fn(
        "search_places", "Look a place name the user typed up in the catalog. Never invent a place.",
        {"query": {"type": "string", "description": "The exact place words from the user."}}, ["query"]),
    "search_features": _fn(
        "search_features", "Look up which search features express a wish (\"chó\" -> animals). Use it BEFORE record_fact "
        "when no feature in FEATURES obviously fits; a wish no feature expresses cannot change the search.",
        {"query": {"type": "string", "description": "Vietnamese or English words for the wish; try synonyms."}}, ["query"]),
    "ask_choice": _fn(
        "ask_choice", f"Ask the user ONE multiple-choice question and wait. 2-{MAX_OPTIONS} short options in Vietnamese, "
        "each at most 40 characters. Ends your turn.",
        {"text": {"type": "string"}, "options": {"type": "array", "items": {"type": "string"}},
         "multi": {"type": "boolean", "description": "true when several options may be picked."},
         "reason": {"type": "string", "description": "Why this matters, one short Vietnamese clause."},
         "placeholder": {"type": "string", "description": "Example of what the user could type in the \"other answer\" box, "
                         "for THIS question, in their voice (\"cuối tháng 12\"). Empty if none."}},
        ["text", "options", "multi", "reason", "placeholder"]),
    "ask_text": _fn(
        "ask_text", "Ask the user ONE open question and wait for typed text, or a picked day. Ends your turn.",
        {"text": {"type": "string", "description": "ONLY the question, one short Vietnamese sentence: no greeting, no praise."},
         "placeholder": {"type": "string", "description": "Example answer the user could type, for THIS question, in their voice "
                         "(\"cuối tháng 12, hoặc 20/12\")."},
         },
        ["text", "placeholder"]),
    "open_quiz": _fn(
        "open_quiz", "Open the quiz when the user explicitly asks to start it, continue it, or do it again "
        "(\"mở phần câu hỏi\", \"hỏi tiếp đi\", \"làm lại trắc nghiệm\"). The system starts the first quiz, "
        "continues a paused quiz, or brings answered cards back so answers can change. Call it with no arguments, "
        "after one short handover line in text. Ends your turn.",
        {}, []),
}
