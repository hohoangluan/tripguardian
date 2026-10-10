"""Every model task in one place: role, prompt, output schema and call settings. Edit prompts and settings here.

A task's prompt_hash is stored with each result, so changing a prompt re-runs that task on the next build.
"""

import asyncio
import base64
import hashlib
import json
import re
import time
from dataclasses import dataclass, replace

import openai

from .roles import AGENT, EXTRACTOR, JUDGE, JUDGE_FIRST, JUDGE_STRONG, USER_SIM, Role

ATTEMPTS = 4  # per call: a broken JSON answer or a busy / unreachable server is tried again
RETRY_S = 2.0  # first wait after HTTP 429 or a connection error; doubles each time
RUNAWAY_WS = 300  # whitespace chars in a row that mean a guided answer is looping (it would run on to max_tokens)
RUNAWAYS = 2  # a looping answer is asked again once: it loops again on the same input, so more tries only burn the server


class BadBody(Exception):
    """The server answered with text that is not a chat completion; retried like a busy server."""


class Runaway(ValueError):
    """Guided decoding looped on whitespace instead of finishing the JSON; the read was cut."""


class OutOfQuota(Exception):
    """Every model of a pool is resting after a usage-limit answer."""


_REST: dict[str, float] = {}  # model -> monotonic time it may be asked again (after a usage-limit answer)
QUOTA_REST_S = 600.0  # when the server does not say how long
UNSUPPORTED_REST_S = 60.0  # 9router rotates accounts; one may not offer the model


def _quota_rest(e: Exception) -> float | None:
    """Seconds to rest a model after this error, or None when it is not a usage limit. 9router answers an exhausted
    upstream account with 503 or 429 and "usage limit ... (reset after 19m 38s)" or an exhausted-quota message."""
    text = str(e)
    if re.search(r"model is not supported when using", text, re.I):
        return UNSUPPORTED_REST_S  # the proxy picked an account without this model; the next pick may have it
    if not re.search(r"usage limit|quota|exhausted|resource_exhausted|reset after", text, re.I):
        return None
    m = re.search(r"reset after (?:(\d+)h)?\s*(?:(\d+)m)?\s*(?:(\d+)s)?", text)
    if m and any(m.groups()):
        h, mi, se = (int(x or 0) for x in m.groups())
        return h * 3600 + mi * 60 + se + 5
    return QUOTA_REST_S


async def read_stream(stream) -> str:
    """The text of a streamed answer. A run of RUNAWAY_WS whitespace chars closes the stream (the server stops
    decoding) and raises Runaway: a loop would otherwise take max_tokens of server time for an answer that fails."""
    text, run = [], 0
    try:
        async for chunk in stream:
            piece = chunk.choices[0].delta.content if chunk.choices else None
            if not piece:
                continue
            text.append(piece)
            run = run + len(piece) if not piece.strip() else len(piece) - len(piece.rstrip())
            if run >= RUNAWAY_WS:
                raise Runaway(f"{RUNAWAY_WS} whitespace chars in a row after {sum(map(len, text))} chars")
    finally:
        await stream.close()
    return "".join(text)


def pick(models: str) -> str:
    """First model of a comma-separated pool that is not resting."""
    now_ = time.monotonic()
    for m in (x.strip() for x in models.split(",") if x.strip()):
        if _REST.get(m, 0) <= now_:
            return m
    raise OutOfQuota(models)


class SchemaError(ValueError):
    """The answer is JSON but not of the task's schema; retried like broken JSON."""


def validate(value, schema: dict, path: str = "$") -> None:
    """The subset of JSON schema the tasks use: type, enum, properties, required, items."""
    t = schema.get("type")
    kinds = {"object": dict, "array": list, "string": str, "boolean": bool, "integer": int, "number": (int, float)}
    if t in kinds and (not isinstance(value, kinds[t]) or (t in ("integer", "number") and isinstance(value, bool))):
        raise SchemaError(f"{path}: expected {t}")
    if "enum" in schema and value not in schema["enum"]:
        raise SchemaError(f"{path}: {value!r} not in {schema['enum']}")
    if t == "object":
        for k in schema.get("required", []):
            if k not in value:
                raise SchemaError(f"{path}: missing {k}")
        for k, sub in schema.get("properties", {}).items():
            if k in value and value[k] is not None:
                validate(value[k], sub, f"{path}.{k}")
    if t == "array":
        for i, x in enumerate(value):
            validate(x, schema.get("items", {}), f"{path}[{i}]")


def parse_answer(text: str) -> dict:
    """The JSON object of an answer: the whole text, else the last outermost object in it (a model that thinks or
    wraps the JSON in prose or a code fence). Outermost: an object nested in an earlier one is not a candidate, so a
    fenced {"items": [{...}, {...}]} is not cut down to its last item."""
    try:
        return json.loads(text)
    except json.JSONDecodeError:
        pass
    dec, found, at = json.JSONDecoder(), None, text.find("{")
    while at >= 0:
        try:
            obj, end = dec.raw_decode(text, at)
        except json.JSONDecodeError:
            at = text.find("{", at + 1)
            continue
        if isinstance(obj, dict):
            found = obj
        at = text.find("{", end)
    if found is None:
        raise json.JSONDecodeError("no JSON object in the answer", text[:200], 0)
    return found


@dataclass(frozen=True)
class Task:
    name: str
    role: Role
    prompt: str  # str.format template; fields are filled by render()
    schema: dict  # strict JSON schema of the answer
    max_tokens: int
    temperature: float = 0.0
    parallel: int | None = None  # concurrent calls; None = what the role's endpoint takes (Role.parallel)
    extra_body: dict | None = None  # sent with guided calls, e.g. to switch a model's thinking off

    def __post_init__(self):
        if self.parallel is None:
            object.__setattr__(self, "parallel", self.role.parallel())

    @property
    def prompt_hash(self) -> str:
        return hashlib.sha256(self.prompt.encode()).hexdigest()[:12]

    def render(self, **fields) -> str:
        return self.prompt.format(**fields)

    async def ask(self, client, model: str, images: list[bytes] = (), **fields) -> dict:
        """images: JPEG bytes sent after the prompt, in order (the model reads images, docs/LLM_PROVIDER.md)."""
        content = self.render(**fields)
        if not self.role.guided:
            content += ("\n\nAnswer with exactly one JSON object and nothing else. It must match this JSON schema:\n"
                        + json.dumps(self.schema, ensure_ascii=False))
        if images:
            content = [{"type": "text", "text": content}] + [
                {"type": "image_url", "image_url": {"url": "data:image/jpeg;base64," + base64.b64encode(b).decode()}}
                for b in images]
        attempt = runaways = 0
        while attempt < ATTEMPTS:
            attempt += 1
            current = pick(model)  # model may be a pool "a,b,c": a model out of quota rests, the next one answers
            try:
                if self.role.guided:
                    r = await client.chat.completions.create(
                        model=current, messages=[{"role": "user", "content": content}],
                        temperature=self.temperature, max_tokens=self.max_tokens, stream=True,
                        response_format={"type": "json_schema", "json_schema": {
                            "name": self.name, "schema": self.schema, "strict": True}},
                        **({"extra_body": self.extra_body} if self.extra_body else {}))
                    if isinstance(r, str):  # a busy or down server can answer with a plain body, not a completion
                        raise BadBody(r[:200])
                    text = await read_stream(r) if hasattr(r, "__aiter__") else r.choices[0].message.content or ""
                else:  # proxies (9router) stream some upstreams whatever is asked: always read a stream
                    text = ""
                    s = await client.chat.completions.create(
                        model=current, messages=[{"role": "user", "content": content}],
                        temperature=self.temperature, max_tokens=self.max_tokens, stream=True)
                    async for chunk in s:
                        if chunk.choices and chunk.choices[0].delta.content:
                            text += chunk.choices[0].delta.content
                answer = parse_answer(text)
                validate(answer, self.schema)
                if "," in model:
                    answer["_model"] = current  # which model of the pool answered
                return answer
            except BadBody:
                if attempt == ATTEMPTS:
                    raise
                await asyncio.sleep(RETRY_S * 2 ** (attempt - 1))
            except Runaway:
                runaways += 1
                if runaways >= RUNAWAYS:
                    raise
            except (json.JSONDecodeError, SchemaError):
                # guided decoding now and then loops on whitespace until max_tokens cuts the JSON; a new call is fine
                if attempt == ATTEMPTS:
                    raise
            except (openai.RateLimitError, openai.APIConnectionError, openai.APITimeoutError,
                    openai.InternalServerError, openai.BadRequestError) as e:  # a passing 500 from the server
                if isinstance(e, openai.BadRequestError) and _quota_rest(e) is None:
                    raise  # a real bad request: retrying cannot fix it
                rest = _quota_rest(e)
                if rest is not None:  # this model's account is spent: rest it, the pool's next model goes on
                    _REST[current] = time.monotonic() + rest
                    if "," in model:
                        attempt -= 1  # not this call's fault; pick() raises OutOfQuota when all rest
                        continue
                # the key's 40 concurrent calls are shared with other runs; wait for a free slot
                if attempt == ATTEMPTS:
                    raise
                await asyncio.sleep(RETRY_S * 2 ** (attempt - 1))
        raise OutOfQuota(model)  # the last attempts all hit spent accounts

    async def stream(self, client, model: str, messages: list[dict] | None = None, **fields):
        """Text deltas of one streamed call. No retry: a live turn falls back instead of waiting."""
        messages = messages or [{"role": "user", "content": self.render(**fields)}]
        s = await client.chat.completions.create(
            model=model, messages=messages,
            temperature=self.temperature, max_tokens=self.max_tokens, stream=True,
            response_format={"type": "json_schema", "json_schema": {"name": self.name, "schema": self.schema,
                                                                    "strict": True}})
        async for chunk in s:
            if chunk.choices and chunk.choices[0].delta.content:
                yield chunk.choices[0].delta.content


