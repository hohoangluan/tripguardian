# Kế hoạch: nâng chất lượng corpus cho Place Decision

Plan làm việc tạm (`RULE.md` §0.1): khi xong từng việc, gộp phần còn giá trị vào `docs/specs/CORPUS_SPEC.md` / `docs/CORPUS.md` / `docs/log/DEV_LOG.md`, xóa mục tương ứng ở đây; hết việc thì xóa file.

Hiện trạng (2026-10-02): ontology v5, 1437 địa điểm đã observe + aggregate (`data/intel/places/`), đo chất lượng và lỗ hổng: memory `observe-quality-audit`, `observe-pending-tasks`. Mục tiêu: Place Decision (`docs/PLACE_DECISION.md`) đọc được corpus mà không vi phạm ràng buộc cứng.

Mỗi việc ghi: đầu ra, file, các bước, nghiệm thu, ước lượng. Ước lượng là ngày công của một session làm tuần tự, chưa tính thời gian máy chạy (ghi riêng).

## Thứ tự và phụ thuộc

```text
V2 gán nhãn (người) ─────────────┐        chạy song song với V1, V3
V1 prompt + extractor + chạy lại ─┼──► V5 serving record + gom nhóm ──► V6 bộ đánh giá offline
V4 bằng chứng effort (TikTok, ảnh)┘
V3 thời gian + giá + ontology  ──► gộp vào lần chạy lại của V1
```

Gộp mọi đổi prompt / ontology (V1, V3) vào **một** lần chạy lại: đổi prompt hay hint là mất cache toàn bộ.

## V1 — Sửa prompt, thử extractor mạnh hơn, chạy lại

- Đầu ra: ba feature hết lỗi đã đo; một lần `gmaps observe` + `aggregate` trên toàn bộ.
- File: `config/ontology.yaml`, `src/corpus/llm/tasks.py` (`REVIEW_OBSERVE`, `REVIEW_VERIFY`), `src/corpus/llm/roles.py` (model của vai trò).
- Việc:
  1. `condition_change`: `improved` đúng ~30% (711 lần, đa số xe thuê "xe mới"). Siết hint + claim (chỉ "so với trước đây của chính nơi này"), hoặc bỏ `improved`, giữ `declined`.
  2. `long_walk` `present` ~65%: "đường đi vào quán hơi xa" (đi xe) vẫn lọt. Thêm phản ví dụ vào hai prompt; cân nhắc bắt buộc quote có "đi bộ" / khoảng cách / thời gian.
  3. `weather_exposed` `sheltered` ~50%: "trời mưa che dù ra tận xe", xe thuê "đi ko sợ mưa gió". `sheltered` phải nói về mái che / trong nhà của nơi đó.
  4. Lỗi nhỏ: `booking_needed` yes từ chuyện người viết đã đặt ("Đặt bàn tr xác nhận có bàn…"); `visit_duration` lẫn thời lượng liệu trình spa; `steep_or_stairs` absent từ "Đi thẳng xe lên cao nhất".
  5. Thử extractor mạnh hơn trên cùng bộ 62 mẫu đã chấm tay (và bộ nhãn V2 khi có): nếu hơn rõ rệt thì dùng cho nhóm effort + suitability, Gemma cho phần còn lại. Cấu hình ở `roles.py`; đổi model là mất cache.
  6. Bộ kiểm trước khi chạy: `python scripts/observe_prompt_eval.py` (16 câu chuẩn, kỳ vọng in OK / FAIL) và `python scripts/observe_places_eval.py` (6 place thật, so bản đang lưu với prompt mới, không ghi file). Thêm câu mới cho từng lỗi sửa. Cần mạng UIT.
- Nghiệm thu: 5 feature trên đạt ≥ 85% trên bộ nhãn V2 (hoặc mẫu chấm tay ≥ 60 mục / feature); `python -m pytest -q` pass; `DEV_LOG` cập nhật.
- Ước lượng: 0,5–1 ngày sửa + thử; **chạy lại 3,5–7 giờ** (1437 địa điểm, mạng UIT, key Gemma dùng chung 40 call). Chạy bằng `Start-Process -WindowStyle Hidden` để không chết theo phiên.

## V2 — Gán nhãn chuẩn (người + code ngưỡng)

