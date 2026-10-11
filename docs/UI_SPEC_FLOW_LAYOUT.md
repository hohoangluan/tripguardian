# TripGuardian — Đặc tả luồng màn và bố cục: User Web

Dành cho người vẽ từng màn trong Figma. Tài liệu này trả lời hai câu: **màn nào nối sang màn nào, bằng thao tác gì, chuyển cảnh ra sao** (§1–3), và **mỗi màn chia vùng thế nào** (§4–6).

Không chép lại ở đây:
- Mục bắt buộc và danh sách frame trạng thái của từng trang: `docs/UI_SPEC_USER_WEB.md` §4. Bố cục dưới đây là chỗ đặt các mục đó.
- Màu, chữ, khung 1440: `docs/UI_SPEC_USER_WEB.md` §8–9. Quy tắc hiển thị dữ liệu: §6.
- Landing: `docs/UI_SPEC_LANDING.md`. Ở đây chỉ có cú chuyển landing → app.

Đánh số trang theo `docs/UI_SPEC_USER_WEB.md` §3 (Trang 0–10). Route và hành vi chuyển lấy từ code: `web/src/user/UserApp.tsx`, `web/src/user/screens/`, `web/src/App.tsx`.

---

## 1. Bản đồ màn

```text
 Landing / ── Bắt đầu ──► Hiểu chuyến đi (câu mẫu là lượt đầu)
 /app  ── chưa có tài khoản ──► Vào ứng dụng ── Dùng thử / đăng nhập ──► Khám phá
                                                                         │ gõ một câu · chủ đề
 ══════ TRONG LUỒNG (stepper 3 bước) ════════════════════════════════════╪═══════════
 Bước 1  Hiểu chuyến đi ── agent đủ hiểu / Bắt đầu tìm ───────────────────┤ trip → decision
 Bước 2  Chọn nơi ⇄ Chi tiết ⇄ So sánh  + trợ lý  + thanh "Đã chọn"       │ (khả thi + lịch ngầm)
          └──────── Xem lịch trình ───────────────────────────────────────┤ decision → planning
 Bước 3  Lịch trình (+ ngăn Tối ưu) ── Chốt kế hoạch này ──────────────────┤
 ═════════════════════════════════════════════════════════════════════════╪═══════════
         Phản hồi ──► Chuyến của tôi
 NGOÀI LUỒNG (rail trái): Khám phá ⇄ Chuyến của tôi ⇄ Đã lưu ⇄ Hồ sơ
```

Route và mục bắt buộc từng màn: `docs/UI_SPEC_USER_WEB.md` §3–4. Route lấy từ code: `web/src/user/UserApp.tsx`.

## 2. Bảng chuyển màn

| Từ | Thao tác | Tới | Ghi chú | Kiểu |
|---|---|---|---|---|
| Landing | `Bắt đầu` | Hiểu chuyến đi | câu mẫu thành lượt đầu | T1 |
| `/app` | chưa có tài khoản | Vào ứng dụng | | — |
| Vào ứng dụng | Dùng thử / đăng nhập xong | Khám phá | | T1 |
| Khám phá | Enter trong ô nhập, một trong 4 thẻ, một chủ đề | Hiểu chuyến đi | chuyến mới; chuyến cũ vẫn ở Chuyến của tôi | T1 |
| Khám phá | `Đi tiếp` trên Chuyến đang lập | bước đang dở | | T1 |
| Hiểu chuyến đi | agent tự chốt / `Bắt đầu tìm` | Chọn nơi | `trip → decision` | T2 |
| Hiểu chuyến đi | `Xem đầy đủ` / `Thu gọn`, `Esc` | panel vé trên chính màn | | T4 |
| Chọn nơi | ảnh / `Chi tiết` | Chi tiết | | T3 |
| Chọn nơi | `So sánh` trên cặp giống nhau, nút nổi "So sánh N nơi" | So sánh | | T3 |
| Chọn nơi | `Bỏ` | sheet lý do | lý do không bắt buộc | T4 |
| Chọn nơi | Thêm / Khóa / trả lời câu hỏi làm hẹp / nhắn trợ lý | ở lại | thẻ đổi trạng thái, thanh "Đã chọn" hiện dòng chênh lệch, lịch dựng lại ngầm | T5 |
| Chọn nơi | `Sửa vé chuyến`, `Nới giới hạn`, cách sửa "nới" | Hiểu chuyến đi | `decision → trip` | T1 ngược |
| Thanh "Đã chọn" | bấm thân thanh | danh sách đã chọn | | T4 |
| Thanh "Đã chọn" | một cách sửa trong dải chú ý | ở lại | xung đột co lại / biến mất | T5 |
| Thanh "Đã chọn" | `Xem lịch trình` (chỉ khi khả thi hoặc chưa biết số ngày) | Lịch trình | `decision → planning` + một lần Tối ưu | T2 |
| Chi tiết / So sánh | `Về danh sách gợi ý` / back | Chọn nơi | giữ tab | T3 ngược |
| Chi tiết | `Báo thông tin sai` | hộp nhập | gửi vào hàng chờ | T4 |
| Lịch trình | chọn hành trình, đổi chỗ nghỉ, thay dự phòng | ở lại | dòng báo + Hoàn tác | T5 |
| Lịch trình | `Tối ưu lịch` / `Xem đề xuất` | ngăn Tối ưu | | T4 |
| Lịch trình | `+ Thêm nơi` / `Quay lại chọn nơi` / bước 2 trên stepper | Chọn nơi | `planning → decision`, giữ lựa chọn | T1 ngược |
| Lịch trình | `Chốt kế hoạch này` | Phản hồi | | T1 |
| Phản hồi | `Gửi` | trạng thái đã gửi | | T5 |
| Phản hồi | `Bỏ qua` / `Đến Chuyến của tôi` | Chuyến của tôi | | T1 |
| Chuyến của tôi | `Đi tiếp` / `Xem lịch` / `Phản hồi` | đúng màn của chuyến đó | | T1 |

