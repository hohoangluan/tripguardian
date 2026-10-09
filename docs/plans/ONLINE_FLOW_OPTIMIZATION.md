# Tối ưu luồng online — yêu cầu còn lại

Spec làm việc cho phần chưa triển khai. Nền tảng agent/harness và heuristic hiện trạng ở `docs/AGENT_HARNESS.md`. Không xem các yêu cầu dưới đây là tính năng đã có.

## Trip: clue một câu

Trích xuất toàn bộ clue trong một câu và giữ quote/provenance. Suy luận soft preference hoặc estimate có nhãn; không suy ra fact địa điểm hoặc tự nâng thành hard constraint. Laya vẫn tùy chọn; chưa huấn luyện trong phần nền tảng. Prior, dừng theo score / ngân sách lượt / idle, "xem gợi ý" và mẫu dài hạn đã có: `docs/TRIP_UNDERSTANDING.md` §7, §17.

## Decision và Planning nền

Shortlist không tự trở thành tập đã chọn. Anchor có provenance từ người dùng; resolve tên đơn thuần không có nghĩa là đã chọn. “Chọn giúp phần còn lại” là act ủy quyền rõ, giữ điểm khóa, không tự nới constraint.

Thay đổi lựa chọn hoặc dữ liệu ảnh hưởng lịch tạo snapshot có dạng Decision Output nhưng đánh dấu preview, không gọi confirm. Debounce có cấu hình; job mới thay job chờ cũ, kết quả job đang chạy hết hạn bị bỏ. Tập rỗng trả diagnostics nhẹ, không crawl lodging.

Key dùng hash nội dung Decision Output phục vụ lập lịch được canonicalize, bỏ timestamp/log không ảnh hưởng lịch. Cache key bổ sung version serving/config/solver và fingerprint live context còn TTL. Chỉ hash ID địa điểm không đủ: ngày, constraint, visit duration và mục tiêu cũng ảnh hưởng lịch. Job mang revision/fingerprint; cache không chia sẻ state/act riêng giữa người dùng.

Confirm dùng diagnostics phù hợp snapshot hiện tại; nếu preview lỗi hoặc chưa xong, dựng/kiểm đồng bộ đúng input trước chuyển stage. Preview không có quyền chốt hoặc thay lựa chọn. Dùng heuristic cho kiểm dữ liệu, cache, debounce và act đơn giản; LLM cho hiểu nhiều clue, câu mơ hồ và đánh đổi trong quyền đã cấp.

## Calendar và repair ngày đi

Planning mở phương án đề xuất và các phương án khác, chỉ act; “+ Thêm nơi” quay về Decision cùng phiên; xác nhận tạo Plan Output đã kiểm. Hành vi Web này đã có; preview nền ở Decision thuộc phần trên.

Sau đó người dùng đăng nhập/cấp quyền Calendar để đồng bộ lịch đã duyệt. Module Calendar có agent/adapter riêng, không tự tạo giờ hay địa điểm ngoài Plan Output. Cần chốt nguồn Calendar và cách đăng nhập trước triển khai adapter.

Repair hiểu sự cố, khóa phần đã thực hiện, chỉ dựng lại phần còn lại với live context có nguồn; hiển thị diff, người dùng đồng ý rồi mới cập nhật Calendar. Báo sự cố không trực tiếp sửa fact địa điểm. Cần contract idempotency, quyền và xử lý xung đột với thay đổi Calendar từ bên ngoài.

LangGraph có thể dùng khi cần checkpoint/resume và chờ người dùng lâu; contract module giữ độc lập framework. Không thêm dependency chỉ để giảm số call LLM.
