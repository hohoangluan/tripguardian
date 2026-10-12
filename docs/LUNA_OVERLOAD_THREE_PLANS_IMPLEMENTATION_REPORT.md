# Kiểm tra và sửa Planning quá tải của Luna

Trạng thái: đã sửa các finding runtime của review, bổ sung regression và chạy luồng Web với fixture tổng hợp. Không coi toàn bộ đề xuất trong `OVERLOAD_AND_THREE_PLANS_IDEAS.md` là đã triển khai hoặc đã đo hiệu quả với người dùng.

## Lỗi đã xác minh và sửa

| Vấn đề | Kết quả |
|---|---|
| Chọn profile ném `KeyError: balance` | Fallback dùng mục tiêu `least_travel` thực sự có trong config. Năm test edit có sẵn đã fail trước sửa và pass sau sửa. |
| Backup làm hỏng metrics hoặc nâng sai giá trị selection | Utility selection có mẫu số riêng; backup không góp vào giá trị selection giữ lại. Utility dùng sở thích cho backup mang nguồn `selection_and_preferences`, không giả nguồn Decision score. Test swap/add cho cả ba profile kiểm preview read-only, metrics, undo/redo và replay. |
| `make_room` thiếu token | Boundary public bắt buộc token; giữ replay action public không cần token cũ. Regression kiểm thiếu/sai token, sửa nested edit hoặc danh sách drop, atomic apply và replay. |
| Preview response cũ ghi đè panel hoặc lỗi mới | Harness trả revision cho `preview-act`. Web kiểm thứ tự request, journey, revision, Planning session và View đã chụp ở cả success/catch. Provider sở hữu panel; apply dùng đúng action/token đang hiển thị. |
| Giữ tất cả chưa dùng được | Sửa selection, rebuild, score, metrics, confirm và replay cho `keep_all`. Draft invalid xem được nhưng không confirm. Timeline, lỗi, độ vững và chi phí gốc có phần đối chiếu riêng; Web chỉ cho chọn baseline hợp lệ. Delta không so được sau đổi home hoặc thiếu dữ liệu là unknown. |
| Đường chọn/chốt trong UI | Card, tab và bảng so sánh khóa profile unavailable; chốt khóa khi validator hoặc active profile không đạt. Bảng so sánh cũng khóa trong lúc mutation. |
| Handoff bỏ qua ba thẻ | Browser phát hiện `toPlan → recommend` tự chọn profile đầu. Web bỏ automatic recommend với overload; server trả fallback `choose_overload_profile` khi chưa chọn, giữ quyết định cho user. Regression dùng Decision và Planning thật. |
| UI thiếu chênh lệch selection | Hiện delta của lịch đang sửa, lý do trên card, tỷ lệ giữ utility/mong muốn và số nơi chưa có giá. |

Các sửa trước đó của Luna về wish theo giờ, dữ liệu thiếu, lodging overload, directed transport, hazard fail-closed và reoptimize được kiểm lại bằng suite hiện tại; không nới hard/physical constraint.

## Kiểm chứng

Môi trường hiện tại dùng `.venv/bin/python` (Python 3.12); direct importer và venv `/tmp` của báo cáo cũ không còn. HTTP/Chromium chạy ngoài sandbox vì sandbox chặn localhost socket và sau đó lỗi khởi tạo process. Không coi lỗi quyền môi trường là lỗi sản phẩm.

