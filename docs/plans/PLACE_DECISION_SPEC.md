# Spec làm việc — Backend Place Decision

Spec tạm (`RULE.md` §0.1): khi xây xong, gộp phần còn giá trị vào `docs/PLACE_DECISION.md` (mục "Bản chạy hiện tại") rồi xóa file này. Hành vi tham chiếu: `docs/PLACE_DECISION.md` §1–17; spec này chỉ chốt cách cài đặt và các số liệu còn để ngỏ.

## 1. Phạm vi

Trong phạm vi:
- Module `src/decision/`: ① Resolve → ⑩ Xác nhận theo `PLACE_DECISION.md` §3, tất định, có test.
- Agent Gemma cho vòng ⑧ ↔ ⑨ khi user gõ chữ; chip / nút bấm không gọi LLM.
- HTTP + SSE: `python -m decision serve` → `127.0.0.1:8767`; Vite proxy `/api/decision`.
- Web: Shortlist, Compare, CurateBar, Feasibility đọc từ backend.
- `python -m decision evaluate` thay `python -m corpus evaluate`.
- `trip.SearchInput.Context` thêm `budget_vnd`, `experience`.

Ngoài phạm vi: Planning & Validation, Live Context, User Profile dài hạn (`recent_interest = 0`), giờ cố định của anchor (Search Input chưa có giờ anchor → không kiểm chồng giờ anchor), thẻ do LLM viết.

## 2. Ranh giới module

```text
trip (public: SearchInput, các type con)  ─┐
corpus.serving (public: load, check,       ├─►  decision  ──► data/decision/sessions/<id>.json
  feature, mmr, similarity, areas)         │
corpus.llm (public: AGENT, DECISION_TURN)  ─┘
```

- `decision` chỉ import qua `__init__.py` của `trip`, `corpus.serving`, `corpus.llm`, `corpus.ontology`.
- `corpus` không import `decision`. `trip` không import `decision`.
- Chỉ đọc `data/serving/places.json`; chỉ ghi `data/decision/`.

## 3. File

| File | Việc |
|---|---|
| `settings.py` | Đọc `config/decision.yaml` thành dataclass đóng băng |
| `geo.py` | `km(a, b)`, `minutes(km, mobility)` = km × `road_factor` / tốc độ, làm tròn phút; tâm Đà Lạt khi không có base |
| `trip_days.py` | Ngày của chuyến từ `start_date` + `days` → danh sách (ngày, thứ, `day_type`); chỉ có `month` → không biết thứ |
| `screen.py` | ③ Sàng lọc (§5) |
| `fit.py` | ④ Hợp bối cảnh (§6) |
| `rank.py` | ⑤ Xếp hạng (§7) |
| `diversify.py` | ⑥ Đa dạng, cỡ shortlist, nhóm hiển thị (§8) |
| `compare.py` | ⑦ So sánh (§9) |
| `cards.py` | Thẻ ứng viên bằng template (§10) |
| `feasibility.py` | ⑨ Khả thi tổ hợp (§11) |
| `curation.py` | Thao tác ⑧, Session Profile của phiên, pattern (§12) |
| `scope.py` | `replan_scope(diff)` (§13) |
| `pipeline.py` | Chạy ③–⑨ trên một `Session` → `View` |
| `session.py` | `Session` (pydantic), lưu / đọc, phiên bản + hoàn tác |
| `agent.py`, `guard.py`, `policy.py` | Lượt gõ chữ (§14) |
| `output.py` | ⑩ Decision Output (§15) |
| `engine.py`, `server.py`, `__main__.py` | Điều phối, HTTP + SSE, CLI `serve` / `evaluate` |
| `evaluate.py` | Mô phỏng offline (§17) |

## 4. Đầu vào

- `SearchInput` validate bằng chính model của `trip`. `ontology_version` khác version hiện tại → từ chối (409).
- Anchor (`place_id`) đã resolve ở Trip Understanding. Nơi user thêm trong phiên: `place_id` phải có trong serving, nếu không → 400 (tìm theo tên dùng `GET /api/trip/places` sẵn có). Nơi không có trong serving vẫn giữ được nếu là anchor: mọi khía cạnh `unknown`, thẻ ghi "chưa có trong dữ liệu".
- Ứng viên: record có `usable_as` không rỗng. Vai trò `experience` → nhóm trải nghiệm; `meal` (không `experience`) → nhóm ăn uống.

## 5. Sàng lọc

Mỗi ứng viên nhận `checks: list[Check(kind, feature, result, reason)]`.

