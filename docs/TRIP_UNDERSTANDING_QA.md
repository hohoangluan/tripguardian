# Hướng dẫn QA — Trip Understanding & Chuẩn bị Kiểm thử Tự động

Tài liệu chuẩn hóa phục vụ:
1. **Kiểm thử Trip Understanding:** Tạo bộ vài ngàn use case (prompt tự nhiên thuần túy + hoàn tất hội thoại/control) để kiểm tra độ hiểu, trích xuất thực tế, an toàn fail-closed và biên dịch `SearchInput`.
2. **Chuẩn bị dữ liệu bàn giao cho Place Decision & Planning:** Cung cấp đầu vào chuẩn ngữ nghĩa, tách biệt rõ ràng giữa kiểm thử trích xuất và giải pháp tự động hóa tổ hợp địa điểm ở bước Planning (§10).

Nguồn sự thật tối cao là **code và schema hiện tại** (`src/trip/`, `src/decision/`, `src/planning/`); không coi câu trả lời hay suy luận của model là bằng chứng state đã được ghi.

---

## 1. Ranh giới và luồng kiểm thử

Hệ thống Trip Understanding hiện tại hoạt động theo cơ chế **Chat-with-cards** chia sẻ chung một `TripState` (`docs/TRIP_UNDERSTANDING.md` §4):

```text
USER PROMPT ──► CLEF FLASH ──┬──► PREPASS (từ khóa tất định: slots độ chính xác cao)
 (văn bản)      (chặn rác,   │         │
                lạc đề)      │         ▼ suggestions
                             └──► AGENT LOOP (LLM + function calling: record_fact, resolve, ask, web)
                                       │
                                       ▼ (qua domain.guard)
                             TRIP STATE (mọi field có provenance: source, confidence, evidence)
                                       │
                                       ├──► READINESS & MISSING (domain/readiness.py)
                                       │
                                       ▼ (nút Show / Next khi ready)
                               SEARCH INPUT (context, hard_filters, soft_weights, unknowns...)
                                       │
                                       ▼
                             PLACE DECISION & PLANNING (§10)
```

Mỗi test case kiểm thử ngữ nghĩa được chia làm hai giai đoạn rõ ràng:

1. **Giai đoạn 1 — Prompt tự nhiên thuần túy:**
   - Người dùng gửi một hoặc nhiều lượt văn bản tự do (không gửi payload JSON thô).
   - Kiểm tra: Slot extraction, Suggestion handling, Hard constraint, Safety signal, Provenance quote substring, và phát hiện yêu cầu chưa hỗ trợ (`unmapped`).
2. **Giai đoạn 2 — Hoàn tất thông tin thiếu bằng thẻ / control:**
   - Trả lời các card do engine dựng (`quiz_queue` hoặc agent `ask`), chọn chip, chọn lịch, chọn địa điểm / chỗ ở từ ô tìm kiếm.
   - Kiểm tra: Cập nhật state, biến đổi `missing`, kiểm tra điều kiện `ready` và biên dịch sang `SearchInput`.

---

## 2. Thông tin cốt lõi, điều kiện chuyển bước và hành vi Runtime

### 2.1 Bảng phân loại mức độ quan trọng

