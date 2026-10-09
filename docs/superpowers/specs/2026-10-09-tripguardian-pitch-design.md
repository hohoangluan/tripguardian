# Thiết kế chỉnh sửa deck pitching TripGuardian

## 1. Mục tiêu

Chỉnh lại deck pitching 15 phút cho ban giám khảo cuộc thi, giảng viên và mentor sau vòng phản biện nội dung và bố cục.

Deck mới phải giúp một người chưa biết TripGuardian hiểu được, theo đúng thứ tự:

1. người dùng đang gặp quyết định khó nào;
2. các công cụ hiện tại thực sự làm được gì;
3. TripGuardian tham gia ở bước nào và không tuyên bố điều gì quá bằng chứng;
4. cơ chế dữ liệu, AI và constraint vận hành ra sao;
5. phần nào đã chạy, phần nào mới được đánh giá offline và phần nào chưa chứng minh với người dùng.

Thông điệp chính:

> TripGuardian hỗ trợ người dùng chốt địa điểm trước khi xếp lịch, bằng bằng chứng có trạng thái và kiểm tra ràng buộc có thể giải thích.

Đầu ra:

- deck HTML 1920 × 1080 dùng `deck-stage`;
- PowerPoint `.pptx` chỉnh sửa được;
- bộ font gốc tải về cùng deck;
- slide nguồn ở phần phụ lục để phục vụ phản biện;
- không dùng claim thị trường, traction hoặc tác động người dùng khi chưa có dữ liệu.

## 2. Kết luận phản biện deck hiện tại

Vòng audit ngày 09/10/2026 dùng ảnh chụp mới của đủ 14 slide trong `designs/tripguardian-pitch/shots/`.

### 2.1. Điểm đang làm tốt

- Câu chuyện đi từ vấn đề tới giải pháp, dữ liệu, kỹ thuật và sản phẩm thử nghiệm.
- Màu sắc bám sản phẩm; các slide 5, 9 và 14 có nhịp trình chiếu rõ.
- Số liệu nội bộ lấy đúng từ file hiện tại và đã nêu giới hạn coverage.
- Ảnh giao diện là ảnh thật của sản phẩm, không dùng mockup giả.

### 2.2. Vấn đề cấu trúc và nội dung

| Slide hiện tại | Vấn đề khi nhìn từ phía giám khảo | Hướng sửa |
|---|---|---|
| 1 | Ảnh nền là screenshot landing còn chữ và nút mờ phía sau, tạo lớp chữ ma và làm cover khó đọc | Dùng `landing-poster.webp` không có UI; chỉ giữ một lớp thông điệp |
| 2 | Vấn đề hợp lý nhưng chưa có tình huống ra quyết định cụ thể | Thêm một ví dụ tổ hợp nơi đều hấp dẫn nhưng vượt thời gian/di chuyển |
| 3 | Số liệu tốt nhưng bốn tỉ lệ chưa dẫn tới một kết luận duy nhất | Chốt bằng câu: mỗi nguồn giải quyết một phần, người dùng vẫn gánh bước tổng hợp |
| 4 | Gom đối thủ thành “tìm kiếm” và “chatbot” là không chính xác; Wanderlog, Tripadvisor AI và Mindtrip đã có itinerary, AI, route hoặc booking | Thay bằng luồng thật của công cụ có tên và nguồn chính thức |
| 5 | Ba câu hỏi đúng nhưng chưa chứng minh vì sao TripGuardian khác | Đặt sau hai slide cạnh tranh để trở thành lời đáp cho khoảng trống đã chứng minh |
| 6 | Ảnh UI nhỏ; người xem khó biết hệ thống đã hiểu gì và bước tiếp theo là gì | Chỉ ra đầu vào, bản hiểu và quyết định chuyển bước trên ảnh |
| 7 | Connector khó theo dõi; thiếu khối Planning & Validation dù nội dung nói tới xếp lịch | Dựng lại thành một đường đọc trái → phải, có nhánh cảnh báo nhưng hội tụ rõ |
| 8 | Dòng nguồn chạm số slide; `Fact/Signal/Estimate` chưa nói rõ mỗi loại ảnh hưởng quyết định thế nào | Tách “loại bằng chứng” khỏi “quy tắc sử dụng”; sửa vùng chân slide |
| 9 | Mô hình `pass/fail/unknown` mới là tuyên bố khái niệm | Thêm một ví dụ địa điểm đóng cửa / thiếu bằng chứng / constraint thể chất |
| 10 | Bốn khối lớn nhưng nhiều khoảng rỗng; người nghe phải tự suy ra data flow | Thêm contract ra của từng giai đoạn và ranh giới offline/online |
| 11 | “Chạy trên dữ liệu thật” đứng cạnh “30 chuyến ẩn” dễ bị hiểu thành thử nghiệm người dùng thật | Tách rõ: dữ liệu địa điểm thật; bài đo 30 Trip State mô phỏng offline |
| 12 | Ba ảnh cho thấy sản phẩm nhưng ảnh thứ ba là trạng thái không xếp được lịch; chưa nói vì sao đây là hành vi đúng | Ghi rõ fail-closed và hành động phục hồi dành cho người dùng |
| 13 | Lộ trình hợp lý nhưng chưa liên kết trực tiếp với giới hạn đã nêu | Đổi thành slide “đã chứng minh / chưa chứng minh / bước đo tiếp theo” |
| 14 | Kết rõ nhưng chưa chuẩn bị câu phản biện lớn nhất | Giữ kết; thêm phụ lục nguồn và ranh giới claim sau slide kết |