Physical:
- Biết thứ của các ngày đi, `hours` có giá trị và nơi đóng mọi ngày đi → `fail` (`closed_all_trip_days`). `hours` là `OUTDATED` → không fail, chỉ cảnh báo.
- `hours` thiếu → cảnh báo `hours_unknown`.

User hard (`HardFilter`):
- `op = ne` → `corpus.serving.check(rec, feature, value)`.
- `op = eq` → `pass` khi giá trị chắc (`VERIFIED`/`OUTDATED`) bằng `value` và không ai nói giá trị khác; `fail` khi giá trị chắc khác `value`; còn lại `unknown`.
- Feature ngoài nhóm `effort`, `suitability` (không phải an toàn / tiếp cận): giá trị `UNCERTAIN` khác giá trị cấm và không ai nói giá trị cấm → `pass` + cảnh báo `uncertain_value` (`PLACE_DECISION.md` §6.2).

Kết quả:

| | Ứng viên thường | Anchor / nơi khóa / nơi user thêm |
|---|---|---|
| physical `fail` | `excluded` + lý do | Đề xuất wishlist (conflict physical) |
| hard `fail` | `excluded` + lý do | Conflict `relax` (giữ + hỏi nới cho riêng nơi này) |
| `unknown` | `unverified` (mở sẵn khi `unknown_policy = flag`) | Giữ + cờ "chưa xác minh được" |

Nới: `Session.relaxed: set[(place_id, feature)]`, chỉ áp cho nơi đó.

## 6. Hợp bối cảnh

`context_fit ∈ [0, 1]` + cờ, tính cho ứng viên qua sàng lọc:

```text
tâm      = base (nếu resolve được) hoặc tâm Đà Lạt; anchor cũng là tâm
d        = km tới tâm gần nhất
radius   = radius_km[mobility] × travel_mult (Session Profile) ; max_leg_min có → min(radius, quy đổi từ phút)
dist     = 1 − min(1, d / radius)
area     = +area_bonus nếu cùng identity.area với một anchor
crowd    = −crowd_penalty khi crowd_tolerance = avoid và crowd_by_time[day_type của chuyến] có buổi ngày ≥ crowd_busy_pct
            (cờ "đông <buổi> <ngày thường|cuối tuần>"); không biết day_type → xét cả hai, chỉ cờ
weather  = cờ "cần dự phòng mưa" khi weather_exposed = present hoặc setting = outdoor, và tháng ∈ rainy_months
access   = cờ khi rough_road_access = present (xe máy: "đường xấu"; ride: "xe công nghệ khó vào")
context_fit = clamp(dist + area + crowd, 0, 1)
```

`context_fit < min_context_fit` → ở lại pool, không vào shortlist.

## 7. Xếp hạng

Mỗi thành phần lưu riêng trong `score_parts`:

```text
conf(f)      = agreement × min(1, n / 3) × {VERIFIED 1, OUTDATED 0.7, UNCERTAIN 0.5}
pref         = Σ_w weight · match(w) · conf / Σ|weight|          (weight 0 bỏ qua)
               match = 1 khi giá trị (theo context nếu by_context có, nếu không giá trị chung) = value
uncertainty  = Σ_{weight>0, không có bằng chứng hoặc UNCERTAIN} |weight| / Σ|weight|
novelty      = new: −1 nếu đã đi · familiar: +0.3 nếu đã đi · mix / không biết: 0
experience   = first: pop_pct · returning: 1 − pop_pct · không biết: 0
popularity   = pop_pct = phân vị của provenance.voices trong tập ứng viên
price        = −price_sensitivity × price_level_norm (chỉ khi Session Profile đã tăng độ nhạy giá)
score        = Σ w_* · phần tương ứng   (w_* trong config, có version)
```

`novelty = new` + đã đi → không vào khám phá (trừ anchor). Soft weight `avoid` khớp → `pref` âm.

## 8. Đa dạng và cỡ shortlist

```text
ngày_khả_dụng = days (thiếu → default_days, cờ)
slot_trải_nghiệm = max(1, ngày × per_day[pace] − số anchor trải nghiệm)
slot_ăn         = ngày × meals_per_day
cỡ_nhóm         = ceil(slot × spare_factor)
```

