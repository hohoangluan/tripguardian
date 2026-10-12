# Kế hoạch — Tài khoản, Đang đi, Thông báo, Admin Analytics

File làm việc tạm (RULE §0.1). Chốt với người dùng 2026-10-08; một session khác thực hiện. Làm xong bước nào thì gộp phần đã ship vào tài liệu chính thức (§10) và gạch bước đó ở §5. Xong hết thì xóa file này.

## 0. Đọc trước khi làm

- `RULE.md`, `AGENTS.md`, `docs/ARCHITECTURE.md`, `docs/AGENT_HARNESS.md`, `docs/Role_Web_Functional_Design.md`.
- **Working tree dùng chung, nhiều session đang sửa.** Không commit trừ khi người dùng bảo; nếu được bảo, chỉ commit file của mình bằng index tạm (`GIT_INDEX_FILE`), không `git add -A`, không `git commit -a`.
- `web/dist` là site đang chạy thật (`./run.sh prod`, tripguardian.visioncare-host.uk). Build kiểm thử ra `outDir` tạm, không ghi đè `dist`.
- Cổng **5432** trên máy là một Postgres **không phải của dự án** (nghe ở `0.0.0.0`, không thấy container). Không dùng, không đụng.
- Playwright dùng chromium-1169, bản ghim 1.52.0 (headless_shell bị treo trên máy này).
- Mỗi bước ở §5 phải xong kiểm chứng của nó trước khi sang bước sau.

## 1. Quyết định đã chốt

| Chủ đề | Quyết định |
|---|---|
| Đăng ký | Bắt buộc có tài khoản mới vào `/app`. Landing vẫn public. Bỏ chế độ khách (`continueAsGuest`) |
| Đăng nhập | **Chỉ Google** ở đợt này. Email/mật khẩu làm sau, khi người dùng báo. Bỏ các nút Zalo / Facebook / Apple / TikTok khỏi màn đăng nhập |
| Lưu trữ | Tài khoản, hồ sơ, hành trình, event, thông báo lưu ở **Postgres** của dự án. Bỏ tài khoản giả lập trong localStorage |
| Hồ sơ | Avatar, tên hiển thị, thành phố xuất phát, phương tiện hay dùng, hay đi với ai. Mọi trường đều tùy chọn và chỉ là **prior** cho Trip; chuyến hiện tại luôn thắng |
| Google Calendar | Người dùng đã đăng ký OAuth app. Chức năng: chỉ xuất lịch vào một calendar riêng của app. Event không có reminder. **Mọi lần ghi (tạo / sửa / xóa) cần người dùng xác nhận trên bản xem trước.** Không tự đồng bộ |
| Đang đi | Người dùng bấm **Đã đến** trên app để nhận gợi ý tại chỗ và gần đây. Không ép: không đánh dấu điểm "bị lỡ", không trách móc, không streak |
| Thông báo | Có, theo kiểu Duolingo: ít, đúng lúc, giọng vui, nhiều biến thể câu. **Không** học kiểu làm người dùng thấy có lỗi. Kênh: web push (PWA) + hộp thông báo trong app |
| Giọng | Giọng "TripGuardian / bạn" như landing. Chưa làm mascot |
| Admin | Toàn quyền **xem** mọi dữ liệu người dùng (transcript, phiên, event). Vẫn không gõ giá trị fact cho địa điểm |
| Analytics | Server **private** riêng: `python -m analytics serve`, cổng `:8770`, chỉ bind `127.0.0.1`. Đọc Postgres bằng role chỉ-đọc |

## 2. Hiện trạng (đã kiểm tra 2026-10-08)

- `web/src/user/account.ts`: tài khoản giả lập, mọi thứ nằm trong localStorage, mật khẩu không được lưu. `screens/Auth.tsx`, `screens/Account.tsx` dùng nó.
- Harness (`src/harness/`):
  - `ThreadingHTTPServer`, `MAX_BODY = 65536`.
  - Phiên lưu ở `data/harness/sessions/<id>.json` (116 file). Store có giao diện nhỏ: `new / lock / get / save / append_feedback`.
  - Receipt **không có thời điểm**; log Planning không có `at`; chỉ log Decision có `at`.
  - Feedback ở `data/harness/feedback.jsonl` (8 dòng, gần như chỉ có điểm `fit`).
  - Ai có `journey_id` cũng đọc được hành trình đó.
  - `POST /sessions` nhận `user_id` do client tự gửi.
- Trip `ProfileStore` (`src/trip/infrastructure/profile.py`): mẫu dài hạn lưu file ở `data/trip/profiles/<user_id>.json`. Đang tắt bằng `patterns.enabled: false`.
- Proxy:
  - `web/server.mjs` (prod) chỉ public `/api/harness/*`, mọi `/api/*` khác bị chặn.
  - Vite dev proxy `/api/harness` → 8769, `/api` → 8765 (review).