### 2.3. Vấn đề font và tính di động

File PPTX hiện gọi `Lora`, `Be Vietnam Pro` và `JetBrains Mono` nhưng không nhúng font. Máy export cũng không có ba font này trong fontconfig; khi mở ở môi trường khác, PowerPoint hoặc LibreOffice thay font và làm đổi độ rộng, xuống dòng và vị trí.

Giải pháp đã được duyệt:

- giữ nguyên ba font thương hiệu;
- tải bản TTF chính thức từ Google Fonts vào `designs/tripguardian-pitch/fonts/`;
- lưu kèm giấy phép OFL;
- HTML dùng `@font-face` local, không phụ thuộc mạng;
- bundle hướng dẫn cài font trước khi mở PPTX;
- exporter không hỗ trợ nhúng font vào PPTX, vì vậy deck phải nói rõ yêu cầu cài font; QA sẽ render lại PPTX sau khi font được cài trong môi trường kiểm thử.

## 3. Định vị cạnh tranh đã hiệu chỉnh

Không dùng lập luận “công cụ hiện tại chỉ tìm kiếm hoặc sinh lịch”. Tài liệu công khai cho thấy:

| Công cụ | Luồng công khai được phép trình bày | Điều họ làm tốt |
|---|---|---|
| Google Maps | Tìm địa điểm → xem thông tin/review → lưu vào list → lấy chỉ đường | Định danh, vị trí, review, danh sách và điều hướng |
| Traveloka | Tìm theo điểm đến/ngày → chọn/lọc → điền thông tin → thanh toán → nhận và quản lý voucher | Giao dịch, giá, booking và vận hành sau đặt |
| Wanderlog | Tạo chuyến → thêm địa điểm → xếp theo ngày → xem bản đồ/thời gian → tối ưu route; kèm reservation, collaboration, budget | Lắp ráp lịch trình và quản lý chuyến đi |
| Tripadvisor AI | Mô tả chuyến đi → nhận lựa chọn cá nhân hóa → lưu lịch theo ngày → sửa, sắp xếp, chia sẻ → đi tới booking | AI planning dựa trên review, giá và availability |
| Mindtrip | Nêu sở thích → khám phá/lưu ý tưởng → dựng và chỉnh itinerary → cộng tác → booking → dùng map trong chuyến đi | Luồng AI travel end-to-end |

Nguồn chính thức, truy cập ngày 09/10/2026:

- Google Maps Help: <https://support.google.com/maps/answer/3184808?hl=en>
- Traveloka: <https://www.traveloka.com/en-vn/how-to/bookhotel>
- Wanderlog: <https://wanderlog.com/> và <https://help.wanderlog.com/hc/en-us/articles/13545624787867-Optimize-route>
- Tripadvisor AI: <https://www.tripadvisor.com/AIAssistant>
- Mindtrip Traveler FAQ: <https://resources.mindtrip.ai/travelers/help/traveler-faqs>

Kết luận cạnh tranh được phép nói:

> TripGuardian không khác biệt vì “có AI”, “có lịch trình” hay “có tối ưu tuyến”. Các sản phẩm khác đã làm tốt những phần đó. Điểm đặt cược của TripGuardian là biến bước chốt địa điểm thành một quyết định có evidence, trạng thái `pass/fail/unknown`, hard constraint và quyền xác nhận cuối của người dùng trước khi xếp lịch.

Không được nói:

- TripGuardian là sản phẩm duy nhất làm việc này;
- đối thủ không kiểm tra ràng buộc;
- đối thủ tạo lịch không khả thi;
- TripGuardian tốt hơn đối thủ khi chưa có benchmark đối đầu;
- tài liệu công khai không nêu một cơ chế đồng nghĩa sản phẩm chắc chắn không có cơ chế đó.

Khi cần so sánh một điểm chưa xác minh, dùng cách viết:

> Trong các tài liệu công khai đã đối chiếu, chưa thấy mô tả cơ chế này ở cùng mức chi tiết.

## 4. Chuỗi slide mới

Deck có 15 slide chính cho phần trình bày và một slide phụ lục không tính vào 15 phút.

| # | Tiêu đề | Câu hỏi của người nghe được trả lời | Nội dung chính | Thời lượng |
|---|---|---|---|---:|
| 1 | TripGuardian — Chọn đúng nơi trước khi xếp lịch | Sản phẩm là gì? | Tên, định vị một câu, phạm vi Đà Lạt | 0:25 |
| 2 | Người dùng không thiếu gợi ý; họ thiếu một quyết định có thể kiểm tra | Vấn đề cụ thể là gì? | Nhiều nguồn, đánh đổi, tổ hợp khó khả thi; một ví dụ cụ thể | 0:55 |
| 3 | Ở Việt Nam, một quyết định du lịch phải ghép nhiều nguồn | Vì sao phù hợp Việt Nam? | 53/47/35/32% và vai trò từng nguồn | 0:55 |
| 4 | Các công cụ hiện tại giải quyết những phần khác nhau của hành trình | Đối thủ là ai và luồng của họ là gì? | Năm luồng công khai có tên; ghi điều mỗi công cụ làm tốt | 1:25 |
| 5 | Khoảng trống nằm ở bước chốt lựa chọn dưới ràng buộc | TripGuardian chen vào đâu? | Hành trình Explore → Shortlist → Validate set → Schedule → Book/Navigate; đặt các công cụ lên đúng đoạn | 1:05 |
| 6 | TripGuardian bắt đầu từ quyết định, không bắt đầu từ một lịch sinh sẵn | Giá trị khác biệt là gì? | Ba câu hỏi cốt lõi và ranh giới claim | 0:50 |
| 7 | Từ một câu kể đến danh sách địa điểm do người dùng chốt | Người dùng đi qua sản phẩm như thế nào? | Hiểu → so sánh → kiểm tra tổ hợp → xếp lịch; UI thật | 1:00 |
| 8 | Trước khi xếp lịch, mỗi lựa chọn đi qua bốn lớp kiểm tra | Hệ thống ra quyết định như thế nào? | Trip State → Evidence → Decision → Validation/Planning; nhánh explain/unknown; ba phương án đánh đổi | 1:25 |
| 9 | Mỗi kết luận giữ nguyên loại bằng chứng và độ chắc chắn | Data & AI đổi mới ở đâu? | Fact/Signal/Estimate, quote, nguồn, freshness, review gate | 1:00 |
| 10 | AI hiểu ngôn ngữ; rule và validator giữ ranh giới | Tại sao có thể tin? | Ví dụ `pass/fail/unknown`; physical constraint; user hard constraint | 1:10 |
| 11 | Kiến trúc tách tri thức địa điểm khỏi bối cảnh chuyến đi | Hệ thống có bài bản và khả thi không? | Bốn module, contract ra, offline ghi/online đọc, live context theo request | 1:00 |
| 12 | Bản thử nghiệm chạy trên dữ liệu địa điểm Đà Lạt và bài đo offline | Hiện đã làm được đến đâu? | 1.696 nơi, 28.466 VERIFIED; 30 Trip State mô phỏng, 96,7%, 0 hard violation, 273 ms | 1:10 |
| 13 | Ba màn hình cho thấy người dùng kiểm soát quyết định | Sản phẩm có dùng được không? | Bản hiểu, so sánh khác biệt, fail-closed và cách phục hồi | 1:00 |
| 14 | Những gì đã chứng minh — và chưa chứng minh | Claim nào chắc, claim nào còn thiếu? | Implemented / offline-evaluated / chưa có user evidence; bước đo tiếp theo | 0:50 |
| 15 | Từ hàng nghìn nơi đến một chuyến đi có thể tin | Cần nhớ điều gì? | Nhắc lại định vị, mời demo và phản biện | 0:25 |
| A1 | Nguồn và ranh giới so sánh | Claim dựa vào đâu? | Link nguồn đối thủ, nguồn Việt Nam, nguồn dữ liệu nội bộ, ngày truy cập | Phụ lục |

Tổng nội dung chính: khoảng 14 phút 35 giây, còn lại dành cho chuyển slide.

## 5. Thiết kế slide cạnh tranh

### 5.1. Slide 4 — Luồng thật của công cụ hiện tại

Hình thức: năm hàng ngang, mỗi hàng có tên công cụ, một chuỗi 4–5 bước và một câu “mạnh ở”. Không dùng bảng tính năng với quá nhiều dấu tích.

Mỗi luồng chỉ trình bày điều nguồn chính thức mô tả. Tên sản phẩm là text; không tải logo nếu không cần.