| Thông tin | Phân loại | Hành vi Runtime thực tế trong code |
|---|---|---|
| `days` | Cốt lõi | Thiếu thì vào `missing`; prepass đọc được từ số/chữ; thiếu vẫn cho phép xuất `SearchInput` với `days = null`. |
| `companions` | Cốt lõi | Thiếu thì vào `missing`. **Prepass chỉ đưa vào `suggestions`** (không tự ghi state); Agent phải gọi `record_fact`. Không tự đoán nhóm người. |
| `mobility` | Cốt lõi | Thiếu thì vào `missing`. **Prepass chỉ đưa vào `suggestions`**; Agent phải gọi `record_fact`. Không tự đổi taxi/Grab thành ô tô. |
| `start_date` hoặc `month` | Cốt lõi | Thiếu cả hai thì `missing.target = when`. Prepass đọc được ngày/tháng cụ thể. Có tháng chưa có nghĩa là biết ngày/thứ. |
| `signals` chưa xử lý | Chặn an toàn | `knee`, `wheelchair`, `pregnant`, `elderly`, `kids`, `vegetarian`, `vegan`, `motion_sick`, `height`. **Khi còn signal mở: `ready = false`**, trực tiếp gọi `compile_search_input` sẽ ném `UnhandledSignal`. |
| Hard constraints (vận động / chế độ ăn) | Chặn an toàn | Phải giữ đúng `meaning`, `scope`, `subject`, `unknown_policy` và `evidence`. Signal được coi là `handled` khi có hard filter tương ứng phủ nó (`domain/state.py::settle`). |
| `people` | Điều kiện | Prepass đọc được từ số người; cần thiết để chia ngân sách nhóm và tính toán xe đoàn đông (`coach_access`). Không trực tiếp chặn nút Next. |
| `budget_vnd` + `budget_scope` | Điều kiện | Prepass đọc số tiền và scope trong cùng mệnh đề. Thiếu scope thì heuristic đoán theo ngưỡng 2 triệu VND. `SearchInput` giữ `context.budget_intent` đầy đủ; scalar `budget_vnd` quy về **VND/người/ngày** (nếu không đủ days/people để chia thì `budget_vnd = null` và thêm vào `unknowns`). |
| Đoàn đông (`car` + `people >= 9`) | Tự động | Khi `mobility = car` và `people >= 9`, compiler tự động chèn hard filter `coach_access ne no` với `unknown_policy = exclude`. |
| Chỗ ở (`lodging`, `base`) | Hậu cần | Không bắt buộc ở Trip; nếu chưa có thì `SearchInput.context.lodging = null`, Planning sẽ cảnh báo `base_unknown` và xếp lịch từ điểm tham quan đầu tiên. |
| Gu, mục đích, nhịp độ, novelty, liked_groups | Tùy chọn | Không chặn Next; thiếu thì giữ `unknown` hoặc trung tính. |

### 2.2 Chi tiết cơ chế `ready` và `missing`
- `config/trip.yaml` định nghĩa `required: [days, companions, mobility, when]`. Danh sách này được `domain/readiness.py` dùng để tạo mảng `missing: [{target, label}]` cho UI hiển thị và hướng dẫn hỏi tiếp.
- Tuy nhiên, trong `domain/understanding.py`, **`ready` chỉ phụ thuộc vào việc có còn `signals` chưa xử lý hay không**. Do đó, trường hợp `ready = true` nhưng `missing` vẫn còn các trường cốt lõi là hoàn toàn hợp lệ.
- Khi người dùng gửi action `{kind: "show"}`:
  1. `Engine._show` sẽ thử gọi `strictest()` trên các signal còn mở (áp dụng giả định bảo thủ fail-closed).
  2. Nếu sau `strictest()` vẫn còn signal mở → từ chối chuyển bước (`MISSING_SAY`).
  3. Nếu không còn signal mở → cho phép xuất `done.search_input`, các trường cốt lõi thiếu sẽ mang giá trị `null` và nằm trong `unknowns`.
- **Lưu ý QA:** Khi viết assertion kiểm thử, không khẳng định "thiếu days thì nút Show luôn bị từ chối", mà phải kiểm tra `missing` chứa `days` và `SearchInput.context.days is None`.

---

## 3. Giao thức tương tác API & Envelope

### 3.1 Gửi Prompt qua API

Trong UI, người dùng chỉ nhập văn bản tự nhiên. API hỗ trợ 2 chế độ:

#### A. Chế độ Trip API độc lập (Standalone Server — Cổng 8766)
- Khởi tạo phiên: `POST /api/trip/sessions` với payload `{}` (hoặc `{experience, start_with, user_id, remember}`).
- Gửi lượt nói: `POST /api/trip/sessions/<session_id>/turn`
  ```json
  {
    "kind": "text",
    "text": "Mình muốn đi Đà Lạt 3 ngày vào tháng 12 với người yêu, đi xe máy."
  }
  ```
- SSE Events trả về theo thời gian thực:
  - `preview`: Bản xem trước state ngay sau khi Prepass chạy xong (giúp UI phản hồi tức thì).
  - `progress`: Các bước chạy nền (Clef, tìm kiếm ontology, tra cứu web).
  - `say`: Lời thoại của Agent (delta hoặc replace).
  - `state`: Cập nhật `understanding` (bản hiểu nhu cầu, matched count, matching board).
  - `card`: Thẻ trả lời tiếp theo (`quiz_queue` hoặc `ask`).
  - `done`: Chứa `{search_input}` khi hoàn tất.
  - `error`: Lỗi nếu có.

#### B. Chế độ Agent Harness (Hệ thống tích hợp Journey)
- Tạo journey: `POST /api/harness/sessions`
- Gửi request: `POST /api/harness/sessions/<id>/request`
  ```json
  {
    "request_id": "qa-tu-prompt-001",
    "stage": "trip",
    "operation": "turn",
    "expected_revision": 0,
    "payload": {
      "kind": "text",
      "text": "Mình muốn đi Đà Lạt 3 ngày vào tháng 12 với người yêu, đi xe máy."
    }
  }
  ```

