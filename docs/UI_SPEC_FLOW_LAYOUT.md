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
                       BẮT ĐẦU (T0 lặn sương)
  /landing ──────────────────────────────────────►  /app
                                                      │
                     chưa có tài khoản ──► [1] Vào ứng dụng ──┐
                                                      │        │ xong
                     có chuyến đang lập ──► [0] Trang chủ ◄───┤
                     chưa có chuyến ──────► [2] Bắt đầu ◄─────┘
                                                      │
  ═══════════════ TRONG LUỒNG (thanh trên = 4 bước) ═══╪══════════════════════════════
                                                      ▼
  Bước 1   [3] Hiểu chuyến đi ── BẮT ĐẦU TÌM / agent tự chốt ──► (chờ: đang chuẩn bị gợi ý)
                                                      │
  Bước 2   [4] Gợi ý ⇄ [5] Chi tiết địa điểm          ▼
             │  ⇄ [6] So sánh          thanh "Đã chọn" dính đáy trên 4·5·6
             └──────────── Kiểm tra khả thi ──────────┐
  Bước 3   [7] Kết quả khả thi ── Xếp lịch ──► (chờ: đang xếp lịch)
                                                      │
  Bước 4   [8] Lịch trình ── Chốt kế hoạch này ───────┤
  ═════════════════════════════════════════════════════╪══════════════════════════════
                                                      ▼
           [10] Phản hồi ──► [0] Trang chủ   (hoặc quay lại [8])

  NGOÀI LUỒNG (thanh trên = nav ngang):  [0] Trang chủ ⇄ Chuyến đi ⇄ Khám phá ⇄ [9] Hồ sơ
