# TripGuardian — Đặc tả UI/UX: User Web (bản người dùng dùng hằng ngày)

Dành cho designer / Figma. Tài liệu này trả lời **cần thiết kế mấy trang, mỗi trang phải có mục gì, mỗi trang có mấy trạng thái phải vẽ**. Bố cục từng màn và luồng chuyển màn: `docs/UI_SPEC_FLOW_LAYOUT.md`. Phong cách hình ảnh, chi tiết grid và vi tương tác: **designer toàn quyền**. Mục tiêu là giao diện đẹp trên máy tính. Web không có bản điện thoại: điện thoại mở bất kỳ trang nào cũng thấy trang tải ứng dụng (`docs/UI_SPEC_LANDING.md` §5); ứng dụng làm sau.

Đọc kèm:
- `docs/UX_Design_Brief.md` — thiết kế cho ai, nguyên tắc, cách hiển thị chất lượng dữ liệu (§4), hệ thị giác đang dùng (§7).
- `docs/Role_Web_Functional_Design.md` §2 — chức năng đầy đủ từng màn (nguồn sự thật về chức năng).
- Bản đang chạy: `web/src/user/` (React). Dùng để đối chiếu nội dung thật, **không phải để copy layout** — layout chính là phần cần designer làm lại cho đẹp.

---

## 1. Phạm vi

Chỉ **User Web** — phần người dùng mở hằng ngày, tất cả nằm dưới `/app`. Ngoài phạm vi: landing `/` (`docs/UI_SPEC_LANDING.md`), Admin Web `/admin`.

- **Chỉ làm máy tính (desktop 1440).** Bề mặt rộng đủ chỗ đặt cạnh nhau "lý do phù hợp", "đánh đổi" và bằng chứng. Cửa sổ máy tính hẹp vẫn phải dùng được (khối xếp chồng, không cuộn ngang), nhưng không thiết kế riêng cho điện thoại — điện thoại dùng ứng dụng (làm sau).
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

## 3. Bản đồ trang

| Route `/app/…` | Tên trang | Người dùng làm gì ở đây | Khung |
|---|---|---|---|
| `login` (hoặc `/app` lần đầu, chưa có tài khoản) | Vào ứng dụng | Dùng thử không cần tài khoản, hoặc đăng nhập | BARE |
| `` (gốc) | **Khám phá** | Gõ một câu / chủ đề (dán link, đính kèm file ở khung chat của Hiểu chuyến đi); người quay lại thấy chuyến đang lập | NAV |
| `understand` | Hiểu chuyến đi | Trả lời từng lượt hỏi của agent; soát và sửa vé | FLOW 1 |
| `explore` | **Chọn nơi** | Đọc tập nhỏ có lý do + đánh đổi; thêm / bỏ / khóa / so sánh; hỏi trợ lý; thanh "Đã chọn" báo khả thi và lịch ngầm | FLOW 2 |
| `explore/place/:id` | Chi tiết địa điểm | Thông tin thực tế ⟂ bằng chứng trải nghiệm; báo thông tin sai | FLOW 2 |
| `explore/compare/:ids` | So sánh | 2–3 nơi cạnh nhau, chỉ điểm khác nhau | FLOW 2 |
| `plan` | Lịch trình | Chọn hành trình, đọc từng ngày, chỗ nghỉ, dự phòng, Tối ưu, chốt | FLOW 3 |
| `done` | Phản hồi | Vài câu ngắn sau khi chốt | FLOW (3 bước xong) |
| `trips` | Chuyến của tôi | Đang lập · sắp tới · đã đi; đi tiếp hoặc mở lại lịch | NAV |
| `saved` | Đã lưu | Nơi đã thả tim; thêm vào chuyến khi nơi đó nằm trong gợi ý | NAV |
| `profile` | Hồ sơ | Tài khoản, sở thích của chuyến hiện tại, nguồn kết nối (sắp có) | NAV |

