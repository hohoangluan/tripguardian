# Mock homepage TripGuardian

Bản mock desktop tham chiếu `../../homepage.jpg`: nền kính tím nhạt, bố cục ba cột, ảnh lớn cạnh danh sách gợi ý, năm thẻ khám phá và thanh chuyến đi dưới cùng. Khung và ảnh bo góc như bản đầu: khung ngoài 26 px, panel chính 19 px, ảnh lớn 12 px, thẻ ảnh 11 px; avatar và dấu bước vẫn tròn. Giữ cột bạn bè và hoạt động cá nhân với dữ liệu minh họa.

Chức năng bấm thử: tìm chủ đề, lưu / bỏ lưu, mở ý tưởng, nhập chuyến mới, tiếp tục chuyến đang lập, xem bạn bè, Chuyến của tôi, Hôm nay và Hồ sơ. Dữ liệu chỉ nằm trong bộ nhớ của bản mock; tải lại trang sẽ về trạng thái ban đầu. Không gọi backend.

Từ thư mục gốc repo:

```sh
python3 -m http.server 4311 --directory ui_mock_for_design/designs
```

Mở `http://localhost:4311/homepage/`. File giao diện: `index.html`; ảnh chụp desktop: `desktop.png`. CSS, JavaScript và icon nằm trong HTML; ảnh thật nằm trong `assets/`.

Ảnh được sao chép nguyên bản, không dùng ảnh sinh. `cloud.jpg`, `pine.jpg`, `lake.jpg` lấy từ ảnh Google Maps của Đồi Đa Phú, Rừng thông và Hồ Xuân Hương trong `data/gmaps/places/`. `cafe.jpg` và `indoor.jpg` lấy từ `tiemcu.jpg` và `hk.jpg` trong `docs/design/desktop/v4-chat-cards/img/`, tương ứng Tiệm Cà Phê Cũ 1991 và HongKong Cổ Trấn. Ảnh minh họa chủ đề; không tự chứng minh giờ mở cửa, thời tiết hoặc khả năng đáp ứng ràng buộc.
