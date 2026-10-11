# Tổng kết Trip Understanding · Place Decision · Planning (2026-10-07)

Tài liệu làm việc, không phải tài liệu chính thức (`RULE.md` §0.1). Tóm tắt ba module online như code hiện tại, những gì đổi trong phiên 2026-10-07, kết quả benchmark đầu tiên và việc còn lại. Chi tiết nằm ở tài liệu chính thức được trỏ trong từng mục.

## 1. Bức tranh chung

```text
Web ──► harness (router, revision, snapshot, handoff; không gọi LLM)
          ├─ trip      câu tự do + chip  ──► Trip State ──► Search Input
          ├─ decision  shortlist + tuyển chọn ──► Decision Output (địa điểm đã xác nhận)
          └─ planning  phương án lịch + sửa ──► Plan Output
```

- Mỗi module sở hữu state, tool, guard của mình; harness chỉ điều phối qua public API (`docs/AGENT_HARNESS.md` §1–3).
- Chip, sửa panel, act, router **không gọi model**. Model (vai trò `Agent`, Gemma trên UIT) chỉ chạy cho câu gõ cần suy luận và cho đề xuất nội bộ của Planning (`docs/AGENT_HARNESS.md` §5).
- Bất biến: không bịa địa điểm; thiếu bằng chứng là `unknown`; hard constraint fail-closed; physical constraint không có đường code nào nới.

## 2. Trip Understanding — `src/trip/`

**Vai trò.** Hiểu chuyến này cần gì, hỏi ít nhất có thể, xuất Search Input cho Decision (`docs/TRIP_UNDERSTANDING.md` §1, §9).

**Cách chạy một lượt** (`§4`, `§14`):

| Đầu vào | Xử lý | Gọi model |
|---|---|---|
| Chip, sửa panel, "Xem gợi ý" | Rule tất định ghi Trip State | Không |
| Câu gõ chỉ có số ngày / số người / phương tiện | Heuristic `frame` | Không |
| Câu gõ chỉ lặp nhãn một chip của thẻ đang mở, hoặc "bỏ qua" / "không chắc" | Heuristic `chip_echo` (mới) | Không |
| Câu gõ còn lại | prepass → S1 (Laya, đang tắt) → Agent → guard | 1 call |

Guard kiểm mọi update của Agent: quote phải nằm trong câu người dùng, giá trị phải parse được, câu hỏi tier 1 luôn thắng lựa chọn của Agent, `say` không được nêu số hay tên địa điểm người dùng chưa nói.

**Chọn câu hỏi và dừng** (`§5–7`): tier 1 (safety, khung chuyến, anchor trùng tên, ngày) luôn hỏi; câu thích ứng theo điểm giá trị thông tin; dừng khi điểm thấp, hết `turn_budget` (5), hoặc `idle_limit` (2) câu liên tiếp không thêm gì.

**Đổi trong phiên này** (code ở `engine.py`, `heuristics.py`, `state.py`; test ở `tests/trip/test_engine.py`):

- **Câu gõ không còn làm mất câu hỏi đang mở.** Thẻ chỉ tính là đã hỏi khi câu gõ ghi được field của thẻ. Câu lạc đề giữ thẻ mở (`meta.held`), không tốn ngân sách; câu thứ hai như vậy liên tiếp thì thẻ đóng như cũ. Câu không thêm gì vẫn tính vào `idle_limit`.
- **Chip và chữ cùng lượt:** chữ thắng cho cùng field, và lời đáp nói rõ "Mình ghi theo câu bạn gõ: …".
- **`chip_echo`:** gõ lại đúng nhãn chip được xử lý như bấm chip, không gọi model. Không áp dụng cho thẻ Agent viết và thẻ có ô nhập chữ. Gõ "đi lại bình thường" giờ đóng được thẻ safety.
- Tài liệu đã cập nhật: `docs/TRIP_UNDERSTANDING.md` §7, `docs/AGENT_HARNESS.md` §5.

**Lỗi và lỗ hổng đã biết:**

| Mức | Vấn đề | Bằng chứng |
|---|---|---|
| P0 | Agent có thể ghi hard filter **ngược chiều**: "tránh dốc, bậc thang" thành `steep_or_stairs = present` (bắt buộc có), guard để lọt | Smoke live t01: Decision chọn 6 nơi vi phạm giới hạn thật |
| P1 | Người dùng gõ chữ bị kẹt ở thẻ tier 1 (`dates`, `c_other`, `policy:*`) và thẻ `clarify:*`: câu văn xuôi không đóng được thẻ, thẻ quay lại mãi | Live đêm 2026-10-07: 3/8 chatter và 8/8 brief kẹt (số tạm, run chưa xong) |
| P1 | Người chỉ bấm chip **không báo được** đau gối, xe lăn, ăn chay, say xe, sợ độ cao (chỉ "bố mẹ" và "trẻ nhỏ" mở thẻ safety); cũng không chọn được 6–7 ngày, tháng, số người, điều muốn tránh | Bench offline: `safety_unreachable` = 12, kéo theo 18 nơi vi phạm ở 4 chuyến |
| P2 | Chip ngân sách ghi mức trần của khoảng (300k / 700k / 1,5tr); `purpose` không vào Search Input | Đọc code |