```

"Chuyến đi" trên nav không phải một trang: nó mở lại đúng bước đang dở (chưa có chuyến thì mở [2]).

## 2. Bảng chuyển màn

Cột **Kiểu** trỏ sang §3. Dòng nào có backend thì chỗ chờ nằm ở kiểu T2.

| Từ | Thao tác | Tới | Ghi chú | Kiểu |
|---|---|---|---|---|
| Landing | `BẮT ĐẦU` | `/app` | | T0 |
| Logo trên [1] | bấm | Landing | | T0 ngược |
| `/app` | chưa có tài khoản | [1] | | — |
| [1] | Dùng thử / đăng nhập xong | [0] nếu có chuyến, không thì [2] | | T1 |
| [2] | Enter trong ô nhập, hoặc bấm một trong 4 thẻ, hoặc *Theo gu quen thuộc / Lần này khác* | [3] | câu đã gõ thành lượt đầu tiên của [3] | T1 |
| [3] | `BẮT ĐẦU TÌM`, hoặc agent tự chốt sau một câu trả lời | [4] | backend chuyển stage `trip → decision` | T2 |
| [3] | `Xem đầy đủ` / `Thu gọn`, `Esc` | panel trên chính [3] | | T4 |
| [4] | bấm ảnh / tên / `Chi tiết` trên thẻ | [5] | | T3 |
| [4] | `So sánh` trên một cặp, hoặc nút nổi "So sánh N nơi" | [6] | | T3 |
| [4] | `Bỏ` | sheet lý do bỏ trên [4] | lý do không bắt buộc | T4 |
| [4] | Thêm / Khóa / trả lời câu hỏi làm hẹp / nhắn | ở lại [4] | thẻ đổi trạng thái, thanh "Đã chọn" hiện dòng chênh lệch | T5 |
| [4] | phản hồi agent cần hiểu lại chuyến | [3] | | T1 ngược |
| [5] | `Về danh sách gợi ý` / back trình duyệt | [4] | giữ tab và vị trí cuộn | T3 ngược |
| [5] | `Báo thông tin sai` | form trên [5] | chỉ gửi vào hàng đợi review | T4 |
| [6] | bấm tên một nơi | [5] | | T3 |
| [6] | `Giữ nơi này` / `Bỏ nơi này` | ở lại [6] | | T5 |
| Thanh "Đã chọn" | bấm thân thanh | panel danh sách đã chọn | | T4 |
| Thanh "Đã chọn" | `Kiểm tra khả thi` | [7] | | T1 |
| [7] | chọn một cách sửa có hành động | ở lại [7] | xung đột co lại / biến mất | T5 |
| [7] | cách sửa "nới giới hạn" | [3] | | T1 ngược |
| [7] | `Chọn địa điểm` (rỗng) / `Quay lại chọn lại` | [4] | | T1 ngược |
| [7] | `Xác nhận và xếp lịch` (chỉ khi khả thi hoặc chưa biết) | [8] | backend `decision → planning` | T2 |
| [8] | chọn phương án, đổi chỗ nghỉ, dùng dự phòng | ở lại [8] | dòng chênh lệch trên thanh đáy | T5 |
| [8] | tên một điểm dừng | [5] | | T3 |
| [8] | `+ Thêm nơi` / `Chọn lại địa điểm` | [4] | backend `planning → decision`, lịch phải xếp lại | T1 ngược |
| [8] | `Quay lại kiểm tra` | [7] | như trên | T1 ngược |
| [8] | `Chốt kế hoạch này` | [10] | | T1 |
| [10] | `Gửi` | [10] trạng thái đã gửi | | T5 |
| [10] | `Bỏ qua` / `Về trang chủ` | [0] | | T1 |
| [10] | `Xem lại lịch trình` | [8] | | T1 ngược |
| [0] | `Đi tiếp` | bước đang dở; còn xung đột thì [7] | | T1 |
| [0] | một nơi đã lưu | [5] | | T3 |
| [0] | `Chuyến mới` | hộp xác nhận → [2] | chuyến cũ bị thay | T1 |
| Thanh 4 bước | bấm một bước đã xong | bước đó | lùi stage ở backend; mọi kết quả bước sau bị bỏ | T1 ngược |
| Nút hồ sơ (mọi màn có thanh trên) | bấm | [9] | | T1 |
| [9] | `Tạo tài khoản` | [1] → xong quay về [9] | | T1 |
| [9] | `Mở tiếp` ở "Chuyến đi đang lập" | bước đang dở | | T1 |

## 3. Kiểu chuyển cảnh

Năm kiểu, không thêm kiểu thứ sáu. Mỗi chuyển động phải nói được bằng lời nó nghĩa là gì.

| Kiểu | Nghĩa | Chuyển động |
|---|---|---|
| **T0 Lặn sương** | đi vào / ra khỏi sản phẩm | Đã có trong code (`App.tsx`). Landing → app: camera lao vào sương 0,9 s, màn trắng phủ 0,35 s, đổi trang dưới lớp trắng, lớp trắng tan 0,6 s. App → landing: phủ trắng 0,4 s rồi thế giới 3D hiện ra khỏi sương. |
| **T1 Sang bước** | đi tới hoặc lùi một bước trong luồng | Nội dung cũ mờ và dịch 24px theo chiều đi, nội dung mới vào từ phía ngược lại, 280 ms. **Thanh trên đứng yên**; đoạn của bước mới lấp đầy trên thanh 4 bước. Lùi thì chiều ngược lại. |
| **T2 Chờ máy** | backend đang làm, có thể vài giây | Sang ngay bố cục khung của màn đích (§6.3), chữ nói đúng việc đang làm. Xong thì nội dung thật hiện thay khung, không nhảy bố cục. Không thanh phần trăm giả. |
| **T3 Đào sâu** | xem kỹ một nơi rồi quay lại | Ảnh bìa thẻ nở thành dải ảnh đầu trang chi tiết (phần tử chung), phần còn lại mờ vào. Quay lại: dải ảnh thu về đúng thẻ cũ, **giữ tab và vị trí cuộn**. Không đổi đoạn trên thanh 4 bước — vẫn là bước "Chọn nơi". |
| **T4 Lớp phủ** | làm một việc nhỏ mà không rời màn | Panel trượt từ cạnh nó bám vào (phải cho `Xem đầy đủ`, dưới cho thanh "Đã chọn" và sheet), 240 ms. Màn bên dưới **không bị làm mờ** khi vẫn dùng được (panel `Xem đầy đủ`); bị phủ mờ khi là hộp chặn (lý do bỏ, báo sai). Đóng bằng `Esc` hoặc nút đóng. |
| **T5 Cập nhật tại chỗ** | dữ liệu đổi, màn không đổi | Phần đổi nháy nền hồng nhạt 600 ms rồi tắt; danh sách tự xếp lại bằng chuyển vị trí, không nhảy. Dòng chênh lệch trượt lên từ thanh đáy, tự ẩn sau vài giây, **không chặn thao tác**. |

`prefers-reduced-motion: reduce`: T0, T1, T3, T4 thành đổi tức thì hoặc mờ chéo ≤120 ms; T5 chỉ còn đổi màu nền, không dịch chuyển.

Lỗi giữa đường chuyển (backend từ chối, mất mạng): ở lại màn cũ, hiện dòng lỗi ngay cạnh nút vừa bấm, nút bấm lại được. Không sang màn đích rỗng.

---

## 4. Khung chung

Khung 1440: nội dung trong cột 1280, lề 80, grid 12 cột, gutter 24 (`docs/UI_SPEC_USER_WEB.md` §9). Ba chế độ khung:

```text
BARE (trang 1)
┌──────────────────────────────────────────────────────────────────────────────┐
│ TripGuardian                                                                 │  ← chỉ logo, bấm về landing
├──────────────────────────────────────────────────────────────────────────────┤
│                         nội dung căn giữa                                    │
└──────────────────────────────────────────────────────────────────────────────┘

FLOW (trang 2–8, 10) — chế độ tập trung, không nav
┌──────────────────────────────────────────────────────────────────────────────┐
│ TripGuardian      ① Hiểu chuyến đi ─ ② Chọn nơi ─ ③ Khả thi ─ ④ Lịch trình   (●) │  64px
├──────────────────────────────────────────────────────────────────────────────┤
│ kicker nhỏ                                                                   │
│ TIÊU ĐỀ TRANG                                                                │  đầu trang
│ một dòng phụ                                                                 │
│ … nội dung …                                                                 │
├──────────────────────────────────────────────────────────────────────────────┤
│ [thanh dính đáy nếu màn có — "Đã chọn" trên 4·5·6, thanh chốt trên 8]         │  72px
└──────────────────────────────────────────────────────────────────────────────┘

