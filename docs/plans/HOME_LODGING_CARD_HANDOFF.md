# Bàn giao — trang chủ, bạn bè, thẻ chỗ ở (2026-10-13)

File làm việc tạm (RULE §0.1): xong việc thì gộp phần còn giá trị vào tài liệu chính thức rồi xóa file này.

## 0. Đọc trước khi làm

- Working tree **dùng chung** nhiều session; **không commit, không `git add -A`**. Mọi việc dưới đây chưa commit.
- Deploy: `./run.sh prod` (backup DB → migrate → build vào `web/.deploy-build` → chép `web/dist` → khởi động lại harness + public → smoke). Trước khi chạy, kiểm **không có session nào đang build**: `pgrep -af "vite build --outDir .deploy-build|prod_assets"`. Hai build cùng lúc dẫm lên nhau (build hỏng `ENOENT …UserApp-*.css`; site live không sao).
- Sửa backend (`src/`) thì phải chạy `./run.sh prod` đầy đủ để **khởi động lại harness**; chỉ chép frontend sẽ chạy frontend mới trên backend cũ (đã gặp: tab Chỗ ở trống).
- Người dùng thấy giao diện cũ → nhắc Ctrl+Shift+R (`sw.js` không cache, nhưng trình duyệt giữ bundle cũ).
- Test hỏng sẵn, **không phải của việc này**: `tests/harness/test_{dispatch,tools}.py` (`no open question 'meal:…'`), `tests/planning/test_planning_{golden,lodging_golden,variants}.py`, `tests/trip/test_vibes.py` (2 test an toàn ảnh: ảnh tải lên chưa được mã hóa lại trước khi tới model, ảnh quá nhiều pixel chưa bị chặn sớm; session khác đang viết, **đã lên production**).

## 1. Đã xong và đã deploy (đừng làm lại)

Tài liệu chính thức đã cập nhật: `docs/ACCOUNTS.md` §8 §9, `docs/Role_Web_Functional_Design.md` §6, `docs/ANALYTICS.md` (`theme_open`, `journey.copy`), `docs/PLANNING.md` (danh sách chỗ ở theo trang), `docs/log/DEV_LOG.md` (`home-social`, `lodging-browse`).

| Phần | Ở đâu |
|---|---|
| Khung app toàn màn hình theo mẫu `ui_mock_for_design/designs/homepage` (màu mận / hồng của luồng), trang Dành cho bạn, Đã xem gần đây; bỏ Hôm nay khỏi menu | `web/src/user/home/{Frame,dialogs,themes}.tsx`, `screens/{Discover,Recent}.tsx`, `css/home.css`, ảnh `web/public/img/home/` |
| Cột Bạn bè ẩn / hiện (`tg.friends.open`), khi ẩn còn icon cạnh "Chào, …" | `home/Frame.tsx` (`useFriendsOpen`, `FriendsIcon`) |
| Nút "Lên lịch chuyến của bạn" → chat Tìm hiểu, chuyển cảnh `tg-trip-start` | `screens/Discover.tsx` (`plan`) |
| Bạn bè (nickname, lời mời, online/offline, tin nhắn, gửi lịch trình, "Lấy về" = bản sao) | `src/social/`, `src/harness/server.py`, `dispatch.py` (`owns`, `copy`), `migrations/004_social.sql`, `web/src/user/social.ts` |
| Đã lưu (nơi + chủ đề) và Đã xem gần đây theo tài khoản | `src/accounts/library.py`, `web/src/user/store.ts` |
| Tab Chỗ ở: lưới **mọi** chỗ ở (1499), trang 18, cuộn tải thêm; không ô tìm, không "cần chọn", không "Bạn ở đâu?" | `src/planning/engine.py` (`lodging_options(decision, offset, limit)`), `lodging.py` (`anywhere(limit=None)`), `src/harness/dispatch.py` (`lodging`, `_page`), `web/src/user/screens/Lodging.tsx` |
| Lịch trình chưa có chỗ ở: 3 gợi ý, "Chọn" = `pick_lodging` | `web/src/user/screens/plan/parts.tsx` (`NoHotel`), `css/itinerary.css` |

## 2. Đang làm — đồng bộ thẻ chỗ ở với thẻ các tab khác

Yêu cầu: thẻ ở tab Chỗ ở phải **giống hệt** thẻ Ăn uống (`web/src/user/ui/PlaceCard.tsx`), không để dòng trống ("Chưa có lý do rõ", "Chưa có giá"); tab "Chỗ ở" có số đếm như "Ăn uống 546". Chưa sửa dòng code nào cho phần này.

Thẻ chuẩn (`PlaceCard` + `src/decision/cards.py` `card()`): nhãn loại cụ thể · "Hợp nhất" · nút tim · "Ảnh: …" | tên · `khu · ★ điểm` | ≤ 3 dòng "vì sao hợp" | hộp **Đánh đổi** | hàng số liệu (thời lượng · giá · `≈ N′ từ trung tâm Đà Lạt` · `Trust`) | nút Thêm.

Thẻ chỗ ở hiện tại (`Lodging.tsx` `LodgingCard`) khác: nhãn chung "Chỗ ở", địa chỉ đầy đủ thay khu, lý do chỉ từ điều người dùng đã nói (`pref_fit`) nên thường trống, không có phút tới trung tâm, không có `Trust`, không có tim.

