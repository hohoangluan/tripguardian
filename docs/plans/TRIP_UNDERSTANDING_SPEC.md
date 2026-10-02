# Spec làm việc: Trip Understanding (bản chạy được đầu tiên)

Spec tạm thời (`RULE.md` §0.1). Thiết kế sản phẩm nằm ở `docs/TRIP_UNDERSTANDING.md`, tool và guardrail ở `docs/ARCHITECTURE.md` §18; spec này chỉ chốt **cách xây** bản đầu. Xây xong: gộp phần còn giá trị vào `docs/TRIP_UNDERSTANDING.md` (+ `DEV_LOG`, `LLM_PROVIDER`, `Role_Web_Functional_Design`, README) rồi xóa file này.

## 0. Phạm vi

| Có trong bản này | Để sau |
|---|---|
| Package Python `src/trip/`: Trip State có nguồn, coverage, ngân hàng câu, `rank_questions`, policy, agent 1 bước, guard, compile Search Input, HTTP + SSE | Lexicon build từ span + embedding (`TRIP_UNDERSTANDING.md` §5.2), dùng bản từ khóa |
| Role `AGENT` = Gemma (UIT), stream | Gu suy từ anchor (§5.3), gazetteer khu vực, weather / sun_times |
| Web: màn hội thoại + bản hiểu nhu cầu thay Setup + Discover; adapter Search Input → `TripState` web để Shortlist chạy nguyên | Place Decision đọc thẳng Search Input |
| Resolve anchor theo tên + link Maps (+ link TikTok nếu video có trong corpus) | User Profile thật (`get_profile`), import lịch / danh sách |
| Unit test + smoke test thật với Gemma | Mô phỏng user giả lập (§16) |

Quyết định đã chốt khi brainstorm:

- Backend Python + agent LLM (không chạy LLM trong trình duyệt).
- Approach **agent một bước có khung**: code prefetch mọi thứ agent cần, **1 call LLM / lượt** ra output có kiểu, guard validate, lỗi thì policy tất định chạy tiếp cùng state.
- Model: chỉ **Gemma** (`AGENT` role, cùng endpoint UIT với Extractor). Không tự chuyển sang model khác. Khi Gemma quá timeout, lượt đó do **policy tất định** trả lời (không phải model khác).
- Bố cục: chat bên trái + bản hiểu nhu cầu bên phải (mobile: thanh trượt đáy).
- Setup + Discover bị xóa; mọi chỉnh sửa đi qua bản hiểu nhu cầu.

## 1. Module

```
src/trip/                 online, chỉ ĐỌC corpus; import corpus chỉ qua corpus.ontology, corpus.llm
  __init__.py             public API: Engine, Session, TurnInput, Event, SearchInput
  __main__.py             python -m trip serve [--port 8766]
  state.py                Field, TripState, SearchInput, Evidence … (pydantic, frozen, extra=forbid)
  catalog.py              Catalog: data/intel/places + data/gmaps (tên, category, lat/lng, hours) → Candidate
  coverage.py             coverage(hard, candidates) → Coverage(pass, fail, unknown, level)
  prepass.py              tất định trên câu user: số ngày, tháng, ngày, người đi cùng, phương tiện, tín hiệu nhóm C,
                          ngân sách, từ khóa feature (lexicon tối thiểu) → list[Proposal]
  resolve.py              tên / link → Anchor (matched | choose | missing); port từ web/src/user/search.ts
  questions.py            ngân hàng câu A–I (Question, Chip → update), luật tầng 1, rank_questions
  policy.py               chọn câu kế + điều kiện dừng (dùng cho chip, edit, và đường lui)
  agent.py                build prompt (compact) → stream role AGENT → TurnPlan
  guard.py                TurnPlan + state → updates hợp lệ + câu kế hợp lệ
  compile.py              TripState → SearchInput
  understanding.py        TripState → các dòng bản hiểu nhu cầu (UI có kiểu)
  engine.py               một lượt: apply → prepass → agent → guard → policy → events
  sessions.py             memory + data/trip/sessions/<id>.json (state + transcript)
  server.py               ThreadingHTTPServer stdlib, 127.0.0.1 only, JSON + SSE
config/trip.yaml          ngưỡng: n_min, top_k, enough_factor, turn_budget, stop_score, timeout, cost câu hỏi
src/corpus/llm/           + role AGENT (roles.py), + task TRIP_TURN (prompt + schema, tasks.py)
```

