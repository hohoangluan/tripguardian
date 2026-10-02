# Planning & Validation + Live Context — Thiết kế chi tiết

Vị trí trong luồng hệ thống: `docs/ARCHITECTURE.md` §9–14. Đầu vào: `docs/PLACE_DECISION.md` §15. File này là thiết kế chi tiết để triển khai.

## Mục tiêu

Từ **tập địa điểm đã xác nhận** của Place Decision, dựng 2–3 **phương án lịch trình** đã kiểm tra, mỗi phương án tối ưu một mục tiêu khác nhau, kèm **chỗ ở** được chọn sao cho cả chuyến đi ít di chuyển nhất, rồi để người dùng sửa, góp ý và chốt.

Đích: tối ưu có thật (đo được so với baseline), kiểm tra tất định (lịch trông hợp lý là chưa đủ), và giải thích được từng lựa chọn — kể cả cái đã phải hy sinh.

## Phạm vi

Trong: chia ngày; gom cụm; thứ tự trong ngày; khớp giờ mở cửa; chọn thời gian tham quan theo nhịp độ; thời gian đệm và nghỉ; đề xuất chỗ ở (tra live theo yêu cầu); điểm vào / ra thành phố; kiểm tra cuối; độ vững; kế hoạch dự phòng; 2–3 phương án theo mục tiêu; vòng người dùng sửa / góp ý / chọn; Live Context (thời gian di chuyển, thời tiết, chỗ ở, geocode, mặt trời, lễ).

Ngoài: booking và thanh toán; điều hướng turn-by-turn; traffic thời gian thực; giá phòng từ API OTA; nhiều thành phố; cộng tác nhóm; đưa chỗ ở vào Place Intelligence.

## Nguyên tắc

1. **Chỗ ở không bao giờ vào Place Intelligence.** Nó được tra live theo từng request, chỉ sống trong phiên, mang `source` + `fetched_at` (`ARCHITECTURE.md` §1).
2. **Chỗ ở là biến trong bài tối ưu**, không phải danh sách gợi ý rời. Mỗi ứng viên được chấm bằng cách làm anchor đầu / cuối ngày rồi xếp lại cả lịch và đo.
3. **Mọi bước tất định.** Cùng input → cùng output. Không random. Agent chỉ hiểu câu tự do và giải thích; mọi thứ cần đúng là rule.
4. **Physical constraint không bao giờ nới ngầm.** Không có đường code nào nới nó.
5. **Không bịa.** Thiếu dữ liệu → `unknown` + gắn cờ, không điền giá trị. Thiếu quán ăn trong tập đã xác nhận → chừa khoảng trống, không tự thêm địa điểm.
6. **Số live luôn có nguồn và thời điểm.** Thời gian di chuyển, giá phòng, thời tiết đều gắn nhãn ước lượng / tham khảo, không phải Fact.
7. **Không xáo lịch âm thầm.** Mỗi thay đổi hiện qua diff; nơi đã khóa không bị dời.

## Ranh giới module

```
src/live/                      Live Context — gọi mạng, đọc-ghi cache; KHÔNG có đường ghi data/intel
  __init__.py                  public API: travel_matrix, route_shape, weather, lodging_near, geocode,
                               sun_times, holidays
  cache.py                     cache theo key + TTL → data/live/<source>/
  osrm/                        ma trận thời gian (/table) + hình lộ trình (/route), service local
  weather/                     Open-Meteo: dự báo theo giờ trong tầm; ngoài tầm → khí hậu theo tháng
  lodging/                     crawl mặt lodging của Maps theo request
  geocode/                     text → toạ độ (Nominatim)
  sun.py                       mọc / lặn, công thức NOAA, tính local
  holidays.py                  config/holidays.yaml

src/planning/                  Planning & Validation — rule tất định
  model.py settings.py         kiểu dữ liệu; ngưỡng từ config/planning.yaml
  lodging.py                   ⓐ vùng tìm → sàng → K ứng viên
  cluster.py days.py route.py  ⓑ gom cụm, chia ngày (DP), thứ tự trong ngày
  schedule.py                  ⓒ khớp giờ mở, visit theo pace, đệm, nghỉ
  validate.py                  ⓓ kiểm tra cuối, fail-closed
  robustness.py                ⓔ độ vững 3 mức
  backup.py                    ⓕ dự phòng từ backup_pool
  objectives.py variants.py    điểm theo mục tiêu; dựng 2–3 phương án
  repair.py scope.py           repair_day; phạm vi chạy lại
  output.py                    Plan Output
  session.py                   phiên có phiên bản, undo
  agent.py guard.py policy.py  một call mỗi lượt chữ; guard; policy từ khóa khi agent lỗi
  engine.py server.py          HTTP + SSE, cổng 8768
  evaluate.py                  mô phỏng offline
```