VIDEO_FILTER = Task(
    name="video_filter",
    role=EXTRACTOR,
    max_tokens=300,
    schema={
        "type": "object",
        "properties": {
            "relevance": {"type": "string", "enum": ["yes", "no", "unsure"]},
            "reason": {"type": "string"},
        },
        "required": ["relevance", "reason"],
        "additionalProperties": False,
    },
    # Caption and hashtags only: the search query says how a video was found, not what it is about, and made the
    # model call vague captions relevant. Dropping is final, so "no" needs clear evidence.
    prompt="""You screen TikTok videos found by searching {city}, Vietnam, for a travel product. Judge from the caption
and hashtags below. Dropping a useful video loses data for good, keeping a useless one only costs a little, so:
- yes: the text is about something a visitor could see, eat, drink, stay at, do or book: a place, dish, cafe,
  restaurant, stay, sight, activity, event, trip vlog, itinerary, tip, price, tour, rental, photo-shoot service,
  or a venue opening. The city does not have to be named (the search already scoped it).
- no: ONLY when the text clearly shows another topic: personal life or feelings, jobs, relationship content with no
  place or activity, outfits, product ads not tied to a place, another city or country, news or accidents, memes,
  entertainment clips.
- unsure: anything else, e.g. only hashtags, a quote, just the city name, or weather with nothing else.
Examples: "Quán ốc ngon, giòn, sạch, chủ dễ thương" -> yes. "Săn mây đồi Đa Phú lúc 5h sáng" -> yes.
"Khai trương cơ sở 3 ở 33 Nguyễn Văn Cừ" -> yes. "Trở lại Đà Lạt sau 6 năm cùng gia đình #travel" -> yes.
"105 ngày thất nghiệp #dailyvlog" -> no. "Tai nạn trên đèo Prenn chiều 25/9" -> no. "#comga20k" -> unsure.
"Đà Lạt mưa cả ngày" -> unsure. Give a one-sentence reason.

Caption: {desc}
Hashtags: {hashtags}""",
)

PLACE_FILTER = Task(
    name="place_filter",
    role=EXTRACTOR,
    max_tokens=300,
    schema=VIDEO_FILTER.schema,
    # Name and Maps category only: the search query ("thác", "hồ", …) says how a place was found, not what it is.
    # Strict: the list is what travellers are offered, so a place that is not itself worth going to is dropped.
    prompt="""You screen places found on Google Maps around {city}, Vietnam, for a travel product that suggests
places a traveller goes to. Judge from the name and Maps category below. Keep only places a traveller would go to
for the place itself. Read the name first: owners pick Maps categories loosely, so when the name says what the place
is (Homestay, Hotel, Khách sạn, Nhà nghỉ, Villa, Công ty, Văn phòng, Tour, Travel, Cửa hàng điện thoại, Ban quản lý,
Trường, Bệnh viện…) the name wins over the category; a name that is only a brand or a person's name leaves the
category to decide.
- yes: a sight, viewpoint, waterfall, lake, hill, pass, peak, pine forest, park, square, garden or flower garden,
  farm / strawberry garden / tea hill open to visitors, eco or amusement area, campsite, temple, pagoda, church,
  monastery, museum, historic site, railway station as a sight, cable car, craft village, market or night market,
  mall, local specialty shop, cafe, tea house, restaurant, eatery, street food, bakery, bar, spa / massage,
  golf course, activity venue (canyoning, zipline, horse riding…), motorbike rental.
- no: any lodging, even with a cafe, restaurant or campsite: hotel, homestay, hostel, resort, villa, guesthouse,
  motel, inn (nhà nghỉ, nhà khách, nhà trọ), serviced apartment, rooms to rent; a name containing
  homestay / hotel / khách sạn / resort / villa / nhà nghỉ / hostel is lodging. A campsite / camping / picnic area
  (khu cắm trại) is a place to go, not lodging. Also no: tour operator, travel agency,
  ticket or booking office, transport company; ordinary shops a traveller does not come for (jewelry, clothing,
  shoes, phones, electronics, cosmetics, optician, pharmacy, convenience store, grocery, supermarket, household or
  building supplies, pet shop); offices, companies, schools, hospitals, clinics, banks, ATMs, government or police
  offices, repair or car shops, gas stations, residential areas, private houses, apartment blocks, construction,
  bus stops, parking, utilities, industrial sites, management boards.
- unsure: only when the name and category give no hint of what it is.
Examples: "Thác Datanla (Điểm thu hút khách du lịch)" -> yes. "Đồi chè Cầu Đất (Nông trại)" -> yes.
"Hồ Tuyền Lâm (Hồ)" -> yes. "Lavender Đà Lạt (Nhà hàng)" -> yes. "Reo Campsite (Khu cắm trại)" -> yes. "Peaceful Stream Homestay & Coffee (Khu cắm trại)"
-> no. "Khu du lịch Thông Reo - Smiling Pine (Khách sạn)" -> no. "Highland Sport Travel - Adventure Tours (Nhà điều
hành du lịch)" -> no. "PNJ GO! Đà Lạt (Cửa hàng trang sức)" -> no. "Công ty TNHH Xây dựng Thác Mơ (Công ty xây
dựng)" -> no. "Đồi 1508 (none)" -> unsure. Give a one-sentence reason.

Name: {name}
Category: {category}""",
)

PLACE_QC = Task(
    name="place_qc",
    role=JUDGE,
    max_tokens=1500,
    schema={
        "type": "object",
        "properties": {
            "tourism_relevant": {"type": "boolean"},
            "relevance_reason": {"type": "string"},
            "in_city": {"type": "boolean"},
            "category_ok": {"type": "boolean"},
            "bad_reviews": {"type": "array", "items": {"type": "object", "properties": {
                "review_id": {"type": "string"},
                "problem": {"type": "string", "enum": ["owner_reply", "spam", "garbled", "truncated", "not_a_review", "other"]}},
                "required": ["review_id", "problem"], "additionalProperties": False}},
            "field_issues": {"type": "array", "items": {"type": "string"}},
            "verdict": {"type": "string", "enum": ["ok", "warn", "bad"]},
        },
        "required": ["tourism_relevant", "relevance_reason", "in_city", "category_ok", "bad_reviews", "field_issues", "verdict"],
        "additionalProperties": False,
    },
    prompt="""You check one place scraped from Google Maps for a travel product about {city}, Vietnam.
Decide from the data only:
- tourism_relevant: would a traveller visit or use it (sight, food, drink, lodging, shopping, activity, tour, rental)?
  Pharmacies, offices, schools, repair shops, private houses, etc. are not.
- in_city: the address is in {city} or its surrounding tourist area.
- category_ok: the category fits the name and description.
- bad_reviews: reviews whose text is an owner reply, spam or advertising, garbled, cut mid-sentence, or not about the place.
- field_issues: short notes on fields that look wrong or inconsistent (e.g. hours, price, phone).
- verdict: ok = usable; warn = usable with the issues noted; bad = wrong place or unusable data.

Place:
{place}

Reviews (newest first, sample):
{reviews}""",
)

