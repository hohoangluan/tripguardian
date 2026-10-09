# TripGuardian — Thiết kế chức năng Web

Tài liệu này nói **mỗi vai trò được làm gì và mỗi màn hình phải cho làm gì, hiển thị gì**. Không bàn vì sao (xem `docs/Project_Context.md`), luồng hệ thống phía sau (xem `docs/ARCHITECTURE.md`), cách thiết kế giao diện (xem `docs/UX_Design_Brief.md`), hay đặc tả trang cho designer (xem `docs/UI_SPEC_USER_WEB.md`).

Màn nào nằm ở file nào và gọi backend nào: §6.

---

## 1. Bề mặt và vai trò

```text
LANDING      giải thích vấn đề, một CTA → User Web          /          (public)
USER WEB     lên kế hoạch, quyết định, đi cùng trong chuyến    /app       (cần tài khoản Google)
ADMIN WEB    nội bộ: duyệt dữ liệu bị đánh dấu, theo dõi       /admin
             phiên, chất lượng, hệ thống
```

Chỉ có hai vai trò: **User** (người lên kế hoạch chuyến đi) và **Admin** (đội vận hành). MVP không cần Super Admin, Moderator, Data Manager, hay Analyst.

### Quyền của User

| Nhóm | Được phép |
|---|---|
| Chuyến đi | Tạo, xem, sửa chuyến đi của mình |
| Sở thích, constraint, anchor | Thêm, sửa; khóa hoặc bỏ nơi bắt buộc đến |
| User Profile | Cấp hoặc thu hồi nguồn dữ liệu; xem, sửa, đặt lại profile của mình |
| Địa điểm | Nhập địa điểm đã lưu; xem gợi ý và bằng chứng; so sánh; thêm, bỏ, khóa, thay |
| Kế hoạch | Xem cảnh báo, xung đột, phương án dự phòng; tạo và sửa lịch trình |
| Phản hồi | Gửi phản hồi; báo thông tin địa điểm sai |
| Trong chuyến | Check-in tự nguyện, bỏ qua, đánh giá Hợp / Không hợp; xuất lịch ra Google Calendar (luôn xem trước rồi xác nhận); bật / tắt thông báo |
| Tài khoản | Sửa hồ sơ, đổi avatar, xóa tài khoản (`docs/ACCOUNTS.md`) |

User **không** được: sửa dữ liệu nguồn của địa điểm, sửa bằng chứng hay confidence, xem dữ liệu của người khác, vào Admin Web.

### Quyền của Admin

| Nhóm | Được phép |
|---|---|
| Review | Xử lý hàng đợi review: Accept, Disable, hoặc Report error trên một giá trị, liên kết, loại, hoặc bản trùng |
| Địa điểm | Xem danh sách địa điểm và bằng chứng; yêu cầu làm mới nguồn |
| Xung đột | Accept để giữ chưa chắc chắn, hoặc Report error trên observation của nguồn sai (build lại, rule chọn giá trị; xung đột vẫn giữ trong lịch sử) |
| Quan sát | Xem toàn bộ dữ liệu người dùng (transcript, phiên, event, check-in, thông báo), analytics, Insights, pilot, trạng thái hệ thống, lỗi, phản hồi |

Admin **không** gõ giá trị mới cho fact của địa điểm: dữ liệu do agent xây, giá trị sai được báo lỗi và hệ thống build lại từ bằng chứng (`docs/CORPUS.md` §7 Publish và review). Admin không sửa lịch trình của User và không quyết định thay User.

---

## 2. User Web — các màn hình

Luồng bắt đầu khác nhau theo trạng thái bắt đầu (`docs/Project_Context.md` §3.2). Cách hiển thị giá trị chưa chắc chắn, fact, signal, estimate: `docs/UX_Design_Brief.md` §4.

### 2.1 Vào ứng dụng