`corpus.llm` là chỗ duy nhất giữ prompt và thiết lập model (docstring `tasks.py`), nên prompt agent nằm ở `tasks.py` dưới tên `TRIP_TURN`; `trip/agent.py` chỉ render và gọi stream. `Task.ask` hiện không stream → thêm `Task.stream(client, model, **fields)` trả async iterator chuỗi delta (cùng `response_format`, `temperature`, `max_tokens`).

Role mới trong `roles.py`, biến `.env` mới (thêm vào `.env.example`, `docs/LLM_PROVIDER.md`):

```
AGENT_API_KEY / AGENT_BASE_URL / AGENT_MODEL   # mặc định = Gemma UIT (như Extractor)
```

## 2. Data model (`state.py`)

```
Evidence   turn: int, quote: str | None, tool: str | None          # ít nhất một trong quote / tool
Field[T]   value: T | None = None
           source: user | anchor | profile | inferred | default
           confidence: high | medium | low
           status: unknown | asked | confirmed | skipped
           evidence: list[Evidence]                                # bắt buộc khi value != None và source != default
```

```
TripState
  start_date  Field[date]       month  Field[int 1..12]      days  Field[int 1..7]
  companions  Field[frozenset[solo|partner|friends|kids|parents]]  people Field[int 1..20]
  base        Field[Base(place_id | None, text)]
  mobility    Field[motorbike|car|ride]
  arrive_at / leave_at / day_end   Field[time]
  purpose     Field[relax|bond|photo|food_culture|nature|explore|adventure]
  anchors     list[Anchor(text, place_id | None, state: matched|choose|missing, candidates[place_id], priority: must|want)]
  signals     list[Signal(kind, quote, turn, handled: bool)]       kind: knee|elderly|kids|wheelchair|motion_sick|height|vegetarian|pregnant
  hard        list[Hard(feature, op: ne|eq, value, unknown_policy: exclude|flag|None, evidence)]
  soft        dict[str, Field[love|avoid|off]]                     key "feature=value" hoặc "feature=value@ctx_key.ctx_value[.ctx…]"
  pace        Field[slow|normal|packed]    max_leg_min Field[int]  crowd_tolerance Field[avoid|ok_if_worth|fine]
  novelty     Field[familiar|new|mix]      visited list[place_id]
  budget_vnd  Field[int]                                            # mỗi người mỗi ngày; corpus chưa kiểm → hiện "chưa kiểm được"
  unmapped    list[Unmapped(phrase, turn)]
  meta        experience: first|returning|None, start_with, turn: int, adaptive_turns: int,
              asked: list[qid], skipped: set[qid], unsure_streak: int
```

Bất biến (validator trong model, có test):

1. `soft` / `hard` chỉ nhận feature + value có trong ontology hiện hành (`Ontology.valid`), context chỉ `Ontology.valid_context`.
2. Field `source=user, status=confirmed` chỉ bị đổi bởi update `source=user` (câu user mới, chip, edit). `inferred` / `anchor` / `profile` không ghi đè nó.
3. `skipped` không bị hỏi lại trong session.
4. `TripState` bất biến; mọi thay đổi qua `apply(state, update) -> state` trong `state.py`.

```
SearchInput (frozen)
  ontology_version: int
  context    start_date | month, days, base, mobility, companions, people, arrive_at, leave_at, day_end
  hard_filters  [{feature, op, value, unknown_policy}]
  anchors       [{place_id, priority}]                 # chỉ anchor matched
  soft_weights  [{feature, value, context: {k: v} | None, weight: 1 | -1 | 0, source}]
  pace          {level, max_leg_min, crowd_tolerance}
  novelty       {level, visited}
  unknowns      [field name]                           # field còn unknown / skipped
  unmapped      [phrase]
```

`compile(state)` từ chối (raise `UnhandledSignal`) khi còn `Signal.handled = False` thuộc nhóm thể chất (guardrail §18.3).

## 3. Catalog và coverage

`Catalog.load()` đọc một lần lúc server khởi động: `data/intel/places/*.json` (features: `n`, `top_value`, `status`, `needs_review`; `identity`; `operation.hours`) + tên từ `place_name`. Candidate:

```
Candidate  id, name, category, lat, lng, hours: dict[weekday, list[(open, close)]] | None,
           signals: dict[feature, (top_value, n, served: bool)]      # served = n ≥ n_min, không needs_review, status ≠ uncertain
```

Coverage cho một `Hard(feature, ne, value)` trên tập ứng viên hiện tại:

```
fail    = served ∧ top_value == value
pass    = served ∧ top_value ≠ value          (vd steep_or_stairs top = absent)
unknown = còn lại
level   = enough  nếu pass ≥ top_k × enough_factor
          thin    nếu 0 < pass < ngưỡng
          none    nếu pass = 0
```

`eq` ngược lại. Level `thin`/`none` sinh câu **mức chấp nhận chưa xác minh** (`TRIP_UNDERSTANDING.md` §5.4) với số thật: "Chỉ {pass} nơi xác minh được …, {unknown} nơi chưa có thông tin."

## 4. Ngân hàng câu và chọn câu

`Question(qid, group, text(state) -> str, chips: list[Chip], multi, cost, sensitive, applies(state) -> bool, reason(state) -> str)`; `Chip(id, label, updates: list[Update])`. Mọi câu tự thêm chip `unsure` ("Không chắc") và `skip` ("Bỏ qua"); `unsure` ghi field `unknown` + `unsure_streak += 1`; `skip` thêm qid vào `skipped`.

| qid | Nhóm | Hỏi khi | Ghi |
|---|---|---|---|
| `frame` | A+B | thẻ mở đầu | days, companions, mobility (3 hàng chip trong một thẻ) + ô nhập tự do |
| `dates` | A | days biết, start_date/month chưa | start_date (date picker chip "chưa chốt") |
| `mobility` | A | chưa có | mobility |
| `companions` | B | chưa có | companions, people |
| `base` | A | chưa có, ≥ 2 anchor hoặc `max_leg_min` đặt | base (ô tìm nơi gần chỗ ở) |
| `times` | A | days biết, chưa hỏi | arrive_at, leave_at |
| `c_effort` | C | signal knee / elderly / kids / wheelchair chưa handled | hard steep_or_stairs ≠ present, long_walk ≠ present; signal.handled |
| `c_other` | C | signal motion_sick / height / vegetarian chưa handled | vegetarian → hard vegetarian_options = yes; còn lại → unmapped; handled |
| `policy:<feature>` | C | hard có coverage thin/none, chưa có unknown_policy | unknown_policy exclude / flag |
| `budget` | D | chưa có | budget_vnd |
| `anchor_pick:<i>` | E | anchor state choose | anchor.place_id |
| `anchor_priority` | E | ≥ 2 anchor matched | priority |
| `pace` | F | chưa có | pace |
| `max_leg` | F | chưa có | max_leg_min |
| `crowd` | F | chưa có | crowd_tolerance (+ soft crowd=low khi avoid) |
| `purpose` | G | chưa có | purpose + soft mặc định `inferred` (bảng §3 TRIP_UNDERSTANDING) |
| `vibe` | G | soft rỗng | soft theo feature (chip từ danh sách experience có coverage enough) |
| `novelty` | H | experience = returning | novelty |
| `clarify:<phrase>` | I | prepass / agent thấy từ chủ quan khớp > 1 feature | soft cho các feature được chọn; chip chỉ gồm feature có coverage enough |
| `show_first` | I | unsure_streak ≥ 2 | dừng |

Tầng 1 (`questions.required(state) -> qid | None`), thứ tự:
1. signal thể chất chưa handled → `c_effort` / `c_other`; rồi `policy:<feature>` nếu cần.
2. anchor `choose` → `anchor_pick:<i>`.
3. thiếu chặn khả thi: days → `frame`/`dates`; mobility; companions.
4. mâu thuẫn: anchor matched đóng cửa vào ngày đi (cần start_date + hours); `cloud_hunting=present` love mà user nói dậy muộn → thẻ nêu cái giá, chip chọn.

Tầng 2 (agent quyết, policy dùng thứ tự đơn giản): `clarify:*` vừa phát sinh → `purpose` nếu chưa có và user mơ hồ.