PLACE_VIDEO_FILTER = Task(
    name="place_video_filter",
    role=EXTRACTOR,
    max_tokens=300,
    schema=VIDEO_FILTER.schema,
    # Caption and hashtags only, as in VIDEO_FILTER. The video becomes evidence for this one place, so a video about
    # a look-alike place, another branch or the city in general would put wrong facts on it: only "yes" is kept.
    prompt="""A TikTok search for one Google Maps place in {city}, Vietnam returned the video below. Decide from its
caption and hashtags whether the video is about THIS place, so it can be used as evidence for it.
- yes: the text names this place (also without accents, abbreviated, as a hashtag, or in English / Vietnamese
  variants) or clearly describes being at it; a video about several places counts when this is one of them.
- no: the text is about another place: a similar name, another branch of a chain in another city or clearly another
  address, a different kind of business than the category, or a place elsewhere; or it is about another topic, or
  only about the city in general.
- unsure: the text is too thin to tell (only generic hashtags, a quote, a song), or the place is a chain with several
  branches in {city} and the text does not show which one.
Examples for "Thác Datanla (Điểm thu hút khách du lịch)": "Máng trượt Datanla siêu phê" -> yes.
"#thacdatanla #dalat" -> yes. "Thác Pongour mùa nước lớn" -> no. "Đà Lạt 3 ngày 2 đêm" -> no. "chill thôi #xuhuong" ->
unsure. Give a one-sentence reason.

Place: {name}
Category: {category}
Address: {address}

Caption: {desc}
Hashtags: {hashtags}""",
)

ASR_CHECK = Task(
    name="asr_check",
    role=EXTRACTOR,
    max_tokens=4000,
    schema={
        "type": "object",
        "properties": {
            "segments": {"type": "array", "items": {"type": "object", "properties": {
                "i": {"type": "integer"},
                "status": {"type": "string", "enum": ["ok", "fixed", "garbled", "lyrics"]},
                "text": {"type": "string"}},
                "required": ["i", "status", "text"], "additionalProperties": False}},
            "quality": {"type": "string", "enum": ["good", "partial", "unusable"]},
            "screen_text": {"type": "array", "items": {"type": "string"}},
        },
        "required": ["screen_text", "segments", "quality"],
        "additionalProperties": False,
    },
    # The transcript becomes evidence, so a wrong "fix" is worse than a dropped segment: fix only what the sound and
    # the context make certain, never add meaning. Code (asr_check.guard) also undoes edits that do not sound like
    # the ASR words; the raw ASR text is kept next to the checked text. screen_text first: names come from it.
    prompt="""Below is a Vietnamese speech-recognition transcript of a TikTok video about {city}, Vietnam, split into
numbered segments, with {frames} frames of the video attached (evenly spaced). ASR mishears words, above all names
and English loanwords, and turns background songs or noise into nonsense.
First, screen_text: every name or word you can read on screen in the frames (signs, menus, text overlays), exactly
as written there. Then check each segment and return one entry per segment, same i, in order:
- ok: the text is sensible Vietnamese (or English) speech; return it unchanged.
- fixed: most of the segment is already correct words and only a few are misheard. Fix a word only when the intended
  word sounds like what ASR wrote (e.g. "đa tan la" -> "Datanla", "mátage" -> "massage", "sân bay" -> "săn mây" when
  the video is about clouds). A name may only be fixed to a name written in the caption, hashtags or screen_text, and
  only when it sounds alike: never put a place name in just because the video is about that place. Never rewrite a
  segment, and never add words, facts, prices or names: when most words are wrong, it is garbled.
- When a segment also has "ASR2" (a second model's hearing of the same audio), build the text from the words of
  ASR and ASR2 only, taking whichever makes sense; mark it fixed (or ok if ASR was already right).
- garbled: the text makes no sense and cannot be fixed with certainty; return "".
- lyrics: the words are a song's lyrics (background music, in any language), not someone speaking; return "".
quality: good = most segments ok / fixed; partial = some usable speech; unusable = nothing usable.

Caption: {desc}
Hashtags: {hashtags}
Places the video was matched to (a hint for what it is about, not words to insert): {places}

Segments:
{segments}""",
)

PLACE_VIDEO_VERIFY = Task(
    name="place_video_verify",
    role=EXTRACTOR,
    max_tokens=800,
    schema={
        "type": "object",
        "properties": {
            "verdict": {"type": "string", "enum": ["yes", "no", "unsure"]},
            "evidence": {"type": "array", "items": {"type": "object", "properties": {
                "source": {"type": "string", "enum": ["caption", "hashtags", "transcript", "frame"]},
                "quote": {"type": "string"}},
                "required": ["source", "quote"], "additionalProperties": False}},
            "reason": {"type": "string"},
        },
        "required": ["verdict", "evidence", "reason"],
        "additionalProperties": False,
    },
    # Last gate before a video counts as evidence for a place: it must show or talk about THIS place. Caption-only
    # matching (PLACE_VIDEO_FILTER) already passed; here the speech and the frames must agree with it.
    prompt="""A TikTok video was matched to one Google Maps place in {city}, Vietnam. Decide from the video's caption,
hashtags, speech transcript and the {frames} frames attached (evenly spaced, in order) whether the video really shows
or talks about THIS place.
- yes: the place is named in the caption, hashtags, speech or on screen (sign, menu, text overlay), or the frames
  clearly show it and nothing points elsewhere. A video about several places counts when this is one of them.
- no: the video is about another place (similar name, another branch, another city), or its content does not match
  this place (e.g. a waterfall video for a cafe), or it is about something else.
- unsure: nothing in the text, speech or frames settles it, or the video names a place that may contain or belong
  to this one (a park, complex or area with several parts) and the data does not say how they relate.
Read on-screen text exactly as it appears in the frame; do not copy spellings from the transcript, which is machine
speech recognition and may mishear names.
The same video was also matched to the other places listed below. Places with similar names are often different
businesses: when the evidence fits one of them at least as well as this place, answer no or unsure, never yes for
both.
evidence: up to 4 items that decide it. For caption / hashtags / transcript, quote the exact words; for a frame,
write the text you read on screen or what it shows, prefixed by the frame number ("frame 2: sign 'Thác Datanla'").
Give a one-sentence reason.

Place: {name}
Category: {category}
Address: {address}
Other places matched to this video: {others}

Caption: {desc}
Hashtags: {hashtags}
Transcript: {transcript}""",
)

PLACE_POI_MATCH = Task(
    name="place_poi_match",
    role=EXTRACTOR,
    max_tokens=300,
    schema={
        "type": "object",
        "properties": {
            "relation": {"type": "string", "enum": ["same_place", "part_of", "branch", "different"]},
            "reason": {"type": "string"},
        },
        "required": ["relation", "reason"],
        "additionalProperties": False,
    },
    # The place page of the POI lists its videos for this Maps place without any search, so a wrong POI would show
    # users another place's videos: only same_place maps (corpus.crawl.tiktok.place_poi).
    # The video count is left out of the prompt: "videos about this place were tagged with it" pushed the model to
    # same_place for a sight inside a larger one (a turbine on a tea hill) and for villas at other addresses.
    prompt="""Is the TikTok place below the same real place as the Google Maps place, both in {city}, Vietnam?
Users will be shown the TikTok place's videos as videos of the Google Maps place, so answer same_place only when the
two are clearly one place.
- same_place: one business or sight. Names may differ in language, accents, word order or extra words ("Thác Hang
  Cọp" = "Tiger Cave"; "Tiệm bánh Thanh Châu" = "Patisserie de Chau"); addresses may be written differently or one may
  be vague (a plus code, only the city), but they must not name different streets, house numbers, wards or communes.
- part_of: one is inside or part of the other: a sight or spot within a larger area (a turbine on a tea hill, a gate
  of a park), a cafe inside a park or resort, a hotel's spa, or a street or area the place is on.
- branch: another outlet of the same brand, or a different business with a similar name.
- different: unrelated, or the TikTok place is only a district, street or area.
Reason: one sentence.

{pair}""",
)