### 3.2 Gửi Action ở Giai đoạn Hoàn tất (Cards / Controls)

Không gửi JSON trạng thái thô để gian lận việc extract. Sử dụng đúng các kind action được Engine hỗ trợ:

- **Trả lời câu hỏi trắc nghiệm (Quiz card / Chip):**
  ```json
  {"kind": "answer", "qid": "companions", "chips": ["who:partner"]}
  ```
- **Chọn ngày trên lịch:**
  ```json
  {"kind": "answer", "qid": "dates", "value": "2026-12-14"}
  ```
- **Chọn kết quả tìm kiếm chỗ ở / địa điểm:**
  ```json
  {
    "kind": "answer",
    "qid": "lodging",
    "value": "{\"text\": \"Khách sạn Colline\", \"lat\": 11.942, \"lng\": 108.437, \"kind\": \"corpus\", \"place_id\": \"hotel_colline\"}"
  }
  ```
  *(Lưu ý: `value` là JSON string được mã hóa, không phải object trần).*
- **Chỉnh sửa trực tiếp trên bản hiểu nhu cầu (Control Edit):**
  ```json
  {"kind": "edit", "target": "days", "value": "4"}
  ```
  *(Để xóa một scalar về unknown, truyền `"value": null`).*
- **Yêu cầu xuất kết quả để sang bước tiếp theo:**
  ```json
  {"kind": "show"}
  ```

---

## 4. Toàn bộ Inventory của TripState

Mỗi trường dữ liệu trong `TripState` được bọc bởi `Field[T]` mang provenance (`source`, `confidence`, `status`, `evidence`, `requirement`):
- `source`: `user` | `anchor` | `profile` | `inferred` | `default`
- `confidence`: `high` | `medium` | `low`
- `status`: `unknown` | `asked` | `confirmed` | `skipped`
- `evidence`: Bắt buộc phải có `turn` kèm `quote` (trích dẫn nguyên văn từ lời user) hoặc `tool` (tên công cụ tra cứu).

### 4.1 Bảng Scalars và Phân chia Prepass vs Agent

| Field | Kiểu dữ liệu / Range | Vai trò Prepass | Vai trò Agent | Ghi chú kiểm thử QA |
|---|---|---|---|---|
| `start_date` | `date` (ISO `YYYY-MM-DD`) | **Ghi Fact** | `resolve_relative_date`, `weekday_date` | Ngày đã qua phải bị reject. |
| `month` | `int` (1–12) | **Ghi Fact** | `record_fact` | Đổi month sẽ tự reset `month_part`. |
| `month_part` | `early`, `mid`, `late` | **Ghi Fact** | `record_fact` | Đầu / giữa / cuối tháng. |
| `days` | `int` (1–30) | **Ghi Fact** | `record_fact` | Range chuẩn: 1–30 ngày. Khuyến nghị ≤ 14. |
| `nights` | `int` (0–30) | **Ghi Fact** | `record_fact` | Phải ≤ days. Giảm days làm mất nights nếu nights > days mới. |
| `people` | `int` (1–20) | **Ghi Fact** | `record_fact` | Số người thực tế, không tính thú cưng. |
| `budget_vnd` | `int` (10.000–50.000.000) | **Ghi Fact** | `record_fact` | Số tiền thô user nói. |
| `budget_scope` | `trip_total`, `per_day`, `per_person`, `per_person_day` | **Ghi Fact** | `record_fact` | Đọc trong cùng mệnh đề với tiền. |
| `companions` | Set các ID: `solo`, `partner`, `friends`, `kids`, `parents`, `baby`, `pet`, `coworkers` | **Chỉ Suggestion** | **Bắt buộc Agent ghi** | Prepass không ghi trực tiếp vào state! Kiểm tra agent gọi `record_fact(companions, ...)`. |
| `companions_other` | `tuple[str, ...]` | Bỏ qua | Agent ghi | Đối tượng ngoài từ vựng chuẩn (vd: "hàng xóm"). |
| `mobility` | `motorbike`, `car`, `walk` | **Chỉ Suggestion** | **Bắt buộc Agent ghi** | Prepass không ghi trực tiếp. Taxi/Grab không tự chuyển thành car. |
| `purpose` | `relax`, `bond`, `photo`, `food_culture`, `nature`, `explore`, `adventure` | Bỏ qua | Agent ghi | Mục đích chính chuyến đi. |
| `pace` | `slow`, `normal`, `packed` | **Chỉ Suggestion** | Agent ghi | Nhịp độ chuyến đi. |
| `novelty` | `familiar`, `new`, `mix` | **Chỉ Suggestion** | Agent ghi | Thích quán quen hay khám phá mới. |
| `crowd_tolerance` | `avoid`, `ok_if_worth`, `fine` | Bỏ qua | Agent ghi | Thái độ với nơi đông đúc. |
| `liked_groups` | `tuple[nature, sights, chill, meal]` | **Chỉ Suggestion** | Agent ghi | Giữ đúng thứ tự xuất hiện, loại bỏ trùng lặp. |
| `checkin_at` | `str` (HH:MM) | Bỏ qua | Agent ghi | Giờ bắt đầu ngày đầu tiên (00:00–23:59). |
| `checkout_at` | `str` (HH:MM) | Bỏ qua | Agent ghi | Giờ kết thúc ngày cuối cùng. |
| `day_end` | `str` (HH:MM) | Bỏ qua | Agent ghi | Giờ kết thúc các ngày thông thường. |
| `base` | `Base` | Bỏ qua | Agent / Card | Khu vực hoặc toạ độ lưu trú trung tâm. |
| `origin` | `Base` | Bỏ qua | Card / Search | Nơi xuất phát (thường qua ô tìm kiếm geo). |
| `arrival_mode` | `self`, `bus`, `plane` | Bỏ qua | Card / Edit | Phương thức di chuyển đến Đà Lạt. |
| `lodging_booked` | `yes`, `no` | Bỏ qua | Card / Edit | Đã đặt chỗ ở trước hay chưa. |
| `lodging` | `Base` | Bỏ qua | Card / Search | Chỗ ở cụ thể đã chốt. |