Tầng 3 `rank_questions(state, catalog) -> list[(qid, score)]`:

```
cands   = catalog lọc theo hard hiện tại (fail loại; unknown loại nếu policy ≠ flag)
rank(s) = top_k ứng viên theo Σ weight × [served ∧ top_value == value] (+ by_context khi soft có context)
với q áp dụng được:
   impact(q) = Σ_chip P(chip) · (1 − Jaccard(topK(state ⊕ chip), topK(state)))      P đều, bỏ unsure/skip
   score(q)  = impact(q) / q.cost
```

Dừng (`policy.should_stop`): không có câu tầng 1 **và** (score cao nhất < `stop_score` **hoặc** `adaptive_turns ≥ turn_budget` **hoặc** `unsure_streak ≥ 2` **hoặc** user bấm "Xem gợi ý"). Câu tầng 1 vẫn được hỏi khi hết ngân sách.

## 5. Một lượt (`engine.py`)

Input (`TurnInput`, một trong):

```
text    {text}                          câu user gõ (kể cả ô nhập trong thẻ)
answer  {qid, chips: [id], text?}       chạm chip; text kèm → xử lý như "text" sau khi áp chip
edit    {target, value | null}          sửa / xóa một dòng ở bản hiểu nhu cầu
show    {}                              "Xem gợi ý"
```

Luồng:

```
answer / edit ─► apply tất định (source=user, confirmed) ─► policy chọn câu ─► events      (không gọi LLM, < 100 ms)
text ─► prepass (tất định, < 50 ms) ─► event preview
     ─► agent: prompt = {state tóm tắt, câu user, prepass, câu tầng 1 bắt buộc (nếu có), top-5 rank_questions,
                         ngân sách còn lại, danh sách feature id + nhãn tiếng Việt}
        stream role AGENT; parse JSON tăng dần, đẩy say theo delta ─► event say
     ─► guard(TurnPlan) ─► apply ─► policy kiểm câu kế ─► events state, card
        Gemma quá timeout (token đầu 8 s, tổng 30 s) / JSON hỏng / lỗi mạng
        ─► áp prepass (inferred, confidence medium) + policy chọn câu + say mẫu:
           "Mình ghi lại được phần này; câu bạn gõ mình chưa hiểu hết, bạn có thể nói lại theo cách khác."
show ─► còn tầng 1 → card câu đó + say "Còn một câu để tránh xếp nhầm chỗ không hợp"; không thì compile ─► event done
```

Output schema của `TRIP_TURN` (strict JSON, `say` đứng đầu để stream):

```
say      string  ≤ 2 câu: ghi nhận ngắn + dẫn vào câu hỏi kế; không nêu tên địa điểm, số liệu
updates  [{field: enum, op: set|add|remove, value: string, quote: string, how: said|inferred}]
         field ∈ start_date, month, days, companions, people, base, mobility, arrive_at, leave_at, day_end, purpose,
                 anchor, signal, soft, hard, pace, max_leg_min, crowd_tolerance, novelty, budget_vnd, unmapped
         value là chuỗi, guard parse theo field (soft: "noise=quiet:love", "crowd=low@day_type.weekend:love")
next     {kind: ask|stop, qid: string, custom_text: string, custom_chips: [string], reason: string}
```

`guard.py`:

| Kiểm | Xử lý khi sai |
|---|---|
| `quote` (fold dấu, khoảng trắng) là chuỗi con của câu user lượt này | bỏ update |
| value parse được theo field; feature / value / context có trong ontology | soft/hard sai → `unmapped(quote)`; field khác → bỏ |
| `how = said` → `source=user, confidence=high`; `inferred` → `source=inferred, confidence=medium` | — |
| update không ghi đè field `user + confirmed` trừ khi `how=said` | bỏ update |
| có câu tầng 1 mà `next.qid` khác | thay bằng câu tầng 1, giữ `say` |
| hết ngân sách và `next` không phải tầng 1 | `stop` |
| `qid` không có trong ngân hàng và không có `custom_text` | policy chọn câu |
| `custom_text` (laddering / làm rõ tầng 2) cần ≥ 2 chip, ≤ 6 chip; mỗi chip ≤ 40 ký tự | policy chọn câu |
| `say` chứa tên một địa điểm trong catalog (tên ≥ 2 từ, không phải anchor của phiên) hoặc chữ số không có trong câu user | thay `say` bằng câu dẫn mẫu của câu hỏi kế |