NAV (trang 0, 9, Khám phá)
│ TripGuardian        Trang chủ   Chuyến đi   Khám phá   Hồ sơ               (●) │  64px
```

- Thanh 4 bước: đã xong = dấu tích, bấm được để lùi; đang ở = đậm; chưa tới = nhạt, không bấm được. Trang 10 hiện cả bốn đã xong. Trang 2 dùng khung FLOW với bước 1 đang ở.
- `(●)` là nút hồ sơ (chữ cái đầu tên hoặc icon), luôn ở góc phải, trừ khung BARE.
- Không bao giờ hiện cùng lúc thanh 4 bước và nav.
- Thanh dính đáy chiếm 72px; nội dung chừa 96px cuối trang để thẻ cuối không bị che.

---

## 5. Bố cục từng màn — desktop 1440

Ký hiệu: `[c1–8]` = chiếm cột 1 đến 8 trong grid 12 cột. Mỗi màn có: bố cục, vùng, đi vào từ / đi ra tới, và một dòng **khi hẹp lại (390)**.

### Trang 1 — Vào ứng dụng · khung BARE

```text
┌───────────────────────────────┬──────────────────────────────────────────────┐
│ [c1–6]                        │ [c7–12] thẻ trắng, căn giữa dọc               │
│                               │  MỘT CÂU SẢN PHẨM LÀM GÌ                      │
│   minh hoạ nét mảnh           │  [ DÙNG THỬ, KHÔNG CẦN TÀI KHOẢN ]  ← mạnh nhất│
│   (đồi, hồ, tuyến 5 điểm)     │  ──────── hoặc ────────                       │
│                               │  [ Google ]                       ← nổi nhất  │
│                               │  [Zalo] [Facebook] [Apple] [TikTok]           │
│                               │  email ______  mật khẩu ______  [Vào]         │
│                               │  Tạo tài khoản · Quên mật khẩu                │
└───────────────────────────────┴──────────────────────────────────────────────┘
```

Frame 2 (email): nửa phải là form đăng nhập / tạo tài khoản / quên mật khẩu, đổi qua lại bằng link dưới form.
Ra: [0] hoặc [2]. **Khi hẹp lại:** bỏ minh hoạ, thẻ chiếm cả màn.

### Trang 2 — Bắt đầu · khung FLOW (bước 1)

```text
                 [c3–10] căn giữa
                 CHUYẾN ĐÀ LẠT CỦA BẠN ĐANG THẾ NÀO?
                 Gõ tự nhiên, hoặc dán link TikTok, Google Maps…
                 ┌─────────────────────────────────────────────┐
                 │ ô nhập 3 dòng                                │  ← thành phần mạnh nhất
                 │ Enter để bắt đầu            [ BẮT ĐẦU → ]    │
                 └─────────────────────────────────────────────┘
                 ─────── chưa biết gõ gì? chọn một ───────
   [c2–11]  ┌──────────┐ ┌──────────┐ ┌──────────┐ ┌──────────┐
            │ icon     │ │ icon     │ │ icon     │ │ icon     │   4 thẻ lớn, bằng nhau
            │ Chưa có  │ │ Vài nơi  │ │ Một nơi  │ │ Một lịch │
            │ ý tưởng  │ │ đã lưu   │ │ phải đến │ │ có sẵn   │
            └──────────┘ └──────────┘ └──────────┘ └──────────┘
                 (người quay lại) Bạn đã đi Đà Lạt với mình…  (Theo gu quen thuộc) (Lần này khác)
                                     Về trang giới thiệu
```

Ra: [3]. **Khi hẹp lại:** 4 thẻ thành lưới 2×2; ô nhập dính trên khi bàn phím mở.

### Trang 0 — Trang chủ · khung NAV

```text
 CHÀO LINH,
 Chuyến Đà Lạt của bạn còn 2 việc chưa xong.
┌──────────────────────────────────────────────────────────────────────────────┐
│ [c1–5] ảnh bìa thật     │ [c6–12] CHUYẾN ĐANG LẬP                             │  thẻ lớn nhất
│ của 1 nơi đã chọn       │ Đà Lạt 3 ngày                                      │
│                         │ 12/11 · 3 ngày · 4 nơi đã chọn         (mono)      │
│                         │ ■■■■■■■■ ■■■■■■■■ □□□□□□□□ □□□□□□□□  4 đoạn         │
│                         │ ! Còn 1 xung đột chưa xử lý          [ ĐI TIẾP ]   │
└──────────────────────────────────────────────────────────────────────────────┘
┌──────────────────────────────────────┐ ┌─────────────────────────────────────┐
│ [c1–6] NƠI ĐÃ LƯU 5                  │ │ [c7–12] CHUYẾN ĐÃ ĐI 0              │
│ ▢ Tên · lý do để dành            ›   │ │ (rỗng) Đi xong chuyến này, nó sẽ…   │
│ ▢ …  (tối đa 3 dòng)             ›   │ │                                     │
└──────────────────────────────────────┘ └─────────────────────────────────────┘
 KHÁM PHÁ ĐÀ LẠT
