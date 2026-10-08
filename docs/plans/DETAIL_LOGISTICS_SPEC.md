# Spec — Xem chi tiết, hiện hết gợi ý, hỏi hậu cần

File làm việc tạm (RULE §0.1): khi làm xong, gộp phần còn giá trị vào tài liệu chính thức ghi ở §6 rồi xóa file này.
Người dùng duyệt từng phần trong chat ngày 2026-10-08.

## 0. Mục tiêu

| # | Người dùng nói | Xong khi |
|---|---|---|
| A | "Xem chi tiết" hiện như video `20261008-0352-34.7778994.mp4`, bố cục y chang; gallery nhiều ảnh hơn, chọn ảnh đẹp nhất; animation mở tối ưu UX | Bấm "Xem chi tiết" ở đĩa xoay **và** ở lưới mở cùng một modal theo bố cục video (khối ảnh giữ như đĩa xoay hiện tại); tab Hình ảnh hiện ~12 ảnh/nơi do Gemma chọn |
| B | Gợi ý hiện quá ít; hiện hết cho người dùng chọn, rồi họ chat để thu hẹp | Explore hiện mọi nơi qua giới hạn cứng, nhóm đầu có nhãn "Hợp nhất" |
| C | Sau phase chat hỏi điểm xuất phát (tìm như Google Maps), phương tiện (xe khách / máy bay → đề xuất chuyến để chốt hoặc bỏ qua), khách sạn | Ba câu hỏi chạy trong Understand; chuyến đã chốt điền giờ đến / giờ về; khách sạn đã chọn là mốc khi xếp lịch |
| C' | Gợi ý khách sạn theo vibe người dùng thích (Trip Understanding); điểm ưa thích nặng hơn điểm vị trí; khâu chậm chuyển offline | Thứ tự khách sạn do mức hợp gu quyết định trước, vị trí sau; mỗi thẻ nói "hợp vì …" kèm bằng chứng |

Bất biến giữ nguyên (`AGENTS.md`): không bịa (chuyến, giá chỉ từ nguồn crawl, có `source` + `fetched_at`; khách sạn chỉ từ corpus); không có bằng chứng → `unknown`; online không ghi Place Intelligence; mỗi nguồn ngoài một module + một thư mục dữ liệu; gọi model theo vai trò.

## 1. A — Modal "Xem chi tiết"

### 1.1 Bố cục (theo video)

Một component `PlaceSheet` (`web/src/user/ui/PlaceSheet.tsx`), mở dạng modal phủ màn hiện tại; nền mờ. Dùng ở:
đĩa xoay (`DiscPicker.tsx`), lưới (`PlaceCard.tsx`), và trang `/explore/place/:id` (link chia sẻ; trang chỉ bọc `PlaceSheet` ở chế độ không modal).

```text
┌ ‹ Quay lại gợi ý địa điểm ─────────────────────────────── ✕ ┐
│ ── NHÀ HÀNG · PHƯỜNG 9               ┌─────────────┐┌────┐ │
│ Lẩu bò Ba Toa                        │             ││ ảnh│ │  ← khối ảnh như đĩa xoay hiện tại
│ "Giờ cao điểm phải chờ gần 30 phút." │  ảnh lớn    │├────┤ │    (`tg-disc__big` + 3 ảnh nhỏ):
│ Trích từ đánh giá của người đã đến   │  (ảnh bìa)  ││ ảnh│ │    bấm ảnh nhỏ thì đổi ảnh lớn
│ Đồ ăn: tốt · Khẩu phần: nhiều        │             │├────┤ │  ← 2–3 feature VERIFIED nổi nhất (labels.ts)
│                                      └─────────────┘│ ảnh│ │
│                                                     └────┘ │
│ Đánh giá | Giờ mở cửa hôm nay | Thời gian tham quan          │
│ [Thêm vào hành trình →]   ♡                                  │
│ Tổng quan  Hình ảnh  Gợi ý lịch trình  Đánh giá   (dính đầu) │
│ …nội dung tab…                                               │
└──────────────────────────────────────────────────────────────┘
```