# quote last: with it before the context fields, guided decoding sometimes loops on whitespace after the quote
# (the model wants to close the object) until max_tokens cuts the JSON.
_REVIEW_OBS_KEYS = ("feature", "value", "time_of_day", "day_type", "weather", "quote")
_REVIEW_OBS = {
    "type": "object",
    "properties": {k: {"type": "string"} for k in _REVIEW_OBS_KEYS},
    "required": list(_REVIEW_OBS_KEYS),
    "additionalProperties": False,
}

REVIEW_OBSERVE = Task(
    name="review_observe",
    role=EXTRACTOR,
    max_tokens=6000,
    schema={
        "type": "object",
        "properties": {"reviews": {"type": "array", "items": {
            "type": "object",
            "properties": {
                "ref": {"type": "string"},
                "observations": {"type": "array", "items": _REVIEW_OBS},
                "proposed": {"type": "array", "items": {
                    "type": "object", "properties": {"label": {"type": "string"}, "quote": {"type": "string"}},
                    "required": ["label", "quote"], "additionalProperties": False}},
            },
            "required": ["ref", "observations", "proposed"],
            "additionalProperties": False}}},
        "required": ["reviews"],
        "additionalProperties": False,
    },
    # Feature and value are plain strings: the whole ontology as enums is too big for a strict schema; the gate
    # (corpus.observe.gmaps.gate) drops anything outside config/ontology.yaml and any quote not in the review.
    prompt="""You extract evidence about one place in {city}, Vietnam from its Google Maps reviews, for a travel
product that matches places to what a traveller wants. Use only what each review states, never your own knowledge.

Place: {name} ({category})

Features (id = allowed values: meaning) and context values:
{ontology}

For each review ref return the observations it states clearly:
- feature and value: from the list above, spelled exactly.
- quote: the shortest exact words of the review that state it; copy them, do not translate, shorten words or fix
  spelling.
- One review often gives several observations, one sentence can give several. The same feature can appear twice
  with different context ("sáng vắng, chiều đông" -> crowd low with time_of_day morning, crowd high with afternoon).
- time_of_day, day_type, weather: only when the review says it for that statement; otherwise "unknown".
- Not mentioned means no observation. Never infer a value from silence, the category or the star rating.
- Going with someone is not suitability: "đi cùng gia đình" is NOT kids suitable; "hợp cho trẻ em", "bé nhà mình
  chơi rất thích" is. The same for elderly, couples, groups, wheelchair.
- A denied or missing quality is never "present": "khó chụp hình", "view chẳng có gì" give no photo_spot /
  scenic_view; "có mái che, không sợ mưa" is weather_exposed sheltered; "không chặt chém" is tourist_trap absent;
  "đường vào toàn đường nhựa" is rough_road_access absent. Use the opposite value only when the feature has one.
- The reviewer's own story is not a fact about the place: "mình đặt bàn trước", "đặt bàn được xác nhận có bàn" are
  NOT booking_needed yes; "đường đi hơi xa", "đường vào quán hơi xa" (riding there) are NOT long_walk, which needs
  walking on foot; "quán nằm trên dốc" is NOT steep_or_stairs unless visitors must climb; "xe mới", "mới mở" are NOT
  condition_change; staff holding an umbrella to the car or a rented bike "không sợ mưa gió" are NOT weather_exposed
  sheltered, which needs the place's own roof or indoor space; a spa session "massage 90 phút" is NOT visit_duration.
- Words about another place are not about this one. A comparison with, or a description of, another branch, a hotel,
  a shop, a café, a waterfall, or the area, street and road around it ("quán X bên cạnh", "chi nhánh Hòa Bình", "khu
  này", "ngoài kia", "trên đường tới", "mấy quán nổi tiếng") gives no observation for this place. The Judge's commonest
  reason for rejecting a claim is exactly this, so when the words could belong either to this place or to something
  near it, leave them out.
- Praise without a concrete point ("tuyệt vời", "10 điểm", "sẽ quay lại") gives no observation.
- Something useful for choosing the place that is not in the list: add it to proposed with a short English label
  and its quote.
- Questions, ads and owner replies give nothing.
Return every ref, with empty lists when it states nothing.

Examples:
"View đồi thông đẹp, cà phê hơi dở, cuối tuần đông nghẹt" -> scenic_view present "View đồi thông đẹp";
drink_quality poor "cà phê hơi dở"; crowd high "cuối tuần đông nghẹt" with day_type weekend.
"Đường lên dốc đá lởm chởm, mém té mấy lần" -> rough_road_access present "dốc đá lởm chởm"; steep_or_stairs present
"Đường lên dốc".
"Giá nước ngáo giá, 1 ly 180k" -> value_for_money poor "ngáo giá"; tourist_trap present "ngáo giá".
"Đi cùng gia đình, rất vui" -> nothing.
"Đông lắm, tới là hết bàn, nên đặt trước. Đậu xe ngay cửa" -> crowd high "Đông lắm"; booking_needed yes "nên đặt
trước"; long_walk absent "Đậu xe ngay cửa".
"Đi 1 vòng tầm 40 phút là hết, đường bằng nên ông bà đi được" -> visit_duration under_1h "Đi 1 vòng tầm 40 phút";
steep_or_stairs absent "đường bằng"; elderly suitable "ông bà đi được".
"Gửi xe xong đi bộ gần 2km mới tới thác, vé 50k" -> long_walk present "đi bộ gần 2km"; entry_fee paid "vé 50k".
"Đi thẳng xe lên tận đỉnh, nhà vệ sinh hơi bẩn" -> steep_or_stairs absent "Đi thẳng xe lên tận đỉnh"; toilet dirty
"nhà vệ sinh hơi bẩn".
"Giá đúng như menu, không chặt chém khách du lịch, có chuyển khoản" -> tourist_trap absent "không chặt chém khách du
lịch"; cash_only absent "có chuyển khoản".
{note}
Reviews:
{reviews}""",
)

REVIEW_VERIFY = Task(
    name="review_verify",
    role=EXTRACTOR,
    max_tokens=300,
    schema={
        "type": "object",
        "properties": {"verdict": {"type": "string", "enum": ["supports", "contradicts", "insufficient"]},
                       "reason": {"type": "string"}},
        "required": ["verdict", "reason"],
        "additionalProperties": False,
    },
    # Second read of a high-impact observation (ontology `check: span`): the extractor reads many reviews at once
    # and misses negation, sarcasm, location remarks and exceptions; this call sees one review and one claim.
    prompt="""You check one claim about a place against one Google Maps review of it. Decide from the review only.

Place: {name} ({category})
Claim, with the words it was taken from: {claim}

The claim can itself be negative ("người đi xe lăn không vào được nơi này"): a review saying that SUPPORTS it.
- supports: the review clearly says the claim is true of this place.
- contradicts: the review says the opposite of the claim, e.g. it denies what the claim affirms ("mấy chị hông chặt
  chém" against "nơi này chặt chém"), or says it with sarcasm ("dành cho người lớn tuổi chứ decor sến" is not
  "hợp với người lớn tuổi").
- insufficient: anything else, e.g. a remark about the location ("quán nằm ngay dốc" does not mean visitors must
  climb), an exception for some people ("miễn phí bé dưới 80cm" does not mean free entry), the reviewer's own route
  ("đi bộ từ khách sạn qua"), riding a long way ("đường đi hơi xa", "đường vào quán hơi xa" are not walking far:
  walking far needs words about going on foot, a walking distance or time), what the reviewer did ("mình đặt bàn
  trước", "đặt bàn được xác nhận" do not mean booking is needed), heat or cold ("trên tầng 2 nóng" is not weather),
  a service or a vehicle instead of the place ("nhân viên che dù ra tận xe", a rented bike "đi không sợ mưa gió" do
  not mean the place has a roof; "xe mới" does not mean the place changed), a seat they were given, or a guess.
Give a one-sentence reason.

Review: {passage}""",
)

