# Bằng chứng pitch theo thang điểm 100 — 17/10/2026

Bảng ngắn theo 6 tiêu chí nằm ngay đầu [pitch_desk.md](../pitch_desk.md). File này chỉ để tra nguồn khi phản biện. Các điểm 20/15/20/20/15/10 là trọng số của ban giám khảo, không phải điểm tự chấm.

## 1. Số nào dùng ngay

| Bằng chứng | Kết quả | Nguồn / phạm vi |
|---|---|---|
| Nhu cầu người dùng | 21/47 (44,7%) khó nhất ở cân đối lịch; 18/47 (38,3%) ưu tiên lịch hợp lý | Khảo sát đã lọc, cách tính ở pitch §Phụ lục A; tái sử dụng số khảo sát, không thu mẫu mới |
| Giá trị cảm nhận | Hỗ trợ cân nhắc địa điểm 4,03/5; 27/36 (75%) dùng nguyên hoặc chỉ chỉnh nhỏ | 36 người tạo được lịch; tự báo cáo, chưa đối chứng |
| Phù hợp tiếng Việt | “2 triệu cả chuyến, 2 người, 2 ngày” → 500.000đ/người/ngày; đúng scope, không đoán | [Hai lượt Agent thật](evidence/pitch_20261017/trip_live.json), 7,853 giây cho câu ngân sách |
| Hỏi lại thay vì suy đoán sức khỏe | “Mình đi Đà Lạt cùng ba mẹ.” → hỏi về đi bộ xa/dốc/cầu thang; chưa tạo hard constraint | Cùng transcript; 4,238 giây; một lần mỗi câu, không phải tỷ lệ chính xác trên tập lớn |
| Chọn nơi có căn cứ | 30 ca: 0 vi phạm, 0 `unknown` vào shortlist; 29/30 đủ ≥8 nơi | [Decision](evidence/pitch_20261017/decision.json); `group_food` thiếu do bằng chứng mỏng; p50 80 ms, max 326 ms là thời gian pipeline |
| Kiểm thử phần mềm | **2.950 pass, 0 fail, 3 skip, 7 deselected**, 446,46 giây | [Tổng hợp](evidence/pitch_20261017/tests_summary.json), [JUnit](evidence/pitch_20261017/tests.xml); có Postgres, loại crawler/live |
| Lập lịch và chốt | 10/10 chốt được | [Planning](evidence/pitch_20261017/planning.json); API trong tiến trình, không có chat/browser |
| Bắt lịch cố ý sai | 30/30 phát hiện; 0/30 đối chứng bị báo nhầm | [Bơm lỗi](evidence/pitch_20261017/validator.json); 6 nhóm × 5 biến thể, dữ liệu tổng hợp |
| Quy mô dữ liệu | 3.172 nơi; 713.216 review; 240.574/769.936 nhãn Judge đánh dấu sai (31,25%) | Serving được kiểm lại; số review/Judge tái sử dụng kiểm đếm 00:13 ngày 17/10 trong `PITCH_SLIDES_8_9_11.md`, không phải accuracy của Judge |
| Truy nguồn thật | Review Trạm Ký Ức “đông quá” → `crowd=high` → serving evidence | [ID, nguồn, observation](evidence/pitch_20261017/review_example.json); câu trích khớp nguyên văn; bối cảnh chưa rõ giữ `unknown` |
| Trải nghiệm giao diện | 3,78/5; 62% chấm 4–5 | n=32 người đã xem/sửa lịch; khảo sát riêng, không gộp với mẫu 36 |

**Cách nói gọn:** “10/10 lịch tạo ra qua kiểm tra; khi cố tình đưa vào 30 vi phạm, hệ thống phát hiện đủ 30, và không báo nhầm trên 30 đối chứng.” Không diễn đạt thành “đúng 100% trong thực tế”.

## 2. Đã kiểm lại lịch sử sửa lỗi

Mốc Git lúc bắt đầu: `4676c67`, checkout có nhiều thay đổi chưa commit. Sửa đổi có sẵn trong checkout được đối chiếu trực tiếp, không nhận là sửa mới trong lượt này:

| Phần | Thay đổi thấy trong code / test | Cách dùng khi pitch |
|---|---|---|
| Decision | Lọc nơi quá xa từ tâm gần nhất; giải thích `why_not`; memo thẻ; xử lý mong muốn ăn uống/đông người; test phân biệt toàn trang với shortlist `top` | Không dùng số 22 fail cũ làm trạng thái hiện tại; phải dựa kết quả chạy mới |
| Trip | `party_size` nhận “nhóm mình 6 đứa”; cơ chế đưa câu hỏi về mục còn thiếu; xử lý tiền/ngày/nhóm | Log `fast1`: **34/35 mục `done`, 4/5 persona đủ 7/7**; [chi tiết](evidence/pitch_20261017/conversation_history.json). `done` không chứng minh tất cả fact đúng hoặc đều do người dùng cung cấp |
| Planning | Cache phép mô phỏng/kiểm tra ngày; chạy các hướng quá tải riêng; kiểm ngân sách/meal/activity; thêm regression test cache | Dùng số mới bên dưới; không quy mọi cải thiện cho một thay đổi khi chưa A/B cùng điều kiện |
| Harness / Web | Handoff quá tải và contract test được cập nhật; landing test được sửa theo giao diện hiện có | Test đổi có thể là cập nhật contract; không gọi mọi test xanh là một lỗi sản phẩm đã sửa |

**Bộ test lớn đã hoàn tất:** **2.950 passed, 0 failed, 3 skipped, 7 deselected**, 446,46 giây; có `TEST_DATABASE_URL`, không chạy `tests/crawl` và marker `live`. Không còn 22 fail trong phạm vi vừa chạy. [Số theo module và lý do skip](evidence/pitch_20261017/tests_summary.json).

**Hồi quy tập trung vừa chạy:** 476 passed, 143 skipped, 6 deselected, 0 fail, 60,05 giây. Gồm Decision, Harness, validator và landing; loại marker `live`/`corpus`, không cấu hình Postgres trong lượt focused nên các ca cần DB bị skip. Không cộng số này vào tổng suite lớn. Bằng chứng gốc: `logs/pitch_recheck_20261017/focused_fast.xml`.

## 3. Hiệu năng — chỉ giữ một con số dễ hiểu trên slide

| Phép đo mới | Nhỏ nhất | Trung vị | Lớn nhất |
|---|---:|---:|---:|
| Dựng phương án Planning (`ms_variants`, 10 ca) | 0,564 s | 7,742 s | 12,118 s |
| Cả lượt evaluator, gồm thử chỗ ở (`ms_total`, 10 ca) | 2,469 s | 9,248 s | 16,428 s |

Số 3,2–30,7 giây trong bản pitch cũ không còn là lần đo mới nhất. Các số mới là thời gian API trong tiến trình, đo khi máy còn chạy test; không bao gồm hiểu nhu cầu bằng Agent, HTTP hoặc render browser. Không ghi “hiệu năng người dùng thấy” cho phép đo này. Số 24/60 ms chọn/bỏ giữ ở Q&A dưới nhãn **số lịch sử**, không cần đưa lên slide chính.

10/10 lịch vẫn ở mức `fragile` (Mong manh), không có OSRM và thời tiết đầy đủ. Tổng di chuyển **dài hơn baseline nearest-neighbour trung bình 22,3%**, chưa chứng minh tiết kiệm di chuyển. Baseline không áp cùng bộ ràng buộc nên không dùng để nói ưu thế tối ưu tuyến.

## 4. Bộ 30 ca và phép bơm lỗi

`config/eval_trips.yaml` có **10 kịch bản đặt tên + 5 bộ lọc × 4 bộ sở thích = 30**. Commit đầu `5440476`, tác giả Git `hoangluan0312`, 02/10/2026. Đây chỉ xác minh người đưa file vào Git; chưa xác minh độc lập người thiết kế. Bộ ca được dùng trong test phát triển nên gọi **bộ nội bộ**, không gọi held-out độc lập.

**Không có ca được gắn ground truth “bất khả thi”.** Decision dùng `budget_vnd=None`; ca tên `no_trap_budget` chỉ lọc bẫy du lịch/xếp ưu tiên giá trị, không kiểm trần tiền. Planning chỉ dùng 10 kịch bản có tên, cùng 3 ngày và ngân sách 3 triệu/người/ngày theo scalar của evaluator; không phải cùng persona 2 ngày/2 triệu của demo. Con số 10/10 không chứng minh mọi yêu cầu đều có lời giải.

Bộ bổ sung tạo trực tiếp lịch sai, không để scheduler tự sửa trước khi kiểm:

| Loại lỗi | Phát hiện | Đối chứng hợp lệ bị báo lỗi |
|---|---:|---:|
| Hai điểm chồng giờ | 5/5 | 0/5 |
| Ghé ngoài giờ mở cửa | 5/5 | 0/5 |
| Chi phí đã biết vượt trần | 5/5 | 0/5 |
| Chặng đi ngắn hơn ma trận yêu cầu | 5/5 | 0/5 |
| Ràng buộc không dốc nhưng không có bằng chứng | 5/5 | 0/5 |
| Ràng buộc không dốc nhưng nơi có dốc | 5/5 | 0/5 |

