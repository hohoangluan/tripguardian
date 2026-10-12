# BENCH — spec làm việc (tạm thời)

Đo Trip Understanding bằng user giả lập có Trip State ẩn, chạy qua harness thật (Trip → Decision → Planning) trên dữ liệu serving thật. Khi xong: gộp phần còn giá trị vào `docs/TRIP_UNDERSTANDING.md` §16 rồi xóa file này (`RULE.md` §0.1).

## Thành phần

- `src/bench/hidden.py` — `HiddenTrip`: sự thật của một người (khung, khẩu vị, cơ thể → hard filter, anchor, `indifferent`, `brief`).
- `python -m bench generate --seed 1` → `config/bench_trips.yaml` (40 chuyến, cố định, check in). Quota: mỗi signal ≥ 3, mỗi companions ≥ 5, mỗi mobility ≥ 8. Loại chuyến mà hard filter còn < `top_k` nơi pass theo `corpus.serving.check`. `--briefs` cần `USER_SIM_*` + `--live`.
- `python -m bench run [--styles tapper,baseline,brief] [--only ids] [--live]` → `data/bench/<timestamp>/{runs,fields,summary}.csv`, session ở `.../sessions/`.
- `config/bench.yaml` — ngưỡng gate + `gate_trips` (10 chuyến). `tests/bench/` chạy gate offline.

## Kiểu user

- `tapper` (offline): **chỉ bấm chip**, không bao giờ gõ. Bảng (qid, chip) → (field, value) nằm trong bench. Field không có chip → `skip`; qid lạ → `skip` và tăng `unmapped_chips`. `ready` → `show`; `show_first` → `more` nếu còn khẩu vị chưa nói, else `show`; `policy:*` → `exclude`; `closed:*` → `keep`.
- `baseline`: form cố định 14 ô (days, dates, companions, people, mobility, base, pace, crowd_tolerance, novelty, budget_vnd, loves, avoids, giới hạn sức khỏe/ăn uống → hard filter, anchors) điền từ sự thật, dựng `trip.SearchInput` trực tiếp, đưa vào `decision.Tools` / `planning.Tools`. turns = 14. `purpose` không có trong Search Input → không chấm (`n/a`).
- `brief`: gửi brief làm lượt gõ rồi tapper trả lời tiếp; không có brief → `no_brief`.
- `chatter` (chỉ live): USER_SIM trả lời mọi thẻ bằng lời.

## Downstream chung

Sau `done` → `advance` → chọn theo thứ tự hiển thị các thẻ `main`: `2 × days` experience + `1 × days` meal (days lấy từ Search Input, thiếu thì 2), bỏ nơi đã chọn sẵn (anchor) → `advance` → variant đầu tiên nếu view `ok` → `confirm`.

## Chấm điểm

Verdict mỗi field: `correct`, `wrong`, `missing`, `invented`, `ok_unknown`, `inferred`, `unreachable`, `n/a`.

- `inferred`: giá trị sự thật không có, hệ thống ghi với nguồn suy ra (mark ✎, `source != user`, hoặc soft do chip của thẻ khác ghi kèm). Cột `fields_inferred`.
- `invented`: giá trị ở field sự thật để `indifferent` (hoặc soft/hard/anchor thừa) mà không có nguồn suy ra. Gate = 0.
- `unreachable` (chỉ tapper): sự thật không chip nào diễn đạt được: `people`, days 6–7, `month`, avoids, love ngoài thẻ vibe, anchors, base khi thẻ base không hiện, hard filter của signal không phải parents/kids (`safety_unreachable`). Ngoài accuracy.
- accuracy = correct / (correct + wrong + missing).
- budget: đúng khi cùng bucket chip (<300k, 300–700k, 700k–1.5M, >1.5M).
- `safety_missed`: hard filter mong đợi, reachable, không có trong Search Input. Gate = 0.
- `hard_violations`: nơi confirmed fail hard filter **của sự thật** (`corpus.serving.check`; `eq` kiểm tương tự), trừ nơi user relax (per confirmed place). Gate = 0.
- `unknown_hours_share`: nơi confirmed có `operation.hours` = None.

## Câu hỏi mở

- Coverage của Trip (`steep_or_stairs` 38 nơi pass, `long_walk` 18) lệch xa `corpus.serving.check` (1257 / 1488): generator loại chuyến theo serving check, nên gần như không loại.
- `lost_questions`, `silent_overrides` chưa đo.