- Admin: `Analytics.tsx` là khung tĩnh. `Sessions.tsx` chỉ đọc localStorage.
- Đã có sẵn trong `.venv`: Pillow 12.3. Chưa có: `psycopg`, `cryptography`, `pywebpush`, `google-auth`.
- Corpus có feature trải nghiệm kèm bằng chứng (`config/ontology.yaml` nhóm `experience`, `service`, `effort`, `operation.visit_duration`). Live có OSRM và Open-Meteo. Planning có `backups` / `on_delay`.

## 3. Kiến trúc

```text
web /app ──► /api/auth/*, /api/harness/*  (harness :8769, public qua server.mjs)
               ├─ auth, me, calendar, push, notifications, events  → accounts / companion / notify (public API)
               └─ trip · decision · planning · companion (journey)
web /admin ─► /api/analytics/* (analytics :8770, private) ──► Postgres (role chỉ-đọc)
notify worker (python -m notify run) ──► Postgres, live (thời tiết), web push
```

| Package mới | Trách nhiệm |
|---|---|
| `src/db/` | Pool kết nối (`psycopg` 3 + `psycopg_pool`, sync), runner migration, đọc `DATABASE_URL` |
| `src/accounts/` | Google OAuth, phiên đăng nhập, hồ sơ, avatar, xóa tài khoản, liên kết Calendar (token mã hóa) |
| `src/companion/` | Chế độ Đang đi: `trips` / `trip_stops`, check-in, gợi ý tại chỗ và gần đây, điều chỉnh phần còn lại của ngày, xem trước và áp thay đổi Calendar |
| `src/notify/` | Lập lịch thông báo, template, giới hạn, giờ yên lặng, tự tạm dừng, gửi web push, hộp thông báo |
| `src/analytics/` | Server private chỉ đọc: số liệu và danh sách phiên cho Admin |

Phụ thuộc một chiều, chỉ qua `__init__.py`:

```text
db        ──► (không gì)
accounts  ──► db
companion ──► db, accounts, planning, decision, corpus.serving, live
notify    ──► db, accounts, companion, live
harness   ──► trip, decision, planning, agents, accounts, companion, notify, db
analytics ──► db
```

Không module nào trong số trên ghi Place Intelligence. Check-in và thông báo không phải bằng chứng về địa điểm. "Tới nơi thấy khác thông tin" đi qua `corpus.review.reports` như nút Báo sai.

**Env mới trong `.env`** (thêm vào `.env.example`, không commit giá trị):
`DATABASE_URL`, `DATABASE_URL_READONLY`, `APP_BASE_URL`, `TOKEN_ENC_KEY` (Fernet), `VAPID_PUBLIC_KEY`, `VAPID_PRIVATE_KEY`, `VAPID_SUBJECT`. Đã có sẵn trong `.env` (người dùng đăng ký): `GOOGLE_CLIENT_ID`, `GOOGLE_CLIENT_SECRET`, `GOOGLE_REDIRECT_URI`. `.env.example` chưa có ba khóa này; thêm vào với giá trị rỗng.

**Google OAuth đã đăng ký:**
- **Callback duy nhất:** `GOOGLE_REDIRECT_URI = https://tripguardian.visioncare-host.uk/api/auth/google/callback`. Đăng nhập và kết nối Calendar dùng **chung** callback này; `state` (lưu phía server, gắn cookie ngắn hạn) mang `purpose: login | calendar` và `next`. Đọc URI từ env, không ghép từ `APP_BASE_URL`.
- **Đường dẫn là `/api/auth/*`, không nằm dưới `/api/harness/*`.** Vì vậy:
  - `web/server.mjs` phải proxy thêm `/api/auth/*` sang harness :8769 (hiện chỉ public `/api/harness/*`).
  - Vite dev thêm proxy `/api/auth` → 8769, đặt trước `/api`.
  - Harness phục vụ các route `/api/auth/*`. Các API khác của tài khoản vẫn ở `/api/harness/*`.
- **Dev local:** Console mới có URI prod. Muốn đăng nhập ở `http://127.0.0.1:5173` thì người dùng phải thêm `http://127.0.0.1:5173/api/auth/google/callback` vào Console, rồi `.env` dev đặt `GOOGLE_REDIRECT_URI` tương ứng. Nếu không thì thử đăng nhập thật trên domain prod.
- **Hỏi người dùng trước A1 / A5:** Google Calendar API đã bật trong project chưa; consent screen đã khai scope `calendar.app.created` chưa; app đang ở Testing hay Production. Ở Testing: tối đa 100 test user, refresh token hết hạn sau 7 ngày.

## 4. Postgres