Dữ liệu đo trên corpus (1509 bản ghi `stay`):
- loại cụ thể có đủ (`identity.category`: "Khách sạn 3 sao", "Lưu trú nhà dân", …); khu có đủ (`identity.area`); điểm ở `provenance.rating_trend.recent_mean` (1499).
- đặc điểm VERIFIED, n ≥ 2: `service_attitude=good` 1382, `cleanliness=clean` 1335, `value_for_money=good` 1253, `noise=quiet` 864, `cozy_decor` 733, `scenic_view` 261, `parking=easy` 211, `nature` 195; mặt xấu: `parking=hard` 65, `noise=loud` 39, `service_attitude=poor` 15, `value_for_money=poor` 11, `cleanliness=dirty` 9.
- `details.known_for.headline` **trống** với mọi chỗ ở.
- giá/đêm: **chỉ 741/1524** (xem §3).

Cách làm đã chốt (backend sinh đủ trường, frontend chỉ hiển thị):
1. `src/planning/tools.py` `create_engine`: đang truyền `labels=decision_settings().labels`; truyền thêm `polarity`, `center`, `near_min`, `speed_kmh`, `road_factor` từ cùng `decision.load_settings()` (API công khai).
2. `src/planning/engine.py` `_lodging_card` thêm: `category`, `area`, `rating` (fallback `recent_mean`), `why` = `fit` (điều người dùng muốn) rồi điểm mạnh VERIFIED n ≥ 2 theo n giảm dần ("Yên tĩnh, theo 864 người" — chữ theo `phrase()` của `planning/lodging.py`), tối đa 3, có thêm dòng "Gần trung tâm Đà Lạt, ≈N phút (ước tính)" khi N ≤ `near_min`; `tradeoffs` = mặt xấu VERIFIED (giá trị cuối trong `polarity`), "Chưa biết ngân sách; giá khoảng …/đêm" khi ngân sách chưa biết, `unverified`; `location {center, minutes}` (công thức `src/decision/geo.py` `minutes(d_km, mobility, cfg)`: km thẳng × `road_factor` / `speed_kmh`); `confidence {level, reason}` như `_confidence` không có điều muốn: high ≥ 40 người viết, medium ≥ 10.
   - Điểm mạnh: giá trị đầu trong `polarity`, hoặc `present` / `suitable` / `good` / `included` của các đặc điểm trong `stay_features` (`config/ontology.yaml`), **trừ** `steep_or_stairs`, `cold`.
3. `web/src/user/planning/types.ts` `LodgingCandidate`: thêm các trường trên. `Lodging.tsx` `LodgingCard`: dựng lại theo đúng markup của `PlaceCard` (cùng class `tg-pc*`, thêm tim `toggleSaved`, `Trust`), giá hiển thị `…/đêm`.
4. `web/src/user/screens/Explore.tsx` dòng tab Chỗ ở: hiện `total` (cần đưa `total` từ `LodgingPanel` lên, hoặc gọi `lodgingOptions` một lần ở Explore).
5. Test: `tests/planning/test_planning_lodging_rank.py` thêm ca: thẻ có `why` khi người dùng chưa nói gì, có `location.minutes`, có `confidence`; mặt xấu vào `tradeoffs`.

## 3. Tiếp theo — bổ sung giá chỗ ở từ Google Maps

- Giá/đêm chỉ đến từ thẻ trong **danh sách khách sạn** của kết quả tìm Maps: `src/corpus/crawl/gmaps/search.py` `price_vnd(card_text)` → `data/gmaps/list/dalat_stay.json` (`price_vnd`, `price_at`) → `observe/gmaps/extract.py` `listed_price` → serving `operation.price_per_night` (`serving/record.py` `_night`).
- Thiếu giá: **783** mục của `dalat_stay.json`. Trang chi tiết của chúng đã crawl (`data/gmaps/places/<fid>/place.json`) nhưng `price` trống: crawler trang chi tiết không đọc ô giá phòng.
- Việc tiếp: thử 3 trang chi tiết thiếu giá xem Maps có hiện giá/đêm không (Maps chỉ hiện giá khi có phòng trống cho ngày mặc định), rồi mới viết bước crawl đọc giá từ trang chi tiết và ghi vào cùng chỗ (`price_vnd`, `price_at`). Theo memory: captcha do người dùng giải, mỗi nguồn một module / thư mục riêng, tách lane, không chạy `aggregate` / `serving` / `build` song song với crawl của session khác.
- Sau khi có giá: `python -m corpus aggregate` → serving → `python web/scripts/export_snapshot.py` → `./run.sh prod`.

## 4. Kiểm chứng nhanh

```sh
export TEST_DATABASE_URL=$(.venv/bin/python -c 'from dotenv import dotenv_values; print(dotenv_values(".env")["DATABASE_URL"])')
PYTHONPATH=src .venv/bin/python -m pytest -q tests/social tests/accounts tests/planning/test_planning_lodging_rank.py tests/harness/test_harness_server.py
cd web && node_modules/.bin/tsc --noEmit -p tsconfig.json
```

Xem giao diện với dữ liệu thật mà không đụng DB live: tạo schema tạm (`CREATE SCHEMA stage_x` + `python -m db migrate` với `options=-csearch_path=stage_x,public`), chạy `python -m harness serve --port 8795` với `DATABASE_URL` đó, `APP_BASE_URL=http://127.0.0.1:5199`, `TG_TEST_LOGIN=1`, và `HARNESS_PORT=8795 vite --port 5199`; đăng nhập thử qua `/api/auth/test/login?email=…&next=/app`. Xong thì tắt và `DROP SCHEMA stage_x CASCADE`.