### 4.2 Collections và Ràng buộc phức hợp

1. **`signals: tuple[Signal, ...]`**
   - Prepass ghi trực tiếp khi gặp từ khóa thể chất/sức khỏe: `knee`, `elderly`, `wheelchair`, `pregnant`, `motion_sick`, `height`, `vegetarian`, `vegan`.
   - Mỗi signal có `kind`, `quote`, `turn`, `handled: bool`.
2. **`hard: tuple[Hard, ...]`**
   - Kế thừa từ `Requirement`: `feature`, `op` (`eq` | `ne`), `value`, `unknown_policy` (`exclude` | `flag`), `evidence`.
   - Chứa metadata ngữ nghĩa: `meaning`, `scope` (`all`, `eating`, `drinking`, `sightseeing`, `accommodation`, `travel`), `subject` (`traveler`, `group`, `member`, `unspecified`), `subject_count` (1–20), `ambiguity`.
   - Prepass tự động tạo hard filter cho: `steep_or_stairs` (tránh dốc/bậc) và `long_walk` (ngại đi bộ xa).
3. **`soft: dict[str, Field[Weight]]`**
   - Key là chuỗi `SoftKey` chuẩn hóa: `<feature>=<value>[@<context_key>.<context_val>]`.
   - Weight: `love` (+1), `avoid` (-1), `off` (0).
4. **`anchors: tuple[Anchor, ...]`**
   - `text`, `place_id`, `state` (`matched`, `choose`, `missing`), `candidates`, `priority` (`must`, `want`).
5. **`activities: dict[str, Activity]`**
   - Gắn hoạt động cụ thể tại POI: `eating`, `coffee`, `drinking`, `tasting`, `wine_tasting`, `alcohol_consumption`, `sightseeing`, `photography`, `walking`, `nightlife`, `accommodation`, `travel`.
6. **`time_preferences: tuple[TimePreference, ...]`**
   - Ưu tiên mềm về buổi: `period` (`morning`, `midday`, `afternoon`, `evening`, `daytime`, `sunrise`, `sunset`), `weight` (1–3), `place_id?`, `activity?`, `evidence`.
7. **`unmapped: tuple[Unmapped, ...]`**
   - Lưu trữ các yêu cầu người dùng nêu mà hệ thống/ontology chưa hỗ trợ (ví dụ: "cần chỗ gửi xe bán tải", "quán có phòng VIP riêng"), có `phrase`, `turn`.
8. **`vibes: tuple[Vibe, ...]`**
   - Phong cách không gian: `phrase`, `cues`, `status` (`cues`, `kinds`, `done`, `none`), `places`.

---

## 5. Từ vựng Ontology v12 & Condition Mở rộng

