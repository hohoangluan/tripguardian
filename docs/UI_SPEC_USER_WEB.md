# TripGuardian — Đặc tả UI/UX: User Web (bản người dùng dùng hằng ngày)

Dành cho designer / Figma. Tài liệu này trả lời **cần thiết kế mấy trang, mỗi trang phải có mục gì, mỗi trang có mấy trạng thái phải vẽ**. Bố cục từng màn và luồng chuyển màn: `docs/UI_SPEC_FLOW_LAYOUT.md`. Phong cách hình ảnh, chi tiết grid và vi tương tác: **designer toàn quyền**. Mục tiêu là giao diện đẹp, dùng được trên điện thoại một tay.

Đọc kèm:
- `docs/UX_Design_Brief.md` — thiết kế cho ai, nguyên tắc, cách hiển thị chất lượng dữ liệu (§4), hệ thị giác đang dùng (§7).
- `docs/Role_Web_Functional_Design.md` §2 — chức năng đầy đủ từng màn (nguồn sự thật về chức năng).
- Bản đang chạy: `web/src/user/` (React). Dùng để đối chiếu nội dung thật, **không phải để copy layout** — layout chính là phần cần designer làm lại cho đẹp.

---

## 1. Phạm vi

Chỉ **User Web** — phần người dùng mở hằng ngày, tất cả nằm dưới `/app`. Ngoài phạm vi: landing `/landing`, Admin Web `/admin`.

- **Vòng này chỉ làm desktop 1440.** Chốt bố cục, hệ thị giác và hệ thành phần ở bề mặt rộng trước, nơi đủ chỗ đặt cạnh nhau "lý do phù hợp", "đánh đổi" và bằng chứng — ba thứ trên điện thoại phải nén lại. Mobile 390 làm vòng sau, **dùng lại đúng hệ thành phần này**.
- Đích cuối vẫn là điện thoại (người dùng lên kế hoạch trên điện thoại, thường ngay sau khi xem TikTok). Nên mỗi khối ở đây phải nói rõ được **khi hẹp lại thì nó xếp thế nào** — ghi chú một dòng cạnh frame là đủ.
- **Toàn bộ nội dung tiếng Việt**, từ ngữ đời thường, không thuật ngữ hệ thống.
- MVP một thành phố: **Đà Lạt**, chuyến 2–4 ngày, cặp đôi / nhóm bạn / gia đình nhỏ; xe máy, ô tô hoặc xe công nghệ.

## 2. Designer được tự do gì, phải giữ gì

| Toàn quyền sáng tạo | Phải giữ |
|---|---|
| Grid, khoảng trắng, cỡ chữ, tỉ lệ thẻ, bo góc, bóng, màu bổ sung | Danh sách trang và **mục bắt buộc** của mỗi trang ở §4 |
| Cách gom nhóm, thứ tự khối trong một trang, dùng tab / accordion / sheet / carousel | Thứ bậc quyết định: lý do phù hợp và đánh đổi luôn đi **cùng nhau**, không tách trang |
| Chuyển động, vi tương tác, cảm giác "sống" khi danh sách thay đổi | Quy tắc hiển thị dữ liệu ở §6 (fact / signal / estimate / độ tin cậy / chưa biết) |
| Thay hệ thị giác hiện tại bằng hướng mạnh hơn, nếu giữ được "poster du lịch Đà Lạt" và đọc tốt ngoài nắng | Mỗi trạng thái liệt kê ở §4 phải có một frame — kể cả trạng thái rỗng và lỗi |
| Icon set, minh họa, cách dùng ảnh poster | Tiếng Việt, giọng điệu ở §7 |

Không được làm: dùng số sao / phần trăm trần làm tín hiệu chính; trình bày ước lượng như sự thật đã xác nhận; gợi ý chỗ ở; thay bản đồ Google bằng nhà cung cấp khác; hiện transcript video.

## 3. Bản đồ trang — 11 trang, ~35 frame desktop 1440

