"""official observe: a place's own website (corpus.crawl.official) -> data/official/observations/<fid_dir>.json.

The Extractor (corpus.llm.OFFICIAL_OBSERVE) reads the page text in chunks and names entry ticket prices and opening
hours with a quote; code keeps a fact only when its quote is in the page and its amount / times are in its quote
(gate). A site several listed places share (one operator's site) only gives facts whose quote stands near a
distinctive word of the place's name. Output, in the shared observation format: `entry_fee` paid / free
(source_type `official_page`, one authoritative author `official:<fid>`, docs/CORPUS.md §5) and `place_facts`:
`hours` ({day: [[open, close], ...]} for the days the site names; ranges that overlap one another are a conflict and
give no hours) and `tickets_vnd` ({adult: [...], child: [...]}). A place is read again when its pages or the prompt
change; a failed call leaves the place without a file (retried next run, data/official/observe_errors.jsonl).
"""

import asyncio
import collections
import hashlib
import json
import re
import unicodedata
from urllib.parse import urlparse

import openai

from ...crawl.common.files import append_jsonl, data_dir, load_config, now, safe_name, write_json
from ...llm import OFFICIAL_OBSERVE, OutOfQuota
from ...ontology import UNKNOWN, load as load_ontology
from .. import observation

CHUNK_CHARS = 6000
NEAR = 500  # chars around a quote that must name the place on a shared site
SOURCE_TYPE = "official_page"
WANT = re.compile(r"\d\s*(?:k|đ|đồng|vnđ|vnd|nghìn|ngàn|000)\b|\d{1,2}\s*(?:h|giờ|:)\s*\d{0,2}|vé|giá|miễn phí|free|"
                  r"mở cửa|giờ hoạt động|opening|ticket", re.I)
FREE = re.compile(r"miễn phí|free|không (?:thu|mất) phí|không bán vé", re.I)
TIME = re.compile(r"^([01]\d|2[0-4]):([0-5]\d)$")
DAYS = ("sun", "mon", "tue", "wed", "thu", "fri", "sat")
GENERIC = {"da", "lat", "dalat", "quan", "cafe", "coffee", "ca", "phe", "nha", "hang", "tiem", "the", "va", "and",
           "khu", "du", "lich", "cn", "chi", "nhanh", "spa", "massage", "vuon", "farm", "garden", "store", "shop",
           "center", "centre", "dl", "kdl", "resort", "park", "cong", "vien"}


def norm(text: str) -> str:
    return " ".join(unicodedata.normalize("NFC", text or "").split()).casefold()


def fold(text: str) -> str:
    text = unicodedata.normalize("NFD", (text or "").lower())
    return "".join(c for c in text if unicodedata.category(c) != "Mn").replace("đ", "d")


def name_words(name: str) -> set[str]:
    return {w for w in re.findall(r"[a-z0-9]+", fold(name)) if len(w) > 1} - GENERIC


def chunks(pages: list[dict]) -> list[tuple[str, str]]:
    """(url, text) pieces of at most CHUNK_CHARS that may state a price or hours; a line repeated on several pages
    of the site (menus, footers) is kept on the first page only."""
    seen, out = set(), []
    for p in pages:
        lines = []
        for line in (p.get("text") or "").splitlines():
            key = norm(line)
            if not key or key in seen:
                continue
            seen.add(key)
            lines.append(line.strip())
        cur = ""
        for line in lines:
            if cur and len(cur) + len(line) + 1 > CHUNK_CHARS:
                out.append((p["url"], cur))
                cur = ""
            cur = f"{cur}\n{line}" if cur else line
        if cur:
            out.append((p["url"], cur))
    return [(u, t) for u, t in out if WANT.search(t)]


def amount_in(quote: str, amount: int) -> bool:
    digits = re.sub(r"(?<=\d)[.,\s](?=\d{3}(?!\d))", "", quote)
    if re.search(rf"(?<!\d){amount}(?!\d)", digits):
        return True
    return amount % 1000 == 0 and bool(re.search(rf"(?<!\d){amount // 1000}\s*(?:k|nghìn|ngàn|n)(?!\w)", quote, re.I))