## 3. Kiểu chuyển cảnh

Năm kiểu (T1–T5), không thêm kiểu thứ sáu. Mỗi chuyển động phải nói được bằng lời nó nghĩa là gì.

| Kiểu | Nghĩa | Chuyển động |
|---|---|---|
| **T1 Sang bước** | đi tới hoặc lùi một bước trong luồng | Nội dung cũ mờ và dịch 24px theo chiều đi, nội dung mới vào từ phía ngược lại, 280 ms. **Thanh trên đứng yên**; bước mới sáng lên trên stepper. Lùi thì chiều ngược lại. |
| **T2 Chờ máy** | backend đang làm, có thể vài giây | Sang ngay bố cục khung của màn đích (§6.3), chữ nói đúng việc đang làm. Xong thì nội dung thật hiện thay khung, không nhảy bố cục. Không thanh phần trăm giả. |
| **T3 Đào sâu** | xem kỹ một nơi rồi quay lại | Ảnh bìa thẻ nở thành dải ảnh đầu trang chi tiết (phần tử chung), phần còn lại mờ vào. Quay lại: dải ảnh thu về đúng thẻ cũ, **giữ tab và vị trí cuộn**. Không đổi bước trên stepper — vẫn là bước "Chọn nơi". |
| **T4 Lớp phủ** | làm một việc nhỏ mà không rời màn | Panel trượt từ cạnh nó bám vào (phải cho `Xem đầy đủ`, dưới cho thanh "Đã chọn" và sheet), 240 ms. Màn bên dưới **không bị làm mờ** khi vẫn dùng được (panel `Xem đầy đủ`); bị phủ mờ khi là hộp chặn (lý do bỏ, báo sai). Đóng bằng `Esc` hoặc nút đóng. |
| **T5 Cập nhật tại chỗ** | dữ liệu đổi, màn không đổi | Phần đổi nháy nền nhạt 600 ms rồi tắt; danh sách tự xếp lại bằng chuyển vị trí, không nhảy. Dòng chênh lệch trượt lên từ thanh đáy, tự ẩn sau vài giây, **không chặn thao tác**. |

`prefers-reduced-motion: reduce`: T1, T3, T4 thành đổi tức thì hoặc mờ chéo ≤120 ms; T5 chỉ còn đổi màu nền, không dịch chuyển.

Lỗi giữa đường chuyển (backend từ chối, mất mạng): ở lại màn cũ, hiện dòng lỗi ngay cạnh nút vừa bấm, nút bấm lại được. Không sang màn đích rỗng.

---

## 4. Khung chung

Nội dung trong cột tối đa 1280, lề 48 (`--tg-max`, `--tg-gutter` trong `web/src/user/css/tokens.css`). Ba chế độ khung:

```text
BARE (Vào ứng dụng)   ảnh trái + thẻ phải, không thanh trên
FLOW (bước 1–3, Phản hồi)
┌──────────────────────────────────────────────────────────────────────────────┐
│ ▲ TripGuardian      ① Hiểu chuyến đi ─ ② Chọn nơi ─ ③ Lịch trình      [vé] (●) │ 68px
├──────────────────────────────────────────────────────────────────────────────┤
│ … nội dung …                                                                 │
│ [thanh dính đáy nếu màn có: "Đã chọn" trên Chọn nơi · Chi tiết · So sánh;    │ 76px
│  thanh chốt trên Lịch trình]                                                  │
└──────────────────────────────────────────────────────────────────────────────┘
NAV (Khám phá, Chuyến của tôi, Đã lưu, Hồ sơ): rail trái 76px — logo · 4 icon có tooltip · avatar
```

- Stepper: đã xong = dấu tích, bấm được để lùi; đang ở = nền trắng nổi; chưa tới = nhạt. Phản hồi hiện cả ba đã xong.
- `[vé]` chỉ ở Hiểu chuyến đi: icon nhỏ có số mục, mở popover vé; `(●)` là avatar / icon hồ sơ.
- Không bao giờ hiện cùng lúc stepper và rail.
- Trợ lý ở Chọn nơi là tab nhỏ mép phải, mở thành ngăn 380px bên phải; ghim thì lưới còn 2 cột.