| # | Route | Tên trang | Người dùng làm gì ở đây | Ưu tiên | Frame tối thiểu (desktop) |
|---|---|---|---|---|---|
| 0 | `/app` (quay lại) | **Trang chủ** | Xem chuyến đang lập tới đâu, việc còn tồn; vào tiếp hoặc mở chuyến mới | P1 | 2 |
| 1 | `/app` (chưa đăng nhập) | Vào ứng dụng | Đăng nhập, hoặc dùng thử không cần tài khoản | P1 | 2 |
| 2 | `/app` (đã vào) | Bắt đầu | Trả lời 2 câu: đã đến Đà Lạt chưa, đang có gì | P1 | 2 |
| 3 | `/app/understand` | Hiểu chuyến đi | Khai ngày đi, người đi, phương tiện, giới hạn; trả lời câu hỏi sở thích; nhập địa điểm đã lưu; xem tóm tắt | P0 | 5 |
| 4 | `/app/shortlist` | Gợi ý | Đọc một tập nhỏ có lý do + đánh đổi; thêm / bỏ / khóa / so sánh | P0 | 5 |
| 5 | `/app/place/:id` | Chi tiết địa điểm | Xem bằng chứng: clip, comment, giờ giá, mức vận động, hợp với ai | P0 | 3 |
| 6 | `/app/compare/:ids` | So sánh | Đặt 2–3 nơi giống nhau cạnh nhau, chốt một | P0 | 2 |
| — | lớp phủ trên 4–6 | Thanh "Đã chọn" | Luôn thấy đã chọn mấy nơi, tổng thời gian, khả thi sơ bộ | P0 | 2 |
| 7 | `/app/feasibility` | Kết quả khả thi | Hiểu đi được hay không, xung đột ở đâu, sửa thế nào | P0 | 3 |
| 8 | `/app/plan` | Lịch trình | Chọn phương án, đọc lịch từng ngày, chỗ nghỉ, dự phòng, chốt | P0 | 5 |
| 9 | `/app/profile` | Hồ sơ và dữ liệu | Xem / sửa / xóa điều hệ thống suy ra; cấp hoặc thu nguồn | P2 | 2 |
| 10 | `/app/feedback` | Phản hồi | Trả lời ngắn sau khi chốt kế hoạch | P2 | 2 |

P0 = lõi sản phẩm, làm trước. **Nếu chỉ kịp làm 4 trang thì làm trang 3, 4, 5, 8** — bốn màn này quyết định sản phẩm sống hay chết; trang 1, 2, 9, 10 suy ra được từ hệ thành phần.

**Khung chung mọi trang (`/app`) — thanh trên có hai chế độ:**

```text
TRONG luồng (trang 3–8)   wordmark · thanh tiến trình 4 bước · nút hồ sơ      ← chế độ tập trung, không có nav
NGOÀI luồng (trang 0, 9)  wordmark · nav ngang: Trang chủ · Chuyến đi · Khám phá · Hồ sơ
```

Thanh tiến trình: Hiểu chuyến đi → Chọn nơi → Khả thi → Lịch trình. Sau tiêu đề mỗi trang có một dải ảnh poster minh họa. Thanh tiến trình bấm được để quay lại bước trước. Thiết kế lại khung này tự do, nhưng bốn bước phải đọc được trong một cái nhìn trên điện thoại.

---

## 4. Từng trang: mục bắt buộc và trạng thái phải vẽ

### Trang 0 — Trang chủ (`/app`, người quay lại)

**Chỉ hiện cho người đã có ít nhất một chuyến.** Người lần đầu vào thẳng hai câu hỏi ở trang 2 → luồng 4 bước, **không thấy trang này** — với người chưa có gì, một hub là một bước thừa trước khi được giúp.

Mục bắt buộc, theo đúng thứ tự, **bốn ô, hết là hết**:
1. **Lời chào + việc còn tồn** — một dòng nói *việc chưa xong*, không phải "chào mừng trở lại": *"Chuyến Đà Lạt của bạn còn 2 việc chưa xong."*
2. **Chuyến đang lập** — thẻ lớn nhất trang: ảnh bìa, tên chuyến, `12–14/11 · 3 ngày · 4 nơi đã chọn`, **thanh tiến trình 4 đoạn** đúng bước đang dở, dòng cảnh báo nếu còn xung đột, nút **Đi tiếp**.
3. **Nơi đã lưu** và **Chuyến đã đi** — hai thẻ nhỏ cạnh nhau. "Chuyến đã đi" có lối tắt *"Dùng lại gu chuyến này"*.
4. **Khám phá Đà Lạt** — ba thẻ chủ đề (*theo khu · theo thời tiết · theo giờ trong ngày*), gắn nhãn `sắp mở` khi chưa có.
5. **Chuyến mới** — một dải mỏng cuối trang, không phải nút to.

**Ràng buộc cứng — chống biến hub thành feed:**
- Không danh sách vô tận, không "gợi ý hôm nay", không widget kéo tương tác. Bốn ô, chiều cao cố định.
- Mỗi thẻ dẫn tới **một quyết định**, không dẫn tới một bài đọc. "Khám phá" là **cách vào luồng** (*"8 chỗ trong nhà khi mưa"* → bấm là thành shortlist), không phải tạp chí.
- Blog / khám phá **không được chen vào** 4 bước: trong luồng không có link thoát ra đọc bài.
- MVP chỉ có Đà Lạt: "Chuyến đã đi" không được hiện thành phố khác.

Frame: (1) có chuyến đang lập, còn xung đột · (2) không có chuyến nào đang lập (ô 2 thành lời mời bắt đầu).

### Trang 1 — Vào ứng dụng (`/app`, chưa đăng nhập)

Mục: nút **"Dùng thử, không cần tài khoản"** là nút mạnh nhất · Google (nổi nhất trong các nhà cung cấp), Zalo, Facebook, Apple, TikTok · email + mật khẩu (email để lấy lại mật khẩu, không dùng username) · một câu nói sản phẩm làm gì.

Frame: (1) chọn cách vào · (2) email + mật khẩu / tạo tài khoản / quên mật khẩu.