_VIDEO_OBS_KEYS = ("feature", "value", "source", "ref", "time_of_day", "day_type", "weather", "quote")
_VIDEO_OBS = {
    "type": "object",
    "properties": {**{k: {"type": "string"} for k in _VIDEO_OBS_KEYS if k not in ("source", "ref")},
                   "source": {"type": "string", "enum": ["speech", "caption", "frame"]}, "ref": {"type": "integer"}},
    "required": list(_VIDEO_OBS_KEYS),
    "additionalProperties": False,
}

VIDEO_OBSERVE = Task(
    name="video_observe",
    role=EXTRACTOR,
    max_tokens=4000,
    schema={"type": "object", "properties": {"observations": {"type": "array", "items": _VIDEO_OBS}},
            "required": ["observations"], "additionalProperties": False},
    # One (video, place) pair that place_verify accepted. The same ontology and rules as REVIEW_OBSERVE; frames only
    # for what a picture can prove, and only when the video is about this one place (the code sends no frames
    # otherwise). The gate (corpus.observe.tiktok) checks every quote against the numbered segment or the caption.
    prompt="""You extract evidence about one place in {city}, Vietnam from a TikTok video about it, for a travel
product that matches places to what a traveller wants. Use only what the video says or shows, never your own
knowledge.

Place: {name} ({category})
Other places this video is also about (their facts are NOT about this place): {others}

Features (id = allowed values: meaning) and context values:
{ontology}

Return the observations the video states clearly about THIS place:
- feature and value: from the list above, spelled exactly.
- source and ref: "speech" with ref = the segment number [i] the words are in; "caption" with ref = 0 (caption or
  hashtags); "frame" with ref = the frame number 1-{frames} ({frame_note}).
- quote: for speech / caption the shortest exact words that state it, copied from that one segment or the caption,
  not translated or fixed; for a frame, a short plain description of what the frame shows ("long stone staircase
  up the hill").
- A frame may only give: {frame_features}. Only what the picture itself clearly shows at this place; never a value
  from a frame because the place "looks" calm, cheap or suitable. Stairs or a steep path visitors walk up is
  steep_or_stairs present, not nature; a pet or stray animal in the picture is not animals.
- The speech is machine speech recognition and may mishear words: skip a statement whose words do not make sense.
- time_of_day, day_type, weather: only when the video says or clearly shows it for that statement; else "unknown".
- Not mentioned means no observation. Never infer a value from silence, the category or the video's mood.
- Going with someone is not suitability; a denied quality is never "present"; what the creator did ("mình đặt bàn
  trước", "đi xe lên") is not a fact about the place; riding a long way is not long_walk; ads, songs and greetings
  give nothing.

Caption: {desc}
Hashtags: {hashtags}
Text read on screen: {screen_text}

Speech segments:
{segments}""",
)

VIDEO_VERIFY = Task(
    name="video_verify",
    role=EXTRACTOR,
    max_tokens=300,
    schema=REVIEW_VERIFY.schema,
    # Second read of a high-impact video observation (ontology `check: span`): one claim, the speech around the quote
    # or the one frame it came from.
    prompt="""You check one claim about a place against part of a TikTok video about it. Decide from the material
below only (and the attached frame, if any).

Place: {name} ({category})
Claim, with the words or the picture it was taken from: {claim}

- supports: the material clearly shows or says the claim is true of this place.
- contradicts: it shows or says the opposite.
- insufficient: anything else: another place, the creator's own route or vehicle ("đi xe lên" is not climbing),
  a remark about the location, words that make no sense (speech recognition errors), a picture that could be
  somewhere else or does not clearly show it, or a guess.
Give a one-sentence reason.

Material: {passage}""",
)


DECISION_OPS = ["select", "drop", "lock", "travel", "crowd", "price", "trip", "visited"]

DECISION_TURN = Task(
    name="decision_turn",
    role=AGENT,
    max_tokens=900,
    temperature=0.2,
    parallel=4,
    # `say` first: the server streams it before the updates arrive (src/decision/agent.py).
    schema={
        "type": "object",
        "properties": {
            "say": {"type": "string"},
            "updates": {"type": "array", "items": {
                "type": "object",
                "properties": {
                    "op": {"type": "string", "enum": DECISION_OPS},
                    "place": {"type": "string"},
                    "value": {"type": "string"},
                    "quote": {"type": "string"},
                },
                "required": ["op", "place", "value", "quote"],
                "additionalProperties": False,
            }},
        },
        "required": ["say", "updates"],
        "additionalProperties": False,
    },
    prompt="""You help a traveller choose the places for a trip to Đà Lạt, Vietnam. The places on screen are listed
under PLACES with an alias (P1, P2, ...). In this turn: understand the user's latest message, turn what it asks
into updates, and reply.

`say` (Vietnamese): 1-2 short sentences, warm but not chummy, "mình" for yourself and "bạn" for the user, no slang,
no emoji. Say what you changed or understood. Name a place only with a name from PLACES. Never state a number or a
fact that is not in PLACES or in the user's message. If OPEN QUESTION is not "none", end by pointing the user to it.

`updates`: one entry per request in the message.
- select | lock: the user wants place `place` in the trip (lock: must keep it). value "".
- drop: the user does not want `place`; value = the reason if stated: far | crowded | pricey | dislike | visited,
  else "". A long wait or queue counts as crowded.
- visited: the user has been to `place` already. value "".
- crowd: the user wants fewer crowded or busy places in general, no single place ("bỏ mấy chỗ đông đi", "ít người
  thôi", "tránh chỗ phải xếp hàng"). value "".
- travel: the user wants places closer in general, less riding ("gần hơn", "đừng đi xa quá"). value "".
- price: the user wants cheaper places in general ("rẻ hơn chút"). value "".
  For these three, `op` names the wish and `value` stays ""; never put the wish into `value`.
- trip: a wish about the trip or the kind of place, not one place on screen: quieter, vegetarian, no stairs, near
  the centre, a budget, who comes along, "not like <a place>", "like <a place>". value "". quote = the exact words
  of that wish. Trip Understanding reads it and the list is rebuilt; do not also turn it into select or drop,
  except a drop when the user also rejects a place on screen by name.
- place: an alias from PLACES, or "" when the update is about no single place.
- quote: the exact words from the user's message that support the update, copied, not paraphrased.
- When unsure, leave it out. Never invent a place.

FEATURES (id: values)
{features}

PLACES (alias | name | group | chosen | notes)
{places}

SESSION PROFILE: {profile}
FEASIBILITY: {feasibility}
OPEN QUESTION: {pending}

USER MESSAGE:
{text}""",
)


PLANNING_OPS = ["drop", "move_day", "reorder_edge", "pick_lodging", "lodging_near", "pace", "relax", "variant",
                "unmapped"]

