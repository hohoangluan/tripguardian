# Bàn giao: Trip Understanding redesign (cập nhật 2026-10-15, tối)

Spec: `docs/superpowers/specs/2026-10-13-trip-understanding-redesign-design.md` (R), kiến trúc + ma trận test `docs/superpowers/specs/2026-10-15-trip-understanding-architecture.md` (§5.1–§5.7). Hành vi hiện tại đã gộp vào `docs/TRIP_UNDERSTANDING.md` §4–§5, `docs/UI_SPEC_USER_WEB.md` Trang 3, `docs/LLM_PROVIDER.md` (Agent trên sol).

## 0. Phiên tối 15/10 (Claude tự làm, không dùng sol để code)

| Việc | Trạng thái |
|---|---|
| Agent Gemma → `cx/gpt-6.1-sol` qua 9router, reasoning `low` (`AGENT_REASONING_EFFORT`), `prompt_cache_key`, httpx client riêng mỗi call (sửa §1.5 "different event loop") | Xong. **Production đã chuyển** (chỉ restart harness, chưa build web), kiểm bằng khách thật: 2 call sol, câu đào sâu đúng |
| `./run.sh start/prod` tự khởi động 9router (`router_start`) | Xong, chưa chạy `./run.sh prod` |
| Mỗi lượt một câu hỏi: `ask_required` (agent chọn mục bắt buộc + lúc hỏi), câu đào sâu bằng chữ / `ask_user` ≤ 3 lựa chọn, chặn câu thứ 3 liên tiếp (`followup_cap`), chọn thẻ → agent phản hồi (`picked`), deck 1 tab, 3 lựa chọn tốt nhất mỗi nhóm | Xong, test `tests/trip/test_one_question_flow.py` |
| Tốc độ: `record_fact` nhận danh sách + `say` + `ask_required` → lượt thường 1 call (sol chỉ trả 1 tool call mỗi lần, mức reasoning không đổi tốc độ) | Xong; bench v6 đo tốc độ (`logs/bench_trip/sol_v6`) |
| Khối suy nghĩ: mỗi tool gọi phát một dòng `progress` | Xong |
| Clef: đọc kèm lời người dùng khi kiểm câu trả lời; `CLEF_TIMEOUT_S` 30 → 2 trong `.env`; đo 19/20 đúng, p50 0,55 s | Xong (`.env` mới có hiệu lực khi restart harness) |
| Guard: cho nhắc lại tên nơi người dùng đã nói; tên chỉ gồm từ chung không tính | Xong |
| Web: `Ask.tsx` (thẻ kiểu AskUserQuestion, khung ảnh carousel nền mờ), `ask.css`, `useDeckForm` dùng chung, Board `Ngày đi` một dòng | Xong, `node logs/bench_trip/shots_ask.mjs` pass; ảnh `frontend_images/understand-ask*.png`, `understand-deck-drill.png`, `understand-photo-*.png`. **Chưa lên production**: chờ người dùng xem ảnh (RULE §0.2) rồi `./run.sh prod` |
| §1.4 test đỏ S4 | Giữ S4, test sửa có ghi lý do |

Bench hội thoại: `logs/bench_trip/serve.py 8793 logs/bench_trip/sessions_sol` + `BENCH_PORT=8793 .venv/bin/python logs/bench_trip/converse.py <out> 5`, xem bằng `logs/bench_trip/show.py <out>/*.json`. v6 (một call mỗi lượt): 4/5 người dùng mô phỏng đủ 7 mục sau 9–11 lượt, mỗi lượt p50 6,7 s / p90 13,4 s, ~17k token prompt (76% cache), 0 lỗi (v5 hai call: p50 10,6 s, 3/56 lượt quá 30 s). Còn lại: persona "vague" (không chốt ngày) dừng ở 5/7; câu trả lời chưa stream từng chữ (nó nằm trong tham số `record_fact`, hiện khi call xong).

Clef: giữ lại sau khi tối ưu (người dùng: "nếu không được thì bỏ"). Bộ ca `tests/trip/clef_cases.yaml`, chạy `python -m pytest --collect-in-virtualenv -m live tests/trip/test_clef_live.py -s`: 0/51 chặn nhầm (trước 4), kiểm lời 11/11. Khung ảnh: mọi kiểu có ảnh (tối đa 6), lăn chuột để xoay.

## 1. Việc cũ còn mở

| # | Việc | Trạng thái |
|---|---|---|
| 1 | Production "không vào được" (16:05) | Chưa rõ; smoke 19:15 ok (khách tạo được chuyến) |
| 2 | Bỏ giới hạn 20 khách/IP/giờ | Đã lên production cùng lần restart harness 19:15 |
| 3 | Landing trắng trên máy khách | Chưa làm |

## 2. Đã xong hôm nay

