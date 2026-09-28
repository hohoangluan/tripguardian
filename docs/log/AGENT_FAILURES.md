# Nhật ký lỗi của agent

Mục đích: học các kiểu lỗi lặp lại của coding agent trước khi biến chúng thành rule cố định.

File này là bằng chứng và lịch sử học hỏi, không phải file hướng dẫn.

Một lỗi không tự động trở thành rule. Chỉ đưa vào `RULE.md` khi lỗi lặp lại, rủi ro cao, hoặc chạm vào một bất biến quan trọng.

---

## Phân loại lỗi

Chọn một nhóm chính:

* `CONTEXT` — đọc quá nhiều, bỏ sót ngữ cảnh liên quan, hoặc xem nhầm chỗ
* `SCOPE` — sửa code không liên quan hoặc mở rộng task
* `REASONING` — sửa triệu chứng thay vì nguyên nhân gốc
* `ARCHITECTURE` — vi phạm ranh giới module/interface/dependency
* `CONTRACT` — làm hỏng hoặc hiểu sai schema/API public
* `IMPLEMENTATION` — logic cài đặt sai
* `OVERENGINEERING` — abstraction, framework, cấu hình, độ phức tạp không cần thiết
* `TESTING` — kiểm chứng thiếu, sai, bị nới lỏng, hoặc gây hiểu lầm
* `PERFORMANCE` — tốn latency, token, I/O, bộ nhớ, compute không cần thiết
* `RELIABILITY` — lỗi retry, concurrency, state, lỗi một phần, idempotency
* `SECURITY` — xử lý không an toàn về tin cậy, secret, quyền, input
* `STOP` — vẫn tiếp tục sửa code sau khi task đã xong
* `OTHER` — không thuộc các nhóm trên

---

## F001 — Tên ngắn mô tả lỗi

**Ngày:** YYYY-MM-DD
**Task:** Agent được yêu cầu làm gì.
**Nhóm:** `CATEGORY`

### Kỳ vọng

Mô tả kết quả đúng nhỏ nhất.

### Thực tế

Mô tả chính xác agent đã làm gì.

Không suy đoán ở đây.

### Bằng chứng

* File đã sửa:
* Diff liên quan:
* Lệnh/test:
* Lỗi/kết quả:

### Vì sao đây là vấn đề

Nêu hậu quả cụ thể:

* hành vi sai,
* diff thừa,
* coupling kiến trúc,
* tốn thêm token/thời gian chạy,
* khó bảo trì,
* lỗi ẩn,
* v.v.

### Nguyên nhân gốc

Điều gì có vẻ đã gây ra lỗi?

Phân biệt giữa:

* thiếu ngữ cảnh,
* suy luận sai,
* task mơ hồ,
* thiếu rule,
* bỏ qua rule đã có,
* giả định sai về kiến trúc,
* kiểm chứng không đủ.

Nếu chưa chắc nguyên nhân, ghi `UNKNOWN`.

### Cách làm đúng hơn

Mô tả agent lẽ ra nên làm gì.

Giữ cụ thể và tối thiểu.

### Bài học

Viết bài học chung về kỹ thuật/agent trong một hoặc hai câu.

### Quyết định về rule

**Hành động:** `NONE | WATCH | ADD | MODIFY | REMOVE`

**Lý do:**

Không thêm rule cố định chỉ vì lỗi xảy ra một lần.

### Tái diễn

**Số lần:** 1
**Lỗi liên quan:** không có

### Trạng thái

`OPEN | UNDER_OBSERVATION | RESOLVED | PROMOTED_TO_RULE`

---

# Chính sách nâng thành rule

Một lỗi có thể được đưa vào `RULE.md` khi thỏa ít nhất một điều:

1. Cùng một kiểu lỗi xảy ra nhiều lần.
2. Chỉ một lần xảy ra cũng có thể gây rủi ro nghiêm trọng về tính đúng, bảo mật, hoặc mất dữ liệu.
3. Hành vi vi phạm một bất biến nền tảng của dự án.
4. Một rule ngắn gọn có thể ngăn cả nhóm lỗi mà không gây tác dụng phụ đáng kể.

Khi nâng thành rule:

* viết rule chung nhỏ nhất đủ để ngăn lỗi;
* không mã hóa sự cố cụ thể;
* ghi ID lỗi gốc ở đây;
* giữ mục này làm bằng chứng lịch sử.

---

# Câu hỏi khi review

Khi review một task của agent, hỏi:

**Ngữ cảnh:** Có chỉ đọc những gì cần thiết không?

**Phạm vi:** Có tạo thay đổi nhỏ nhất đủ dùng không?

**Suy luận:** Có sửa nguyên nhân gốc hay chỉ vá triệu chứng?

**Kiến trúc:** Có tôn trọng contract và ranh giới public không?

**Độ phức tạp:** Có thêm thứ gì mà yêu cầu hiện tại không cần không?

**Kiểm chứng:** Test có thực sự chạy qua hành vi đã thay đổi không?

**Hiệu quả:** Có lãng phí token, call, I/O, hoặc compute không?

**Dừng:** Có dừng khi hành vi yêu cầu đã hoàn thành không?