- **Container riêng:** `postgres:16`, tên `tripguardian-pg`, chỉ mở `127.0.0.1:5433`, volume `tripguardian-pgdata`. `run.sh` thêm lệnh `db` (khởi động container nếu chưa chạy) và `db-backup` (`pg_dump` vào `data/backup/pg/<date>.sql.gz`, giữ 14 bản).
- **Role:** `tg_app` có quyền ghi; `tg_analytics` chỉ có `SELECT`.
- **Migration:** file SQL đánh số trong `migrations/` cùng runner `python -m db migrate`. Không dùng Alembic.

Bảng (chỉ nêu cột chính; mọi bảng có `created_at timestamptz default now()`):

| Bảng | Cột chính |
|---|---|
| `users` | `id uuid pk`, `email citext unique`, `google_sub text unique`, `display_name`, `avatar_key`, `role text check (user, admin)`, `status`, `last_login_at`, `deleted_at` |
| `auth_sessions` | `token_hash bytea pk` (sha256 của token), `user_id`, `expires_at`, `user_agent`, `last_seen_at` |
| `profiles` | `user_id pk`, `home_city`, `usual_mobility`, `usual_companions`, `consents jsonb` (điều khoản / chính sách: phiên bản + thời điểm) |
| `calendar_links` | `user_id pk`, `refresh_token_enc bytea`, `scopes text[]`, `calendar_id`, `connected_at`, `revoked_at` |
| `journeys` | `id text pk`, `user_id uuid null`, `stage`, `revision`, `envelope jsonb` (sessions, outputs, snapshots, receipts y như file hiện tại), `app_version`, `updated_at` |
| `feedback` | `id`, `journey_id`, `user_id`, `at`, `scores jsonb`, `more_search`, `note` |
| `events` | `id bigserial`, `at`, `user_id`, `journey_id`, `source (server, client)`, `name`, `props jsonb`, `app_version`; index `(name, at)` và `(journey_id)` |
| `trips` | `id uuid`, `journey_id`, `user_id`, `start_date`, `end_date`, `status (planned, active, done)`, `plan_hash` |
| `trip_stops` | `id uuid`, `trip_id`, `day`, `seq`, `place_id`, `planned_arrive`, `planned_leave`, `status (planned, arrived, skipped)`, `arrived_at`, `skip_reason`, `rating smallint null` (−1 / +1), `added_on_trip bool` |
| `checkins` | `id`, `trip_id`, `stop_id null`, `place_id`, `at` (check-in ở nơi ngoài lịch có `stop_id` rỗng) |
| `calendar_events` | `stop_id pk`, `google_event_id`, `etag`, `synced_hash` |
| `calendar_sync` | `trip_id pk`, `state (none, synced, drifted)`, `synced_plan_hash`, `last_preview jsonb`, `preview_hash` |
| `push_subscriptions` | `id`, `user_id`, `endpoint unique`, `p256dh`, `auth`, `user_agent` |
| `notification_prefs` | `user_id pk`, `enabled_kinds text[]`, `quiet_start`, `quiet_end`, `paused_until`, `ignored_streak` |
| `notifications` | `id uuid`, `user_id`, `trip_id`, `kind`, `template_id`, `variant`, `payload jsonb`, `scheduled_at`, `sent_at`, `opened_at`, `action`, `status (scheduled, sent, skipped, cancelled)`, `skip_reason` |

**Xóa tài khoản:**
- Xóa `profiles`, `calendar_links` (thu hồi token phía Google trước), `push_subscriptions`, `notification_prefs`, `auth_sessions`, file avatar. Đặt `users.deleted_at` và xóa email / tên.
- `journeys`, `events`, `feedback`, `trips` giữ lại nhưng đặt `user_id = NULL`. Số liệu tổng hợp vẫn đúng mà không còn gắn với người.

## 5. Lộ trình

**Còn lại trước khi xóa file này** (cần người dùng):
- A1: đăng nhập Google thật một lần trên domain prod (sau khi deploy).
- A5: thử Calendar thật với tài khoản test; xác nhận Calendar API đã bật và consent screen có scope `calendar.app.created`.
- A7: gửi thử push thật. Điện thoại đang nhận trang tải app ở mọi trang người dùng, nên `/app` trên Android Chrome chưa mở được: cần quyết định cho phép web trên điện thoại hay chỉ thử trên Chrome máy tính.

### ~~A0 — Postgres~~ (đã ship 2026-10-09, gộp vào tài liệu chính thức)
- Container + `run.sh db`, `db-backup`, `src/db/`, `migrations/001_init.sql` (mọi bảng ở §4), `python -m db migrate`.
- Thêm dependency `psycopg[binary,pool]` vào `pyproject.toml`.
- Test: marker `pg` mới; test bỏ qua khi thiếu `TEST_DATABASE_URL`, nếu có thì mỗi lần chạy tạo schema tạm.
- **Xong khi:** `python -m db migrate` chạy lại nhiều lần không lỗi (idempotent); test `pg` pass.

