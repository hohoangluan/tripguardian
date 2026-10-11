# Đang đi, Google Calendar và thông báo

Phần đi cùng người dùng sau khi lịch đã chốt. Code: `src/companion/` (chuyến, check-in, gợi ý, Calendar), `src/notify/` (thông báo), HTTP ở `src/harness/`. Web: `web/src/user/screens/Today.tsx`, `today.ts`, `notify.ts`, `screens/Inbox.tsx`, `public/sw.js`. Cấu hình: `config/companion.yaml`, `config/notifications.yaml`.

## 1. Quy tắc

- Không ép: check-in là tự nguyện. Không có trạng thái "lỡ"; điểm không check-in vẫn là `planned`, nghĩa là chưa biết. Đánh giá chỉ là nút Hợp / Không hợp trên thẻ, không popup.
- Gợi ý chỉ lấy từ serving index; thiếu bằng chứng thì giữ `unknown`. Hard constraint của chuyến vẫn áp, fail-closed.
- Check-in và thông báo không phải bằng chứng về địa điểm và không ghi Place Intelligence. "Tới nơi thấy khác thông tin" đi qua nút Báo sai như mọi nơi khác.
- Không gì tự đổi kế hoạch: thêm nơi, điều chỉnh, ghi Calendar đều cần người dùng xác nhận.

## 2. Chuyến và điểm dừng

Khi `planning.confirm` commit, harness gọi `Companion.sync`: bảng `trips` (một dòng mỗi hành trình, `plan_hash`) và `trip_stops` (mỗi mục `visit` của itinerary, giờ đến / rời theo `Asia/Ho_Chi_Minh`). Chốt lại kế hoạch thì điểm chưa đến được dời theo lịch mới, điểm không còn trong lịch bị xóa, điểm đã check-in hoặc đã bỏ qua giữ nguyên. Hành trình chốt trước khi có bảng này được tạo chuyến ở lần mở Hôm nay đầu tiên.

## 3. Màn Hôm nay

Route `/app/today?journey=<id>[&stop=<id>]`. Mở được khi hành trình có `outputs.planning` (router `route_companion`, thiếu thì 409).

| API | Việc |
|---|---|
| `GET /api/harness/sessions/<id>/today?day=` | Ngày đang xem (mặc định ngày hôm nay của chuyến, nếu không thì ngày 1), điểm dừng và trạng thái, check-in gần nhất, `tight`, cảnh báo của lịch, điều kiện ngày, trạng thái Calendar |
| `POST …/companion {operation: checkin, stop_id \| place_id}` | Đã đến; `place_id` cho "Tôi đang ở nơi khác" (nơi phải có trong serving) |
| `POST …/companion {operation: skip, stop_id, reason?}` | Lý do tùy chọn: `far, crowded, pricey, dislike, tired, weather, other` |
| `POST …/companion {operation: rate, stop_id, value: 1 \| -1 \| null}` | Hợp / Không hợp / bỏ chọn |
| `POST …/companion {operation: add, place_id, day, confirmed: true}` | Planning `add_from_backup` rồi confirm; chỉ nơi trong backup pool của Decision (gợi ý gần đây mang `addable`); Planning từ chối thì 400 và lịch cũ giữ nguyên |
| `POST …/companion {operation: adjust, option_id, confirmed: true}` | Một phương án đang được đề xuất (§5), qua Planning act rồi confirm; confirm lỗi thì act được undo |
| `GET …/companion/suggest?place=&similar=1` | Gợi ý §4 |

Trước khi đến, thẻ điểm dừng hiện giờ, giờ mở, cảnh báo của lịch nhắc tên nơi đó. Bấm Đã đến mở bảng "Ở đây" (bên phải; dưới 900 px là sheet dưới đáy). Trên màn rộng, check-in gần nhất tự mở lại bảng này.

## 4. Gợi ý "Ở đây"

`companion/suggest.py`, hàm thuần trên serving record:

- **Chơi gì ở đây**: feature nhóm `experience` có giá trị `VERIFIED` / `OUTDATED` và bằng chứng, cái chuyến này muốn (`soft_weights` dương) lên trước, tối đa `suggest_count`. Web hiện kèm trích dẫn và clip từ snapshot.
- **Lưu ý thực tế**: `entry_fee, wait_time, booking_needed, parking, toilet, cash_only` có giá trị; `UNCERTAIN` ghi "chưa chắc".
- **Theo giờ thực tế**: bình minh / hoàng hôn tính bằng `live.sun_times` cho nơi có `sunset_view` / `cloud_hunting`; mức đông chỉ hiện khi nơi có bảng giờ đông của Google (`crowd_by_time`).
- **Gần đây**: thời gian đi ước tính (đường thẳng × `road_factor` / tốc độ theo phương tiện) ≤ `nearby_max_min`; đi tới, ở `visit_minutes.short`, quay lại vừa thời gian trước điểm kế tiếp (hoặc trước `day_end`); không đóng cửa theo giờ đã xác nhận (giờ chưa có thì "chưa xác nhận"); qua hard filter (`unknown` bị loại, trừ filter `unknown_policy: flag` thì giữ và gắn cờ); không nằm trong lịch, không bị bỏ với lý do `dislike`. Xếp theo `decision.preference_fit`, rồi gần hơn trước; tối đa `nearby_count`.
- **Nơi tương tự ở gần**: như Gần đây, cùng `category_group`; chỉ khi người dùng bấm "Đông quá hoặc không như kỳ vọng".

## 5. "Phần còn lại hơi chật"

Check-in hôm nay muộn hơn giờ dự kiến ≥ `tight_threshold_min` và ngày đó còn điểm chưa đến → web hiện một dòng trung tính "Phần còn lại hơi chật · Xem cách điều chỉnh". Phương án lấy từ `backups.on_delay` của Plan Output cho ngày đó (bỏ điểm đó, `option_id = drop:<place_id>`); người dùng chọn và xác nhận thì mới đổi.

