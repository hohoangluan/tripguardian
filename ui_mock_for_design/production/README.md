# Mock UI cho User Web production

Bộ mock toàn luồng của **User Web desktop hiện tại**, trừ landing page. Prototype độc lập; không sửa code production, không gọi Harness / LLM, không đăng nhập hoặc ghi Google Calendar thật. Admin không thuộc bề mặt public production.

## Mở và đi thử

Mở `index.html`, hoặc chạy từ gốc repo:

```sh
python3 -m http.server 4313 --bind 0.0.0.0 --directory ui_mock_for_design/production
```

Preview trên máy chủ: **http://192.168.20.156:4313/** (cần LAN/VPN tới máy chủ). `localhost:4313` chỉ dùng khi trình duyệt chạy cùng máy với server.

Mở **`standalone.html`** trực tiếp nếu không truy cập được mạng máy chủ: toàn bộ code và ảnh được nhúng trong một file, không cần chạy server. File chứa ảnh nguồn nên chỉ giữ local, không commit public. Mở `#login` để đi từ đầu; `#atlas` để xem các quyết định thiết kế. Menu review trên cùng mở trực tiếp từng màn và trạng thái. **Đặt lại** trả về kịch bản mẫu; dữ liệu thử chỉ lưu ở key `tg.production.mock.v1` của trình duyệt.

1. Đăng nhập / khách → đồng ý dữ liệu → Khám phá trong app.
2. Kể chuyến → card nhịp đi → ngày → hậu cần; có luồng khớp danh sách / link và tóm tắt sửa được: ngày, số ngày/người, bạn đồng hành, phương tiện, giờ đến/về, ngân sách, giới hạn chặng và sở thích.
3. Lựa chọn → chi tiết 4 tab / nguồn bằng chứng → so sánh; thêm, lưu, khóa và hoàn tác độc lập.
4. Chỗ ở → chọn, tìm tên, xác nhận đổi / bỏ.
5. Chọn phương án → tổng quan → từng ngày; chuyển ngày và đổi thời lượng đều xem trước → xác nhận → hoàn tác.
6. Chốt trong prototype → phản hồi / bỏ qua → Chuyến của tôi.
7. Hôm nay → check-in tự nguyện → Hợp / Không hợp → Ở đây / dự phòng; Calendar xem trước → xác nhận.
8. Đã lưu, thông báo, hồ sơ, cài đặt thông báo, ngắt Calendar, xóa tài khoản hai bước.

**21 mục review** gồm 18 màn/nhóm màn sản phẩm và 3 mục bàn giao: bản đồ luồng, trạng thái/components, nền tảng thiết kế. Các mục review không phải route production mới.

## Học, bỏ và giữ

Bảng đầy đủ nằm ngay trong `#atlas`; mapping route và file production cũng ở đó.

- **Học workspace:** chat rộng + preview bên phải; composer dính trong panel, tóm tắt riêng; card cân đối và một hành động tiếp tục rõ.
- **Học itinerary:** thẻ phương án một ảnh, phần chừa có lý do; tổng quan trước khi vào ngày; trải nghiệm trái, bản đồ phải.
- **Giữ production:** gallery / 4 tab chi tiết, nguồn + ngày, bằng chứng, khóa và so sánh, constraint fail-closed, bảng đánh đổi, unavailable, độ vững / backup, preview và hoàn tác, Calendar có xác nhận, semantics hồ sơ và check-in.
- **Bỏ từ homepage mock:** bạn bè, activity feed, đã xem gần đây; chưa có chức năng tương ứng trong production.
- **Bỏ từ itinerary mock:** kéo đổi thứ tự, “Căn lại giờ”, luồng thay/thêm nơi qua trang tìm độc lập. Production hiện có chuyển ngày, chỉnh thời lượng, backup và quay về Lựa chọn để thêm nơi.
- **Không bắt mọi chuyến chừa nơi:** kịch bản bình thường giữ tập đã chọn; trạng thái quá tải mới hiển thị các hướng chừa. Giữ tất cả và phương án không khả dụng không thể bỏ qua validation.
- **Thống nhất thị giác:** nền giấy + Thông của production; bỏ việc đổi xanh sage sang tím giữa các phase. Sidebar ngoài hành trình có nhãn; thanh bước trong hành trình giữ 4 bước production.
- **Điện thoại:** giữ trang Dùng ứng dụng của production; không mở rộng thành mobile app trong bộ mock này.

