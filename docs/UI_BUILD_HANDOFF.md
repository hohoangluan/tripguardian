# TripGuardian — Bàn giao: dựng lại giao diện User Web + Landing

Viết cho người (hoặc session) **bắt đầu code**. Tài liệu này nói **việc gì cần làm, theo thứ tự nào, chạm vào file nào, và cái gì đã chốt rồi đừng mở lại**.

Chốt ngày 2026-10-04. Mọi quyết định dưới đây đã qua duyệt, kèm ảnh dựng thử để đối chiếu.

---

## 0. Đọc trước khi gõ dòng code đầu tiên

| Tài liệu | Nói gì |
|---|---|
| `docs/UI_SPEC_USER_WEB.md` | 12 trang của app: mục bắt buộc, trạng thái, hệ màu (§8), những thứ chỉ desktop mới có (§9.1) |
| `docs/UI_SPEC_LANDING.md` | Landing: nhuộm lại 3D, ngân sách chữ, 7 màn cuộn, quy tắc animation |
| `docs/UX_Design_Brief.md` | Nguyên tắc sản phẩm và cách hiển thị chất lượng dữ liệu (§4) — **phần này không đổi và không được vi phạm** |
| `docs/Role_Web_Functional_Design.md` §2 | Chức năng từng màn (nguồn sự thật về chức năng) |
| `docs/design/desktop/v3-rose-photo/README.md` | 20 ảnh dựng thử đã chốt, map sang route, và **danh sách lỗi có sẵn trong ảnh — đừng chép theo** |

Ảnh trong `docs/design/desktop/v3-rose-photo/` là **bản dựng ý tưởng**, không phải asset: ảnh do model vẽ lại gần giống frame gốc. Dùng để đối chiếu bố cục, mật độ chữ, màu — không cắt ra dùng.

Các hướng **đã thử và loại** nằm ở `docs/design/desktop/_archive/`. Trước khi đề xuất lại một hướng, xem nó có nằm trong đó không.

---

## 1. Hệ thị giác — đổi toàn bộ sang trắng hồng

Đây là việc đầu tiên vì mọi thứ khác ăn theo nó.

Hồng chính đã dịu lại (2026-10-04): `#E4607F` gắt và điệu, thay bằng hồng phấn `#EFB8C4` **chữ mận** trên nút; hồng đậm `#C97890` chỉ cho nét/pin/viền.

| Vai trò | Giá trị |
|---|---|
| Nền trang | `#FFF9F8` |
| Bề mặt | `#FFFFFF` |
| Mực | `#3A2B32` (phụ `#5E4A54`, mờ `#7D6873`) |
| Hồng phấn (chính) | `#EFB8C4` — nút chính, tab/chip đang chọn, thanh tỉ lệ; chữ trên nó là mận (5.5:1) |
| Hồng đậm | `#C97890` — pin đã chọn, tuyến, viền thẻ đã chọn, focus ring (3.2:1, chỉ nét không chữ) |
| Hồng nhạt | `#FCEEF1` — khối mềm, bằng chứng trải nghiệm |
| Đường kẻ | `#F3E1E4` / `#E8CDD3` |
| Mận | `#6B3550` — khối quy tắc cứng, thanh dính đáy, footer; chữ trắng (9.3:1) |
| Hổ phách | `#A8660F` (chữ `#9A5D0E` trên `#FBF0DF`) — **chỉ** cảnh báo và đánh đổi |
| Xanh mực | `#4A6488` — link, dòng nguồn dữ liệu |
| Dã quỳ `#F2B31B` | **Một chỗ duy nhất trong toàn sản phẩm**: đĩa mặt trời trong 3D của landing |

Quy tắc: chữ trắng **chỉ** trên nền mận / hổ phách (hồng phấn quá nhạt cho chữ trắng → dùng chữ mận); **không bao giờ** chữ hồng trên nền trắng. Minh hoạ là **nét mảnh** tô hồng phấn, không gradient tràn, không emoji.

**Việc cần làm:**
- [x] `web/src/styles.css` §`:root` — giữ nguyên **tên** token, đổi giá trị sang bảng trên. Đổi tên token sẽ làm vỡ landing.
- [x] `web/src/user/user.css` — restyle theo hệ mới. Ảnh poster/empty còn tông xanh–vàng: tạm nhuộm bằng CSS `filter`, **cần vẽ lại** nét mảnh hồng.
- [x] Rà lại tương phản: chữ thường ≥ 4.5:1, chữ ≥24px ≥ 3:1. Hồng trên trắng **trượt** ngưỡng, nên hồng chỉ dùng cho nền nút và đường kẻ, không cho chữ nhỏ.
- [x] Admin Web **không đổi** — vẫn hệ cũ.

