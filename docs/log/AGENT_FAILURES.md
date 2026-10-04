# Nhật ký lỗi của agent

Bằng chứng về các kiểu lỗi lặp lại của coding agent, để quyết định cái nào đáng thành rule. Không phải file hướng dẫn: một lỗi không tự động thành rule.

**Nhóm lỗi:** `CONTEXT` (đọc sai / thiếu ngữ cảnh) · `SCOPE` (sửa thứ không liên quan) · `REASONING` (vá triệu chứng) · `ARCHITECTURE` (phá ranh giới module) · `CONTRACT` (hỏng schema / API public) · `IMPLEMENTATION` · `OVERENGINEERING` · `TESTING` · `PERFORMANCE` · `RELIABILITY` · `SECURITY` · `STOP` (sửa tiếp sau khi đã xong) · `OTHER`.

**Nâng thành rule** khi thỏa ít nhất một điều: cùng kiểu lỗi xảy ra nhiều lần · một lần cũng đủ gây rủi ro nặng về tính đúng, bảo mật, mất dữ liệu · vi phạm một bất biến nền tảng · một rule ngắn ngăn được cả nhóm lỗi mà không gây tác dụng phụ. Khi nâng: viết rule chung nhỏ nhất, không mã hóa sự cố cụ thể, ghi ID lỗi gốc ở đây, giữ mục này làm bằng chứng.

**Mẫu một mục:**

```markdown
## F00N — <tên ngắn>

**Ngày:** YYYY-MM-DD · **Nhóm:** `CATEGORY` · **Task:** agent được yêu cầu làm gì
**Kỳ vọng:** kết quả đúng nhỏ nhất.
**Thực tế:** agent đã làm gì (không suy đoán).
**Bằng chứng:** file, diff, lệnh / test, lỗi.
**Hậu quả:** hành vi sai · diff thừa · coupling · tốn token · lỗi ẩn · …
**Nguyên nhân gốc:** thiếu ngữ cảnh | suy luận sai | task mơ hồ | thiếu rule | bỏ qua rule có sẵn |
giả định sai về kiến trúc | kiểm chứng không đủ | `UNKNOWN`
**Lẽ ra nên:** cụ thể, tối thiểu.
**Rule:** `NONE | WATCH | ADD | MODIFY | REMOVE` + lý do
**Tái diễn:** số lần · lỗi liên quan · **Trạng thái:** `OPEN | UNDER_OBSERVATION | RESOLVED | PROMOTED_TO_RULE`
```

---

## Các mục

_Chưa có mục nào._
