"""Cloudflare Clef: a small zero-shot classifier (docs/TRIP_UNDERSTANDING.md §4).

It answers natural-language questions with a probability per option. It checks facts and replies the Agent produced
(`Judge`) and ranks features; it never gates a message before the Agent. A slow or failing Clef decides nothing (fail open).
"""

import json
import re
import os
import urllib.request

from dotenv import load_dotenv

from ..domain.text import squash
from .settings import ROOT, Settings

FEATURE = "tool.feature_rank"
NONE = "none"
SUPPORT = "fact.supported_by_quote"
CLARITY = "other.states_value"  # quiz other-gate: a typed answer clearly states a value for the field
PROMISE = "reply.promises_results"
INVENT = "reply.states_unsaid_fact"


def ask(state: dict, questions: dict, cfg: Settings) -> dict:
    """One Clef request -> {question name: answer}. {} when Clef is not configured, slow or failing: it decides nothing."""
    load_dotenv(ROOT / ".env")
    token, account = os.getenv("CLOUDFLARE_API_TOKEN"), os.getenv("CLOUDFLARE_ACCOUNT_ID")
    if not (token and account):
        return {}
    try:
        timeout = float(os.getenv("CLEF_TIMEOUT_S", cfg.clef_timeout_s))
    except ValueError:
        timeout = cfg.clef_timeout_s
    payload = {"model": os.getenv("CLEF_MODEL", "clef-flash"), "state": state, "questions": questions}
    model_id = os.getenv("CLEF_MODEL_ID", "@cf/cloudflare/clef-flash")
    request = urllib.request.Request(
        f"https://api.cloudflare.com/client/v4/accounts/{account}/ai/run/{model_id}", json.dumps(payload).encode(),
        {"Content-Type": "application/json", "Authorization": f"Bearer {token}"}, method="POST")
    try:
        with urllib.request.urlopen(request, timeout=timeout) as response:
            raw = json.load(response)["result"]["answers"]
            return raw if isinstance(raw, dict) else {a["name"]: a for a in raw}  # by name; older replies were a list
    except (OSError, ValueError, KeyError, TypeError):
        return {}


def prob(answers: dict, name: str, option: str) -> float:
    """The probability Clef gave `option` of question `name`; 0 when it chose another option or did not answer."""
    a = answers.get(name) or {}
    try:
        return float((a.get("probabilities") or {}).get(option, 0)) if a.get("choice") == option else 0.0
    except (TypeError, ValueError):
        return 0.0


def feature_question(features) -> dict:
    """Which features of a place the message asks for. A closed set always picks something: "none" is the way out."""
    return {"type": "choice",
            "instructions": "Tin nhắn của khách nêu mong muốn nào về đặc điểm của một địa điểm? Chọn none nếu chỉ nói thông tin "
                            "chuyến đi (ngày, người, phương tiện, ngân sách) hoặc không đặc điểm nào diễn đạt được.",
            "criteria": {**{f.id: f"{f.id}: {f.hint[:100]}" for f in features}, NONE: "không đặc điểm nào ở trên diễn đạt được"}}


def ranked(answers: dict, ids, at_least: float, top: int) -> tuple[str, ...]:
    """Feature ids Clef gave at least `at_least`, best first, at most `top`."""
    probs = (answers.get(FEATURE) or {}).get("probabilities") or {}
    best = sorted(((float(p), k) for k, p in probs.items() if k in ids), reverse=True)
    return tuple(k for p, k in best[:top] if p >= at_least)


# a negation right before a word of the claim reverses it: "không đi bộ xa được" against "muốn đi bộ"
NEGATION = re.compile(r"\b(khong|chang|dung|chua|khong duoc|khong the)\s+(?:\w+\s+){0,2}?(\w+)")
STOP_CLAIM = {"khach", "muon", "tranh", "phai", "co", "the", "cho", "mot", "nhung", "khong", "chi", "duoc"}


