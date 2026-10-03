"""Every model task in one place: role, prompt, output schema and call settings. Edit prompts and settings here.

A task's prompt_hash is stored with each result, so changing a prompt re-runs that task on the next build.
"""

import asyncio
import base64
import hashlib
import json
from dataclasses import dataclass

import openai

from .roles import AGENT, EXTRACTOR, JUDGE, Role

ATTEMPTS = 4  # per call: a broken JSON answer or a busy / unreachable server is tried again
RETRY_S = 2.0  # first wait after HTTP 429 or a connection error; doubles each time


class BadBody(Exception):
    """The server answered with text that is not a chat completion; retried like a busy server."""


@dataclass(frozen=True)
class Task:
    name: str
    role: Role
    prompt: str  # str.format template; fields are filled by render()
    schema: dict  # strict JSON schema of the answer
    max_tokens: int
    temperature: float = 0.0
    parallel: int = 36  # concurrent calls; the UIT key allows 40 (HTTP 429 above), ~1 s each -> ~35 calls/s

    @property
    def prompt_hash(self) -> str:
        return hashlib.sha256(self.prompt.encode()).hexdigest()[:12]

    def render(self, **fields) -> str:
        return self.prompt.format(**fields)

    async def ask(self, client, model: str, images: list[bytes] = (), **fields) -> dict:
        """images: JPEG bytes sent after the prompt, in order (the model reads images, docs/LLM_PROVIDER.md)."""
        content = self.render(**fields)
        if images:
            content = [{"type": "text", "text": content}] + [
                {"type": "image_url", "image_url": {"url": "data:image/jpeg;base64," + base64.b64encode(b).decode()}}
                for b in images]
        for attempt in range(1, ATTEMPTS + 1):
            try:
                r = await client.chat.completions.create(
                    model=model, messages=[{"role": "user", "content": content}],
                    temperature=self.temperature, max_tokens=self.max_tokens,
                    response_format={"type": "json_schema", "json_schema": {"name": self.name, "schema": self.schema,
                                                                            "strict": True}})
                if isinstance(r, str):  # a busy or down server can answer with a plain body, not a completion
                    raise BadBody(r[:200])
                return json.loads(r.choices[0].message.content)
            except BadBody:
                if attempt == ATTEMPTS:
                    raise
                await asyncio.sleep(RETRY_S * 2 ** (attempt - 1))
            except json.JSONDecodeError:
                # guided decoding now and then loops on whitespace until max_tokens cuts the JSON; a new call is fine
                if attempt == ATTEMPTS:
                    raise
            except (openai.RateLimitError, openai.APIConnectionError, openai.APITimeoutError,
                    openai.InternalServerError):  # a passing 500 from the server
                # the key's 40 concurrent calls are shared with other runs; wait for a free slot
                if attempt == ATTEMPTS:
                    raise
                await asyncio.sleep(RETRY_S * 2 ** (attempt - 1))

    async def stream(self, client, model: str, **fields):
        """Text deltas of one streamed call. No retry: a live turn falls back instead of waiting."""
        s = await client.chat.completions.create(
            model=model, messages=[{"role": "user", "content": self.render(**fields)}],
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
    parallel=8,  # long prompts
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
    parallel=8,  # four images per call
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
    parallel=38,  # ~50 s per batch of 15; the key allows 40 concurrent, Task.ask backs off on 429; caps REVIEW_VERIFY
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
    parallel=8,  # four images per call
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
    parallel=8,
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


TRIP_FIELDS = ["start_date", "month", "days", "companions", "people", "base", "entry_point", "exit_point", "mobility",
               "arrive_at", "leave_at", "day_end", "purpose", "anchor", "signal", "soft", "hard", "pace", "max_leg_min", "crowd_tolerance",
               "novelty", "budget_vnd", "unmapped"]

TRIP_TURN = Task(
    name="trip_turn",
    role=AGENT,
    max_tokens=900,
    temperature=0.2,
    parallel=4,
    # `say` first: the server streams it to the user before the structured part arrives (src/trip/agent.py).
    schema={
        "type": "object",
        "properties": {
            "say": {"type": "string"},
            "updates": {"type": "array", "items": {
                "type": "object",
                "properties": {
                    "field": {"type": "string", "enum": TRIP_FIELDS},
                    "op": {"type": "string", "enum": ["set", "add", "remove"]},
                    "value": {"type": "string"},
                    "quote": {"type": "string"},
                    "how": {"type": "string", "enum": ["said", "inferred"]},
                },
                "required": ["field", "op", "value", "quote", "how"],
                "additionalProperties": False,
            }},
            "next": {
                "type": "object",
                "properties": {
                    "kind": {"type": "string", "enum": ["ask", "stop"]},
                    "qid": {"type": "string"},
                    "custom_text": {"type": "string"},
                    "custom_chips": {"type": "array", "items": {"type": "string"}},
                    "reason": {"type": "string"},
                },
                "required": ["kind", "qid", "custom_text", "custom_chips", "reason"],
                "additionalProperties": False,
            },
        },
        "required": ["say", "updates", "next"],
        "additionalProperties": False,
    },
    prompt="""You help a traveller prepare a trip to Đà Lạt, Vietnam. In this turn: understand the user's latest
message, record what it says about the trip, and choose the next question. Never suggest places in this step.

`say` (Vietnamese): 1-2 short sentences, warm but not chummy, "mình" for yourself and "bạn" for the user, no slang,
no emoji. Acknowledge what you understood, then lead into the next question. Never name a place. Never state a number
or fact the user did not say. The question and its options appear on a card under your text, so do not list options.

`updates`: one entry per fact in the user's message.
- field: one of the allowed fields. op: set for one value; add / remove for lists (companions, anchor, signal, soft,
  hard, unmapped).
- value formats:
  start_date YYYY-MM-DD (today is {today}; a date already past means next year) | month 1-12 | days 1-7 | people
  companions solo|partner|friends|kids|parents | mobility motorbike|car|ride | arrive_at, leave_at, day_end HH:MM
  purpose relax|bond|photo|food_culture|nature|explore|adventure | pace slow|normal|packed | max_leg_min minutes
  crowd_tolerance avoid|ok_if_worth|fine | novelty familiar|new|mix | budget_vnd VND per person per day
  base: the area or place the user stays at, in their words | anchor: one place name or link they must visit
  entry_point, exit_point: where the trip enters and leaves the city (bus station, airport, a pass if driving), in their words
  signal: knee|elderly|kids|wheelchair|pregnant|motion_sick|height|vegetarian (health, body or diet hints)
  soft: feature=value[@context_key.context_value]:love|avoid, ids from FEATURES only
  hard: feature!=value or feature=value, only for what must not / must happen
  unmapped: a wish FEATURES cannot express, in the user's words
- quote: the exact words from the user's message that support the update, copied, not paraphrased.
- how: said when the user stated it; inferred when you concluded it (e.g. "đi với bố mẹ" -> signal elderly, inferred).
- A subjective word with several meanings ("chill", "đẹp", "vui"): do not guess a feature; ask what it means.
- When unsure, leave it out. A missing value is fine; a wrong one is not.

`next`:
- If REQUIRED is not "none": kind ask, qid = its id.
- Otherwise follow the user's thread: clarify a subjective word, or ask why they want a place they named (at most
  twice), using custom_text + 2-6 short custom_chips naming concrete things; or pick a qid from CANDIDATES; or kind
  stop when nothing left would change the result (BUDGET 0 means stop).
- reason: why the question matters, Vietnamese, one short clause, shown to the user.
- Unused fields: "" or [].

FEATURES (id: values - meaning)
{features}

TRIP STATE
{state}

LAST QUESTION SHOWN: {last_question}
EXPERIENCE WITH ĐÀ LẠT: {experience}
KEYWORD MATCHES (deterministic, may be wrong): {prepass}
REQUIRED: {required}
CANDIDATES:
{candidates}
BUDGET: {budget}

USER MESSAGE:
{text}""",
)

DECISION_OPS = ["select", "drop", "lock", "travel", "crowd", "price", "soft", "visited", "unmapped"]

DECISION_TURN = Task(
    name="decision_turn",
    role=AGENT,
    max_tokens=700,
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
  else "".
- visited: the user has been to `place` already. value "".
- travel | crowd | price: the user wants places closer | less crowded | cheaper in general, no single place. value "".
- soft: a wish about the kind of place: value "feature=value:love" or "feature=value:avoid", ids from FEATURES only.
- unmapped: a wish FEATURES cannot express; value = the user's words.
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
    parallel=8,  # four images per call
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
- Unsure, blurry, or could be anywhere -> nothing. Return an empty list when nothing is clearly shown.""",
)

PHOTO_VERIFY = Task(
    name="photo_verify",
    role=EXTRACTOR,
    max_tokens=300,
    parallel=8,
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
