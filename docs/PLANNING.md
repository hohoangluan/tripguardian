# Planning & Validation + Live Context

Bước online thứ ba và cuối. Vị trí trong luồng: `docs/ARCHITECTURE.md` §3. Đầu vào: `docs/PLACE_DECISION.md` §15. Code: `src/live/` (Live Context) + `src/planning/` (lịch trình); CLI và API ở §CLI và API.

## Mục tiêu

Từ **tập địa điểm đã xác nhận** của Place Decision, dựng 2–3 **phương án lịch trình** đã kiểm tra, mỗi phương án tối ưu một mục tiêu khác nhau, kèm **chỗ ở** được chọn sao cho cả chuyến đi ít di chuyển nhất, rồi để người dùng sửa, góp ý và chốt.

Đích: tối ưu có thật (đo được so với baseline), kiểm tra tất định (lịch trông hợp lý là chưa đủ), và giải thích được từng lựa chọn — kể cả cái đã phải hy sinh.

## Phạm vi

Trong: chia ngày; gom cụm; thứ tự trong ngày; khớp giờ mở cửa; chọn thời gian tham quan theo nhịp độ; thời gian đệm và nghỉ; đề xuất chỗ ở (tra live theo yêu cầu); điểm vào / ra thành phố; kiểm tra cuối; độ vững; kế hoạch dự phòng; 2–3 phương án theo mục tiêu; vòng người dùng sửa / góp ý / chọn; Live Context (thời gian di chuyển, thời tiết, chỗ ở, geocode, mặt trời, lễ).

Ngoài: booking và thanh toán; điều hướng turn-by-turn; traffic thời gian thực; giá phòng từ API OTA; nhiều thành phố; cộng tác nhóm; đưa chỗ ở vào Place Intelligence.

## Nguyên tắc

1. **Chỗ ở không bao giờ vào Place Intelligence.** Nó được tra live theo từng request, chỉ sống trong phiên, mang `source` + `fetched_at` (`docs/ARCHITECTURE.md` §1).
2. **Chỗ ở là biến trong bài tối ưu**, không phải danh sách gợi ý rời. Mỗi ứng viên được chấm bằng cách làm anchor đầu / cuối ngày rồi xếp lại cả lịch và đo.
3. **Solver và kiểm chứng tất định.** Agent nội bộ chỉ đề xuất bố trí trên phương án đã dựng; quyền, khả thi và điểm mục tiêu do rule kiểm trước khi áp dụng.
4. **Physical constraint không bao giờ nới ngầm.** Không có đường code nào nới nó.
5. **Không bịa.** Thiếu dữ liệu → `unknown` + gắn cờ, không điền giá trị. Thiếu quán ăn trong tập đã xác nhận → chừa khoảng trống, không tự thêm địa điểm.
6. **Số live luôn có nguồn và thời điểm.** Thời gian di chuyển, giá phòng, thời tiết đều gắn nhãn ước lượng / tham khảo, không phải Fact.
7. **Không xáo lịch âm thầm.** Mỗi thay đổi hiện qua diff; nơi đã khóa không bị dời.

## Ranh giới module

```
src/live/                      Live Context — gọi mạng, đọc-ghi cache; KHÔNG có đường ghi data/intel
  __init__.py                  public API: travel_matrix, route_shape, weather, lodging_near, lodging_seen, geocode,
                               geosearch, flights, flights_url, buses, buses_url, sun_times, holidays, events,
                               advisories, Unavailable
  http.py                      một GET (JSON hoặc trang HTML), một timeout, không retry; lỗi → Unavailable
  cache.py settings.py         cache theo key + TTL → data/live/<source>/; ngưỡng từ config/live.yaml
  osrm/                        ma trận thời gian (/table) + hình lộ trình (/route), service local
  weather/                     Open-Meteo: dự báo theo giờ trong tầm; ngoài tầm → khí hậu theo tháng
  lodging/                     crawl mặt lodging của Maps theo request, qua public API của corpus.crawl
  geocode/                     text → toạ độ (Nominatim); gợi ý khi gõ (Photon, lỗi → Nominatim)
  flights/                     chuyến bay một ngày từ Google Flights, qua public API của corpus.crawl
  buses/                       xe khách một ngày từ Vexere (trang render sẵn, HTTP thường)
  sun.py                       mọc / lặn, công thức NOAA, tính local
  holidays.py events.py        config/holidays.yaml, config/events.yaml (nhập tay)
  advisories.py                config/advisories.yaml (thông báo nhập tay, có nguồn)

src/planning/                  Planning & Validation — rule tất định
  model.py settings.py         kiểu dữ liệu; ngưỡng từ config/planning.yaml
  places.py                    Decision Output + serving record → nơi xếp được + điểm đầu / cuối chuyến
  frame.py                     các ngày của chuyến: ngày, thứ, khung giờ dùng được
  conditions.py                điều kiện từng ngày (DayCond) từ live; hazard, đông khách, đóng cửa dịp Tết; `fetch_live`
  travel.py                    một ma trận OSRM mỗi chuyến, chặng ngắn đi bộ, đường lui thô có nhãn
  traits.py                    fact của một nơi mà mục tiêu / độ vững / dự phòng dùng chung
  lodging.py                   ⓐ vùng tìm → nguồn (corpus `stay` hoặc live) → sàng → xếp theo gu → K ứng viên
  logistics.py                 tra cứu cho câu hỏi hậu cần trước khi có phiên Planning: geo, chỗ ở theo tên, chuyến
  cluster.py days.py route.py  ⓑ gom cụm, chia ngày (DP), thứ tự trong ngày
  schedule.py                  ⓒ khớp giờ mở, visit theo pace, đệm, nghỉ
  validate.py                  ⓔ kiểm tra cuối, fail-closed
  robustness.py                ⓕ độ vững 3 mức
  backup.py                    ⓗ dự phòng từ backup_pool
  objectives.py variants.py    ⓖ điểm theo mục tiêu; dựng 2–3 phương án
  build.py                     ghép một đường: prepare → schedule_trip → with_home
  repair.py scope.py           repair_day; phạm vi chạy lại
  output.py                    Plan Output
  session.py                   phiên có phiên bản, undo / redo
  agent.py guard.py policy.py  một call mỗi lượt chữ; guard; policy từ khóa khi agent lỗi
  proposal.py                 PlanningProposal và call Agent nội bộ, không chat
  tools.py skills.yaml        adapter public cho harness; quyền agent theo module
  engine.py server.py          HTTP + SSE, cổng 8768
  evaluate.py                  đo offline trên 30 chuyến ẩn
```

Phụ thuộc một hướng: `planning` → `live`, `decision`, `trip`, `corpus.serving`, `corpus.ontology` (chỉ qua `__init__.py`; RULE §2). `live` không biết `planning`. `decision` không đổi.

Dữ liệu:

| Thư mục | Ghi bởi | Nội dung |
|---|---|---|
| `data/live/<source>/` | `src/live` | cache theo request, có TTL, mỗi mục mang `source` + `fetched_at` (`lodging`, `osrm`, `weather`, `geocode` — chỉ tạo khi nguồn đó được gọi) |
| `data/planning/sessions/` | `src/planning` | phiên API độc lập; `data/planning/eval.json` là kết quả `evaluate` |
| `data/intel/`, `data/serving/`, `data/gmaps/` | chỉ offline corpus | Planning chỉ đọc |

## Đầu vào

Decision Output nguyên dạng (`docs/PLACE_DECISION.md` §15): `confirmed` (id, role `anchor | locked | selected`, visit minutes, flags, relaxed), `backup_pool` (kèm `for` + `reason`), `wishlist`, `trip_context` (bản chụp Search Input), `decision_log`, `feasibility`.

Thêm vào Trip State (`docs/TRIP_UNDERSTANDING.md` §3, §9): `entry_point`, `exit_point` kiểu `Base` (text + `place_id` hoặc toạ độ sau geocode) — nơi người dùng vào / ra thành phố (bến xe, sân bay, tự lái). `src/trip/domain/questions.py` thêm một câu khi chưa biết. Thiếu → ngày đầu / cuối chỉ bị cắt theo `arrive_at` / `leave_at`, gắn cờ "ước lượng ngày đầu / cuối kém chắc".

## Live Context

Mọi hàm trả `None` khi không có dữ liệu; không bịa. `src/live` không import `corpus.aggregate` / `corpus.serving` để ghi, và test khẳng định không có đường ghi tới `data/intel`, `data/serving`, `data/gmaps`.

| Nguồn | Public API | Cách lấy | TTL | Khi lỗi |
|---|---|---|---|---|
| `osrm/` | `travel_matrix(points, mode)`, `route_shape(points, mode)` | OSRM local trên OSM Việt Nam; `/table` cho ma trận, `/route` cho hình đường của lịch đã chốt | 7 ngày | rơi về ước lượng thô của Planning (`travel.rough_minutes`: đường chim bay × `road_factor` ÷ `rough_speed_kmh`); plan gắn `travel_source = rough` + cảnh báo; độ vững trần "Khả thi" |
| `weather/` | `weather(lat, lng, dates)` | Open-Meteo forecast theo ngày (trong tầm 16 ngày): xác suất mưa, lượng mưa mm, gió giật, dông (`weather_code` 95–99). Ngoài tầm → `config/climate.yaml` theo tháng (chỉ xác suất mưa) | 3 giờ / tĩnh | `None` → ngày đó không xét thời tiết, gắn cờ "chưa biết thời tiết"; số nguồn không cho giữ `None` |
| `lodging/` | `lodging_near(center, radius_km, check_in, check_out, price_max)` | crawl **mặt lodging của Maps** theo request (xem dưới) | 24 giờ | danh sách rỗng → anchor = `base` / `entry_point`, nói rõ "chưa tra được chỗ ở" |
| `geocode/` | `geocode(text)` | Nominatim, 1 req/s, User-Agent riêng của dự án | 30 ngày | `None` → hỏi lại người dùng |
| `geocode/` | `geosearch(text, limit=6)` | Photon (OSM, làm cho gõ-tới-đâu-gợi-ý-tới-đó), lỗi → Nominatim | 30 ngày | `Unavailable` → ô tìm hiện "không thấy" |
| `flights/` | `flights(src, dst, day, fetch=True)` | Google Flights (`hl=vi`, `curr=VND`) qua `corpus.crawl.open_sessions`; đọc `aria-label` của từng dòng chuyến ("Từ … đồng … của <hãng>. Rời … lúc HH:MM … và đến … lúc HH:MM …") | 26 giờ | `Unavailable` (captcha, trang không có dòng nào, trình duyệt chết); không bao giờ trả chuyến giả |
| `buses/` | `buses(origin, day, way, fetch=True)` | trang tuyến của Vexere; trang render sẵn nên một GET HTTP stdlib là đủ, không cần trình duyệt: chuyến nằm trong `__NEXT_DATA__` `routeReducer.trips` (giờ đón / đến của `route.schedules[0]`, `fareLarge`, điểm đón / trả). `origin` là toạ độ (tỉnh gần nhất trong `config/live.yaml` `vexere_regions`) hoặc tên tỉnh | 26 giờ | `Unavailable` (trang đổi / bị chặn, tỉnh không có trong bảng) |
| `sun.py` | `sun_times(date, lat, lng)` | công thức NOAA, không mạng, không thêm dependency | — | — |
| `holidays.py` | `holidays(dates)` | `config/holidays.yaml` (lễ Việt Nam, nhập tay) | — | — |
| `events.py` | `events(dates)` | `config/events.yaml` (lễ hội, Noel, Tết; nhập tay): `crowd` busy / peak, `closure_risk` | — | ngày không liệt kê = chưa biết sự kiện nào, không phải ngày vắng |
| `advisories.py` | `advisories(dates)` | `config/advisories.yaml` (thông báo thiên tai / đường bị chặn, nhập tay từ thông báo chính thức, bắt buộc có `source`) | — | rỗng = chưa có thông báo trong dữ liệu, **không** phải an toàn |

### OSRM

Thiết lập một lần mỗi máy, `scripts/osrm_setup.sh` + mục trong `README.md`: tải `vietnam-latest.osm.pbf` (Geofabrik) → `osrm-extract` (profile `car`) → `osrm-partition` → `osrm-customize` → `osrm-routed --max-table-size 300`.

Mode: OSM không có profile xe máy chuẩn. Dùng profile `car` rồi nhân `mode_factor` (`config/live.yaml`: `car 1.0`, `motorbike 0.95`). Chặng ngắn hơn `walk_km` tính đi bộ bằng khoảng cách × `road_factor` ÷ tốc độ đi bộ. Mọi số này hiển thị là **ước lượng**, không nói là thời gian thật của một nhà cung cấp nào.

Một ma trận mỗi lượt cho tập điểm = `confirmed` + K chỗ ở + `entry_point` + `exit_point`. Khoảng 20 điểm → 400 cặp, một request. Mọi phương án dùng chung ma trận đó.

### Chỗ ở (crawl live)

Dùng mặt **"Khách sạn"** của Maps, không phải search địa điểm thường: đặt check-in = ngày đầu chuyến, check-out = ngày cuối (`nights = days − 1`), đặt trần giá bằng bộ lọc giá của Maps. Thẻ trả về: `name`, `fid`, `lat/lng`, `rating`, `reviews`, `price_per_night`, `amenities`.

