# Khảo sát UI/UX TripGuardian

[Script tạo Google Form](create_tripguardian_ui_survey.gs) bám format mẫu, rút gọn cho mục đích đánh giá UI/UX: xác nhận tham gia, 2 câu bối cảnh, 3 ma trận gồm **10 phát biểu**, 1 câu góp ý mở. Thời gian trả lời dự kiến 2–3 phút, chưa tính dùng thử.

| Ma trận | Nội dung | Số dòng |
|---|---|---|
| B1 | Bố cục, chữ, màu sắc | 3 |
| B2 | Bắt đầu tạo chuyến, nhãn nút, chuyển bước | 3 |
| B3 | Tìm hiểu, Lựa chọn, Lịch trình, hài lòng chung | 4 |

Cả ba ma trận dùng cùng 5 mức: **1 — Hoàn toàn không đồng ý; 2 — Không đồng ý; 3 — Trung lập; 4 — Đồng ý; 5 — Hoàn toàn đồng ý**. Được bỏ trống từng dòng chưa trải nghiệm; không quy đổi ô trống thành mức 3 khi tổng hợp.

1. Mở [Google Apps Script](https://script.google.com/), tạo dự án mới.
2. Dán toàn bộ nội dung file `.gs` vào `Code.gs`.
3. Chọn hàm `createTripGuardianSurvey`, bấm **Run / Chạy**, cấp quyền tạo Google Form.
4. Mở **Execution log / Nhật ký thực thi**: `FORM EDIT URL` để xem và chỉnh, `FORM RESPOND URL` để trả lời khảo sát. Kiểm tra quyền truy cập của người trả lời trong Google Forms trước khi chia sẻ.

Mỗi lần chạy tạo một form mới. Muốn chỉnh form đã tạo, dùng link chỉnh sửa đã ghi trong log. Script không thu email, không giới hạn mỗi tài khoản một phản hồi và không công khai bảng tổng hợp phản hồi.

Người từ chối tham gia kết thúc ngay. Người chưa vào website, không xem được giao diện hoặc chỉ thấy trang giới thiệu ứng dụng trên điện thoại chuyển thẳng đến góp ý, bỏ qua ma trận.

Nội dung đối chiếu với code của `web/src/user/screens/{Discover,Understand,Explore,Plan}.tsx` và thanh bước trong `web/src/user/trip.tsx`; chức năng từng màn ở [tài liệu Web](../../docs/Role_Web_Functional_Design.md). Không yêu cầu người dùng xác nhận độ chính xác của gợi ý hoặc tính khả thi của lịch trình.

API tham khảo: [FormApp](https://developers.google.com/apps-script/reference/forms/form-app), [GridItem](https://developers.google.com/apps-script/reference/forms/grid-item), [MultipleChoiceItem](https://developers.google.com/apps-script/reference/forms/multiple-choice-item).