## 2. Thế giới 3D của landing — nhuộm lại, không dựng lại

Hình học, camera, GSAP ScrollTrigger, Lenis, 5 beat dính: **giữ nguyên 100%**. Chỉ đổi màu, khoảng 20 giá trị.

- [x] `web/src/scene/Terrain.tsx` — 5 dải cao độ: bờ `#E8CFC6` · đồng `#DCB6AE` · sườn `#B98C92` · rừng sâu `#7E5A68` · đỉnh sương `#C9A7AE`; mặt hồ `#F3DDE0` (giữ `metalness 0.25`)
- [x] `web/src/scene/Pines.tsx` — `setHSL(0.42±.05, .28–.40, .13–.20)` → `setHSL(0.93±.03, .10–.22, .22–.32)`. **Một dòng.**
- [x] `web/src/scene/Director.tsx` — `MIST #F6E7E6`, `CLEAR #FDF3F1`; hemisphere `#FFF9F8`/`#6B3550`; nắng `#FFD9CE`; **thêm một đĩa mặt trời `#F2B31B`**
- [x] `web/src/scene/Mist.tsx` — `#FCEDEC`
- [x] `web/src/scene/Pins.tsx` — pin thường `#A98E95` · pin đã chọn `#C97890` · nhãn `#FFFFFF`
- [x] `web/src/scene/Route.tsx` — tuyến `#C97890`, đoạn lỗi `#B06A12`
- [x] Giữ **scrim trắng mềm** sau mọi chữ nằm trên 3D — palette hồng tương phản thấp hơn xanh–vàng cũ.
- [x] Mobile **không chạy 3D**: thay bằng ảnh render sẵn của chính cảnh đó.

## 3. Landing — cắt chữ, để animation kể

Chi tiết ở `docs/UI_SPEC_LANDING.md`. Tóm tắt việc:

- [x] **Ngân sách chữ mỗi màn cuộn**: 1 nhãn ≤4 từ + 1 tiêu đề ≤6 từ + tối đa 1 dòng phụ ≤16 từ. Cắt hết đoạn mô tả dài và hai chú thích hai bên ở mỗi beat hiện tại.
- [x] Cấu trúc 7 màn: Hero → `842 → 5` → Hiểu chuyến đi → Bằng chứng → Khả thi → Lịch trình → Ảnh thật → CTA, rồi Hỏi nhanh + SẮP CÓ + footer.
- [x] Hai beat mới: **`842 → 5`** (pin sáng dồn rồi tắt còn 5) và **ảnh thật** (mosaic 6 nơi, màu gốc, tràn hai mép, mỗi ô ghi tên nơi + `@creator`).
- [x] Khối **SẮP CÓ** trước CTA cuối: *Khám phá Đà Lạt · Nhật ký chuyến đi · Thêm thành phố*, đều gắn `chưa mở`.
- [x] `prefers-reduced-motion: reduce` → tắt scrub, tắt sương, tắt bay chip; mỗi beat về **một ảnh tĩnh ở trạng thái cuối** và vẫn hiểu trọn. **Bắt buộc, không phải tuỳ chọn.**
- [x] Số trên landing lấy từ build thật (`web/public/data/snapshot.json`). Không có số đối chứng thì **bỏ ô đó**, không điền số đẹp.
- [x] **Quay lại video demo** bằng `web/scripts/record_demo.mjs` sau khi app đã restyle — `web/public/media/demo.mp4` hiện mang màu kem/xanh thông, để nguyên thì landing hồng kẹp video xanh.

## 4. `/app/understand` — làm lại theo mô hình ý định

Trang khó nhất, và là trang đã tốn 24 bản thử. Đặc tả đầy đủ: `docs/UI_SPEC_USER_WEB.md` §4 Trang 3. Ba điều dễ làm sai nhất:

- [x] **Giao diện không được đoán thay agent.** Ý định, số câu mỗi ý định, thứ tự ý định đều do agent quyết lúc chạy → **không** `câu 2/3`, **không** thanh chia đoạn, **không** câu kế tiếp dạng chữ ma, **không** `4/8 ý định`, **không** danh sách ý định sắp hỏi.
- [x] **Một ý định = một dòng vé**, không phải một dòng mỗi câu hỏi. Chuỗi nhiều câu gói trong một thẻ bên trái, trả lời xong **gộp thành một dòng**.
- [x] **Dấu `—` chỉ có một nghĩa**: chỗ này chưa có gì. Dòng đã ghi thì nhãn trái, giá trị phải, không gạch ngang.

Thêm:
- [x] Hai chế độ hỏi: một lượt (không thẻ bao) và nhiều lượt (cả chuỗi trong một thẻ).
- [x] `Vì sao hỏi` là **dòng nhỏ dưới câu hỏi**, không phải thẻ riêng.
- [x] `Xem đầy đủ`: panel 55%, cột hỏi 42% **vẫn dùng được**, **panel cuộn dọc** — không thu nhỏ chữ để nhét vừa màn; header dính trên, chân dính dưới.
- [x] Dòng kết luận mở ra được để xem chuỗi câu đã hỏi, mỗi câu con có `Sửa` riêng.
- [x] Khoảng trống nửa dưới cột trái **giữ nguyên** — chỗ cho lượt tới mọc xuống, không lấp bằng trang trí.

## 5. Các màn còn lại của app

Theo đúng ảnh chốt trong `v3-rose-photo/`, giữ chức năng cũ, chỉ đổi hệ thị giác và các điểm ghi trong spec:

- [x] `01-shortlist` · `03-place` · `08-compare` · `04-feasibility` · `05-plan` · `09-profile` · `10-feedback` · `06-auth` · `07-start`
- [x] **Trang chủ `/app` mới** (`14-home`) — chỉ cho người quay lại; người lần đầu vào thẳng 2 câu hỏi. Bốn ô: *Chuyến đang lập · Nơi đã lưu + Chuyến đã đi · Khám phá Đà Lạt (`sắp mở`) · Chuyến mới*. Ràng buộc chống biến thành feed: không danh sách vô tận, mỗi thẻ dẫn tới **một quyết định**, blog/khám phá **không chen vào** 4 bước.
- [x] **Top bar hai chế độ**: trong luồng = stepper 4 bước; ngoài luồng = nav ngang *Trang chủ · Chuyến đi · Khám phá · Hồ sơ*. Không bao giờ hiện cả hai.
- [x] **Chi tiết địa điểm phải dùng bản đồ Google thật** — ràng buộc cứng, không vẽ bản đồ tay như trong ảnh dựng thử.

## 6. Thứ tự làm

```
1. Token màu (styles.css + user.css)        ← mọi thứ ăn theo
2. Thành phần dùng chung (spec §5)           ← thẻ địa điểm, nhãn tin cậy, chip cứng/mềm, vé
3. /app/understand                           ← trang khó nhất, làm sớm để lộ vấn đề sớm
4. Các màn app còn lại
5. Trang chủ /app + top bar hai chế độ
6. Nhuộm 3D + landing
7. Quay lại video demo
```

Lý do để `/app/understand` lên trước các màn khác: nó dùng gần hết bộ thành phần chung (chip cứng/mềm, nhãn nguồn, nhãn tin cậy, vé, trạng thái rỗng). Làm xong nó thì các màn sau chủ yếu là lắp ghép.

## 6b. Đã làm (2026-10-04) — và chỗ lệch so với đặc tả

Cả 7 bước ở §6 đã có trong code. Ảnh chụp kiểm tra ở `web/shots/` (gitignore), quay lại bằng `web/shots/walk.mjs` và `web/shots/land.mjs`.