Phụ thuộc một hướng: `planning` → `live`, `decision`, `trip`, `corpus.serving`, `corpus.ontology` (chỉ qua `__init__.py`; RULE §2). `live` không biết `planning`. `decision` không đổi.

Dữ liệu:

| Thư mục | Ghi bởi | Nội dung |
|---|---|---|
| `data/live/{osrm,weather,lodging,geocode}/` | `src/live` | cache theo request, có TTL, mỗi mục mang `source` + `fetched_at` |
| `data/planning/` | `src/planning` | phiên, phiên bản lịch, Plan Output, `eval.json` |
| `data/intel/`, `data/serving/`, `data/gmaps/` | chỉ offline corpus | Planning chỉ đọc |

## Đầu vào

Decision Output nguyên dạng (`PLACE_DECISION.md` §15): `confirmed` (id, role `anchor | locked | selected`, visit minutes, flags, relaxed), `backup_pool` (kèm `for` + `reason`), `wishlist`, `trip_context` (bản chụp Search Input), `decision_log`, `feasibility`.

Thêm vào Trip State (`TRIP_UNDERSTANDING.md` §4, §11): `entry_point`, `exit_point` kiểu `Base` (text + `place_id` hoặc toạ độ sau geocode) — nơi người dùng vào / ra thành phố (bến xe, sân bay, tự lái). `src/trip/questions.py` thêm một câu khi chưa biết. Thiếu → ngày đầu / cuối chỉ bị cắt theo `arrive_at` / `leave_at`, gắn cờ "ước lượng ngày đầu / cuối kém chắc".

## Live Context

Mọi hàm trả `None` khi không có dữ liệu; không bịa. `src/live` không import `corpus.aggregate` / `corpus.serving` để ghi, và test khẳng định không có đường ghi tới `data/intel`, `data/serving`, `data/gmaps`.

| Nguồn | Public API | Cách lấy | TTL | Khi lỗi |
|---|---|---|---|---|
| `osrm/` | `travel_matrix(points, mode)`, `route_shape(points, mode)` | OSRM local trên OSM Việt Nam; `/table` cho ma trận, `/route` cho hình đường của lịch đã chốt | 7 ngày | rơi về ước lượng thô của Planning (`travel.rough_minutes`: đường chim bay × `road_factor` ÷ `rough_speed_kmh`); plan gắn `travel_source = rough` + cảnh báo; độ vững trần "Khả thi" |
| `weather/` | `weather(lat, lng, dates)` | Open-Meteo forecast theo giờ (trong tầm 16 ngày): mưa mm, xác suất, nhiệt. Ngoài tầm → `config/climate.yaml` theo tháng | 3 giờ / tĩnh | `None` → ngày đó không xét mưa, gắn cờ "chưa biết thời tiết" |
| `lodging/` | `lodging_near(center, radius_km, check_in, check_out, price_max)` | crawl **mặt lodging của Maps** theo request (xem dưới) | 24 giờ | danh sách rỗng → anchor = `base` / `entry_point`, nói rõ "chưa tra được chỗ ở" |
| `geocode/` | `geocode(text)` | Nominatim, 1 req/s, User-Agent riêng của dự án | 30 ngày | `None` → hỏi lại người dùng |
| `sun.py` | `sun_times(date, lat, lng)` | công thức NOAA, không mạng, không thêm dependency | — | — |
| `holidays.py` | `holidays(dates)` | `config/holidays.yaml` (lễ Việt Nam, nhập tay) | — | — |

### OSRM

Thiết lập một lần mỗi máy, `scripts/osrm_setup.sh` + mục trong `README.md`: tải `vietnam-latest.osm.pbf` (Geofabrik) → `osrm-extract` (profile `car`) → `osrm-partition` → `osrm-customize` → `osrm-routed --max-table-size 300`.