- Đã có (2026-10-02): backend `src/corpus/review/labels.py` + route `/api/labels/*` + màn Admin `Gán nhãn` (`/admin/labels`), `labels.jsonl` append-only, thống kê độ chính xác theo (feature, value) với cận dưới Wilson (`GATE_MIN_N = 30`, `GATE_LOWER = 0.8`). Quyết định ở màn `Hàng đợi duyệt` ghi vào `decisions.jsonl` (kind `feature_review`).
- Chạy: `python -m corpus review` (cổng 8765) và `cd web && npm run dev`; mở `http://localhost:5173/admin/labels`. Phím: `c` đúng, `w` sai, `u` không chắc, `s` bỏ qua.
- Việc còn lại (người): gán ≥ 30 nhãn đúng/sai cho mỗi giá trị quan trọng, ưu tiên nhóm effort, suitability, `booking_needed`, `weather_exposed`, `entry_fee`, `visit_duration`. Khoảng 300–500 nhãn, ~1–1,5 giờ nếu đạt 5 nhãn/phút, thực tế 3–4 giờ.
- Việc còn lại (code, 0,5 ngày):
  1. `aggregate` đọc `labels.stats()`: mỗi (feature, value) có cờ `servable` (đạt ngưỡng) và `measured_precision`; giá trị không đạt không được phục vụ một mình (cần xác nhận người hoặc nguồn thẩm quyền). Quy tắc ghi vào `CORPUS_SPEC.md` §5/§6.
  2. Nhãn sau V1 phải gán lại: nhãn gắn với id observation `gmaps:<review_id>:<n>`, đổi prompt thì id có thể trỏ tới nội dung khác. Lưu thêm `prompt_hash` / quote vào bản ghi nhãn, hoặc chỉ tính nhãn có quote trùng quote hiện tại.
  3. `decisions.jsonl` kind `feature_review` (accept / disable / report / refresh) chưa được `aggregate` đọc: `disable` phải loại giá trị khỏi serving, `accept` đặt `needs_review = false`.
- Nghiệm thu: số liệu `/api/labels/stats` khớp tay trên 20 mục; test cho từng quy tắc; `needs_review` giảm theo quyết định.
- Ước lượng: 0,5 ngày code + 3–4 giờ người gán nhãn.

## V3 — Thời gian tham quan, giá dạng số, ontology

- Đầu ra: `visit_duration` phủ cao hơn 19%; giá vé/giá món dạng số; ontology bổ sung theo nhu cầu thật.
- File: `config/ontology.yaml`, `config/` (mặc định theo category, mới), `src/corpus/observe/gmaps/*`, `src/corpus/aggregate/place.py`.
- Việc:
  1. Mặc định thời gian tham quan theo category trong config (min / typical / long), hiển thị là `estimate`, không bao giờ là fact; feature `visit_duration` từ review chỉ ghi đè khi `n` đủ.
  2. Giá dạng số: trích số tiền từ review (`entry_fee` hiện chỉ có/không) và `tickets` thô của Maps (`place.json`.`tickets`, giá US$; đổi VND và ghi nguồn). `price_range` mới có 779/1437.
  3. Ontology: xem `data/gmaps/observe_summary.json`.`proposed_top`. Đáng thêm: `kids_suitable` (đã có `kids`, gộp), `toilet_condition`, `mosquitoes`, `tasting_available`, `costume_rental`, `small_space`. Bỏ qua `vehicle_condition`, `delivery_service`, `strawberry_quality` (không phục vụ quyết định chọn điểm đến). Thêm khi nào nhóm đề xuất ≥ 3 nguồn độc lập (`CORPUS_SPEC.md` §4), version ontology lên 6.
  4. 41 địa điểm không có category: lấy từ `place.json` hoặc `filter`/`list`.
- Nghiệm thu: test cho parse giá; 100% địa điểm có khoảng thời gian tham quan (từ review hoặc mặc định, ghi nguồn); ontology v6 qua `tests/test_ontology.py`.
- Ước lượng: 1–1,5 ngày; gộp vào lần chạy lại của V1.

## V4 — Bằng chứng effort từ TikTok và ảnh Maps

Hiện 63% địa điểm không có bằng chứng effort; fail-closed nên các nơi này không vào danh sách chính khi user có điều kiện dốc / bậc / đi bộ xa.

- **V4a TikTok observe** (`src/corpus/observe/tiktok/`, mới; mỗi nguồn một module, `RULE.md` §2).
  - Đầu vào: cặp (video, địa điểm) `yes` từ `place_verify.evidence_pairs()`; transcript đã kiểm (`asr_check`), keyframe, `screen_text`.
  - Việc: Extractor trích observation cùng format (`src/corpus/observe/__init__.py`), span = đoạn transcript có timestamp (`start_s`, `end_s`) hoặc frame; gate: quote có trong transcript, timestamp trong video; ontology dùng chung. Feature hợp với video: effort (bậc, đường vào, dốc), `setting`, `crowd`, `scenic_view`, `weather_exposed`. `aggregate` đọc `data/tiktok/observations/` không đổi code (nguồn `tiktok_segment`, loại `video`).
  - Phụ thuộc: crawl TikTok còn dở (lúc tạm dừng 754/2595 video, `docs` memory `tiktok-crawl-resume`); Gemma cần mạng UIT.
  - Ước lượng: 1,5–2 ngày code + thử; chạy Gemma trên ~1000–2500 video 2–5 giờ; **crawl TikTok phụ thuộc mạng và chống chặn, có thể thêm nhiều ngày**.
