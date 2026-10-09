# Thiết kế deck pitching TripGuardian

## 1. Mục tiêu

Tạo deck pitching 15 phút cho ban giám khảo cuộc thi, giảng viên và mentor. Deck cân bằng giá trị sản phẩm với chiều sâu Data & AI, bám đúng code, dữ liệu và giao diện hiện tại của TripGuardian.

Thông điệp chính:

> TripGuardian giúp người dùng chọn đúng địa điểm trước khi xếp lịch, bằng dữ liệu có bằng chứng và kiểm tra constraint có thể giải thích.

Đầu ra:

- deck HTML 1920 × 1080 dùng `deck-stage`;
- PowerPoint `.pptx` chỉnh sửa được;
- các sơ đồ, số liệu và chữ là đối tượng chỉnh sửa được, không raster hóa toàn slide;
- không có speaker notes.

## 2. Đối tượng và nhịp trình bày

- Đối tượng: ban giám khảo cuộc thi, giảng viên, mentor.
- Thời lượng: 15 phút, dành khoảng 2–3 phút cho demo và phản biện.
- Giọng kể: rõ ràng, có bằng chứng, không phóng đại; bắt đầu từ vấn đề người dùng rồi chứng minh bằng hệ thống kỹ thuật.
- Cấu trúc: vấn đề → khoảng trống hiện tại → giải pháp → cơ chế quyết định → Data & AI → kiến trúc → bằng chứng chạy thật → UX → bước tiếp theo.

## 3. Chuỗi slide

| # | Tiêu đề | Vai trò | Nội dung chính | Thời lượng |
|---|---|---|---|---:|
| 1 | TripGuardian — Chọn đúng nơi trước khi xếp lịch | Mở đầu | Tên sản phẩm, một câu định vị, nhận diện hiện tại | 0:30 |
| 2 | Nhiều gợi ý hơn không làm chuyến đi dễ quyết định hơn | Vấn đề | Quá tải lựa chọn, dữ liệu rời rạc, khó kiểm tra tổ hợp | 1:00 |
| 3 | Người Việt đang tự nối mạng xã hội, Maps và review bằng tay | Bối cảnh Việt Nam | Hành vi tìm hiểu đa nguồn; Đà Lạt là phạm vi kiểm chứng | 1:00 |
| 4 | Các công cụ hiện tại dừng ở tìm kiếm hoặc sinh lịch | Khoảng trống | Thiếu lớp quyết định có constraint, bằng chứng và đánh đổi | 1:00 |
| 5 | TripGuardian biến ý định thành quyết định có kiểm chứng | Giá trị cốt lõi | Ba câu hỏi: nơi nào hợp, vì sao, có đi cùng nhau được không | 1:00 |
| 6 | Một hành trình: hiểu → chọn → kiểm tra → xếp lịch | Trải nghiệm | Luồng người dùng từ câu kể tự do tới lịch trình | 1:15 |
| 7 | Luồng quyết định từ mục tiêu đến các phương án đánh đổi | Sơ đồ trung tâm | Input → Place Intelligence → Trip Understanding → Place Decision → giải thích/bất định → Planning; người dùng chốt | 1:30 |
| 8 | Place Intelligence biến dữ liệu rời rạc thành bằng chứng | Data & AI | Google Maps/TikTok tách nguồn; Fact, Signal, Estimate; evidence span và review gate | 1:15 |
| 9 | AI đề xuất; constraint và validator giữ kế hoạch khả thi | Tin cậy | `pass / fail / unknown`, fail-closed, physical constraint không nới, model theo vai trò | 1:15 |
| 10 | Kiến trúc tách tri thức địa điểm khỏi từng chuyến đi | Kỹ thuật | Bốn giai đoạn; offline ghi, online đọc; public API; live context theo request | 1:15 |
| 11 | Sản phẩm đã chạy trên dữ liệu Đà Lạt thực | Bằng chứng | Chỉ số dữ liệu, đánh giá 30 chuyến, tốc độ và giới hạn hiện tại | 1:15 |
| 12 | Người dùng luôn là người quyết định cuối | UX/demo | Ảnh thật: hiểu chuyến đi, so sánh, cảnh báo, lịch trình | 1:15 |
| 13 | Bước tiếp theo là tăng coverage trước khi mở rộng địa bàn | Khả thi | Tăng nhãn cho giá trị phủ định, thử nghiệm người dùng, mở rộng có kiểm soát | 0:45 |
| 14 | Từ hàng nghìn nơi đến một chuyến đi có thể tin | Kết | Nhắc lại định vị và lời mời phản biện/demo | 0:30 |

Tổng thời lượng nội dung mục tiêu: khoảng 14 phút; phần còn lại dành cho chuyển slide hoặc demo ngắn.

## 4. Ánh xạ thang điểm