**Không có trang Khả thi riêng.** Khả thi được Decision kiểm sau mỗi thao tác và lịch được dựng ngầm; kết quả nằm trên thanh "Đã chọn" (§4).

**Khung — hai chế độ, không bao giờ hiện cả hai:**

```text
NAV   rail trái: logo · Khám phá · Chuyến của tôi · Đã lưu · Hồ sơ · avatar
FLOW  thanh trên: logo · stepper 3 bước (Hiểu chuyến đi → Chọn nơi → Lịch trình) · vé (ở bước 1) · avatar
```

Bước đã xong trên stepper bấm được để quay lại; hành trình trên máy chủ lùi theo (`back`), không bao giờ tiến hộ. Vé chuyến đi là một nút nhỏ mở popover, không phải panel cố định.

---

## 4. Từng trang: mục bắt buộc và trạng thái phải vẽ

### Vào ứng dụng (`/app/login`)

Nút **"Dùng thử, không cần tài khoản"** mạnh nhất. Email + mật khẩu (tài khoản hiện chỉ lưu trong trình duyệt); Google, Zalo, Facebook, Apple hiện `sắp có`. Chuyến đi không phụ thuộc tài khoản: máy chủ giữ theo mã hành trình.

### Khám phá (`/app`)

Hero ảnh Đà Lạt + **một ô nhập tự do** (Enter để bắt đầu; câu gõ thành lượt đầu của Hiểu chuyến đi) + chip gợi ý · ba thẻ chủ đề (*theo khu · theo thời tiết · theo giờ trong ngày*), mỗi thẻ là **một câu mở đầu**, không phải bài đọc.
- Người quay lại (đã có chuyến): thẻ **Chuyến đang lập** — ảnh nơi đã chọn, ngày, số nơi, tiến độ 3 đoạn, cảnh báo nếu còn chỗ cần chú ý, **Đi tiếp**; lối tắt *Theo gu quen thuộc / Lần này khác*; dải *Chuyến mới*.
- Không hỏi "đã đến Đà Lạt chưa"; không feed, không danh sách vô tận.

### Trang 3 — Hiểu chuyến đi (`/app/understand`) — trang khó nhất

Chốt 2026-10-04 sau 24 bản thử. Ảnh: `docs/design/desktop/v3-rose-photo/02-understand-k-ask.png`, `…-k-chain.png`, `…-k-expanded.png`. Các bản đã loại nằm ở `docs/design/desktop/_archive/understand-iterations/` — đọc trước khi đề xuất lại một hướng cũ.

#### Mở đầu: một cuộc trò chuyện, có khoảng dừng trước khi hỏi

Đổi 2026-10-08 (người dùng đi từ ô chat ở landing vào, phải thấy mình đang nói với AI). Câu mở (`frame`) **không phải thẻ hỏi** mà là **thẻ trò chuyện** cùng chỗ trong chồng thẻ (`web/src/user/screens/TripChat.tsx`):