```bash
.venv/bin/python -m pytest tests/planning/test_planning_overload_edits.py -q -p no:cacheprovider
# 16 passed; gồm 6 trường hợp backup swap/add qua ba profile.

.venv/bin/python -m pytest tests/planning/test_planning_overload_edits.py tests/harness/test_tools.py::test_real_overload_handoff_offers_profiles_and_confirms_only_valid_drafts -q -p no:cacheprovider
# 17 passed, 1 skipped; phiên có assertion automatic recommend không chọn profile.

.venv/bin/python -m pytest tests/harness/test_harness_server.py::test_real_preview_http_enforces_owner_input_and_read_only_revision -q -p no:cacheprovider
# 1 passed, 1 skipped; đúng owner, sai owner, chưa đăng nhập, JSON sai và action >8192 ký tự.

.venv/bin/python -m pytest tests/planning tests/decision tests/harness -q -p no:cacheprovider
# Lần cuối: 791 passed, 98 skipped, 1 deselected, 276,51 giây; exit 0.

node web/scripts/test_planning_state.mjs
# 5 passed; request đảo thứ tự, edit/revision, đổi journey và đổi View/session trong cùng journey.

TG_BROWSER_TEST=1 .venv/bin/python -m pytest tests/harness/test_overload_browser.py -q -p no:cacheprovider
# 1 passed, 1 skipped, 91,56 giây; Chromium thật + harness/Decision/Planning thật, live và đăng nhập tổng hợp.

cd web
npm run build
# TypeScript/Vite pass; còn cảnh báo config và chunk size có sẵn.
```

Suite composer bổ sung fixture có sun `(360, 1050)` để một visit không đạt cả sunrise lẫn sunset, và đúng 98 nơi/14 ngày: có hướng trimmed hợp lệ, giữ must, không trùng visit. Test tuần nhẹ vẫn được giữ riêng. Đây là fixture mô phỏng, không phải benchmark dịch vụ live.

RED/GREEN mới đã quan sát: chọn keep-all fail ở nhánh chỉ duyệt profiles; timed invalid keep-all fail ở serialization; nhãn nguồn utility backup sai; HTTP preview thiếu revision; public recommend tự chọn profile; preview catch chấp nhận View cũ. Sau sửa, các regression liên quan pass trong suite cuối.

## Browser đã chạy và giới hạn

Luồng đã chạy: selection quá tải ở Chọn nơi → Xem 3 hướng → ba card → chọn hướng available → mở timeline Giữ tất cả → preview restore (chọn make-room nếu cần) → apply → đổi Gọn tuyến → preview reoptimize → đóng preview → chốt → `/app/done`. Không có page error.

Browser ban đầu phát hiện automatic profile selection. Lần tiếp theo dừng vì test cố chọn Tiết kiệm unavailable; fixture đã chuyển sang chọn hướng available, giữ nguyên fail-closed. Không nới assertion sản phẩm để ép profile unavailable thành hợp lệ.

Chưa chạy riêng browser swap, browser undo/redo, browser đảo promise hoặc đổi journey khi preview đang chờ; các hành vi này có regression Engine/gate nhưng không được coi là đã chứng minh E2E. Postgres bị skip do thiếu `TEST_DATABASE_URL`; không khẳng định persistence Postgres. Không gọi model, OSRM thật, lodging crawl thật hoặc triển khai production. Chưa đo confusion matrix Decision/Planning, chất lượng tối ưu toàn cục hoặc lợi ích người dùng.

## Phạm vi file và review

Source sửa trong phiên này:

- `src/planning/engine.py`, `src/planning/composer.py`, `src/harness/dispatch.py`.
- `web/src/user/pd/decision.tsx`; `web/src/user/planning/api.ts`, `current.ts`, `planning.tsx`, `types.ts`; `web/src/user/screens/Plan.tsx`.
- Test bổ sung: `tests/planning/test_planning_overload_edits.py`, `test_planning_composer.py`; `tests/harness/test_tools.py`, `test_harness_server.py`, `test_overload_browser.py`; `web/scripts/test_planning_state.mjs`, `test_overload_ui.mjs`.
- Tài liệu: `docs/PLANNING.md`, `AGENT_HARNESS.md`, `Role_Web_Functional_Design.md`, báo cáo này.

Snapshot đầu phiên của các source hiện có tại `/tmp/overload-review-start`; không còn hai baseline `/tmp` được nêu trong bàn giao cũ. Không nhận toàn dirty diff là của phiên này. Không reset/clean/stage/commit hoặc sửa các file dirty ngoài phạm vi.

Review độc lập chỉ đọc code tìm thêm stale-error khi cùng journey đổi Planning session; regression đã RED/GREEN và sửa cả success/catch. Lượt recheck của reviewer bị lỗi môi trường khởi tạo process, nên không ghi là đã được reviewer xác nhận lại. Suite cuối và browser có kết quả trực tiếp nêu trên.