PLANNING_TURN = Task(
    name="planning_turn",
    role=AGENT,
    max_tokens=700,
    temperature=0.2,
    parallel=4,
    # `say` first: the server streams it before the updates arrive (src/planning/agent.py).
    schema={
        "type": "object",
        "properties": {
            "say": {"type": "string"},
            "updates": {"type": "array", "items": {
                "type": "object",
                "properties": {
                    "op": {"type": "string", "enum": PLANNING_OPS},
                    "ref": {"type": "string"},
                    "value": {"type": "string"},
                    "quote": {"type": "string"},
                },
                "required": ["op", "ref", "value", "quote"],
                "additionalProperties": False,
            }},
        },
        "required": ["say", "updates"],
        "additionalProperties": False,
    },
    prompt="""You help a traveller edit a day-by-day itinerary for a trip to Đà Lạt, Vietnam. DAYS lists every place
already in the plan grouped by day (alias P1, P2, ...), with how far it is from today's lodging. VARIANTS lists the
2-3 plan options on screen (alias V1, V2, ...). LODGING lists the lodging candidates on screen (alias L1, L2, ...).
In this turn: understand the user's latest message, turn what it asks into updates, and reply.

`say` (Vietnamese): 1-2 short sentences, warm but not chummy, "mình" for yourself and "bạn" for the user, no slang,
no emoji. Say what you changed or understood, using only names and numbers from DAYS / VARIANTS / LODGING or the
user's own message. If the request names no clear place, day or candidate, or asks for something bigger than one
change (e.g. "đổi hết đi"), do not guess -- ask a short clarifying question instead and leave updates empty.

`updates`: one entry per request in the message.
- drop: the user does not want `ref` (a P# place) in the plan; value = the reason if stated: far | crowded | pricey
  | dislike | visited, else "". If they mean a whole day ("ngày 2 nhiều quá") without naming a place, pick the P#
  in DAYS for that day that is farthest from the lodging and not already locked -- unless two are close enough that
  you are not sure, in which case ask instead (empty updates).
- move_day: move `ref` (a P# place) to a different day; value = the day number as the user said it ("2" for "ngày 2").
- reorder_edge: put `ref` (a P# place) first or last within its own day; value = "first" or "last".
- pick_lodging: the user wants `ref` (an L# lodging candidate) as the stay; value = "". Only use this when the
  user clearly means one of the candidates actually listed in LODGING.
- lodging_near: the user wants the lodging near a place or area they name; ref = "", value = that place or area in
  their own words.
- pace: the user wants to go slower, more relaxed, or pack in more stops; value = slow | normal | packed.
- relax: the user is fine with `ref` (a P# place) despite a constraint they set earlier (e.g. stairs); value = the
  feature id from FEATURES. Only use this for a place clearly named.
- variant: the user wants a different plan option already on screen (`ref` = a V# alias); value = "". Only use this
  when the user clearly means one of the options actually listed in VARIANTS.
- unmapped: a request none of the above fits; ref = "", value = the user's words.
- quote: the exact words from the user's message that support the update, copied, not paraphrased.
- When unsure, leave it out. Never invent a place, a day, a candidate or a plan option.

FEATURES (id: values)
{features}

DAYS (day | alias | name | minutes from lodging)
{days}

VARIANTS (alias | objective | score summary)
{variants}

LODGING (alias | name | price)
{lodging}

USER MESSAGE:
{text}""",
)

_PHOTO_OBS_KEYS = ("feature", "value", "photo", "quote")
PHOTO_OBSERVE = Task(
    name="photo_observe",
    role=EXTRACTOR,
    max_tokens=2000,
    schema={"type": "object", "properties": {"observations": {"type": "array", "items": {
        "type": "object",
        "properties": {"feature": {"type": "string"}, "value": {"type": "string"}, "photo": {"type": "integer"},
                       "quote": {"type": "string"}},
        "required": list(_PHOTO_OBS_KEYS), "additionalProperties": False}}},
        "required": ["observations"], "additionalProperties": False},
    # Visitors' and the owner's Google Maps photos of one place (crawl gmaps photos). A photo proves what is visible,
    # never an absence, a quality, a price or who the place suits; the gate (corpus.observe.gmaps.photos) keeps only
    # PHOTO_VALUES. Each photo is numbered in the order attached.
    prompt="""You read {count} Google Maps photos of one place in {city}, Vietnam, attached in order and numbered 1-{count}
(photo i = the i-th image), for a travel product that matches places to what a traveller needs. Report only what a
photo itself clearly shows AT this place. Photos marked "owner" were posted by the business (marketing).

Place: {name} ({category})
Photos: {photo_list}

You may only report these features and values:
{allowed}

Rules:
- One observation per (feature, value, photo). quote = a short plain description of what that photo shows that
  proves it ("long concrete staircase up a hillside", "dirt track with mud puddles", "crowd packed on a viewing deck").
- steep_or_stairs present: a long flight of stairs or a steep slope visitors climb to reach or see the place. A few
  steps at a door or a porch, or stairs visitors need not use, are not.
- rough_road_access present: the access road or path itself is dirt, rocks or mud.
- crowd high: many people filling the space. Never "quiet" because a photo happens to be empty.
- setting: only from a photo that shows where visitors sit or walk (a room, a terrace, a garden); indoor = inside a
  building, outdoor = open air, both = that one photo shows both. Never from food, drinks, a menu, a person close-up,
  a treatment, a car park or the street. One value per photo.
- A pet or stray animal is not animals; a dish photo, a selfie close-up, a menu or a receipt gives nothing.
- outdoor_seating: the seating itself must be visible in the open air, tables and chairs with sky or garden around
  them. A roofed terrace or a covered hall is not outdoor; a photo of the facade is not indoor; food on a table says
  nothing about where that table stands.
- What you report must be the photo's own subject, not something guessed from a corner, a background or a reflection.
  The Judge rejects a claim whenever the picture only hints at it.
- Unsure, blurry, or could be anywhere -> nothing. Return an empty list when nothing is clearly shown.""",
)

PHOTO_VERIFY = Task(
    name="photo_verify",
    role=EXTRACTOR,
    max_tokens=300,
    schema=REVIEW_VERIFY.schema,
    prompt="""You check one claim about a place against one Google Maps photo of it (attached). Decide from the photo
only.

Place: {name} ({category})
Claim, with what the photo was said to show: {claim}

- supports: the photo clearly shows the claim is true of this place.
- contradicts: the photo clearly shows the opposite.
- insufficient: anything else: it could be somewhere else, it does not clearly show it, or it needs a guess.
Give a one-sentence reason.""",
)


# Gallery photos of one place for the web (web/scripts/pick_covers.py): which ones are the best to show. Scores only
# order the gallery; nothing here becomes evidence about the place.
PHOTO_RANK = Task(
    name="photo_rank",
    role=EXTRACTOR,
    max_tokens=1200,
    schema={"type": "object", "properties": {"photos": {"type": "array", "items": {
        "type": "object",
        "properties": {"photo": {"type": "integer"}, "beauty": {"type": "integer"}, "shows_place": {"type": "integer"}},
        "required": ["photo", "beauty", "shows_place"], "additionalProperties": False}}},
        "required": ["photos"], "additionalProperties": False},
    prompt="""You pick the photos a travel app shows first for one place in {city}, Vietnam. {count} photos are attached
in order, numbered 1-{count}. They come from Google Maps visitors and frames of TikTok clips.

Place: {name} ({category})

Score every photo, one entry per photo number:
- beauty 1-10: how good the picture itself is: composition, light, sharpness, colour. 1 = blurry, dark, tilted,
  cluttered, a screenshot or text overlay; 10 = a clean, well-lit picture worth a postcard.
- shows_place 1-10: how well it shows what this place is to someone who has never been there: the view, the space,
  the building, the garden, the signature dish of a restaurant. 1 = a menu, a receipt, a close-up of an object, a
  person filling the frame, or something that could be anywhere; 10 = you know at once what kind of place this is.
Judge each photo on its own; do not give every photo the same score.""",
)


REVIEW_QC = Task(
    name="review_qc",
    role=EXTRACTOR,
    max_tokens=1500,
    schema={
        "type": "object",
        "properties": {"bad": {"type": "array", "items": {"type": "object", "properties": {
            "ref": {"type": "string"},
            "problem": {"type": "string", "enum": ["owner_reply", "spam", "not_a_review"]},
            "reason": {"type": "string"}},
            "required": ["ref", "problem", "reason"], "additionalProperties": False}}},
        "required": ["bad"],
        "additionalProperties": False,
    },
    # Every review of a place, in batches (corpus.crawl.gmaps.qc). A flagged review gives no evidence at all, so only
    # clear cases are flagged; short, generic or one-sided praise is still a visitor's review.
    prompt="""You screen Google Maps reviews of one place in {city}, Vietnam, before they become evidence for a travel
product. List ONLY the reviews that are clearly one of these (most reviews are fine; leave them out):
- owner_reply: written by the business or its staff (thanks customers in the shop's name, answers a complaint,
  advertises its own menu or prices as "we").
- spam: advertising another business, promo codes, links or phone numbers asking for contact, text unrelated to any
  place, gibberish, or a review written in exchange for a reward ("đánh giá để được tặng", "đồ uống được tặng để đổi
  lấy đánh giá", "review nhận quà").
- not_a_review: a question, a reply to another person, about a different place, or the writer clearly never used or
  visited this place ("chưa tới nhưng ...").
A real visit told oddly (machine-translated, wrong currency, very short, off-topic remarks) is still a review: keep it
out of the list. Give a reason of a few words. Answer {{"bad": []}} when none.

Place: {name} ({category})
Reviews:
{reviews}""",
)

