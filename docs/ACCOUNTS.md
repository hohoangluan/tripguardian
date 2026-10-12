# Tài khoản

Đăng nhập, phiên, khách, hồ sơ, avatar, xóa tài khoản và liên kết Google Calendar. Code: `src/accounts/` (public API ở `__init__.py`), HTTP ở `src/harness/server.py`, Postgres ở `src/db/` + `migrations/`. Web: `web/src/user/account.ts`, `screens/Auth.tsx`, `screens/Account.tsx`.

## 1. Quy tắc

- `/app` cần một phiên: tài khoản Google (đăng nhập **chỉ bằng Google**) hoặc phiên khách (§7); landing `/` vẫn public.
- Hồ sơ là **prior**, không phải fact: chuyến hiện tại luôn thắng (`docs/TRIP_UNDERSTANDING.md` §17).
- Chỉ lưu hash SHA-256 của token phiên; refresh token Google mã hóa bằng Fernet (`TOKEN_ENC_KEY`).
- Admin xem được mọi dữ liệu người dùng; không ai gõ fact địa điểm qua tài khoản.

## 2. Đăng nhập

```text
GET /api/auth/google/start?next=/app/...      → 302 Google (code + PKCE S256, scope openid email profile)
GET /api/auth/google/callback?state&code     → kiểm state, đổi code, verify id_token (google-auth)
                                              → upsert users theo google_sub → auth_sessions → cookie → 302 next
POST /api/auth/logout                         → xóa phiên, xóa cookie
```