## 6. Google Calendar

Một calendar riêng do app tạo cho mỗi chuyến ("TripGuardian · Đà Lạt dd–dd/MM"), mỗi điểm dừng có giờ một event: giờ đến / rời, địa chỉ, cảnh báo nhắc tên nơi, link `APP_BASE_URL/app/today?stop=<id>`, `reminders: {useDefault: false, overrides: []}`.

| API | Việc |
|---|---|
| `GET /api/harness/calendar/preview?journey=` | `{state: none \| synced \| drifted, connected, calendar: {create, summary}, changes: [{op: create \| update \| delete, stop, after?}], preview_hash}` |
| `POST /api/harness/calendar/apply {journey, preview_hash}` | Chỉ áp đúng bản đã xem: hash khác thì 409 kèm `preview` mới. Áp tuần tự; lỗi giữa chừng thì phần đã áp được ghi, trả `failed` + `not_done`, không tự thử lại |
| `POST /api/harness/calendar/disconnect {delete_calendar}` | Thu hồi token; chỉ xóa các calendar khi người dùng chọn |

Chưa kết nối → 409 kèm link xin quyền (`docs/ACCOUNTS.md` §5). Kế hoạch đổi mà Calendar đã đồng bộ → `state = drifted`; web chỉ hiện "Lịch Google khác kế hoạch hiện tại · N thay đổi [Xem]", không nhắc lại, không tự đồng bộ. Bảng: `calendar_sync` (calendar, hash kế hoạch đã đồng bộ, bản xem trước), `calendar_events` (event của từng điểm).

## 7. Thông báo

Ít, đúng lúc, giọng "TripGuardian / bạn", nhiều biến thể; không bao giờ "bạn đã lỡ", "bạn chưa check-in", đếm ngược giả hay so sánh với người khác. Kênh: web push (PWA) và Hộp thông báo `/app/inbox`; mọi thông báo đã gửi đều có trong hộp.

| `kind` | Khi nào |
|---|---|
| `plan_unfinished` | 24 giờ sau khi có shortlist mà chưa chốt, một lần |
| `book_ahead` | 10:00, 3 ngày trước chuyến, nếu có nơi `booking_needed = yes` (VERIFIED / OUTDATED) |
| `eve_of_trip` | 20:00 tối hôm trước; dự báo đọc lúc gửi |
| `day_brief` | 7:30 mỗi ngày đi |
| `checkin_hint` | Giờ đến dự kiến của 2 điểm đầu chuyến |
| `golden_hour` | 45 phút trước hoàng hôn / bình minh ở nơi có `sunset_view` / `cloud_hunting` trong lịch ngày đó |
| `weather_change` | Kiểm mỗi 3 giờ trong ngày đi: khả năng mưa (Open-Meteo) ≥ `rain_alert`, còn điểm ngoài trời hôm nay và lịch có phương án dự phòng; một lần mỗi ngày |
| `post_trip` | 10:00 ngày sau khi về |
| `paused` | Sau 3 thông báo liên tiếp không được mở; rồi im cho tới khi người dùng tự mở app |

Luật (`notify.decide`): loại bị tắt → bỏ; đang tạm im → bỏ; quá hạn hiệu lực → bỏ; rơi vào 22:00–7:00 → dời tới 7:00, hết hiệu lực trước đó thì bỏ; trước chuyến tối đa 1 / ngày, trong chuyến tối đa 3 / ngày. Mọi chỗ trống của câu lấy từ dữ liệu thật: biến thể thiếu dữ liệu không được dùng, không còn biến thể nào thì bỏ (`skip_reason = no_data`). Mẫu câu nằm ở `config/notifications.yaml`, người duyệt mới sửa; model không viết câu lúc gửi. Khi mỗi biến thể của một loại đã gửi ≥ `bandit_min_sends`, biến thể được chọn bằng Thompson sampling theo phần thưởng "mở rồi có thao tác trong `open_window_h` giờ" (`docs/ANALYTICS.md`).

Worker: `python -m notify run [--once]` (mỗi phút; `./run.sh start` / `prod` chạy nó). Mỗi lượt: lập lại thông báo của chuyến có `plan_hash` mới (hủy cái chưa gửi, không gửi lại khóa đã gửi), kiểm dự báo mỗi 3 giờ, gửi cái đến hạn. Push trả 404 / 410 thì xóa subscription.

Web: chỉ xin quyền sau khi chốt kế hoạch, bằng thẻ "Nhận vài lời nhắc trong chuyến?" ở Hôm nay, có nút "Không, cảm ơn" (không hỏi lại). Hồ sơ có bật / tắt từng loại, tạm im, và hướng dẫn "Thêm TripGuardian vào màn hình chính" cho iPhone (chỉ hướng dẫn). `sw.js` hiện thông báo; bấm vào thì đánh dấu đã mở và mở `url?n=<id>`.

| API | Việc |
|---|---|
| `GET /api/harness/push/key` | Khóa VAPID public |
| `POST /api/harness/push/subscribe {subscription}`, `/push/unsubscribe {endpoint}` | Subscription của trình duyệt (endpoint phải https) |
| `GET /api/harness/notifications` | Hộp thông báo, mới nhất trước |
| `POST /api/harness/notifications/<id>/open {action?}` | Đã mở; đặt lại chuỗi bỏ qua |
| `GET / PATCH /api/harness/me/notification-prefs` | `{enabled_kinds, paused}` |

Điện thoại vẫn nhận trang tải app ở mọi trang người dùng, nên hiện tại push chỉ đăng ký được từ trình duyệt máy tính.