### Trang 2 — Bắt đầu (`/app`, đã vào)

Mục: **một ô nhập tự do** là thành phần mạnh nhất — người dùng gõ hoặc dán (link TikTok / Maps, danh sách đã lưu, lịch có sẵn, hay chỉ một câu). Ngay dưới là **một thẻ chip gọn** cho bốn thông tin chặn: *ngày* · *đi với ai* · *phương tiện* · *nơi lưu trú* (bỏ trống được).
- Khi người dùng chưa biết gõ gì: bốn thẻ bấm lớn *Chưa có ý tưởng gì* / *Vài địa điểm đã lưu* / *Một nơi nhất định phải đến* / *Một lịch trình có sẵn*.
- **Không hỏi "đã đến Đà Lạt chưa"** và không hỏi người dùng thuộc nhóm nào. Trạng thái bắt đầu được phân loại từ chính nội dung nhập (`docs/Project_Context.md` §3.2).
- Người quay lại có hồ sơ: thêm lối tắt *Theo gu quen thuộc* / *Lần này khác*.

Frame: (1) ô nhập + thẻ chip · (2) bốn thẻ bấm lớn · (3) biến thể người quay lại.

### Trang 3 — Hiểu chuyến đi (`/app/understand`) — trang khó nhất

Chốt 2026-10-04 sau 24 bản thử. Ảnh: `docs/design/desktop/v3-rose-photo/02-understand-k-ask.png`, `…-k-chain.png`, `…-k-expanded.png`. Các bản đã loại nằm ở `docs/design/desktop/_archive/understand-iterations/` — đọc trước khi đề xuất lại một hướng cũ.

Hai cột: **trái là cuộc hỏi, phải là vé**. Không bong bóng chat, không avatar, không nút gửi, không chấm "đang gõ". Lượt đã trả lời **co thành một dòng** kèm chip đáp án và nút `Sửa`.

#### A. Agent quyết, giao diện không được đoán thay

Ý định hỏi, số câu mỗi ý định, và thứ tự các ý định **do agent quyết lúc chạy**. Vì vậy màn hình **không bao giờ** hiện:

- `câu 2 / 3` hay bất kỳ phân số nào của số câu
- thanh tiến độ chia đoạn theo số câu
- câu hỏi kế tiếp dạng chữ ma
- `4 / 8 ý định` hay tổng số ý định
- danh sách ý định sắp hỏi

Chỉ được hiện **số thứ tự lượt hiện tại** (`câu 3`) và **những gì đã xảy ra**.

#### B. Cột trái — hai chế độ hỏi

| Chế độ | Khi nào | Hình dạng |
|---|---|---|
| **Một lượt** | ý định một câu là đủ | Câu hỏi + lựa chọn + ô nhập, không thẻ bao |
| **Nhiều lượt** | agent cần khai thác thêm | **Cả chuỗi nằm trong một thẻ trắng**: lượt xong co thành dòng có chip đáp án + `Sửa`, lượt đang hỏi nền blush, **không có chỗ trống cho lượt chưa tới** |

Mục bắt buộc, theo thứ tự:
1. **Hàng đầu, gom một dòng**: chip nhãn ý định (`BUỔI TỐI`) · gạch đứng · `câu N` · đẩy sang phải: `Có 128 nơi đang hợp với nhu cầu của bạn` + thanh mảnh. Chế độ nhiều lượt thêm `Bỏ qua phần này` ở cuối hàng. **Con số là sự thật hiện tại**, không phải dự đoán "sẽ lọc còn bao nhiêu".
2. **Câu hỏi** — chữ hoa hẹp, cỡ vừa, không khung, không avatar.
3. **`Vì sao hỏi`** — một dòng nhỏ màu xanh mực **ngay dưới câu hỏi**, không phải thẻ riêng. Nói câu này đổi cái gì, và nói rõ bỏ qua được.
4. **Lựa chọn** — thẻ trắng bo 16px viền hồng, mỗi thẻ một nhãn đậm + một dòng mô tả cho rõ nghĩa. Luôn có `Chưa chắc` và thẻ này **nhỏ, nhạt hơn** các thẻ kia.
5. **Ô nhập tự do** — **một đường kẻ**, không hộp bo, không nút gửi; gợi ý `Enter để gửi` ở cuối dòng.
6. **Hàng cuối** — `Bỏ qua câu này` bên trái; bên phải một dòng nhỏ nói đúng cách agent chạy: *"Mình hỏi tiếp tuỳ câu trả lời của bạn."* (một lượt) hoặc *"Mình hỏi thêm nếu còn chưa rõ, xong sẽ gộp thành một dòng trên vé."* (nhiều lượt).

**Khoảng trống nửa dưới cột trái là có chủ ý** — chỗ cho các lượt tới mọc xuống. Không lấp bằng nội dung trang trí.

#### C. Cột phải — vé

Vé thon (~300px), chạy hết chiều cao. Chỉ ghi **cái đã có**; không liệt kê thứ chưa hỏi.

