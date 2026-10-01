"""Every model task in one place: role, prompt, output schema and call settings. Edit prompts and settings here.

A task's prompt_hash is stored with each result, so changing a prompt re-runs that task on the next build.
"""

import asyncio
import base64
import hashlib
import json
from dataclasses import dataclass

import openai

from .roles import EXTRACTOR, JUDGE, Role

ATTEMPTS = 4  # per call: a broken JSON answer or a busy / unreachable server is tried again
RETRY_S = 2.0  # first wait after HTTP 429 or a connection error; doubles each time


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
                return json.loads(r.choices[0].message.content)
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
  scenic_view; "có mái che, không sợ mưa" is weather_exposed sheltered. Use the opposite value only when the feature
  has one.
- The reviewer's own story is not a fact about the place: "mình đặt bàn trước" is NOT booking_needed yes; "đường đi
  hơi xa" (riding there) is NOT long_walk; "quán nằm trên dốc" is NOT steep_or_stairs unless visitors must climb.
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
  ("đi bộ từ khách sạn qua"), riding a long way ("đường đi hơi xa" is not walking far), what the reviewer did
  ("mình đặt bàn trước" does not mean booking is needed), heat or cold ("trên tầng 2 nóng" is not weather), a seat
  they were given, or a guess.
Give a one-sentence reason.

Review: {passage}""",
)