- Chưa đăng nhập: chỉ có "Tiếp tục với Google"; lần đầu thêm màn đồng ý điều khoản và chính sách dữ liệu (`docs/ACCOUNTS.md` §2). Google trả về đúng trang đang mở.
- Một ô nhập tự do: người dùng gõ hoặc dán link đã lưu, danh sách, lịch có sẵn, hoặc chỉ một câu. Hệ thống tự phân loại trạng thái bắt đầu, không hỏi.
- Lối tắt khi chưa biết gõ gì: "Chưa có gì" / "Địa điểm đã lưu" / "Nơi bắt buộc đến" / "Một lịch trình".
- Người dùng quay lại có hồ sơ: đề xuất "Theo gu quen thuộc" hoặc "Lần này khác".

### 2.2 Thiết lập chuyến đi

- Bắt buộc: ngày đi, số người và là ai (người yêu, bạn, trẻ em, bố mẹ), phương tiện. Hỏi sau phần trò chuyện, bỏ qua được: điểm xuất phát, cách tới Đà Lạt (tự đi / xe khách / máy bay; xe khách, máy bay thì chọn chuyến đi, chuyến về từ trang đặt vé), chỗ ở (đã có thì gõ tìm; chưa có thì hệ thống gợi ý theo gu ở màn "Bạn ở đâu?" trước lịch). Chỗ ở là điểm bắt đầu / kết thúc mỗi ngày của lộ trình.
- Tùy chọn: nơi bắt buộc đến, booking cố định, giờ check-in/check-out và giờ phải rời Đà Lạt, giới hạn cứng (ngân sách, thời gian di chuyển tối đa mỗi chặng, tránh đường dốc, phải xong trước một giờ, loại hoạt động không muốn).
- Giới hạn cứng và sở thích mềm là hai loại khác nhau (`docs/ARCHITECTURE.md` §2).

### 2.3 Khám phá sở thích

- Mỗi lần một câu hỏi, kèm chip gợi ý, ô nhập tự do, "Chưa chắc", "Bỏ qua / gợi ý trước đi". Quy tắc chọn câu hỏi và ngân hàng câu hỏi: `docs/TRIP_UNDERSTANDING.md` §5, §12.
- Có profile: chỉ hỏi điều khác lần này — "Theo gu quen thuộc / Muốn thử cái mới / Đi với người khác / Có yêu cầu riêng".
- Kết thúc bằng **Tóm tắt chuyến đi**: thông tin cơ bản, anchor, giới hạn cứng, sở thích (đánh dấu nếu lấy từ hồ sơ), điều còn chưa biết. Sửa được trước khi bắt đầu tìm.

### 2.4 Nhập địa điểm đã lưu / lịch trình có sẵn

- Mỗi mục: đã khớp ✓ / cần chọn (2–3 ứng viên với tên, khu vực, ảnh hoặc ghim bản đồ) / không tìm thấy (giữ ở dạng "chưa xác minh" hoặc xóa).
- Gộp trùng ("Túi Mơ To" và "Tiệm Túi Mơ To" là một nơi). Gắn nhãn bắt buộc đến / đã lưu / đã đi / tránh / chưa rõ.
- Không bao giờ đoán match. Nơi chưa xác minh vẫn ở lại trong chuyến đi, có đánh dấu (`docs/PLACE_DECISION.md` §4).

### 2.5 Shortlist

- Gom theo nhóm: điểm tham quan, thiên nhiên & view, ăn uống & cà phê, mua sắm / đặc sản. Chỗ ở không nằm trong shortlist (§2.2).
- Thẻ địa điểm:

```text
Tên · loại · khu vực
Vì sao phù hợp   ✓ view rừng thông  ✓ hợp cặp đôi  ✓ gần khu Ngày 2 của bạn
Đánh đổi         ! thêm ~25 phút di chuyển
Thời gian        60–90 phút
Độ tin cậy       Cao / Trung bình / Thấp
```

