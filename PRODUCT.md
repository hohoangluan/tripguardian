# Product

<!-- impeccable:product-schema 1 -->

## Platform

web

## Users
Người tự lên kế hoạch chuyến tự túc 2–4 ngày ở Đà Lạt: cá nhân, cặp đôi, nhóm nhỏ, tự di chuyển bằng xe máy hoặc ô tô. Họ không thiếu gợi ý (TikTok, Maps, blog) mà thiếu cách biến gợi ý rời rạc thành chuyến đi thật: còn mở không, giờ, giá, đường đi, có hợp người đi cùng, có vừa thời gian không. Web người dùng thiết kế cho desktop (1280–1440); điện thoại chỉ được dẫn sang ứng dụng.

## Product Purpose
Giúp người dùng chọn đúng địa điểm trước khi có lịch trình, rồi kiểm tra các nơi đã chọn có đi được cùng nhau không. Giá trị nằm ở quyết định, không ở bản itinerary. Thành công là người dùng tự tin chốt một lịch đi được, hiểu vì sao mỗi nơi có mặt và cái giá của nó.

## Positioning
Không phải "AI tạo lịch trình". Mỗi gợi ý có lý do và có cái giá; hệ thống không chọn thay, không tự bỏ nơi người dùng đã chọn; không bao giờ bịa địa điểm (không có bằng chứng thì ghi `unknown`).

## Operating Context
Luồng bốn bước: Tìm hiểu (kể chuyến, trả lời thẻ hỏi) → Lựa chọn (đĩa xoay chọn nơi) → Lịch trình (xếp, sửa, chốt) → Đánh giá sau chuyến. Khách dùng thử không cần đăng nhập, 1 chuyến/ngày, không lưu lịch sử. Dữ liệu: đánh giá Google Maps, clip TikTok; giờ mở cửa, giá, thời gian di chuyển là ước tính.

## Capabilities and Constraints
- Ràng buộc cứng (thể chất, giờ mở cửa) fail-closed, không có đường nào nới.
- User Profile là prior, không phải fact: bối cảnh chuyến hiện tại thắng; `unknown` ≠ không thích.
- Sở thích mềm không loại nơi nào; chỉ xếp hạng.
- Tiếng Việt; chữ trên giao diện nói như người, tên nút nêu hành động.
- Không hiện số câu hỏi hay tiến độ theo câu (docs/WEB.md).

## Brand Commitments
Tên TripGuardian, giọng "bạn". Bảng màu mận/hồng chỉ lấy từ token; chữ hiển thị Lora, chữ thân Inter. Không dùng emoji làm icon.

## Evidence on Hand
Snapshot địa điểm `web/public/data/snapshot.json`, ảnh bìa, đánh giá thật; docs/PROJECT_CONTEXT.md, docs/WEB.md, docs/UI_DESIGN.md. Chưa có số liệu người dùng thật để trích; không bịa.

## Product Principles
1. Lý do và cái giá đi cùng mọi gợi ý.
2. Người dùng giữ quyền chốt; hệ thống nói rõ khi không xếp được và vì sao.
3. Không biết thì nói "chưa rõ", không giả vờ chắc.
4. Một việc chính mỗi màn, ít lối đi, nhãn nói đúng điều sẽ xảy ra.

## Accessibility & Inclusion
Tương phản chữ thân ≥ 4,5:1, thao tác bàn phím được, tôn trọng `prefers-reduced-motion`.
