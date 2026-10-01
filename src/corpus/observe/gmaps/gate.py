"""Gate (docs/specs/CORPUS_SPEC.md §6) for one Extractor answer: only observations whose feature and value the
ontology knows and whose quote is really in the review survive. Quotes match after NFC, whitespace and case folding.
"""

import collections
import re
import unicodedata

from ...ontology import UNKNOWN, Ontology
from .. import CONTEXT_KEYS


class BadAnswer(Exception):
    pass


def norm(text: str) -> str:
    return re.sub(r"\s+", " ", unicodedata.normalize("NFC", text)).strip().casefold()


def gate(answer: dict, refs: dict[str, dict], ont: Ontology):
    if not isinstance(answer, dict) or not isinstance(answer.get("reviews"), list):
        raise BadAnswer("answer has no reviews list")
    kept, proposed, dropped = [], [], collections.Counter()
    for item in answer["reviews"]:
        ref = item.get("ref")
        if ref not in refs:
            dropped["unknown_ref"] += 1
            continue
        text = norm(refs[ref]["text"])
        for o in item.get("observations") or []:
            quote = norm(o.get("quote") or "")
            context = {k: o.get(k) or UNKNOWN for k in CONTEXT_KEYS}
            if not ont.valid(o.get("feature"), o.get("value")):
                dropped["not_in_ontology"] += 1
            elif not quote or quote not in text:
                dropped["quote_not_in_review"] += 1
            elif not all(ont.valid_context(k, v) for k, v in context.items()):
                dropped["bad_context"] += 1
            else:
                kept.append((ref, {"feature": o["feature"], "value": o["value"], "quote": o["quote"].strip(),
                                   "context": context}))
        for p in item.get("proposed") or []:
            quote = norm(p.get("quote") or "")
            if (p.get("label") or "").strip() and quote and quote in text:
                proposed.append((ref, {"label": p["label"].strip(), "quote": p["quote"].strip()}))
            else:
                dropped["proposed_bad_quote"] += 1
    return kept, proposed, dropped