┌────────────┐ ┌────────────┐ ┌────────────┐   3 thẻ [c1–4][c5–8][c9–12], nhãn `sắp mở`
└────────────┘ └────────────┘ └────────────┘
 ─ minh hoạ nhỏ · Bắt đầu một chuyến mới ··························· (Chuyến mới) ─   dải mỏng
```

Chiều cao cố định, không cuộn vô tận. Frame 2 (không có chuyến đang lập): thẻ lớn thành lời mời bắt đầu, nút `Bắt đầu` → [2].
**Khi hẹp lại:** xếp dọc theo đúng thứ tự trên; ảnh bìa thành dải 160px trên đầu thẻ chuyến.

### Trang 3 — Hiểu chuyến đi · khung FLOW (bước 1)

Bố cục đã chốt sau 24 bản thử; quy tắc nội dung ở `docs/UI_SPEC_USER_WEB.md` §4 Trang 3 (đọc trước khi vẽ).

```text
┌────────────────────────────────────────────────────────┬─────────────────────┐
│ [c1–8] CỘT HỎI                                         │ [c10–12] VÉ ~300px   │
│ (BUỔI TỐI) | câu 3 ········ Có 128 nơi đang hợp ▓▓▓░░   │ VÉ CHUYẾN NÀY        │
│                                                        │ Ngày     12–14/11    │
│ ┌ (nhiều lượt: thẻ trắng bao cả chuỗi) ──────────────┐ │ Đi với   người yêu   │
│ │ ✓ lượt đã xong · (chip đáp án)             Sửa     │ │ Xe       xe máy      │
│ │ ░ lượt đang hỏi — nền blush ░░░░░░░░░░░░░░░░░░░░░ │ │ ┃GIỚI HẠN┃ con dấu   │
│ │ CÂU HỎI CHỮ HOA HẸP                                │ │ ┄sở thích┄ ×         │
│ │ Vì sao hỏi: … (xanh mực, 1 dòng)                   │ │ ░ Buổi tối đang hỏi ░│
│ │ ┌────────┐ ┌────────┐ ┌────────┐ ┌─────┐           │ │                      │
│ │ │lựa chọn│ │lựa chọn│ │lựa chọn│ │Chưa │ ← nhỏ, nhạt│ │ CÒN CHƯA RÕ          │
│ │ └────────┘ └────────┘ └────────┘ └─────┘           │ │ · …        Trả lời   │
│ │ ___________________________________ Enter để gửi  │ │                      │
│ └────────────────────────────────────────────────────┘ │ đã ghi 6 mục         │
│ Bỏ qua câu này          Mình hỏi tiếp tuỳ câu trả lời… │ ╞═ BẮT ĐẦU TÌM ═╡    │
│                                                        │ Xem đầy đủ           │
│ (khoảng trống có chủ ý — lượt sau mọc xuống đây)        │                      │
└────────────────────────────────────────────────────────┴─────────────────────┘
```

- Cột hỏi cuộn; vé **dính**, chạy hết chiều cao màn (trừ thanh trên). Lượt mới mọc xuống dưới, cột tự cuộn để lượt đang hỏi nằm ở 1/3 trên.
- Khi agent ghi thêm một dòng lên vé: dòng đó vào bằng T5. Vé không nhảy chiều dài đột ngột: dòng mới đẩy các dòng dưới xuống bằng chuyển vị trí.
- Lời agent đang nói (`say`) hiện ngay dưới hàng cuối của lượt đang hỏi, chữ thường, không bong bóng.

**`Xem đầy đủ` (T4):**

```text
┌──────────────────────────────┬───────────────────────────────────────────────┐
│ cột hỏi ~42%                 │ panel 55% — trượt từ phải                      │
│ vẫn trả lời được,             │ VÉ CHUYẾN NÀY                    Thu gọn  ← dính│
│ không mờ, không bị che        │ Ngày   12–14/11   bạn trả lời ở câu 2   Sửa    │
│                              │ ▸ Buổi tối  thích chợ đêm  kết luận từ 3 câu   │
│                              │    ├ câu 4 … Sửa                               │
│                              │    └ Chỉ dòng kết luận được dùng để gợi ý.     │
│                              │ ┃Ngân sách ≤ 1tr┃ đang loại 6 nơi  (Nới) (Bỏ)  │
│                              │ ┄cà phê┄ cao · từ hồ sơ · 12 lần lưu           │
│                              │ ╞═ BẮT ĐẦU TÌM ═╡   Đặt lại toàn bộ   ← dính   │
└──────────────────────────────┴───────────────────────────────────────────────┘
```

Frame nhập địa điểm (frame 4 của spec): một khối trong cột hỏi, mỗi mục một hàng `[✓ đã khớp] / [? cần chọn: 2–3 ứng viên ngang] / [✕ không tìm thấy: Giữ chưa xác minh · Xóa]`, nhãn bắt buộc đến / đã lưu / … ở cuối hàng.
Ra: [4] qua T2. **Khi hẹp lại:** vé thành thanh mỏng dính dưới (`đã ghi 6 mục · Xem vé`), bấm mở thành bottom sheet cao 90%; panel `Xem đầy đủ` chính là sheet đó.

### Trang 4 — Gợi ý · khung FLOW (bước 2)

```text
 GỢI Ý CHO CHUYẾN CỦA BẠN
 Một tập nhỏ đáng cân nhắc, kèm lý do và cái giá phải đánh đổi. Bạn chốt, mình không chọn thay.
