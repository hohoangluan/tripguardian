# TripGuardian — Thiết kế chức năng Web

Tài liệu này nói **mỗi vai trò được làm gì và mỗi màn hình phải cho làm gì, hiển thị gì**. Không bàn vì sao (xem `docs/Project_Context.md`), luồng hệ thống phía sau (xem `docs/ARCHITECTURE.md`), hay cách thiết kế giao diện (xem `docs/UX_Design_Brief.md`).

---

## 1. Bề mặt và vai trò

```text
LANDING      giải thích vấn đề, một CTA → User Web          /landing
USER WEB     lên kế hoạch và quyết định (sản phẩm chính)      /app
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

User **không** được: sửa dữ liệu nguồn của địa điểm, sửa bằng chứng hay confidence, xem dữ liệu của người khác, vào Admin Web.

### Quyền của Admin

| Nhóm | Được phép |
|---|---|
| Review | Xử lý hàng đợi review: Accept, Disable, hoặc Report error trên một giá trị, liên kết, loại, hoặc bản trùng |
| Địa điểm | Xem danh sách địa điểm và bằng chứng; yêu cầu làm mới nguồn |
| Xung đột | Accept để giữ chưa chắc chắn, hoặc Report error trên observation của nguồn sai (build lại, rule chọn giá trị; xung đột vẫn giữ trong lịch sử) |
| Quan sát | Xem phiên chuyến đi, analytics, pilot, trạng thái hệ thống, lỗi, phản hồi |

Admin **không** gõ giá trị mới cho fact của địa điểm: dữ liệu do agent xây, giá trị sai được báo lỗi và hệ thống build lại từ bằng chứng (`docs/CORPUS.md` §7). Admin không sửa lịch trình của User và không quyết định thay User.

---

## 2. User Web — các màn hình

Luồng bắt đầu khác nhau theo kinh nghiệm và trạng thái bắt đầu (`docs/ARCHITECTURE.md` §3). Cách hiển thị giá trị chưa chắc chắn, fact, signal, estimate: `docs/UX_Design_Brief.md` §4.

### 2.1 Vào ứng dụng

- Hỏi "Đã đến Đà Lạt chưa?" (lần đầu / đã từng), rồi "Bạn đang có gì?" (chưa có gì / địa điểm đã lưu / nơi bắt buộc đến / một lịch trình).
- Người dùng quay lại có hồ sơ: đề xuất "Theo gu quen thuộc" hoặc "Lần này khác".

### 2.2 Thiết lập chuyến đi

- Bắt buộc: ngày đi, số người và là ai (người yêu, bạn, trẻ em, bố mẹ), phương tiện. Không bắt buộc: chỗ ở.
- Tùy chọn: nơi bắt buộc đến, booking cố định, giờ check-in/check-out và giờ phải rời Đà Lạt, giới hạn cứng (ngân sách, thời gian di chuyển tối đa mỗi chặng, tránh đường dốc, phải xong trước một giờ, loại hoạt động không muốn).
- Giới hạn cứng và sở thích mềm là hai loại khác nhau (`docs/ARCHITECTURE.md` §4).

### 2.3 Khám phá sở thích

- Mỗi lần một câu hỏi, kèm chip gợi ý, ô nhập tự do, "Chưa chắc", "Bỏ qua / gợi ý trước đi". Quy tắc chọn câu hỏi: `docs/Project_Context.md` §12.
- Có profile: chỉ hỏi điều khác lần này — "Theo gu quen thuộc / Muốn thử cái mới / Đi với người khác / Có yêu cầu riêng".
- Kết thúc bằng **Tóm tắt chuyến đi**: thông tin cơ bản, anchor, giới hạn cứng, sở thích (đánh dấu nếu lấy từ hồ sơ), điều còn chưa biết. Sửa được trước khi bắt đầu tìm.

### 2.4 Nhập địa điểm đã lưu / lịch trình có sẵn

- Mỗi mục: đã khớp ✓ / cần chọn (2–3 ứng viên với tên, khu vực, ảnh hoặc ghim bản đồ) / không tìm thấy (giữ ở dạng "chưa xác minh" hoặc xóa).
- Gộp trùng ("Túi Mơ To" và "Tiệm Túi Mơ To" là một nơi). Gắn nhãn bắt buộc đến / đã lưu / đã đi / tránh / chưa rõ.
- Không bao giờ đoán match. Nơi chưa xác minh vẫn ở lại trong chuyến đi, có đánh dấu (`docs/ARCHITECTURE.md` §5).

### 2.5 Shortlist

- Gom theo nhóm: điểm tham quan, thiên nhiên & view, ăn uống & cà phê, mua sắm / đặc sản. Chỗ ở là anchor, không nằm trong gợi ý.
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

Xung đột với giới hạn của người dùng → đưa ra "nới giới hạn này" kèm cái giá cụ thể. Xung đột vật lý → chỉ đưa ra cách dời có thật (`docs/ARCHITECTURE.md` §8).

### 2.10 Lịch trình

- Theo từng ngày: dòng thời gian (giờ đến, khoảng thời gian ở lại, di chuyển giữa các điểm), bản đồ lộ trình, chi phí ước tính, cảnh báo tại đúng điểm dừng.
- Nhãn độ vững mỗi ngày: Vững / Khả thi / Mong manh, kèm lý do một câu (`docs/ARCHITECTURE.md` §12).
- Phương án dự phòng gắn với điểm nhạy cảm ("Nếu mưa: A → B trong nhà", "Bị trễ: bỏ C trước"); chỉ thay khi người dùng chọn.
- Thông tin chưa xác nhận vẫn được đánh dấu ("Giờ mở cửa chưa xác nhận — kiểm tra trước khi đi").

### 2.11 Hồ sơ và dữ liệu

- Nguồn đã kết nối (mỗi nguồn tùy chọn, do người dùng tự thêm — `docs/Project_Context.md` §6.1), điều hệ thống suy ra ("thích cà phê — cao, từ 12 lần lưu"), nút sửa / xóa / đặt lại.
- Không có nguồn nào thì mọi thứ vẫn chạy.

### 2.12 Phản hồi

- Sau kế hoạch hoặc sau chuyến đi: gợi ý có đúng, lý do có dễ hiểu, lịch có thực tế, có còn phải tìm chỗ khác, có tự tin hơn. Ngắn, không bắt buộc.
- Dùng cho analytics và pilot; nếu người dùng cho phép, nơi đã đến và phản hồi cập nhật User Profile (`docs/Project_Context.md` §8.5).

---

## 3. Admin Web — các màn hình

```text
ADMIN
├── Dashboard
├── Review Queue
├── Places (danh sách + chi tiết)
├── Evidence (theo dõi + xung đột)
├── Trip Sessions
├── Analytics
└── System Monitor
```

### 3.1 Hàng đợi review

Việc chính hằng ngày của Admin. Nội dung và thứ tự hàng đợi: `docs/CORPUS.md` §7.

- **Danh sách:** loại mục (giá trị Judge đánh dấu · kiểm tra giá trị cho phép về an toàn / tiếp cận / đối tượng phù hợp · tên chưa resolve · feature đề xuất), địa điểm, khía cạnh, vì sao nằm ở đây, mức rủi ro.
- **Một mục:** giá trị, thành phần độ tin cậy (số nguồn, đồng thuận, độ mới, loại nguồn), bằng chứng (clip tại timestamp, comment, trích đoạn chính thức), finding của Judge.
- **Thao tác:** Accept · Disable · Report error (giá trị / liên kết / loại POI/ZONE / trùng / category). Accept hàng loạt cho mục rủi ro thấp cùng loại.
- Mẫu ngẫu nhiên các mục đã publish được trộn vào **không đánh dấu** và phải trông y hệt các mục khác.

### 3.2 Danh sách địa điểm và chi tiết

- **Danh sách:** địa điểm · trạng thái · bằng chứng · độ tin cậy · cập nhật. Lọc theo trạng thái (bộ trạng thái chung: `docs/CORPUS.md` §6), category, thành phố (theo config), coverage. Hiển thị khía cạnh có trạng thái tệ nhất.
- **Chi tiết:** Identity, Operation, Experience, Environment, Effort, Suitability — mỗi khía cạnh có trạng thái, coverage, bằng chứng, độ mới, độ tin cậy; finding của Judge và lịch sử review.
- **Thao tác:** Accept · Disable · Report error · Request refresh. Provenance cũ không bao giờ bị xóa.

### 3.3 Theo dõi bằng chứng và xung đột

- **Mỗi bản ghi:** nhận định · nguồn · thời điểm thu thập · độ tin cậy · trạng thái. Lọc: Fresh / Outdated / Missing / Conflicting / Single source.
- **Xung đột** (cùng nhận định, khác giá trị): Accept (giữ chưa chắc chắn) · Report error trên observation của nguồn sai (build lại, rule chọn giá trị) · Refresh sources. Khi chưa xử lý, User Web nhận trạng thái chưa chắc chắn.

### 3.4 Dashboard

```text
Places 842 · Verified 691 · Needs Review 23 · Outdated 53
Last build: auto-published 88% · sampled precision 96% · cost per place $0.04
Today: trip sessions 18 · completed plans 13 · blocked plans 2 · feasible plans 91%
```

Vài con số để phát hiện vấn đề nhanh; không cần nhiều biểu đồ.

### 3.5 Phiên chuyến đi

Để debug, đánh giá pilot, tìm chỗ người dùng bỏ dở. Không hiển thị dữ liệu cá nhân không cần thiết.

```text
Trip #1028 · lần đầu · 3 ngày · bắt đầu từ địa điểm đã lưu
15 nhập → 12 đã xác minh → 3 bị lọc → 8 shortlist → 6 được chọn → 1 xung đột → 5 cuối cùng → khả thi sau điều chỉnh
```

### 3.6 Analytics

| Nhóm | Đo |
|---|---|
| Acquisition | Lượt vào landing, click CTA, CTR, nguồn traffic, campaign, UTM source / medium / campaign / content, số chuyến bắt đầu theo nguồn |
| Phễu sản phẩm | Landing → CTA → bắt đầu → xong bối cảnh → xem shortlist → chọn địa điểm → kiểm tra khả thi → tạo lịch → chấp nhận kế hoạch |
| Quyết định | Ứng viên nhập → shortlist → được chọn; số lần bỏ, khóa, so sánh, thay; số xung đột; số lần sửa trước khi có kế hoạch hợp lệ |
| Chất lượng | Chỉ số thành công của sản phẩm (`docs/Project_Context.md` §18) |
| Pilot | Người tham gia, hoàn thành, kế hoạch được chấp nhận, thời gian lập kế hoạch trung vị, số lần sửa trung bình, độ tự tin, phản hồi |

Chỉ số chất lượng quan trọng hơn lượt xem hay click CTA. Ngưỡng chỉ đặt sau khi có baseline thật.

### 3.7 Theo dõi hệ thống và lỗi

- **Thành phần:** Corpus build (lần chạy gần nhất, ngân sách đã dùng) · Discovery · Resolution · Evidence pipeline · Recommendation · Feasibility · Routing · LLM. Trạng thái: Healthy / Warning / Unavailable.
- **Lỗi gần đây:** thời gian · sự kiện · địa điểm hoặc chuyến đi liên quan ("20:14 thiếu giờ mở cửa — Place #128").

---

## 4. Ưu tiên MVP

| User Web | Admin Web |
|---|---|
| 1. Thiết lập chuyến đi · 2. Khám phá sở thích · 3. Shortlist · 4. So sánh · 5. Tuyển chọn · 6. Kết quả khả thi · 7. Lịch trình · 8. Cảnh báo / dự phòng | 1. Hàng đợi review · 2. Danh sách địa điểm + chi tiết · 3. Theo dõi bằng chứng · 4. Phiên chuyến đi · 5. Analytics sản phẩm / pilot · 6. Theo dõi hệ thống · 7. Acquisition / UTM |

## 5. Ngoài phạm vi MVP

- User Web: chỉ đường từng bước, đặt chỗ và thanh toán, tính năng mạng xã hội, cộng tác nhóm lớn, thành phố ngoài Đà Lạt.
- Admin Web: nhiều cấp admin, quy trình duyệt nhiều bước, ma trận quyền chi tiết, CRM, hệ thống chăm sóc khách hàng, billing, quản lý booking, nền tảng quản lý campaign, quản lý tài khoản nâng cao, nền tảng kiểm duyệt, dashboard doanh nghiệp.