### ~~A1 — Đăng nhập Google, khóa `/app`~~ (đã ship 2026-10-09, gộp vào tài liệu chính thức)
- **Luồng:** `GET /api/auth/google/start?next=` → 302 sang Google (authorization code + PKCE + `state` có `purpose: login`, scope `openid email profile`) → `GET /api/auth/google/callback` (đúng `GOOGLE_REDIRECT_URI`) → kiểm `state`, đổi code, verify `id_token` bằng `google-auth` → upsert `users` theo `google_sub` → tạo `auth_sessions` → đặt cookie `tg_session` (`HttpOnly; SameSite=Lax; Path=/`, `Secure` khi `APP_BASE_URL` là https; trượt 30 ngày) → 302 về `next`. `next` chỉ nhận đường dẫn tương đối.
- **Lần đầu đăng nhập:** màn đồng ý điều khoản và chính sách dữ liệu (bắt buộc tích), ghi vào `profiles.consents`.
- **Endpoint:** `GET /api/harness/me`, `POST /api/auth/logout`.
- **Harness:**
  - Mọi `/api/harness/*` đều cần phiên hợp lệ, thiếu thì trả 401 (`/api/auth/*` không cần).
  - Mutation kiểm header `Origin` khớp `APP_BASE_URL` (dev thì khớp host).
  - Hành trình gắn `user_id` lúc tạo. Đọc hoặc sửa hành trình của người khác trả **404**.
  - `user_id` / `remember` không lấy từ body nữa mà lấy từ phiên. Trip `ProfileStore` dùng `users.id.hex` (32 ký tự, khớp regex sẵn có).
  - `GET /api/harness/trips` liệt kê theo chủ sở hữu; bỏ tham số `ids`.
- **Web:**
  - `account.ts` giữ API export nhưng đọc từ `/me`.
  - `Auth.tsx` chỉ còn nút "Tiếp tục với Google".
  - Route `/app/*` gặp 401 thì chuyển sang đăng nhập rồi quay lại đúng trang.
  - `journey.ts` gửi cookie (`credentials: 'same-origin'`).
- **Xong khi:** test harness cho 401 / 404 khác chủ / Origin sai; walk Playwright với `GOOGLE_*` giả lập bằng một route test chỉ bật khi có cờ env (không bao giờ bật ở prod); đăng nhập thật bằng tay một lần.

### ~~A2 — Hồ sơ~~ (đã ship 2026-10-09, gộp vào tài liệu chính thức)
- `PATCH /api/harness/me` (các trường hồ sơ).
- `POST /api/harness/me/avatar`: route này có trần body riêng 5 MB; chỉ nhận jpeg / png / webp; Pillow mở được mới nhận; crop vuông, resize 256 px, bỏ EXIF, lưu `data/accounts/avatars/<uuid>.webp`.
- `GET /api/harness/avatars/<key>`. Chưa có avatar riêng thì dùng ảnh Google.
- `DELETE /api/harness/me`: xóa tài khoản như §4, hỏi xác nhận hai bước trên web.
- **Prior cho Trip:** khi tạo hành trình, các trường hồ sơ đi vào Trip như **gợi ý có nguồn "từ hồ sơ"** trên thẻ, giống cơ chế mẫu dài hạn (`docs/TRIP_UNDERSTANDING.md` §17). Không tự điền thành fact của chuyến.
- **Web:** `Account.tsx` thêm avatar, các trường, nút xóa tài khoản.

### ~~A3 — Hành trình sang Postgres~~ (đã ship 2026-10-09, gộp vào tài liệu chính thức)
- `PgStore` cùng giao diện store hiện tại.
  - `save` dùng `UPDATE … WHERE id = $1 AND revision = $2` để chặn ghi đè, kèm khóa trong tiến trình như cũ.
  - Receipt nằm trong `envelope`.
- Feedback ghi vào bảng `feedback`.
- **Thời điểm:** thêm `at` cho receipt và log Planning.
- **Lệnh import:** `python -m harness import-files data/harness/sessions data/harness/feedback.jsonl` nạp 116 file, `user_id = NULL`.
- Store file giữ lại cho test và CLI module.
- **Xong khi:** toàn bộ test harness pass với cả hai store; restart server rồi tiếp tục được hành trình.