1. **AI chào** bằng bong bóng trái (lời chào riêng của khung chat, không chép lại câu `frame`; thẻ hỏi **không bao giờ** hiện lại câu mở này). Trợ lý có avatar (`BotAvatar` trong `ui/icons.tsx`: cây thông của logo trên nền tròn màu pine; ảnh `public/img/gen/bot-avatar.webp` thay bản vẽ khi đã sinh bằng `web/scripts/gen_ui_images.py bot-avatar`) đứng cạnh tin nhắn của nó và ở đầu thẻ, "thở" nhẹ khi đang gõ. Lời chào là câu hỏi mở về chuyến đi người dùng mong muốn; ô nhắn như chatbot (`Nhắn cho TripGuardian…`), không có nút gợi ý hay dòng hướng dẫn. Nút kẹp giấy, kéo-thả hoặc dán từ clipboard để **đính kèm ảnh hoặc file**; tệp hiện trong ô nhắn trước khi gửi (ảnh có thumbnail, bỏ được bằng ×), ảnh hiện trong bong bóng sau khi gửi. File chữ (`.txt`, `.csv` Google Takeout, `.json` / `.geojson`, `.kml`) được đọc ngay trong trình duyệt (`web/src/user/tu/attach.ts`) thành từng dòng tên nơi hoặc link và gửi kèm; link Google Maps / TikTok dán thẳng vào ô. Mỗi dòng được khớp với dữ liệu, dòng không khớp giữ là "chưa tìm thấy", không đoán. Agent chưa đọc nội dung ảnh (chỉ biết có ảnh kèm). Câu đã gõ ở trang home **đã là tin nhắn đầu**, không hỏi lại.
2. **Lúc AI đọc**: bong bóng AI có chấm "đang gõ", lời đáp stream, và **những gì đang ghi** theo sự kiện `preview`: `“3 ngày” → Số ngày`. Đây là chỗ người dùng thấy hệ thống đang nghĩ gì.
3. **Khoảng dừng — `Mình đã hiểu như này`**: lời đáp của AI thành tin nhắn, dưới nó là thẻ tóm tắt: mỗi dòng đã hiểu kèm nguồn (`từ “…”` hoặc `mình đoán, sửa được`) và nút sửa (mở `Xem đầy đủ` đúng dòng đó); nơi muốn đến, giới hạn cứng bỏ được; sở thích mềm là chip có ×. Sau đó **`Mình cần hỏi thêm một số ý`** liệt kê `Còn chưa rõ` (lấy từ `unknowns`, là sự thật hiện tại, **không** phải danh sách câu sắp hỏi hay số câu — vẫn giữ §A).
4. Người dùng **sửa bằng lời** ngay trong ô chat, bao nhiêu lượt cũng được (mỗi lần gõ là một lượt mới, AI có thể hỏi lại ngay trong chat khi câu khó hiểu, tóm tắt cập nhật) hoặc bấm **`Đúng rồi, hỏi tiếp`**. Chỉ khi đó thẻ trò chuyện mới rơi xuống và thẻ câu hỏi ngắn đầu tiên được chia ra — **không bao giờ** là câu mở `frame` lần nữa, kể cả khi chat chưa ghi được gì (khi đó các câu ngắn hỏi từ đầu). Nếu agent đã đủ, nút là `Đúng rồi, bắt đầu tìm`.

Phiên đã có lịch sử câu trả lời thì vào thẳng chồng thẻ. Cột trái hiện `Trò chuyện · bạn kể, mình ghi` khi đang chat, sau đó là dòng `Bạn kể` đã xong. Màn này không chờ snapshot địa điểm (ảnh hiện khi snapshot tới; landing tải trước snapshot lúc rảnh).

#### Chuyển giữa các câu

Bấm trả lời là **thẻ rơi ngay** (380 ms), không chờ máy chủ; câu trả lời được gửi cùng lúc. Trong lúc chờ, hai thẻ nền nghiêng lên và hiện chấm chờ + lời AI đang stream (`Mình đang ghi lại câu trả lời…`). Thẻ mới về sớm hơn 380 ms thì chờ thẻ cũ rơi xong rồi mới được chia. Gõ tự do trong thẻ cũng đi theo đường này. Không có câu hỏi mới (lỗi, hoặc agent hỏi lại đúng câu đó) thì thẻ cũ được chia lại. Thẻ mới mà đầu thẻ nằm khuất trên màn thì trang cuộn về đầu chồng thẻ. `prefers-reduced-motion` tắt hết, đổi thẻ tức thì.

**Chọn một hay chọn nhiều** luôn nói trước khi bấm: dòng nhỏ trên các lựa chọn (`Chọn một ý` · `Chọn một hoặc nhiều ý, xong bấm “Xong câu này”` · `Mỗi dòng chọn một ý…`), và dấu trên từng lựa chọn: tròn = chọn một (bấm là gửi), vuông = chọn nhiều. Câu nhiều dòng ghi `chọn một` / `chọn nhiều` cạnh tên dòng.