Câu `custom` được lưu như một `Question` tạm (`qid = custom:<turn>`), chip của nó **không** có update sẵn: chạm chip = lượt `text` với nội dung chip, để agent hiểu lại theo ngữ cảnh.

## 6. API (`server.py`, 127.0.0.1:8766)

| Method | Path | Body / trả về |
|---|---|---|
| POST | `/api/trip/sessions` | `{experience, start_with}` → JSON `{id, view}` (view = transcript + understanding + card) |
| GET | `/api/trip/sessions/<id>` | `{id, view}` (mở lại sau khi tải lại trang) |
| POST | `/api/trip/sessions/<id>/turn` | `TurnInput` → `text/event-stream` |
| GET | `/api/trip/places?q=` | tìm nơi (ô chọn chỗ ở, anchor) |

Event SSE (mỗi event một dòng `event:` + `data:` JSON):

```
preview  {fields: [{target, text}]}           kết quả prepass, panel hiện mờ "đang hiểu"
say      {delta}                              chữ agent, nối dần
state    {understanding, can_show}            bản hiểu nhu cầu sau guard
card     {qid, text, reason, chips, multi, input: none|text|date|place}
done     {search_input}                       chỉ sau "show" hợp lệ
error    {message}                            lỗi không cứu được (session không tồn tại …)
```

Vite proxy: `/api/trip` → `127.0.0.1:8766` đặt **trước** `/api` → 8765.

## 7. Web

- `web/src/user/tu/api.ts`: tạo / mở session, gửi lượt, đọc SSE bằng `fetch` + `ReadableStream` (POST nên không dùng `EventSource`).
- `web/src/user/tu/adapter.ts`: `SearchInput → Partial<TripState>` (bảng dưới) + lưu nguyên `searchInput` vào `TripState` (field mới, optional).
- `web/src/user/screens/Understand.tsx`: màn hội thoại. Route `/app/understand`; `STEPS` gộp "Chuyến đi" + "Sở thích" thành "Hiểu chuyến đi"; `Start` xong → `/app/understand`. Xóa `Setup.tsx`, `Discover.tsx` và route của chúng; `Sessions.tsx` (admin) vẫn đọc `tg.trip.v1` như cũ.

| Search Input | TripState web |
|---|---|
| context.start_date / month, days, people, mobility, arrive_at, leave_at, day_end | `startDate` (month → ngày 1 của tháng gần nhất phía trước, đánh dấu ước lượng), `days`, `people`, `vehicle`, `arriveAt`, `leaveAt`, `rules.dayEnd` |
| context.companions | `who` |
| context.base.place_id | `lodging` |
| hard steep_or_stairs ne present | `rules.avoidSteep = true` |
| pace.max_leg_min | `rules.maxLegMin` |
| soft weight 1 / -1 | `prefs[feature] = {weight: love / avoid, from: profile nếu source profile, còn lại answer}` |
| anchors must | `mustVisit` + `locked` |
| pace.level | `pace` |

Bố cục và hành vi:

```
desktop ≥ 960px                                          mobile
┌ Hội thoại (cuộn) ──────────────┬ Bản hiểu (sticky) ┐   ┌ Hội thoại ──────────────┐
│ bong bóng agent / user          │ Mục đích  … ✎     │   │ …                        │
│ thẻ câu hỏi: text · vì sao hỏi  │ Chuyến    …        │   │ thẻ câu hỏi              │
│   [chip][chip][chip]            │ Anchor    …        │   ├──────────────────────────┤
│   Không chắc · Bỏ qua           │ Bắt buộc  … (cờ)   │   │ 3 ngày · bố mẹ · tránh dốc ▴ │  ← chạm mở bottom sheet
│ [ Gõ thêm…              ][Gửi]  │ Sở thích  …        │   │ [ Gõ thêm…      ][Gửi]   │
│                                 │ Chưa rõ / Chưa kiểm│   └──────────────────────────┘
│                                 │ [Xem gợi ý →]      │
└─────────────────────────────────┴────────────────────┘
```