- **Một ý định = một dòng**, không phải một dòng mỗi câu hỏi. Ba trạng thái dòng: **đã chốt** (nhãn + giá trị) · **đang hỏi** (nền blush, chữ `đang hỏi`, không phân số) · dòng chưa có thì **không xuất hiện**.
- **Dòng đã ghi nhận: nhãn trái, giá trị phải, không gạch ngang.** Dấu `—` chỉ có một nghĩa duy nhất: chỗ này chưa có gì.
- **Giới hạn cứng = con dấu mực thẳng** (không nghiêng — đây là chỗ phải đọc kỹ và sửa). **Sở thích mềm = chip viền đứt** có ×, mỗi chip có nhãn nguồn riêng (`từ hồ sơ của bạn · 12 lần lưu`).
- **`CÒN CHƯA RÕ`** — danh sách **động do agent tự đánh dấu**, có thể rỗng; mỗi dòng có nút `Trả lời`.
- Chân vé: `đã ghi N mục` (đếm cái đang có, **không phải phân số**) · nút `BẮT ĐẦU TÌM` dạng cuống vé · `Xem đầy đủ`.

Đã thử và **loại**: treo sở thích ra ngoài vé bằng móc và dây (`_archive/understand-iterations/02-understand-m-*.png`, `…-l-*.png`) — bỏ vì khi chưa có dữ liệu hồ sơ thì chỗ đó khuyết một mảng.

#### D. `Xem đầy đủ` — màn soát lại và sửa

Panel chiếm **55% bên phải**, cột hỏi hẹp còn ~42% nhưng **vẫn trả lời được, không bị làm mờ, không bị che**. Thanh trên không bao giờ bị đè. Đóng bằng `Thu gọn` hoặc `Esc`.

- **Panel cuộn dọc được.** Nội dung **không được thu nhỏ chữ để nhét vừa một màn** — cỡ chữ giữ như các màn khác, dài quá thì cuộn. Header của panel (`VÉ CHUYẾN NÀY`, `Thu gọn`) **dính trên** khi cuộn; chân panel (`BẮT ĐẦU TÌM`, `Đặt lại toàn bộ`) **dính dưới**.
- Mỗi dòng có **nguồn** (`bạn trả lời ở câu 2`, `kết luận từ 3 câu hỏi`) và nút `Sửa` nhảy về đúng chỗ đó.
- **Dòng kết luận mở ra được**, bên dưới là **chuỗi câu đã hỏi** để ra kết luận đó, mỗi câu con có `Sửa` riêng, chốt bằng dòng *"Chỉ dòng kết luận được dùng để gợi ý."* Dòng đang hỏi cũng mở được, câu chưa trả lời để `…`.
- Giới hạn cứng kèm **cái giá** (`đang loại 6 nơi`) và hai nút `Nới` · `Bỏ`.
- Sở thích kèm **mức tin cậy** và nguồn riêng từng chip.

#### E. Những mục khác của trang này

1. **Nhập địa điểm đã lưu / lịch trình có sẵn** — ba trạng thái phân biệt tức thì: **đã khớp ✓** · **cần bạn chọn** (2–3 ứng viên, mỗi cái có tên, khu vực, ảnh hoặc ghim bản đồ) · **không tìm thấy** (giữ dạng "chưa xác minh" hoặc xóa). Gộp trùng ("Túi Mơ To" và "Tiệm Túi Mơ To" là một nơi). Nhãn: bắt buộc đến / đã lưu / đã đi / tránh / chưa rõ. **Không bao giờ đoán match.**
2. **Chỗ ở** (không bắt buộc): người dùng đã có thì nhập, tra như mục 1. Hệ thống **không gợi ý chỗ ở**; nó chỉ quyết định điểm bắt đầu / kết thúc lộ trình.
3. **Nhãn "từ hồ sơ của bạn"** trên mọi thứ suy ra từ lịch sử, sửa được bằng một chạm, đọc như suy đoán chứ không như cài đặt.

Frame: (1) một lượt · (2) nhiều lượt · (3) `Xem đầy đủ` có dòng kết luận đã mở · (4) nhập địa điểm, ba trạng thái cùng khung · (5) vé khi chưa có sở thích nào.

### Trang 4 — Gợi ý / Shortlist (`/app/shortlist`)

Tiêu đề đang dùng: *"Gợi ý cho chuyến của bạn — một tập nhỏ đáng cân nhắc, kèm lý do và cái giá phải đánh đổi. Bạn chốt, mình không chọn thay."*

Mục bắt buộc:
1. **Khối nơi bắt buộc đến** lên trên cùng (nếu có).
2. **Tab nhóm**: điểm tham quan · thiên nhiên & view · ăn uống & cà phê · mua sắm / đặc sản, mỗi tab có số lượng. Chỗ ở **không** nằm trong shortlist.
3. **Thẻ địa điểm** — thành phần quan trọng nhất của sản phẩm. Trên desktop 3 cột, phải đủ các mục sau mà vẫn đọc nhanh:

```text
Tên · loại · khu vực            [ảnh bìa từ frame clip thật, ghi @creator]
Vì sao phù hợp   ✓ view rừng thông  ✓ hợp cặp đôi  ✓ gần khu Ngày 2 của bạn
Đánh đổi         ! thêm ~25 phút di chuyển
Thời gian        60–90 phút
Độ tin cậy       Cao / Trung bình / Thấp
Thao tác         Thêm · Bỏ · Khóa · So sánh · Chi tiết
```

4. **Nhóm nơi giống nhau**: hiện thành cặp/nhóm kèm câu như *"cả hai đều là quán cà phê rừng thông, có lẽ bạn chỉ cần một"* và lối tắt **So sánh**.
5. **Câu hỏi làm hẹp** chen giữa danh sách (một câu, bỏ qua được).
6. **Ô nhắn tự do** ("Nói với mình, ví dụ: yên tĩnh hơn đi") và **hộp "vì sao không gợi ý X"**.
7. **Thông báo bị loại bởi giới hạn cứng**: *"Ngân sách đã loại 6 nơi"* — nói rõ giới hạn nào, mở ra xem được.
8. **Khối "chưa xác minh được điều kiện của bạn"** gập lại, kèm lời nhắc tự kiểm tra trước.

Trạng thái: bình thường · quá ít kết quả (*"nới một giới hạn?"*) · mọi nơi bị một giới hạn loại (rỗng, có minh họa) · sheet hỏi lý do khi bỏ (*Quá xa / Quá đông / Quá đắt / Không thích / Đã đi rồi*) · nút nổi "So sánh 2 nơi" khi đã chọn 2.

Frame: 5.

### Trang 5 — Chi tiết địa điểm (`/app/place/:id`)

Nguyên tắc: **mọi nhận định cách bằng chứng một chạm**.

Mục bắt buộc:
1. **Thông tin thực tế** — giờ, giá, đặt chỗ: giá trị + nguồn (chính thức / Google) + ngày kiểm tra. Xung đột thì hiện **cả hai giá trị**, đánh dấu chưa xác nhận.
2. **Trải nghiệm** — mỗi nhận định mở ra bằng chứng: clip TikTok phát **đúng đoạn**, và xu hướng comment kèm **cỡ mẫu**: *"62% trong 123 comment về độ đông, từ 30 creator"*, cùng 2–3 comment gốc có link về video.
3. **Mức vận động** — đi bộ, dốc, đường vào.
4. **Hợp với ai** — cặp đôi, trẻ em, người lớn tuổi.
5. **Bản đồ Google** khi dữ liệu đến từ Google.
6. Nút **Báo thông tin sai** — nhẹ, không phải nút chính; chỉ đưa vào hàng đợi review, không đổi dữ liệu.
7. Thao tác dính dưới: Thêm vào danh sách chọn · Bỏ · Khóa.

Thông tin thực tế và bằng chứng trải nghiệm **phải tách rõ về mặt hình ảnh** — hai loại sự thật khác nhau.

Frame: (1) trang chi tiết · (2) bằng chứng mở (clip + comment) · (3) có xung đột giá trị + báo sai.

### Trang 6 — So sánh (`/app/compare/:ids`)

Mục: 2 (tối đa 3) nơi cạnh nhau; **chỉ hiện thuộc tính khác nhau** (trải nghiệm, di chuyển, độ đông, chi phí, thời điểm đẹp nhất) · một câu hỏi chốt (*"Ưu tiên ít di chuyển hay chỗ yên tĩnh hơn?"*) · chọn xong cập nhật chuyến đi ngay, hệ thống không chọn thay.

Frame: (1) 2 nơi · (2) 3 nơi.

### Thanh "Đã chọn" (lớp phủ trên trang 4–6)

Luôn hiển thị: số nơi đã chọn · tổng thời gian tham quan · thời gian di chuyển ước tính · chi phí ước tính · cảnh báo · **khả thi sơ bộ**.

Mỗi thay đổi hiện một **dòng chênh lệch** đọc trong nháy mắt: *"+1 nơi · +70 phút · +35 phút di chuyển — Ngày 2 có thể quá tải."* Dòng này **không được chặn thao tác**.

Trên desktop: thanh dính đáy, full width, không che thẻ dưới cùng (chừa chỗ cuộn cuối trang). Mobile tính sau.

Frame: (1) thanh thu gọn kèm dòng chênh lệch · (2) mở ra thành danh sách đã chọn.

### Trang 7 — Kết quả khả thi (`/app/feasibility`)

Ba kết quả, **ba frame riêng**, giọng khác nhau:

| Kết quả | Phải có |
|---|---|
| **Khả thi** | Xác nhận ngắn + đồng hồ "cần ~X giờ trên Y giờ có" + nút sang xếp lịch |
| **Khả thi một phần** | Nơi nào xung đột · vi phạm quy tắc nào · mỗi cách sửa **được gì cụ thể** (*"Bỏ C: tiết kiệm 90 phút, Ngày 2 ổn"*) · người dùng chọn cách sửa |
| **Không khả thi** | Lý do tổng thể (*"cần 14 giờ, có 9 giờ · vượt ngân sách 400k · hai booking trùng giờ"*) + lối quay lại tuyển chọn |