def reverses(quote: str, claim: str) -> bool:
    """True when the user's quote negates a word of the claim, so the quote says the opposite. Code, not Clef: Clef
    reads polarity inconsistently. 'không muốn …' is left out: it is a wish for the opposite, which Clef judges."""
    if squash(claim.split(":", 1)[0]).endswith("tranh"):  # "muốn tránh X": a negation there is the wish itself
        return False
    words = {w for w in squash(claim.split(":", 1)[-1]).split() if len(w) >= 2 and w not in STOP_CLAIM}
    for m in NEGATION.finditer(squash(quote)):
        if m[2] in words:
            return True
    return False


class Judge:
    """Small yes / no checks on what the Agent is about to write or ask. Each one fails open: no answer, no veto."""

    def __init__(self, cfg: Settings):
        self.cfg = cfg

    def features(self, wish: str, features) -> list[str]:
        """Feature ids that express `wish`, best first (features: the ontology's Feature objects)."""
        answers = ask({"user_message": wish}, {FEATURE: feature_question(features)}, self.cfg)
        return list(ranked(answers, {f.id for f in features}, self.cfg.clef_feature_min, 5))

    def unsupported(self, quote: str, claim: str) -> bool:
        """True only when Clef is sure the user's `quote` does not say `claim`, or the quote negates the claim."""
        if reverses(quote, claim):
            return True
        answers = ask({"user_message": quote, "claim": claim}, {SUPPORT: {
            "type": "choice",
            "instructions": "The user's message is in Vietnamese. Decide whether it supports the claim. "
                            "Answer B if it says the opposite of the claim. Answer D if it is unrelated to the claim.",
            "criteria": {"A": "the message clearly states the claim, same direction",
                         "C": "the claim can be reasonably inferred from the situation, and the message does not negate it",
                         "B": "the message says the opposite of the claim, or negates it",
                         "D": "the message is unrelated, or nothing supports the claim"}}}, self.cfg)
        # reversed or unrelated facts are refused; a clear or reasonable inference is kept
        return prob(answers, SUPPORT, "B") + prob(answers, SUPPORT, "D") >= self.cfg.clef_verify_min

    def clear_for_field(self, text: str, field_label: str) -> bool:
        """Quiz other-gate: True only when Clef is sure the typed answer clearly
        states a value for this field. Anything else (and any Clef failure) means
        the chat phase resolves it. Fail-open towards the chat, never towards a guess."""
        answers = ask({"user_message": text, "field": field_label}, {CLARITY: {
            "type": "choice", "instructions": f"Câu của khách có nói rõ một giá trị cho {field_label} không? "
                                              "Rõ là nêu con số, lựa chọn hay ý cụ thể (kể cả nói khác từ gợi ý). "
                                              "Chỉ chọn A khi đúng vậy.",
            "criteria": {"A": "nói rõ", "B": "không nói hoặc mơ hồ", "C": "chưa rõ"}}}, self.cfg)
        return prob(answers, CLARITY, "A") >= self.cfg.clef_clarity_min

    def bad_reply(self, say: str, user: str = "") -> str | None:
        """Why `say` may not be shown: it promises results, or states a fact the user never gave. None when fine or unsure.
        user: what the user said in this session, so a figure the reply only repeats is not taken for a made-up one."""
        answers = ask({"user_said": user, "reply": say}, {
            PROMISE: {"type": "choice", "instructions": "Câu trả lời có hứa sẽ gợi ý địa điểm, lịch trình hay tìm kiếm không?",
                      "criteria": {"A": "có hứa hoặc nói sẽ làm", "B": "không", "C": "chưa rõ"}},
            INVENT: {"type": "choice", "instructions": "Câu trả lời có nêu số liệu hay thông tin cụ thể về địa điểm, giá, giờ, "
                                                       "thời tiết như một sự thật mà người dùng chưa nói (user_said) không? "
                                                       "Nhắc lại đúng điều người dùng đã nói là không.",
                     "criteria": {"A": "có nêu", "B": "không", "C": "chưa rõ"}}}, self.cfg)
        if prob(answers, PROMISE, "A") >= self.cfg.clef_reply_min:
            return "promises results"
        if prob(answers, INVENT, "A") >= self.cfg.clef_reply_min:
            return "states a fact nobody gave"
        return None