**Đã duyệt, chưa làm (sub-project B):** đường brief cho người viết dài (`TRIP_BRIEF` chỉ trích xuất, read-back dựng từ panel, chỉ hỏi câu bắt buộc; mục tiêu tiến độ < 2 s, read-back < 10 s p90); model chỉ ghi đoạn trích + nhãn, code quy đổi tiền / ngày / tên địa điểm; `visited`; `card_answer` cho thẻ đang mở (câu nới safety chỉ nhận khi thẻ đang mở và `how = said`); hỏi bằng văn xuôi và nhớ 3 lượt gần nhất; gắn giá trị cho chip của thẻ Agent viết.

## 3. Place Decision — `src/decision/`

**Vai trò.** Từ Search Input và serving index, giúp người dùng chọn một tập địa điểm nhỏ, đã kiểm, trước khi xếp lịch. Hỗ trợ chọn, không chọn thay (`docs/PLACE_DECISION.md` §1).

**Luồng** (`§3–15`): resolve anchor → truy xuất ứng viên → sàng lọc constraint fail-closed (`pass` / `fail` / `unknown`, lưu lý do loại) → độ hợp bối cảnh thô → xếp hạng → gom nơi gần trùng, chia nhóm, shortlist → người dùng tuyển chọn (chọn, bỏ kèm lý do, khóa, đổi, nới có ghi nhận, so sánh, "vì sao không") → kiểm khả thi tổ hợp → Decision Output.

**Câu gõ:** một Agent call mỗi lượt biến câu thành act có kiểm; heuristic `exact_command` xử lý "chọn / bỏ / khóa <tên đầy đủ>" không gọi model (`docs/AGENT_HARNESS.md` §5). Địa điểm ngoài màn hình không bị bịa vào lựa chọn.

**Đổi trong phiên này:** không đổi code Decision.

**Đã duyệt, chưa làm (sub-project C):** "chọn giúp phần còn lại" — act ủy quyền rõ, giữ điểm khóa, không nới constraint; kết hợp với đường brief để người viết "lên lịch giúp mình" đi thẳng tới lịch (`docs/plans/ONLINE_FLOW_OPTIMIZATION.md`).

**Đo riêng:** `python -m decision evaluate` trên `config/eval_trips.yaml` (`§17`).

## 4. Planning — `src/planning/`

**Vai trò.** Xếp các địa điểm đã xác nhận thành lịch theo ngày, có kiểm cuối, độ vững và dự phòng (`docs/PLANNING.md` §Mục tiêu).

**Thuật toán** (`§Thuật toán`): gom cụm, chia ngày → thứ tự trong ngày → giờ tham quan, đệm, bữa → `validate.py` kiểm lại toàn bộ timeline (nơi duy nhất quyết định đạt / không) → độ vững → nhiều phương án theo mục tiêu → dự phòng. Chỗ ở crawl nền, không bắt người dùng chờ. Người dùng sửa bằng act; Agent chỉ đề xuất nội bộ, đề xuất phải qua kiểm lại (`§Agent đề xuất nội bộ`).

**Đổi trong phiên này — sửa lỗi xác nhận:**

- **Triệu chứng:** phương án hiện "hợp lệ" nhưng bấm xác nhận bị từ chối "plan has unresolved violations" (9/80 lần chạy bench).
- **Nguyên nhân gốc:** ngày sau có điểm bình minh thì bộ xếp lịch kéo giờ bắt đầu sớm (`early_start`), nhưng giờ đó chỉ nằm trong lịch đã dựng; bước xác nhận dựng lại ngày với giờ gốc nên thấy "bắt đầu trước giờ của ngày".
- **Sửa:** quy tắc thành một hàm `pull_early` (`build.py`); bước dựng lịch và mọi chỗ kiểm lịch đã dựng (hiển thị, đề xuất, xác nhận) áp cùng quy tắc qua `_ctxs_for(..., results)` (`engine.py`). Không nới kiểm tra. Test: `tests/planning/test_planning_engine.py::test_a_variant_whose_later_day_opens_early_for_a_sunrise_place_confirms`.
- **Tác dụng:** tỉ lệ ra được lịch trong bench 80% → 95% (tapper), 75% → 82,5% (baseline).