Thêm: khối **"Kiểm tra trước khi đi"** (cảnh báo), khối **"Để dành cho dịp khác"** (nơi bị gạt). Xung đột với giới hạn của người dùng → đưa ra "nới giới hạn này" **kèm cái giá cụ thể**. Xung đột vật lý (không đi kịp) → **chỉ** đưa cách dời có thật; không nút nào biến điều bất khả thi thành "khả thi".

Yêu cầu: từ một xung đột đến cách sửa của nó trong **một bước**.

Frame: 3.

### Trang 8 — Lịch trình (`/app/plan`)

Mục bắt buộc:
1. **Tab phương án** + **bảng đánh đổi** giữa các phương án (mỗi phương án tối ưu một mục tiêu khác: ít di chuyển / nhiều trải nghiệm / rẻ hơn…), có cột chi phí (*"Một phần chưa có giá"* khi thiếu).
2. **Tab ngày** (Ngày 1, Ngày 2… kèm thứ + ngày).
3. **Dòng thời gian một ngày**: giờ đến, thời gian ở lại, di chuyển giữa các điểm, cùng các khối *Ăn (tự chọn) · Nghỉ · Chờ · Đệm*. **Cảnh báo nằm tại đúng điểm dừng**, không dồn xuống cuối.
4. **Bản đồ lộ trình** (Google) + tổng di chuyển ước tính của ngày.
5. **Panel chỗ nghỉ đêm** — danh sách nơi người dùng đã nhập, giá/đêm nếu có, đổi được; đổi thì giờ di chuyển tính lại.
6. **Nhãn độ vững mỗi ngày**: Vững / Khả thi / Mong manh + lý do một câu.
7. **Phương án dự phòng** gắn với điểm nhạy cảm: *"Nếu mưa: A → B trong nhà"*, *"Bị trễ: bỏ C trước"* — chỉ thay khi người dùng chọn.
8. **Không có ô nhắn** — màn này chỉ nhận thao tác (chọn phương án, đổi chỗ nghỉ, dùng dự phòng, `+ Thêm nơi`); mỗi thao tác kèm dòng báo đã làm gì (*"Đã xếp lại một vài ngày bị ảnh hưởng"*).
9. Thông tin chưa xác nhận vẫn đánh dấu tại chỗ: *"Giờ mở cửa chưa xác nhận — kiểm tra trước khi đi"*.
10. Chân trang: *Quay lại kiểm tra* · **Chốt kế hoạch này**.

Luôn ghi rõ: *"Giờ giấc và đường đi là ước tính."*

Frame: (1) chọn phương án (chưa chọn) · (2) lịch một ngày đầy đủ · (3) panel chỗ nghỉ + đổi · (4) "Chưa xếp được lịch" (rỗng, có lối quay lại) · (5) sau một thao tác: dòng chênh lệch + lịch đã xếp lại.

### Trang 9 — Hồ sơ và dữ liệu (`/app/profile`)

Mục: **Nguồn đã kết nối** (mỗi nguồn tùy chọn, người dùng tự thêm; cấp / thu hồi) · **Điều hệ thống suy ra về bạn** (*"thích cà phê — cao, từ 12 lần lưu"*) kèm sửa / xóa / đặt lại · **Chuyến đi đang lập**. Không nguồn nào thì mọi thứ vẫn chạy — frame rỗng phải nói điều đó, không ép kết nối.

Frame: (1) có nguồn và suy đoán · (2) chưa có nguồn nào.

### Trang 10 — Phản hồi (`/app/feedback`)

Mục: tiêu đề đổi theo trạng thái (*"Kế hoạch đã chốt."* → *"Cảm ơn bạn."*) · vài câu hỏi ngắn, **bỏ qua được**: gợi ý có đúng, lý do có dễ hiểu, lịch có thực tế, có còn phải tìm chỗ khác, có tự tin hơn.

Frame: (1) form · (2) đã gửi.

---

## 5. Thành phần dùng chung (thiết kế một lần, dùng mọi nơi)

