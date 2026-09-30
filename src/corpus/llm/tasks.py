"""Every model task in one place: role, prompt, output schema and call settings. Edit prompts and settings here.

A task's prompt_hash is stored with each result, so changing a prompt re-runs that task on the next build.
"""

import hashlib
import json
from dataclasses import dataclass

from .roles import EXTRACTOR, JUDGE, Role


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

    async def ask(self, client, model: str, **fields) -> dict:
        r = await client.chat.completions.create(
            model=model, messages=[{"role": "user", "content": self.render(**fields)}],
            temperature=self.temperature, max_tokens=self.max_tokens,
            response_format={"type": "json_schema", "json_schema": {"name": self.name, "schema": self.schema, "strict": True}})
        return json.loads(r.choices[0].message.content)


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