Hai cột: **trái là cuộc hỏi, phải là vé**. Sau phần mở đầu, các thẻ câu hỏi không có bong bóng chat hay avatar. Lượt đã trả lời **co thành một dòng** kèm chip đáp án và nút `Sửa`.

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
2. **Hậu cần** (sau phần trò chuyện, trước "Bắt đầu tìm"; `docs/TRIP_UNDERSTANDING.md` §Hậu cần): *Bạn khởi hành từ đâu?* (ô gõ có gợi ý như Google Maps, mỗi dòng: icon · tên · địa chỉ) → *Bạn tới Đà Lạt bằng gì?* (Tự đi · Xe khách · Máy bay) → với xe khách / máy bay: danh sách chuyến đi rồi chuyến về (hãng, giờ đi → đến, điểm đón / trả, giá + *"giá tham khảo lúc HH:mm dd/mm, kiểm lại khi đặt"*, lọc Sáng · Chiều · Đêm · Rẻ nhất, *Chọn chuyến này*, cuối danh sách *Tôi tự lo phần này*; đang tra → skeleton; không tra được → nút mở Google Flights / Vexere đã điền sẵn + ô nhập giờ) → *Cho mình biết nơi bạn sẽ lưu trú ở Đà Lạt nhé.* (ô tìm là phần chính: chỗ ở trong dữ liệu trước, rồi địa chỉ; chip *Chưa có, gợi ý giúp mình*; *Bỏ qua*). Không có kết quả → *"Không thấy nơi này. Thử gõ địa chỉ hoặc tên đường."* Chuyến và giá chỉ từ trang đặt vé, không bao giờ do hệ thống tự viết.
3. **Nhãn "từ hồ sơ của bạn"** trên mọi thứ suy ra từ lịch sử, sửa được bằng một chạm, đọc như suy đoán chứ không như cài đặt.

Frame: (1) một lượt · (2) nhiều lượt · (3) `Xem đầy đủ` có dòng kết luận đã mở · (4) nhập địa điểm, ba trạng thái cùng khung · (5) vé khi chưa có sở thích nào.

### Chọn nơi (`/app/explore`)

Tiêu đề: *"Gợi ý cho chuyến của bạn"*, dưới là *"N nơi hợp với chuyến của bạn, xếp từ hợp nhất. Chat để thu hẹp"*; số này đổi sau một lượt chat thì hiện "−12 nơi" / "+5 nơi" ngay cạnh.