- `state` lưu ở bảng `oauth_states` (10 phút, dùng một lần) và trong cookie `tg_oauth` (`Path=/api/auth`); callback chỉ nhận khi hai cái khớp. Callback duy nhất là `GOOGLE_REDIRECT_URI`, dùng chung cho đăng nhập và Calendar (`purpose: login | calendar`).
- `next` chỉ nhận đường dẫn trên site (bắt đầu bằng `/`, không `//`, không `\`); sai thì về `/app`.
- Cookie `tg_session`: `HttpOnly; SameSite=Lax; Path=/`, `Secure` khi `APP_BASE_URL` là https, 30 ngày; dùng lại sau hơn 1 giờ thì gia hạn 30 ngày và gửi lại cookie.
- Lỗi đăng nhập về `/app/login?error=denied|state|failed`; tài khoản `status ≠ active` không đăng nhập được.
- Lần đầu: màn đồng ý điều khoản và chính sách dữ liệu (bắt buộc tích), ghi `profiles.consents.{terms,privacy} = {version, at}`. Phiên bản hiện tại là `TERMS_VERSION` trong `src/accounts/service.py`; đổi phiên bản thì mọi người được hỏi lại.
- Walk-through không có Google: `TG_TEST_LOGIN=1` bật `GET /api/auth/test/login?email=&name=&next=`; route tự tắt khi `APP_BASE_URL` là https.

Web: `account.ts` đọc `GET /api/harness/me`; mọi lời gọi `/api/harness/*` trả 401 đưa về màn đăng nhập rồi Google trả về đúng trang đang mở.

## 3. Hồ sơ và avatar

| API | Việc |
|---|---|
| `GET /api/harness/me` | `{id, email, name, avatar, role, home_city, usual_mobility, usual_companions, consents, needs_consent, calendar, terms_version}`; mở app cũng kết thúc trạng thái tạm im thông báo |
| `POST /api/harness/me/consent` | `{version}` = phiên bản hiện tại |
| `PATCH /api/harness/me` | `display_name` ≤ 60, `home_city` ≤ 80, `usual_mobility ∈ {motorbike, car, walk}` (`walk` = không dùng xe riêng; hệ thống không đặt xe công nghệ), `usual_companions ∈ {solo, partner, friends, kids, parents}`; `null` / `""` xóa trường |
| `POST /api/harness/me/avatar` | Body là file ảnh, tối đa 5 MB, JPEG / PNG / WebP mà Pillow mở được; cắt vuông, 256 px, bỏ EXIF, lưu `data/accounts/avatars/<uuid>.webp`; file gốc không giữ |
| `GET /api/harness/avatars/<key>` | Ảnh WebP; chưa có avatar riêng thì `avatar` là ảnh Google |
| `DELETE /api/harness/me` | `{confirm: true}`; web hỏi hai bước |

Prior cho Trip: khi tạo hành trình, `usual_mobility` / `usual_companions` vào Trip State với `source = profile` (hiện ✎ "từ hồ sơ"); lời người dùng trong chuyến ghi đè. `home_city` chưa vào Trip: điểm xuất phát của Trip là một điểm có tọa độ chọn từ ô tìm kiếm.

## 4. Xóa tài khoản

Thu hồi token Google trước, rồi xóa `profiles`, `calendar_links`, `push_subscriptions`, `notification_prefs`, `auth_sessions`, `oauth_states`, file avatar và mẫu dài hạn của Trip. `users` giữ dòng với `deleted_at`, `status = deleted`, email / tên / `google_sub` bị xóa. `journeys`, `events`, `feedback`, `trips`, `notifications` giữ lại với `user_id = NULL`. Đăng nhập lại bằng cùng Google tạo tài khoản mới.

## 5. Liên kết Google Calendar

`GET /api/auth/google/start?purpose=calendar&next=` (cần đang đăng nhập) xin thêm scope `calendar.app.created` với `access_type=offline`, `prompt=consent`, `include_granted_scopes=true`; chỉ gọi khi người dùng bấm "Thêm vào Google Calendar". Callback chỉ nhận khi Google trả refresh token, có đúng scope, và cùng tài khoản Google đã đăng nhập; xong về `next?calendar=connected`, lỗi về `next?calendar=failed`. Ngắt kết nối thu hồi token (`docs/COMPANION.md` §Calendar).

## 6. Postgres

Container `tripguardian-pg` (`postgres:16`, `127.0.0.1:5433`, volume `tripguardian-pgdata`). `./run.sh db` tạo / khởi động container, tạo role và database (`python -m db bootstrap`, cần `POSTGRES_PASSWORD`) rồi `python -m db migrate`. `./run.sh db-backup` → `data/backup/pg/<ngày>.sql.gz`, giữ 14 bản. Cổng 5432 trên máy là Postgres khác, không dùng.

- `tg_app` (`DATABASE_URL`) ghi; `tg_analytics` (`DATABASE_URL_READONLY`) chỉ `SELECT`, không đọc `auth_sessions`, `oauth_states`, `calendar_links`, `push_subscriptions`.
- Migration là file SQL đánh số trong `migrations/`, áp một lần mỗi file trong transaction, ghi vào `schema_migrations`; chạy lại không làm gì.
- Test đánh dấu `pg` chỉ chạy khi có `TEST_DATABASE_URL`; mỗi test dùng một schema tạm.

## 7. Khách

Vào `/app` không cần đăng nhập: nút `Lên lịch chuyến của bạn` ở landing (hoặc `Dùng thử, không cần tài khoản` ở `/app/login`) gọi `POST /api/auth/guest` (cùng origin). Server tạo một dòng `users` với `kind = 'guest'` (không email, không Google) cùng `profiles`, và cookie `tg_session` **24 giờ** trượt: cùng cookie, cùng kiểm tra chủ sở hữu như tài khoản. Đã có phiên thì trả `{started: false}`. Một địa chỉ (`CF-Connecting-IP`, rồi `X-Forwarded-For`, rồi địa chỉ kết nối) mở tối đa 20 khách mỗi giờ (`GUEST_PER_IP_HOUR` ở `src/harness/server.py`), quá thì 429.

| | Tài khoản | Khách |
|---|---|---|
| Lập chuyến (hiểu → chọn → lịch), phản hồi | có | có, như nhau |
| Số chuyến | không giới hạn, giữ lâu dài | không giới hạn, xóa khi hết phiên |
| Hồ sơ làm prior, học qua các chuyến (`remember`) | có (học theo đồng ý) | không: không prior, `remember = false` |
| Chuyến của tôi | mọi chuyến | các chuyến của phiên này |
| Hôm nay, thông báo, Google Calendar, avatar, sửa hồ sơ | có | không: server trả `403 {"error": "guest"}`, web hiện "cần đăng nhập Google" |
| Điều khoản | màn đồng ý lần đầu | không chặn (`needs_consent = false`) |

- **Dọn:** `Accounts.purge_guests()` xóa khách mà mọi phiên đã hết hạn, khi có khách mới và mỗi giờ bằng luồng nền của `run()`. Xóa `trips` (kéo theo điểm dừng, check-in) rồi dòng `users`; `journeys`, `events`, `feedback` ở lại với `user_id = NULL`, như khi xóa tài khoản (§4). Đăng xuất hoặc `DELETE /api/harness/me` của khách xóa ngay (`drop_guest`).
- **Khách đăng nhập Google:** callback chuyển các hành trình của khách sang tài khoản (`Harness.adopt`) rồi xóa dòng khách; sự kiện `auth.guest_adopted`.
- `GET /api/harness/me` có `guest`; `new_users` của analytics chỉ đếm `kind = 'user'`.
- Web: `startGuest()` ở `account.ts`; `screens/Guest.tsx` (ghi chú khách ở Chuyến của tôi và Phản hồi, trang Hôm nay / Thông báo cần đăng nhập, trang Khách thay Hồ sơ); thanh bên ẩn Hôm nay và Thông báo.