- Mặt lodging của Maps **bỏ qua khung bản đồ** (`CORPUS.md` §Phạm vi) nên không liệt kê đủ được. Với live-only thì không sao: chỉ cần top ứng viên quanh một khu.
- Nhiều homestay Đà Lạt không lên OTA nên không có giá, có khi không có thẻ. Thẻ không giá vẫn **được giữ**, `price = unknown`, không bị trần giá loại, hiện "chưa có giá".
- `price_per_night` là giá OTA tại thời điểm crawl → mang `source` + `fetched_at`, nhãn "giá tham khảo, kiểm lại khi đặt". Không phải Fact.
- `start_date` chưa biết (chỉ có `month`) → crawl không đặt ngày; giá bỏ trống, gắn cờ.
- Dùng lại code crawl đúng ranh giới: `src/corpus/crawl/__init__.py` hiện không export gì nên deep import là vi phạm RULE §2. Thêm public API tối thiểu — `open_sessions`, `LoginRequired`, `maps_search(ctx, query, limit, at)` — rồi `src/live/lodging` gọi qua đó và chỉ ghi `data/live/lodging/`. Không copy code Playwright.
- `LoginRequired` hoặc captcha → trả rỗng kèm lý do; Planning chạy tiếp ở phương án không chỗ ở. Ngày check-in /
check-out và trần giá hiện mới lọc được ở phía Planning (`price_max`), chưa gửi lên bộ lọc của Maps — giá đọc được
là giá Maps hiển thị mặc định tại thời điểm crawl, không phải giá đúng hai ngày đó; cần dò lại bằng trình duyệt
thật trước khi nối UI ngày / giá của Maps. Giá và tiện nghi đọc bằng quét văn bản thô của thẻ (không phải một
class CSS riêng): best-effort, kiểm lại trước khi tin.

### Chuyến xe khách, chuyến bay (câu hỏi hậu cần)

Mỗi chuyến: `mode`, `carrier`, `depart_at`, `arrive_at` (giờ VN `YYYY-MM-DDTHH:MM`), `from_point`, `to_point`, `price_vnd | None`, `stops` (chuyến bay: số điểm dừng, `0` = bay thẳng; xe khách: `None`), `source`, `fetched_at` — đúng `Transit` của Trip State (`docs/TRIP_UNDERSTANDING.md`). `fetch=False` chỉ đọc cache (trả `None` khi thiếu); `flights_url` / `buses_url` là trang đặt vé đã điền điểm đi, đích, ngày cho người dùng tự mở khi không tra được.

Chạy trước mỗi ngày: `scripts/prewarm_transit.py` (cron, `README.md` §Chạy) gọi đúng hai hàm trên cho `config/live.yaml` `transit_prewarm` — chuyến bay: mọi sân bay trong `config/airports.yaml` ↔ `DLI` × `flight_days` ngày kể từ mai; xe khách: mọi tỉnh trong `vexere_regions` ↔ Đà Lạt × `bus_days` ngày kể từ hôm nay; entry còn dưới 20 giờ tuổi thì giữ; 8 lần bị chặn liền (trang captcha) thì dừng nguồn đó, ngày không có chuyến không tính. Kết quả nằm trong cache của chính module. Sân bay không có chuyến thẳng thì Google trả chuyến nối chuyến; chúng được giữ như mọi chuyến (giờ đi / đến thật, `stops` ≥ 1). Parser đọc trang kết quả đầu tiên, không bấm "Xem các chuyến bay khác" (nút đó mở trang khác không có các dòng chuyến).

Online (`planning/logistics.py`, qua harness `docs/AGENT_HARNESS.md`): cache có → `ready`; thiếu → một lượt crawl nền cho mỗi tuyến / ngày, trả `pending`, SSE đẩy kết quả khi xong; crawl lỗi → `unavailable` (không thử lại trong 10 phút) kèm trang đặt vé.

### Điều kiện từng ngày

Một ngày có thể đổi chính kế hoạch: thời tiết xấu hơn mức "xác suất mưa", cuối tuần / lễ / lễ hội làm đông, dịp Tết nhiều quán đóng cửa, thông báo thiên tai. Engine gọi `conditions.fetch_live` (một lần mỗi lần dựng) lấy `weather` và `signals` (`holiday`, `events`, `advisories` mỗi ngày) từ `src/live`; `prepare()` đổi chúng thành một `DayCond` cho từng ngày có ngày cụ thể. Ngày không có tín hiệu thì không có `DayCond` và lịch giữ nguyên như trước. Nguồn thời tiết không trả lời → `weather = None` (cờ "chưa biết thời tiết"); ba file nhập tay không bao giờ làm hỏng chuyến.

| Điều kiện | Cách đọc | Tác động |
|---|---|---|
| Thời tiết | `heavy`: dông hoặc mưa ≥ `heavy_rain_mm` hoặc gió giật ≥ `heavy_gust_kmh`; `severe`: mưa ≥ `severe_rain_mm` hoặc gió giật ≥ `severe_gust_kmh` | `heavy` tính như ngày mưa (`wet` ≥ `rain_high`): đệm lớn hơn, nơi ngoài trời bị phạt khi chia ngày, nơi nhạy cảm có dự phòng, mục tiêu `weather_robust`, kịch bản mưa của độ vững. `severe`: nơi `weather_exposed` **không được xếp** vào ngày đó |
| Thông báo | `advisories.yaml`, phạm vi `city` hoặc vòng tròn `lat, lng, radius_km` | `severe`: nơi trong phạm vi không được xếp (bão chỉ chặn nơi ngoài trời; ngập, sạt lở, cháy, đường bị chặn chặn mọi nơi trong vùng); thấp hơn `severe`: vẫn xếp, có cờ, nơi trong vùng là nhạy cảm (`advisory`) và dự phòng không lấy nơi cùng vùng |
| Đông khách | cuối tuần = `busy`; ngày lễ hoặc sự kiện `peak` = `peak`; một nơi "đông" khi `crowd = high` đã xác minh hoặc `crowd_by_time` của chính nó ≥ `crowd_busy_pct` đúng loại ngày (`weekday` / `weekend` / `holiday`) | nơi đông: thời gian tham quan tăng `crowd_visit_pct`, đệm thêm `crowd_buffer_min`; chia ngày phạt `weights.crowd` × mức × (`crowd_avoid_factor` nếu người dùng tránh đông); ngày `peak` làm nơi đó nhạy cảm (`crowd`) và dự phòng không lấy nơi đông; `crowd_tips` nói giờ vắng nhất từ chính số liệu của nơi |
| Đóng cửa dịp Tết | sự kiện `closure_risk` | cờ mỗi ngày; nơi ăn uống được đệm thêm `closure_buffer_min` và nhạy cảm (`holiday_closure`), dự phòng phải có giờ đã xác minh. Không tự kết luận một quán đóng |