- Chọn trong mỗi vai trò bằng `corpus.serving.mmr` trên `pool_factor × cỡ` ứng viên đứng đầu.
- Nhóm gần trùng: `near_duplicate_group` của record. Shortlist hiện đại diện; các nơi cùng nhóm còn lại (qua sàng lọc) là `alternatives` của đại diện.
- Nhóm hiển thị: `anchors` (luôn đầu), rồi `experience` theo `category_group` gộp: thiên nhiên (`nature`, `garden_farm`, `camping`), tham quan (`attraction`, `museum`, `religious`, `amusement`, `market`, `tour`, `golf`, `other`), cà phê và thư giãn (`cafe`, `spa`, `bar`, `dessert`); `meal` → ăn uống. Map nằm trong config.
- Nơi đã chọn / khóa luôn hiện, đứng đầu nhóm của nó, không bị xếp lại.

## 9. So sánh

`compare(a, b)` → các dòng `{aspect, a, b, better: a|b|none|unknown}`:
- Feature có bằng chứng chắc ở cả hai (`n ≥ 2`, giá trị khác nhau), có thứ tự tốt/xấu (config `polarity`, ví dụ `crowd: [low, medium, high]` thấp tốt hơn). Giống nhau → bỏ.
- Feature user quan tâm (`soft_weights`) mà một bên không có bằng chứng → `unknown`, ghi "chưa biết", không tính là thua.
- Hy sinh: km tới tâm (ước lượng thô theo phút), độ đông theo buổi của chuyến (`crowd_by_time`), mức giá, thời gian tham quan `typical`.
- Chỉ so cặp cùng nhóm gần trùng hoặc cùng nhóm hiển thị; khác vai trò → 400.

## 10. Thẻ ứng viên

Template, chỉ từ serving record và kết quả rule; mỗi dòng mang `sid` (feature id) để web mở bằng chứng:

| Mục | Template |
|---|---|
| `why` (≤ 3) | Feature khớp `soft_weights` có `pref` cao nhất: "<nhãn feature>, <n> người nhắc"; anchor: "Nơi bạn muốn đến"; gần tâm: "Gần <tâm>, ≈<phút> phút (ước tính)" |
| `tradeoffs` (≤ 3) | Cờ từ §6, feature xấu có bằng chứng (`n ≥ 2`): "<nhãn> theo <n> người" |
| `visit` | `[short, long]` phút + `source` |
| `location` | khu vực, km / phút ước tính tới tâm |
| `confidence` | `high`: không feature quan tâm nào `UNCERTAIN`/`OUTDATED`/thiếu · `medium` · `low`; kèm lý do; cờ `declined` khi `condition_change = declined` hoặc `rating_trend = falling` |
| `depends_on_unknown` | "Chưa biết ngân sách của bạn; giá khoảng …" khi `budget` ∈ `unknowns` và record có giá |
| `unmapped` | Danh sách cụm "chưa kiểm được" của Search Input (chung cho mọi thẻ, hiện một lần) |

Nhãn tiếng Việt của feature / value: `config/decision.yaml` `labels` (lấy từ `web/src/data/labels.ts` để hai nơi khớp nhau).

## 11. Khả thi tổ hợp

Chạy trên `selected` (gồm anchor và nơi khóa) sau mỗi thao tác:

```text
khung ngày    ngày 1: max(arrive_at, day_start) → day_end · giữa: day_start → day_end · cuối: day_start → leave_at
              (thiếu → day_start, day_end, leave_at trong config)
cần           Σ visit.typical + Σ buffer[pace] + đi lại
đi lại        Σ_stop intra_leg_min + Σ_khu 2 × minutes(tâm, tâm khu)
```

| Kiểm tra | Fail khi | Loại |
|---|---|---|
| `time` | cần > có | physical (`partial`; > có × `infeasible_ratio` → `infeasible`) |
| `hours` | biết thứ, nơi đóng mọi ngày đi | physical |
| `far_areas` | số khu có km tới tâm > `far_km` > số ngày | user (`partial`) |
| `per_day` | số nơi trải nghiệm > ngày × `per_day_max[pace]` | user |
| `budget` | biết `budget_vnd`: Σ giá giữa khoảng / ngày > budget × `budget_slack` | user |
| `relax` | nơi khóa vi phạm hard filter chưa nới | user |
| `wishlist` | nơi khóa vi phạm physical | physical |

- `hours` `OUTDATED`/thiếu → cảnh báo "kiểm tra lại trước chuyến", không fail.
- Mỗi conflict có `fixes: [{label, effect, action}]`, `action` là đúng payload của `POST /act`. `effect` tính bằng cùng phép tính: "Bỏ C: bớt ≈<phút> phút". Bỏ gợi ý nơi có `score` thấp nhất chưa khóa trong ngày / khu gây lỗi.
- `status`: `feasible` (không conflict) · `partial` · `infeasible` · `unknown` (thiếu `days` → chỉ chạy kiểm tra không cần ngày, cờ).

