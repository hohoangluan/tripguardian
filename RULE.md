# RULE.md

## 0. Ngôn ngữ
- Tài liệu (docs, spec, plan, README, dev log) viết tiếng Việt, kể cả khi người dùng viết tiếng Anh.
- Code, comment, identifier, tên file, tên schema, commit message viết tiếng Anh.
- Trong tài liệu, giữ nguyên thuật ngữ kỹ thuật và identifier (`POI`, `VERIFIED`, `Fact`, …) như trong code.
- Viết tối giản: ngắn, chính xác, đúng chức năng; không lặp nội dung đã có ở tài liệu khác, chỉ trỏ tới.

## 0.1 Tài liệu chính thức
- Tài liệu chính thức là các file trong `docs/` và thư mục con của nó (ví dụ `docs/specs/`, `docs/log/`) được liệt kê trong `AGENTS.md`. File không có trong danh sách đó (ví dụ spec/plan làm việc) không phải tài liệu chính thức.
- Mỗi tài liệu giữ một vai trò riêng để không phải đọc tài liệu dài; mỗi nội dung chỉ nằm một nơi. Nơi khác cần thì dẫn sang (`docs/X.md` §N), không chép lại.
- Spec dùng để xây thật (ví dụ `docs/specs/CORPUS_SPEC.md`) là tài liệu chính thức, tách khỏi tài liệu mô tả hiện trạng (ví dụ `docs/CORPUS.md`).
- Spec/plan làm việc là tạm thời: khi đã được duyệt và thực hiện, gộp nội dung còn giá trị vào tài liệu chính thức rồi xóa spec/plan. Không giữ thư mục spec/plan lưu trữ.
- Không tạo bản dịch song song; thay đổi được sửa thẳng vào tài liệu chính thức.
- Tài liệu chính thức mô tả **đúng code hiện tại**, không nhắc lại hành vi/cấu trúc trước đây, không viết "trước đây làm X, giờ đổi thành Y". Khi code đổi, sửa thẳng đoạn mô tả cũ, không thêm ghi chú lịch sử.
- Ngoại lệ: `docs/log/DEV_LOG.md` (giữ **Hiện tại** + **Trước đó** theo đúng khuôn mẫu của chính nó) và `docs/log/AGENT_FAILURES.md` (nhật ký bằng chứng lỗi) là log theo thiết kế, không phải tài liệu mô tả hiện trạng — không áp dụng quy tắc "chỉ giữ hiện tại" ở trên cho hai file này.

## 1. Nguồn sự thật
- Code + test mô tả hành vi runtime.
- Schema/interface public định nghĩa contract giữa các module.
- Tài liệu phải khớp với code đã ship.

## 2. Ranh giới
- Module chỉ giao tiếp qua interface public có kiểu.
- Không import phần nội bộ của module khác.
- I/O, LLM, network chỉ nằm ở biên module.
- Mỗi nguồn dữ liệu ngoài (TikTok, Google, …) có module/thư mục con riêng cả trong code lẫn trong thư mục dữ liệu; không gộp nhiều nguồn vào một file hay một thư mục.

## 3. Contract
- Input/output public có kiểu.
- Validate dữ liệu không tin cậy (bên ngoài/LLM/người dùng) tại biên.
- Không bịa giá trị còn thiếu.

## 4. Thay đổi tối thiểu
- Thay đổi nhỏ nhất đủ để giải quyết trọn vẹn yêu cầu.
- Không refactor, đổi tên, di chuyển, hay format lại code không liên quan.

## 5. Không kiến trúc phỏng đoán
- Chỉ xây những gì yêu cầu hiện tại cần.
- Ưu tiên code trực tiếp hơn abstraction, factory, hook, framework chưa dùng đến.

## 6. Test
- Test hành vi đã thay đổi.
- Không nới lỏng hay xóa test hiện có chỉ để code pass.
- Sửa nguyên nhân, không sửa test.

## 7. Ngữ cảnh
- Tìm trước, đọc tối thiểu cần thiết.
- Bắt đầu từ public API → schema → test → implementation.
- Không quét repo mù quáng.

## 8. Hoàn thành
- Chạy bước kiểm chứng rẻ nhất mà đủ.
- Review diff để loại thay đổi không liên quan.
- Dừng khi hành vi yêu cầu chạy đúng và test liên quan pass.