Validate là chỗ duy nhất quyết định: nơi bị hazard mà vẫn có trong lịch là vi phạm `hazard`; không ngày nào xếp được → `back_to_decision` như mọi vi phạm khác. Dữ liệu vắng thì không kết luận: ngày không có số đo không thành `severe`, và "không có thông báo" không bao giờ được viết thành "an toàn".

Plan Output (qua `shared_output` và view của Engine) thêm `day_conditions` (từng ngày, chỉ khi có điều kiện) và `crowd_tips`. Web hiện chúng trên ngày đang chọn (`web/src/user/screens/Plan.tsx`).

### Trạng thái vận hành theo thời điểm

`place_live_status(place)` (đóng cửa tạm, giờ ngày lễ) chỉ chạy ở bước xác nhận cuối, best-effort, timeout mỗi nơi, giới hạn số nơi mỗi phiên. Không tra được → giữ cảnh báo "kiểm tra lại trước chuyến" như giờ `UNCERTAIN` / `OUTDATED` đã có. Không bao giờ sửa giờ trong corpus.

## Thuật toán

### ⓐ Ứng viên chỗ ở — `lodging.py`

0. **Đã có chỗ ở:** `lodging_booked = yes` và `lodging` có toạ độ → chỗ ở đó là `base` (mọi ngày đi và về từ đó), phiên mở ra đã có `lodging_point` (`source: user`, như `set_lodging`), `lodging.status = booked`; không tra, không gợi ý. Vẫn đổi được bằng `set_lodging`.
1. **Vùng tìm:** tâm trọng số của các nơi đã chọn (trọng số = `visit typical`); tách tối đa 2 tâm nếu đường kính cụm > `split_min`. Thêm vùng quanh `entry_point` khi ngày đầu / cuối gấp.
2. **Nguồn theo dữ liệu có sẵn:** serving có ≥ `stay_min` chỗ ở nhóm `stay` trong vùng (≤ 2 × `radius_km` quanh một tâm) → đọc từ corpus (`source: corpus`, giá tham khảo từ đánh giá); ít hơn → `lodging_near(center, radius_km, check_in, check_out, price_max)` như cũ (`source: live`, chưa có đánh giá đã observe nên không so được gu). `price_max = lodging_share × budget_vnd ÷ nights` khi `budget_vnd` đã biết. Không có cờ bật tắt tay: corpus `stay` đủ là tự chuyển.
3. **Sàng tất định:** ngoài vùng → bỏ. Dưới `min_reviews` → bỏ (chống rác, không phải tiêu chí chất lượng). Hard filter (`!=`) chỉ loại khi có bằng chứng chống: chỗ ở corpus theo `check` của serving, thẻ live theo `amenities`; không có → giữ, ghi vào `unverified` ("chưa xác minh: …").
4. **Bể để xếp:** corpus → `lodging_pool` chỗ hợp gu nhất (gần hơn thắng khi bằng nhau) để ma trận di chuyển nhỏ; live → `lodging_k` chỗ gần nhất.
5. **Xếp hạng** (sau khi ma trận có các ứng viên): `lodging_score = w_pref·pref_fit + w_loc·loc_fit + w_price·price_fit + w_rating·rating_fit` (`lodging_weights`, gu nặng hơn vị trí). `pref_fit` = tổng soft (`love` +1, `avoid` −1) và người đi cùng (`kids`, `parents` → `elderly`, `partner` → `couples` `=suitable`, +1) mà feature `VERIFIED` của chỗ ở khớp, chia số mong muốn; không có bằng chứng → 0, không bao giờ âm (`docs/PLACE_DECISION.md` §8). `loc_fit = 1 − phút trung bình tới các nơi đã chọn ÷ loc_ref_min` (≥ 0). `price_fit` theo trần giá, không giá → 0. `rating_fit` theo điểm, không có → 0. Giữ `lodging_k`. Mỗi thẻ mang `fit` ("hợp vì": nhãn feature + số đánh giá nhắc), `avg_min`, `unverified`, `source`.
6. **Giá đúng ngày về sau:** chỗ ở corpus đang hiện → `lodging_near` chạy nền, giá live (khớp theo id Maps) thay giá tham khảo của 5 thẻ đầu (`price_at`). Thứ tự không đổi; giá vượt trần → thẻ không còn được đề xuất (trừ khi người dùng nâng trần).
7. Luôn giữ thêm **phương án "không chỗ ở"** (anchor = `base` / `entry_point`) để so sánh thật.

### ⓑ Gom cụm và chia ngày — `cluster.py`, `days.py`

- Khung ngày: ngày đầu từ `arrive_at` (hoặc `entry_point` + travel tới chỗ ở); ngày cuối đến `leave_at` − travel tới `exit_point`; ngày giữa `day_start..day_end`.
- Cụm: `area` của serving record trước, rồi chia / gộp theo **đường kính thực** (ma trận OSRM) với ngưỡng `cluster_max_min`.
- Gán cụm → ngày: số ngày ≤ `max_days` (7), cụm ≤ `max_clusters` (8) → **DP trên tập con**, tất định. Hàm phí = tổng di chuyển + phí vi phạm giờ mở + lệch số nơi mỗi ngày theo pace + phí "cụm ngoài trời vào ngày mưa xác suất cao". Phí bằng nhau → ngày sớm hơn nhận nơi (một nơi duy nhất nằm ở Ngày 1 nếu Ngày 1 chứa được). Vượt giới hạn → rơi về gán tham lam, gắn cờ.
- Ghim: anchor giờ cố định ghim ngày + giờ; nơi chỉ mở vài ngày trong chuyến ghim ngày; `locked` cùng ngày người dùng đã chỉ định không đổi.

### ⓒ Thứ tự trong ngày — `route.py`

- Mỗi ngày mở và kết ở chỗ ở; ngày đầu mở ở `entry_point`, ngày cuối kết ở `exit_point`.
- n ≤ `exact_n` (7) nơi mỗi ngày → **vét cạn permutation** có cắt tỉa theo giờ mở (≤ 5040) → tối ưu thật. n lớn hơn → nearest-neighbour + 2-opt + or-opt. Cả hai tất định.
- Buổi: `pins` (`config/planning.yaml`: `sunset_view`, `cloud_hunting`, `live_music`) + `sun_times` → hoàng hôn / đêm ghim cuối ngày; sương / bình minh ghim đầu ngày. Một nơi có nhiều tính năng theo giờ chỉ cần **một**, không lấy giao: nếu người dùng muốn (soft weight dương) một trong số đó thì chỉ giữ các ghim được muốn (`build.prepare`), còn lại ưu tiên khung nằm trong ngày. Khung mà giờ mở cửa của chính nơi đó không chứa nổi (nhạc 18:00 ở quán đóng 18:30) thì không ghim. Ngày nào vẫn hỏng vì hai nơi cùng muốn một buổi → bỏ ghim của nơi xếp muộn nhất trước, tới khi ngày đạt, kèm cảnh báo `pin_dropped`; nơi đó vẫn được ghé, chỉ không đúng giờ đẹp nhất.
- Bữa ăn: `meals_per_day`. Có quán ăn trong `confirmed` → chèn vào khung trưa / tối **mà quán đó mở cửa và hợp với buổi của nó** (quán chỉ mở chiều nhận bữa tối); không khung nào hợp thì ghé như một điểm thường. Không có quán → chừa khoảng trống "ăn trưa (tự chọn)", không thêm địa điểm.