- Thao tác: thêm vào danh sách chọn · bỏ · khóa · so sánh · xem chi tiết.
- Nơi giống nhau hiển thị thành cặp/nhóm ("cả hai đều là quán cà phê rừng thông, có lẽ bạn chỉ cần một") kèm lối tắt So sánh.
- Trạng thái: quá ít kết quả ("nới một giới hạn?"); mọi nơi bị một giới hạn cứng loại (nói rõ giới hạn nào).

### 2.6 Chi tiết địa điểm (bằng chứng)

- **Thông tin thực tế** (giờ, giá, đặt chỗ): giá trị + nguồn (chính thức / Google) + ngày kiểm tra. Xung đột hiển thị cả hai giá trị, đánh dấu chưa xác nhận.
- **Trải nghiệm**: mỗi feature mở ra clip TikTok phát tại đúng đoạn và xu hướng comment kèm cỡ mẫu ("62% trong 123 comment về độ đông, từ 30 creator"), cùng 2–3 comment gốc có link về video.
- **Mức vận động** (đi bộ, dốc, đường vào) và **đối tượng phù hợp** (cặp đôi, trẻ em, người lớn tuổi).
- Nút **Báo thông tin sai**: chỉ đưa địa điểm vào hàng đợi review và kích hoạt làm mới nguồn; không đổi dữ liệu và không được coi là bằng chứng.

### 2.7 So sánh

- 2 (tối đa 3) nơi giống nhau; chỉ hiển thị các thuộc tính khác nhau (trải nghiệm, di chuyển, độ đông, chi phí, thời điểm đẹp nhất).
- Một câu hỏi tiếp theo, ví dụ "Ưu tiên ít di chuyển hay chỗ yên tĩnh hơn?". Lựa chọn cập nhật chuyến đi ngay; hệ thống không chọn thay.

### 2.8 Tuyển chọn — danh sách đã chọn kèm khả thi trực tiếp

- Luôn hiển thị: số nơi đã chọn, tổng thời gian tham quan, thời gian di chuyển ước tính, chi phí ước tính, cảnh báo, khả thi sơ bộ.
- Mỗi thay đổi hiện một dòng chênh lệch: "+1 nơi · +70 phút · +35 phút di chuyển — Ngày 2 có thể quá tải."
- Khi bỏ (tùy chọn, chỉ khi hữu ích): "Quá xa / Quá đông / Quá đắt / Không thích / Đã đi rồi". Ý nghĩa của từng lý do: `docs/Project_Context.md` §8.3.

### 2.9 Kết quả khả thi

| Kết quả | Hiển thị |
|---|---|
| **Khả thi** | Chuyển sang xếp lịch |
| **Khả thi một phần** | Nơi nào xung đột, vi phạm quy tắc nào, mỗi cách sửa được gì ("Bỏ C: tiết kiệm 90 phút, Ngày 2 ổn"); người dùng chọn cách sửa |
| **Không khả thi** | Lý do tổng thể (cần 14 giờ, có 9 giờ · vượt ngân sách 400k · hai booking trùng giờ) và lối quay lại tuyển chọn |

Xung đột với giới hạn của người dùng → đưa ra "nới giới hạn này" kèm cái giá cụ thể. Xung đột vật lý → chỉ đưa ra cách dời có thật (`docs/PLACE_DECISION.md` §13.3).

### 2.10 Lịch trình

- Màn chỉ nhận act, không chat. Planning Agent đề xuất nội bộ từ phương án đã kiểm; “+ Thêm nơi” quay về tuyển chọn trong cùng hành trình.
- Theo từng ngày: dòng thời gian (giờ đến, khoảng thời gian ở lại, di chuyển giữa các điểm), bản đồ lộ trình, chi phí ước tính, cảnh báo tại đúng điểm dừng.
- Nhãn độ vững mỗi ngày: Vững / Khả thi / Mong manh, kèm lý do một câu (`docs/PLANNING.md` ⓕ).
- Phương án dự phòng gắn với điểm nhạy cảm ("Nếu mưa: A → B trong nhà", "Bị trễ: bỏ C trước"); chỉ thay khi người dùng chọn.
- Thông tin chưa xác nhận vẫn được đánh dấu ("Giờ mở cửa chưa xác nhận — kiểm tra trước khi đi").