Mục bắt buộc:
1. **Nơi bắt buộc đến** (nhóm `anchors` của Decision) lên trên cùng.
2. **Tab nhóm** theo nhóm của Decision, mỗi tab có tổng số nơi của nhóm (`total`); mũi tên trái / phải đổi tab. Nhóm khác vừa đổi sau một lượt lọc lại thì tab hiện "+N mới" tới khi mở. Lưới tự tải thêm khi cuộn gần cuối (3 thẻ khung), hết thì một dòng "Đã xem hết N nơi ở nhóm này". Chỗ ở **không** nằm trong danh sách.
3. **Thẻ địa điểm**: ảnh thật (ghi nguồn) · nhãn "Hợp nhất" cho nơi `top` · tên · loại · khu · *Vì sao phù hợp* (≤3 ✓) · *Đánh đổi* (hổ phách, ngay dưới) · thời gian (khoảng) · giá hoặc "Chưa có giá" · khoảng cách ước tính · độ tin cậy · `Thêm · Khóa · So sánh · Bỏ` + trái tim lưu. Hàng thao tác phụ hiện rõ hơn khi hover/focus nhưng luôn bấm được.
4. **Cách xem Đĩa xoay**: nửa đĩa ở mép trái, các nơi là cánh quạt hình mảnh vành khuyên (cạnh trong, cạnh ngoài cong theo cùng một vòng tròn, khe đều 8px) khép thành một vòng liền trên 180°; nơi đang xem nằm ngang ở giữa, viền xanh. Đĩa là vòng lặp, không có điểm đầu. Tối đa 7 cánh (3 trên, 1 giữa, 3 dưới) để ảnh trên cánh to và rõ; ít nơi hơn thì góc mỗi cánh = 180° / số nơi (tối đa 45°). Lăn chuột hay kéo trên đĩa thì xoay đĩa; phần còn lại cuộn như trang, không cắt chữ, đĩa nằm trên thanh "Đã chọn". Nhóm nơi là hàng tab có chữ và số ở đầu cột nội dung; không có hàng "Nơi trước / Nơi sau". ↑ ↓ đổi nơi, ← → xem ảnh; cùng thao tác như thẻ. Màn hẹp (≤ 900px): đĩa thành dải cánh cuộn ngang.
5. **Cặp nơi giống nhau** (từ `alternatives`) kèm **So sánh**; **câu hỏi làm hẹp** (`pending`) chen trong lưới, một câu, bỏ qua được.
6. **Giới hạn đã loại N nơi** — mở ra theo từng giới hạn, `Nới giới hạn` đưa về Hiểu chuyến đi.
7. **Chưa xác minh được điều kiện của bạn** gập lại.
8. **Trợ lý "Hỏi TripGuardian"**: tab nhỏ mép phải (phím `/`), mở thành ngăn 380px không phủ mờ, ghim được (lưới còn 2 cột). Gõ tự do đi qua lượt chat của Decision; thay đổi hiện ngay trên lưới và thanh "Đã chọn", kèm chip tối đa 6 nơi mới vào và hoàn tác (không có hoàn tác cho lần lọc lại theo mong muốn: câu trả lời kết bằng "Giữ N nơi, thay M nơi hợp hơn"). *"Vì sao không gợi ý X?"* được trả lời từ dữ liệu (`why-not`), không qua agent. Không tự mở; chỉ hiện một chấm + dòng gợi ý tắt được.

Trạng thái: bình thường · quá ít kết quả · mọi nơi bị giới hạn loại (rỗng) · sheet lý do bỏ (*Quá xa / Quá đông / Quá đắt / Không thích / Đã đi rồi*, không bắt buộc) · nút nổi "So sánh N nơi" · đang tải (khung xương) · lỗi tải (thử lại).
Frame: 5.

### Chi tiết địa điểm (`/app/explore/place/:id`)

Nguyên tắc: **mọi nhận định cách bằng chứng một chạm**.

Mục bắt buộc:
1. **Thông tin thực tế** — giờ, giá, đặt chỗ: giá trị + nguồn (chính thức / Google) + ngày kiểm tra. Xung đột thì hiện **cả hai giá trị**, đánh dấu chưa xác nhận.
2. **Trải nghiệm** — mỗi nhận định mở ra bằng chứng: clip TikTok phát **đúng đoạn**, và xu hướng comment kèm **cỡ mẫu**: *"62% trong 123 comment về độ đông, từ 30 creator"*, cùng 2–3 comment gốc có link về video.
3. **Mức vận động** — đi bộ, dốc, đường vào.
4. **Hợp với ai** — cặp đôi, trẻ em, người lớn tuổi.
5. **Bản đồ Google** khi dữ liệu đến từ Google.
6. Nút **Báo thông tin sai** — nhẹ, không phải nút chính; gửi `POST /api/harness/reports` kèm mã ẩn danh của trình duyệt. Chỉ khi đủ nhiều người khác nhau cùng báo một điều thì corpus mới đổi (`docs/CORPUS.md`).
7. Thao tác dính dưới: Thêm vào danh sách chọn · Bỏ · Khóa.

Thông tin thực tế và bằng chứng trải nghiệm **phải tách rõ về mặt hình ảnh** — hai loại sự thật khác nhau.

Frame: (1) trang chi tiết · (2) bằng chứng mở (clip + comment) · (3) có xung đột giá trị + báo sai.