### ⓓ Giờ, tham quan, đệm, nghỉ — `schedule.py`

Visit theo pace: thong thả → `long`, cân bằng → `typical`, đi nhiều nơi → `min`. Thời lượng là một khoảng ước tính: mức của pace không vừa ca mở cửa hoặc phần còn lại của ngày thì rút dần về mức `short`, không thấp hơn. Kiểm tra độ vững (`robustness.py`) không rút, để "trễ 15 phút" vẫn đo đúng. Đến sớm → `wait`; quá giờ đóng → vi phạm. Đệm = `buffer_min[pace]` + phụ phí theo độ không chắc (mưa, chặng dài, giờ `UNCERTAIN`). Nghỉ chèn theo pace, và chặn "đi liên tục quá `max_consecutive_min` mà không nghỉ".

### ⓔ Kiểm tra cuối — `validate.py`

Nơi **duy nhất** kết luận đạt / không đạt, và kết luận từ chính dòng thời gian cuối cùng. Tám kiểm tra: ngày đi · giờ mở cửa · chồng lấn · thời gian di chuyển · anchor · ngân sách (gồm tiền phòng khi đã biết giá) · hard constraint · địa điểm trùng (cùng **một** nơi xếp hai lần). Hai nơi "gần trùng" (cùng kiểu, `PLACE_DECISION.md` §9.1) mà người dùng vẫn giữ là lựa chọn của họ: chỉ cảnh báo `near_duplicate`, không chặn. Kiểm "đúng giờ đẹp nhất" (hoàng hôn, bình minh, nhạc): nơi nào bộ xếp lịch đã bỏ ghim giờ để vừa ngày (cảnh báo `pin_dropped`) được ghi trong `DayResult.unpinned`, và mọi lần kiểm lại, kể cả lúc xác nhận, tôn trọng đúng quyết định đó, nên kế hoạch đã hiện ra là hợp lệ thì xác nhận được. Thêm một kiểm `hazard` (nơi bị thời tiết rất xấu hay thông báo `severe` loại khỏi ngày, xem §Điều kiện từng ngày). Trả `ok` + danh sách vi phạm, mỗi vi phạm có `physical: bool` và cái giá đã tính của từng cách sửa. Không phương án nào hợp lệ → trả về tầng Place Decision kèm nơi gây lỗi (`docs/PLACE_DECISION.md` §14, dòng "Planning báo không xếp được").

### ⓕ Độ vững — `robustness.py`

Nhiễu cố định trong config, không random: xuất phát trễ +15 / +30 phút; visit +20%; travel +25%; mưa theo xác suất dự báo. Mỗi kịch bản chạy lại thứ tự đã chọn của từng ngày và đếm số nơi bị mất (ngoài giờ mở, hoặc sau nó không kịp về điểm kết ngày; đệm là thứ hấp thụ trễ). Mưa không random: nơi phơi mưa ở ngày `rain_prob ≥ rain_high` tính là mất; không có dự báo thì bỏ kịch bản này và nói rõ. Ba mức — **Vững** (đủ đệm để chịu vài chậm trễ nhỏ), **Khả thi** (chạy được nếu phần lớn đúng giờ dự kiến), **Mong manh** (đúng về toán nhưng một chậm trễ nhỏ làm hỏng các điểm sau): Vững = mọi kịch bản mất ≤ `solid_max_lost`; Khả thi = các kịch bản `tier: small` mất ≤ `feasible_max_lost`; còn lại Mong manh. `travel_source = rough` → trần "Khả thi".

### ⓖ Mục tiêu và phương án — `objectives.py`, `variants.py`

**Nhịp độ và mục tiêu là hai thứ riêng.** Nhịp độ (`pace`: thong thả · cân bằng · đi nhiều) mô tả cường độ chuyến đi và đổi thành tham số: thời gian tham quan, số nơi mỗi ngày, thời gian nghỉ, độ lớn đệm, mức di chuyển chấp nhận. Mục tiêu mô tả tối ưu theo cái gì.

Năm mục tiêu: `least_travel`, `low_cost`, `weather_robust`, `diverse`, `preference_fit`. Chọn tối đa 3 bằng rule từ Trip State (pace; `budget_vnd` đã biết?; tháng mưa?; `soft_weights`) — không cố định trước.

```
for lodging in K+1 ứng viên:          # 6 + phương án không chỗ ở
    for obj in mục tiêu đã chọn:      # ≤ 3
        p = schedule(days(clusters, lodging, obj), obj)
        if validate(p).ok:
            score[(obj, lodging)] = obj.score(p), robustness(p)
best mỗi obj → 2–3 phương án; bỏ phương án trùng (cùng chỗ ở + cùng thứ tự mọi ngày)
```

21 lần dựng lịch mỗi lượt (K+1 chỗ ở × tối đa 3 mục tiêu), dùng chung một ma trận OSRM (toạ độ ứng viên nằm
trong CÙNG ma trận đó) và cache thứ tự trong ngày theo `(ngày, điểm mở, điểm đóng, tập nơi)` — đổi chỗ ở chỉ đổi
điểm mở/đóng ngày, không tính lại cụm hay chia ngày. Mỗi mục tiêu giữ tổ hợp (chỗ ở, lịch) tốt nhất riêng cho nó.
Ngân sách: **< 2 s** khi cache nóng, đo trong `evaluate.py`.

### ⓗ Dự phòng — `backup.py`

Nơi nhạy cảm = ngoài trời + ngày mưa xác suất cao · giờ `UNCERTAIN` / `OUTDATED` · sát giờ đóng · thuộc cụm xa. Thay thế lấy từ `backup_pool` (Decision đã kèm `for` + `reason`): cùng cụm, cùng nhóm, qua được constraint. Không có → nêu rõ "không có phương án thay".

## Chỗ ở không làm người dùng chờ

Crawl Maps mất giây đến chục giây, nên không chặn màn hình:

```
mở màn Planning → dựng ngay 2–3 phương án với anchor = base / entry_point   (nhanh, OSRM nóng)
                → song song: lodging_near(...) chạy nền, SSE event progress
                → có ứng viên → chấm lại K × mục tiêu → diff ("đổi anchor sang homestay X: −55 phút/ngày")
                → người dùng chọn chỗ ở, hoặc giữ nguyên
```

## Vòng người dùng sửa và góp ý

