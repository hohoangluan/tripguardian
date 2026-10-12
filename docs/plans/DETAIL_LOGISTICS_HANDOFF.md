# Bàn giao — phần còn lại của DETAIL_LOGISTICS_SPEC

File làm việc tạm (RULE §0.1). Spec gốc đã gộp vào tài liệu chính thức và xóa (`TRIP_UNDERSTANDING.md` §Hậu cần, `PLANNING.md` ⓐ + Live Context, `PLACE_DECISION.md` §9, `CORPUS.md` §Phạm vi, `Role_Web_Functional_Design.md` §6, `UI_SPEC_USER_WEB.md`). **Còn giữ file này chỉ vì lỗi chặn ở "WEB báo lại cho BE" (§2)**: BE sửa xong, chạy lại walk §3.6, rồi xóa file. Bàn giao 2026-10-08 tối, chia cho **hai session chạy song song**:

- **Session BE** (backend): §2 dưới — chuyến bay / xe khách, endpoint harness, chỗ ở theo gu ở Planning.
- **Session WEB** (web + tài liệu): §3 dưới — thẻ hỏi hậu cần, màn "Bạn ở đâu?", hoàn tất ảnh, kiểm thử toàn luồng, gộp tài liệu.

Hai session gặp nhau ở **§1 Hợp đồng**: làm đúng hình dạng đó thì không phải chờ nhau (WEB giả lập API bằng dữ liệu mẫu cho tới khi BE xong).

## 0. Đọc trước khi làm