| Tab | Nội dung (lấy từ `PlaceDetail.tsx` hiện tại, không bỏ phần nào) |
|---|---|
| Tổng quan | bảng: đánh giá, giờ mở hôm nay, thời gian tham quan, giá, địa chỉ, khoảng cách, nguồn (số người viết + ngày dữ liệu); dải 4 ảnh nhỏ; bản đồ nhỏ + "Mở trên Google Maps"; vì sao hợp / đánh đổi kèm bằng chứng |
| Hình ảnh | **danh sách cuộn hiện hết ảnh** của nơi (≤ 12), mỗi ảnh ghi nguồn. Không lightbox, không hiệu ứng |
| Gợi ý lịch trình | giờ mở theo ngày, nên dành bao lâu, giá, độ đông theo buổi (ngày thường / cuối tuần), ghi chú "ước tính" |
| Đánh giá | điểm + số lượt Google, trích dẫn kèm ngày, clip TikTok, "Báo thông tin sai" |

Nút: "Thêm vào hành trình" = `act({type:'select'})`; đã chọn → "Đã trong hành trình" (bấm mở `DropSheet`); khóa / so sánh nằm trong menu `⋯` như đĩa xoay. Esc / ✕ / "Quay lại" đóng modal và trả focus về nút đã mở nó. URL đổi sang `?place=<id>` (Back của trình duyệt đóng modal).

### 1.2 Animation

- Mở: shared-element — ảnh lớn đang hiện (đĩa) hoặc ảnh thẻ (lưới) bay vào chỗ ảnh lớn của modal (View Transitions API; trình duyệt không hỗ trợ → FLIP bằng `getBoundingClientRect` + Web Animations). Ba ảnh nhỏ fade-in lệch nhau 40 ms; chữ fade-up. Tổng ~380 ms, easing `cubic-bezier(.2,.8,.2,1)`.
- Đóng: ngược lại, ảnh về đúng chỗ cũ.
- `prefers-reduced-motion` → chỉ fade 150 ms.
- Màu, font, bo góc chỉ dùng token có sẵn (`css/tokens.css`).

### 1.3 Ảnh: 12 ảnh / nơi, Gemma chọn ảnh đẹp

`web/scripts/pick_covers.py`:

1. Ứng viên như hiện tại (ảnh Maps + khung hình clip TikTok), lọc người bằng YOLO như hiện tại.
2. Bỏ ảnh gần trùng bằng pHash (khoảng cách Hamming ≤ 8), giữ ảnh nét hơn.
3. Tối đa 16 ứng viên / nơi → một lời gọi task mới `photo_rank` (`src/corpus/llm/tasks.py`, role `EXTRACTOR` = Gemma, cùng cách đính ảnh như `photo_observe`). Model trả cho mỗi ảnh `beauty` 1–10 (bố cục, ánh sáng, độ nét) và `shows_place` 1–10 (ảnh cho thấy nơi đó là gì). Output validate bằng schema; ảnh model không chấm → giữ điểm heuristic cũ.
4. Điểm = `beauty + shows_place` + điểm heuristic cũ (Maps ưu tiên, độ nét) làm tie-break. `KEEP = 12`. Ảnh đầu là ảnh bìa (ảnh lớn của modal).
5. `covers.json` giữ cấu trúc cũ (mảng ảnh mỗi nơi), dài hơn. Nếu > 3 MB: tách `covers/<id>.json`, `covers.json` chỉ giữ ảnh bìa, modal tải phần còn lại khi mở.

Vận hành (người dùng xác nhận 2026-10-08, ghi ở `docs/plans/SESSION_TIKTOK.md`): khi chạy `photo_rank` thì tạm dừng `logs/tiktok_lan_uit_lane.sh`, xong thì chạy lại.

## 2. B — Hiện hết gợi ý

- `src/decision/diversify.py` `pick`: trả **mọi** ứng viên qua hard filter và `min_context_fit`, sắp theo MMR cho phần đầu (cỡ cũ `k`) rồi theo `score` cho phần còn lại. Nơi gần trùng vẫn có `alternatives` nhưng **cũng nằm trong danh sách**.
- Mỗi card thêm `top: bool` (true với `k` nơi đầu — cỡ shortlist cũ). Schema `src/decision` + `web/src/user/pd/types.ts`.
- Web: header Explore "N nơi hợp với chuyến của bạn · chat để thu hẹp" (mở Assistant); badge "Hợp nhất" cho `top`; lưới hiện 24 nơi, cuộn tới đâu hiện thêm tới đó; đĩa xoay giữ nguyên (đã chỉ vẽ ±6 nan).
- Feasibility (`infeasible_ratio`, nhắc chọn quá nhiều) không đổi: tính trên nơi **đã chọn**, không trên số nơi được hiện.