- Gửi câu → bong bóng user hiện ngay; event `preview` làm các dòng panel sáng mờ "đang hiểu"; `say` chạy chữ; `state` chốt panel (mờ → rõ, ✎ cho `inferred` / `anchor` / `profile`); `card` trượt vào.
- Chip một lựa chọn gửi ngay khi chạm; chip nhiều lựa chọn có nút "Xong". Phím số 1–9 chọn chip, Enter gửi ô nhập. `aria-live="polite"` cho luồng chat; tôn trọng `prefers-reduced-motion`.
- Mỗi thẻ có dòng "vì sao hỏi" (`reason`, gồm số thật từ coverage khi có).
- Panel: mỗi dòng sửa tại chỗ bằng editor đúng kiểu (date, segmented, chip toggle, ô tìm nơi, nút xóa); sửa = lượt `edit`. "Chưa rõ" và "Chưa kiểm được" luôn hiện.
- "Xem gợi ý" luôn hiện; còn câu an toàn thì nút hiện "Còn 1 câu an toàn" và gửi `show` để server trả thẻ đó. `done` → adapter → `navigate('/app/shortlist')`.
- Backend không chạy → banner: "Chưa kết nối được trợ lý. Chạy `python -m trip serve` rồi tải lại."
- Session id lưu `localStorage` (`tg.tu.v1`, try/catch); tải lại trang → `GET` session dựng lại màn.
- Giao diện dùng lại token / class sẵn có (`user.css`, `ui/bits.tsx`: `Chip`, `Segmented`, `Icon`, `Page`).

## 8. Lỗi

| Tình huống | Xử lý |
|---|---|
| Gemma timeout / 429 / JSON hỏng | lượt đó chạy policy (§5), log `agent_fallback` vào transcript |
| Guard bỏ update / thay câu | log lý do vào transcript (để eval), user không thấy lỗi |
| Session không tồn tại | 404 → web tạo session mới, giữ `experience` / `start_with` |
| `data/intel` trống | server không khởi động, báo cần chạy `python -m corpus aggregate` |
| Hai lượt cùng session gửi chồng | khóa theo session; lượt sau chờ |

## 9. Test

- `tests/trip/test_state.py`: bất biến §2 (ontology, ghi đè user confirmed, skipped, evidence bắt buộc).
- `test_prepass.py`: câu tiếng Việt thật → proposal ("3 ngày 2 đêm", "2N1Đ", "tháng 12", "12–14/12", "đi với ba má", "mẹ đau gối", "đi xe máy", "300k/người", "chill" → mơ hồ).
- `test_coverage.py`, `test_questions.py`: catalog fixture nhỏ dựng tay; tầng 1 đúng thứ tự; `rank_questions` cho impact 0 khi mọi đáp án ra cùng top-K; dừng đúng điều kiện.
- `test_guard.py`: từng dòng bảng §5.
- `test_compile.py`: ví dụ §15 `TRIP_UNDERSTANDING.md` ra đúng Search Input; còn signal chưa handled → `UnhandledSignal`.
- `test_engine.py`: agent giả (trả TurnPlan định sẵn, hoặc timeout) → thứ tự event, đường lui.
- `test_server.py`: tạo session, lượt `answer`, đọc SSE.
- Smoke thật (`pytest -m live`, bỏ qua mặc định): 5 câu mẫu qua Gemma → JSON hợp lệ, thời gian token đầu / tổng được in ra.
- Web: `npm run build` (tsc) + chạy thật bằng Chrome qua `playwright-core` theo kịch bản §15 `TRIP_UNDERSTANDING.md`, chụp màn desktop + mobile, không lỗi console.

## 10. Thứ tự xây

1. `state.py`, `catalog.py`, `coverage.py` + test.
2. `prepass.py`, `resolve.py` + test.
3. `questions.py`, `policy.py`, `compile.py`, `understanding.py` + test.
4. Role `AGENT`, task `TRIP_TURN`, `Task.stream`; `agent.py`, `guard.py` + test; smoke Gemma.
5. `engine.py`, `sessions.py`, `server.py`, `__main__.py` + test.
6. Web: `tu/api.ts`, `tu/adapter.ts`, `Understand.tsx`, route; xóa Setup / Discover; chạy thật.
7. Gộp tài liệu, xóa spec này.
