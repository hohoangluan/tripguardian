# Mock lịch trình desktop

Tham chiếu: `Recording 2026-10-13 132300.mp4`. Giao diện dùng nền trắng ngà, chữ tím đậm, nút tím nhạt, thẻ bo tròn và bố cục của video. Chỉ thiết kế desktop từ 1024 px.

Luồng:

1. Chọn một trong ba phương án, thấy rõ sáu nơi giữ và ba nơi tạm bỏ. Mỗi thẻ có một ảnh đại diện và hướng ưu tiên. Nội dung chính là ba nơi tạm bỏ kèm lý do; không liệt kê ảnh của sáu nơi giữ. Chưa chọn thì nút đi tiếp bị khóa. Ba hướng minh họa: giữ nơi hợp gu, bớt đi xa, tiết kiệm hơn.
2. Bấm “Xem lịch trình” vào tổng quan: bản đồ ngang, các mốc đến / chỗ nghỉ / lịch ba ngày / về. Không đặt ba phương án trong màn lịch chính; có nút quay lại đổi phương án.
3. Mở thẻ ngày: danh sách trải nghiệm bên trái, bản đồ bên phải; thanh ngày cố định, danh sách cuộn riêng. Thẻ có ảnh lớn, tên, sao và số đánh giá từ catalog, khu vực, thời lượng, giờ ghé, nút đổi và tạm bỏ. Nhấn giữ khung thẻ hoặc ảnh địa điểm để đổi thứ tự trong ngày; các nút vẫn thực hiện thao tác riêng. Thẻ nổi theo con trỏ, các thẻ còn lại trượt nhường chỗ trong lúc kéo, thẻ thả xuống trượt vào vị trí mới. Esc hủy kéo; chế độ giảm chuyển động bỏ animation. Cũng có thể kéo tay nắm hoặc dùng nút lên / xuống bằng chuột và bàn phím. Bấm ảnh bình thường mở chi tiết; thả sau khi kéo không mở chi tiết. Số thứ tự trên bản đồ cập nhật cùng danh sách. Nơi bắt buộc không có nút đổi / bỏ, nhưng có thể đổi thứ tự ghé. Sau chỉnh sửa, giờ và chặng di chuyển cũ được ẩn, thay bằng trạng thái chưa tính lại.
4. Bấm “Đổi” hoặc “Thêm trải nghiệm”: màn tìm địa điểm toàn trang theo video, ô tìm ở trên, bộ lọc bên trái, kết quả bên phải. Chọn và xác nhận đưa về ngày đang chỉnh.

Thử được: chọn phương án bằng chuột / bàn phím, bảng so sánh, tổng quan, chuyển ngày, chi tiết nơi, thay / thêm / bỏ nơi, lọc và tìm, sơ đồ cả chuyến, Google Maps, đổi phương án. Chỉnh tay làm chi phí chuyển sang “Chưa cập nhật”; dùng lại phương án gốc sau chỉnh tay cần xác nhận trong mock.

Tên, tọa độ và ảnh từ catalog / mock hiện có; ảnh nguồn Google Maps. Ảnh bản đồ lấy từ OpenStreetMap, ghi attribution trên bản đồ; đường nối là minh họa, không phải đường chỉ dẫn. Chuyến đến, về và chỗ nghỉ chưa có thông tin. Thời gian, giá, gu và tập giữ/bỏ là dữ liệu minh họa, chưa qua kiểm tra khả thi. Không tạo liên kết chia sẻ hoặc đặt chỗ thật.

Mock độc lập, không gọi backend và không sửa ứng dụng thật. Mở: `http://localhost:4311/itinerary/index.html`.

Nút “Căn lại giờ” mở bản xem trước cho ngày đang xem, giữ nguyên thứ tự và tập địa điểm. Mock tính giờ minh họa từ thời lượng cố định, đệm nghỉ 10 phút, chặng đi 20 / 35 phút và khoảng ăn; chỉ áp dụng khi xác nhận. Đổi thứ tự hoặc tập nơi làm giờ minh họa đã áp dụng mất hiệu lực. Chưa kiểm tra giờ mở cửa, khung giờ trải nghiệm và điều kiện đi lại; đây không phải lịch đã xác nhận khả thi.