AUDIT_SCHEMA = {
    "type": "object",
    "properties": {"items": {"type": "array", "items": {"type": "object", "properties": {
        "ref": {"type": "string"},
        "verdict": {"type": "string", "enum": ["correct", "wrong", "unsure"]},
        "reason": {"type": "string"}},
        "required": ["ref", "verdict", "reason"], "additionalProperties": False}}},
    "required": ["items"],
    "additionalProperties": False,
}

# The Judge in place of a person (docs/P1_CORPUS.md §6): it reads what a small model claimed about one feature of one
# place next to the source, and says whether each claim holds for this place in the ontology's sense. Its verdicts are
# labels (corpus.review.labels, by = judge model): wrong claims leave the evidence, and they measure precision.
_AUDIT_PROMPT = """You audit a travel database about {city}, Vietnam, built from Google Maps reviews and photos and
TikTok videos. A small model read each source below and claimed that a place has a value of a feature. Decide for
every item, from its own source only, whether the claim is true FOR THAT PLACE in the sense the feature defines.

Places:
{places}

Features (definition; what each value claims):
{features}

Verdicts:
- correct: the source clearly says (or the picture clearly shows) that this place has this value, as defined.
- wrong: the words are negated, sarcastic, hypothetical, an exception ("free for kids under 1m"), about another place,
  the city, the road network or traffic in general, the writer's own action or choice instead of a property of the
  place ("mình đặt bàn trước", "mình đi bộ khám phá thành phố"), a different feature, too weak for the definition
  (a 20 m walk is not a long walk; a steep road you drive up is not stairs you climb), or the picture does not show it
  or does not show this place.
- unsure: the source is not enough to tell.
Accept clear paraphrases and direct implications, not only the definition's words: "hợp nhóm bạn, gia đình" or "đi
đoàn thoải mái" is suitable for groups; "nhiều bậc thang, không hợp người khó di chuyển" is unsuitable for wheelchairs;
a child happily doing the place's activity there is suitable for kids; a review that bought an entry or tour ticket
proves it is paid; a trip made to hunt clouds at the place supports cloud hunting even on a day without clouds.
Stairs: a flight of about five or more steps visitors must climb (to enter, to the seats, through the site) is
steep_or_stairs present, the same in words or in a picture; one or two steps are not.
Judge each item on its own source. Reason: at most 15 words.

Items:
{items}"""

# same verdicts, shorter answer: no reason for "correct" (output tokens are the dearest); the schema is not part of
# prompt_hash, the verdict rules are unchanged
AUDIT_SCHEMA_SHORT = {**AUDIT_SCHEMA, "properties": {"items": {"type": "array", "items": {"type": "object", "properties": {
    "ref": {"type": "string"},
    "verdict": {"type": "string", "enum": ["correct", "wrong", "unsure"]},
    "reason": {"type": "string", "description": "empty string when correct; else at most 8 words"}},
    "required": ["ref", "verdict", "reason"], "additionalProperties": False}}}}

OBS_AUDIT = Task(name="obs_audit", role=JUDGE, max_tokens=12000, schema=AUDIT_SCHEMA, prompt=_AUDIT_PROMPT, parallel=8)
# optional first reader (JUDGE_FIRST_MODEL): its "correct" stands, wrong / unsure go to OBS_AUDIT (judge.audit)
OBS_AUDIT_FIRST = Task(name="obs_audit", role=JUDGE_FIRST, max_tokens=12000, schema=AUDIT_SCHEMA, prompt=_AUDIT_PROMPT,
                       parallel=8)
# values that widen a choice (suitable for elderly / kids / wheelchair ...): a wrong "yes" can hurt someone
OBS_AUDIT_STRONG = Task(name="obs_audit", role=JUDGE_STRONG, max_tokens=12000, schema=AUDIT_SCHEMA,
                        prompt=_AUDIT_PROMPT, parallel=8)

# The audit on the Extractor's Gemma (judge.audit, JUDGE_ENGINE=gemma) while no Codex quota is left. Gemma made the
# claims and tends to confirm them, so its prompt is strict: each item carries the value's claim sentence, and the
# answer writes the strongest doubt before the verdict. Measured 2026-10-06 (logs/judge_exp/gemma_eval.py, 663
# sol-labelled claims stratified per feature): it lets 10% of wrong claims stand (the production prompt on Gemma: 48%)
# and drops 31% of correct ones; 8 items per call, ~8 s. Missing evidence can be crawled again; a wrong claim reaches
# the traveller, so precision comes first.
_AUDIT_GEMMA_TRAPS = """not enough: words that only hint or imply it ("không khí mát" is not nature); advice or preference ("nên
đặt trước để có chỗ đẹp" is not booking needed); a condition or exception ("phí 10k nếu không mua nước"); negated,
sarcastic or hypothetical words; something near or sold there instead of the place (a waterfall's slope is not stairs
visitors climb; a drink at 20k is not an entry ticket; fresh fruit is not a clean shop); the writer's own action or
choice ("mình đặt bàn trước"); weaker than the definition."""

_AUDIT_GEMMA_PROMPT = """You check claims in a travel database about {city}, Vietnam. A small model read each source (a Google Maps
review or a TikTok video) and claimed that a place has a value of a feature. Many claims are wrong: be strict. A claim
stands only when its own source says it plainly about this place.

Places:
{places}

Features (definition; what each value claims):
{features}

For every item first write the strongest reason the claim could be wrong (doubt, at most 12 words): is it about
another place, the area or the road beyond, only implied, advice, a condition, or weaker than the definition? Things
that are """ + _AUDIT_GEMMA_TRAPS + """
Then the verdict: correct only if the doubt clearly fails and the source states the claim about this place; wrong if
the doubt holds; unsure if the source cannot tell.

Items:
{items}"""

AUDIT_SCHEMA_DOUBT = {
    "type": "object",
    "properties": {"items": {"type": "array", "items": {"type": "object", "properties": {
        "ref": {"type": "string"},
        "doubt": {"type": "string"},
        "verdict": {"type": "string", "enum": ["correct", "wrong", "unsure"]}},
        "required": ["ref", "doubt", "verdict"], "additionalProperties": False}}},
    "required": ["items"],
    "additionalProperties": False,
}

OBS_AUDIT_GEMMA = Task(name="obs_audit", role=EXTRACTOR, max_tokens=8000, schema=AUDIT_SCHEMA_DOUBT,
                       # concurrency: the Extractor endpoint's (Role.parallel); Task.ask backs off on 429
                       prompt=_AUDIT_GEMMA_PROMPT,
                       extra_body={"chat_template_kwargs": {"enable_thinking": False}})

PLACE_STATUS = Task(
    name="place_status",
    role=JUDGE,
    max_tokens=1500,
    parallel=16,
    schema={
        "type": "object",
        "properties": {
            "status": {"type": "string", "enum": ["open", "closed", "changed", "unclear"]},
            "since": {"type": "string"},
            "reason": {"type": "string"},
        },
        "required": ["status", "since", "reason"],
        "additionalProperties": False,
    },
    prompt="""Is this place in {city}, Vietnam, still operating as described, as of {today}? Reviewers reported it
closed or changed. Weigh the dates: a later review describing a normal visit outweighs an older closure report;
a report about one part (a closed zone, a removed bridge, renovation) is not a closure of the place.
Judge the place as a visitor uses it: a sight, hill, lake or area people still visit is open even if a business on it
(a factory, a shop, a ticket booth) stopped.
- open: visitors can go there now and have the experience its reviews describe.
- closed: it stopped operating (for good or for an open-ended time) and nothing later shows a normal visit.
- changed: the address now hosts a different business or a different kind of place (e.g. restaurant became a cafe).
- unclear: the evidence does not settle it.
since: the month it closed or changed (YYYY-MM) when stated, else "". Reason: one sentence.

Place: {name} ({category}), {address}
Google Maps at crawl time: status "{maps_status}", hours: {hours}
Closure / change reports:
{reports}
Newest reviews (date, stars, text):
{reviews}""",
)

