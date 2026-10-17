# TripGuardian — Thiết kế chức năng Web

Tài liệu này nói **mỗi vai trò được làm gì và mỗi màn hình phải cho làm gì, hiển thị gì**. Không bàn vì sao (xem `docs/Project_Context.md`), luồng hệ thống phía sau (xem `docs/ARCHITECTURE.md`), cách thiết kế giao diện (xem `docs/UX_Design_Brief.md`), hay đặc tả trang cho designer (xem `docs/UI_SPEC_USER_WEB.md`).

Màn nào nằm ở file nào và gọi backend nào: §6.

---

## 1. Bề mặt và vai trò

```text
LANDING      giải thích vấn đề, một CTA → User Web          /          (public)
USER WEB     lên kế hoạch, quyết định, đi cùng trong chuyến    /app       (tài khoản Google hoặc khách)
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

- Bắt buộc: ngày đi, số người và là ai (người yêu, bạn, trẻ em, bố mẹ), phương tiện. Hỏi sau phần trò chuyện, bỏ qua được: cách tới Đà Lạt (tự đi / xe khách / máy bay; không chọn chuyến), điểm xuất phát (nhà), đã có chỗ ở chưa (có thì gõ tìm; chưa thì chọn ở tab "Chỗ ở" của Chọn nơi, gợi ý theo gu). Chỗ ở là điểm bắt đầu / kết thúc mọi ngày của lộ trình.
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
- So sánh nơi giống nhau mở từ nút nổi "So sánh N nơi" (lưới không chen dòng "khá giống nhau").
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
- Chi phí, độ vững và dự phòng đọc từ lịch hiện tại sau sửa; xung đột validation hiện trước khi chốt. Gợi ý thêm hoạt động có trạng thái đang tìm / chưa tải được, không cản thao tác sửa lịch. Read/SSE cũ không thay view mới (`docs/AGENT_HARNESS.md`).
- Quá tải mở ba thẻ để user chọn, không tự chọn qua Agent. Giữ tất cả có phần đối chiếu timeline riêng; nút chọn bị khóa khi lịch gốc chưa hợp lệ. Mọi đường chọn profile unavailable và nút chốt draft vi phạm đều bị vô hiệu. Preview/apply và delta theo lịch hiện tại: `docs/PLANNING.md` §Vòng người dùng sửa và góp ý.
- Nhãn độ vững mỗi ngày: Vững / Khả thi / Mong manh, kèm lý do một câu (`docs/PLANNING.md` ⓕ).
- Thẻ độ phù hợp giờ ghé giải thích ước lượng theo hoạt động và phút rút; gợi ý khoảng trống/quá tải có nút thêm tùy chọn từ backup, xếp lại ngày và hoàn tác được (`docs/PLANNING.md` §Độ phù hợp giờ ghé).
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
| Landing (§1) | máy tính: `user/screens/Landing.tsx` (người đã đăng nhập có thêm "Dùng thử khách": phiên khách mới, tài khoản giữ nguyên) + cảnh 3D `user/landing/{scene,terrain}.ts`; điện thoại: `user/screens/GetApp.tsx` thay cho **mọi** trang người dùng (`/`, `/app/...`; chọn bằng `user/landing/device.ts`, `UserApp.tsx`) — web không có bản điện thoại, ứng dụng sẽ có sau; dữ liệu thật trích từ snapshot ở `user/landing/*.json` | — |
| Đăng nhập (§2.1) | `user/screens/Auth.tsx` (Google, form email + mật khẩu hai tab Đăng nhập / Tạo tài khoản, "Dùng thử, không cần tài khoản" = khách mới sạch), `user/account.ts` (401 ở bất kỳ lời gọi harness nào → màn đăng nhập) | `harness` — `/api/auth/*` (`google`, `register`, `login`, `guest`, `logout`), `/me` |
| Khung app (mọi trang không thuộc luồng chuyến: Dành cho bạn, Chuyến của tôi, Đã lưu, Đã xem gần đây, Thông báo, Cài đặt, Hôm nay mở từ link) | `user/home/Frame.tsx` (phủ toàn màn hình: thanh bên là cột icon hẹp (kiểu Pinterest), tên mỗi nút hiện thành tooltip khi rê chuột hoặc focus bàn phím; các thẻ trắng rời nhau: (1) logo (bấm về `/app`); (2) Dành cho bạn · Chuyến của tôi · Đã lưu · Đã xem gần đây; (3) Cài đặt (trang hồ sơ) · Hỗ trợ (`user/screens/Support.tsx`, câu hỏi chung với landing ở `user/faq.ts`); hai thẻ giữa nằm giữa chiều cao cột; Đăng xuất ở đáy cột; nút "Tạo chuyến đi" (đủ chữ) cố định ở góc dưới bên phải màn hình, cùng hàng với nút Đăng xuất (đối xứng hai bên màn hình); mục đang mở là ô vuông đen; **không** có Hôm nay; thanh chuyến đang lập chỉ hiện khi chuyến chưa chốt lịch, chốt rồi thì ẩn; nó nổi trên trang ở đáy, cùng hàng với Đăng xuất và Tạo chuyến đi, không đẩy thứ gì dịch đi), `user/home/Chats.tsx` (hai nút tròn cạnh ảnh đại diện (`user/home/Who.tsx`: ở trang chủ nằm đầu cột phải kèm tên và @nickname, bấm ảnh mở hồ sơ để chỉnh; ở các trang khác là ảnh nhỏ + hai nút ở góc trên phải): chuông Thông báo → `/inbox`, và Đoạn chat — danh sách bạn bè kiểu Messenger: tìm, lọc Tất cả / Chưa đọc / Đang hoạt động, chấm tin chưa đọc), `user/home/dialogs.tsx` (chủ đề, kể chuyến mới, bạn bè, gửi lịch trình; cửa sổ chat gắn góc dưới phải tối đa ba, thu nhỏ thành ảnh đại diện, trang phía sau vẫn dùng được), `user/social.ts`, `user/css/home.css` (`.tg-home` dùng bộ màu mận / hồng `.tg-rose` của luồng); bố cục theo mẫu `ui_mock_for_design/designs/homepage/` | `harness` — `friends`, `users`, `messages` (`docs/ACCOUNTS.md` §8), `me/library` (§9) |
| Dành cho bạn — trang chủ app | `user/screens/Discover.tsx`, `user/home/themes.ts` (5 chủ đề, ảnh thật trong `public/img/home/`; câu của chủ đề thành lượt đầu của Tìm hiểu); bố cục theo bảng điều khiển du lịch mẫu: giữa là ô tìm, thẻ ảnh lớn (tiêu đề + phụ đề, chip số địa điểm có thật trong snapshot, hiện khi snapshot tải xong; trang chủ, Chuyến của tôi, Hỗ trợ, Thông báo, Hồ sơ mở ngay không chờ snapshot, các trang còn lại hiện khung chờ trong khi tải (snapshot tải ngay khi đã đăng nhập); không có nút) và "Gợi ý để bắt đầu" (thẻ chủ đề chỉ có nhóm + tên, thẻ đầu nâng và phóng nhẹ, không nghiêng); cột phải tô nhạt gồm hồ sơ (`Who`), lịch tháng (`user/home/MiniCalendar.tsx`, đánh dấu ngày của chuyến đang lập chỉ khi chuyến có ngày) và "Top xu hướng", danh sách 5 chủ đề dạng thẻ có ô số pastel (01–05; rê chuột thì nâng và nghiêng); bấm một chủ đề hoặc ảnh ở "Gợi ý để bắt đầu" mở blog `user/home/ThemeBlog.tsx` + `user/css/blog.css` (thẻ giấy kem kiểu bưu thiếp: ảnh trong khung, tem ở góc, 5 chủ đề là tab dọc bên phải; nền phía sau làm mờ; ảnh bay ra từ thẻ vừa bấm bằng Web Animations, đổi tab thì ảnh hiện từ trên xuống; Esc / bấm ngoài đóng); `/` focus ô tìm, Enter mở "Kể mình nghe chuyến đi"; cỡ chữ của trang chủ (`user/css/home.css`) đã tăng 10% so với bản trước | `harness` — `me/library`, event `theme_open` |
| Hiểu chuyến đi (§2.2–2.4) | `user/screens/Understand.tsx` (một khung chat, `docs/UI_SPEC_USER_WEB.md` Trang 3), `user/screens/understand/` (`Turn.tsx` lượt chat + khối các bước + câu hỏi, `Ask.tsx` thẻ một câu hỏi và khung chọn ảnh, `Deck.tsx` form đáp án dùng chung và thẻ nhiều mục của sheet đọc lại, `Cards.tsx` dấu hiệu / các kiểu / có phải nơi này, `History.tsx` lịch sử/tìm kiếm/tạo và mở chuyến thật, `Board.tsx` tiến độ tám nhóm thông tin + số nơi đang hợp, `Composer.tsx` ô nhắn, ảnh thu nhỏ ở trình duyệt), `user/css/chat.css` + `user/css/ask.css` + `user/css/workspace.css` (font, nền sáng và rail `Sidebar` dùng chung homepage), `user/ui/Ticket.tsx`, `user/tu/`; thẻ hậu cần (`docs/TRIP_UNDERSTANDING.md` §Hậu cần): `user/screens/understand/LodgingCards.tsx` (câu hỏi chỗ ở = dải thẻ để chạm chọn: ảnh, loại, tên, khu · điểm, giá/đêm hoặc "Chưa có giá", lý do hợp; bấm *Chọn chỗ này* là ghi chỗ ở và đi tiếp; *Cứ xếp giúp* để app tự chọn; gõ tên chỉ là lối phụ sau liên kết *Mình đã có chỗ ở rồi*; trong chat đọc `lodging/suggest?top=`, ở sheet đọc lại trước lịch trình đọc `read/decision/lodging` nên có phút tới các nơi đã chọn; chỉ chỗ ở trong corpus, lỗi tải thì hiện ô gõ), `user/ui/PlaceInput.tsx` (ô gõ có gợi ý kiểu Google Maps: từ ký tự thứ 2, chờ 250 ms, ≤ 6 dòng, tô đậm chữ khớp, ↑ ↓ Enter Esc; dùng cho xuất phát, chỗ ở đã đặt, "Tìm chỗ ở khác") | `harness` :8769 — stage `trip`; `/geo`, `/lodging/suggest` |
| Chọn nơi, Chi tiết, So sánh, thanh "Đã chọn" (khả thi + lịch ngầm), trợ lý (§2.5–2.9) | `user/screens/{Explore,PlaceDetail,Compare}.tsx`, `user/ui/{PlaceCard,SelectedBar,Assistant,DiscPicker}.tsx`, `user/ui/PlaceSheet.tsx` ("Xem chi tiết": modal mở từ đĩa xoay, lưới, anchor, trợ lý, thanh "Đã chọn"; URL `?place=<id>`, Back / Esc đóng; ảnh bay vào chỗ bằng View Transitions, không hỗ trợ thì FLIP; tab Tổng quan · Hình ảnh · Gợi ý lịch trình · Đánh giá (tab Đánh giá hiện mọi lời đã thu, mới nhất trước, tải dần khi cuộn: `Reviews` trong `PlaceSheet.tsx`, `reviewsOf` ở `lib.ts`); tab Tổng quan mở đầu bằng đoạn giới thiệu dựng từ dữ liệu có thật (loại, khu, điểm Google, điều hay được khen / cần lưu ý, xu hướng điểm), có thêm "Nổi tiếng vì" dưới tên và các khối của `user/ui/PlaceDetails.tsx` (Tổng tiền, Gọi món gì / làm gì, Giờ và mùa đẹp, Đường đi, Trời xấu, Đi cùng ai với x của chuyến lên đầu, Chuẩn bị, Cần cảnh báo, Nơi tương tự), mỗi dòng kèm số người nhắc và lời của họ, khối hoặc dòng không có dữ liệu thì **ẩn**, không hiện ô trống; thêm khối "Tiện ích và dịch vụ" từ danh sách của Google; `web/scripts/export_snapshot.py` đưa khối `details` của serving vào snapshot; `PlaceDetail.tsx` bọc nó ở chế độ trang cho link chia sẻ), `user/ui/useStagedList.ts` (chuyển cảnh lưới khi danh sách đổi: giữ / gỡ / thêm / thay hết), `user/pd/` (`more(group, n)` hiện trang `n` của một tab), `user/ui/Pager.tsx` (số trang dưới lưới của mọi tab: trang đầu, cuối và quanh trang đang xem; "Nơi a–b trong N"), ô tìm trên hàng tab của `Explore.tsx` (gõ là tìm trên mọi tab theo tên / loại, `read/decision/search`; kết quả ghi tab của từng nơi, cuối là nơi trùng tên không có trong gợi ý kèm lý do), `user/screens/Lodging.tsx` (tab "Chỗ ở" có số đếm như các tab khác (`useLodgingList` do `Explore` giữ); thẻ cùng markup với `PlaceCard` (nhãn loại, tim, `Trust`, phút từ trung tâm); lưới mọi chỗ ở trong corpus như các nhóm khác, không nhãn "cần chọn" hay lời nhắc; quanh các nơi đã chọn lên đầu, còn lại theo gu rồi điểm; chia trang bằng `Pager` như các tab khác, mỗi trang đọc `?offset=`; `set_lodging` / `clear_lodging`) | `harness` :8769 — stage `decision`, `preview`, `read/decision/lodging`, `reports` |
| Lịch trình, Tối ưu (§2.10) | `user/screens/Plan.tsx` (điều phối + hộp thoại) và `user/screens/plan/` (`Choose` chọn phương án, `Overview` tổng quan, `DayView` + `reorder.ts` từng ngày kéo thả, `Swap` + `candidates.ts` đổi / thêm nơi, `parts.tsx` thẻ bên, `TripMap`), `user/css/itinerary.css`; bố cục theo mẫu `ui_mock_for_design/designs/itinerary/`; `user/ui/RouteStory.tsx` (sơ đồ hành trình, mở từ Tổng quan), `user/planning/` (thẻ bên có "Chuẩn bị trước khi đi" từ `checklist` của phương án; thanh tổng kết ghi "có thể thêm tới … cho trò chơi, thuê đồ" từ `metrics.extras_max_vnd`); chỗ ở hiện ở thẻ bên, "Đổi chỗ ở" quay về tab "Chỗ ở" của Chọn nơi; chưa có chỗ ở thì hiện 3 chỗ ở Planning gợi ý, chọn ngay tại chỗ (`pick_lodging`), kèm "Xem tất cả chỗ ở" về tab Chỗ ở; Lựa chọn không nhắc chọn chỗ ở | `harness` :8769 — stage `planning` (`recommend` cho Tối ưu) |
| Phản hồi (§2.12) | `user/screens/Done.tsx` | `harness` — `feedback` |
| Chuyến của tôi, Đã lưu, Đã xem gần đây, Hồ sơ (§2.11) | `user/screens/{Account,Recent}.tsx`, `user/store.ts` (Đã lưu nơi + chủ đề theo tài khoản); Chuyến của tôi có "Gửi cho bạn bè" cho chuyến đã qua Tìm hiểu; Hồ sơ có nickname, giới thiệu | `harness` — `trips`, `/me`, `/me/avatar`, `/me/notification-prefs`, `/calendar/disconnect`, `/me/library` |
| Hôm nay (§2.13; không có trong điều hướng, mở từ thông báo / link), Hộp thông báo | `user/screens/Today.tsx`, `user/today.ts`, `user/screens/Inbox.tsx`, `user/notify.ts`, `public/sw.js`, `public/manifest.webmanifest`; event web: `user/events.ts` | `harness` — `today`, `companion`, `calendar`, `push`, `notifications`, `events` |
| Admin, mọi màn (§3) | `admin/AdminApp.tsx`, `admin/screens/`, `admin/api.ts` | `review` :8765 — `/api/queue`, `/api/labels{,/next,/stats,/photo,/frame}`, `/api/decision{,s}` |
| Admin: Hôm nay, Phiên, Phân tích, Insights, Nhu cầu của một nơi (§3.5–3.7) | `admin/analytics.ts`, `admin/screens/{Dashboard,Sessions,Analytics,AnalyticsTabs,Insights,Places}.tsx` | `analytics` :8770 (private, chỉ đọc) |

Client hành trình chung: `user/journey.ts`. Contract `/api/harness`, router, handoff và retry ở `docs/AGENT_HARNESS.md`.

Dữ liệu chỉ-đọc của corpus mà cả hai bề mặt dùng để hiển thị địa điểm: `web/public/data/snapshot.json`, sinh bằng `python web/scripts/export_snapshot.py` sau `python -m corpus aggregate`. Không có file đó thì mọi màn báo lỗi tải dữ liệu.

Chuyển trang: `router.ts` `navigate` bọc việc đổi đường dẫn trong View Transitions (`web/src/viewTransition.ts`, kiểu `user/css/motion.css`): trang cũ giữ nguyên trên màn hình tới khi trang mới dựng xong rồi hai trang giao thoa mờ ~280 ms, nên trang nặng không giật giữa chừng. Không bọc khi: chỉ đổi query (tờ chi tiết nơi), `replace`, Admin, đã có một transition đang chạy (ảnh bay của tờ chi tiết, của "Lên lịch chuyến của bạn", rời landing), hoặc trình duyệt không hỗ trợ / giảm chuyển động (khi đó `tg-flow` mờ dần 150 ms như trước). Mọi chỗ cần View Transition gọi `startTransition` ở file này, không gọi `document.startViewTransition` trực tiếp.

Đĩa xoay ở Lựa chọn: một lần lăn chuột xoay một nơi, cách nhau tối thiểu 230 ms (`TURN_GAP_MS` trong `DiscPicker.tsx`), đĩa quay 360 ms. Lưới và đĩa xoay là một logic, chỉ khác cách vẽ: cùng nhóm, tab, thứ tự, trang, và cùng các dòng của một nơi (`user/ui/cardLines.ts`: tối đa 3 lý do, đánh đổi, 2 cảnh báo).

Ứng dụng (`/app`) vẽ ở 82,5% cỡ gốc (`html.tg-scaled` trong `tokens.css`, `vite.config.ts` đổi px thành rem).

Dữ liệu snapshot (hàng chục MB) được tải ngầm ngay khi đã vào app và đọc trong worker (`data/snapshotWorker.ts`, `data/store.ts`), nên chuyển Tìm hiểu → Lựa chọn không bị khựng. Thanh bước chỉ có Tìm hiểu · Lựa chọn · Lịch trình (`STEPS` ở `user/trip.tsx`); `/done` (Phản hồi) là trang sau khi chốt lịch, không phải một bước.

Chạy cả stack: `README.md`. Hệ thị giác, font, màu: `docs/UX_Design_Brief.md` §7.