### 2.11 Hồ sơ và dữ liệu

- Avatar, tên hiển thị, thành phố hay xuất phát, phương tiện hay dùng, hay đi với ai: đều tùy chọn, chỉ là gợi ý ban đầu "từ hồ sơ" cho chuyến mới.
- Sở thích của chuyến hiện tại (từ lời người dùng hoặc từ hồ sơ), Google Calendar đã kết nối và nút ngắt, cài đặt thông báo theo loại + tạm im, hướng dẫn thêm vào màn hình chính (iPhone).
- Xóa tài khoản: hỏi hai bước.

### 2.12 Phản hồi

- Sau kế hoạch hoặc sau chuyến đi: gợi ý có đúng, lý do có dễ hiểu, lịch có thực tế, có còn phải tìm chỗ khác, có tự tin hơn. Ngắn, không bắt buộc.
- Dùng cho analytics và pilot; nếu người dùng cho phép, nơi đã đến và phản hồi cập nhật User Profile (`docs/Project_Context.md` §8.5).

### 2.13 Hôm nay (Đang đi)

- Sau khi chốt lịch: từng ngày, mỗi điểm dừng một thẻ (giờ, ảnh, giờ mở, cảnh báo của lịch). Nút **Đã đến** tự nguyện; không có trạng thái "lỡ". Bỏ qua kèm lý do tùy chọn; sau khi đến có Hợp / Không hợp.
- Đã đến mở "Ở đây": chơi gì ở đây (kèm trích dẫn, clip), lưu ý thực tế, giờ hoàng hôn / mức đông theo giờ khi có dữ liệu, gần đây (vừa thời gian trước điểm sau), nơi tương tự khi đông hoặc không như kỳ vọng. "Tôi đang ở nơi khác" tìm nơi rồi check-in.
- Tới muộn: một dòng trung tính "Phần còn lại hơi chật · Xem cách điều chỉnh"; đổi lịch chỉ khi người dùng chọn và xác nhận.
- Thẻ Google Calendar (xem trước → xác nhận; lệch kế hoạch thì một dòng "Lịch Google khác kế hoạch hiện tại"), thẻ xin bật thông báo, Hộp thông báo. Chi tiết: `docs/COMPANION.md`.

---

## 3. Admin Web — các màn hình

```text
ADMIN
├── Dashboard                     /admin
├── Review Queue                  /admin/review
├── Labels (gán nhãn đo chất lượng) /admin/labels
├── Places (danh sách + chi tiết)  /admin/places
├── Evidence (theo dõi + xung đột) /admin/evidence
├── Trip Sessions                 /admin/sessions
├── Analytics                     /admin/analytics
└── System Monitor                /admin/system
```

### 3.1 Hàng đợi review

Việc chính hằng ngày của Admin. Nội dung và thứ tự hàng đợi: `docs/CORPUS.md` §7 Publish và review.

- **Danh sách:** loại mục (giá trị Judge đánh dấu · kiểm tra giá trị cho phép về an toàn / tiếp cận / đối tượng phù hợp · tên chưa resolve · feature đề xuất), địa điểm, khía cạnh, vì sao nằm ở đây, mức rủi ro.
- **Một mục:** giá trị, thành phần độ tin cậy (số nguồn, đồng thuận, độ mới, loại nguồn), bằng chứng (clip tại timestamp, comment, trích đoạn chính thức), finding của Judge.
- **Thao tác:** Accept · Disable · Report error (giá trị / liên kết / loại POI/ZONE / trùng / category). Accept hàng loạt cho mục rủi ro thấp cùng loại.
- Mẫu ngẫu nhiên các mục đã publish được trộn vào **không đánh dấu** và phải trông y hệt các mục khác.

