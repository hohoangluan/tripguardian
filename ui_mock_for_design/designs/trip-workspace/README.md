# Mock workspace chuyến đi

Mở `index.html` hoặc `fullscreen.html`: hai trang dùng chung bố cục và tương tác.

Bố cục tham chiếu từ ảnh người dùng: chat rộng, thanh bước gọn, danh sách nơi xem trước bên phải. Palette kem sáng và xanh sage; dùng hướng dẫn `ui-ux-pro-max`, không dùng `baoyu-design`.

Nút **Tóm tắt chuyến đi** cạnh avatar mở thông tin trong dialog, nhấp nháy nhẹ khi đóng; tắt chuyển động theo `prefers-reduced-motion`. Tóm tắt không nằm trong cột địa điểm. Thẻ có **Xem chi tiết** để mở ảnh, thông tin và bản đồ. Chỉ phase Chọn nơi có checkbox chọn địa điểm; luồng tiếp tục giữ bước kiểm tra nhu cầu trước khi chọn.

Mock không gọi API TripGuardian. Nội dung nhu cầu, lý do phù hợp và lịch trình là minh họa. Tên địa điểm và ảnh lấy từ catalog hiện có; thiếu bằng chứng được ghi chưa rõ. Google Maps chỉ tải khi mở chi tiết.

Preview: `http://localhost:4311/trip-workspace/index.html`. Ảnh kiểm chứng: `refined-desktop.png`, `refined-mobile.png`.
