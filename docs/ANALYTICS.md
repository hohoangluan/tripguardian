# Event và Analytics

Số liệu Admin từ event thật. Ghi: `src/harness/events.py` (harness), `web/src/user/events.ts` (web). Đọc: `src/analytics/` (server private). Màn: `web/src/admin/screens/Analytics.tsx`, `AnalyticsTabs.tsx`, `Sessions.tsx`, `Insights.tsx`, hàng "Hôm nay" ở `Dashboard.tsx`, panel "Nhu cầu" ở `Places.tsx`.

## 1. Event

Bảng `events`: `at, user_id, journey_id, source (server | client), name, props, app_version`. Không chứa email, tên, số điện thoại hay chữ người dùng gõ (trừ `q` của ô tìm nơi). Ghi lỗi không làm hỏng request gây ra nó.

**Server** (harness): sau mỗi mutation hành trình, `name = <stage>.<operation>[.<act type>]`, props `revision, latency_ms, first_ms` (tới event SSE đầu), `path` (`agent | fallback | heuristic:exact_command`, từ event nội bộ `trace` của adapter `Tools`), `error` khi mutation thất bại, `compiled` khi Trip vừa ra Search Input, `refined` khi câu gõ ở Chọn nơi đi qua Trip. Lượt Trip thêm `kind, qid, exit (skip | unsure)`. Act thêm `place_id, reason, with_id, group, id, objective, pace`. `planning.confirm` thêm `places, hard_checks, hard_fail, hard_unknown, robustness`. Ngoài ra: `journey.create`, `preview.<status>`, `places.search {q, hits}`, `why_not`, `page_more`, `feedback.submit`, `auth.login`, `auth.consent`, `companion.<operation>`, `calendar.connect | apply | disconnect`, `notify.prefs {paused, kinds_off}`. Lần replay theo receipt không ghi lại.

**Client**: `POST /api/harness/events {events: [...]}`, tối đa 50 event / 32 KiB mỗi lô; tên và prop ngoài allowlist bị bỏ. Không phiên thì chỉ giữ `page_view`, `landing_cta`. Web gom lô 10 giây hoặc 20 event, gửi bằng `sendBeacon` khi rời / ẩn tab.

| Tên | Props |
|---|---|
| `page_view` | `route` |
| `landing_cta` | `utm_*` |
| `card_impression` | `place_id, group, rank` (một lần mỗi nơi mỗi hành trình; chỉ làm mẫu số: thẻ hiện mà không bấm không có nghĩa là không thích) |
| `detail_open` | `place_id, from` |
| `evidence_play` | `place_id, video_id` |
| `compare_open` | `a, b` |
| `outbound_click` | `kind (maps | tiktok | booking), place_id` |
| `tab_hidden` | `stage, ms` (thời gian rời tab) |
| `today_open`, `install_prompt_seen` | — |
| `suggestion_open` | `place_id, kind` |
| `push_permission` | `result` |

**Phiên bản**: `app_version` = git sha ngắn + hash `config/*.yaml`, tính khi harness khởi động; gắn vào event và hành trình.

**Dữ liệu cũ**: `python -m harness import-files` nạp hành trình file và sinh các mốc phễu từ trạng thái đã lưu (`props.imported`, giờ = giờ sửa file, không dùng để tính thời gian; không biết được `preview`).

## 2. Server analytics

```sh
python -m analytics serve [--port 8770]   # 127.0.0.1, chỉ GET, role tg_analytics (DATABASE_URL_READONLY)
python -m analytics cluster               # mỗi tuần: nhóm ý người dùng viết (vai trò Extractor), cần DATABASE_URL
```

Vite proxy `/api/analytics` → 8770 (`ANALYTICS_PORT`). `./run.sh start` chạy nó; bản public không chạy và `web/server.mjs` chặn mọi `/api/*` ngoài harness / auth. Bộ lọc chung: `from`, `to` (ngày theo giờ Việt Nam; mặc định 30 ngày), `start_with`, `app_version`.