Hệ thống sử dụng Ontology version **12** với **71 features** chuẩn hóa. Mọi prompt sinh ra cần bám sát ý nghĩa thực tế của các feature này:

### 5.1 Bảng 71 Features theo Nhóm

```text
[EXPERIENCE] (25)
scenic_view, cloud_hunting, sunset_view, photo_spot, nature, flower_garden, heritage_architecture,
cozy_decor, laptop_friendly, long_stay_chill, live_music, adventure_activity, hiking, animals,
local_specialty_food, food_quality (good|mixed|poor), drink_quality (good|mixed|poor),
hands_on_workshop, pick_your_own, cultural_show, camping, tasting_available, wine_tasting_available,
costume_rental, kids_play_area.

[ENVIRONMENT] (16)
crowd (low|medium|high), noise (quiet|moderate|loud), setting (indoor|outdoor|both),
cleanliness (clean|dirty), weather_exposed (present|sheltered), parking (easy|hard), outdoor_seating,
spacious, small_space, toilet (clean|dirty), mosquitoes, fog_blocks_view, cold, toilet_available (yes|no),
heater (present|absent), hot_water (good|poor).

[SERVICE] (15)
service_attitude (good|poor), service_quality (good|mixed|poor), value_for_money (good|poor),
tourist_trap (present|absent), wait_time (none|short|long), booking_needed (yes|no),
portion_size (generous|small), entry_fee (free|paid), vegetarian_options (yes|no), vegan_options (yes|no),
alcohol_required (yes|no), cash_only (present|absent), condition_change (declined),
scam_stage (parking|photo|tout|forced_purchase|menu_price|rental), breakfast (included|not_included).

[EFFORT] (8)
rough_road_access (present|absent), steep_or_stairs (present|absent), long_walk (present|absent),
car_access (yes|no), coach_access (yes|no), night_road_risk (present), rest_benches (present|absent),
stroller_access (yes|no).

[SUITABILITY] (6)
kids (suitable|unsuitable), elderly (suitable|unsuitable), wheelchair (suitable|unsuitable),
couples (suitable|unsuitable), groups (suitable|unsuitable), pets (allowed|not_allowed).

[OPERATION] (1)
visit_duration (under_1h|1_to_2h|half_day|full_day).
```

### 5.2 Điều kiện mở rộng (Special Conditions cho Hard Filters)
- `fit.<companion>`: `good`, `bad`, `conditional` (áp dụng cho: `solo`, `partner`, `friends`, `kids`, `baby`, `parents`, `pregnant`, `wheelchair`, `pet`, `coworkers`, `large_group`).
- `venue_category`: `bar`.
- `activity`: Mọi enum thuộc `Activity`.

---

## 6. Kiểm tra SearchInput và Các Điểm Chuyển Đổi Dễ Lỗi

`SearchInput` là hợp đồng công khai bàn giao sang Place Decision. Cần assertion đúng các quy tắc sau:

1. **Quy đổi Ngân sách (`budget_vnd` và `budget_intent`):**
   - `context.budget_intent`: Lưu cấu trúc gốc `{amount, currency: "VND", scope, scope_guessed, source, evidence...}`.
   - `context.budget_vnd`: Bắt buộc là **VND/người/ngày**.
     - `trip_total`: `amount / (days * people)`
     - `per_day`: `amount / people`
     - `per_person`: `amount / days`
     - `per_person_day`: `amount`
   - *Quy tắc an toàn:* Nếu thiếu `people` (và companions không phải solo=1 hay partner=2) hoặc thiếu `days` khi scope cần chia, thì `context.budget_vnd = null` và `"budget_vnd"` phải xuất hiện trong `unknowns`.
2. **Nguyên tắc Fail-closed trên Hard Filter:**
   - Mọi hard filter trong `SearchInput.hard_filters` đều phải có `unknown_policy` rõ ràng (`exclude` hoặc `flag`). Nếu Trip State chưa có, compiler mặc định gán `exclude`.
3. **Xe đoàn đông (`coach_access`):**
   - Nếu `mobility = "car"` và `people >= 9`, compiler tự thêm hard filter:
     `{"feature": "coach_access", "op": "ne", "value": "no", "unknown_policy": "exclude"}`.
4. **Anchors:**
   - Chỉ anchor có `state = "matched"` và có `place_id` hợp lệ mới xuất hiện trong `SearchInput.anchors`. Anchor chưa match hoặc missing không được chuyển thành ID giả định.
5. **Vibes:**
   - Chỉ các vibe có `status = "done"` mới được chuyển sang `SearchInput.vibes`.