- **Working tree dùng chung, đang lẫn việc của nhiều session.** `web/src/user/` mới (Shell, Account, css/*, …) phần lớn **chưa được track**; index có sẵn nhiều mục staged lạ (xóa 50 file cũ). **Không commit** trừ khi người dùng bảo; nếu được bảo, chỉ commit file của mình bằng index tạm (`GIT_INDEX_FILE`), không `git add -A`, không `git commit -a`.
- Không chạy lại / đè: `web/public/data/covers.json` (vừa build xong), `data/live/`, `data/gmaps/`.
- Test gmaps dùng trình duyệt (`tests/crawl/gmaps/test_gmaps_{crawl,page,search}.py`) fail sẵn vì máy thiếu `chromium_headless_shell` — không liên quan. `tests/crawl/gmaps/test_gmaps_gate.py` (của session khác) trùng tên với `tests/observe/gmaps/test_gmaps_gate.py`: chạy hai thư mục riêng.
- Chromium dùng để chụp màn hình (`.cache/ms-playwright/chromium-1169`) **không có H.264**: trình phát TikTok báo "Player error" chỉ trong môi trường test; Chrome/Edge/Safari thật phát được.
- Vite dev phụ đang chạy ở cổng **5174** (proxy tới harness 8769 đang phục vụ prod) — dùng để xem, không sửa `web/dist`.
- `landing/` đang có session khác sửa: `tsc` báo lỗi ở `src/user/landing/*` là của họ.

### Đã xong (chưa commit) — đừng làm lại

| Phần | Ở đâu | Kiểm chứng |
|---|---|---|
| B (danh sách đầy đủ, lọc ít xáo trộn) | đã commit trước đó (`6ca7ad3`…`b5665f1`) | `tests/decision` |
| A modal "Xem chi tiết" | `web/src/user/ui/PlaceSheet.tsx`, `css/sheet.css`; mở từ đĩa, lưới, anchor, Assistant, SelectedBar; `?place=<id>`, Back / Esc đóng; View Transitions + FLIP; `screens/PlaceDetail.tsx` bọc sheet ở chế độ trang | `web/scripts/shots_sheet.mjs <base> <journey>` |
| A clip TikTok | trong tab Đánh giá: hover 280 ms phát xem trước (tắt tiếng, player nhúng chính thức `tiktok.com/player/v1`), bấm mở trình xem dọc kiểu TikTok (↑ ↓, Esc) | như trên, tab Đánh giá |
| A ảnh 12/nơi | task `PHOTO_RANK` (`src/corpus/llm/tasks.py`), `web/scripts/pick_covers.py` (YOLO + pHash + Gemma). Đã chạy hết: 1.704 nơi có gallery, 1.671 nơi Gemma chấm, 0 lỗi, `covers.json` 2,87 MB (không tách). Web đọc được bản tách (`useGallery` trong `data/store.ts`) | log `logs/pick_covers.log`; cache `.cache/photo_rank.json` |
| Yêu cầu UI giữa chừng | bước "Tìm hiểu / Lựa chọn / Lịch trình / Đánh giá", bấm sang bước sau được (`FlowBar onAhead`), nút "Vé chuyến" dạng pill màu sun, đĩa xoay to hơn + nhãn đứng thẳng | xem 5174 |
| C' corpus `stay` | `config/queries.yaml` khối `stay:`, phase `gmaps stay_search`, `listing.build_stay` → `list/<city>_stay.json`, nhóm `stay` (`category_defaults.yaml`, `usable_as: []`), `stay_features` (`ontology.yaml`) lọc ở aggregate, Place Decision loại nhóm `stay` kể cả khi được nêu tên, observe / qc đọc cả hai danh sách (`files.listed`). Crawl + observe đã bàn giao ở `SESSION_GMAPS.md` / `SESSION_MODEL.md` mục ▶ Chỗ ở | `tests/crawl/gmaps/test_gmaps_listing.py`, `tests/aggregate`, `tests/decision` |
| C câu hỏi hậu cần (backend trip) | `src/trip/domain/logistics.py` (origin → arrival_mode → inbound / outbound → lodging_booked, tier 0, chèn trước `ready` qua `policy.before_ready`), field mới trong `state.py` (`origin`, `arrival_mode`, `inbound`, `outbound`, `lodging_booked`, `lodging`; `Base` có `lat/lng/province/kind`; model `Transit`), `Context` của Search Input mang đủ các field đó; `config/trip.yaml` (`arrival_buffer_min`, `entry_roads`), `config/airports.yaml` | `tests/trip/test_logistics.py` (184 test trip pass) |
| C `live.geosearch` | `src/live/geocode/photon.py` (Photon → Nominatim, cache `data/live/geocode/`) | `tests/live/test_geosearch.py` |
| Dữ liệu cho chuyến | bảng mã Vexere 27 tỉnh trong `config/live.yaml` (`vexere_regions`, đọc vào `live.Settings`); fixture cắt gọn `tests/fixtures/live/flights_sgn_dli_20261112.html`, `vexere_hcm_dalat_20261112.html` | — |

## 1. Hợp đồng giữa hai session

**Thẻ câu hỏi** (đã có, `trip.domain.questions.Question` → `card()`): `input` ∈ `geo | transit | lodging`; `params` chỉ có ở transit: `{mode: "plane"|"bus", from, to, date: "YYYY-MM-DD"}` (`from`/`to` là IATA khi bay, tên tỉnh / "Lâm Đồng" khi xe khách). `exits: true` = nút "Bỏ qua" (với transit hiện là "Tôi tự lo phần này"). Trả lời qua harness như mọi thẻ: `{kind: "answer", qid, value}` với `value` là **chuỗi JSON**:

| qid | value |
|---|---|
| `origin` | `{"text", "lat", "lng", "province"}` (một dòng của `/geo`) |
| `arrival_mode` | chip `self` / `bus` / `plane` (không có value) |
| `inbound`, `outbound` | một `Transit` nguyên vẹn từ `/transit`, **hoặc** `{"time": "HH:MM"}` khi người dùng nhập tay |
| `lodging_booked` | chip `suggest` (= `lodging_booked: no`), **hoặc** value `{"kind": "corpus"|"live"|"address", "id"?, "text", "lat", "lng"}` (một dòng của `/lodging/suggest`) → `lodging_booked: yes`, `lodging` = `base` = điểm đó |

`Transit` (`src/trip/domain/state.py`): `{mode, carrier, depart_at, arrive_at ("YYYY-MM-DDTHH:MM" giờ VN), from_point, to_point, price_vnd|null, source, fetched_at}`.

**Endpoint harness mới** (BE làm, WEB gọi; GET, không cần journey):

| Đường | Trả |
|---|---|
| `/api/harness/geo?q=` | `[{text, address, province, lat, lng, source, fetched_at}]` ≤ 6 (`live.geosearch`) |
| `/api/harness/lodging/suggest?q=` | ≤ 6 dòng `{kind, id?, text, address, rating?, lat, lng}`: chỗ ở của mình trước (serving nhóm `stay`, rồi thẻ live đã crawl trong `data/live/lodging/`, tra tên tại chỗ), rồi địa chỉ từ `geosearch`; nguồn tìm lỗi → vẫn trả phần của mình |
| `/api/harness/transit?mode=&from=&to=&date=` | `{status: "ready"|"pending"|"unavailable", trips: [Transit], book_url}`; `book_url` = Google Flights / Vexere đã điền điểm đi, đích, ngày (dùng khi `unavailable` hoặc rỗng) |
| `/api/harness/transit/events?…` (SSE) | cùng tham số; khi `pending` đẩy một event `{status, trips, book_url}` lúc crawl live xong (giống luồng `planning/lodging/events`) |

**Ticket** (WEB): các dòng trip mới có `target` = `origin`, `arrival_mode`, `inbound`, `outbound`, `lodging_booked`, `lodging` (đã có trong `understanding.TRIP_ROWS`); sửa / xóa qua `{kind: "edit", target, value|null}` như mọi dòng.

**Planning** đọc `decision_output.trip_context.context.{lodging_booked, lodging, inbound, outbound}` (đã có trong Search Input).

**Thẻ chỗ ở** (WEB đã đọc, `web/src/user/planning/types.ts` `LodgingCandidate`; BE §2.6 thêm vào `view.lodging.candidates[]` và event `progress`, mọi trường mới đều tùy chọn): `{id, name, price_vnd, source: "corpus"|"live", rating, reviews, fit: [{text, mentions, quote|null}], unverified: [text], avg_min}`. `fit` rỗng + `source: "live"` → web ghi "chưa đủ dữ liệu để so gu"; thẻ đầu chỉ mang nhãn "Hợp gu bạn nhất" khi `fit` không rỗng. Màn "Bạn ở đâu?" dùng `pick_lodging` / `set_lodging {text}` / `clear_lodging` sẵn có.

## 2. Session BE

> **▶ Làm tiếp từ đây (2026-10-08 23:50, session BE nghỉ; người dùng giao lại sau):**
> 1. **Đang chạy, không cần làm gì trừ theo dõi:** crawl Google Maps cho chỗ ở `dalat_stay` (8 runner, 64 tab, 300 review mới nhất/chỗ ở, ~11,5 chỗ ở/phút, phase `crawl` xong ~01:45 rồi tự chạy relevant → extremes → photos → keywords). Cách theo dõi, captcha, khởi động lại: `SESSION_GMAPS.md` ▶ Chỗ ở §Theo dõi / làm tiếp. Captcha → người dùng giải ở DevTools 9530 / 9533.
> 2. **Sau khi crawl chỗ ở xong:** ghi một dòng vào `CORPUS_HANDOFF.md` §▶▶ cho SESSION_MODEL observe nhóm `stay` → aggregate → `python -m corpus serving`. Serving có ≥ `stay_min` (50) chỗ ở trong vùng tìm thì Planning tự chuyển từ crawl live sang corpus (`planning/lodging.py candidates`), không cần sửa code; khởi động lại harness để nạp serving mới.
> 3. **Lỗi BE còn mở (WEB báo, xem khối "WEB báo lại cho BE" dưới):** (a) ~~có `entry_point` là Planning trả `no_valid_variant`~~ — **đã sửa 2026-10-09** (`planning/build.py` `prepare`: chưa có nơi ở thì các ngày sau không còn lấy `entry_point` làm nhà; sân bay / bến xe chỉ mở ngày đầu; test `test_the_entry_point_only_opens_day_one…`). Còn lại: có nơi ở trong thành phố mà địa điểm ghim giờ (mây / hoàng hôn) vẫn quá chật 5 phút ở session `4d82f382c4d6` — ca dữ liệu chật, không phải lỗi `entry_point`; (b) `/geo`, `/lodging/suggest` chưa ưu tiên vùng (Photon `lat`/`lon` + `bbox`).
> 4. **Chưa cài cron** `15 3 * * * cd <repo> && ./run.sh prewarm >> logs/prewarm_transit.log 2>&1` (crontab của `luanhh` đang trống; cache chuyến chỉ sống 26 giờ). Hỏi người dùng trước khi cài.
> 5. Prod harness :8769 đã được khởi động lại lúc 23:00 (riêng harness, không build `web/dist`) để có endpoint mới + biến trình duyệt. Lần sau thử trên harness dev cổng riêng trước.

> **Xong 2026-10-08 (chưa commit).** 955 test pass (`tests/live tests/planning tests/harness tests/decision tests/trip`); kiểm đầu-cuối qua HTTP với `planning.Tools` thật: `/transit` bay SGN→DLI `pending` → SSE `ready` sau ~18 s (5 chuyến), lần sau `ready` từ cache; xe khách ~1,5 s. Code: `src/live/{flights,buses}/`, `live.lodging_seen`, `src/planning/logistics.py`, `planning/lodging.py` (`booked`, `rank`, `refresh_prices`), `engine.py`, `harness/{server,dispatch}.py`, `scripts/prewarm_transit.py`. Tài liệu đã gộp (WEB **không** làm lại ở §3.7): `PLANNING.md` (ranh giới, Live Context + §Chuyến xe khách, chuyến bay, ⓐ, cấu hình), `AGENT_HARNESS.md` §4, `README.md` (cron).
>
> **Bổ sung hợp đồng cho WEB:**
> - Thẻ `inbound` / `outbound` xe khách có thêm `params.lat`, `params.lng` (điểm xuất phát) khi có: gửi kèm vào `/transit` và `/transit/events` (chọn tỉnh Vexere theo khoảng cách; tên tỉnh sau sáp nhập 2025 không khớp bảng của Vexere). `tu/api.ts` `transitQuery` hiện bỏ hai trường này.
> - View Planning: `lodging.status` thêm `booked` (đã có chỗ ở → không có ứng viên; `state.lodging_point` là chỗ đó, `source: user`). Mỗi ứng viên: `id, name, price_vnd, source (corpus|live), price_at (null = giá tham khảo; có = giá live lúc đó), rating, reviews, avg_min, fit [{text, mentions, quote}], unverified [nhãn đã viết thường]`. `quote` hiện luôn `null` (serving không mang câu trích; web lấy từ snapshot nếu cần).
> - `Transit` có thêm `stops` (số điểm dừng của chuyến bay, `0` = bay thẳng; `null` với xe khách). Sân bay không có chuyến thẳng (Huế, Thọ Xuân, Đồng Hới, …) chỉ có chuyến nối chuyến: web nên hiện "1 điểm dừng" để không lẫn với chuyến thẳng. Gửi lại nguyên `Transit` (có `stops`) khi trả lời thẻ.
> - Production: `run.sh` tự đặt `CORPUS_BROWSER_CHANNEL` / `PLAYWRIGHT_BROWSERS_PATH` khi máy không có Chrome; harness :8769 đã khởi động lại với code mới (2026-10-08 23:00). `./run.sh prewarm` đã chạy: 756/756 ngày xe khách, 539/540 tuyến-ngày chuyến bay trong cache.

> **WEB báo lại cho BE (2026-10-08 23:xx, walk toàn luồng `web/scripts/shots_app.mjs` trên harness dev :8779):**
> - **Chặn toàn luồng:** chọn chuyến bay → `entry_point` = "Cảng Hàng Không Quốc Tế Liên Khương" → Planning `no_valid_variant`, `places: []` (journey `4d82f382c4d6`). Thử `engine.preview` trên chính Decision Output đó: có `entry_point` bất kỳ (sân bay có tọa độ, "Bến xe Liên tỉnh Đà Lạt" chỉ có chữ) → hỏng, kể cả `arrive_at` 09:00 / `leave_at` 15:00; bỏ `entry_point` (giữ `exit_point`) → xếp được. Tái hiện: `create_engine(Path("data")).preview(dec)` với `dec = json.load(open("data/harness/sessions/4d82f382c4d6.json"))["outputs"]["decision"]`, đổi `dec["trip_context"]["context"]["entry_point"]`.
> - `/lodging/suggest?q=ana` trả địa chỉ ở Thái Lan; `/geo?q=Quận 1, Hồ Chí Minh` trả trường đại học, không có chính "Quận 1". Nên giới hạn / ưu tiên vùng (Photon `bbox` / `lat,lon` bias quanh Đà Lạt cho chỗ ở; Việt Nam cho xuất phát).

Thứ tự gợi ý; mỗi mục có test theo spec §5 (C live, C' planning).

1. **`src/live/buses/`** (Vexere, cache `data/live/vexere/`): `live.buses(origin_province_or_point, date, way)` — chọn tỉnh gần nhất trong `vexere_regions` theo tọa độ (`Base.lat/lng` của origin; tên tỉnh chỉ để dự phòng). HTTP stdlib là đủ (trang render sẵn, không cần Playwright — khác spec §3.3, ghi lại trong `docs/PLANNING.md`). URL và đường dẫn JSON: comment trong `config/live.yaml`. Mỗi trip trong `routeReducer.trips`: `busName`, `route.schedules[0].pickup_date` / `arrival_time` (đã có múi +07:00), `fromName`/`fromAddress`, `toName`/`toAddress`, `fareLarge` (giá). Parser chạy trên `tests/fixtures/live/vexere_hcm_dalat_20261112.html`.
2. **`src/live/flights/`** (Google Flights qua `corpus.crawl.open_sessions`, cache `data/live/flights/`): `live.flights(origin_iata, dest_iata, date)`. URL đã thử: `https://www.google.com/travel/flights?q=Flights%20from%20SGN%20to%20DLI%20on%202026-11-12%20one%20way&hl=vi&curr=VND`, chờ ~8 s. Mỗi chuyến có `aria-label` dạng "Từ 890181 đồng Việt Nam trở lên. Chuyến bay thẳng của Vietnam Airlines. Rời … lúc 06:10 vào … và đến … lúc 07:05 vào …" (fixture `flights_sgn_dli_20261112.html`). Trang chỉ hiện 5 chuyến "hàng đầu"; muốn đủ thì bấm "Các chuyến bay khác" trước khi đọc. Lỗi / captcha / rỗng → `Unavailable`, không bao giờ trả chuyến giả.
3. Test boundary: `src/live` không ghi gì ngoài cache (đã có `tests/live/test_boundaries.py`, thêm `flights`, `buses` vào `live.__all__` và danh sách của test).
4. **`scripts/prewarm_transit.py`** + `config/live.yaml` `transit_prewarm` (bay: các sân bay trong `config/airports.yaml` × 30 ngày × 2 chiều; xe: `vexere_regions` × 14 ngày × 2 chiều; TTL 26 giờ trong cache của chính module). Ghi cron vào `README.md`.
5. **Harness**: thêm các endpoint §1 (`src/harness/server.py` + `dispatch.Harness`, gọi qua `planning.Tools` — Planning là chủ Live Context). Transit: đọc cache → `ready`; thiếu → crawl nền + SSE; lỗi → `unavailable` + `book_url`.
6. **Planning — chỗ ở** (spec §4.2): `planning/lodging.py candidates` đọc serving nhóm `stay` khi ≥ `stay_min` (config, 50) chỗ ở trong vùng tìm, chưa đủ → `lodging_fn` live như cũ (thẻ `source: live`, "chưa đủ dữ liệu để so gu"); `lodging_score = w_pref·pref_fit + w_loc·loc_fit + w_price·price_fit + w_rating·rating_fit` (`config/planning.yaml lodging_weights`: 2.0 / 0.8 / 0.5 / 0.3); `unknown` không trừ điểm; hard filter có bằng chứng chống mới loại; mỗi thẻ có "hợp vì …" kèm số người nhắc. Giá live về muộn không đổi thứ hạng đã hiện trừ khi vượt trần.
7. **Planning — chỗ ở đã đặt**: `lodging_booked = yes` + `lodging` có tọa độ → session Planning tạo ra đã có `lodging_point` (như `set_lodging`, `source: "user"`) và không crawl / gợi ý chỗ ở; `planning/places.resolve_point` dùng thẳng `lat/lng` của `Base` khi có; `decision/fit.centers` cũng vậy (base không có `place_id` nhưng có tọa độ).
8. Chạy lại: `tests/live tests/planning tests/harness tests/decision tests/trip`.

## 3. Session WEB

> **Xong 2026-10-08 trừ §3.6 (chưa commit).** 1–4: `ui/PlaceInput.tsx`, `ui/TransitPick.tsx`, thẻ `geo | transit | lodging` trong `screens/Understand.tsx`, dòng vé mới (`tu/labels.ts`, `ui/Ticket.tsx`), `screens/Lodging.tsx` (gắn trong `Plan.tsx`), `params.lat/lng` gửi kèm `/transit`, `lodging.status = booked` ở cột bên. 5: `make_thumbs.py` 11.666 ảnh mới, 0 lỗi; `shots_sheet.mjs` 1440 + 390 không lỗi trang. 6: kịch bản ở `web/scripts/shots_app.mjs` (không phải `test_journey.mjs` — file đó là unit test client `journey.ts`); chạy trên harness dev :8779 qua xuất phát → máy bay → chuyến đi / về (dữ liệu Google Flights thật) → "chưa có" → Lựa chọn, rồi **dừng ở Lịch trình vì lỗi `entry_point` của Planning** (§2, báo lại cho BE). Bỏ `entry_point` qua vé thì "Bạn ở đâu?" hiện 6 chỗ ở live thật, chọn một → màn chọn hành trình. 7: đã gộp tài liệu + mục `DEV_LOG.md` `detail-logistics`; đã xóa spec và `PLAN_1`.

1. **`PlaceInput`** (`web/src/user/ui/PlaceInput.tsx`, spec §3.4): gợi ý từ ký tự thứ 2, debounce 250 ms, ≤ 6 dòng, tô đậm phần khớp, ↑ ↓ Enter Esc; mỗi dòng icon loại · tên · khu / địa chỉ ngắn · ★ nếu có; rỗng → "Không thấy nơi này. Thử gõ địa chỉ hoặc tên đường.". Dùng cho thẻ `origin` (`/geo`) và `lodging_booked` (`/lodging/suggest`).
2. **Thẻ trong `screens/Understand.tsx`** cho `input = geo | transit | lodging` (theo §1). Transit: danh sách chuyến (hãng, giờ đi → đến, điểm đón / trả, giá + "giá tham khảo lúc HH:mm dd/mm, kiểm lại khi đặt"), lọc nhanh Sáng / Chiều / Đêm / Rẻ nhất, "Chọn chuyến này", cuối danh sách "Tôi tự lo phần này" (= `skip`); `pending` → skeleton + SSE; `unavailable` / rỗng → nút mở `book_url` và ô nhập tay giờ (`{"time"}`). Lodging: ô tìm là phần chính, text "Cho mình biết nơi bạn sẽ lưu trú ở Đà Lạt nhé.", chip "Chưa có, gợi ý giúp mình", "Bỏ qua". Thêm `'geo' | 'transit' | 'lodging'` và `params` vào `tu/types.ts`.
3. **Vé chuyến**: nhãn + cách hiện cho các target mới (`tu/labels.ts` `FIELD_LABEL`, `valueText`): xuất phát, phương tiện, chuyến đi / về (hãng + giờ), chỗ ở.
4. **Màn "Bạn ở đâu?"** (`web/src/user/screens/Lodging.tsx`, spec §4.3): hiện khi `lodging_booked = no` lúc bấm "Xếp lịch", trước lịch. Thẻ: ảnh, tên, điểm, giá/đêm hoặc "chưa có giá", "Hợp vì: …" kèm trích dẫn, số phút trung bình tới các nơi đã chọn; thẻ đầu "Hợp gu bạn nhất"; bấm thẻ mở `PlaceSheet`; hành động chọn (`pick_lodging`) · "Tôi ở chỗ khác" (`PlaceInput` → `set_lodging`) · "Cứ xếp giúp" · "Bỏ qua". Dữ liệu: `read/planning/lodging` sẵn có (BE bổ sung trường gu ở §2.6).
5. **Ảnh**: chạy `web/scripts/make_thumbs.py` cho ảnh mới trong `covers.json` (gallery giờ 12 ảnh/nơi); xem lại tab Hình ảnh trên 5174; chụp `shots_sheet.mjs` ở 1440 và 390.
6. **Toàn luồng**: `web/scripts/test_journey.mjs` thêm một chuyến: chat → xuất phát → máy bay → chọn chuyến → chưa có khách sạn → chọn nơi → chọn khách sạn → lịch (spec §5 hàng cuối). Chạy khi BE xong §2.5–2.7.
7. **Tài liệu** (làm cuối, sau khi BE xong): gộp vào tài liệu chính thức theo spec §6 (`PLACE_DECISION.md` §9.2, `TRIP_UNDERSTANDING.md` §Hậu cần, `CORPUS.md` §Phạm vi + Phase 1 nhóm `stay` (kèm `stay.gmaps` trong `config/queries.yaml`: chỗ ở lấy 300 review mới nhất + relevant + extremes), `LLM_PROVIDER.md` task `photo_rank`, `Role_Web_Functional_Design.md` §6 `PlaceSheet` / `Lodging.tsx` / `PlaceInput`; `PLANNING.md`, `AGENT_HARNESS.md`, `README.md` BE đã làm), một mục mới trong `docs/log/DEV_LOG.md`; rồi **xóa** `DETAIL_LOGISTICS_SPEC.md`, `DETAIL_LOGISTICS_PLAN_1.md` và file này.