| Thành phần | Trạng thái cần có |
|---|---|
| Thẻ địa điểm | mặc định · đã chọn · đã khóa · đang so sánh · chưa xác minh · độ tin cậy thấp |
| Nhãn độ tin cậy | Cao / Trung bình / Thấp + chạm mở lý do một dòng (*"3 nguồn độc lập, kiểm tra tháng này"*) |
| Dấu "chưa xác nhận" | trên một giá trị, chạm mở lý do |
| Dấu "quá hạn" | *"có thể đã thay đổi — kiểm tra lần cuối <ngày>"* |
| Chip giới hạn cứng | nền đặc + khóa; đang áp dụng / vừa nới |
| Chip sở thích mềm | viền đứt; từ hồ sơ / người dùng tự nói · bỏ được |
| Khối bằng chứng | clip (ảnh bìa + @creator + link gốc) · comment gốc · trích đoạn nguồn chính thức |
| Trình phát clip | phát từ đúng đoạn; dọc, không transcript |
| Xu hướng comment | bản gọn cho thẻ nhỏ và bản đầy cho trang chi tiết, luôn có cỡ mẫu |
| Dòng chênh lệch | tăng / giảm / cảnh báo |
| Cảnh báo tại điểm dừng | nhẹ / nặng |
| Bong bóng hội thoại + chip trả lời | câu hỏi · đang nghĩ · đã trả lời (sửa được) |
| Bottom sheet | nhiều độ cao; dùng cho panel hiểu chuyến đi, lý do bỏ, danh sách đã chọn |
| Thanh tiến trình 4 bước | bước hiện tại · đã xong · chưa tới |
| Trạng thái rỗng | mỗi loại một câu dẫn hành động, có minh họa |
| Đang tải | dữ liệu địa điểm · một lượt hỏi · đang xếp lịch |
| Lỗi | lỗi tải dữ liệu · lỗi một hành động (thử lại được) |

## 6. Quy tắc hiển thị dữ liệu (áp dụng mọi trang, không thương lượng)

| Trạng thái | Người dùng thấy |
|---|---|
| Đã xác minh | Giá trị, bình thường |
| Chưa chắc chắn | Giá trị + dấu "chưa xác nhận"; chạm xem lý do |
| Quá hạn | Giá trị + "có thể đã thay đổi — kiểm tra lần cuối <ngày>" |
| Chưa biết | **"Chưa có thông tin"** — không bao giờ là giá trị mặc định, không bao giờ là "không" |

| Loại giá trị | Cách trình bày |
|---|---|
| **Fact** (giờ, giá) | Giá trị chính xác + nguồn + ngày |
| **Signal** (độ đông, yên tĩnh) | Xu hướng + bối cảnh + cỡ mẫu: *"sáng cuối tuần: đông · 123 comment, 30 creator"* |
| **Estimate** (thời gian tham quan, di chuyển) | **Luôn là khoảng**: "60–90 phút", "≈35 phút" |
| **Độ tin cậy** | Cao / Trung bình / Thấp + lý do một dòng |

Thông tin thực tế (chính thức / Google) và bằng chứng trải nghiệm (TikTok) phải **tách rõ về mặt hình ảnh**.

## 7. Giọng điệu nội dung

- Câu ngắn, như một người bạn hiểu Đà Lạt nói. Không "hệ thống đã xử lý", không "vui lòng".
- Mọi gợi ý có **cả hai phía**: vì sao phù hợp *và* đánh đổi.
- Mọi xung đột nêu **tên địa điểm + quy tắc bị vi phạm + cách khắc phục**.
- Không bao giờ lặng lẽ bỏ nơi người dùng đã chọn; nới giới hạn phải do người dùng xác nhận.
- Câu hỏi nào cũng bỏ qua được và có "Chưa chắc".

## 8. Hệ thị giác — trắng hồng (đã chốt 2026-10-04)

| Vai trò | Giá trị | Dùng ở đâu |
|---|---|---|
| Nền trang | `#FFF9F8` | ngoài thẻ |
| Bề mặt | `#FFFFFF` | thẻ, panel, top bar |
| Mực | `#3A2B32` | chữ chính |
| Hồng phấn | `#EFB8C4` | nút chính, tab/chip đang chọn, thanh tỉ lệ — **chữ mận** trên nó |
| Hồng đậm | `#C97890` | pin bản đồ, tuyến, viền thẻ đã chọn, focus — chỉ nét, không chữ |
| Hồng nhạt | `#FCEEF1` | khối mềm, bằng chứng trải nghiệm, bong bóng câu hỏi |
| Mận | `#6B3550` | **khối quy tắc cứng**, thanh dính đáy, footer |
| Hổ phách | `#A8660F` | **chỉ** đánh đổi và cảnh báo |
| Xanh mực | `#4A6488` | link, dòng nguồn dữ liệu |

Dịu lại từ `#E4607F` (2026-10-04): hồng chính cũ gắt và điệu. Ảnh dựng thử trong `v3-rose-photo/` vẫn mang hồng cũ — lấy bố cục, không lấy độ đậm.

- Chữ trắng **chỉ** trên nền mận / hổ phách; trên hồng phấn dùng chữ mận. Không bao giờ chữ hồng trên nền trắng.
- Phong cách: editorial nhẹ, nhiều trắng, hairline hồng nhạt 1px, bo 16px, bóng rất nhẹ, minh hoạ **nét mảnh** tô hồng phấn. Không gradient tràn, không emoji.
- Chữ: display hẹp chữ hoa cho tiêu đề và nút · sans hình học cho nội dung · **mono cho giờ, thời lượng, giá, cỡ mẫu**.
- Ảnh bìa địa điểm là **ảnh thật của chính nơi đó**: ảnh Google Maps hoặc frame clip TikTok, luôn ghi nguồn (`Ảnh: Google Maps` / `@creator`). **Không dùng ảnh có người** chiếm đáng kể khung hình (chọn offline bằng `web/scripts/pick_covers.py`). Ảnh thật giữ nguyên màu — không nhuộm hồng.
- Dã quỳ `#F2B31B` **không dùng trong app**; nó chỉ còn một chỗ duy nhất là mặt trời trong 3D của landing (`docs/UI_SPEC_LANDING.md`).