6. **Mục Chưa rõ (`unknowns`):**
   - Chứa danh sách các trường chưa xác định trong số: `dates`, `days`, `nights`, `companions`, `base`, `mobility`, `purpose`, `pace`, `budget_vnd`.

---

## 7. Yêu cầu Nằm Ngoài Khả Năng (Out-of-Scope)

Khi sinh prompt ngẫu nhiên, cần có tập use case kiểm tra khả năng xử lý an toàn của hệ thống trước các yêu cầu chưa được hỗ trợ:

| Yêu cầu ngoại lệ | Giới hạn hệ thống hiện tại | Kỳ vọng hành vi của hệ thống |
|---|---|---|
| Gọi xe công nghệ (Grab, Taxi, xe buýt) | `mobility` chỉ hỗ trợ `motorbike`, `car`, `walk`. | Không tự ý chuyển thành `car`. Agent ghi vào `unmapped` hoặc hỏi làm rõ phương tiện di chuyển chính trong thành phố. |
| Chuyến đi nhiều thành phố / Tỉnh khác | Corpus hiện tại chỉ phục vụ Đà Lạt và vùng phụ cận. | Không bịa lịch trình liên tỉnh; thông báo rõ phạm vi hỗ trợ hiện tại của ứng dụng. |
| Giờ hẹn cố định tại điểm ("phải có mặt lúc 14:30") | `time_preferences` chỉ hỗ trợ buổi (`afternoon`), không hỗ trợ mốc phút tuyệt đối. | Không ép thành mốc giờ cứng; ghi nhận ưu tiên buổi và đưa ghi chú chi tiết vào `unmapped`. |
| Dị ứng thực phẩm nghiêm ngặt (đậu phộng, hải sản, gluten) | Dữ liệu Place Intelligence chưa có nhãn chứng nhận dị ứng y tế. | Không tạo bộ lọc ăn kiêng giả mạo; chỉ lưu ghi chú cảnh báo cho người dùng tự kiểm tra. |
| Lịch trình trên 30 ngày hoặc đoàn trên 20 người | Schema giới hạn `days` trong [1, 30], `people` trong [1, 20]. | Hệ thống từ chối cập nhật giá trị vượt ngưỡng (`ValueError`), không âm thầm cắt gọn số liệu. |
| Prompt Injection / Phá hoại / Hỏi thông tin thời gian thực | `input_guard` và Agent Guard kiểm soát đầu vào. | Regex chặn mẫu tấn công rõ ràng; phần còn lại Agent tự từ chối theo `CHAT_POLICY` và không gọi tool. |

---

## 8. Ma trận Sinh Hàng Ngàn Use Case Ngẫu Nhiên

Để chuẩn bị sinh vài ngàn prompt tự nhiên thuần túy cho Trip Understanding và Decision, ma trận sinh test case cần kết hợp có hệ thống các chiều không gian sau:

### 8.1 Các Chiều Biến Thiên Độc Lập

```text
1. Bối cảnh chuyến (Trip Context):
   - Thời lượng: 1 ngày (đi về trong ngày), 2N1Đ, 3N2Đ, 4N3Đ, 7 ngày, 14 ngày, biên 30 ngày, lỗi (0 ngày, 35 ngày).
   - Thời gian: Ngày ISO cụ thể, tháng tương lai, đầu/giữa/cuối tháng, từ tương đối ("cuối tuần này", "thứ 4 tuần sau").
   - Nhóm đi: Solo, cặp đôi, nhóm bạn (3-8 người), gia đình có trẻ em, gia đình 3 thế hệ (ông bà + cháu), thú cưng, đoàn công ty (10-20 người).
   - Di chuyển: Xe máy, ô tô tự lái, đi bộ, Grab/taxi (out-of-scope).
   - Ngân sách: Rõ ràng (kèm scope), mơ hồ không scope, ngân sách thấp (< 1tr), ngân sách cao (> 20tr), miễn phí/tiết kiệm.

2. Ràng buộc & Tín hiệu Sức khỏe (Safety Signals & Hard Constraints):
   - Thể chất: Đau gối/khớp, người cao tuổi, phụ nữ mang thai, người đi xe lăn, say xe, sợ độ cao.
   - Ăn kiêng: Thuần chay (vegan), ăn chay (vegetarian), kiêng rượu bia, dị ứng món.
   - Ràng buộc tổ hợp: Vừa có người già đau chân vừa có trẻ nhỏ hiếu động; nhóm ăn chay đi cùng người thích đặc sản thịt nướng.

3. Sở thích & Gu Không gian (Soft Tastes & Vibes):
   - Nhóm ưu tiên: Nature, Sights, Chill, Meal (đơn lẻ hoặc kết hợp đa nhóm).
   - Tính từ chủ quan: "Chill", "sống ảo", "hoang sơ", "ấm cúng", "yên tĩnh", "sang trọng".
   - Phong cách (Vibe): Retro, vintage, kiểu Hàn, phong cách Đà Lạt xưa.
   - Anchor thực tế: Chứa 1-3 link TikTok / tên quán thật trong corpus (Quán cà phê X, Chợ đêm, Đồi chè Cầu Đất...).

4. Hình thức Ngôn ngữ & Phong cách Prompt:
   - Ngắn gọn súc tích: "Đà Lạt 3N2Đ 2 người xe máy 5tr."
   - Kể chuyện dài nhiều chi tiết: Tả lịch trình mong muốn, giờ giấc, thói quen dậy muộn, thích ngắm hoàng hôn.
   - Tiếng Việt biến thể: Có dấu, không dấu ("di da lat 3 ngay voi bo me"), gõ vội sai chính tả nhẹ, tiếng lóng giới trẻ ("bồ tèo", "săn mây đỉnh chóp").
   - Câu phủ định & Đính chính: "Thích view đồi nhưng tuyệt đối không leo dốc", "Chuyến này không đi xe máy nữa, đổi sang ô tô".
```