┌──────────────────────────────────────────────────────────────────────────────┐
│ NƠI BẮT BUỘC ĐẾN  (nếu có) — hàng thẻ ngang, viền mận                         │
└──────────────────────────────────────────────────────────────────────────────┘
 ┃Ngân sách đã loại 6 nơi ▾┃   ← dải mận mảnh, mở ra danh sách
 (Tham quan 8) (Thiên nhiên & view 6) (Ăn uống & cà phê 9) (Mua sắm 3)        ← tab
┌────────────┐ ┌────────────┐ ┌────────────┐
│ thẻ        │ │ thẻ        │ │ thẻ        │   3 cột [c1–4][c5–8][c9–12]
└────────────┘ └────────────┘ └────────────┘
 ┄ Cả hai đều là quán cà phê rừng thông, có lẽ bạn chỉ cần một.   (So sánh) ┄  ← dải nối 2 thẻ
┌──────────────────────────────────────────────────────────────────────────────┐
│ CÂU HỎI LÀM HẸP (chen sau hàng thẻ thứ 2, full width, bỏ qua được)            │
│ (chip) (chip) (Chưa chắc)                                         Bỏ qua      │
└──────────────────────────────────────────────────────────────────────────────┘
┌────────────┐ ┌────────────┐ ┌────────────┐
└────────────┘ └────────────┘ └────────────┘
 ▸ Chưa xác minh được điều kiện của bạn (3)      ← gập
┌──────────────────────────────────────┐ ┌─────────────────────────────────────┐
│ [c1–7] NÓI VỚI MÌNH                  │ │ [c8–12] VÌ SAO KHÔNG GỢI Ý…?         │
│ ________________ ví dụ: yên tĩnh hơn │ │ Tên địa điểm ______  → câu trả lời   │
└──────────────────────────────────────┘ └─────────────────────────────────────┘
                                                        (So sánh 2 nơi) ← nút nổi, phải dưới, trên thanh đáy
══════════════════ thanh "Đã chọn" dính đáy (xem dưới) ═══════════════════════════
```

**Thẻ địa điểm** (thành phần quan trọng nhất):

```text
┌───────────────────────────────┐
│ ảnh bìa 16:10      @creator   │  ← bấm = T3 sang [5]
│                    [Cao]      │  nhãn tin cậy góc ảnh
├───────────────────────────────┤
│ TÊN ĐỊA ĐIỂM                  │
│ cà phê · Trại Mát             │
│ ✓ view rừng thông             │  vì sao phù hợp — tối đa 3
│ ✓ hợp cặp đôi                 │
│ ! thêm ~25 phút di chuyển     │  đánh đổi — hổ phách, luôn ngay dưới
│ 60–90 phút          (mono)    │
│ [ + Thêm ]  Khóa · Bỏ · ⇄ · Chi tiết │  hover hiện đủ; không hover vẫn có Thêm
└───────────────────────────────┘
```

Thẻ đã chọn: viền hồng đậm, nút `Thêm` thành `✓ Đã chọn`. Thẻ khóa: thêm dấu khóa ở góc ảnh. Thẻ đang so sánh: dấu ⇄ bật.
Sheet lý do bỏ (T4, từ dưới, rộng 560 căn giữa): `Bỏ <tên>?` + 5 chip lý do + `Bỏ luôn, không cần lý do`.
**Khi hẹp lại:** 1 cột thẻ; tab thành hàng cuộn ngang dính dưới thanh trên; hai ô "Nói với mình / Vì sao không" xếp dọc.

### Thanh "Đã chọn" · lớp phủ trên 4, 5, 6

Chỉ hiện khi đã chọn ít nhất 1 nơi.

```text
THU GỌN (72px, nền mận, full width)
┌──────────────────────────────────────────────────────────────────────────────┐
│ 4 nơi · 6 giờ 30 · ≈1 giờ 50 đi · ~800k   (Có vẻ đi kịp)  │ +1 nơi · +70 phút…│ [KIỂM TRA KHẢ THI →] │
└──────────────────────────────────────────────────────────────────────────────┘
  bấm thân thanh = mở                                    dòng chênh lệch, tự ẩn

MỞ RA (T4 từ dưới, cao ~60% màn, nền trắng, màn sau phủ mờ)
┌──────────────────────────────────────────────────────────────────────────────┐
│ ĐÃ CHỌN 4 NƠI                                                       Thu gọn  │
│ ▢ Tên nơi · 60–90 phút · ! cảnh báo                       (🔒)  (✕)          │
│ ▢ …                                                                          │
│ tổng: thời gian · di chuyển · chi phí · cảnh báo                             │
│                                              [ KIỂM TRA KHẢ THI → ]          │
└──────────────────────────────────────────────────────────────────────────────┘
```

**Khi hẹp lại:** thanh còn `4 nơi · Có vẻ đi kịp · ›`; mở ra thành bottom sheet.

### Trang 5 — Chi tiết địa điểm · khung FLOW (bước 2)

```text
 ← Về danh sách gợi ý
 TÊN ĐỊA ĐIỂM                                   [ + Thêm vào danh sách ] Khóa · Bỏ
 cà phê · Trại Mát · [Độ tin cậy: Cao ⓘ]