| Tiêu chí | Điểm | Slide chứng minh |
|---|---:|---|
| Mức độ giải quyết vấn đề và tác động | 20 | 2, 3, 5, 6 |
| Mức độ phù hợp với Việt Nam | 15 | 3, 8, 11 |
| Tính sáng tạo và khác biệt | 20 | 4, 5, 7, 9 |
| Đổi mới trong sử dụng Dữ liệu & AI | 20 | 7, 8, 9, 10 |
| Tính khả thi và sản phẩm thử nghiệm | 15 | 11, 12, 13 |
| Trình bày và Trải nghiệm người dùng | 10 | toàn deck, trọng tâm 6, 7, 12 |

Rubric là xương sống nội dung nhưng không xuất hiện như mục lục chấm điểm trong deck.

## 5. Hệ thị giác

Deck kế thừa hệ hiện tại của User Web:

- nền giấy `#FAF7F2`;
- xanh Thông làm màu chính;
- Hồng sương dùng cho cảm xúc du lịch và cover;
- Nắng/amber dùng cho cảnh báo, bất định và đánh đổi;
- Lora cho tiêu đề, Be Vietnam Pro cho nội dung, JetBrains Mono cho số liệu;
- tối đa hai nền chính: giấy sáng và xanh Thông đậm;
- không dùng emoji, icon tự vẽ hoặc gradient tím-xanh kiểu AI;
- dùng ảnh thật của sản phẩm và địa điểm khi có; ảnh sinh chỉ dùng nếu thật sự cần và được duyệt riêng.

Nhịp bố cục:

1. Slide 1–3: giàu cảm xúc travel, ít chữ, ảnh/sa bàn hiện tại chiếm ưu thế.
2. Slide 4–6: editorial, so sánh trực quan và hành trình người dùng.
3. Slide 7–10: sơ đồ kỹ thuật rõ, nhiều khoảng thở, khối và connector chỉnh sửa được.
4. Slide 11–13: số liệu lớn, screenshot thật và giới hạn minh bạch.
5. Slide 14: kết thúc tối giản trên nền xanh Thông.

Slide 7 bám cấu trúc ảnh tham chiếu: các khối có nhãn, màu theo vai trò, connector có hướng, đầu ra là nhiều phương án đánh đổi. Không sao chép nguyên văn hoặc màu sắc của ảnh mẫu.

## 6. Số liệu được phép dùng

Số liệu phải lấy từ file hiện có tại thời điểm dựng và ghi nguồn nhỏ trên slide.

Tại thời điểm viết spec:

- `data/serving/places.json`, build ngày 2026-10-08: 1.696 địa điểm, 128 khu vực, 28.466 trạng thái feature `VERIFIED`, 4.081 `UNCERTAIN`, 2.779 `OUTDATED`;
- `data/decision/eval.json`: 30 chuyến ẩn, shortlist mục tiêu 8 nơi, `filled_rate = 0.967`, 0 vi phạm hard constraint, 0 `unknown`/`uncertain` trong danh sách chính, 0% near-duplicate, thời gian tối đa 273 ms;
- `docs/log/DEV_LOG.md`: 249.605 bằng chứng từng được index cho màn gán nhãn; số này chỉ dùng nếu ghi rõ phạm vi và thời điểm, không trình bày như số hiện tại nếu chưa kiểm lại;
- ảnh giao diện từ `web/shots/app/` và tài sản thương hiệu trong `web/public/img/`.

Không dùng số thị trường, traction, người dùng hoặc doanh thu nếu không có nguồn kiểm chứng.

## 7. Tính chỉnh sửa và animation

- Mỗi slide là một `<section>` HTML tĩnh trực tiếp dưới `deck-stage`.
- Text nằm trong leaf element; cấu trúc lặp được viết tường minh để sửa từng mục.
- Sơ đồ dùng HTML/CSS shape và connector; không dùng ảnh chụp của sơ đồ.
- Chỉ dùng animation khi thứ tự tiết lộ có ý nghĩa:
  - slide 7: xuất hiện tuần tự theo luồng quyết định;
  - slide 11: số liệu xuất hiện theo nhóm.
- Animation dùng `data-anim` để giữ được khi xuất PowerPoint.

## 8. Kiểm chứng trước bàn giao

- deck chạy qua HTTP bằng `python3 -m http.server 4311 --directory designs`;
- kiểm tra console không có lỗi;
- kiểm tra từng slide ở 16:9 và thumbnail;
- xác nhận không có font dưới 24 px, tiêu đề tối thiểu 48 px;
- xác nhận title sequence kể được câu chuyện khi đọc riêng;
- đối chiếu lại mọi số liệu với file nguồn;
- xuất `.pptx` chỉnh sửa được và mở kiểm tra số slide, text, shape, connector và animation;
- rà soát PowerPoint không có tràn chữ, mất font hoặc ảnh ngoài project.

## 9. Phạm vi không làm

- Không tạo số liệu thị trường, traction hay kết quả thử nghiệm chưa có.
- Không trình bày tính năng trong plan như tính năng đã chạy.
- Không thêm slide đội ngũ khi chưa có thông tin người thật.
- Không raster hóa toàn bộ slide để đạt độ giống hình ảnh.
- Không sửa code sản phẩm ngoài thư mục deck.