### 5.2. Slide 5 — Vị trí của TripGuardian

Hình thức: một hành trình chung:

```text
Khám phá → Lưu/thu hẹp → Kiểm tra tập đã chọn → Xếp lịch → Đặt dịch vụ/điều hướng
```

Các công cụ khác được đặt ở đoạn họ công khai tập trung. TripGuardian nổi ở ba đoạn giữa, đặc biệt “Kiểm tra tập đã chọn”.

Footer bắt buộc:

> Đây là so sánh định vị từ tài liệu công khai, không phải benchmark chất lượng đối đầu.

## 6. Chính xác hóa bằng chứng nội bộ

Tại snapshot hiện tại:

- `data/serving/places.json`, build 08/10/2026: 1.696 địa điểm, 128 khu vực, 28.466 `VERIFIED`, 4.081 `UNCERTAIN`, 2.779 `OUTDATED`;
- `data/decision/eval.json`: 30 Trip State ẩn trong `config/eval_trips.yaml`, chạy pipeline thật trên dữ liệu serving; đây là mô phỏng offline, không phải 30 người dùng;
- kết quả: shortlist mục tiêu 8, `filled_rate = 0.967`, 0 hard violation, 0 `unknown`/`uncertain` trong danh sách chính, 0% near-duplicate, tối đa 273 ms;
- một kịch bản chưa đủ 8 nơi;
- chưa có bằng chứng về thời gian tiết kiệm, mức tin tưởng, retention, conversion hoặc tác động hành vi thật.

Slide 12 phải phân hai vùng:

- **Dữ liệu hiện có:** nơi và trạng thái feature;
- **Bài đo offline:** 30 Trip State mô phỏng và kết quả pipeline.

Không dùng cụm “30 chuyến ẩn” nếu không kèm từ “mô phỏng”.

## 7. Hệ thị giác và font

Giữ hệ hiện tại:

- giấy `#FAF7F2`, xanh Thông, Hồng sương, Nắng;
- Lora cho tiêu đề;
- Be Vietnam Pro cho nội dung;
- JetBrains Mono cho nhãn kỹ thuật và số;
- mọi font tối thiểu 24 px;
- tối đa một thông điệp chính và một minh họa chính trên mỗi slide;
- nguồn nằm trong vùng chân riêng, không đè số slide hoặc nội dung.

Font local cần có:

```text
fonts/
├── Lora-Regular.ttf
├── Lora-SemiBold.ttf
├── BeVietnamPro-Regular.ttf
├── BeVietnamPro-Medium.ttf
├── BeVietnamPro-SemiBold.ttf
├── BeVietnamPro-Bold.ttf
├── JetBrainsMono-Medium.ttf
├── JetBrainsMono-Bold.ttf
├── OFL-Lora.txt
├── OFL-BeVietnamPro.txt
├── OFL-JetBrainsMono.txt
└── README.md
```

Cover dùng `web/public/img/landing-poster.webp`, không dùng screenshot có UI làm ảnh nền.

## 8. Tiêu chí kiểm chứng

- HTML không gọi Google Fonts hoặc ảnh ngoài project.
- Browser báo đủ 16 slide, không lỗi console, không overflow.
- Mỗi slide được xem ở 1920 × 1080 và thumbnail.
- Slide 4 trình bày đủ tên và luồng của Google Maps, Traveloka, Wanderlog, Tripadvisor AI, Mindtrip.
- Slide 5 có disclaimer về nguồn công khai và không dùng khẳng định độc quyền.
- Slide 8 có khối Planning & Validation và connector đọc được từ trái sang phải.
- Slide 9/10 có ví dụ cụ thể, không chỉ thuật ngữ.
- Slide 12 ghi “Trip State mô phỏng offline”, không gọi là người dùng hoặc thử nghiệm thực địa.
- Slide 14 tách rõ implemented, offline-evaluated và unproven.
- PPTX có 16 slide, text/shape editable, animation count khớp HTML.
- PPTX được render lại trong môi trường có font local và so với ảnh HTML; không được có chữ cắt, xuống dòng sai hoặc chồng nhau.
- `fonts/README.md` nói rõ phải cài font trước khi mở PowerPoint vì exporter không nhúng font.

## 9. Phạm vi không làm

- Không dựng benchmark giả giữa TripGuardian và đối thủ.
- Không chụp hoặc sao chép giao diện đối thủ khi nguồn text đã đủ chứng minh luồng.
- Không thay code sản phẩm ngoài `designs/tripguardian-pitch/`.
- Không tuyên bố product-market fit, traction, tác động hoặc ưu thế chất lượng.
- Không đổi font thương hiệu sang font hệ thống.
- Không raster hóa toàn slide để che lỗi font hoặc bố cục.