### ~~A4 — Event và Analytics P0~~ (đã ship 2026-10-09, gộp vào tài liệu chính thức)
- **Server event:** harness ghi `events` sau mỗi mutation đã commit với `name = "<stage>.<operation>[.<action>]"`. `props` gồm `revision`, `latency_ms`, `path` (`heuristic:chip_echo`, `heuristic:exact_command`, `clef_reject:*`, `agent`, `fallback`), `error`. Thêm các event `preview.<status>`, `places.search` (`q`, `hits`), `why_not`, `page_more`.
- **Client event:** `POST /api/harness/events`, gửi theo lô, tối đa 50 event / 32 KiB; tên ngoài allowlist (§6) bị bỏ. Web gửi bằng `navigator.sendBeacon` khi rời trang.
- **Stamp phiên bản:** `app_version` = git sha ngắn + hash `config/*.yaml`, tính lúc khởi động server.
- **`src/analytics/`:** `python -m analytics serve --port 8770`, kết nối `DATABASE_URL_READONLY`.
  - `GET /api/analytics/funnel`, `/decision`, `/sessions`, `/sessions/<id>`; bộ lọc `from`, `to`, `start_with`, `app_version`.
  - Vite thêm proxy `/api/analytics` → 8770, đặt **trước** `/api`. `run.sh start` thêm service analytics; prod không chạy nó.
- **Admin:**
  - `Analytics.tsx` có tab Phễu và Quyết định (§6) dùng số thật.
  - `Sessions.tsx` liệt kê phiên trên server: lọc theo stage đã tới, bỏ dở, feedback thấp, có lỗi. Màn chi tiết là timeline phát lại.
  - `Dashboard.tsx` có hàng "Hôm nay" dùng số thật.
- **Xong khi:** phễu của dữ liệu import khớp số đếm tay trên 3 hành trình mẫu.

### ~~A5 — Google Calendar (mọi lần ghi đều có xác nhận)~~ (đã ship 2026-10-09, gộp vào tài liệu chính thức)
- **Kết nối:**
  - `GET /api/auth/google/start?purpose=calendar&next=` xin thêm scope `https://www.googleapis.com/auth/calendar.app.created` (`include_granted_scopes=true`, `access_type=offline`, `prompt=consent`).
  - Cùng callback `/api/auth/google/callback`, nhánh `purpose: calendar`: lưu refresh token đã mã hóa bằng Fernet (`TOKEN_ENC_KEY`), cần thêm dependency `cryptography`.
  - Chỉ xin quyền khi người dùng bấm "Thêm vào Google Calendar".
- **Xem trước:** `GET /api/harness/calendar/preview?journey=` → `{state, changes: [{op: create|update|delete, stop, before?, after?}], preview_hash}`.
  - Lần đầu: tạo calendar "TripGuardian · Đà Lạt dd–dd/MM" và mỗi điểm dừng một event.
  - Mỗi event: `start` / `end` = giờ đến / rời; `location`; `description` gồm cảnh báo và link `APP_BASE_URL/app/today?stop=<id>`; `reminders: {useDefault: false, overrides: []}`.
- **Áp thay đổi:** `POST /api/harness/calendar/apply {journey, preview_hash}`. Chỉ áp khi `preview_hash` khớp đúng bản người dùng vừa xem; khác thì trả 409 và web hiện lại bản mới.
  - Cập nhật `calendar_events`, `calendar_sync`.
  - Lỗi giữa chừng thì ghi lại phần đã áp và báo đúng phần còn thiếu, không tự thử lại.
- **Lệch giữa app và Calendar:** khi Plan Output đổi mà `plan_hash` ≠ `synced_plan_hash` thì `state = drifted`. Web chỉ hiện dòng "Lịch Google khác kế hoạch hiện tại · N thay đổi [Xem]", không nhắc lại, không tự đồng bộ.
- **Hủy liên kết:** `POST /api/harness/calendar/disconnect {delete_calendar: bool}` → thu hồi token; chỉ xóa calendar khi người dùng chọn.
- **Xong khi:** test với Google API giả lập: tạo / sửa / xóa đúng diff, `preview_hash` cũ bị từ chối, event không có reminder; thử thật bằng tay một lần với tài khoản test.

### ~~A6 — Màn Hôm nay (Đang đi)~~ (đã ship 2026-10-09, gộp vào tài liệu chính thức)
- **Tạo chuyến:** khi `planning.confirm`, `companion` tạo `trips` + `trip_stops` từ Plan Output. Chốt lại kế hoạch thì cập nhật các điểm chưa tới, giữ nguyên điểm đã check-in.
- **Harness:** thêm stage đọc / ghi `companion`. Router cho phép khi `outputs.planning` có. Operation: `checkin {stop_id | place_id}`, `skip {stop_id, reason?}`, `rate {stop_id, value}`, `add {place_id}`, `adjust {option_id}`. `add` và `adjust` đi qua act của Planning rồi confirm lại, và chỉ chạy khi người dùng đã bấm xác nhận trên bản xem trước.
- **Gợi ý sau khi bấm Đã đến**, chỉ lấy từ serving index:
  - **Chơi gì ở đây:** feature nhóm `experience` có giá trị và bằng chứng (clip đúng đoạn, quote), sắp theo khớp `soft` của chuyến.
  - **Lưu ý thực tế:** `entry_fee`, `wait_time`, `booking_needed`, `parking`, `toilet`, `cash_only`.
  - **Theo giờ thực tế:** giờ hoàng hôn / bình minh lấy từ Open-Meteo (`daily.sunset`) qua `live` cho nơi có `sunset_view` / `cloud_hunting`. Mức đông theo giờ chỉ hiện khi có bằng chứng.
  - **Gần đây:** nơi có thời gian đi ≤ `nearby_max_min`, vừa với thời gian còn dư trước điểm sau, và đang mở. Giờ mở chưa có bằng chứng thì gắn "chưa xác nhận". Hard constraint của chuyến vẫn áp. Bỏ nơi đã có trong lịch và nơi người dùng đã bỏ với lý do "không thích". Xếp theo hàm fit public của `decision` (kiểm tra `decision/__init__.py`; chưa có thì thêm một hàm public nhỏ, không deep import).
  - **Nơi tương tự ở gần:** dùng khi người dùng báo đông hoặc không như kỳ vọng.
