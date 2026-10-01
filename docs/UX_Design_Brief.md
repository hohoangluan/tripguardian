# TripGuardian — Brief thiết kế UI/UX

Dành cho UI/UX designer. Brief nói **thiết kế cho ai, theo nguyên tắc nào, hiển thị dữ liệu ra sao, và không được làm gì**. Danh sách màn hình và chức năng từng màn: `docs/Role_Web_Functional_Design.md`. Layout và phong cách hình ảnh do designer quyết định.

---

## 1. Sản phẩm trong một phút

Người đi du lịch không thiếu gợi ý; họ thiếu sự hỗ trợ để **quyết định**: nơi nào hợp với chuyến đi này, vì sao chọn nơi này thay vì nơi kia, và các nơi đã chọn có đi chung được không. TripGuardian là **trợ lý ra quyết định, không phải máy tạo lịch trình**; người dùng luôn chốt cuối. Chi tiết: `docs/Project_Context.md` §1–5.

```text
Hiểu chuyến đi → Xác minh địa điểm → So sánh → Người dùng chọn → Kiểm tra khả thi → Xếp lịch
```

MVP: **Đà Lạt**, chuyến 2–4 ngày, cặp đôi / nhóm bạn / gia đình nhỏ, đi xe máy, ô tô, hoặc xe công nghệ.

## 2. Thiết kế cho ai, trong bối cảnh nào

| | Cần nhất từ giao diện |
|---|---|
| **Lần đầu đến** | Được dẫn dắt: bắt đầu từ đâu, mỗi ngày bao nhiêu điểm là thực tế, nên bỏ nơi nào trong các nơi giống nhau |
| **Đã từng đến** | Nhanh: bỏ qua phần cơ bản, tìm cái mới, kiểm tra danh sách đã có |

Bốn điểm bắt đầu: chưa có ý tưởng · đã lưu địa điểm · có nơi bắt buộc đến · đã có lịch trình (`docs/Project_Context.md` §3).

- **User Web ưu tiên điện thoại:** người dùng lên kế hoạch trên điện thoại, thường ngay sau khi xem TikTok.
- **Admin Web là desktop:** dày thông tin, thao tác nhanh, có phím tắt.
- Nội dung giao diện bằng **tiếng Việt**, từ ngữ đời thường, không dùng thuật ngữ hệ thống.

## 3. Nguyên tắc thiết kế (bắt buộc)

1. **Giúp quyết định, đừng bắt người dùng lướt.** Một tập nhỏ hữu ích (shortlist, không phải 50 kết quả). Gom các nơi giống nhau và nói nên giữ nơi nào.
2. **Sự không chắc chắn phải hiện ra.** Nếu giờ mở cửa chưa xác nhận, nói rõ ngay tại chỗ ra quyết định. Không hiển thị giá trị đoán như giá trị chắc chắn.
3. **Mọi nhận định cách bằng chứng một chạm.** "Buổi sáng yên tĩnh" mở ra các comment và clip video đứng sau nó.
4. **Giải thích cả hai phía.** Mọi gợi ý có "vì sao phù hợp" *và* điểm đánh đổi. Mọi xung đột nêu tên địa điểm, quy tắc bị vi phạm, và cách khắc phục.
5. **Người dùng giữ quyền kiểm soát.** Không bao giờ lặng lẽ bỏ một nơi người dùng đã chọn. Giới hạn do người dùng đặt chỉ được nới khi họ xác nhận.
6. **Điều bất khả thi về vật lý là cứng.** Không nút nào biến kế hoạch không đi kịp thành "khả thi"; chỉ đưa ra cách dời có thật.
7. **Chỉ hỏi điều làm thay đổi kết quả.** Mỗi câu hỏi bỏ qua được và có "Chưa chắc". Không hỏi lại điều đã biết. Cách hỏi theo người dùng và giọng điệu: `docs/Project_Context.md` §12.4–12.5.
8. **Suy đoán từ hồ sơ phải có nhãn.** Mọi thứ điền sẵn từ lịch sử người dùng được đánh dấu "từ hồ sơ của bạn" và sửa được bằng một chạm.

## 4. Cách hiển thị chất lượng dữ liệu (áp dụng mọi màn)

| Trạng thái dữ liệu | Người dùng thấy |
|---|---|
| Đã xác minh | Giá trị, bình thường |
| Chưa chắc chắn (xung đột hoặc bằng chứng yếu) | Giá trị kèm dấu "chưa xác nhận"; chạm để xem lý do |
| Quá hạn | Giá trị kèm "có thể đã thay đổi — kiểm tra lần cuối <ngày>" |
| Cần duyệt / đã vô hiệu | Không hiển thị |
| Chưa biết | "Chưa có thông tin" — không bao giờ là giá trị mặc định, không bao giờ là "không" |

| Loại giá trị | Cách trình bày |
|---|---|
| Fact (giờ, giá) | Giá trị chính xác + nguồn + ngày |
| Signal (độ đông, yên tĩnh) | Xu hướng kèm bối cảnh và cỡ mẫu ("sáng cuối tuần: đông · 123 comment, 30 creator") |
| Estimate (thời gian tham quan) | Luôn là khoảng ("60–90 phút") |
| Độ tin cậy | Cao / Trung bình / Thấp; chạm để xem lý do một dòng ("3 nguồn độc lập, kiểm tra tháng này") |