Mỗi nhóm dịch giờ bắt đầu 0/10/20/30/40 phút. Đây là 6 cơ chế với biến thể, không phải 30 loại lỗi độc lập; không kiểm độ chính xác dữ liệu giờ, giá, đường hoặc thời tiết ngoài đời. Script: `tests/planning/bench_pitch_validator.py`.

## 5. Review thật và mô tả đối thủ

Trạm Ký Ức: câu trích “đông quá” có trong review, observation nằm trong evidence của thuộc tính phục vụ. Google Maps ghi **“một tháng trước”**, observation có mốc dữ liệu `as_of=12/10/2026`; ngày `observed_at=12/09/2026` là quy đổi tương đối, không phải timestamp chính xác. Không gắn thêm “sáng cuối tuần” vào review này. Trạng thái serving `VERIFIED` nói về bằng chứng hỗ trợ, không bảo đảm nơi luôn đông.

Đã mở lại trang chính thức ngày 17/10/2026:

- [Wanderlog](https://wanderlog.com/): gom lịch/bản đồ, tối ưu tuyến, ngân sách và chia chi phí.
- [Layla](https://layla.ai/): chat lập lịch theo ngày/gu/ngân sách; kết hợp tư vấn viên; cho điều chỉnh trước khi đặt.
- [Mindtrip](https://mindtrip.ai/): ghi nhớ gu, cân nhắc đánh đổi, hỗ trợ chọn và đặt dịch vụ, theo dõi thay đổi chuyến đi.

Đây là mô tả nhà cung cấp, không phải kết quả chạy đối thủ. Slide 4 bỏ các cột chưa đo. UI chưa đổi đồng bộ ba nhãn đề xuất; pitch không được nói UI đã đổi.

## 6. Kịch bản quá tải đã lặp 5 lần qua API

**5/5 lần báo quá tải, 5/5 lần chọn phương án và chốt thành công**. Cùng 10 nơi thật, 2 ngày, 2 người, trần 500.000đ/người/ngày; khung ngày 09:00–21:00 và 08:00–18:00. Đầu vào đã cấu trúc sẵn, không gọi Agent hay browser. Tập này trả **2 hướng khác nhau** (`fit`, `travel`), mỗi hướng bỏ 1 nơi; không nói luôn có đủ 3 hướng.

| Lần | Dựng Planning | Cả luồng chọn → lập → chốt |
|---|---:|---:|
| 1 | 3.657 s | 4.246 s |
| 2 | 3.662 s | 4.562 s |
| 3 | 4.057 s | 4.466 s |
| 4 | 3.796 s | 4.248 s |
| 5 | 3.958 s | 4.426 s |

**Danh sách nơi cố định:** Tiệm cà phê phía tây mặt trời - Specialty Coffee Roastery; Cafe Đợi Một Người - Yersin; Xuân Hương Garden Coffee; Cà Phê Amelie; Coffee Em và Trịnh; Săn Mây Nhà Gỗ Cầu Đất; Thác Prenn; Hồ Xuân Hương; Đồi Thông Hai Mộ; Đèo Prenn.

[Bằng chứng từng lần, input và lịch cuối](evidence/pitch_20261017/demo_api.json). Kết quả này xác minh cơ chế quá tải, chưa phải lịch được người đánh giá chấm chất lượng ngoài đời; vẫn có cảnh báo giá/giờ/thời tiết thiếu.

## 7. Chạy lại và phạm vi còn thiếu

```sh
.venv/bin/python -m decision evaluate
.venv/bin/python -m planning evaluate
.venv/bin/python tests/planning/bench_pitch_validator.py --out logs/pitch_recheck_20261017/validator.json
.venv/bin/python submission/tools/pitch_demo_probe.py --runs 5 --out logs/pitch_recheck_20261017/demo_api_final.json
```

Toàn bộ log thô: `logs/pitch_recheck_20261017/`; bằng chứng nhỏ để mang theo deck: `submission/evidence/pitch_20261017/`. File `manifest.json` trong log lưu HEAD và SHA-256 code/config/test lúc bắt đầu. Lần test trong sandbox gặp lỗi kết nối Postgres; kết quả đó không được tính là lỗi sản phẩm. Lượt ngoài sandbox dùng database test từ cấu hình cục bộ, không ghi thông tin kết nối vào báo cáo.

Chưa có: năm lần demo **browser đầy đủ**, video dự phòng gắn nhãn đúng phiên mới, ba lần luyện thuyết trình có bấm giờ, thử nghiệm người dùng có đối chứng. Không lấy API rehearsal thay cho những việc này.
