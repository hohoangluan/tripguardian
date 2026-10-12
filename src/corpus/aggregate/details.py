"""Details of a place (docs/CORPUS.md §5), code only: the free-text `detail.<kind>` observations of every source
-> clusters per kind. Two phrasings of one thing ("bánh căn trứng", "Bánh căn trứng ngon") form one cluster; a cluster
counts one vote per author, so it says how many independent people named the thing. Nothing is guessed: a cluster's
numbers (amount, months, hours) are those its members' quotes stated.

Which observations count: not labelled wrong (or unsure on a second look); a targeted sample (Maps' extremes /
keyword hits) only for a kind the ontology marks `targeted`; a business speaking about itself (an owner account, its
official page) only for a kind marked `owner`. Serving (corpus.serving.details) decides which clusters are served.
"""

import collections
import re
import statistics
import unicodedata
from functools import lru_cache

import yaml

from ..crawl.common.files import ROOT
from ..observe import TARGETED
from ..ontology import UNKNOWN, Ontology
from ..review import label_key
from .estimates import _VND

SERVING = ROOT / "config" / "serving.yaml"
AUTHORITATIVE = {"official_page"}  # the place's own site: one such source is enough to serve (serving)
EVIDENCE_MAX = 5


@lru_cache(maxsize=1)
def settings() -> dict:
    """config/serving.yaml `details` (read here so aggregate does not import serving)."""
    return yaml.safe_load(SERVING.read_text(encoding="utf-8"))["details"]


def tokens(text: str, stopwords) -> frozenset[str]:
    text = unicodedata.normalize("NFC", text or "").casefold()
    text = _VND.sub(" ", text)
    return frozenset(w for w in re.findall(r"\w+", text) if w not in stopwords)


def author_of(o: dict) -> str:
    return o.get("author") or o["id"]


def counts_for(o: dict, kind, verdicts: dict[str, str]) -> bool:
    if verdicts.get(label_key(o["source_id"], o["feature"], o["value"], o["span"]["quote"])) in ("wrong", "unsure_again"):
        return False
    if o.get("sample") in TARGETED and not kind.targeted:
        return False
    speaks_for_itself = ":owner:" in (o.get("author") or "") or o["source_type"] in AUTHORITATIVE
    return kind.owner or not speaks_for_itself


def same(a: frozenset, b: frozenset, jaccard: float) -> bool:
    if not a or not b:
        return a == b
    return len(a & b) / len(a | b) >= jaccard or a <= b or b <= a


def cluster(items: list[dict], jaccard: float) -> list[list[dict]]:
    """Groups of items ({text, tokens, author, id}) that say one thing. Deterministic: items are taken in order of how
    many authors wrote exactly that text, then by text; each joins the first group whose first item (leader) it matches
    (token overlap >= jaccard, or one token set inside the other), else leads a new group. No chaining through a
    middle item."""
    key = lambda x: " ".join(x["text"].casefold().split())  # noqa: E731
    writers = collections.defaultdict(set)
    for x in items:
        writers[key(x)].add(x["author"])
    groups: list[list[dict]] = []
    for x in sorted(items, key=lambda x: (-len(writers[key(x)]), key(x), x["author"], x["id"])):
        for g in groups:
            if key(g[0]) == key(x) or same(g[0]["tokens"], x["tokens"], jaccard):
                g.append(x)
                break
        else:
            groups.append([x])
    return groups


def typical(group: list[dict], jaccard: float) -> str:
    """The member phrase most members are close to (ties: the shorter, then alphabetical)."""
    close = lambda a, b: bool(a | b) and len(a & b) / len(a | b) >= jaccard  # noqa: E731 -- overlap only, not containment
    best = max(group, key=lambda x: (sum(close(x["tokens"], y["tokens"]) for y in group), -len(x["text"]),
                                     [-ord(c) for c in x["text"].casefold()]))
    return best["text"].strip()


def commonest(values):
    values = [v for v in values if v is not None]
    return collections.Counter(values).most_common(1)[0][0] if values else None


def build(group: list[dict], jaccard: float) -> dict:
    by_author = collections.defaultdict(list)
    for x in group:
        by_author[x["author"]].append(x)
    firsts = [xs[0] for xs in by_author.values()]
    amounts = [statistics.median(x["detail"]["amount_vnd"] for x in xs if x["detail"].get("amount_vnd"))
               for xs in by_author.values() if any(x["detail"].get("amount_vnd") for x in xs)]
    count = lambda pick: dict(sorted(collections.Counter(  # noqa: E731
        v for xs in by_author.values() for v in {v for x in xs for v in pick(x)}).items()))
    authority = any(x["source_type"] in AUTHORITATIVE for x in group)
    ranked = sorted(group, key=lambda x: (x["source_type"] not in AUTHORITATIVE, x["observed_at"] is None,
                                          [-ord(c) for c in x["observed_at"] or ""], x["id"]))
    evidence, seen = [], set()
    for x in ranked:  # one per author first
        if x["author"] not in seen and len(evidence) < EVIDENCE_MAX:
            seen.add(x["author"])
            evidence.append(x["id"])
    return {
        "text": typical(group, jaccard), "n": len(by_author), "authority": authority,
        "members": sorted(x["id"] for x in group), "evidence": evidence,
        "amount_vnd": int(round(statistics.median(amounts))) if amounts else None,
        "audience": commonest(x["detail"].get("audience") for x in firsts),
        "unit": commonest(x["detail"].get("unit") for x in firsts),
        "min_people": commonest(x["detail"].get("min_people") for x in firsts),
        "months": count(lambda x: x["detail"].get("months") or ()),
        "days": count(lambda x: x["detail"].get("days") or ()),
        "hours": sorted({x["detail"]["hour"] for x in group if x["detail"].get("hour")}),
        "time_of_day": count(lambda x: [x["context"]["time_of_day"]] if x["context"]["time_of_day"] != UNKNOWN else ()),
        "who": group[0]["detail"].get("who"),
        "verdicts": count(lambda x: [x["detail"]["verdict"]] if x["detail"].get("verdict") else ()),
    }


def place_details(files: list[dict], ont: Ontology, verdicts: dict[str, str], cfg: dict | None = None) -> dict[str, list[dict]]:
    """{kind: [cluster]} of one place, biggest first; a kind nobody observed is absent."""
    cfg = cfg or settings()
    stop = frozenset(cfg["stopwords"])
    by_kind = collections.defaultdict(list)
    for f in files:
        for o in f.get("details") or []:
            kind = ont.detail_kind(o["feature"])
            if kind and counts_for(o, kind, verdicts):
                by_kind[kind.id].append({"text": o["value"], "tokens": tokens(o["value"], stop), "author": author_of(o),
                                         "id": o["id"], "detail": o.get("detail") or {}, "context": o["context"],
                                         "source_type": o["source_type"], "observed_at": o.get("observed_at")})
    out = {}
    for kid, items in sorted(by_kind.items()):
        parts = [items]
        if kid == "fit":  # per companion first: "with the dog" and "with the baby" never merge
            who = collections.defaultdict(list)
            for x in items:
                who[x["detail"].get("who")].append(x)
            parts = [who[w] for w in sorted(who, key=str)]
        clusters = [build(g, cfg["cluster_jaccard"]) for part in parts for g in cluster(part, cfg["cluster_jaccard"])]
        out[kid] = sorted(clusters, key=lambda c: (-c["n"], not c["authority"], c["text"].casefold()))
    return out