- Thông tin thực tế (chính thức / Google) và bằng chứng trải nghiệm (TikTok) phải tách rõ về mặt hình ảnh; chúng là hai loại sự thật khác nhau.
- Tránh dùng phần trăm trần và số sao làm tín hiệu chính; độ phổ biến chỉ là một yếu tố.
- Nguồn gốc các trạng thái và loại giá trị: `docs/CORPUS.md` §4, §6.

## 5. Các màn cần thiết kế và điểm nhấn

Chức năng đầy đủ từng màn: `docs/Role_Web_Functional_Design.md` §2 (User Web), §3 (Admin Web). Ưu tiên MVP: §4 của tài liệu đó.

| Màn | Điểm nhấn thiết kế |
|---|---|
| Thiết lập chuyến đi (§2.2) | Giới hạn cứng và sở thích mềm phải trông khác nhau: một bên là quy tắc, một bên là thiên hướng |
| Khám phá sở thích (§2.3) | Cảm giác hội thoại ngắn, không phải biểu mẫu; một câu mỗi lượt |
| Nhập địa điểm (§2.4) | Ba trạng thái khớp / cần chọn / không tìm thấy phải phân biệt tức thì |
| Shortlist (§2.5) | Thẻ gọn trên điện thoại nhưng vẫn đủ "vì sao phù hợp" + "đánh đổi" |
| Chi tiết địa điểm (§2.6) | Bằng chứng một chạm; clip phát tại đúng đoạn |
| Tuyển chọn (§2.8) | Nơi sản phẩm có cảm giác "sống": dòng chênh lệch đọc trong nháy mắt, không chặn thao tác |
| Kết quả khả thi (§2.9) | Từ xung đột đến cách sửa trong một bước |
| Lịch trình (§2.10) | Dòng thời gian + bản đồ; cảnh báo nằm tại đúng điểm dừng |
| Hàng đợi review (§3.1) | Tốc độ: xử lý 50 mục trong 10 phút; mục mẫu ẩn phải trông y hệt mục thường |

## 6. Ràng buộc cứng

- Clip TikTok phát từ bản đã thu (`data/tiktok/videos/<id>/video.mp4`, ảnh bìa từ `frames/`), luôn ghi @creator và link về clip gốc; không có bản thu thì dùng embed TikTok. Không hiển thị transcript.
- Dữ liệu lấy từ Google hiển thị kèm **bản đồ Google**, không dùng nhà cung cấp bản đồ khác.
- Không màn nào trình bày estimate hay giá trị chưa chắc chắn như fact đã xác nhận.
- Người dùng và admin không sửa tay dữ liệu địa điểm; chỉ báo lỗi hoặc duyệt.
- Chỗ ở không được gợi ý. Người dùng đã có chỗ ở thì nhập; nó là anchor và chỉ quyết định điểm bắt đầu / kết thúc của lộ trình.

## 7. Hệ thị giác đang dùng

| | User Web + landing | Admin Web |
|---|---|---|
| Hướng | Poster du lịch Đà Lạt, ưu tiên điện thoại | "Phòng điều khiển", chỉ desktop, sáng/tối theo hệ thống |
| Chữ | Phudu (tiêu đề, nút; chữ hoa, chỉ câu ngắn), Geologica (nội dung, tên địa điểm), Space Mono (giờ, số, khoảng ước tính) | Mona Sans (độ rộng tạo phân cấp), JetBrains Mono (dữ liệu, phím tắt) |
| Nền | Landing: thế giới 3D làm nền; hero và 5 bước căn giữa (bước dính giữa màn hình: tiêu đề trên, thẻ sản phẩm giữa, hai chú thích hai bên), rồi phần giấy kem (video demo, FAQ, CTA). App: giấy kem, bề mặt đặc, dải ảnh poster sau tiêu đề mỗi màn | Bề mặt trung tính; thẻ "Việc cần làm" nền thông đậm là điểm nhìn đầu tiên |
| Màu | Giấy `#F4F0E6`, thông `#1D3B33`, hồ `#2F5D6B`, dã quỳ `#F2B31B` (chữ vàng chỉ trên nền tối) | Cùng thông và dã quỳ; màu trạng thái theo `admin/model.ts` |

- Quy tắc cứng là khối nền thông đậm có khóa vàng; sở thích mềm là chip viền đứt.
- Ảnh poster sinh qua `web/scripts/gen_images.py`; chúng là minh họa, không phải ảnh địa điểm thật. Ảnh bìa thẻ địa điểm lấy từ frame clip thật của chính nơi đó, có ghi creator.
- Video demo landing quay từ app thật bằng `web/scripts/record_demo.mjs`.
- Vào `/app` lần đầu là màn đăng nhập: Google (nổi nhất), Zalo, Facebook, Apple, TikTok, hoặc email + mật khẩu (email để còn lấy lại mật khẩu, không dùng username); nút "Dùng thử, không cần tài khoản" mạnh nhất vì không bắt buộc tài khoản. Bản thử mô phỏng đăng nhập trong trình duyệt (`web/src/user/account.ts`, không lưu mật khẩu); auth thật thay module này.

## 8. Câu hỏi mở cho designer

1. Hiển thị "khả thi trực tiếp" trên điện thoại thế nào mà không che shortlist (bottom sheet, thanh dính, …)?
2. Đánh dấu sở thích "từ hồ sơ của bạn" thế nào để chúng đọc như suy đoán sửa được, không phải cài đặt?
3. Cách nhẹ nhất để hiển thị xu hướng comment kèm cỡ mẫu trên một thẻ nhỏ là gì?
4. Người dùng đi từ một xung đột đến cách sửa của nó trong một bước thế nào?
5. Hàng đợi review trông thế nào khi admin cần xử lý 50 mục trong 10 phút?