| Chỗ | Lệch thế nào | Vì sao |
|---|---|---|
| Ảnh bìa địa điểm | Lấy cả **ảnh Google Maps** của chính nơi đó, không chỉ frame clip; **loại ảnh có người** chiếm > 1,5% khung | Frame clip hay là mặt/chân người; ảnh Maps chụp đúng chỗ, nét hơn. Chọn offline bằng `web/scripts/pick_covers.py` (YOLO) → `web/public/data/covers.json`; ảnh thật vẫn giữ màu gốc, luôn ghi nguồn |
| Dải poster sau tiêu đề | Bỏ hẳn; minh hoạ thay bằng nét mảnh SVG (`web/src/ui/LineArt.tsx`) | Ảnh chốt không có poster; poster cũ là tranh xanh thông |
| Trang Bắt đầu | Có ô nhập tự do + 4 thẻ lớn; **chưa có** thẻ chip 4 thông tin chặn | Câu hỏi đầu của trang Hiểu chuyến đi đã hỏi đúng 4 thông tin đó; làm hai nơi thì hỏi trùng |
| Hiểu chuyến đi — ý định | Nhãn ý định suy từ `group`/`qid` của câu hỏi; chuỗi nhiều lượt = các lượt liền nhau cùng ý định | API chưa trả ý định riêng |
| Hiểu chuyến đi — `Sửa` ở câu con | Mở dòng kết luận tương ứng để sửa giá trị, không hỏi lại câu đó | API chưa có "trả lời lại một câu" |
| Hiểu chuyến đi — số nơi đang hợp | API trả thêm `matching` / `total` (`src/trip/understanding.py`): số nơi qua giới hạn cứng **hiện tại** | Spec cần con số thật, không dự đoán |
| Nhãn độ vững | Theo phương án, không theo từng ngày | Planning chỉ trả độ vững cho cả phương án; tab ngày hiện thời gian đi |
| So sánh 3 nơi | Ghép 2 lần so sánh cặp (nơi 1–2, 1–3) | API so sánh theo cặp |
| Landing | 3D: hero + 5 beat + CTA (7 điểm dừng camera); sau đó giấy trắng: mosaic ảnh thật → demo → Hỏi nhanh → SẮP CÓ → CTA → footer. Bỏ sa bàn mini và phim thương hiệu 37 s cũ | Đúng cấu trúc §3; hai phần bỏ không có trong spec và mang màu cũ |
| Beat khả thi, lịch trình trên landing | Dùng 5 nơi minh hoạ của cảnh 3D, có ghi "Ví dụ minh hoạ" | Cảnh 3D là sân khấu dựng, không phải toạ độ thật; beat 842 → 5 và beat bằng chứng dùng số thật từ snapshot |
| Đường dẫn pin số 2 → dòng số 2 (beat lịch trình) | Nối tới mép trái thẻ, ngang dòng số 2 (không chui vào trong thẻ) | Toạ độ pin chiếu từ cảnh 3D mỗi khung hình (`story.pins`) |

**Vấn đề phía backend thấy khi kiểm, đã sửa sau đó (2026-10-04):** bộ xếp lịch từ chối phần lớn tổ hợp nơi (ghim giờ lấy giao, thời lượng cứng, quán ăn ép khung trưa, "gần trùng" bị coi là lỗi): giờ 39/40 bộ 4 nơi ngẫu nhiên xếp được (trước 22/40), xem `docs/PLANNING.md`. Tra chỗ ở hỏng do Maps đổi URL danh sách khách sạn và cách ghi giá ("335 N", "1,59 Tr"): đã sửa. Còn một ca biên: hai quán chỉ mở chiều tối cùng tranh bữa tối trong một ngày.

## 7. Chưa quyết — cần chốt trước khi làm tới

- **Mobile 390**: chưa thiết kế. Mỗi frame desktop cần một dòng *"khi hẹp lại: …"*, nhưng bản vẽ mobile là vòng sau.
- **Sáng/tối**: chưa làm. Nếu làm thì làm đủ, không nửa vời.
- **Khám phá Đà Lạt**: mới có chỗ cắm và nhãn `sắp mở`, chưa có nội dung và chưa có luồng.
- **`19-beat-evidence`**: con số `74% trong 96 comment · 24 creator` trong ảnh là **mẫu**; khi làm thật phải lấy từ corpus và ảnh clip phải đúng nơi đang nói.

## 8. Những gì KHÔNG được đổi khi restyle

- Mọi nguyên tắc ở `docs/UX_Design_Brief.md` §3 và cách hiển thị dữ liệu ở §4 — fact / signal / estimate / độ tin cậy / "Chưa có thông tin".
- Thông tin thực tế và bằng chứng trải nghiệm **tách rõ về mặt hình ảnh**.
- Clip phát từ bản đã thu, luôn ghi `@creator` + link clip gốc, **không hiển thị transcript**.
- Dữ liệu Google đi kèm **bản đồ Google**.
- **Không gợi ý chỗ ở.**
- Người dùng và admin **không sửa tay dữ liệu địa điểm**.