## 3. C — Hỏi hậu cần sau phase chat

Thứ tự trong Understand, sau khi chat xong và trước `ready`: **xuất phát → phương tiện → chuyến (nếu xe khách / máy bay) → đã có chỗ ở chưa**. Bốn câu là câu hỏi của `src/trip/domain/questions.py`, nên lưu vào Trip State, có "Bỏ qua", và đi qua harness như mọi câu khác. Chúng thay `entry_exit` / `times` khi đã có câu trả lời.

### 3.1 Điểm xuất phát — `origin`

- Câu hỏi `origin`, `input="geo"`: "Bạn khởi hành từ đâu?". Ô gõ có gợi ý giống Google Maps (debounce 300 ms, ↑/↓/Enter, mỗi dòng: tên · địa chỉ · tỉnh).
- Nguồn: `live.geosearch(text, limit=6)` mới trong `src/live/geocode/` — Photon (OSM, làm cho autocomplete), lỗi → Nominatim. Cache 30 ngày ở `data/live/geocode/`. Harness: `GET /api/harness/geo?q=`.
- Trip State: field mới `origin: Base` (text, lat, lng, province).

### 3.2 Phương tiện — `arrival_mode`

- Chips: **Tự đi (xe máy / ô tô)** · **Xe khách** · **Máy bay**. Field mới `arrival_mode`.
- Tự đi → `entry_point` / `exit_point` suy từ hướng `origin` tới Đà Lạt theo bảng tĩnh `config/trip.yaml` `entry_roads` (ví dụ phía TP.HCM → đèo Prenn; phía Nha Trang → đèo Khánh Lê); câu `times` hỏi như cũ.
- Máy bay → sân bay gần `origin` nhất từ `config/airports.yaml` (mã IATA + tọa độ, bảng tĩnh). Đích luôn `DLI`.

### 3.3 Đề xuất chuyến — chạy trước offline, live chỉ khi thiếu

- Module mới, mỗi nguồn riêng (RULE §2): `src/live/flights/` (Google Flights, cache `data/live/flights/`), `src/live/buses/` (Vexere, cache `data/live/vexere/`). Public API: `live.flights(origin_iata, dest_iata, date)`, `live.buses(origin_province, date)`. Playwright qua `corpus.crawl.open_sessions`, giống `live.lodging`.
- **Chạy trước mỗi ngày** (người dùng chọn 2026-10-08): `scripts/prewarm_transit.py` (cron 1 lần/ngày) gọi đúng hai hàm trên cho danh sách cố định trong `config/live.yaml` `transit_prewarm`: chuyến bay = các tuyến bay thẳng tới / từ `DLI` (~10 sân bay) × 30 ngày tới × 2 chiều; xe khách = ~25 tỉnh / thành hay đi Đà Lạt × 14 ngày tới × 2 chiều. Kết quả nằm trong cache của chính module (TTL 26 giờ), không phải dữ liệu riêng.
- Online: đọc cache → hiện ngay. Cache thiếu tuyến / ngày đó → crawl live nền, đẩy qua SSE (cùng kiểu luồng lodging), web hiện skeleton.
- Mỗi chuyến: `carrier`, `depart_at`, `arrive_at`, `from_point`, `to_point` (tên + địa chỉ điểm đón / trả), `price_vnd | None`, `source`, `fetched_at`. Hiện "giá tham khảo lúc HH:mm dd/mm, kiểm lại khi đặt".
- Câu hỏi `inbound` (chuyến tới Đà Lạt, ngày đầu) rồi `outbound` (chuyến về, ngày cuối), `input="transit"`. Lọc nhanh Sáng / Chiều / Đêm / Rẻ nhất. Mỗi chuyến có "Chọn chuyến này"; cuối danh sách "Tôi tự lo phần này" (= bỏ qua).
- Chọn chuyến → `arrive_at` = giờ đến (+ đệm `arrival_buffer_min` trong config), `leave_at` = giờ đi chuyến về − đệm; `entry_point` / `exit_point` = điểm trả / đón của chuyến (Planning geocode). Câu `times` không hỏi nữa.
- Chưa có `start_date` (mới biết tháng) → hỏi ngày trước; không ngày thì không tra chuyến.
- Cache thiếu và crawl live lỗi / captcha / rỗng: không hiện chuyến nào; hiện nút mở Google Flights / Vexere đã điền sẵn điểm đi, đích, ngày, và hai ô nhập tay giờ đến / giờ về.