┌──────────────────────────────────────────────────────────────────────────────┐
│ dải ảnh thật tràn ngang (3–4 ảnh), mỗi ảnh ghi nguồn       ← đích của T3      │
└──────────────────────────────────────────────────────────────────────────────┘
┌────────────────────────────┐ ┌─────────────────────────────────────────────┐
│ [c1–5] THÔNG TIN THỰC TẾ   │ │ [c6–12] NGƯỜI ĐI TRƯỚC NÓI GÌ   nền hồng nhạt│
│ nền trắng, bảng            │ │ ▸ Buổi sáng yên tĩnh                         │
│ Giờ  7:00–22:00            │ │   62% trong 123 comment · 30 creator         │
│      nguồn Google · 03/10  │ │   ┌clip┐ ┌clip┐ ┌clip┐  dọc 9:16, @creator   │
│ Giá  40–70k  ⚠ chưa xác nhận│ │   "comment gốc" → video                      │
│ Đặt chỗ  Chưa có thông tin │ │ ▸ Đông cuối tuần …                            │
│ bảng giờ theo ngày          │ │                                             │
├────────────────────────────┤ ├──────────────────────┬──────────────────────┤
│ BẢN ĐỒ GOOGLE              │ │ MỨC VẬN ĐỘNG          │ HỢP VỚI AI           │
└────────────────────────────┘ └──────────────────────┴──────────────────────┘
 ⚑ Báo thông tin sai   (link nhẹ, cuối trang)
══════════════════ thanh "Đã chọn" dính đáy ═════════════════════════════════════
```

Trái (fact) và phải (trải nghiệm) **khác nền**: hai loại sự thật khác nhau. Frame bằng chứng mở: một nhận định bung ra, clip đầu phát tại đúng đoạn trong trình phát dọc nổi trên cột phải (T4, màn sau không mờ).
Báo sai (T4, hộp giữa màn): ô nhập để người dùng tả bằng lời của mình chỗ sai + `Gửi`; xong hộp đóng, link thay bằng dòng *"Đã gửi. Mình sẽ kiểm tra lại nguồn; thông tin chỉ đổi sau khi có bằng chứng mới."* Web hiện mới có bản một chạm (`PlaceDetail.tsx`), chưa có ô nhập.
**Khi hẹp lại:** thứ tự dọc: đầu trang → ảnh → trải nghiệm → thực tế → vận động / hợp với ai → bản đồ; thao tác Thêm / Khóa / Bỏ thành thanh dính dưới thay thanh "Đã chọn".

### Trang 6 — So sánh · khung FLOW (bước 2)

```text
 SO SÁNH NHANH
 Chỉ những điểm khác nhau.
┌────────────────┬────────────────┬────────────────┬────────────────┐
│ [c1–3] dính    │ [c4–6]         │ [c7–9]         │ [c10–12]       │
│                │ ảnh · TÊN ›    │ ảnh · TÊN ›    │ ảnh · TÊN ›    │
├────────────────┼────────────────┼────────────────┼────────────────┤
│ Trải nghiệm    │ …              │ …              │ …              │
│ Di chuyển      │ ≈15 phút       │ ≈40 phút ★     │                │  ★ = nơi hơn ở dòng này
│ Độ đông        │ …              │ …              │                │
│ Chi phí        │ …              │ Chưa có thông tin│              │
│ Đẹp nhất lúc   │ …              │ …              │                │
├────────────────┼────────────────┼────────────────┼────────────────┤
│                │ [GIỮ NƠI NÀY]  │ [GIỮ NƠI NÀY]  │ [GIỮ NƠI NÀY]  │
│                │ Bỏ nơi này     │ Bỏ nơi này     │ Bỏ nơi này     │
└────────────────┴────────────────┴────────────────┴────────────────┘
 BẠN ƯU TIÊN ÍT DI CHUYỂN HAY YÊN TĨNH HƠN?   (Ít di chuyển) (Yên tĩnh)
 → nơi hợp ưu tiên được tô nhạt bên trên. Bạn vẫn là người bấm giữ.
══════════════════ thanh "Đã chọn" dính đáy ═════════════════════════════════════
```

2 nơi: hai cột nơi rộng [c4–8][c9–12]. **Khi hẹp lại:** cột thuộc tính dính trái, các nơi cuộn ngang, mỗi nơi rộng 70% màn.

### Trang 7 — Kết quả khả thi · khung FLOW (bước 3)

Cột giữa `[c3–10]`. Ba kết quả dùng chung bố cục, khác giọng và màu đầu trang.

```text
 KIỂM TRA KHẢ THI · 5 NƠI
 ĐI ĐƯỢC, NHƯNG CÒN CHỖ CẦN SỬA          ← khả thi: mực · một phần: hổ phách · không: mận
┌──────────────────────────────────────────────────────────────┐
│ cần 11 giờ trên 9 giờ có                                     │
│ ████████████████████████████████████████▌░░░│▓▓▓▓▓  ← tràn qua vạch│
└──────────────────────────────────────────────────────────────┘
 XUNG ĐỘT