### 3.2 Gán nhãn (đo chất lượng)

Nơi duy nhất sinh ra thước đo precision của corpus (`docs/CORPUS.md` §Đo chất lượng). Khác hàng đợi review: ở đây người duyệt không quyết định số phận một giá trị, chỉ nói "bằng chứng này có đỡ được giá trị này không".

- **Một mục:** feature + giá trị cần chấm, bối cảnh, và đoạn review gốc có **tô đậm đúng quote** mà Extractor dựa vào; ảnh Maps và video TikTok hiện cùng cách.
- **Thao tác:** nhãn đúng / sai / không rõ, kèm ghi chú tùy chọn. Lấy theo lô (`BATCH` = 4) để chấm nhanh.
- **Thống kê:** số nhãn và precision (kèm cận dưới Wilson) theo từng feature, so với `gate` — giá trị chưa đủ nhãn thì chưa được phục vụ một mình (`docs/CORPUS.md` §5 Aggregate, `servable`).

### 3.3 Danh sách địa điểm và chi tiết

- **Danh sách:** địa điểm · trạng thái · bằng chứng · độ tin cậy · cập nhật. Lọc theo trạng thái (bộ trạng thái chung: `docs/CORPUS.md` §Trạng thái), category, thành phố (theo config), coverage. Hiển thị khía cạnh có trạng thái tệ nhất.
- **Chi tiết:** Identity, Operation, Experience, Environment, Effort, Suitability — mỗi khía cạnh có trạng thái, coverage, bằng chứng, độ mới, độ tin cậy; finding của Judge và lịch sử review.
- **Thao tác:** Accept · Disable · Report error · Request refresh. Provenance cũ không bao giờ bị xóa.

### 3.4 Theo dõi bằng chứng và xung đột

- **Mỗi bản ghi:** nhận định · nguồn · thời điểm thu thập · độ tin cậy · trạng thái. Lọc: Fresh / Outdated / Missing / Conflicting / Single source.
- **Xung đột** (cùng nhận định, khác giá trị): Accept (giữ chưa chắc chắn) · Report error trên observation của nguồn sai (build lại, rule chọn giá trị) · Refresh sources. Khi chưa xử lý, User Web nhận trạng thái chưa chắc chắn.

### 3.5 Dashboard

```text
Places 842 · Verified 691 · Needs Review 23 · Outdated 53
Last build: auto-published 88% · sampled precision 96% · cost per place $0.04
Hôm nay: người dùng mới 5 · hành trình 18 · lịch đã chốt 13 · phản hồi 2 · lỗi và fallback 1
```

Vài con số để phát hiện vấn đề nhanh; hàng "Hôm nay" lấy số thật từ server analytics (`docs/ANALYTICS.md`).

### 3.6 Phiên chuyến đi

Để debug, đánh giá pilot, tìm chỗ người dùng bỏ dở. Danh sách hành trình trên server, lọc theo bước đã tới, bỏ dở (24 giờ không động, chưa chốt), phản hồi thấp (điểm ≤ 2), có lỗi / fallback. Chi tiết là dòng thời gian phát lại: event, log Decision / Planning, phản hồi, hội thoại Hiểu chuyến, các yêu cầu đã ghi.

### 3.7 Analytics

Tab Phễu, Trip, Quyết định, Lịch trình, Thực tế, Thông báo, Agent, Chất lượng; lọc theo ngày, cách bắt đầu, phiên bản; Phễu so sánh hai phiên bản. Màn Insights liệt kê việc nên làm (từ khóa cần crawl, mong muốn ontology chưa hiểu, nơi hay bị bỏ, câu hỏi hay bị bỏ qua, phiên lỗi) và các nhóm ý người dùng viết trong tuần. Chi tiết chỉ số: `docs/ANALYTICS.md` §3–4.