## 12. Tuyển chọn và Session Profile

Thao tác (`POST /act`, tất định):

| `type` | Payload | Tác động |
|---|---|---|
| `select` | `place_id` | Vào `selected`; bỏ khỏi `dropped` |
| `drop` | `place_id`, `reason?` ∈ `far, crowded, pricey, dislike, visited` | Ra khỏi `selected`/`locked`, vào `dropped`; lý do → Session Profile |
| `lock` / `unlock` | `place_id` | Khóa / mở khóa (khóa kéo theo `select`) |
| `swap` | `place_id`, `with_id` | Đổi sang nơi thay thế cùng nhóm |
| `relax` | `place_id`, `feature` | Thêm vào `relaxed` |
| `wishlist` | `place_id` | Chuyển nơi vi phạm physical sang wishlist |
| `answer` | `qid`, `chip` | Trả lời câu hỏi pattern / lấp chỗ trống |
| `undo` | — | Về phiên bản trước |

Session Profile (`Session.profile`): `travel_mult` (far → × `far_step`, sàn `travel_mult_min`), `crowd_tolerance` (crowded → `avoid`), `price_sensitivity` (pricey → + `price_step`), `soft` bổ sung (chỉ khi user xác nhận pattern), `visited` (visited → thêm id). `dislike` hay bỏ không lý do → chỉ giảm nơi đó (không quay lại trong phiên), không suy ra feature.

Pattern: ≥ `pattern_min` nơi bị bỏ (trong phiên) cùng có một cặp (feature, value) chắc chắn, không trùng với `soft_weights` đang `love` → `pending_question` (qid `pattern:<feature>=<value>`, chip `Đúng, tránh` / `Không phải`). `Đúng` → thêm soft `avoid`; `Không phải` → không hỏi lại cặp đó.

Lấp chỗ trống: sau `drop`, nếu khả thi báo thời gian dư ≥ `gap_min` → `pending_question` (qid `gap`, chip `Gợi ý nơi tương tự` / `Để thời gian tự do` / `Dồn sang ngày khác`). Không tự lấp. `Gợi ý nơi tương tự` → nơi kế tiếp chưa chọn cùng nhóm hiển thị có `score` cao nhất được đánh dấu `suggested`.

Quay lại Trip Understanding: số nơi bị bỏ ≥ `rethink_drops` và ≥ một nửa shortlist đầu → `pending_question` (qid `rethink`).

## 13. Chạy lại

- `pipeline.run(session)` chạy ③–⑨ toàn bộ mỗi lần (đo mục tiêu < 500 ms cho 1.394 record); bất biến giữ bằng dữ liệu phiên (nơi đã chọn / khóa nằm ngoài phần xếp hạng).
- `replan_scope(diff)` trả bước sớm nhất theo bảng `PLACE_DECISION.md` §14 + phần giữ nguyên; kết quả đi vào `diff` của phản hồi (để giải thích và test). Chỉ chuyển sang chạy từng phần nếu đo thấy chậm.
- Mỗi thao tác tạo một phiên bản (`Session.history`, tối đa `history_max`); `undo` khôi phục.
- Phản hồi có `diff`: nơi vào / ra shortlist, thay đổi trạng thái khả thi, `delta` (nơi, phút tham quan, phút đi lại), một câu tóm tắt.

## 14. Agent

Một call `DECISION_TURN` (role `AGENT`, stream `say` trước) cho mỗi tin nhắn gõ chữ trong màn chọn nơi.

Input prompt: tin nhắn; tóm tắt view (shortlist / đã chọn / bị bỏ gần đây dưới dạng alias `P1…Pn` + tên + nhóm + cờ chính); Session Profile; `pending_question`; trạng thái khả thi + conflict; `unmapped`.

Output:

```text
say       tiếng Việt, 1–2 câu
updates   [{op, place, value, quote}]
          op ∈ select | drop | lock | travel | crowd | price | soft | visited | unmapped
          place = alias hoặc ""; value: lý do drop / soft "feature=value:love|avoid" / ...
next      {kind: none | ask_pattern | ask_gap | rethink, reason}
```