User Web chỉ nhận `act`, tất định, không gọi model cho mỗi nút/chip. Khi xác nhận Decision, Web yêu cầu `recommend` nội bộ một lần rồi mở màn Planning. “+ Thêm nơi” gửi `back` qua harness để về Decision trong cùng journey; lựa chọn được giữ. Contract và phiên ở `docs/AGENT_HARNESS.md`.

| Act | Việc | Chạy lại từ |
|---|---|---|
| `pick_variant(id)` | chọn một trong các phương án | — |
| `pick_lodging(id)`, `clear_lodging`, `set_lodging(text)` | chọn / bỏ / nhập tay chỗ ở (nhập tay → `geocode`) | ⓑ |
| `set_lodging_budget(max_per_night)` | đổi trần giá → crawl lại | ⓐ |
| `move_place(place, day)`, `reorder(day, order)` | đổi ngày / thứ tự | ⓒ ngày liên quan |
| `drop_place(place, reason?)` | bỏ khỏi lịch | ⓔ + `repair_day` |
| `add_from_backup(place, day)`, `swap(a, b)` | thêm / thay từ `backup_pool` | ⓒ–ⓔ ngày đó |
| `lock_slot(place)`, `unlock(place)` | ghim ngày / giờ | — |
| `set_pace`, `set_objective`, `set_day_window(day, start, end)` | đổi tham số | ⓑ |
| `relax(constraint, scope)` | nới **user** constraint, luôn kèm cái giá đã tính | ⓔ |
| `undo`, `redo` | về phiên bản khác | — |
| `confirm` | chốt → Plan Output | ⓔ + `place_live_status` |

`relax` không tồn tại cho physical constraint.

API Planning độc lập có `turn`: một call Agent → guard → act; lỗi dùng `policy.py`. Các ví dụ hiểu câu tự do của API này:

| Người dùng nói | Agent làm |
|---|---|
| "ngày 2 nhiều quá" | `drop_place` nơi có điểm xếp hạng Place Decision thấp nhất trong cụm xa nhất của ngày đó, hoặc hỏi một câu khi hai nơi sát điểm |
| "sáng muốn cà phê trước" | `reorder` ngày đó, nêu cái giá nếu phá giờ mở của nơi khác |
| "chỗ ở gần chợ đêm hơn" | đổi tâm vùng tìm → `lodging_near` lại → diff |
| "xa quá" (không nói nơi nào) | hỏi một câu: nơi nào, hay cả ngày nào |
| bỏ nhiều nơi qua nhiều lượt | dừng sửa lẻ, đề nghị quay về Place Decision chọn lại (`docs/PLACE_DECISION.md` §14) |
| "đổi hết đi" | không tự xoá; hỏi xác nhận, nêu hệ quả |

## Agent đề xuất nội bộ

Public API `PlanningProposal`, `run_proposal` và `Tools` dùng role `AGENT` chung qua runtime `agents`. Prompt/schema riêng nằm ở `proposal.py`; proposal không có lời chat `say`.

`Engine.recommend` dựng baseline tất định trước, gửi snapshot phương án, diagnostics, objective và fingerprint cho một lượt đề xuất; runtime chỉ retry vòng khoảng trắng tối đa một lần trong cùng deadline. Output chỉ gồm fingerprint, ID phương án đã có, act `move_place`/`reorder` và lý do tham chiếu ID diagnostics. Fingerprint hoặc ID không khớp bị từ chối.

Đề xuất chạy trên nháp; giữ membership, anchor, địa điểm role `locked` từ Decision và slot khóa trong Planning. Validator phải không có vi phạm; điểm tính bằng đúng `objectives.metrics/score` của objective đã cấu hình phải không kém baseline. Chỉ khi đạt các kiểm tra này mới lưu state đề xuất. Timeout, schema lỗi, hành động ngoài quyền hoặc lịch/điểm không đạt đều giữ baseline và ghi diagnostics. Replay log phiên không gọi lại LLM.

Agent nội bộ không chọn chỗ ở, đổi pace/day window, nới constraint, mở khóa, thay tập địa điểm hay confirm. Các việc đó cần act của người dùng và guard nghiệp vụ. Physical constraint không có đường nới.

## Guardrail

| Bất biến | Cách ép |
|---|---|
| Không xáo lịch âm thầm | `repair_day` phạt mỗi thay đổi so với phiên bản trước (trọng số trong config); mọi thay đổi đi qua diff |
| Nơi `locked` / anchor không bị dời | `repair_day` từ chối, lỗi nói rõ phải hỏi người dùng |
| Physical không nới | `validate` là nơi duy nhất kết luận pass / fail; không có act `relax` cho physical |
| Không bịa | mọi `place_id`, số phút, giá trong `say` phải có trong kết quả tool của phiên; số live phải mang `source` + `fetched_at` |
| Không nhận lịch chưa kiểm | `confirm` từ chối khi `validate` chưa `ok` |
| Lịch thô không được gắn "Vững" | `robustness` đọc `travel_source`, trần "Khả thi" |
| Live không thành tri thức lâu dài | `src/live` không có đường ghi `data/intel`; test khẳng định |
| Chỗ ở không vào corpus | `data/live/lodging/` tách riêng; `report_data_issue` không áp dụng cho chỗ ở |

## Plan Output

Kế hoạch phải trả lời được cả "vì sao chọn những nơi này" và "đã phải hy sinh gì để khả thi":

```text
Plan Output
├── variants       2–3 phương án: mục tiêu, lịch trình, điểm, độ vững, bảng đánh đổi giữa các phương án
├── chosen         phương án người dùng chốt
├── itinerary      theo ngày: nơi, giờ đến / đi, chặng (phút, mode), chờ, đệm, nghỉ, bữa ăn
├── route          hình lộ trình từng ngày (OSRM /route)
├── lodging        đã chọn + ứng viên khác, mỗi cái: tổng phút di chuyển cả chuyến, giá (hoặc unknown), amenities
├── cost           chi phí ước tính: vé / đồ uống + tiền phòng (khi biết giá)
├── travel_load    phút di chuyển mỗi ngày, chặng dài nhất
├── reasons        vì sao chọn những nơi này (gộp `decision_log`) và vì sao xếp như vậy
├── tradeoffs      đã hy sinh gì để khả thi
├── warnings       giờ `UNCERTAIN` / `OUTDATED`, mưa, thời tiết xấu, thông báo, đông khách, đóng cửa dịp Tết, giá tham khảo, chỗ ở chưa xác minh
├── day_conditions điều kiện từng ngày (khi có): thời tiết, loại ngày, mức đông, thông báo
├── crowd_tips     giờ vắng nhất của nơi đông, từ số liệu của chính nơi đó
├── uncertainty    phần nào là ước lượng, `travel_source`
├── robustness     mức + lý do + kịch bản làm hỏng
├── backups        phương án thay cho từng nơi nhạy cảm
└── provenance     mỗi số live kèm `source` + `fetched_at`
```