- **V4b Ảnh Maps + đọc ảnh**: crawl ảnh Maps theo địa điểm (phase mới `gmaps photos`, ghi `data/gmaps/places/<fid_dir>/photos/`), Gemma đọc ảnh nhận bậc thang / mái che / trong nhà-ngoài trời. Ước lượng 1,5–2 ngày code, 1 ngày chạy.
- **V4c Mặc định theo category**: bảng trong config cho nơi mà effort gần như chắc chắn (spa, nhà hàng mặt phố); ghi rõ `estimate`, hiển thị "chưa xác minh". Không miễn kiểm tra theo category: 9/56 quán cà phê có bằng chứng dốc (nhiều quán ở đồi). Ước lượng 0,5 ngày.
- Nghiệm thu: độ phủ nhóm effort tăng từ 37% lên mục tiêu ≥ 70%, độ chính xác ≥ 85% trên nhãn V2 cho nguồn mới; nhãn V2 hỗ trợ nguồn TikTok (mở rộng `labels.py`: id observation theo nguồn).

## V5 — Serving record + gom nhóm gần trùng

- Đầu ra: module đọc intel → bản ghi phục vụ cho Place Decision (`docs/PLACE_DECISION.md` §2.2, `CORPUS.md` §5).
- File mới: `src/corpus/serving/` (công khai qua `__init__.py`), `tests/serving/`; không import nội bộ module khác.
- Việc:
  1. Serving record: Identity (id, category, lat/lng), Operation (giờ, giá, đặt chỗ, thời gian tham quan = khoảng), Experience, Environment, Effort, Suitability, Provenance (trạng thái và coverage theo khía cạnh, 4 thành phần confidence). Trạng thái `VERIFIED | UNCERTAIN | OUTDATED` được phục vụ; `NEEDS_REVIEW`, `DISABLED` không bao giờ (dùng quyết định V2).
  2. `usable_as` = experience | meal | anchor | backup, tính từ category + coverage (nhà hàng chỉ có inventory là meal / anchor / backup).
  3. `servable` theo ngưỡng độ chính xác V2 cho từng (feature, value).
  4. Cờ độ mới: giờ quá hạn → `OUTDATED`; `closure` ≠ null → `DISABLED` cho physical constraint.
  5. Gom nhóm gần trùng (§9): cùng category, trùng phần lớn feature có bằng chứng, cùng vai trò; chọn đại diện kiểu MMR. Hàm thuần, test được.
  6. Cụm không gian từ lat/lng (khu vực quanh Đà Lạt) để Hợp bối cảnh §7.
- Nghiệm thu: test bất biến của `CORPUS_SPEC.md` (không phục vụ `NEEDS_REVIEW` / `DISABLED`; `unknown` không thành `false`; xung đột không làm phẳng); đọc được 1437 địa điểm trong < vài giây.
- Ước lượng: 2–3 ngày.

## V6 — Bộ đánh giá offline cho Place Decision

- Đầu ra: script mô phỏng vài chục Trip State ẩn, chạy sàng lọc + xếp hạng trên serving record, đo các chỉ số `PLACE_DECISION.md` §17: **vi phạm ràng buộc cứng trong shortlist = 0**, tỉ lệ nơi gần trùng, tỉ lệ `unknown` bị đẩy vào danh sách chính.
- Phụ thuộc: V5. Ước lượng 1–2 ngày.

## Tổng

| Việc | Code | Thời gian máy | Người |
|---|---|---|---|
| V1 | 0,5–1 ngày | 3,5–7 giờ | — |
| V2 (còn lại) | 0,5 ngày | — | 3–4 giờ gán nhãn |
| V3 | 1–1,5 ngày | gộp vào V1 | — |
| V4 | 3,5–4,5 ngày | 3–5 giờ + crawl TikTok chưa biết | — |
| V5 | 2–3 ngày | giây | — |
| V6 | 1–2 ngày | — | — |

Tổng khoảng 9–13 ngày công tuần tự; chia hai session song song (V1+V3+V2 | V4 rồi V5+V6) còn khoảng 5–7 ngày thời gian thực, chưa tính crawl TikTok.

## Ghi chú vận hành

- Gemma (UIT) chỉ truy cập được trên mạng UIT; key chung 40 call đồng thời với `asr_check` / `place_verify` / `gmaps observe`.
- Tiến trình dài chạy bằng `Start-Process -WindowStyle Hidden`, `sh` = `D:\AppDownload\Git\usr\bin\sh.exe`. Tác vụ nền của phiên Claude chết khi đóng phiên; mọi phase tiếp tục từ file trên đĩa.
- Docs `CORPUS_SPEC.md`, `CORPUS.md`, `PLACE_DECISION.md`, `DEV_LOG.md` đang có sửa đổi chưa commit của nhiều session; khi commit docs xem `git diff` từng file, đừng gộp mù.