┌──────────────────────────────────────────────────────────────┐
│ ! Ngày 2 quá tải — Đồi chè Cầu Đất + Thác Datanla             │
│   vi phạm: không quá 9 giờ mỗi ngày                           │
│   ○ Bỏ Thác Datanla — tiết kiệm 90 phút, Ngày 2 ổn            │  ← mỗi cách sửa là 1 hàng bấm,
│   ○ Dời Thác Datanla sang Ngày 3 — Ngày 3 còn 2 giờ trống     │     bấm = áp dụng (T5)
│   ○ Nới giới hạn "9 giờ/ngày" — cái giá: về muộn ~1 giờ  →    │  ← nới = về [3]
└──────────────────────────────────────────────────────────────┘
 KIỂM TRA TRƯỚC KHI ĐI      · Giờ mở cửa X chưa xác nhận …
 ĐỂ DÀNH CHO DỊP KHÁC       (chip nơi) (chip nơi)   ← bấm = [5]
 ─────────────────────────────────────────────────────────────
 Quay lại chọn lại                    [ XÁC NHẬN VÀ XẾP LỊCH → ]   ← khoá khi còn xung đột,
                                                                    chữ thành "Chọn cách sửa ở trên trước"
```

Khi xung đột cuối cùng biến mất: meter co lại vừa vạch (T5), tiêu đề đổi sang giọng khả thi, nút `Xác nhận và xếp lịch` bật. Xung đột vật lý **không có** hàng "nới".
Ra: [8] qua T2. **Khi hẹp lại:** giữ nguyên thứ tự, meter thành một dòng `11g / 9g` + thanh mảnh; nút xác nhận dính dưới.

### Trang 8 — Lịch trình · khung FLOW (bước 4)

Màn này **chỉ nhận thao tác, không có ô nhắn** (`docs/Role_Web_Functional_Design.md` §2.10).

```text
 LỊCH TRÌNH                         (Ít di chuyển) (Nhiều trải nghiệm) (Rẻ hơn)  ← tab phương án
 Giờ giấc và đường đi là ước tính.
┌──────────────────────────────────────────────────────────────────────────────┐
│ Di chuyển ≈3 giờ 10 │ Số nơi 7 │ Chi phí ~1,2tr (một phần chưa có giá) │ [Vững ⓘ] │
└──────────────────────────────────────────────────────────────────────────────┘
 lý do độ vững, 1 dòng
 ▸ So các phương án   (bảng đánh đổi, gập)