### So sánh (`/app/explore/compare/:ids`)

Mục: 2 (tối đa 3) nơi cạnh nhau; **chỉ hiện thuộc tính khác nhau** (trải nghiệm, di chuyển, độ đông, chi phí, thời điểm đẹp nhất) · một câu hỏi chốt (*"Ưu tiên ít di chuyển hay chỗ yên tĩnh hơn?"*) · chọn xong cập nhật chuyến đi ngay, hệ thống không chọn thay.

Frame: (1) 2 nơi · (2) 3 nơi.

### Thanh "Đã chọn" (dính đáy Chọn nơi, Chi tiết, So sánh) — thay trang Khả thi

Luôn hiện: số nơi · tổng giờ tham quan · di chuyển ước tính · chi phí (khi lịch ngầm có) · nút **Xem lịch trình →**. Mỗi thay đổi hiện **dòng chênh lệch** (*"+1 nơi, +90 phút tham quan, +24 phút đi lại"*) kèm **Hoàn tác**; không chặn thao tác.

Bốn trạng thái:

| Trạng thái | Nguồn | Hiện |
|---|---|---|
| **Đang xếp lịch** | lịch ngầm đang dựng (`preview`, debounce 350 ms) | khung xương mảnh |
| **Lịch N ngày sẵn sàng** | `preview` = `ready` | số liệu của phương án ít di chuyển nhất |
| **Cần chú ý** | Decision `partial`, hoặc `preview` = `failed` | dải hổ phách nổi lên: mỗi xung đột = *tên nơi + quy tắc + các cách sửa*, mỗi cách sửa một hàng bấm được kèm cái giá; nút Xem lịch trình khóa đến khi sửa |
| **Chưa đi được** | Decision `infeasible` | dải mận đậm mở sẵn: *"Cần ~X, chuyến đi có Y"* + cách sửa; vẫn chọn tiếp được |

Xung đột với giới hạn người dùng có hàng *nới* đưa về vé chuyến; xung đột vật lý **không** có hàng nới. Cuối danh sách: *"Để dành cho dịp khác"*. Bấm thân thanh mở danh sách đã chọn (khóa / bỏ từng nơi, cảnh báo cần kiểm tra trước khi đi). Thông báo là vùng `aria-live="polite"`.

### Lịch trình (`/app/plan`)

Mục bắt buộc:
1. **Tab phương án** + **bảng đánh đổi** giữa các phương án (mỗi phương án tối ưu một mục tiêu khác: ít di chuyển / nhiều trải nghiệm / rẻ hơn…), có cột chi phí (*"Một phần chưa có giá"* khi thiếu).
2. **Tab ngày** (Ngày 1, Ngày 2… kèm thứ + ngày).
3. **Dòng thời gian một ngày**: giờ đến, thời gian ở lại, di chuyển giữa các điểm, cùng các khối *Ăn (tự chọn) · Nghỉ · Chờ · Đệm*. **Cảnh báo nằm tại đúng điểm dừng**, không dồn xuống cuối.
4. **Bản đồ lộ trình** (Google) + tổng di chuyển ước tính của ngày.
5. **Panel chỗ nghỉ đêm** — chỗ ở đã đặt, hoặc các chỗ ở gợi ý, giá/đêm nếu có, đổi được; đổi thì giờ di chuyển tính lại.
6. **Nhãn độ vững mỗi ngày**: Vững / Khả thi / Mong manh + lý do một câu.
7. **Phương án dự phòng** gắn với điểm nhạy cảm: *"Nếu mưa: A → B trong nhà"*, *"Bị trễ: bỏ C trước"* — chỉ thay khi người dùng chọn.
8. **Không có ô nhắn** — màn này chỉ nhận thao tác (chọn phương án, đổi chỗ nghỉ, dùng dự phòng, `+ Thêm nơi`); mỗi thao tác kèm dòng báo đã làm gì (*"Đã xếp lại một vài ngày bị ảnh hưởng"*).
9. Thông tin chưa xác nhận vẫn đánh dấu tại chỗ: *"Giờ mở cửa chưa xác nhận — kiểm tra trước khi đi"*.
10. **Hai cách xem**: *Theo giờ* (tab ngày + timeline + bản đồ Google + cột bên) và *Hành trình* (sơ đồ thẻ ảnh theo thứ tự đi, từng ngày hoặc cả chuyến).
11. **Tối ưu**: khi vào Lịch trình, Planning Agent đề xuất một lần (`recommend`); máy chủ chỉ giữ đề xuất qua kiểm tra tất định và không kém lịch cũ (`docs/PLANNING.md`). Có cải thiện thì hiện biểu ngữ *"Mình đã tìm được cách xếp tốt hơn"*; ngăn Tối ưu cho xem trước → sau (phút di chuyển), *Vì sao*, dòng *"Mình không đổi chỗ ở, nhịp độ, nơi đã khóa"*, **Giữ lịch cũ** (= hoàn tác) · **Giữ cách xếp mới**. Không tốt hơn / bị chặn thì nói rõ và giữ lịch.
12. Thanh đáy: dòng báo đã làm gì + **Hoàn tác** · **Chốt kế hoạch này**. `+ Thêm nơi` quay về Chọn nơi (hành trình lùi về `decision`, giữ lựa chọn).