Guard (code):
- `quote` phải nằm trong tin nhắn; `place` phải là alias có trong view; `value` đúng tập cho phép, `soft` theo ontology → sai thì bỏ update (ghi log).
- `select`/`lock` chỉ nhận khi quote chứa tên (hoặc một phần tên ≥ 2 từ) của nơi đó.
- Update đi qua đúng các thao tác §12 → cùng bất biến.
- `next` chỉ được chọn khi rule tương ứng (§12) đang mở; nếu không → `none`.
- `say`: bỏ khi có số user không nói và không có trong view, hoặc tên địa điểm ngoài view.
- Lỗi / quá thời gian (`first_token_s`, `total_s` trong config) / JSON hỏng → `policy`: từ khóa (`xa` → far, `đông` → crowded, `đắt|mắc` → pricey, `đi rồi` → visited, `không thích` → dislike) + tên nơi trong view; `say` mặc định.

Event SSE: `say` (`delta` / `replace`), `view` (view mới + diff), `done`, `error`.

## 15. Output

`POST /confirm` chỉ khi khả thi là `feasible` (hoặc `unknown` do thiếu ngày, kèm cờ). Ghi vào phiên và trả về Decision Output đúng `PLACE_DECISION.md` §15:
- `confirmed`: id, vai trò (`anchor | locked | selected`), `visit`, cờ, `relaxed`.
- `backup_pool`: nơi thay thế của nơi đã chọn + nơi bị loại vì lý do theo ngữ cảnh (`weather`, `crowd`) + top chưa chọn, kèm lý do.
- `wishlist`, `trip_context` (Search Input), `decision_log` (thao tác, lý do bỏ, nới, so sánh đã mở).

## 16. HTTP

| Method | Path | |
|---|---|---|
| POST | `/api/decision/sessions` | `{search_input, trip_session?}` → `{id, view}` |
| GET | `/api/decision/sessions/:id` | `{id, view}` |
| POST | `/api/decision/sessions/:id/act` | thao tác §12 → `{view, diff}` |
| POST | `/api/decision/sessions/:id/turn` | `{text}` → SSE |
| GET | `/api/decision/sessions/:id/compare?a=&b=` | §9 |
| GET | `/api/decision/sessions/:id/why-not/:place` | lý do loại (`explain_exclusion`) |
| POST | `/api/decision/sessions/:id/confirm` | §15 |

Lỗi: thiếu `data/serving/places.json` → 503 + "chạy `python -m corpus serving`"; lệch ontology → 409; id lạ → 400; không có phiên → 404. Chỉ bind `127.0.0.1`.

`View`: `groups[{id, label, cards[]}]`, `selected[]`, `unverified{count, open, cards[]}`, `excluded{by_rule[{rule, count}]}`, `wishlist[]`, `feasibility`, `pending_question`, `profile`, `unknowns`, `unmapped`, `version`.

## 17. Đánh giá

`python -m decision evaluate` → `data/decision/eval.json`. Dịch mỗi chuyến của `config/eval_trips.yaml` thành `SearchInput` (hard → `ne`, soft → `love`), chạy pipeline, đo trên nhóm vai trò của chuyến: vi phạm (đọc phân phối gốc), `unknown` trong danh sách chính, tỉ lệ gần trùng, đủ cỡ. Mục tiêu: 0 vi phạm, 0 `unknown`. Xóa `corpus/serving/evaluate.py` và lệnh `corpus evaluate`; test của nó chuyển sang `tests/decision/`.

## 18. Config (`config/decision.yaml`, số khởi đầu, hiệu chỉnh sau pilot)