### 8.2 Cấu trúc JSON Chuẩn cho Bộ Sinh Use Case

Mỗi case sinh ra được lưu theo định dạng JSON chuẩn sau đây để runner có thể tự động nạp và kiểm tra:

```json
{
  "id": "TC-SYNTH-2026-0042",
  "category": "safety_family_multigen",
  "priority": "P0",
  "raw_prompts": [
    "Tháng 12 này cả nhà mình đi Đà Lạt 4 ngày 3 đêm, tổng cộng 6 người gồm vợ chồng mình, bố mẹ già và 2 bé nhỏ. Đi lại bằng ô tô tự lái. Mẹ mình bị đau khớp gối nên tránh chỗ leo bậc thang dốc nhé. Cả nhà thích ngắm cảnh thiên nhiên, thong thả thôi."
  ],
  "clock": {
    "today": "2026-10-15",
    "timezone": "Asia/Ho_Chi_Minh"
  },
  "expected_extraction": {
    "month": 12,
    "days": 4,
    "nights": 3,
    "people": 6,
    "companions": ["partner", "parents", "kids"],
    "mobility": "car",
    "signals_triggered": ["knee", "elderly", "kids"],
    "hard_filters": [
      {
        "feature": "steep_or_stairs",
        "op": "ne",
        "value": "present",
        "unknown_policy": "exclude"
      }
    ],
    "liked_groups": ["nature"],
    "pace": "slow"
  },
  "expected_search_input": {
    "context": {
      "month": 12,
      "days": 4,
      "nights": 3,
      "people": 6,
      "mobility": "car"
    },
    "unknowns_contain": ["budget_vnd", "base"]
  },
  "safety_invariants": {
    "fail_closed_on_stairs": true,
    "no_unhandled_signals_on_show": true
  }
}
```

---

## 9. Phương Pháp Đo Lường & Đánh Giá Tự Động

Khi chạy kiểm thử trên tập vài ngàn use case:

1. **Độ chính xác Trích xuất (Slot Extraction Accuracy):**
   - Đo lường Precision, Recall và F1 trên từng trường dữ liệu: `days`, `month`, `people`, `companions`, `mobility`, `budget_vnd`, `budget_scope`.
   - **Exact Substring Match cho Evidence Quote:** Bất kỳ fact nào có source khác default đều phải có `quote` là chuỗi con chính xác trong văn bản người dùng nhập. Vi phạm quy tắc này bị tính là lỗi bịa đặt (Hallucination Fail).
2. **Độ an toàn Ràng buộc (Safety Invariant Rate):**
   - Tỷ lệ 100% đối với các use case P0: Không bao giờ cho phép signal sức khỏe bị bỏ quên; không nới lỏng hard filter thể chất; compile trực tiếp phải ném lỗi nếu chưa xử lý.
3. **Hiệu năng & Thời gian đáp ứng (Latency Benchmark):**
   - Lượt tiền xử lý tất định (Prepass): < 20 ms.
   - Clef Flash filter: < 500 ms.
   - Agent Loop (kèm model serving): Đo lường P50, P90, P99.

---

## 10. Bàn giao cho Planning & Bài toán Tổ hợp Địa điểm