Tham chiếu: `../designs/trip-workspace`, `../designs/itinerary`, `../designs/homepage`; hành vi đối chiếu từ `web/src/user/UserApp.tsx`, `screens/`, `ui/` và `docs/Role_Web_Functional_Design.md` §6. Bảng chi tiết ưu tiên code hiện tại khi đặc tả UI cũ khác runtime.

## Nội dung và dữ liệu

- Tên, tọa độ, ảnh địa điểm, điểm sao, số đánh giá và giờ có trong catalog hiện tại. Ảnh thật lấy đúng nơi từ mock nguồn / gallery; ghi Google Maps. Một ảnh rừng minh họa chỉ dùng cho card nhịp đi.
- Metadata signal `VERIFIED` lấy từ snapshot, gồm số lượt nhắc và nguồn; không suy cỡ mẫu từ tổng review, không chép review cá nhân hoặc tên tài khoản người thật. Nút Xem nguồn mở metadata trong mock; production phải mở trích đoạn / clip thật.
- Chỗ ở lấy từ `data/gmaps/list/dalat_stay.json`: tên, điểm sao, giá tham khảo và ngày nguồn. Không có ảnh xác minh thì dùng khối thiếu ảnh; không gán ảnh quán cà phê cho khách sạn.
- **Nhu cầu, tập chọn, số nơi hợp, thời lượng, giờ ghé, phương án, giá cả chuyến và các xung đột là kịch bản minh họa**, không phải kết quả của backend production. Phần thiếu vẫn là chưa biết; không gắn độ vững hoặc confidence từ điểm sao.
- Bản đồ dùng tile OpenStreetMap đã có ở mock nguồn, attribution luôn hiển thị. Ghim theo tọa độ thật; đường nối minh họa, không phải tuyến chỉ đường. Google Maps là liên kết ngoài do user bấm.
- Font dùng fallback có sẵn khi mở offline; không yêu cầu tải font hoặc ảnh qua mạng. Thông tin khai báo trong form lưu trong prototype, không gửi ra ngoài.

Ảnh nguồn và ảnh chụp review để local, được `.gitignore` loại khỏi commit public. Không publish hoặc upload bộ dữ liệu này.

## Kiểm chứng

Từ gốc repo, khi preview đang chạy:

```sh
node --check ui_mock_for_design/production/app.js
node ui_mock_for_design/production/verify.mjs
```

Script dùng `playwright-core` và Chromium hiện có của repository. Kiểm tra consent, toàn luồng, khóa, undo, đổi chỗ ở, duration / move preview, feedback, check-in, Calendar, xóa tài khoản và hard constraint. Chụp các màn ở 1440 px, kiểm tra bố cục 1024 / 1280 / 1920 px và trang điện thoại 390 px. Kết quả lần chạy ở `verification.json`; ảnh ở `shots/`.

Dialog đóng bằng Esc và trả focus. Tab dùng phím mũi tên; thang phản hồi dùng radio có trạng thái; icon có nhãn, reduced motion được tôn trọng. Prototype không bổ sung dependency production.

## File

- `index.html`: điểm mở prototype.
- `styles.css`: token, component, layout và breakpoint.
- `app.js`: màn, state, điều hướng và tương tác giả lập.
- `icons.js`: SVG dùng lại từ icon family production.
- `data.js`: metadata địa điểm / chỗ ở trích từ nguồn local.
- `verify.mjs`: kiểm chứng hành vi và tạo ảnh review.