SAME_PLACE = Task(
    name="same_place",
    role=JUDGE,
    max_tokens=800,
    parallel=16,
    schema={
        "type": "object",
        "properties": {
            "relation": {"type": "string", "enum": ["same_place", "part_of", "branch", "different"]},
            "reason": {"type": "string"},
        },
        "required": ["relation", "reason"],
        "additionalProperties": False,
    },
    prompt="""Two Google Maps entries near each other in {city}, Vietnam. Do they describe the same real place?
- same_place: one place listed twice (same business or sight; names, address and reviews describe one visit).
- part_of: one is a part, gate, zone, stall or service inside the other (a cafe inside a park, a boat dock on a lake).
- branch: two outlets of one brand or two separate businesses with similar names.
- different: unrelated places.
Reason: one sentence.

A: {a}
B: {b}
Distance between pins: {meters} m""",
)


# a second, stronger opinion before a place leaves serving or two places become one (corpus.judge status / dedup)
PLACE_STATUS_STRONG = replace(PLACE_STATUS, role=JUDGE_STRONG, parallel=8)
SAME_PLACE_STRONG = replace(SAME_PLACE, role=JUDGE_STRONG, parallel=8)

_DAYS = ["mon", "tue", "wed", "thu", "fri", "sat", "sun"]
OFFICIAL_OBSERVE = Task(
    name="official_observe",
    role=EXTRACTOR,
    max_tokens=2500,
    schema={
        "type": "object",
        "properties": {"facts": {"type": "array", "items": {"type": "object", "properties": {
            "kind": {"type": "string", "enum": ["ticket", "free", "hours"]},
            "quote": {"type": "string"},
            "amount_vnd": {"type": "integer"},
            "audience": {"type": "string", "enum": ["adult", "child", "other", "none"]},
            "open": {"type": "string"},
            "close": {"type": "string"},
            "days": {"type": "array", "items": {"type": "string", "enum": _DAYS}}},
            "required": ["kind", "quote", "amount_vnd", "audience", "open", "close", "days"],
            "additionalProperties": False}}},
        "required": ["facts"],
        "additionalProperties": False,
    },
    # One chunk of a place's own website (corpus.observe.official); code checks every quote and number against the
    # page, so a fact the page does not state word for word is dropped.
    prompt="""You read part of the official website of a place in {city}, Vietnam, and list what it states about
visiting THIS place: entry ticket prices and opening hours. Only what the text says; never guess.

Place: {name} ({category}), {address}
{note}
Page: {url}

Facts to return (an empty list when the text states none for this place):
- kind "ticket": an entry ticket price. amount_vnd = the amount in VND as an integer ("50.000đ", "50k",
  "50 nghìn" -> 50000). audience: "adult" for the normal entry ticket of an adult (or an entry ticket that names no
  group), "child" for children, students or elderly prices, "other" for combos, games, rides, food, drinks, rentals,
  photos, parking, spa or other services, tours and anything that is not the entry ticket. A price in another
  currency is left out.
- kind "free": the text says entry to this place is free for every visitor. Free for some people only (small
  children under a height, the elderly, locals) is not "free": leave it out.
- kind "hours": opening hours (when the place opens and closes; a last admission time, the first / last tour or
  show time and a booking slot are not opening hours). open, close = "HH:MM" in 24 h ("7h30" -> "07:30", "5 giờ chiều" -> "17:00"); days =
  the days they apply to (all seven for "hằng ngày", "mỗi ngày", "daily" or when no day is named). Several time
  ranges -> one fact per range.
Fields that do not apply: amount_vnd 0, audience "none", open "", close "", days [].
quote = the exact words of the text that state the fact, copied character for character (no translation, no
rewording), at most 200 characters, containing the amount or the times.
A page about several places or branches: only facts the text gives for {name}; a branch in another city is not
this place.

Text:
{text}""",
)


# Benchmark users (python -m bench, docs/P2_TRIP_UNDERSTANDING.md §16): a model plays one traveller whose trip it knows in full.
USER_SIM_CODES = (
    "What the codes in the JSON mean: mobility motorbike = you ride your own motorbike, car = your own car; "
    "companions solo = alone, partner = your partner, friends, kids = young children, "
    "parents = your parents / older people; pace slow = few places a day, normal, packed = as many as possible; "
    "crowd_tolerance avoid = you avoid crowds, ok_if_worth = crowds are fine if the place is worth it, fine = you do "
    "not mind; novelty familiar = well-known places, new = places you have not seen, mix; budget_vnd = what one "
    "person spends a day on food and tickets; dates kind exact = a fixed date, month = only the month, undecided = no "
    "dates yet; signals = health or body facts about someone in the group (knee = bad knee, elderly, kids, wheelchair, "
    "pregnant, motion_sick = gets carsick, height = afraid of heights, vegetarian); hard feature != present = that thing "
    "must be avoided (steep_or_stairs = slopes or stairs, long_walk = long walks); loves / avoids = what you like / "
    "dislike in places (feature=value); anchors = places you must or want to visit.")
USER_SIM_BRIEF = Task(
    name="user_sim_brief",
    role=USER_SIM,
    max_tokens=700,
    temperature=0.7,
    parallel=4,
    schema={"type": "object", "properties": {"brief": {"type": "string"}}, "required": ["brief"],
            "additionalProperties": False},
    prompt="""You are a Vietnamese traveller planning a trip to Đà Lạt. Below is everything true about you and this
trip, in JSON. Write the first message you would type to a trip-planning assistant when you want it to plan the whole
trip for you: Vietnamese, casual, one long message of 4-10 sentences, the way people describe a trip to a friend.
Cover most of what matters to you, in your own words and in any order; never use the JSON field names or ids; never
mention anything listed under "indifferent"; never add facts that are not in the JSON.

""" + USER_SIM_CODES + """

Trip: {trip}""",
)

USER_SIM_REPLY = Task(
    name="user_sim_reply",
    role=USER_SIM,
    max_tokens=200,
    temperature=0.5,
    parallel=4,
    schema={"type": "object", "properties": {"reply": {"type": "string"}}, "required": ["reply"],
            "additionalProperties": False},
    prompt="""You are a Vietnamese traveller talking to a trip-planning assistant about a trip to Đà Lạt. Everything true
about you and this trip is in the JSON below. Answer the assistant's question in Vietnamese, in your own words, 1-2
short sentences, as a person would type. Answer only from the JSON; if the JSON has nothing on the question or lists
it under "indifferent", say you have no preference. Never use the JSON field names or ids.

""" + USER_SIM_CODES + """

Trip: {trip}
Assistant's question: {question}
Options shown on screen (you may ignore them): {options}""",
)


# Admin Insights (docs/ANALYTICS.md §Insights): weekly grouping of after-trip notes and free-text wishes. Offline job,
# shown to a person only; it never writes the corpus or a fact.
INSIGHT_CLUSTER = Task(
    name="insight_cluster",
    role=EXTRACTOR,
    max_tokens=1500,
    schema={"type": "object", "additionalProperties": False, "required": ["clusters"], "properties": {
        "clusters": {"type": "array", "maxItems": 8, "items": {
            "type": "object", "additionalProperties": False, "required": ["label", "members"], "properties": {
                "label": {"type": "string", "maxLength": 80},
                "members": {"type": "array", "items": {"type": "integer", "minimum": 1}}}}}}},
    prompt="""Below are short texts that travellers wrote in a Vietnamese trip-planning app for Đà Lạt ({source}).
Group them by what they ask for or complain about. Make at most 8 groups; a text that fits no group stays out.
Name each group in Vietnamese, at most 8 words, saying the need itself ("muốn quán yên tĩnh để làm việc"), never a
judgement of the user. Use only what the texts say; do not invent needs.

Texts (number. text):
{texts}""",
)