- **Tôi đang ở nơi khác:** tìm nơi qua `/api/harness/places?q=` rồi `checkin {place_id}`, nhận gợi ý như trên.
- **Phần còn lại của ngày không còn vừa** (tính lại từ giờ check-in): web hiện một dòng trung tính "Phần còn lại hơi chật · [Xem cách điều chỉnh]". Các phương án lấy từ `backups` / `on_delay` và cách xếp lại của Planning; người dùng chọn thì mới đổi.
- **Không ép:**
  - Trước khi đến vẫn hiện đủ hậu cần và cảnh báo; Đã đến chỉ mở thêm lớp gợi ý theo lúc này.
  - Không có trạng thái "lỡ"; điểm không check-in là `unknown`.
  - Đánh giá chỉ là nút 👍 / 👎 trên thẻ, không popup.
- **Cấu hình mới:** `config/companion.yaml` (`nearby_max_min`, `nearby_count`, `suggest_count`, `tight_threshold_min`).
- **Web:** route `/app/today` (màn Hôm nay); thẻ điểm dừng; sheet "Ở đây"; lối "Tôi đang ở nơi khác". Hệ thị giác theo `docs/UX_Design_Brief.md` §7, chỉ dùng token màu sẵn có; skill `ui-ux-pro-max` + `ui-styling`.
- **Xong khi:** test companion: gợi ý chỉ chứa place_id có trong serving, hard constraint áp, `unknown` giữ nguyên, `add` không qua được validate thì bị từ chối; walk Playwright màn Hôm nay ở 390 px và 1440 px.

### ~~A7 — Thông báo kiểu Duolingo~~ (đã ship 2026-10-09, gộp vào tài liệu chính thức)
- **PWA:**
  - `web/public/manifest.webmanifest` và `web/public/sw.js` (xử lý `push` và `notificationclick`, mở deep link `?n=<id>`).
  - Hồ sơ có mục "Thêm TripGuardian vào màn hình chính" cho iPhone (chỉ hướng dẫn, không nhắc).
- **Xin quyền:** chỉ sau khi chốt kế hoạch, bằng một thẻ nói rõ lợi ích, có nút từ chối. Không xin ở lần vào đầu.
- **Endpoint:** `POST /api/harness/push/subscribe`, `/push/unsubscribe`, `GET /api/harness/notifications` (hộp thông báo), `POST /api/harness/notifications/<id>/open`, `PATCH /api/harness/me/notification-prefs`.
- **Worker:** `python -m notify run`, chạy mỗi 60 giây theo giờ `Asia/Ho_Chi_Minh`.
  - **Lập lịch:** khi trip được tạo hoặc đổi, hủy các thông báo chưa gửi rồi sinh lại.
  - **Theo dõi thời tiết:** trong các ngày đi, kiểm dự báo mỗi 3 giờ.
  - **Gửi:** áp giới hạn, giờ yên lặng, `paused_until`; push trả 404 / 410 thì xóa subscription; mọi thông báo đều có bản sao trong hộp thông báo.
  - Thêm dependency `pywebpush`.
- **Loại thông báo, template và giới hạn:** §7. Thông báo chỉ dẫn tới màn liên quan, không bao giờ tự đổi kế hoạch.
- **Xong khi:** test notify cho giới hạn mỗi ngày, giờ yên lặng, tự tạm dừng sau 3 lần bỏ qua, loại thông báo thiếu dữ liệu thì bị bỏ (`skip_reason`), template điền đủ chỗ trống; gửi thử thật lên Android Chrome.