def hour_in(quote: str, hhmm: str) -> bool:
    h = int(hhmm[:2])
    return any(re.search(rf"(?<!\d)0?{x}(?!\d)", quote) for x in {h, h - 12, h % 24} if x >= 0)


def near_name(text: str, quote: str, words: set[str]) -> bool:
    at = norm(text).find(norm(quote))
    window = fold(norm(text)[max(0, at - NEAR):at + len(norm(quote)) + NEAR])
    return bool(words) and any(re.search(rf"\b{w}\b", window) for w in words)


def gate(fact: dict, text: str, words: set[str] | None) -> str | None:
    """None when the fact stands, else why it is dropped. words: the place's distinctive name words, required near the
    quote on a shared site (None = the site is this place's own)."""
    q = fact["quote"].strip()
    if not q or norm(q) not in norm(text):
        return "quote_not_in_page"
    if words is not None and not near_name(text, q, words):
        return "shared_site_other_place"
    if fact["kind"] == "ticket":
        if fact["audience"] not in ("adult", "child") or not 1000 <= fact["amount_vnd"] <= 5_000_000:
            return "not_entry_ticket"
        return None if amount_in(q, fact["amount_vnd"]) else "amount_not_in_quote"
    if fact["kind"] == "free":
        return None if FREE.search(q) else "free_not_in_quote"
    if not (TIME.match(fact["open"]) and TIME.match(fact["close"])) or not fact["days"]:
        return "bad_hours"
    if fact["open"] >= fact["close"] and fact["close"] != "00:00":
        return "bad_hours"
    return None if hour_in(q, fact["open"]) and hour_in(q, fact["close"]) else "hours_not_in_quote"


def hours_of(facts: list[dict]) -> dict | None:
    """{day: [[open, close], ...]} of the kept hours facts; ranges of one day that overlap differ -> conflict -> None."""
    by_day = collections.defaultdict(set)
    for f in facts:
        for d in f["days"]:
            by_day[d].add((f["open"], f["close"]))
    out = {}
    for d in DAYS:
        if d not in by_day:
            continue
        ranges = sorted(by_day[d])
        if any(b[0] < a[1] for a, b in zip(ranges, ranges[1:])):
            return None
        out[d] = [list(r) for r in ranges]
    return out or None


def shared_hosts(files: list[dict]) -> set[str]:
    hosts = collections.Counter(urlparse(f["website"] if "//" in f["website"] else "http://" + f["website"])
                                .netloc.lower().removeprefix("www.") for f in files)
    return {h for h, n in hosts.items() if n > 1}


def build(doc: dict, place: dict, kept: list[tuple[str, dict]], ont_version: int) -> dict:
    fid = doc["fid"]
    ctx = dict.fromkeys(("time_of_day", "day_type", "weather"), UNKNOWN)
    obs, seen = [], set()
    for url, f in kept:
        if f["kind"] == "hours":
            continue
        value = "free" if f["kind"] == "free" else "paid"
        if (value, norm(f["quote"])) in seen:
            continue
        seen.add((value, norm(f["quote"])))
        obs.append(observation(id=f"official:{fid}:{len(obs)}", place_fid=fid, feature="entry_fee", value=value,
                               context=ctx, source_type=SOURCE_TYPE, source_id=url, author=f"official:{fid}",
                               observed_at=doc["fetched_at"][:10], quote=f["quote"].strip(), field="page_text",
                               extractor=f"official_observe@{OFFICIAL_OBSERVE.prompt_hash}",
                               ontology_version=ont_version))
    if any(f["kind"] == "ticket" and f["audience"] == "adult" for _, f in kept):  # "dưới 90cm miễn phí"
        obs = [o for o in obs if o["value"] != "free"]
    tickets = {a: sorted({f["amount_vnd"] for _, f in kept if f["kind"] == "ticket" and f["audience"] == a})
               for a in ("adult", "child")}
    return {"place_fid": fid, "place_name": place.get("name"), "as_of": doc["fetched_at"][:10], "source": "official",
            "website": doc["website"], "observations": obs, "proposed": [], "ratings": [], "place": {}, "voices": 0,
            "place_facts": {"hours": hours_of([f for _, f in kept if f["kind"] == "hours"]),
                            "tickets_vnd": tickets if any(tickets.values()) else None}}