Chỉ số chất lượng quan trọng hơn lượt xem hay click CTA. Ngưỡng chỉ đặt sau khi có baseline thật.

### 3.8 Theo dõi hệ thống và lỗi

- **Thành phần:** Corpus build (lần chạy gần nhất, ngân sách đã dùng) · Discovery · Resolution · Evidence pipeline · Recommendation · Feasibility · Routing · LLM. Trạng thái: Healthy / Warning / Unavailable.
- **Lỗi gần đây:** thời gian · sự kiện · địa điểm hoặc chuyến đi liên quan ("20:14 thiếu giờ mở cửa — Place #128").

---

## 4. Ưu tiên MVP

| User Web | Admin Web |
|---|---|
| 1. Thiết lập chuyến đi · 2. Khám phá sở thích · 3. Shortlist · 4. So sánh · 5. Tuyển chọn · 6. Kết quả khả thi · 7. Lịch trình · 8. Cảnh báo / dự phòng | 1. Hàng đợi review · 2. Gán nhãn · 3. Danh sách địa điểm + chi tiết · 4. Theo dõi bằng chứng · 5. Phiên chuyến đi · 6. Analytics sản phẩm / pilot · 7. Theo dõi hệ thống · 8. Acquisition / UTM |

## 5. Ngoài phạm vi MVP

- User Web: chỉ đường từng bước, đặt chỗ và thanh toán, tính năng mạng xã hội, cộng tác nhóm lớn, thành phố ngoài Đà Lạt.
- Admin Web: nhiều cấp admin, quy trình duyệt nhiều bước, ma trận quyền chi tiết, CRM, hệ thống chăm sóc khách hàng, billing, quản lý booking, nền tảng quản lý campaign, quản lý tài khoản nâng cao, nền tảng kiểm duyệt, dashboard doanh nghiệp.

---

## 6. Triển khai — màn nào ở đâu

Một app React (`web/`, Vite). `App.tsx` chọn bề mặt theo đường dẫn; mỗi bề mặt có bảng route riêng.