**Còn mở:** `no_valid_variant` vẫn còn ở 2/40 (tapper) và 7/40 (baseline) chuyến, chưa điều tra (có thể do quy tắc chọn nơi của bench); dữ liệu gắn mốc bình minh cho cả quán bar ("The Balcony Speakeasy"); offline không có OSRM và thời tiết nên 49/62 lịch "fragile" — số độ vững offline chưa có nghĩa.

## 5. Benchmark — `src/bench/` (mới)

Đo cả hành trình Trip → Decision → Planning qua harness thật, so với Trip State ẩn biết trước (`docs/TRIP_UNDERSTANDING.md` §16). Thiết kế và quyết định: `docs/plans/BENCH.md`.

- **40 chuyến ẩn** sinh tất định (`python -m bench generate --seed 1`), đóng băng ở `config/bench_trips.yaml`, kèm brief do Gemma viết.
- **Kiểu người dùng:** `tapper` (chỉ bấm chip đúng sự thật), `baseline` (form cố định 14 field), `brief` (một tin dài rồi trả lời tiếp), `chatter` (Gemma đóng vai, trả lời mọi thẻ bằng văn xuôi). Downstream giống nhau cho mọi kiểu.
- **Verdict mỗi field:** `correct`, `wrong`, `missing`, `invented` (phải bằng 0), `inferred` (giá trị chip tự thêm), `unreachable` (chip không diễn đạt được), `ok_unknown`.
- **CSV** trong `data/bench/<thư mục>/`: `runs.csv` (một dòng mỗi chuyến × kiểu), `fields.csv` (mỗi field), `summary.csv` (mỗi kiểu). Ghi sau từng lần chạy; `--resume` chạy tiếp phần thiếu.
- **Chạy:** `python -m bench run` (offline, không gọi model); `python -m bench run --live --styles chatter,brief` (cần `USER_SIM_*`); qua đêm: `scripts/bench_live.sh [DAY]`.

**Kết quả offline sau khi sửa lỗi xác nhận** (`data/bench/20261007-231922`):

| Kiểu | Thẻ hỏi | Độ chính xác field | Bịa | Safety bỏ sót | Safety chip không diễn đạt được | Nơi vi phạm giới hạn thật | Ra được lịch | Nơi không rõ giờ mở |
|---|---|---|---|---|---|---|---|---|
| tapper | 6 | 0,66 | 0 | 0 | 12 | 18 | 95% | 27% |
| baseline | 14 | 1,00 | 0 | 0 | 0 | 0 | 82,5% | 26% |

Đọc: hỏi ít hơn 8 thẻ đổi lấy thiếu `pace` ở 31/40, ngân sách 31/40, sở thích 24/40 chuyến. 18 nơi vi phạm đều thuộc 4 chuyến có giới hạn mà chip không diễn đạt được; hệ thống không vi phạm filter nào nó đã biết.

**Live đêm 2026-10-07** (`data/bench/live-20261007/`, đang chạy lúc viết): khi xong có `DONE` và hai bảng tổng hợp cuối `log.txt`. Số tạm sau 8 chuyến: chatter 5/8 ra Search Input, brief 0/8 — tất cả kẹt ở thẻ không đóng được bằng chữ (lỗi P1 ở §2). Người dùng giả được cho bảng giải nghĩa mã để không nói sai sự thật (vd. `ride` = Grab/taxi).

**Chưa làm:** gate pytest `tests/bench` (ngưỡng chưa hiệu chỉnh); sửa hai check luôn-đúng và lỗi `relaxed` của `scripts/journey_sim.py`; tách "vi phạm filter đã biết" khỏi "vi phạm filter chưa học được"; cho người dùng giả bấm chip sau khi bị hỏi lại (hiện bench dừng lần chạy là `stuck`).

## 6. Việc tiếp theo, theo thứ tự đề xuất

1. Sửa P0: guard từ chối hard filter `=` cho feature nhóm effort / safety (Trip).
2. Đọc kết quả live, rồi làm B: `card_answer` và trả lời thẻ tier 1 bằng chữ trước (gỡ kẹt), sau đó đường brief.
3. Lỗ hổng chip (D): chip safety cho các tín hiệu cơ thể, 6–7 ngày, tháng, số người.
4. C: "chọn giúp phần còn lại" trong Decision.
5. Hoàn tất gate `tests/bench`, rồi gộp nội dung còn giá trị của tài liệu này và `docs/plans/BENCH.md` vào tài liệu chính thức và xóa hai file (`RULE.md` §0.1).

Lưu ý môi trường: serving data được phiên corpus khác dựng lại lúc 22:48 (1704 → 1696 nơi); journey_sim và bench chạy trên dữ liệu thật nên số có thể đổi giữa các lần chạy. Chưa commit gì trong phiên này.