| GET `/api/analytics/…` | Nội dung |
|---|---|
| `funnel` | Landing, CTA, người đăng nhập; mỗi bước: số hành trình tới, giữ lại so với bước trước có số liệu, phút từ lúc tạo (trung vị), số dừng ở đây và thao tác cuối trước khi dừng |
| `decision` | Thao tác, lý do bỏ, trạng thái lịch xem trước, trang thêm, why-not, so sánh, bấm ra ngoài, tỉ lệ chọn theo vị trí, từ khóa tìm không thấy |
| `trip`, `planning`, `reality`, `notifications`, `agent`, `quality` | Các tab §3 |
| `sessions?reached=&abandoned=1&low_feedback=1&error=1`, `sessions/<id>` | Danh sách và phát lại một hành trình (transcript, log module, receipt, event, phản hồi) |
| `today`, `versions`, `insights`, `clusters`, `places/<id>` | Hàng Hôm nay, phiên bản, Insights, nhóm ý, nhu cầu một nơi |

## 3. Chỉ số

Bước phễu (mỗi hành trình đếm một lần): `journey.create` → `trip.turn` có `compiled` → `trip.advance` → `decision.act.select` → `preview.ready` → `decision.advance` → `planning.confirm` → `feedback.submit`. Event có `error` không tính.

| Tab | Chỉ số |
|---|---|
| Phễu | §2; so sánh hai phiên bản cạnh nhau |
| Trip | Lượt tới khi hiểu xong; chip so với gõ tự do; đường trả lời; bỏ qua / chưa chắc theo `qid`; `unmapped` lặp lại; quay lại; refine |
| Quyết định | §2 `decision` |
| Lịch trình | Thao tác, phương án được chọn, dùng gợi ý tự động, quay về Chọn nơi, độ vững của lịch đã chốt, phút từ vào tới chốt, lỗi |
| Thực tế | **Tỉ lệ check-in lại ở điểm sau** (chỉ số chính), muộn so với lịch, khoảng giữa hai điểm so với lịch, đã đến / bỏ qua / chưa biết, check-in ngoài lịch, lý do bỏ qua, Hợp / Không hợp, thêm từ gợi ý; luôn kèm độ phủ check-in |
| Thông báo | Tỉ lệ cho phép; gửi / mở / có ích (thao tác trong 2 giờ sau khi mở) theo loại và biến thể; bị bỏ theo lý do; **tắt hoặc tạm im trên 1.000 thông báo gửi** (chỉ số chặn) |
| Agent | Theo loại yêu cầu dùng model: số lượt, p50 / p95, tới event đầu, fallback, lỗi. Số liệu theo từng lời gọi của từng vai trò chưa được ghi |
| Chất lượng | Vi phạm hard constraint trên lịch đã chốt (phải bằng 0, khác 0 là báo động), tỉ lệ kiểm tra `unknown`, tỉ lệ lịch xem trước xếp được, phút tới lịch được chấp nhận, bấm ra ngoài + rời tab ở Chọn nơi (proxy cho việc phải tìm ở ngoài) |

Ngưỡng cảnh báo chỉ đặt sau khi có baseline thật (`docs/Role_Web_Functional_Design.md` §3.7).

## 4. Insights

Mỗi mục có nút dẫn tới việc cần làm; chỉ đề xuất, không ghi corpus: từ khóa tìm không thấy (danh sách cần crawl), `unmapped` lặp lại ≥ 2 hành trình (đề xuất ontology), nơi hiện ≥ 10 lần mà bị bỏ ≥ 30% (hàng đợi duyệt), câu hỏi Trip bị bỏ qua nhiều (`config/trip.yaml`), phiên có lỗi hoặc fallback (Phiên chuyến đi). Thêm bảng "Nhóm ý người dùng viết": job `cluster` lấy phản hồi sau chuyến và câu gõ tự do 7 ngày qua, nhóm bằng task `INSIGHT_CLUSTER` (`corpus.llm`), ghi bảng `insight_clusters` (thay nhóm của cùng tuần khi chạy lại).