**Đã áp vào code** (`styles.css` `:root`, `user/user.css`). Video demo của landing vẫn phải quay lại.

Ảnh dựng thử cả 10 màn app: `docs/design/desktop/v3-rose-photo/` (`01-shortlist` … `14-home`). Đó là bản dựng ý tưởng để duyệt bố cục và màu, **không phải asset dùng được**.

## 9. Khung và kích thước

| Bề mặt | Khung | Vòng này |
|---|---|---|
| **Desktop** | **1440 × cao tùy trang** (thiết kế chính) | Nội dung trong cột tối đa 1280, lề 80; grid 12 cột, gutter 24 |
| Laptop nhỏ | 1280 | Suy ra: rớt từ 3 cột xuống 2 |
| Điện thoại | 390 × 844 | **Vòng sau.** Mỗi frame desktop ghi một dòng "khi hẹp lại: …" |

Sáng / tối: không bắt buộc cho MVP. Làm thì làm đủ, không nửa vời.

### 9.1 Những thứ chỉ desktop mới có — phải dùng

| | Yêu cầu |
|---|---|
| Nhiều cột | Shortlist 3 cột thẻ · Chi tiết địa điểm **chia đôi**: thông tin thực tế bên trái, bằng chứng trải nghiệm bên phải · Lịch trình 3 cột: dòng thời gian, bản đồ, chỗ nghỉ + dự phòng · Hiểu chuyến đi: hội thoại bên trái, panel "Mình đang hiểu" dính bên phải |
| Panel dính | Panel "Mình đang hiểu" và thanh "Đã chọn" không bị cuộn mất; trên desktop thanh "Đã chọn" là thanh dính dưới full width, **không** phải bottom sheet |
| Hover | Thẻ địa điểm hover hiện đủ thao tác (Thêm / Bỏ / Khóa / So sánh); dấu "chưa xác nhận", nhãn độ tin cậy và cỡ mẫu comment mở bằng hover tooltip **ngoài ra vẫn phải mở được bằng click** (mobile không có hover) |
| So sánh | 3 nơi cạnh nhau thoải mái, cột thuộc tính bên trái dính khi cuộn ngang |
| Thanh trên | Hai chế độ (§3): trong luồng là stepper, ngoài luồng là nav ngang. Không bao giờ hiện cả hai |
| Bàn phím | Tab đi đúng thứ tự đọc; `Enter` chọn; `Esc` đóng sheet; mũi tên đổi tab nhóm / tab ngày. Vẽ rõ **focus ring** — đây là bề mặt có bàn phím |
| Mật độ | Dày hơn mobile nhưng **không dày như Admin Web**: đây vẫn là sản phẩm người dùng, không phải phòng điều khiển |
| Chiều cao | Trang dài cuộn được là bình thường; đừng nhồi mọi thứ vào một màn 900px |

## 10. Cần giao gì

1. **Một Figma page cho mỗi trang ở §3** (10 page), đặt tên theo route: `04 — /app/shortlist`.
2. Trong mỗi page: các frame trạng thái liệt kê ở §4 ở khung 1440, mỗi frame có nhãn trạng thái + một dòng "khi hẹp lại: …".
3. **Một page thành phần** (§5) với variant đầy đủ.
4. **Một page nền tảng**: màu, chữ, khoảng cách, icon, bo góc, bóng.
5. Luồng chính nối bằng prototype: Bắt đầu → Hiểu chuyến đi → Gợi ý → Chi tiết → So sánh → Khả thi → Lịch trình → Chốt.
6. Ghi chú ngắn cạnh frame cho mỗi quyết định khác đặc tả này, kèm lý do.

Dùng **nội dung tiếng Việt thật** (tên địa điểm Đà Lạt thật, câu lý do thật như trong tài liệu này). Không lorem ipsum, không "Place Name 1".

## 11. Năm câu hỏi mở — designer trả lời bằng thiết kế

1. Thanh "Đã chọn" dính đáy trên desktop: đặt bao nhiêu thông tin là đủ mà không thành thanh trạng thái của Admin?
2. Đánh dấu sở thích "từ hồ sơ của bạn" thế nào để đọc như **suy đoán sửa được**, không phải cài đặt?
3. Cách nhẹ nhất để hiện xu hướng comment **kèm cỡ mẫu** trên một thẻ nhỏ?
4. Người dùng đi từ một xung đột đến cách sửa của nó trong **một bước** thế nào?
5. Panel "Mình đang hiểu" ở cột bên: làm sao thấy **nó vừa hiểu thêm** sau mỗi câu trả lời, mà không nhảy giật khi cuộn?