| Màn (§) | File | Backend |
|---|---|---|
| Landing (§1) | máy tính: `user/screens/Landing.tsx` + cảnh 3D `user/landing/{scene,terrain}.ts`; điện thoại: `user/screens/GetApp.tsx` thay cho **mọi** trang người dùng (`/`, `/app/...`; chọn bằng `user/landing/device.ts`, `UserApp.tsx`) — web không có bản điện thoại, ứng dụng sẽ có sau; dữ liệu thật trích từ snapshot ở `user/landing/*.json` | — |
| Đăng nhập (§2.1) | `user/screens/Auth.tsx`, `user/account.ts` (401 ở bất kỳ lời gọi harness nào → màn đăng nhập) | `harness` — `/api/auth/*`, `/me` |
| Khám phá — trang chủ app | `user/screens/Discover.tsx` | — |
| Hiểu chuyến đi (§2.2–2.4) | `user/screens/Understand.tsx`, `user/ui/Ticket.tsx`, `user/tu/`; thẻ hậu cần (`docs/TRIP_UNDERSTANDING.md` §Hậu cần): `user/ui/PlaceInput.tsx` (ô gõ có gợi ý kiểu Google Maps: từ ký tự thứ 2, chờ 250 ms, ≤ 6 dòng, tô đậm chữ khớp, ↑ ↓ Enter Esc; dùng cho xuất phát, chỗ ở đã đặt, "Tôi ở chỗ khác"), `user/ui/TransitPick.tsx` (danh sách chuyến bay / xe khách, lọc Sáng · Chiều · Đêm · Rẻ nhất, skeleton khi đang tra; không tra được → mở trang đặt vé + nhập tay giờ) | `harness` :8769 — stage `trip`; `/geo`, `/lodging/suggest`, `/transit` (+ SSE) |
| Chọn nơi, Chi tiết, So sánh, thanh "Đã chọn" (khả thi + lịch ngầm), trợ lý (§2.5–2.9) | `user/screens/{Explore,PlaceDetail,Compare}.tsx`, `user/ui/{PlaceCard,SelectedBar,Assistant,DiscPicker}.tsx`, `user/ui/PlaceSheet.tsx` ("Xem chi tiết": modal mở từ đĩa xoay, lưới, anchor, trợ lý, thanh "Đã chọn"; URL `?place=<id>`, Back / Esc đóng; ảnh bay vào chỗ bằng View Transitions, không hỗ trợ thì FLIP; tab Tổng quan · Hình ảnh · Gợi ý lịch trình · Đánh giá; `PlaceDetail.tsx` bọc nó ở chế độ trang cho link chia sẻ), `user/ui/useStagedList.ts` (chuyển cảnh lưới khi danh sách đổi: giữ / gỡ / thêm / thay hết), `user/pd/` (`more(group)` tải trang tiếp khi cuộn) | `harness` :8769 — stage `decision`, `preview`, `reports` |
| Lịch trình, Tối ưu (§2.10) | `user/screens/Plan.tsx`, `user/ui/RouteStory.tsx`, `user/planning/`; `user/screens/Lodging.tsx` ("Bạn ở đâu?": hiện một lần trước lịch khi `lodging_booked = no`; thẻ chỗ ở xếp theo gu — "Hợp gu bạn nhất", "Hợp vì …", số phút trung bình tới nơi đã chọn; chọn = `pick_lodging`, "Tôi ở chỗ khác" = `set_lodging`, "Cứ xếp giúp" giữ chỗ ở Planning tự chọn, "Bỏ qua" = `clear_lodging`) | `harness` :8769 — stage `planning` (`recommend` cho Tối ưu) |
| Phản hồi (§2.12) | `user/screens/Done.tsx` | `harness` — `feedback` |
| Chuyến của tôi, Đã lưu, Hồ sơ (§2.11) | `user/screens/Account.tsx`, `user/store.ts` | `harness` — `trips`, `/me`, `/me/avatar`, `/me/notification-prefs`, `/calendar/disconnect`; nơi đã lưu chỉ ở trình duyệt |
| Hôm nay (§2.13), Hộp thông báo | `user/screens/Today.tsx`, `user/today.ts`, `user/screens/Inbox.tsx`, `user/notify.ts`, `public/sw.js`, `public/manifest.webmanifest`; event web: `user/events.ts` | `harness` — `today`, `companion`, `calendar`, `push`, `notifications`, `events` |
| Admin, mọi màn (§3) | `admin/AdminApp.tsx`, `admin/screens/`, `admin/api.ts` | `review` :8765 — `/api/queue`, `/api/labels{,/next,/stats,/photo,/frame}`, `/api/decision{,s}` |
| Admin: Hôm nay, Phiên, Phân tích, Insights, Nhu cầu của một nơi (§3.5–3.7) | `admin/analytics.ts`, `admin/screens/{Dashboard,Sessions,Analytics,AnalyticsTabs,Insights,Places}.tsx` | `analytics` :8770 (private, chỉ đọc) |

Client hành trình chung: `user/journey.ts`. Contract `/api/harness`, router, handoff và retry ở `docs/AGENT_HARNESS.md`.

Dữ liệu chỉ-đọc của corpus mà cả hai bề mặt dùng để hiển thị địa điểm: `web/public/data/snapshot.json`, sinh bằng `python web/scripts/export_snapshot.py` sau `python -m corpus aggregate`. Không có file đó thì mọi màn báo lỗi tải dữ liệu.

Chạy cả stack: `README.md`. Hệ thị giác, font, màu: `docs/UX_Design_Brief.md` §7.