```yaml
version: 1
center: {lat: 11.9404, lng: 108.4583}
speed_kmh: {motorbike: 25, car: 25, ride: 22}
road_factor: 1.4
radius_km: {motorbike: 12, car: 15, ride: 10}
area_bonus: 0.2
crowd_busy_pct: 70
crowd_penalty: 0.2
rainy_months: [5, 6, 7, 8, 9, 10]
min_context_fit: 0.1
weights: {ctx: 1.0, pref: 2.0, nov: 1.0, exp: 0.3, pop: 0.2, unc: 0.5, price: 0.5}
per_day: {slow: 3, normal: 4, packed: 6}
per_day_max: {slow: 4, normal: 5, packed: 7}
meals_per_day: 2
spare_factor: 1.6
pool_factor: 5
default_days: 2
day_start: "08:00"
day_end: "21:00"
leave_at: "15:00"
buffer_min: {slow: 30, normal: 20, packed: 10}
intra_leg_min: 10
far_km: 8
infeasible_ratio: 1.35
budget_slack: 1.0
far_step: 0.8
travel_mult_min: 0.4
price_step: 0.5
pattern_min: 3
gap_min: 90
rethink_drops: 6
history_max: 50
first_token_s: 8
total_s: 30
display_groups:         # §8: category_group -> nhóm hiển thị
  nature: [nature, garden_farm, camping]
  sights: [attraction, museum, religious, amusement, market, tour, golf, other]
  chill: [cafe, spa, bar, dessert]
polarity:               # §9: tốt trước, xấu sau
  crowd: [low, medium, high]
  noise: [quiet, moderate, loud]
  cleanliness: [clean, dirty]
  toilet: [clean, dirty]
  parking: [easy, hard]
  food_quality: [good, mixed, poor]
  drink_quality: [good, mixed, poor]
  service_attitude: [good, poor]
  service_quality: [good, mixed, poor]
  value_for_money: [good, poor]
  wait_time: [none, short, long]
  portion_size: [generous, small]
  tourist_trap: [absent, present]
  weather_exposed: [sheltered, present]
  entry_fee: [free, paid]
  rough_road_access: [absent, present]
  steep_or_stairs: [absent, present]
  long_walk: [absent, present]
labels: ...             # §10: chép từ web/src/data/labels.ts lúc cài đặt
```

## 19. Web

- `web/src/user/pd/{api,types}.ts`: client + type của API.
- Understand: khi nhận `done` → `POST /sessions` → lưu `decisionId` vào `TripState`.
- Shortlist: render `view.groups`; thẻ dùng `card` từ backend (video / bằng chứng vẫn lấy từ snapshot khi có id); bỏ / thêm / khóa / so sánh → `act`; ô "Nói với mình" → `turn` (SSE), bong bóng agent + chip của `pending_question`; mục "chưa xác minh được"; thông báo số nơi bị loại theo quy tắc + "Vì sao không có …".
- Compare: `GET compare`.
- CurateBar: `view.feasibility` + `diff` + `Hoàn tác` (`undo`).
- Feasibility: conflict + fix từ backend; nút xác nhận → `confirm` → `trip.selected = confirmed` → `/app/plan` (Lịch trình giữ prototype client).
- `planner.ts`: bỏ `buildShortlist`, `evaluate`, `similarGroups`, `keepPick`, `sharedTraits`, `deltaLine` khi không còn dùng; giữ `plan`, `rainBackup`, `anchorOf`, `dayWindows` cho Lịch trình.
- Export lại `snapshot.json` (`python web/scripts/export_snapshot.py`) để id khớp serving.
- Vite proxy: `/api/decision` → `127.0.0.1:8767`, đặt trước `/api`.

## 20. Test

- Unit với record mẫu nhỏ dựng trong test: `screen` (ne / eq / unknown / UNCERTAIN theo nhóm / anchor vi phạm / nới), `fit`, `rank` (từng thành phần), `diversify` (cỡ, nhóm, đã chọn đứng yên), `compare`, `cards` (mọi dòng có nguồn), `feasibility` (từng kiểm tra, fix đúng payload), `curation` (lý do → profile, pattern, gap, undo), `scope` (bảng §14).
- Bất biến: nơi khóa không bị loại âm thầm; danh sách chính 0 `unknown` hard; thao tác chip không gọi agent.
- `guard`, `agent` với stream giả (timeout, JSON hỏng, vòng khoảng trắng), `engine`, `server` (mã lỗi).
- `tests/decision/test_live.py` (`-m live`): một lượt Gemma thật.
- `python -m decision evaluate`: 0 vi phạm, 0 `unknown`.
- `trip`: test Context có `budget_vnd`, `experience`.
- Web: `npm run build`; chạy thật trên trình duyệt luồng Understand → Shortlist → bỏ có lý do → khả thi → xác nhận → Lịch trình, không lỗi console.

## 21. Tài liệu khi xong

`docs/PLACE_DECISION.md` (mục "Bản chạy hiện tại" + sửa §3 phân vai: thẻ dùng template), `docs/TRIP_UNDERSTANDING.md` §11 (Context có `budget_vnd`, `experience`), `docs/log/DEV_LOG.md` (mục `place-decision`, sửa `corpus-serving`), `docs/LLM_PROVIDER.md` (task `DECISION_TURN`), `docs/Role_Web_Functional_Design.md`, `README.md`, `AGENTS.md` (không đổi trừ khi cần trỏ). Xóa spec + plan này.