Mode: OSM không có profile xe máy chuẩn. Dùng profile `car` rồi nhân `mode_factor` (`config/live.yaml`: `car 1.0`, `motorbike 0.95`). Chặng ngắn hơn `walk_km` tính đi bộ bằng khoảng cách × `road_factor` ÷ tốc độ đi bộ. Mọi số này hiển thị là **ước lượng**, không nói là thời gian thật của một nhà cung cấp nào.

Một ma trận mỗi lượt cho tập điểm = `confirmed` + K chỗ ở + `entry_point` + `exit_point`. Khoảng 20 điểm → 400 cặp, một request. Mọi phương án dùng chung ma trận đó.

### Chỗ ở (crawl live)

Dùng mặt **"Khách sạn"** của Maps, không phải search địa điểm thường: đặt check-in = ngày đầu chuyến, check-out = ngày cuối (`nights = days − 1`), đặt trần giá bằng bộ lọc giá của Maps. Thẻ trả về: `name`, `fid`, `lat/lng`, `rating`, `reviews`, `price_per_night`, `amenities`.

- Mặt lodging của Maps **bỏ qua khung bản đồ** (`CORPUS_SPEC.md` §Phạm vi) nên không liệt kê đủ được. Với live-only thì không sao: chỉ cần top ứng viên quanh một khu.
- Nhiều homestay Đà Lạt không lên OTA nên không có giá, có khi không có thẻ. Thẻ không giá vẫn **được giữ**, `price = unknown`, không bị trần giá loại, hiện "chưa có giá".
- `price_per_night` là giá OTA tại thời điểm crawl → mang `source` + `fetched_at`, nhãn "giá tham khảo, kiểm lại khi đặt". Không phải Fact.
- `start_date` chưa biết (chỉ có `month`) → crawl không đặt ngày; giá bỏ trống, gắn cờ.
- Dùng lại code crawl đúng ranh giới: `src/corpus/crawl/__init__.py` hiện không export gì nên deep import là vi phạm RULE §2. Thêm public API tối thiểu — `open_sessions`, `LoginRequired`, `maps_search(ctx, query, limit, at)` — rồi `src/live/lodging` gọi qua đó và chỉ ghi `data/live/lodging/`. Không copy code Playwright.
- `LoginRequired` hoặc captcha → trả rỗng kèm lý do; Planning chạy tiếp ở phương án không chỗ ở.

### Trạng thái vận hành theo thời điểm

`place_live_status(place)` (đóng cửa tạm, giờ ngày lễ) chỉ chạy ở bước xác nhận cuối, best-effort, timeout mỗi nơi, giới hạn số nơi mỗi phiên. Không tra được → giữ cảnh báo "kiểm tra lại trước chuyến" như giờ `UNCERTAIN` / `OUTDATED` đã có. Không bao giờ sửa giờ trong corpus.

## Thuật toán

### ⓐ Ứng viên chỗ ở — `lodging.py`

1. **Vùng tìm:** tâm trọng số của các nơi đã chọn (trọng số = `visit typical`); tách tối đa 2 tâm nếu đường kính cụm > `split_min`. Thêm vùng quanh `entry_point` khi ngày đầu / cuối gấp.
2. `lodging_near(center, radius_km, check_in, check_out, price_max)` với `radius_km` theo `mobility`, `price_max = lodging_share × budget_vnd ÷ nights` khi `budget_vnd` đã biết.
3. **Sàng tất định:** không geocode được / ngoài `area` → bỏ. Dưới `min_reviews` → bỏ (chống rác, không phải tiêu chí chất lượng). Hard filter áp được cho chỗ ở (`parking`, `steep_or_stairs`) chỉ lọc khi `amenities` có bằng chứng; không có → `unknown`, hiện "chưa xác minh", không lọc.
4. Cắt còn K (`lodging_k = 6`) theo khoảng cách thô có trọng số tới các cụm — rẻ, trước khi xếp lịch thật.
5. Luôn giữ thêm **phương án "không chỗ ở"** (anchor = `base` / `entry_point`) để so sánh thật.

### ⓑ Gom cụm và chia ngày — `cluster.py`, `days.py`