### 3.4 Chỗ ở — `lodging_booked`

Câu hỏi "Bạn đã đặt chỗ ở chưa?" ngay sau phương tiện (hoặc chuyến). Field mới `lodging_booked`.

| Trả lời | Làm gì |
|---|---|
| Đã đặt | ô `geosearch` như §3.1 (thêm gợi ý từ các chỗ ở trong corpus §4) → chọn đúng chỗ → `lodging_point` của Planning (`set_lodging` / `pick_lodging`) |
| Chưa đặt | khi bấm "Xếp lịch" hiện màn chọn khách sạn (§4.3) trước khi lịch hiện ra |
| Bỏ qua | không chỗ ở; mốc = `entry_point` như hiện tại |

## 4. C' — Khách sạn theo gu, dữ liệu offline

Người dùng chọn 2026-10-08: khách sạn vào corpus, online chỉ đọc. Thẻ crawl live (`name, rating, reviews, price_vnd, amenities`) không đủ để biết hợp gu, và crawl + đọc đánh giá online mất vài phút.

### 4.1 Corpus: nhóm `stay`

- **Phạm vi** (`docs/CORPUS.md` §Phạm vi đổi): corpus có chỗ ở, nhóm `stay`. Explore / Place Decision không gợi ý nhóm này; chỉ Planning đọc.
- **Danh sách** (session GMAPS): khối `stay:` mới trong `config/queries.yaml` — truy vấn "khách sạn", "homestay", "villa", "resort", "nhà nghỉ" ghép theo từng phường / khu của Đà Lạt (danh sách khách sạn của Maps bỏ qua khung bản đồ, nên chia theo tên khu chứ không theo ô lưới), `min_reviews` 30. `gmaps list` ghi chỗ ở vào `list/<city>_stay.json` thay vì bỏ đi. 177 chỗ ở đã thấy trong `search/` hiện có được dùng luôn.
- **Chi tiết, đánh giá, ảnh**: pipeline gmaps hiện có, không đổi code crawl.
- **Observe** (session MODEL, Gemma): task observe hiện có, cùng ontology; `config/ontology.yaml` đánh dấu feature áp dụng cho `stay`: `noise`, `scenic_view`, `cozy_decor`, `cleanliness`, `service_attitude`, `value_for_money`, `parking`, `steep_or_stairs`, `nature`, `couples` / `kids` / `elderly` / `groups` `=suitable`. Không có trích dẫn → `unknown`.
- Aggregate / serving như mọi nơi; `pick_covers.py` (§1.3) chạy cho cả `stay`.

### 4.2 Xếp hạng (Planning, online, chỉ đọc)

```text
lodging_score = w_pref·pref_fit + w_loc·loc_fit + w_price·price_fit + w_rating·rating_fit
w_pref > w_loc   (config/planning.yaml lodging_weights; khởi điểm pref 2.0, loc 0.8, price 0.5, rating 0.3)
```

- `pref_fit`: soft của Trip State (`love` +1, `avoid` −1) khớp feature `VERIFIED` của chỗ ở, chia cho số soft; `unknown` đóng góp 0, không âm — cùng quy tắc `PLACE_DECISION.md` §8. Đi cùng `kids` / `elderly` / `partner` cộng `<who>=suitable`.
- Hard filter (ví dụ tránh dốc / bậc thang): có bằng chứng chống → loại; `unknown` → giữ, gắn "chưa xác minh: …" (như `planning/lodging.py` `sieve` hiện tại).
- `loc_fit`: số phút trung bình tới các nơi đã chọn (ma trận `travel_matrix` sẵn có, chỉ cho top theo `pref_fit` để ma trận nhỏ).
- `price_fit`: theo `price_cap` sẵn có, dùng giá tham khảo trong corpus; không giá → 0, không loại.
- `planning/lodging.py` `candidates` đọc chỗ ở từ serving thay cho `lodging_near`. `live.lodging_near` chỉ còn **cập nhật giá đúng ngày** cho 5 thẻ đầu, chạy nền, không chặn màn; về rồi thì thay giá trên thẻ ("giá ngày dd/mm lúc HH:mm").