### ~~A8 — Analytics đầy đủ~~ (đã ship 2026-10-09, gộp vào tài liệu chính thức)
- Thêm các tab Trip, Planning, Thực tế, Thông báo, Agent; panel "Nhu cầu" trong `Places.tsx`; màn **Insights** (§6).
- So sánh theo `app_version`.
- Phân cụm `feedback.note` và câu gõ tự do mỗi tuần bằng vai trò Extractor (job offline; kết quả lưu bảng `insight_clusters` qua migration mới).
- Bandit chọn biến thể câu thông báo: reward = mở thông báo + có hành động có ích trong 2 giờ sau. Chỉ bật khi mỗi biến thể đã có ≥ 200 lượt gửi.

## 6. Danh mục event và chỉ số

**Allowlist client event:** `page_view {route}`, `landing_cta {utm_*}`, `card_impression {place_id, group, rank}`, `detail_open {place_id, from}`, `evidence_play {place_id, video_id}`, `compare_open {a, b}`, `outbound_click {kind: maps|tiktok|booking, place_id}`, `tab_hidden {stage, ms}`, `today_open`, `suggestion_open {place_id, kind}`, `install_prompt_seen`, `push_permission {result}`.

`card_impression` chỉ dùng làm mẫu số. Thẻ hiện ra mà không được bấm **không** có nghĩa là người dùng không thích (`Project_Context` §8.2).

| Tab | Chỉ số | Dẫn tới chỉnh gì |
|---|---|---|
| Phễu | Landing → đăng nhập → tạo hành trình → Trip compile → thấy shortlist → chọn ≥ 1 → preview `ready` → Planning → confirm → feedback; tỉ lệ rơi, thời gian từng bước, thao tác cuối trước khi bỏ | Màn hoặc câu hỏi làm người dùng rơi |
| Trip | Số lượt tới khi compile; skip / "Chưa chắc" theo `qid`; chip so với gõ tự do; tỉ lệ `chip_echo`, `clef_reject`, fallback; `unmapped` lặp lại; tỉ lệ `back` và `refine` | `trip.yaml`, ontology, prompt |
| Quyết định | Tỉ lệ chọn theo vị trí xếp hạng và nhóm; phân bố lý do bỏ; số trang `more`; số lần `why-not`; từ khóa tìm không thấy; nơi thêm ngoài shortlist; so sánh thì bên nào thắng; nới constraint được nhận / từ chối; preview `failed` / `blocked`; số lần sửa trước khi lịch hợp lệ | `decision.yaml`, danh sách crawl corpus |
| Planning | Phương án được chọn, mức dùng `recommend`, các act, tỉ lệ ngày Mong manh, tỉ lệ quay về Decision, lỗi tra chỗ ở, thời gian từ `advance` tới `confirm` | `planning.yaml` |
| Thực tế | **Tỉ lệ check-in lại ở điểm sau** (chỉ số chính); lệch giờ đến; thời lượng ở lại thật so với ước tính; tỉ lệ đã đến / bỏ / ngoài lịch; nhãn Mong manh có đoán đúng ngày bị vỡ không; tỉ lệ thêm từ gợi ý; 👍 / 👎 so với điểm fit. Luôn kèm tỉ lệ phủ check-in | `live.yaml` `mode_factor`, `buffer_min`, `category_defaults.yaml`, `robustness.py` |
| Thông báo | Tỉ lệ cho phép; tỉ lệ mở và có hành động theo loại và biến thể; **số lượt tắt hoặc tạm dừng trên 1.000 thông báo gửi** (chỉ số chặn) | `config/notifications.yaml` |
| Agent | Theo vai trò: số call, p50 / p95 latency, timeout, sai schema, queue đầy, tỉ lệ fallback; thời gian tới event SSE đầu tiên | `agents.yaml`, `LLM_PROVIDER.md` |
| Chất lượng | `Project_Context` §18: vi phạm hard constraint (phải bằng 0, vượt thì báo động); tỉ lệ `unknown` của các nơi trong lịch cuối; lấy mẫu câu Agent đưa sang màn Labels để đo unsupported claim; tỉ lệ khả thi; robust / fragile; time to accepted plan; `outbound_click` + `tab_hidden` ở Decision làm proxy cho việc phải tìm ở ngoài | — |

**Insights** (mỗi mục có nút dẫn tới hành động):
1. Từ khóa tìm không thấy → danh sách cần crawl.
2. `unmapped` lặp lại → đề xuất ontology.
3. Nơi hiện nhiều nhưng bị bỏ nhiều, hoặc bị report → review queue.
4. Câu hỏi Trip bị skip nhiều → sửa `trip.yaml`.
5. Phiên có lỗi hoặc fallback → mở Sessions.

Insights chỉ đề xuất, không tự ghi corpus.

Ngưỡng cảnh báo chỉ đặt sau khi có baseline thật (`Role_Web` §3.7).

## 7. Thông báo — loại, thời điểm, mẫu câu

Mọi số liệu điền vào câu đều lấy từ dữ liệu thật. Thiếu dữ liệu cho chỗ trống thì **không gửi** loại đó. Template và biến thể nằm ở `config/notifications.yaml`, người duyệt mới được vào file. LLM không viết câu lúc gửi.