Luôn ghi rõ: *"Giờ giấc và đường đi là ước tính."*

Trạng thái: **"Bạn ở đâu?"** (một lần, trước lịch, khi người dùng chọn *Chưa có, gợi ý giúp mình*: thẻ chỗ ở có ảnh, tên, điểm, giá/đêm hoặc *"chưa có giá"*, *"Hợp vì: yên tĩnh (6 đánh giá nhắc) · …"*, số phút trung bình tới các nơi đã chọn; thẻ đầu *"Hợp gu bạn nhất"* khi có bằng chứng gu, chỗ ở chỉ có thẻ live ghi *"Chưa đủ dữ liệu để so gu"*; bấm ảnh mở `PlaceSheet`; *Ở đây* · *Tôi ở chỗ khác* · *Cứ xếp giúp* · *Bỏ qua*) · chọn hành trình (thẻ ảnh lớn, hover xem trước theo ngày + bảng đánh đổi; chỉ hiện khi có ≥2 phương án và chưa chọn) · lịch một ngày · chỗ nghỉ đang tra · "Chưa xếp được lịch" (có lối quay lại) · sau một thao tác · ngăn Tối ưu (tốt hơn / không / bị chặn).

### Chuyến của tôi (`/app/trips`)

Các hành trình trình duyệt này đã bắt đầu (`GET /api/harness/trips`): ảnh bìa (nơi đã chọn đầu tiên), ngày, số người, số nơi, trạng thái *Đang lập · Đã chốt · Đã đi* (đã chốt và ngày cuối đã qua), tiến độ 3 đoạn cho chuyến đang lập. Đang lập → **Đi tiếp** (đúng bước); đã chốt → **Xem lịch** / **Sửa lại**; đã đi → **Xem lại lịch** / **Phản hồi**. *Ẩn khỏi danh sách* chỉ xóa khỏi trình duyệt. Rỗng dẫn về Khám phá.

### Đã lưu (`/app/saved`)

Nơi đã thả tim, lưu trong trình duyệt; lọc theo nhóm. Nơi đã lưu **không tự vào lịch**: *Thêm vào chuyến* chỉ bật khi nơi đó nằm trong gợi ý của chuyến hiện tại.

### Hồ sơ (`/app/profile`)

Tài khoản (hoặc "đang dùng thử") · **Sở thích của chuyến hiện tại** kèm nguồn (*từ lời bạn / từ hồ sơ*), sửa ở vé · nguồn kết nối TikTok / Google `sắp có` · chuyến đang lập. Ghi rõ: hồ sơ dài hạn gắn với tài khoản (sắp có); tín hiệu sức khỏe chỉ dùng trong phiên.