### 4.3 Màn chọn

- Màn "Bạn ở đâu?" (bước toàn màn trước khi lịch hiện ra, `web/src/user/screens/Lodging.tsx`): thẻ gồm ảnh, tên, điểm, giá/đêm hoặc "chưa có giá", **"Hợp vì: yên tĩnh (6 đánh giá nhắc) · view đồi"** kèm trích dẫn, số phút trung bình tới các nơi đã chọn. Thẻ đầu: "Hợp gu bạn nhất". Bấm thẻ mở `PlaceSheet` (§1) của chỗ ở. Hành động: chọn (`pick_lodging`) · "Tôi ở chỗ khác" (`geosearch` → `set_lodging`) · "Cứ xếp giúp" (Planning tự chọn như hiện tại) · "Bỏ qua".
- Ô chỗ ở bên hông màn Plan giữ nguyên để đổi sau.

## 5. Kiểm thử

| Phần | Test |
|---|---|
| A | `pick_covers.py` trên 3 nơi (dry run, in thứ hạng); `shots_app.mjs` mở modal từ đĩa và từ lưới, chụp từng tab |
| B | `src/decision`: số card = số ứng viên qua lọc; `top` đúng `k` nơi đầu; nơi gần trùng có mặt; nhóm `stay` không bao giờ vào Explore |
| C | `src/trip`: chuỗi `origin → arrival_mode → inbound/outbound → lodging_booked`; chọn chuyến điền `arrive_at`/`leave_at` và bỏ câu `times`; "Tự đi" suy `entry_point` |
| C live | parser Google Flights / Vexere chạy trên HTML mẫu lưu trong `tests/fixtures/`; cache có → không mở trình duyệt; lỗi crawl → `Unavailable`, không trả chuyến giả; `src/live` không có đường ghi tới `data/intel`, `data/serving`, `data/gmaps` |
| C' corpus | `gmaps list` giữ chỗ ở vào `<city>_stay.json`, nơi tham quan không lẫn vào; feature ngoài tập `stay` không được ghi cho chỗ ở |
| C' planning | chỗ ở hợp gu xếp trên chỗ ở gần hơn nhưng không hợp; `unknown` không bị trừ điểm; hard filter có bằng chứng chống thì loại; giá live về muộn không đổi thứ hạng đã hiện trừ khi vượt trần |
| Toàn luồng | `web/scripts/test_journey.mjs` thêm một chuyến: chat → xuất phát → máy bay → chọn chuyến → chưa đặt chỗ ở → chọn nơi → chọn khách sạn → lịch |

## 6. Tài liệu chính thức cần sửa khi xong

`docs/PLACE_DECISION.md` §9.2 (bỏ cắt shortlist, thêm `top`) · `docs/TRIP_UNDERSTANDING.md` (4 câu hỏi, field `origin`, `arrival_mode`, `lodging_booked`) · `docs/PLANNING.md` §Live Context (`geosearch`, `flights`, `buses`, chạy trước) và ⓐ (chỗ ở đọc từ corpus, xếp hạng §4.2) · `docs/CORPUS.md` §Phạm vi + Phase 1 (nhóm `stay`) · `docs/LLM_PROVIDER.md` (task `photo_rank`) · `docs/Role_Web_Functional_Design.md` §6 (`PlaceSheet`, `Lodging.tsx`) · `docs/AGENT_HARNESS.md` (`/geo`, SSE chuyến) · `README.md` (cron `prewarm_transit.py`) · `docs/log/DEV_LOG.md`.

## 7. Thứ tự làm

1. **B** (nhỏ, độc lập) → 2. **A** web (modal, animation) → 3. **C'** corpus `stay`: thêm query + `list` (bàn giao session GMAPS crawl, session MODEL observe — chạy song song với các bước sau) → 4. **A** ảnh (`photo_rank`, dừng luồng TikTok khi chạy) → 5. **C** `origin` + `arrival_mode` + `geosearch` → 6. **C** chuyến (module live + `prewarm_transit.py`) → 7. **C'** xếp hạng + màn chọn (khi corpus đã có `stay`).