## CLI và API

| Lệnh | Việc |
|---|---|
| `python -m planning build <decision_output.json>` | in một lịch trình đã kiểm (`--out` ghi Plan Output dạng json) |
| `python -m planning variants <decision_output.json>` | in 2–3 phương án theo mục tiêu, kèm độ vững và dự phòng (`--weather forecast.json`) |
| `python -m planning lodging <decision_output.json>` | như trên, cộng chỗ ở cạnh tranh làm neo mỗi ngày; cần Chrome đã đăng nhập `gmaps` |
| `python -m planning serve [--port 8768]` | HTTP + SSE độc lập |
| `python -m planning evaluate` | 30 chuyến ẩn qua Decision → Planning → `data/planning/eval.json` (§Đo) |

`build` / `variants` / `lodging` / `evaluate` cần OSRM đang chạy để có số thật; không có thì rơi về ước lượng thô kèm cảnh báo (§Live Context).

User Web gọi Planning qua harness (`docs/AGENT_HARNESS.md`), từ Decision Output server đã xác nhận. API độc lập `serve` bind `127.0.0.1:8768`; danh sách dưới đây thuộc API này, gồm `turn` không được router harness cung cấp.

```
POST   /api/planning/sessions              {decision_session_id | decision_output}
GET    /api/planning/sessions/<id>
POST   /api/planning/sessions/<id>/act     tất định; 400 khi act sai (state không đổi)
POST   /api/planning/sessions/<id>/turn    SSE: say(delta|replace) · view · progress · done · error
GET    /api/planning/sessions/<id>/variants
GET    /api/planning/sessions/<id>/lodging tiến độ crawl + ứng viên đã chấm
GET    /api/planning/sessions/<id>/lodging/events  SSE tiến độ crawl nền
POST   /api/planning/sessions/<id>/confirm → Plan Output; 409 khi chưa hợp lệ
```

Lỗi: 400 act sai, 404 không có phiên, 409 sai phiên bản hoặc chưa chốt được. Event `progress` là phần thêm so với `decision` (báo crawl chỗ ở đang chạy).

Web: `web/src/user/planning/` (`types.ts`, `api.ts`, `planning.tsx` — `PlanningProvider` + `usePlanning()`) và `web/src/user/screens/Plan.tsx` ở `/app/plan`. Màn gồm: chọn hành trình + bảng đánh đổi · timeline từng ngày (giờ, chặng, phút di chuyển, đệm, nghỉ) kèm điều kiện ngày · bản đồ Google · chỗ ở · dự phòng của ngày (`backups.places` / `on_delay`, thay bằng `swap`) · ngăn Tối ưu · dòng báo mỗi lần sửa + hoàn tác · nút chốt · “+ Thêm nơi”. Thanh "Đã chọn" ở Chọn nơi gọi handoff và một lần proposal (`web/src/user/pd/decision.tsx` `toPlan`, `web/src/user/planning/api.ts` `runRecommend`); lịch ngầm trước khi xác nhận dùng `Engine.preview` qua harness (`docs/AGENT_HARNESS.md` §2). Chức năng từng màn: `docs/Role_Web_Functional_Design.md` §2.10.

## Cấu hình — `config/planning.yaml`

Một chỗ duy nhất cho mọi ngưỡng của Planning:

| Nhóm | Khoá |
|---|---|
| Di chuyển | `road_factor`, `rough_speed_kmh` (đường lui khi OSRM chết), `walk_km`, `walk_kmh` |
| Khung ngày | `default_days`, `day_start`, `day_end`, `leave_at` |
| Nhịp độ | `visit_key`, `per_day`, `buffer_min` (+ phụ phí `long_leg_min`, `buffer_extra_long`, `buffer_extra_uncertain`, `buffer_extra_rain`), `rest_min`, `max_consecutive_min` |
| Bữa ăn, buổi | `meals_per_day`, `meal_min`, `meal_windows`, `pins` |
| Cụm, ngày, thứ tự | `cluster_max_min`, `cluster_merge_min`, `fill_ratio`, `intra_leg_min`, `max_days`, `max_clusters`, `exact_n`, `improve_passes`, `weights` (`travel`, `overflow`, `count`, `closed`, `crowd`) |
| Mục tiêu, phương án | `max_variants`, `objective_order`, `objective_weights` (trộn lên `weights` khi chia ngày: `travel`, `exposed`, `repeat`, `pref_risk`) |
| Điều kiện ngày | `crowd_busy_pct`, `conditions` (`heavy_rain_mm`, `heavy_gust_kmh`, `severe_rain_mm`, `severe_gust_kmh`, `crowd_visit_pct`, `crowd_buffer_min`, `crowd_avoid_factor`, `closure_buffer_min`) |
| Độ vững | `rain_high`, `robustness` (kịch bản nhiễu có `tier` small / large, `solid_max_lost`, `feasible_max_lost`) |
| Dự phòng | `near_close_min`, `far_leg_min`, `backup_radius_min`, `backups_per_place` |
| Chỗ ở | `radius_km` theo mobility, `lodging_k`, `lodging_share`, `min_reviews`, `split_min`, `stay_min`, `lodging_pool`, `lodging_weights` (`pref`, `loc`, `price`, `rating`), `loc_ref_min` |
| Phiên | trọng số phạt của `repair_day`, `decision_url` |

`version` ở đầu file.

TTL từng nguồn live và endpoint OSRM nằm ở `config/live.yaml`, không nằm ở đây: `src/live` không được đọc config của `planning` (phụ thuộc một hướng).

Thêm `config/climate.yaml` (khí hậu Đà Lạt theo tháng), `config/holidays.yaml` (lễ Việt Nam), `config/events.yaml` (lễ hội, Noel, Tết) và `config/advisories.yaml` (thông báo thiên tai; mặc định rỗng). Ba file sau nhập tay và là toàn bộ sự thật: ngày không liệt kê là chưa biết, không phải bình thường.

## Test

| Mức | Nội dung |
|---|---|
| Unit | `cluster`, `days` (DP), `route` (vét cạn + 2-opt), `schedule` (chờ / đệm / nghỉ), `validate` (mỗi loại vi phạm), `robustness` (mỗi kịch bản), `lodging` (sàng), `objectives` — fixture thuần, không mạng |
| Fixture live | `travel_matrix`, `weather`, `lodging_near` lưu lại từ lần chạy thật (như `tests/fixtures/capture.py` của crawl, che tài khoản); test không gọi mạng |
| Golden | lịch của N chuyến mẫu; đổi thuật toán phải cập nhật golden có chủ ý |
| Bất biến | `src/live` không ghi `data/intel`; physical không có đường nới; `locked` không bị dời; `confirm` chặn khi chưa `ok`; `travel_source = rough` không được "Vững" |
| Live thật (`-m live`) | OSRM local, Open-Meteo, một lần crawl lodging — chạy tay, không trong CI |