### 10.1 Vấn đề Bùng nổ Tổ hợp ở bước Planning
- Place Decision tạo ra một tập shortlist ứng viên (24–60 địa điểm khả thi, được phân theo các tab `nature`, `sights`, `chill`, `meal`).
- Nếu một chuyến đi 3 ngày cần chọn khoảng 9–12 địa điểm để xếp lịch:
  - Số tổ hợp chập 12 của 60 địa điểm là:
    $$C_{60}^{12} \approx 1,4 \times 10^{12} \text{ (hơn 1.400 tỷ tổ hợp)}$$
- **Không thể chọn ngẫu nhiên tất cả các tổ hợp để kiểm thử Planning vì:**
  1. Đa phần các tổ hợp ngẫu nhiên là **phi lý về mặt thực tế** (ví dụ: chọn 10 quán cà phê không có điểm tham quan nào, hoặc chọn các điểm ở 4 góc đèo cách nhau hàng chục km).
  2. Các tổ hợp này sẽ vi phạm kiểm tra khả thi tổng thể (`decision.feasibility`), gây lãng phí tài nguyên tính toán ma trận OSRM và solver.
  3. Không phản ánh đúng hành vi người dùng thật và không đánh giá được chất lượng tối ưu của Planning.

### 10.2 Giải pháp: Bộ Hỗ trợ Tự động Hóa Tuyển chọn cho Planning (Automated Planning Test Harness)
Thay vì tổ hợp ngẫu nhiên mù quáng, hệ thống kiểm thử tự động áp dụng **Bộ tuyển chọn theo Archetype định hướng** (Automated Curation Archetypes) dựa trên chính module `decision.feasibility`:

```text
SEARCH INPUT (từ vài ngàn case Trip Understanding)
       │
       ▼
PLACE DECISION PIPELINE (Sàng lọc + Xếp hạng + Phân nhóm)
       │
       ▼
AUTOMATED CURATION HARNESS (6 Archetype Tuyển chọn Thông minh):
  ├── Archetype 1: Greedy Top-Ranked (Chuẩn mực theo gu)
  ├── Archetype 2: Feasibility-Guided Incremental (Bổ sung có kiểm soát độ khả thi)
  ├── Archetype 3: Cluster-Focused vs Cross-Cluster (Kiểm thử tải di chuyển)
  ├── Archetype 4: Time-Window & Operating Hours Stress (Kiểm thử giờ mở cửa/khung buổi)
  ├── Archetype 5: Capacity Overload (Cố tình quá tải để kiểm thử đề xuất cắt giảm)
  └── Archetype 6: Lodging Variations (Đã đặt trước / Chọn từ tab / Chưa có chỗ ở)
       │
       ▼
DECISION OUTPUT CHUẨN HOÁ
       │
       ▼
PLANNING SOLVER & VALIDATOR
  ├── Tạo 2-3 phương án lịch trình (variants)
  ├── Kiểm tra Timeline, OSRM Travel, Buffer, Giờ mở cửa (fail-closed)
  └── Đánh giá Độ vững (Robustness: solid | feasible | fragile) & Độ giảm di chuyển vs Baseline
```

*(Chi tiết kiến trúc và kế hoạch triển khai bộ hỗ trợ tự động này được trình bày cụ thể trong tài liệu kế hoạch kiểm thử hệ thống).*

---

## 11. Hướng Dẫn Giao Việc cho Agent Sinh Test Case

Khi kích hoạt subagent hoặc script sinh hàng ngàn use case:

> **Chỉ thị:** Đọc kỹ `RULE.md`, `docs/TRIP_UNDERSTANDING.md` và `docs/TRIP_UNDERSTANDING_QA.md`.
> Sinh tập dữ liệu use case thuần túy dạng văn bản tự nhiên của người dùng (User Prompts).
> 1. Đảm bảo bao phủ toàn diện: Bối cảnh chuyến (ngày, người đi, xe cộ, tiền bạc), 71 features ontology v12, tín hiệu an toàn thể chất/ăn kiêng, câu phủ định, từ lóng, prompt injection và yêu cầu out-of-scope.
> 2. Định dạng đầu ra: JSON theo đúng cấu trúc ở §8.2.
> 3. Tuyệt đối không tự bịa đặt ID địa điểm hay tọa độ ngoài corpus; không đưa JSON cấu trúc vào lời thoại giả lập.
> 4. Ghi rõ nhãn kỳ vọng trích xuất (expected slots) và các invariant an toàn để pipeline QA tự động chấm điểm.