## 5. Bố cục từng màn

- **Khám phá**: hero ảnh tràn (78vh) với tiêu đề, ô nhập lớn, chip · (người quay lại) thẻ Chuyến đang lập: ảnh trái, thông tin + tiến độ giữa, cột "Chuyến khác" phải · lưới 4 thẻ bắt đầu · 3 thẻ chủ đề ảnh lớn.
- **Hiểu chuyến đi**: ba cột — trái "Mình đang hiểu" (ý định đã xong, bấm để sửa; ý định đang hỏi) · giữa bộ thẻ câu hỏi xếp chồng (thẻ đã trả lời rơi xuống, thẻ mới chia ra) · phải "Đang hợp với bạn" (số nơi qua giới hạn chạy tới giá trị mới, nhãn "−N nơi" / "+N nơi" của lựa chọn vừa rồi, bốn lựa chọn gần nhất kèm +/−, nơi bắt buộc). Mỗi chip trả lời ghi trước nó làm số này đổi bao nhiêu. Dưới 1180px còn cột giữa và lịch sử dạng dòng.
- **Chọn nơi**: đầu trang + nút Lưới / Đĩa xoay + `Sửa vé chuyến` · dải giới hạn đã loại · nơi bắt buộc · tab nhóm · lưới 3 cột (2 khi ghim trợ lý) · thanh "Đã chọn" dính đáy, dải chú ý nổi ngay trên nó.
- **Chi tiết**: đầu trang + thao tác phải · dải ảnh (1 lớn + 3 nhỏ) · hai cột: *Thông tin thực tế* (giờ, giá, địa chỉ, khoảng cách, độ đông theo buổi, bản đồ Google) ⟂ *Người đi trước nói gì* (lý do + đánh đổi kèm cỡ mẫu, độ đông, bình luận gốc, clip).
- **So sánh**: lưới cột nhãn + 2–3 cột nơi, chỉ hàng khác nhau, ô tốt hơn có dấu tích; hàng thao tác Giữ / Bỏ cuối.
- **Lịch trình**: đầu trang + tab hành trình · dải số liệu (di chuyển, số nơi, chi phí, độ vững, `Tối ưu lịch`) · ba cột: tab ngày + điều kiện ngày + timeline · bản đồ Google lộ trình ngày · cột bên chỗ nghỉ, dự phòng của ngày, lưu ý. Chế độ *Hành trình* thay ba cột bằng sơ đồ thẻ ảnh nằm ngang.
- **Chuyến của tôi / Đã lưu / Hồ sơ**: đầu trang + tab lọc + lưới thẻ; rỗng dùng §6.1.

## 6. Trạng thái dùng chung — đặt ở đâu

### 6.1 Rỗng

Cột giữa `[c4–9]`, căn giữa dọc trong vùng nội dung: minh hoạ nét mảnh 160px → một câu nói vì sao rỗng → **một** nút dẫn tới màn sửa được. Các màn có rỗng: Chọn nơi chưa có gợi ý → Hiểu chuyến đi; Lịch trình chưa có lịch → Chọn nơi; Chuyến của tôi, Đã lưu → Khám phá.

### 6.2 Lỗi

- Lỗi tải trang: thay vùng nội dung bằng khối giống rỗng, chữ hổ phách, nút `Thử lại`.
- Lỗi một thao tác: dòng lỗi ngay dưới nút / thẻ vừa bấm, không toast góc màn.
- Phiên hết hạn ở Chọn nơi: khối rỗng *"Phiên chọn nơi đã hết…"* + nút về Hiểu chuyến đi.
- Màn gặp lỗi hiển thị: khối *"Màn này gặp lỗi hiển thị"* + `Tải lại` (chuyến đi vẫn trên máy chủ).

### 6.3 Chờ (T2)

Mỗi màn có backend vẽ **một khung xương** đúng bố cục thật: Hiểu chuyến đi *"Đang mở cuộc hỏi"*, Chọn nơi *"Đang chuẩn bị gợi ý"*, thanh "Đã chọn" *"Đang xếp lịch…"*, Lịch trình *"Đang xếp lịch… chỗ nghỉ có thể đến sau ~10 giây"*. Trong Hiểu chuyến đi, agent đang trả lời: ô chọn khóa, dòng chữ agent hiện dần ngay dưới câu hỏi, không chấm "đang gõ".

---

## 7. Giao trong Figma

Theo `docs/UI_SPEC_USER_WEB.md` §10, thêm:
1. **Một page "Luồng"**: các frame chính đặt theo bản đồ §1, nối prototype đúng từng dòng bảng §2.
2. Mỗi cạnh prototype gán kiểu §3 (Smart Animate cho T3, Move In cho T4, Dissolve cho T1/T2), thời lượng như bảng.
3. Mỗi frame có nhãn: tên màn · trạng thái · khung (BARE / FLOW / NAV) · một dòng "khi hẹp lại: …" theo §5.