┌───────────────────────────┬──────────────────────────┬─────────────────────────┐
│ [c1–5] NGÀY               │ [c6–9] BẢN ĐỒ GOOGLE      │ [c10–12] CỘT BÊN         │
│ (Ngày 1 T7 12/11 ≈50' đi) │ lộ trình ngày đang xem    │ CHỖ NGHỈ ĐÊM            │
│ (Ngày 2) (Ngày 3)         │                          │ ○ nơi đã nhập · giá/đêm │
│ ☁ điều kiện ngày: mưa…    │      cao 560, dính        │ ● nơi đang dùng         │
│ 08:30 ① Tên nơi  60–90'   │                          │ PHƯƠNG ÁN DỰ PHÒNG       │
│   │ ≈15 phút xe máy       │                          │ Nếu mưa: A → B  (Dùng)  │
│ 10:15 ② Tên nơi           │                          │ Bị trễ: bỏ C trước      │
│   ! giờ mở chưa xác nhận  │ Di chuyển ≈50 phút        │ LƯU Ý CẢ CHUYẾN         │
│ 12:00 ░ Ăn (tự chọn) ░    │ Mở trên Google Maps ↗     │ · …                      │
│ …                         │                          │                         │
└───────────────────────────┴──────────────────────────┴─────────────────────────┘
 + Thêm nơi                 Quay lại kiểm tra
══ thanh đáy (mận): dòng chênh lệch "Đã xếp lại ngày 2" ·········· [ CHỐT KẾ HOẠCH NÀY ] ══
```

- Cảnh báo nằm **ngay dưới điểm dừng** nó thuộc về, không dồn cuối.
- Khối Ăn / Nghỉ / Chờ / Đệm là thẻ mảnh nền hồng nhạt, không có số thứ tự.
- Đổi tab ngày: chỉ cột ngày và bản đồ đổi (mờ chéo 160 ms), cột bên đứng yên.
- Đổi chỗ nghỉ / dùng dự phòng / chọn phương án: T5 trên dòng thời gian, dòng chênh lệch ở thanh đáy.

Ba màn trước khi có lịch đầy đủ (cùng khung, cột giữa `[c3–10]`):

| Trạng thái | Bố cục |
|---|---|
| Đang xếp lịch (T2) | Khung của bố cục trên: tab phương án mờ, dải số liệu mờ, 3 cột khung xương; chữ *"Đang xếp lịch"*, chỗ nghỉ có thể đến sau ~10 giây |
| Chọn một phương án | Tiêu đề *"Chọn một phương án"* + tab phương án lớn + bảng đánh đổi mở sẵn; chưa có cột ngày |
| Chưa xếp được lịch | Minh hoạ + tiêu đề + dòng "Vướng ở: …" + danh sách cảnh báo + `Chọn lại địa điểm` |

**Khi hẹp lại:** tab ngày dính dưới thanh trên; bản đồ thành nút `Xem bản đồ` mở sheet; cột bên xếp dưới dòng thời gian; thanh chốt giữ nguyên ở đáy.

### Trang 10 — Phản hồi · khung FLOW (cả 4 bước đã xong)

```text
                    [c4–9] căn giữa
                    KẾ HOẠCH ĐÃ CHỐT.
                    Vài câu ngắn thôi, bỏ qua được hết.
                    minh hoạ dải nét mảnh
                    ┌──────────────────────────────────┐
                    │ Gợi ý có đúng?      (1)(2)(3)(4)(5)│
                    │ Lý do dễ hiểu?      (1)…(5)       │
                    │ Lịch có thực tế?    (1)…(5)       │
                    │ Có tự tin hơn?      (1)…(5)       │
                    │ Còn phải tìm chỗ khác? (Có)(Không) │
                    │ ô góp ý 3 dòng                    │
                    │ [ GỬI ]   Bỏ qua                  │
                    └──────────────────────────────────┘
```

Đã gửi (T5): tiêu đề thành *"Cảm ơn bạn."*, thẻ thay bằng `[Xem lại lịch trình]  Về trang chủ`. **Khi hẹp lại:** giữ nguyên, thang 1–5 vẫn trên một hàng.

### Trang 9 — Hồ sơ và dữ liệu · khung NAV

```text
 HỒ SƠ VÀ DỮ LIỆU
 (●) Bạn đang dùng thử · Chuyến đi chỉ lưu trên trình duyệt này.   [Tạo tài khoản]
     (đã đăng nhập: tên · email                                       Đăng xuất)
┌──────────────────────────────────────┐ ┌─────────────────────────────────────┐
│ [c1–6] NGUỒN ĐÃ KẾT NỐI              │ │ [c7–12] ĐIỀU HỆ THỐNG SUY RA VỀ BẠN │
│ TikTok   chưa kết nối   (Thêm)       │ │ thích cà phê — cao · từ 12 lần lưu  │
│ Google   đã kết nối     (Thu hồi)    │ │                        Sửa · Xóa    │
│                                      │ │ …                    (Đặt lại hết)  │
└──────────────────────────────────────┘ └─────────────────────────────────────┘
┌──────────────────────────────────────────────────────────────────────────────┐
│ CHUYẾN ĐI ĐANG LẬP   3 ngày · 4 nơi đã chọn · đang ở bước chọn nơi (Mở tiếp) │
└──────────────────────────────────────────────────────────────────────────────┘
```

Frame rỗng: hai thẻ trên nói *"Không có nguồn nào thì mọi thứ vẫn chạy"*, không ép kết nối. **Khi hẹp lại:** xếp dọc.

### Khám phá Đà Lạt · khung NAV

Đầu trang + 3 thẻ chủ đề `[c1–4][c5–8][c9–12]`, mỗi thẻ nhãn `sắp mở`, không bấm được. Khi mở, mỗi thẻ là một lối vào [4] với shortlist dựng sẵn (T1), không phải trang đọc.

---

## 6. Trạng thái dùng chung — đặt ở đâu

### 6.1 Rỗng

Cột giữa `[c4–9]`, căn giữa dọc trong vùng nội dung: minh hoạ nét mảnh 160px → một câu nói vì sao rỗng → **một** nút dẫn tới màn sửa được. Các màn có rỗng: [4] chưa có gợi ý → [3]; [7] chưa chọn nơi → [4]; [8] chưa có lịch → [7].

### 6.2 Lỗi

- Lỗi tải trang: thay vùng nội dung bằng khối giống rỗng, chữ hổ phách, nút `Thử lại`.
- Lỗi một thao tác: dòng lỗi ngay dưới nút / thẻ vừa bấm, không toast góc màn.
- Phiên hết hạn ở [4]: khối rỗng *"Phiên chọn nơi đã hết…"* + nút về [3].

### 6.3 Chờ (T2)

Mỗi màn có backend vẽ **một frame khung xương** đúng bố cục thật: [3] lượt đầu đang hỏi, [4] *"Đang chuẩn bị gợi ý"*, [7] *"Đang kiểm tra"*, [8] *"Đang xếp lịch"*. Trong [3], agent đang trả lời: ô chọn khóa, dòng chữ agent hiện dần ngay dưới câu hỏi, không chấm "đang gõ".

---

## 7. Giao trong Figma

Theo `docs/UI_SPEC_USER_WEB.md` §10, thêm:
1. **Một page "Luồng"**: các frame chính đặt theo bản đồ §1, nối prototype đúng từng dòng bảng §2.
2. Mỗi cạnh prototype gán kiểu §3 (Smart Animate cho T3, Move In cho T4, Dissolve cho T1/T2), thời lượng như bảng.
3. Mỗi frame có nhãn: số trang · trạng thái · khung (BARE / FLOW / NAV) · một dòng "khi hẹp lại: …" lấy từ §5.