- Khung ngày: ngày đầu từ `arrive_at` (hoặc `entry_point` + travel tới chỗ ở); ngày cuối đến `leave_at` − travel tới `exit_point`; ngày giữa `day_start..day_end`.
- Cụm: `area` của serving record trước, rồi chia / gộp theo **đường kính thực** (ma trận OSRM) với ngưỡng `cluster_max_min`.
- Gán cụm → ngày: số ngày ≤ `max_days` (7), cụm ≤ `max_clusters` (8) → **DP trên tập con**, tất định. Hàm phí = tổng di chuyển + phí vi phạm giờ mở + lệch số nơi mỗi ngày theo pace + phí "cụm ngoài trời vào ngày mưa xác suất cao". Vượt giới hạn → rơi về gán tham lam, gắn cờ.
- Ghim: anchor giờ cố định ghim ngày + giờ; nơi chỉ mở vài ngày trong chuyến ghim ngày; `locked` cùng ngày người dùng đã chỉ định không đổi.

### ⓒ Thứ tự trong ngày — `route.py`

- Mỗi ngày mở và kết ở chỗ ở; ngày đầu mở ở `entry_point`, ngày cuối kết ở `exit_point`.
- n ≤ `exact_n` (7) nơi mỗi ngày → **vét cạn permutation** có cắt tỉa theo giờ mở (≤ 5040) → tối ưu thật. n lớn hơn → nearest-neighbour + 2-opt + or-opt. Cả hai tất định.
- Buổi: `pins` (`config/planning.yaml`: `sunset_view`, `cloud_hunting`, `live_music`) + `sun_times` → hoàng hôn / đêm ghim cuối ngày; sương / bình minh ghim đầu ngày.
- Bữa ăn: `meals_per_day`. Có quán ăn trong `confirmed` → chèn vào khung trưa / tối. Không có → chừa khoảng trống "ăn trưa (tự chọn)", không thêm địa điểm.

### ⓓ Giờ, tham quan, đệm, nghỉ — `schedule.py`

Visit theo pace: thong thả → `long`, cân bằng → `typical`, đi nhiều nơi → `min`. Đến sớm → `wait`; quá giờ đóng → vi phạm. Đệm = `buffer_min[pace]` + phụ phí theo độ không chắc (mưa, chặng dài, giờ `UNCERTAIN`). Nghỉ chèn theo pace, và chặn "đi liên tục quá `max_consecutive_min` mà không nghỉ".

### ⓔ Kiểm tra cuối — `validate.py`

Đúng `ARCHITECTURE.md` §11: ngày đi · giờ mở cửa · chồng lấn · thời gian di chuyển · anchor · ngân sách (gồm tiền phòng khi đã biết giá) · hard constraint · địa điểm trùng. Trả `ok` + danh sách vi phạm, mỗi vi phạm có `physical: bool` và cái giá đã tính của từng cách sửa. Không phương án nào hợp lệ → trả về tầng Place Decision kèm nơi gây lỗi (`PLACE_DECISION.md` §14, dòng "Planning báo không xếp được").

### ⓕ Độ vững — `robustness.py`

Nhiễu cố định trong config, không random: xuất phát trễ +15 / +30 phút; visit +20%; travel +25%; mưa theo xác suất dự báo. Mỗi kịch bản xếp lại và đếm số nơi bị mất. Ba mức Vững / Khả thi / Mong manh theo ngưỡng. `travel_source = rough` → trần "Khả thi".

### ⓖ Mục tiêu và phương án — `objectives.py`, `variants.py`

Mục tiêu (`ARCHITECTURE.md` §10): `least_travel`, `low_cost`, `weather_robust`, `diverse`, `preference_fit`. Chọn tối đa 3 bằng rule từ Trip State (pace; `budget_vnd` đã biết?; tháng mưa?; `soft_weights`).

```
for lodging in K+1 ứng viên:          # 6 + phương án không chỗ ở
    for obj in mục tiêu đã chọn:      # ≤ 3
        p = schedule(days(clusters, lodging, obj), obj)
        if validate(p).ok:
            score[(obj, lodging)] = obj.score(p), robustness(p)
best mỗi obj → 2–3 phương án; bỏ phương án trùng (cùng chỗ ở + cùng thứ tự mọi ngày)
```

21 lần dựng lịch mỗi lượt, dùng chung một ma trận OSRM. Ngân sách: **< 2 s** khi cache nóng, đo trong `evaluate.py`.

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