### Phản hồi (`/app/done`)

Tiêu đề *"Kế hoạch đã chốt."* → *"Cảm ơn bạn."* · bốn thang 1–5 (đúng gu, lý do dễ hiểu, lịch thực tế, tự tin hơn) · *còn phải tìm chỗ khác?* · góp ý · bỏ qua được. Gửi `POST /api/harness/sessions/<id>/feedback`.

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
| Stepper 3 bước | bước hiện tại · đã xong (bấm để quay lại) · chưa tới |
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

## 8. Hệ thị giác — nền giấy, Thông / Nắng

Hướng **editorial dẫn bằng ảnh thật**, nền sáng. Màu và khoảng cách là biến CSS trong `web/src/user/css/tokens.css`; component không hard-code màu.

| Vai trò | Giá trị | Tương phản |
|---|---|---|
| Nền / bề mặt / hairline | `#FAF7F2` / `#FFFFFF` / `#E7E1D6` | — |
| Mực / mực phụ / chú thích | `#1B2A2F` / `#4A5A60` / `#6B787D` | 13,9 · 6,7 · 4,56 |
| **Thông** (nút chính, tab chọn, tuyến, focus) | `#0F5F5A`, nhạt `#E3F1EE` | chữ trắng 7,5 |
| **Nắng** (ghim, trái tim, tiến độ — nét, không chữ nhỏ) | `#E8590C`; chữ `#B8420A` | nét 3,6 · chữ 5,5 |
| Hổ phách (đánh đổi, cảnh báo) | chữ `#8A5A00` trên `#FFF4DC` | 5,4 |
| Nguy hiểm | `#B42318` | 6,6 |

- Chữ: tiêu đề **Playfair Display**, nội dung **Inter**, số / giờ / giá / cỡ mẫu **JetBrains Mono**. Nội dung ≥16px, chú thích ≥12px.
- Bo 16–20px, bóng rất nhẹ, icon SVG nét mảnh tự vẽ (`user/ui/icons.tsx`), không emoji. Cảnh báo / đánh đổi luôn có icon và chữ, không chỉ dựa vào màu.
- Ảnh bìa và gallery (≤ 12 ảnh, tab Hình ảnh của `PlaceSheet`) là **ảnh thật của chính nơi đó** (Google Maps hoặc frame clip, chọn offline bằng `web/scripts/pick_covers.py`: không người chiếm khung, bỏ ảnh gần trùng, Gemma xếp ảnh đẹp và thể hiện đúng nơi lên trước), luôn ghi nguồn. Ảnh sinh (`web/scripts/gen_ui_images.py`, `web/public/img/gen/`) chỉ dùng cho không khí và minh họa (hero, bìa hành trình), không bao giờ làm ảnh của một nơi có tên, không ghi nhãn trên giao diện; nguồn gốc nằm trong `manifest.json`.
- Chuyển cảnh: sang bước mờ + dịch 24px 280ms · chờ máy dùng khung xương và chữ nói đúng việc đang làm (không % giả) · lớp phủ 240ms · cập nhật tại chỗ nháy nền nhạt 600ms. `prefers-reduced-motion` tắt hết.

## 9. Khung và kích thước

| Bề mặt | Khung | Vòng này |
|---|---|---|
| **Desktop** | **1440 × cao tùy trang** (thiết kế chính) | Nội dung trong cột tối đa 1280, lề 80; grid 12 cột, gutter 24 |
| Laptop nhỏ | 1280 | Suy ra: rớt từ 3 cột xuống 2 |
| Điện thoại | — | Không có bản web: trang tải ứng dụng (`docs/UI_SPEC_LANDING.md` §5) |

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

1. **Một Figma page cho mỗi trang ở §3** (11 page), đặt tên theo route: `explore — /app/explore`.
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