## Đo — `python -m planning evaluate`

Dùng lại `config/eval_trips.yaml` (30 chuyến ẩn): Trip Understanding → Place Decision → `confirmed` → Planning.

| Chỉ số | Mục tiêu |
|---|---|
| Hard constraint violation trong lịch | 0 |
| Unsupported claim rate (`say` ngoài kết quả tool) | 0 |
| Feasible itinerary rate (tổ hợp Decision nói "khả thi" mà Planning xếp được) | cao; phần hụt là sai số ước lượng thô của Decision (`docs/PLACE_DECISION.md` §17) |
| Tỉ lệ Vững / Khả thi / Mong manh | báo cáo, chưa đặt ngưỡng trước pilot |
| Phút di chuyển so với baseline | baseline = nearest-neighbour + anchor `base`, không chọn chỗ ở. Thước đo "tối ưu" có thật |
| Chỗ ở giảm bao nhiêu phút mỗi ngày so với phương án không chỗ ở | báo cáo |
| Số lượt sửa trước `confirm` | giảm công sức |
| Độ trễ: dựng 21 phương án · crawl chỗ ở | < 2 s · báo cáo |

Hành vi agent không tất định nên đo bằng mô phỏng nhiều lần và so với `policy.py`, như `docs/PLACE_DECISION.md` §17; thêm số lần guardrail chặn, số tool-call mỗi lượt, độ trễ mỗi lượt.

## Giới hạn đã biết

- Thời gian di chuyển không có traffic thời gian thực; profile xe máy là profile ô tô nhân hệ số.
- Giá phòng là giá OTA tại thời điểm crawl; homestay ngoài OTA không có giá.
- Mặt lodging của Maps không liệt kê đủ theo khung bản đồ.
- Vét cạn chỉ trong giới hạn `max_days` / `max_clusters` / `exact_n`; vượt thì rơi về heuristic và gắn cờ.
- Chưa có User Profile dài hạn nên `preference_fit` chỉ dùng `soft_weights` của phiên.
- Giá và tiện nghi của chỗ ở đọc bằng quét văn bản thô trên thẻ Maps (không phải DOM đã dò kỹ): có thể trống hoặc
sai nếu Maps đổi cách hiển thị; ngày check-in / check-out chưa đặt qua bộ lọc của Maps.
- Thông báo thiên tai là file nhập tay (`advisories.yaml`); chưa có nguồn tự động nên rỗng không có nghĩa an toàn. Lễ hội phải được nhập từ thông báo chính thức. Ngưỡng thời tiết và hệ số đông khách là ước lượng, chờ chỉnh sau pilot.
- `place_live_status` (đóng cửa tạm, giờ ngày lễ) chưa gọi mạng: chưa chọn được nguồn. `confirm` chỉ gom lại cờ
`UNCERTAIN` / `OUTDATED` đã có.
- `repair_day` ép "ghim ngày" của nơi `locked`, không ép cứng "ghim giờ" (vị trí chính xác trong ngày) — chỉ phạt
lệch qua `repair_diff_weight`.
- `Trip` / `Schedule` sống trong RAM của tiến trình server, không ghi đĩa: một restart rebuild lại từ `decision` +
`states[0..position]` (gọi `prepare()` một lần rồi phát lại từng version qua `_relayout` / `_rebuild_variant`) —
tốn thêm một lượt dựng Trip (mạng OSRM / geocode đã có cache theo TTL của `live.cache`), không tốn thêm crawl chỗ ở
nếu TTL `lodging` (24h, `config/live.yaml`) còn hiệu lực.
- SSE `.../lodging/events` hiện poll nội bộ mỗi 50ms tới khi crawl xong hoặc tối đa 10s rồi vẫn phát `progress` với
candidates hiện có — chưa có callback trực tiếp từ thread nền; một `queue.Queue` giữa thread crawl và handler sẽ
thay được chỗ poll này.
- `decision_session_id` yêu cầu server của `decision` đang chạy ở `decision_url` (`config/planning.yaml`); không có
cơ chế retry / backoff — một lần lỗi mạng trả thẳng `ActionError` cho người dùng thử lại.
- Sau khi chỗ ở crawl xong, các phương án đã dựng **không** tự chấm lại theo K ứng viên chỗ ở ("chấm lại K × mục
tiêu → diff" ở §Chỗ ở không làm người dùng chờ chưa có): người dùng vẫn chọn được chỗ ở qua `pick_lodging` /
`set_lodging` và lịch xếp lại đúng, nhưng chưa có bảng so sánh "đổi sang chỗ ở X: −N phút/ngày" tự động. `act`'s
`diff` hiện chỉ có `scope`, chưa phải diff đầy đủ như §Guardrail đòi. Plan Output's `lodging.candidates` luôn `[]`
(chỉ `lodging.chosen` có dữ liệu). Không có đường nào trả kết quả sai, chỉ thiếu tính năng so sánh.
- `lodging_near` (câu nói tới một địa danh) đặt chỗ ở thủ công đúng địa danh đó (`set_lodging`), chưa tìm lại K ứng
viên chỗ ở quanh một tâm mới — cần sửa `lodging.py` / `build.py`.
- "Bỏ nhiều nơi qua nhiều lượt -> đề nghị quay về Place Decision" chỉ hoạt động trong kênh gõ chữ (`turn`); các act
`drop_place` gửi qua chip không bị chặn bởi `rethink_drops` -- Planning chưa có cơ chế `Pending`/câu hỏi mở như
`decision.Session` có.
- `python -m planning evaluate` đo lịch dựng được (tỉ lệ có lịch khả thi, phút tiết kiệm so với baseline, chỗ ở tiết
kiệm bao nhiêu phút/ngày, Vững/Khả thi/Mong manh, độ trễ) nhưng **không** mô phỏng hội thoại nhiều lượt với agent
thật: "số lần guardrail chặn, số tool-call mỗi lượt, độ trễ mỗi lượt" chưa đo được, giống khoảng trống ở
`src/decision/evaluate.py`. `confirmed` của mỗi chuyến ẩn là shortlist hạng cao nhất tự động chấp nhận (không có
người dùng thật chọn/bỏ), nên số liệu phản ánh "Planning có xếp được thứ Decision xếp hạng cao không", không phản
ánh một phiên sửa thật.
- Baseline của `evaluate` là nearest-neighbour trên đúng nhóm nơi theo ngày của phương án đã chọn. Thứ tự của
Planning tối ưu cả giờ mở cửa, chờ và cửa sổ thời gian, không chỉ phút di chuyển, nên trên một số chuyến phút di
chuyển có thể dài hơn baseline; `avg_saved_vs_baseline_pct` có thể âm và được báo đúng dấu.