- **Phần 5a (sol)**: bản đọc lại gọn (`readback.py`: nhóm theo tab, `vnd()` "25 triệu", `Line.undo`), `TurnInput` `drop` + `readback_ok` kiểm digest, `view.readback`, `trip.Tools.read("readback" | "search_input")`, harness `TripNotReady` (409 `trip_incomplete`) + thao tác `trip` ở stage decision, guard G15–G18 (mẹ/bố, giá trị ngoài danh sách vào `unmapped`, cờ yes/có, log lý do `schema_refused`).
- **Phần 5c (sol, Claude làm nốt)**: web hiển thị backend: `DeckCard` (`screens/understand/Deck.tsx`), `ReadbackSheet` (`ui/ReadbackSheet.tsx`), Board đọc `required` của backend, `SearchInput.context` dùng `checkin_at` / `checkout_at` / `frame`.
- **Phần 5d (Claude)**: chỉ căn bố cục, không đổi màu/vibe: ảnh drill 3 cột (lỗi trùng class `.tg-cx__ring` trong `chat.css`), deck cuộn bên trong, tab một dòng, sheet cổng thấy đủ nút. Tên nhóm theo thiết kế cũ, một nguồn `readiness.TITLE`: Ngày đi, Đi với, Phương tiện, Lưu ý, Nhịp độ, Ngân sách, Nơi lưu trú (tab deck dùng cùng tên).
- **Review4 (Claude)**: schema tool khoan dung (`how` mặc định `said`, `ask_user` cắt chữ dài, bọc câu đơn, bỏ khóa thừa, `axis` lạ = `place`). Bench Gemma: dừng ở `tool_fail_cap` 10 → 6/76, `schema_refused` 78 → 51, mất người đi cùng 11 → 7/47, Grab/taxi sai 1 → 0/6.
- **Deploy 15:52** (người dùng cho phép): sửa lỗi production do bản deploy 14:43 (web không vẽ được deck). Kiểm trên site thật bằng khách: deck hiện, Board đúng (`frontend_images/live-understand-deck.png`).
- Kiểm chứng: e2e trên backend thật `logs/sol_out/e2e_p5.py` (7 tab → Lựa chọn → "Lập lịch" bị chặn kèm đọc lại → xác nhận digest → Planning) PASS; ảnh `node logs/sol_out/shots_p5.mjs` → `frontend_images/understand-*.png`, `plan-*.png`; `tsc -p web/tsconfig.json --noEmit` sạch; bộ test đầy đủ 1717 passed, lỗi còn lại xem §1.4 và 3 lỗi cũ (planning boundaries `[engine.py]`, `[tools.py]`; decision `test_agent_sees_every_shown_place_but_reasons_only_for_the_first_page`).

## 3. Việc còn lại (theo thứ tự ưu tiên)

1. Bench đầu–cuối có bấm deck như người dùng thật (đo số lần chạm tới khi đủ, đọc lại đúng, lịch tôn trọng khung).
2. Bớt câu hỏi: trung vị ≤ 3 lần chạm (điền sẵn số người từ "với người yêu", chỗ ở "chưa đặt"…). Hiện sau lời kể còn thiếu trung bình 5,9/7 câu.
3. Đọc lại: giữ ✕ cho từng suy luận khi bản đọc dài (đang gộp), bỏ lặp "ngắm hoàng hôn lúc hoàng hôn", dòng mặc định viết "các ngày khác 08:00–21:00". Câu hỏi "Ngày đi" quá dài (4 dòng).
4. Decision spec (`2026-10-15-place-decision-needs-design.md`): đọc `wishes` (món, loại nơi, "giống X"), nhu cầu theo khung ngày, "đủ cho lịch", meal pool.
5. Planning spec (`2026-10-15-planning-day-frame-design.md`): chia ngày quanh `busy`, cửa sổ giờ từng nơi, bữa ăn mỗi ngày, `frame_report`.
6. Phần 6: tín hiệu hành vi (R §15), gộp spec vào `docs/TRIP_UNDERSTANDING.md` và `docs/UI_SPEC_USER_WEB.md`, xóa spec làm việc.
7. Độ trễ khi đông: 38 người cùng lúc p50 ~25 s, p90 ~45–55 s (một người ~3 s).

## 4. Luật khi làm tiếp

- Pytest luôn có `--collect-in-virtualenv` (không có thì treo do NFS trong `.browser/`).
- Code giao sol qua `logs/sol_out/run_sol.sh <brief> <log> high` (9router giờ ở `localhost:20128`, key `JUDGE_*` trong `.env`); Claude thiết kế, viết test, kiểm. Khi sol bị chặn, người dùng cho phép Claude tự làm.
- Frontend chỉ hiển thị backend; giao diện hiện tại là prototype về hình thức: không đổi màu, vibe, thành phần đã thiết kế; chỉ căn bố cục. Sửa UI thì chạy `/ui-ux-pro-max` trước. Tên ngắn, không văn nói.
- Deploy chỉ khi người dùng nói rõ, bằng `./run.sh prod`; sau deploy kiểm site thật bằng khách (Playwright, `chromium-1169`).
- Cây làm việc dùng chung: không git add/commit/checkout/stash.