Chạm chip / nút = `act`, tất định, không gọi model. Gõ chữ = một call agent → plan of acts → guard → cùng các act đó. Agent lỗi, timeout hoặc JSON hỏng → `policy.py` từ khóa làm lượt đó.

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

Agent quyết phần con người:

| Người dùng nói | Agent làm |
|---|---|
| "ngày 2 nhiều quá" | `drop_place` nơi có điểm xếp hạng Place Decision thấp nhất trong cụm xa nhất của ngày đó, hoặc hỏi một câu khi hai nơi sát điểm |
| "sáng muốn cà phê trước" | `reorder` ngày đó, nêu cái giá nếu phá giờ mở của nơi khác |
| "chỗ ở gần chợ đêm hơn" | đổi tâm vùng tìm → `lodging_near` lại → diff |
| "xa quá" (không nói nơi nào) | hỏi một câu: nơi nào, hay cả ngày nào |
| bỏ nhiều nơi qua nhiều lượt | dừng sửa lẻ, đề nghị quay về Place Decision chọn lại (`PLACE_DECISION.md` §14) |
| "đổi hết đi" | không tự xoá; hỏi xác nhận, nêu hệ quả |

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

`ARCHITECTURE.md` §14, thêm phần chỗ ở và phương án:

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
├── warnings       giờ `UNCERTAIN` / `OUTDATED`, mưa, giá tham khảo, chỗ ở chưa xác minh
├── uncertainty    phần nào là ước lượng, `travel_source`
├── robustness     mức + lý do + kịch bản làm hỏng
├── backups        phương án thay cho từng nơi nhạy cảm
└── provenance     mỗi số live kèm `source` + `fetched_at`
```

## API và web

`python -m planning serve` → `127.0.0.1:8768`, web qua proxy `/api/planning`.

```
POST   /api/planning/sessions              {decision_session_id | decision_output}
GET    /api/planning/sessions/<id>
POST   /api/planning/sessions/<id>/act     tất định; 400 khi act sai (state không đổi)
POST   /api/planning/sessions/<id>/turn    SSE: say(delta|replace) · view · progress · done · error
GET    /api/planning/sessions/<id>/variants
GET    /api/planning/sessions/<id>/lodging tiến độ crawl + ứng viên đã chấm
POST   /api/planning/sessions/<id>/confirm → Plan Output; 409 khi chưa hợp lệ
```

Lỗi: 400 act sai, 404 không có phiên, 409 sai phiên bản hoặc chưa chốt được. Event `progress` là phần thêm so với `decision` (báo crawl chỗ ở đang chạy).

Web: `web/src/user/screens/Itinerary.tsx` đổi sang gọi `/api/planning`; `web/src/user/planner.ts` (ước lượng chạy trong trình duyệt của bản thử) **xoá**. Màn gồm: tab phương án + bảng đánh đổi · timeline từng ngày (giờ, chặng, phút di chuyển, đệm, nghỉ) · panel chỗ ở (tổng phút di chuyển cả chuyến, giá hoặc "chưa có giá", "chưa xác minh") · diff mỗi lần sửa · cảnh báo và độ không chắc · dự phòng · nút chốt. Ô gõ chữ tự do như `/app/shortlist`.

## Cấu hình — `config/planning.yaml`

`version`; `road_factor`, `rough_speed_kmh` (đường lui khi OSRM chết), `walk_km`, `walk_kmh`; `default_days`, `day_start`, `day_end`, `leave_at`; `visit_key`, `per_day`, `buffer_min` (+ phụ phí `long_leg_min`, `buffer_extra_long`, `buffer_extra_uncertain`), `rest_min`, `max_consecutive_min`; `meals_per_day`, `meal_min`, `meal_windows`; `pins`; `cluster_max_min`, `cluster_merge_min`, `fill_ratio`, `intra_leg_min`, `max_days`, `max_clusters`, `exact_n`, `improve_passes`; `weights` (`travel`, `overflow`, `count`, `closed`). Các phase sau thêm: `radius_km` theo mobility, `lodging_k`, `lodging_share`, `min_reviews`, `split_min`, kịch bản nhiễu của độ vững + ngưỡng 3 mức, trọng số từng mục tiêu, trọng số phạt của `repair_day`.

TTL từng nguồn live và endpoint OSRM nằm ở `config/live.yaml`, không nằm ở đây: `src/live` không được đọc config của `planning` (phụ thuộc một hướng).

Thêm `config/climate.yaml` (khí hậu Đà Lạt theo tháng) và `config/holidays.yaml` (lễ Việt Nam).

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
| Feasible itinerary rate (tổ hợp Decision nói "khả thi" mà Planning xếp được) | cao; phần hụt là sai số ước lượng thô của Decision (`PLACE_DECISION.md` §17) |
| Tỉ lệ Vững / Khả thi / Mong manh | báo cáo, chưa đặt ngưỡng trước pilot |
| Phút di chuyển so với baseline | baseline = nearest-neighbour + anchor `base`, không chọn chỗ ở. Thước đo "tối ưu" có thật |
| Chỗ ở giảm bao nhiêu phút mỗi ngày so với phương án không chỗ ở | báo cáo |
| Số lượt sửa trước `confirm` | giảm công sức |
| Độ trễ: dựng 21 phương án · crawl chỗ ở | < 2 s · báo cáo |

Hành vi agent không tất định nên đo bằng mô phỏng nhiều lần và so với `policy.py`, như `PLACE_DECISION.md` §17; thêm số lần guardrail chặn, số tool-call mỗi lượt, độ trễ mỗi lượt.

## Các phase

Mỗi phase chạy được và test được riêng.

| Phase | Nội dung |
|---|---|
| P1 | `src/live` nền: `cache`, `osrm`, `geocode`, `sun`, `holidays`; `scripts/osrm_setup.sh`; fixture |
| P2 | Trip State: `entry_point` / `exit_point` + một câu hỏi + sửa `docs/TRIP_UNDERSTANDING.md` |
| P3 | Planning lõi: `cluster` → `days` → `route` → `schedule` → `validate` → `output`; CLI `python -m planning build <decision_output.json>` in lịch. Chưa web, chưa agent |
| P4 | `robustness`, `backup`, `objectives`, `variants` |
| P5 | `live/weather`, `live/lodging`, `lodging.py`, chấm K × mục tiêu, event `progress` |
| P6 | `session` (phiên bản, undo), `act`, `repair_day`, `scope`, `server` + SSE |
| P7 | `agent`, `guard`, `policy` |
| P8 | Web: `Itinerary` thật; xoá `planner.ts` |
| P9 | `evaluate.py`, đo, cập nhật `README.md` + `docs/log/DEV_LOG.md` |

Sau P3 đã có lịch thật dùng được bằng CLI — bằng chứng sớm, trước khi làm phần tốn công.

## Tài liệu phải sửa

| Tài liệu | Sửa gì |
|---|---|
| `docs/ARCHITECTURE.md` §9.1 | "Hệ thống không gợi ý chỗ ở" → chỗ ở không vào Place Intelligence; Planning tra live theo request, chỉ sống trong phiên |
| `docs/ARCHITECTURE.md` §18.2 | thêm tool `travel_matrix`, `lodging_near`, `route_shape` |
| `docs/PLACE_DECISION.md` §5 | bỏ dòng "không có chỗ ở trong ứng viên" → trỏ sang spec này |
| `docs/UX_Design_Brief.md` | "Chỗ ở không được gợi ý" → cách hiển thị chỗ ở live (chưa xác minh, giá tham khảo) |
| `docs/specs/CORPUS_SPEC.md` §Phạm vi | giữ "chỗ ở ngoài corpus", nói rõ Planning tra live |
| `docs/TRIP_UNDERSTANDING.md` §4, §11 | thêm `entry_point`, `exit_point` |
| `AGENTS.md`, `README.md` | thêm spec này vào bảng tài liệu; thêm bước thiết lập OSRM và lệnh `python -m planning` |

`config/queries.yaml` **không** thêm category chỗ ở: crawl live là đường riêng, không phải phase của corpus.

## Giới hạn đã biết

- Thời gian di chuyển không có traffic thời gian thực; profile xe máy là profile ô tô nhân hệ số.
- Giá phòng là giá OTA tại thời điểm crawl; homestay ngoài OTA không có giá.
- Mặt lodging của Maps không liệt kê đủ theo khung bản đồ.
- Vét cạn chỉ trong giới hạn `max_days` / `max_clusters` / `exact_n`; vượt thì rơi về heuristic và gắn cờ.
- Chưa có User Profile dài hạn nên `preference_fit` chỉ dùng `soft_weights` của phiên.