async def run(city: str, limit: int | None = None) -> dict:
    name, _ = load_config(city)
    root = data_dir() / "official"
    out = root / "observations"
    ont = load_ontology()
    files = [json.loads(p.read_text(encoding="utf-8")) for p in sorted((root / "pages").glob("*.json"))] \
        if (root / "pages").exists() else []
    shared = shared_hosts(files)
    todo = []
    for doc in files:
        h = hashlib.sha256(json.dumps([doc["fetched_at"], [p["text"] for p in doc["pages"]],
                                       OFFICIAL_OBSERVE.prompt_hash, ont.version]).encode()).hexdigest()[:16]
        target = out / f"{safe_name(doc['fid'])}.json"
        if target.exists() and json.loads(target.read_text(encoding="utf-8")).get("input_hash") == h:
            continue
        todo.append((doc, h, target))
    todo = todo[:limit]
    print(f"official observe {city}: {len(todo)} sites to read", flush=True)
    if not todo:
        return {"read": 0}
    client, model = OFFICIAL_OBSERVE.role.client()
    client = client.with_options(timeout=240, max_retries=0)
    sem = asyncio.Semaphore(OFFICIAL_OBSERVE.parallel)
    status, dropped = collections.Counter(), collections.Counter()

    async def ask(place, url, text, note):
        for tries in range(30):
            try:
                async with sem:
                    return await OFFICIAL_OBSERVE.ask(client, model, city=name, name=place.get("name"),
                                                      category=place.get("category") or "unknown",
                                                      address=place.get("address") or "unknown", note=note, url=url,
                                                      text=text)
            except (OutOfQuota, openai.RateLimitError, openai.APIConnectionError, openai.APITimeoutError):
                if tries == 29:
                    raise
                await asyncio.sleep(20)

    async def one(doc, h, target):
        pf = data_dir() / "gmaps" / "places" / safe_name(doc["fid"]) / "place.json"
        place = json.loads(pf.read_text(encoding="utf-8")) if pf.exists() else {"name": doc.get("name")}
        host = urlparse(doc["website"] if "//" in doc["website"] else "http://" + doc["website"]).netloc.lower()
        words = name_words(place.get("name") or "") if host.removeprefix("www.") in shared else None
        note = (f"This website belongs to an operator of several places: take only facts given for {place.get('name')}."
                if words is not None else "")
        try:
            parts = chunks(doc["pages"])
            answers = await asyncio.gather(*(ask(place, u, t, note) for u, t in parts))
        except Exception as e:
            append_jsonl(root / "observe_errors.jsonl", {"at": now(), "place": safe_name(doc["fid"]),
                                                          "error": f"{type(e).__name__}: {str(e)[:300]}"})
            status["failed"] += 1
            return
        kept, mine = [], collections.Counter()
        for (url, text), ans in zip(parts, answers):
            for f in ans["facts"]:
                why = gate(f, text, words)
                if why:
                    mine[why] += 1
                else:
                    kept.append((url, f))
        dropped.update(mine)
        write_json(target, {**build(doc, place, kept, ont.version), "input_hash": h,
                            "prompt_hash": OFFICIAL_OBSERVE.prompt_hash, "ontology_version": ont.version,
                            "model": model, "built_at": now(), "stats": {"chunks": len(parts), "kept": len(kept),
                                                                          "dropped": dict(mine)}})
        status["done"] += 1

    await asyncio.gather(*(one(*t) for t in todo))
    summary = {"at": now(), "status": dict(status), "dropped": dict(dropped)}
    print(f"official observe {city}: {json.dumps(summary, ensure_ascii=False)}", flush=True)
    return summary