| `kind` | Khi nào | Mẫu (một biến thể) |
|---|---|---|
| `plan_unfinished` | 24 giờ sau khi có shortlist mà chưa confirm, 1 lần | "{n} nơi ở Đà Lạt vẫn đang xếp hàng chờ bạn chốt 🌲 Còn chừng 2 phút là xong lịch." |
| `book_ahead` | 3 ngày trước, có nơi `booking_needed=yes` | "Psst… {place} hay hết chỗ {when}. Đặt trước cho chắc nha 🍲" |
| `eve_of_trip` | 20:00 tối hôm trước | "Mai lên Đà Lạt rồi! Sáng {t_min}°C, {rain_phrase}: {pack} vào balo nhé 🧥" |
| `day_brief` | 7:30 mỗi ngày đi | "Ngày {d}: {n} điểm, tổng đi xe ~{travel} phút. Mở màn: {first} lúc {time} ☕" |
| `checkin_hint` | Giờ đến dự kiến, **chỉ 2 điểm đầu của chuyến** | "Tới {place} chưa? Bấm *Đã đến*, mình chỉ {highlight} 📸" |
| `golden_hour` | 45 phút trước hoàng hôn / bình minh, nơi trong lịch có `sunset_view` / `cloud_hunting` | "Hoàng hôn hôm nay {sunset}. {place} có trong lịch chiều nay, tới trước {by} là kịp 🌅" |
| `weather_change` | Dự báo đổi làm một nơi nhạy cảm bị ảnh hưởng | "Chiều nay mưa {p}% ☔ {place} dễ lầy, mình có phương án trong nhà, xem thử?" |
| `post_trip` | 10:00 ngày sau khi về, 1 lần | "Về tới nhà an toàn chưa? Kể mình nghe chuyến đi trong 30 giây, lần sau mình gợi ý trúng hơn 💛" |
| `paused` | Sau 3 thông báo liên tiếp không được mở | "Có vẻ giờ chưa phải lúc. Mình tạm im nhé, cần gì thì mình vẫn ở trong app 🌿" |

**Luật:**
- Trước chuyến tối đa 1 thông báo / ngày; trong chuyến tối đa 3 / ngày.
- Không gửi từ 22:00 đến 7:00. Đến hạn trong giờ yên lặng thì dời tới 7:00, hoặc bỏ nếu đã hết hiệu lực.
- Người dùng bật / tắt được từng `kind`.
- Sau `paused`, chỉ gửi lại khi người dùng tự mở app.
- **Cấm:** "bạn đã lỡ", "bạn chưa check-in", đếm ngược giả, so sánh với người khác.

## 8. Quyền riêng tư và bảo mật

- Event không chứa email, tên hay số điện thoại. Transcript nằm trong `journeys.envelope`; Admin xem được.
- Token Google mã hóa khi lưu; chỉ giữ hash của token phiên.
- Analytics dùng role chỉ-đọc. Cả analytics lẫn `/admin` đều không public (`server.mjs` chỉ public `/api/harness/*` và `/api/auth/*` sẽ thêm; mọi `/api/*` khác bị chặn, kiểm lại khi thêm route).
- Avatar luôn được decode và encode lại, không phục vụ file gốc người dùng tải lên.
- Không thu GPS.

## 9. Ngoài phạm vi đợt này

Đăng nhập bằng email/mật khẩu và quên mật khẩu (chờ người dùng báo), mascot, đọc các calendar khác của người dùng, email marketing, hạn tự xóa dữ liệu thô, đa thiết bị cho hộp thông báo ngoài cùng một tài khoản, chuyển Trip `ProfileStore` sang Postgres (mẫu dài hạn đang tắt).

## 10. Gộp vào tài liệu chính thức khi ship

| Bước | Tài liệu |
|---|---|
| A0–A3 | `ARCHITECTURE.md` §3 (phụ thuộc), §5 (dữ liệu: Postgres), §7 (cổng); `AGENT_HARNESS.md` §3 (persistence), §4 (API auth / me); `README.md` (thiết lập Postgres, env, `run.sh db`); tài liệu mới `docs/ACCOUNTS.md` (tài khoản, phiên, hồ sơ, Calendar) |
| A4, A8 | Tài liệu mới `docs/ANALYTICS.md` (event, chỉ số, server); `Role_Web_Functional_Design.md` §3.5–3.7, §6 |
| A5–A7 | Tài liệu mới `docs/COMPANION.md` (Đang đi + thông báo); `Role_Web_Functional_Design.md` §1 (bắt buộc đăng nhập), §2.1, §2.11, §2.13 mới (Hôm nay), §6 |
| Mọi bước | `docs/log/DEV_LOG.md`; thêm tài liệu mới vào danh sách trong `README.md` |
