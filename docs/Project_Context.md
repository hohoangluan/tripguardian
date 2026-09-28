# TripGuardian — Project Context

## 1. Tóm tắt dự án

TripGuardian là hệ thống hỗ trợ người dùng **chọn đúng địa điểm trước khi tạo lịch trình**. Phạm vi kiểm chứng ban đầu là Đà Lạt.

Người dùng không cần chuẩn bị sẵn một danh sách hoàn chỉnh. Họ có thể bắt đầu từ:

* một ý tưởng chuyến đi còn mơ hồ;
* một số địa điểm đã lưu từ TikTok, Facebook, Google Maps hoặc nguồn khác;
* các địa điểm nhất định muốn đi;
* hoặc một lịch trình sơ bộ cần kiểm tra.

TripGuardian sẽ:

1. hiểu nhu cầu, kinh nghiệm và các ràng buộc của chuyến đi, bắt đầu từ User Profile nếu người dùng cho phép;
2. tìm và kiểm tra các địa điểm phù hợp;
3. loại hoặc cảnh báo các lựa chọn không khả thi;
4. giúp người dùng so sánh và chọn địa điểm;
5. kiểm tra tổ hợp đã chọn;
6. xây dựng lịch trình khả thi và giải thích các đánh đổi.

TripGuardian không được định vị đơn thuần là một **AI tạo lịch trình**. Giá trị chính nằm ở ba câu hỏi:

> Nơi nào phù hợp với chuyến đi này?
> Vì sao nên chọn nơi đó thay vì lựa chọn khác?
> Các địa điểm sau khi chọn có thực sự đi được cùng nhau hay không?

Tài liệu này trả lời *vì sao* và *cho ai*. Luồng hệ thống (constraint, chọn địa điểm, khả thi, xếp lịch, độ vững, dự phòng) nằm ở `docs/ARCHITECTURE.md`; chức năng theo vai trò và màn hình nằm ở `docs/Role_Web_Functional_Design.md`; brief cho designer nằm ở `docs/UX_Design_Brief.md`; dữ liệu địa điểm nằm ở `docs/CORPUS.md`.

---

## 2. Problem: nhiều thông tin nhưng khó ra quyết định

Người đi du lịch hiện không thiếu gợi ý. Họ có thể tìm địa điểm qua TikTok, Facebook, YouTube, Google Maps, blog, review, hội nhóm hoặc các nền tảng du lịch.

Khó khăn xuất hiện khi phải biến các gợi ý rời rạc đó thành một chuyến đi thực tế.

Người dùng thường phải tự:

* kiểm tra địa điểm có còn hoạt động hay không;
* đối chiếu giờ mở cửa, giá, vị trí và thời gian di chuyển;
* đánh giá địa điểm có phù hợp với sở thích và người đồng hành;
* nhận ra những địa điểm có trải nghiệm gần giống nhau;
* quyết định nơi nào nên đi và nơi nào nên bỏ;
* kiểm tra liệu tất cả lựa chọn có ghép được vào quỹ thời gian và ngân sách.

Đây là bài toán **ra quyết định dưới nhiều ràng buộc**, không chỉ là bài toán tìm địa điểm hay tối ưu tuyến đường.

Nghiên cứu trong du lịch cũng ghi nhận hiện tượng quá tải lựa chọn: khi số phương án tăng, người dùng có thể khó quyết định hơn hoặc dễ hối tiếc sau lựa chọn [1].

---

# 3. Người dùng mục tiêu

TripGuardian tập trung vào người **tự lên kế hoạch cho chuyến du lịch tự túc**, thay vì người đi theo tour có lịch trình cố định.

Trong phạm vi MVP, ưu tiên:

* chuyến đi khoảng 2–4 ngày;
* cá nhân, cặp đôi hoặc nhóm nhỏ;
* người tự lựa chọn điểm đến và hoạt động;
* sử dụng xe máy, ô tô, taxi hoặc dịch vụ gọi xe;
* phải tự tổng hợp thông tin từ nhiều nguồn.

Người dùng được chia thành **hai nhóm chính theo mức độ kinh nghiệm với điểm đến**.

## 3.1. Nhóm A — Người lần đầu đến Đà Lạt

Đây là người chưa có nhiều hiểu biết thực tế về địa điểm, khoảng cách, khu vực hoặc cách phân bổ thời gian tại Đà Lạt.

Họ thường gặp các vấn đề:

* không biết nên bắt đầu tìm từ đâu;
* khó phân biệt địa điểm thực sự phù hợp với địa điểm chỉ nổi tiếng;
* khó ước lượng khoảng cách và thời gian thực tế;
* dễ chọn quá nhiều địa điểm;
* khó đánh giá hai địa điểm có trải nghiệm tương tự nhau;
* không biết một ngày nên đi bao nhiêu nơi.

Nhóm này cần TripGuardian hỗ trợ nhiều hơn ở:

**Khám phá → Thu hẹp lựa chọn → Giải thích → Kiểm tra khả thi.**

### Các trạng thái thường gặp

**Chưa biết mình muốn gì**

> “Tôi đi Đà Lạt 3 ngày với người yêu nhưng chưa biết nên đi đâu.”

Hệ thống cần giúp khám phá phong cách chuyến đi trước khi đề xuất.

**Đã lưu một số địa điểm**

> “Tôi lưu khoảng 15 chỗ trên TikTok nhưng không biết nên chọn chỗ nào.”

Hệ thống cần kiểm tra, nhóm và giảm danh sách thành các lựa chọn phù hợp hơn.

---

## 3.2. Nhóm B — Người đã từng đến Đà Lạt hoặc có kinh nghiệm

Nhóm này đã biết một phần về điểm đến và thường không cần được giới thiệu lại các địa điểm cơ bản.

Họ có thể:

* đã từng đi Đà Lạt;
* biết một số khu vực và khoảng cách;
* có những nơi chắc chắn muốn quay lại;
* muốn tìm trải nghiệm mới;
* muốn tránh lặp lại chuyến đi trước;
* hoặc đã có sẵn một kế hoạch tương đối rõ.

Vấn đề của họ thường là:

* tìm địa điểm mới phù hợp với sở thích;
* kết hợp địa điểm mới với những nơi đã muốn đi;
* kiểm tra thông tin đã thay đổi từ lần đi trước;
* tối ưu một danh sách có sẵn;
* xử lý các ràng buộc phức tạp hơn.

Nhóm này cần TripGuardian hỗ trợ nhiều hơn ở:

**Kiểm tra → So sánh → Tìm lựa chọn mới → Tối ưu → Xử lý xung đột.**

### Các trạng thái thường gặp

**Có địa điểm bắt buộc**

> “Tôi đã đi Đà Lạt rồi. Lần này chắc chắn muốn quay lại Hồ Tuyền Lâm và tìm thêm vài chỗ mới.”

Các địa điểm này trở thành **anchor** của chuyến đi.

**Đã có plan sơ bộ**

> “Tôi đã lên 8 địa điểm cho 3 ngày, kiểm tra giúp xem có hợp lý không.”

Hệ thống không cần tạo lại từ đầu mà kiểm tra và đề xuất điều chỉnh.

---

## 3.3. Kinh nghiệm và trạng thái bắt đầu là hai yếu tố khác nhau

Việc đã từng đến Đà Lạt không đồng nghĩa người dùng đã có plan.

Tương tự, người lần đầu đi vẫn có thể đã lưu rất nhiều địa điểm.

Do đó TripGuardian xác định hai yếu tố độc lập:

```text
Experience
├── First-time visitor
└── Returning / experienced visitor

Starting state
├── Chưa có ý tưởng rõ
├── Có một số địa điểm đã lưu
├── Có các địa điểm bắt buộc
└── Có lịch trình sơ bộ
```

Experience quyết định **mức độ hướng dẫn**.

Starting state quyết định **điểm bắt đầu của luồng**.

---

# 4. Vì sao bài toán phù hợp với Đà Lạt?

Theo nghiên cứu Traveloka và YouGov với gần 12.000 người tại chín thị trường châu Á–Thái Bình Dương, nhóm người trả lời tại Việt Nam:

* 53% sử dụng mạng xã hội để tìm thông tin điểm đến mới;
* 41% tham khảo bạn bè hoặc người thân;
* 41% tham khảo website và blog du lịch;
* trong giai đoạn lập kế hoạch, 47% sử dụng mạng xã hội, 35% sử dụng nền tảng du lịch và 32% sử dụng các ứng dụng như Google Maps, Waze hoặc Grab [2].

Các nguồn này phục vụ những mục đích khác nhau.

Mạng xã hội tốt cho khám phá.
Maps tốt cho vị trí và đường đi.
Review phản ánh trải nghiệm.
Website chính thức tốt cho thông tin vận hành.

Người dùng vẫn phải tự nối các nguồn thành một quyết định.

Đà Lạt cũng có nhiều loại trải nghiệm nằm ở các khu vực khác nhau. Trong các thời điểm đông khách, giao thông và lượng người có thể làm thay đổi đáng kể tính khả thi của một lịch trình [3], [4].

Vì vậy, khoảng cách, thời gian và điều kiện di chuyển cần tham gia ngay từ **bước lựa chọn địa điểm**, không chỉ sau khi danh sách đã được chốt.

---

# 5. Nhu cầu cốt lõi của người dùng

Người dùng không thực sự cần TripGuardian để nhận thêm một danh sách địa điểm.

Họ cần:

* **giảm công sức nghiên cứu:** không phải mở nhiều nguồn rồi tự tổng hợp;
* **giảm rủi ro chọn sai:** tránh nơi không phù hợp với chuyến đi;
* **thu hẹp lựa chọn:** biết nơi nào đáng cân nhắc và nơi nào có thể bỏ;
* **hiểu sự đánh đổi:** biết vì sao A phù hợp hơn B;
* **kiểm tra tính khả thi:** biết các lựa chọn có thực sự đi được cùng nhau;
* **giữ quyền quyết định:** người dùng vẫn là người chọn địa điểm cuối cùng;
* **có phương án thay thế:** biết phải thay đổi gì khi kế hoạch không khả thi.

Hai nhóm người dùng có cùng nhu cầu cuối cùng nhưng khác điểm bắt đầu:

|                           | Lần đầu đi | Đã có kinh nghiệm |
| ------------------------- | ---------- | ----------------- |
| Khám phá địa điểm         | Cao        | Trung bình        |
| Cần hướng dẫn             | Cao        | Thấp hơn          |
| So sánh lựa chọn          | Cao        | Cao               |
| Tìm trải nghiệm mới       | Trung bình | Cao               |
| Kiểm tra danh sách có sẵn | Trung bình | Cao               |
| Kiểm tra khả thi          | Cao        | Cao               |
| Giữ địa điểm bắt buộc     | Có thể có  | Thường gặp        |

---

# 6. User Profile và cá nhân hóa

TripGuardian không yêu cầu người dùng phải mô tả toàn bộ sở thích từ đầu.

Nếu được người dùng cho phép, hệ thống xây dựng một **User Profile** từ các tín hiệu hành vi trước đó để làm điểm xuất phát cho recommendation.

Mục tiêu của User Profile là giúp TripGuardian hiểu:

* người dùng thường lựa chọn kiểu trải nghiệm nào;
* gần đây đang quan tâm đến điều gì;
* đã từng trải nghiệm những gì;
* đâu có thể là trải nghiệm mới đối với họ;
* một số đặc điểm thường gặp trong cách họ đi chơi.

User Profile chỉ là **prior phục vụ cá nhân hóa**, không phải sự thật tuyệt đối về người dùng và không được dùng để thay thế constraint của chuyến hiện tại.

---

## 6.1. Nguồn dữ liệu

User Profile có thể được xây dựng từ các nguồn người dùng chủ động cho phép:

```text
User Signals
│
├── Google Maps Timeline
├── Google Maps Saved Places
├── TikTok / YouTube activity
├── Search / travel-related browsing
├── Past TripGuardian trips
└── User decisions inside TripGuardian
```

Các nguồn cung cấp những tín hiệu khác nhau:

| Nguồn                        | Giá trị chính                                               |
| ---------------------------- | ----------------------------------------------------------- |
| Google Maps Timeline         | những nơi và loại trải nghiệm người dùng thực sự đã đi      |
| Saved Places                 | nơi người dùng có ý định hoặc mong muốn trải nghiệm         |
| TikTok / YouTube / Search    | những chủ đề và trải nghiệm đang được quan tâm              |
| Past TripGuardian Trips      | lựa chọn và trải nghiệm từ các chuyến trước                 |
| Current TripGuardian Actions | preference thể hiện qua add, remove, lock, compare, replace |

Không phải mọi hành vi đều phản ánh preference.

Các địa điểm mang tính routine như nhà, trường học, nơi làm việc hoặc nhu cầu hằng ngày cần được tách khỏi các hành vi leisure/travel trước khi sử dụng cho cá nhân hóa.

Trên thực tế, tín hiệu bên ngoài chỉ đến qua file hoặc kết nối do người dùng chủ động tạo: file Google Takeout (Saved Places), file Timeline xuất từ điện thoại (Google hiện lưu Timeline trên thiết bị), hoặc file "Tải dữ liệu của bạn" của TikTok. TripGuardian không đọc ngầm tài khoản người dùng. Mọi nguồn đều tùy chọn; không có nguồn nào thì profile bắt đầu từ các quyết định trong TripGuardian.

---

## 6.2. Cấu trúc User Profile

```text
USER PROFILE
│
├── Demonstrated Preferences
├── Recent Interests
├── Experience History
└── Behavioral Defaults
```

### Demonstrated Preferences

Các kiểu trải nghiệm người dùng thường xuyên lựa chọn trong hành vi thực tế.

Ví dụ:

```text
coffee       high
nature       high
quiet        medium
photography  medium
```

Đây là preference dùng để ranking, không phải hard constraint.

---

### Recent Interests

Những trải nghiệm hoặc chủ đề người dùng đang chủ động tìm hiểu gần đây.

Ví dụ:

```text
camping      rising
trekking     rising
pottery      medium
coffee       stable
```

Recent Interest ưu tiên tín hiệu mới hơn.

Các hành động có chủ đích như:

```text
search
save
share
saved place
```

có trọng số cao hơn việc chỉ tình cờ xem một nội dung.

Recent Interest giảm trọng số theo thời gian để tránh một sở thích tạm thời trở thành preference dài hạn.

---

### Experience History

Ghi nhận những loại trải nghiệm hoặc địa điểm người dùng đã từng trải qua.

Ví dụ:

```text
coffee       extensive
waterfall    moderate
camping      none
pottery      none
```

Experience History giúp TripGuardian:

* hạn chế lặp lại quá nhiều trải nghiệm quen thuộc;
* tìm trải nghiệm mới cho returning visitor;
* xác định một recommendation có thực sự mới đối với người dùng hay không.

`Chưa từng trải nghiệm` không đồng nghĩa với `không thích`.

Nếu không đủ evidence:

```text
preference = unknown
```

thay vì tự suy thành:

```text
preference = dislike
```

---

### Behavioral Defaults

Một số hành vi lặp lại có thể dùng làm giá trị mặc định khi lập chuyến đi.

Ví dụ:

```text
pace                 balanced
typical dwell time   60–90 phút
travel tolerance     medium
crowd tolerance      low
```

Behavioral Defaults chỉ giúp giảm input ban đầu. Người dùng luôn có thể thay đổi chúng cho từng chuyến.

---

## 6.3. Exploration Gap

TripGuardian có thể tìm những trải nghiệm người dùng đang quan tâm nhưng chưa từng hoặc ít trải nghiệm.

```text
High Recent Interest
        +
Low / No Experience
        ↓
Exploration Gap
```

Ví dụ:

```text
Camping

Recent Interest
→ High

Experience History
→ None

Result
→ Potential New Experience
```

Nhờ đó hệ thống không chỉ hỏi:

> Người dùng thường thích gì?

mà còn có thể xác định:

> Người dùng có thể muốn khám phá điều gì tiếp theo?

Điều này giúp tránh việc personalization chỉ liên tục đề xuất những trải nghiệm giống lịch sử trước đó.

---

# 7. Current Trip Context và User Profile

User Profile mô tả xu hướng tương đối dài hạn.

Mỗi chuyến đi vẫn có context riêng:

```text
Trip Context
│
├── dates
├── duration
├── companions
├── accommodation / base
├── mobility
├── anchors
├── physical constraints
├── user hard constraints
└── trip-specific override
```

Context của chuyến hiện tại luôn được ưu tiên hơn behavior lịch sử.

Ví dụ:

```text
User Profile
├── hiking = high
├── nature = high
└── outdoor = high

Current Trip
├── đi cùng bố mẹ
└── hạn chế đi bộ
```

TripGuardian không được ưu tiên hiking chỉ vì lịch sử cho thấy user thường thích loại trải nghiệm đó.

Thứ tự xử lý:

```text
Physical Constraints
        ↓
User Hard Constraints
        ↓
Current Trip Override
        ↓
Recent Interests
        ↓
Demonstrated Preferences
```

---

## 7.1. Trip-specific Override

TripGuardian không hỏi lại toàn bộ preference ở mỗi chuyến.

User Profile được dùng làm mặc định.

Hệ thống chỉ cần thu thập những gì **khác với bình thường hoặc chưa biết nhưng có khả năng thay đổi recommendation**.

Ví dụ:

```text
Chuyến này:

[ Theo gu thường ngày ]

[ Muốn thử điều mới ]

[ Đi cùng đối tượng khác ]

[ Có yêu cầu riêng ]
```

Ví dụ user nói:

> Lần này tôi không muốn đi cà phê, muốn thử hoạt động ngoài trời nhiều hơn.

Hệ thống có thể tạo:

```text
Long-term Profile

coffee = high
outdoor = medium

Current Session

coffee = avoid
outdoor = high
novelty = high
```

Current Trip Override chỉ áp dụng cho chuyến hiện tại và không tự động thay đổi User Profile dài hạn.

---

# 8. Cập nhật User Profile

User Profile không phải dữ liệu tĩnh.

Nó được cập nhật dần từ hành vi bên ngoài và các quyết định của người dùng trong TripGuardian.

```text
External Signals
        +
TripGuardian Decisions
        ↓
User Events
        ↓
Interpret Signal
        ↓
Session Profile
        ↓
Repeated / Strong Evidence?
        │
   ┌────┴────┐
   │         │
  NO        YES
   │         │
Session   Long-term
only      Profile Update
```

Hệ thống không cập nhật long-term profile chỉ từ một click hoặc một hành động đơn lẻ.

---

## 8.1. Session Profile

Mỗi chuyến đi có một Session Profile riêng.

Session Profile phản ánh preference đang thể hiện trong chuyến hiện tại và có thể thay đổi nhanh dựa trên hành vi của user.

Ví dụ:

```text
Long-term Profile

coffee = high
nature = high

Current Session

coffee ↓
outdoor ↑
novelty ↑
```

Nếu user liên tục bỏ café và chọn outdoor activities, recommendation trong session hiện tại phải thích nghi ngay.

Điều đó không đồng nghĩa long-term preference về café bị thay đổi.

---

## 8.2. Tín hiệu từ hành vi trong TripGuardian

Các hành động mang mức độ thông tin khác nhau.

```text
Strong Signal
│
├── lock / must-go
├── explicit dislike
├── repeated remove
├── select after comparison
└── show more like this
│
Medium Signal
│
├── add
├── save
├── compare
└── replace
│
Weak Signal
│
├── open detail
├── view
└── dwell
│
Very Weak
│
└── impression
```

Không được coi:

```text
not clicked = dislike
```

Một địa điểm xuất hiện nhưng user không tương tác chưa đủ để giảm preference tương ứng.

---

## 8.3. Khai thác lý do của quyết định

Một hành động `remove` không đồng nghĩa user không thích toàn bộ trải nghiệm của địa điểm.

Ví dụ:

```text
Remove Waterfall A
```

nếu lý do là:

```text
Xa quá
```

thì hệ thống nên cập nhật:

```text
travel tolerance ↓
```

không phải:

```text
nature preference ↓
```

TripGuardian có thể thu thập lý do ngắn khi phù hợp:

```text
Vì sao bạn bỏ địa điểm này?

[ Xa quá ]
[ Đông quá ]
[ Giá cao ]
[ Không hứng thú ]
[ Đã từng đi ]
```

Từ đó:

```text
Xa quá
→ travel tolerance

Đông quá
→ crowd tolerance

Giá cao
→ price sensitivity

Không hứng thú
→ experience preference

Đã từng đi
→ experience history
```

Việc hỏi lý do chỉ nên xuất hiện khi thông tin đó hữu ích cho recommendation tiếp theo.

---

## 8.4. Học từ Compare

Khi user chọn giữa hai địa điểm tương tự, TripGuardian có thể học từ phần khác biệt giữa chúng.

Ví dụ:

```text
Place A
quiet
far
nature

Place B
busy
near
nature
```

Nếu user chọn A, hệ thống không cần tăng `nature` vì cả hai đều có thuộc tính này.

Tín hiệu quan trọng hơn là:

```text
quietness > shorter travel
```

Các lựa chọn pairwise như vậy giúp hệ thống hiểu yếu tố nào quan trọng hơn đối với user.

---

## 8.5. Cập nhật sau chuyến đi

Sau khi chuyến đi kết thúc, hệ thống có thể sử dụng outcome để cập nhật profile.

```text
Planned Trip
      ↓
Actual Trip
      ↓
Visited Places
      ↓
User Feedback
      ↓
Experience History
      +
Preference Evidence
```

Một địa điểm thực sự được ghé thăm chỉ chứng minh:

```text
experienced = true
```

không tự động chứng minh:

```text
liked = true
```

Feedback hoặc các quyết định lặp lại mới được dùng để tăng confidence về preference.

---

## 8.6. Long-term Profile Update

Một preference dài hạn chỉ nên thay đổi khi có:

* nhiều tín hiệu độc lập;
* hành vi lặp lại;
* tín hiệu có chủ đích mạnh;
* hoặc explicit feedback từ user.

Ví dụ:

```text
Trip 1
remove coffee

Trip 2
remove coffee

Trip 3
prefer outdoor over coffee

        ↓

coffee preference may decrease
```

Một hành động trong một trip không đủ để overwrite long-term profile.

---

## 8.7. Confidence, Trend và Freshness

Các thuộc tính trong User Profile cần giữ mức độ chắc chắn.

Ví dụ:

```text
Nature
value       high
confidence  high
trend       stable

Coffee
value       high
confidence  high
trend       declining

Camping
value       medium
confidence  medium
trend       rising
```

`Confidence` thể hiện hệ thống chắc chắn đến mức nào.

`Trend` giúp phân biệt preference ổn định với một interest đang tăng hoặc giảm.

`Freshness` giúp tín hiệu mới có ảnh hưởng phù hợp hơn tín hiệu đã quá cũ.

---

# 9. Vai trò của User Profile trong Recommendation

User Profile không trực tiếp quyết định địa điểm nào được chọn.

Nó chỉ cung cấp tín hiệu personalization sau khi các constraint cần thiết đã được kiểm tra.

```text
Place Intelligence
        +
Trip Context
        +
User Profile
        ↓
Candidate Retrieval
        ↓
Constraint Screening
        ↓
Context Fit
        ↓
Preference Fit
+
Recent Interest
+
Novelty
+
Diversity
        ↓
Shortlist
```

Có thể hiểu:

```text
Constraints
→ địa điểm nào có thể đi

Trip Context
→ địa điểm nào phù hợp với chuyến này

User Profile
→ trong các lựa chọn hợp lệ, đâu có khả năng phù hợp hơn với user
```

---

# 10. Vòng lặp cá nhân hóa

```text
External Behavior
Maps / Saved / Social / Search
            ↓
        User Profile
            ↓
         Start Trip
            ↓
       Recommendation
            ↓
        User Decisions
            ↓
       Session Profile
            ↓
 Recommendation adapts
            ↓
          Trip Result
            ↓
Aggregate + Confidence
            ↓
   Long-term Profile Update
            ↓
          Next Trip
```

External data chủ yếu giúp giải quyết **cold start**.

Sau khi user sử dụng TripGuardian nhiều hơn, các quyết định thực tế trong hệ thống trở thành nguồn personalization quan trọng hơn vì chúng đi kèm với context của từng lựa chọn.

---

# 11. Nguyên tắc User Profile

TripGuardian tuân theo các nguyên tắc:

```text
Không hỏi lại điều hệ thống đã biết đủ chắc chắn.

Observed behavior là evidence, không phải truth.

Unknown không đồng nghĩa dislike.

Visited không đồng nghĩa liked.

Recent interest có thể khác long-term preference.

Current trip context được ưu tiên hơn historical behavior.

Một event đơn lẻ không overwrite long-term profile.

Personalization phải hỗ trợ khám phá, không tạo filter bubble.

Người dùng luôn có thể sửa hoặc override inference của hệ thống.
```

---

# 12. Khám phá nhu cầu

Không phải người dùng nào cũng diễn đạt rõ mình muốn gì.

Người lần đầu đi thường cần nhiều hỗ trợ hơn trong bước này.

Thay vì hỏi một questionnaire cố định, TripGuardian sử dụng hội thoại ngắn và chỉ hỏi khi câu trả lời có thể thay đổi kết quả.

Ví dụ:

> Bạn muốn chuyến đi thiên về nghỉ ngơi hay khám phá nhiều nơi?

> Bạn thấy thoải mái với khoảng bao nhiêu thời gian di chuyển trong một ngày?

> Có kiểu địa điểm nào bạn chắc chắn không muốn đi không?

Người dùng luôn có thể:

* chọn một gợi ý;
* nhập tự do;
* chọn `Không chắc`;
* bỏ qua;
* hoặc yêu cầu hệ thống đề xuất trước.

Hệ thống không hỏi lại những gì đã biết.

Khi đã có User Profile, profile được dùng làm mặc định: bước khám phá chỉ hỏi những gì **khác với bình thường hoặc còn chưa biết** cho chuyến này (mục 7.1). Khi chưa có profile (cold start), hệ thống bắt đầu từ chính chuyến đi.

Trước khi tìm địa điểm, TripGuardian hiển thị một bản hiểu nhu cầu ngắn gồm:

* thông tin chuyến đi;
* anchors;
* hard constraints;
* preferences, đánh dấu phần lấy từ User Profile;
* phần còn chưa chắc.

Người dùng có thể sửa trực tiếp, kể cả các suy luận lấy từ profile.

## 12.1. Nguyên tắc đặt câu hỏi

| # | Nguyên tắc | Căn cứ |
| - | ---------- | ------ |
| 1 | **Chỉ hỏi câu có giá trị thông tin cao nhất.** Mỗi lượt chọn câu mà câu trả lời làm thay đổi tập ứng viên nhiều nhất; câu nào không đổi kết quả thì bỏ. | Chọn câu hỏi để học nhanh preference của user mới trong cold start [11]; hỏi làm rõ khi yêu cầu mơ hồ, nhiều mặt hoặc thiếu [12]. |
| 2 | **Hỏi làm rõ trước khi lập kế hoạch.** Agent phải tự nhận ra thông tin còn thiếu và hỏi trước khi gọi tool / xếp lịch, không tự đoán. | Ask-before-Plan: lập kế hoạch du lịch thất bại khi agent không phát hiện nhu cầu cần làm rõ [13]. |
| 3 | **Constraint phải rõ trước khi lập kế hoạch.** Ràng buộc cứng (ngân sách, thời gian, thể chất) phải được biết hoặc đánh dấu `unknown` trước khi tìm địa điểm, đúng thứ tự xử lý ở mục 7; không có nghĩa là luôn hỏi chúng đầu tiên (12.3). | TravelPlanner tách hard constraint lấy từ yêu cầu user với commonsense constraint; agent LLM thường bỏ sót ràng buộc [14]. |
| 4 | **Hỏi về cách dùng, không hỏi thuộc tính.** Người lần đầu đi không biết thuộc tính nào quan trọng; hỏi "chuyến này để làm gì / đi với ai" dễ trả lời hơn "thích loại POI nào". | Usage-related questions dễ trả lời kể cả với người thiếu kiến thức domain [8]. |
| 5 | **Có gợi ý + cho nhập tự do.** Mỗi câu có lựa chọn sẵn (guidance cao) nhưng không khóa input. | Phương thức elicitation có guidance cao cho kết quả khớp hơn guidance thấp [9]. |
| 6 | **`Không chắc` là câu trả lời hợp lệ nhưng không phải điểm dừng.** Ghi `unknown`, không suy thành không thích; sau đó khai thác gián tiếp qua đề xuất + phản hồi (compare, critique) thay vì hỏi dồn. | Lựa chọn "không ý kiến" dễ thành lối tắt giảm công sức trả lời [16]; critiquing học preference từ phản hồi trên đề xuất cụ thể [17]; CRS kết hợp hỏi và đề xuất [24]. |
| 7 | **Làm rõ từ chủ quan.** "Chill", "yên tĩnh", "đẹp" mang nghĩa khác nhau với từng người; hỏi lại nghĩa trước khi dùng làm tiêu chí. | Thuộc tính chủ quan là thách thức riêng của conversational recommendation [10]. |
| 8 | **Hỏi "vì sao" để tới nhu cầu gốc, tối đa 1–2 bậc.** "Muốn đi đồi chè" → vì sao → "muốn chỗ thoáng, ít người" mở ra lựa chọn thay thế. | Laddering: nối thuộc tính → hệ quả → giá trị người dùng [18]. |
| 9 | **Để LLM sinh câu hỏi mở / ví dụ biên** khi user mô tả mơ hồ, giúp lộ điều user chưa nghĩ tới. Câu trả lời vẫn được chuẩn hóa về field của Trip Context. | Generative active task elicitation: câu hỏi do LM sinh ra thu được nhiều thông tin hơn và user thấy tốn ít công sức hơn [15]. |
| 10 | **Cho phép trả lời bằng hình** khi user khó diễn đạt kiểu trải nghiệm. | Chọn ảnh du lịch để suy ra travel profile, giải quyết cold start [21]. |

## 12.2. Bộ câu hỏi

Bộ câu hỏi là **ngân hàng**, không phải form; nhóm A–I là nhóm chủ đề, **không phải thứ tự hỏi** (thứ tự do 12.3 quyết định). Hệ thống chỉ lấy câu còn thiếu và có khả năng đổi kết quả (12.1 #1); câu đã biết từ input, anchors hoặc User Profile thì hiển thị để xác nhận thay vì hỏi lại (mục 7.1). Mọi câu đều có `Không chắc` và `Bỏ qua`.

**A. Khung chuyến đi** — gần như luôn cần; thiếu thì không lập được lịch.

| Câu hỏi mẫu | Lựa chọn gợi ý | Ghi vào |
| ----------- | -------------- | ------- |
| Bạn đi ngày nào, trong mấy ngày? | chọn ngày / "chưa chốt, khoảng … ngày" | `dates`, `duration` |
| Bạn ở khu nào? | chọn trên bản đồ / "chưa đặt" | `accommodation / base` |
| Bạn di chuyển trong Đà Lạt bằng gì? | tự lái xe máy · ô tô riêng · Grab/taxi · chưa biết | `mobility` |
| Có mốc giờ cố định nào không? | giờ nhận/trả phòng · giờ xe/máy bay · lịch hẹn | `user hard constraints` |

**B. Người đồng hành** — thay đổi mạnh tập địa điểm phù hợp.

| Câu hỏi mẫu | Lựa chọn gợi ý | Ghi vào | Căn cứ |
| ----------- | -------------- | ------- | ------ |
| Bạn đi cùng ai? | một mình · cặp đôi · bạn bè · gia đình có trẻ nhỏ · có người lớn tuổi | `companions` | [19] (quan hệ, tương tác xã hội là động cơ du lịch) |
| (nếu đi nhóm) Trong nhóm có ai sở thích khác hẳn hoặc là người chốt quyết định? | có · không · không chắc | `companions` | [22] (quyết định nhóm trong du lịch) |

**C. Ràng buộc thể chất và tiếp cận** — hard constraint, fail-closed.

| Câu hỏi mẫu | Lựa chọn gợi ý | Ghi vào | Căn cứ |
| ----------- | -------------- | ------- | ------ |
| Có ai ngại đi bộ xa, leo dốc/bậc thang, hoặc cần lối đi bằng phẳng? | đi bộ ≤ ~15 phút · tránh dốc/bậc · không giới hạn | `physical constraints` | [23] (nhu cầu tiếp cận: vận động, thị giác, thính giác, nhận thức; gồm cả trẻ nhỏ, người lớn tuổi) |
| Có ai say xe đường đèo, sợ độ cao, dị ứng hoặc ăn kiêng? | chọn nhiều | `physical constraints` | [23] |

**D. Hard constraint của người dùng**

| Câu hỏi mẫu | Lựa chọn gợi ý | Ghi vào |
| ----------- | -------------- | ------- |
| Mức chi cho ăn uống và vé tham quan, mỗi người mỗi ngày? | các khoảng tiền · không quan trọng | `user hard constraints` |
| Có kiểu địa điểm nào chắc chắn không muốn đi? | chọn nhiều + nhập tự do | `user hard constraints` |

**E. Anchors**

| Câu hỏi mẫu | Lựa chọn gợi ý | Ghi vào |
| ----------- | -------------- | ------- |
| Có nơi nào bạn nhất định muốn đi hoặc đã lưu sẵn? | dán link TikTok / Maps · gõ tên | `anchors` |
| Nếu không đủ thời gian, nơi nào có thể bỏ trước? | xếp thứ tự các anchor | `anchors` (độ ưu tiên) |

**F. Nhịp độ và mức chịu đựng** — soft; lấy mặc định từ Behavioral Defaults nếu có (mục 6.2).

| Câu hỏi mẫu | Lựa chọn gợi ý | Ghi vào |
| ----------- | -------------- | ------- |
| Chuyến này thiên về nghỉ ngơi hay khám phá nhiều nơi? | thong thả · cân bằng · đi nhiều | `pace` |
| Một chặng di chuyển tối đa bao lâu thì bạn vẫn thấy ổn? | ≤ 15 · ≤ 30 · ≤ 60 phút | `travel tolerance` |
| Chỗ đông người thì sao? | tránh · chấp nhận nếu đáng · không ngại | `crowd tolerance` |
| Bạn hay bắt đầu ngày lúc mấy giờ? | sớm (săn mây) · bình thường · muộn | Behavioral Defaults |
| Nếu trời mưa, bạn muốn? | đổi sang trong nhà · giữ nguyên nếu được · để hệ thống đề xuất | `trip-specific override` |

**G. Mục đích và kiểu trải nghiệm** — soft; hỏi theo cách dùng (12.1 #4).

| Câu hỏi mẫu | Lựa chọn gợi ý | Ghi vào | Căn cứ |
| ----------- | -------------- | ------- | ------ |
| Chuyến này chủ yếu để làm gì? | thoát khỏi nhịp thường ngày · thư giãn · gắn kết người đi cùng · thiên nhiên · văn hóa/ẩm thực địa phương · chụp ảnh · thử điều mới | preference của chuyến (`trip-specific override`) | [19], [20] |
| Bạn hình dung khoảnh khắc đáng nhớ nhất của chuyến này là gì? | nhập tự do | preference của chuyến | [8], [15] |
| Chọn vài ảnh bạn thấy "đúng chất" chuyến này. | lưới ảnh | preference của chuyến | [21] |

**H. Kinh nghiệm và mức mới lạ** — chủ yếu cho Nhóm B (mục 3.2).

| Câu hỏi mẫu | Lựa chọn gợi ý | Ghi vào | Căn cứ |
| ----------- | -------------- | ------- | ------ |
| Bạn đã đến Đà Lạt chưa? Lần trước đã đi đâu? | chưa · rồi + chọn nơi đã đi | Experience History | [20] (động cơ đổi theo kinh nghiệm: người có kinh nghiệm thiên về trải nghiệm văn hóa địa phương, thiên nhiên) |
| Lần này muốn quay lại chỗ quen hay thử cái mới? | theo gu thường ngày · muốn thử điều mới · trộn | `trip-specific override` (novelty) | mục 6.3, 7.1 |

**I. Câu hỏi nối tiếp** — chỉ xuất hiện khi được kích hoạt.

| Khi nào | Câu hỏi mẫu | Căn cứ |
| ------- | ----------- | ------ |
| User dùng từ chủ quan ("chill", "yên tĩnh") | Với bạn "chill" nghĩa là: ít người · có view · ngồi lâu được · nhạc nhẹ? | [10] |
| User nêu một địa điểm/hoạt động cụ thể | Điều gì ở nơi đó làm bạn muốn đến? | [18] |
| User chọn `Không chắc` nhiều câu liền | Bạn muốn xem vài gợi ý trước rồi chỉnh không? | [16], [17] |
| User bỏ một đề xuất | Vì sao bạn bỏ địa điểm này? (mục 8.3) | [17] |

## 12.3. Hỏi thích ứng (adaptive questioning)

Không có kịch bản hỏi cố định. Sau mỗi câu trả lời, hệ thống cập nhật bản hiểu nhu cầu rồi quyết định bước tiếp theo: hỏi câu nào trong ngân hàng 12.2, xác nhận một suy luận, hay dừng hỏi để đề xuất.

Căn cứ chọn câu tiếp theo, theo thứ tự ưu tiên:

1. **Thông tin chặn việc lập kế hoạch.** Field còn thiếu mà thiếu thì không kiểm tra được khả thi (ngày, base, `physical constraints` khi có dấu hiệu) được hỏi trước [13], [14].
2. **Tín hiệu từ chính câu trả lời vừa rồi.** Đi theo mạch user mở ra: user nói "đi với bố mẹ" thì câu kế tiếp là nhóm C, không phải nhóm G; user dán link địa điểm thì xác nhận anchor (nhóm E). User có thể đổi chủ đề hoặc yêu cầu đề xuất bất cứ lúc nào (mixed initiative) [24].
3. **Mức thay đổi kết quả.** Giữa các câu còn lại, chọn câu mà các câu trả lời khả dĩ chia tập ứng viên khác nhau nhiều nhất [11], [12].
4. **Đã biết hoặc suy được thì không hỏi.** Giá trị có từ input, anchors hoặc User Profile chuyển thành câu xác nhận, không hỏi lại (mục 7.1).

Dừng hỏi khi:

* các câu còn lại không còn làm thay đổi tập ứng viên đáng kể;
* user chọn `Không chắc` / `Bỏ qua` liên tiếp, hoặc yêu cầu xem đề xuất; khi đó chuyển sang đề xuất rồi học từ phản hồi (compare, critique, lý do bỏ ở mục 8.3–8.4) [16], [17].

Sau khi dừng, hệ thống hiển thị bản hiểu nhu cầu (mục 12); field còn thiếu được đánh dấu `unknown`, không tự điền.

Ví dụ hai user cùng bắt đầu bằng "Muốn đi Đà Lạt 3 ngày":

```text
User 1: "đi với bố mẹ, mẹ đau gối"
  → C: tránh dốc/bậc?          (tín hiệu vừa nêu, hard constraint)
  → A: di chuyển bằng gì?       (chặn khả thi)
  → F: nhịp độ?                 (thường đổi mạnh khi có người lớn tuổi)
  → dừng, hiển thị bản hiểu nhu cầu

User 2: dán 6 link TikTok
  → E: xác nhận 6 anchor, nơi nào bỏ được?
  → A: ở khu nào?               (chặn khả thi)
  → F: một chặng tối đa bao lâu? (6 anchor rải rác → travel tolerance quyết định)
  → dừng, hiển thị bản hiểu nhu cầu
```

## 12.4. Điều chỉnh cách hỏi theo người dùng

Không chia persona với kịch bản hỏi riêng. Ngân hàng câu hỏi dùng chung; thứ thay đổi theo người dùng là **mức hướng dẫn, dạng câu hỏi và độ sâu**. Các nghiên cứu cho thấy nhóm người dùng khác nhau hợp với cách elicitation khác nhau: người mới hưởng lợi từ danh sách phổ biến/gợi ý sẵn, người am hiểu hài lòng hơn khi được nêu tiêu chí trực tiếp [25]; người dùng CRS tách thành nhiều nhóm có sở thích kiểu hội thoại khác nhau, chịu ảnh hưởng của mức muốn tự kiểm soát [26]; động cơ du lịch đổi theo kinh nghiệm [20].

Điều chỉnh dựa trên hai trục ở mục 3.3 và tín hiệu user tự thể hiện trong hội thoại:

| Tín hiệu | Cách hỏi | Căn cứ |
| -------- | -------- | ------ |
| Lần đầu đi (Nhóm A) | Hỏi theo cách dùng (nhóm G), luôn có chip gợi ý, cho "xem gợi ý trước" sớm; hạn chế hỏi thuộc tính. | [8], [25] |
| Đã từng đi (Nhóm B) | Được hỏi thẳng tiêu chí; ưu tiên nhóm H (đã đi đâu, muốn mới hay quen). | [20], [25] |
| Starting state: chưa có ý tưởng | Nhiều câu mở + gợi ý hơn. | [15] |
| Starting state: có địa điểm đã lưu / lịch sơ bộ | Bắt đầu từ xác nhận anchors (nhóm E) và constraint; ít câu hỏi sở thích. | mục 3.3 |
| User trả lời dài, tự nêu tiêu chí (muốn kiểm soát) | Lựa chọn chi tiết hơn, cho chỉnh từng tiêu chí. | [26] |
| User trả lời cụt, nhiều `Không chắc` | Ít câu hơn, chuyển sớm sang đề xuất rồi critique. | [16], [17], [26] |

Không suy đoán tuổi, giới tính hay đặc điểm cá nhân để đổi cách hỏi; chỉ dùng thông tin user đã cung cấp hoặc thể hiện trong hội thoại.

## 12.5. Giọng điệu câu hỏi

Mặc định: **gần gũi nhưng không suồng sã** — như một người hướng dẫn du lịch am hiểu, không như bạn thân.

Căn cứ:

* Chatbot hỏi theo phong cách hội thoại, thân mật (casual) làm người trả lời ít "trả lời cho xong" hơn so với phong cách trang trọng [27]; chatbot biết hỏi nối tiếp thu được câu trả lời cụ thể, rõ và nhiều thông tin hơn khảo sát dạng form [28].
* Nhưng văn phong thân mật làm giảm tin tưởng khi người dùng chưa quen thương hiệu [29] — TripGuardian là sản phẩm mới với phần lớn user.
* Với chatbot hỗ trợ du lịch, văn phong đúng với vai trò (register) quyết định cảm nhận phù hợp và độ tin cậy nhiều hơn sở thích cá nhân của user [30]; đặc điểm xã hội của chatbot phải khớp kỳ vọng của user, làm quá sẽ gây khó chịu [31].
* Khi hỏi thông tin nhạy cảm về sức khỏe, user đánh giá văn phong trang trọng là có năng lực và phù hợp hơn [32].
* Tiếng Việt không có đại từ trung tính; cách xưng hô luôn định vị quan hệ, tuổi và mức tôn trọng giữa hai bên [33].

Quy tắc:

| Tình huống | Giọng điệu | Ví dụ |
| ---------- | ---------- | ----- |
| Mặc định | Câu ngắn, tự nhiên, xưng "mình" – gọi "bạn"; không tiếng lóng, emoji tiết chế. | "Chuyến này bạn muốn thong thả hay đi được nhiều nơi?" |
| User dùng văn phong thân mật | Được nới theo user một mức, không bắt chước tiếng lóng hay đổi sang cách xưng hô quá thân mật ("tui", "bà", "ní"). | — |
| Câu hỏi nhạy cảm (nhóm C, ngân sách, ăn kiêng) | Trung tính, tôn trọng, nói rõ vì sao hỏi, nhấn mạnh có thể bỏ qua. | "Để tránh chỗ phải leo dốc, cho mình hỏi: có ai trong nhóm ngại đi bộ xa hoặc lên bậc thang không? Bạn có thể bỏ qua." |
| Cảnh báo, không khả thi, thiếu dữ liệu | Rõ ràng, không đùa, không giảm nhẹ. | "Hai nơi này cách nhau khoảng 50 phút, không kịp trước giờ đóng cửa." |

Giọng điệu chỉ đổi cách diễn đạt, không đổi nội dung câu hỏi, lựa chọn gợi ý hay field được ghi.

---

# 13. Nguồn thông tin

TripGuardian phân biệt **nguồn để khám phá** và **nguồn đủ căn cứ để ra quyết định**.

| Nguồn                           | Giá trị chính                             |
| ------------------------------- | ----------------------------------------- |
| TikTok, Facebook, YouTube, blog | Khám phá địa điểm và kiểu trải nghiệm     |
| Comment TikTok, cộng đồng       | Tín hiệu trải nghiệm lặp lại (độ đông, yên tĩnh, đường vào) |
| Google Maps / Places            | Định danh, vị trí, địa chỉ, giờ hoạt động (không lưu rating và review) |
| Website hoặc trang chính thức   | Giá, giờ mở cửa, quy định, thông báo      |
| Nguồn địa phương                | Sự kiện, giao thông, cảnh báo             |
| Weather / route service         | Điều kiện theo thời điểm                  |
| Người dùng                      | Nhu cầu, constraint và anchor             |
| Tín hiệu hành vi được cho phép  | Tín hiệu cá nhân hóa (mục 6.1), không phải evidence về địa điểm |

Mỗi nhận định quan trọng về địa điểm nên có:

```text
Claim
+ Source
+ Collected time
+ Confidence
```

Khi dữ liệu thiếu hoặc mâu thuẫn, hệ thống thể hiện **chưa chắc chắn** thay vì để AI tự điền.

Cách Place Intelligence được xây và kiểm tra (agent, gate, người duyệt theo rủi ro) nằm ở `docs/CORPUS.md`.

---

# 14. Nguyên tắc sản phẩm

TripGuardian tuân theo các nguyên tắc sau.

### 1. Chọn trước, lập lịch sau

Một địa điểm chỉ được đưa vào lịch sau khi đã đánh giá độ phù hợp.

### 2. Ràng buộc trước sở thích

Hard constraint được kiểm tra trước khi xếp hạng bằng preference.

### 3. Phù hợp quan trọng hơn nổi tiếng

Độ phổ biến chỉ là một tín hiệu.

### 4. Người dùng giữ quyền chọn

TripGuardian hỗ trợ quyết định, không quyết định thay toàn bộ.

### 5. Giải thích cả chọn và bỏ

Người dùng cần hiểu sự đánh đổi.

### 6. Không che giấu bất định

Thiếu dữ liệu phải được thể hiện là thiếu dữ liệu.

### 6. AI không tự xác nhận tính khả thi

Giờ mở cửa, thời gian, tuyến đường, ngân sách và constraint phải được kiểm tra bằng logic xác định.

### 7. Cá nhân hóa không vượt qua chuyến đi

User Profile là prior, chỉ được dùng sau khi đã kiểm tra constraint. Context của chuyến hiện tại luôn được ưu tiên hơn hành vi lịch sử.

---

# 15. Ví dụ

Người dùng:

> Tôi lần đầu đi Đà Lạt, 3 ngày với người yêu, đi xe máy. Tôi đã lưu khoảng 15 địa điểm trên TikTok nhưng không biết nên chọn chỗ nào. Tôi thích thiên nhiên và cà phê nhưng không muốn chạy xe quá nhiều.

TripGuardian:

1. nhận diện người dùng là **first-time visitor**;
2. đọc danh sách đã lưu;
3. chuẩn hóa các địa điểm;
4. loại hoặc cảnh báo các nơi không phù hợp constraint;
5. nhóm các địa điểm có trải nghiệm tương tự;
6. đề xuất shortlist.

Ví dụ:

```text
15 saved places
        ↓
12 places verified
        ↓
3 places conflict with travel preference
        ↓
2 pairs have highly similar experiences
        ↓
8 useful candidates
```

Hệ thống có thể giải thích:

> Hai quán A và B đều thiên về view rừng và nằm ở hai khu vực khác nhau. Với preference không muốn chạy xe nhiều, bạn có thể chỉ cần chọn một.

Người dùng chọn A.

Ngay sau đó:

> Giữ A giúp ngày 2 giảm khoảng 35 phút di chuyển so với B.

Sau khi người dùng chọn xong, hệ thống mới xây lịch trình.

---

# 16. Vai trò của AI

LLM phù hợp với:

* hiểu ngôn ngữ tự nhiên;
* trích xuất preference;
* diễn giải tín hiệu hành vi và lý do quyết định cho User Profile;
* hiểu yêu cầu mơ hồ;
* trích xuất bằng chứng về địa điểm từ video, comment, và trang web (luôn kèm span nguồn);
* tổng hợp evidence;
* tạo câu hỏi thích ứng;
* giải thích kết quả.

LLM không tự quyết định:

* giờ mở cửa có hợp lệ hay không;
* hai khoảng thời gian có xung đột hay không;
* ngân sách có vượt hay không;
* tuyến đường có khả thi hay không;
* một plan có vi phạm hard constraint hay không.

Các phần này cần logic xác định.

Tương tự, model không ghi fact về địa điểm. Model trích observation; rule tổng hợp chúng; một model mạnh hơn kiểm tra các địa điểm rủi ro cao; người duyệt những gì vẫn bị đánh dấu.

---

# 17. Phạm vi MVP

## Trong phạm vi

* Đà Lạt;
* first-time và returning visitor;
* trip context;
* preference discovery;
* nhập saved places;
* anchor và must-go places;
* tìm và kiểm tra địa điểm (agent xây, người duyệt theo rủi ro);
* shortlist;
* compare;
* user curation;
* feasibility;
* multi-day itinerary;
* route optimization;
* cảnh báo và backup.

## Ngoài phạm vi

* điều hướng turn-by-turn;
* nền tảng booking đầy đủ;
* mạng xã hội du lịch;
* collaboration phức tạp cho nhóm lớn;
* bao phủ toàn Việt Nam;
* cam kết mọi thông tin đều real-time;
* để LLM tự tạo dữ kiện còn thiếu.

---

# 18. Thước đo thành công

TripGuardian cần được đánh giá bằng chất lượng quyết định, không chỉ bằng việc có tạo được itinerary hay không.

| Mục tiêu            | Chỉ số                                          |
| ------------------- | ----------------------------------------------- |
| Đúng constraint     | Hard constraint violation rate                  |
| Có căn cứ           | Evidence coverage                               |
| Không bịa           | Unsupported claim rate                          |
| Khả thi             | Feasible itinerary rate                         |
| Giảm công sức       | Time to accepted plan                           |
| Giảm tìm kiếm ngoài | External searches / tabs                        |
| Giúp lựa chọn       | Tỷ lệ user chọn được shortlist                  |
| Dễ hiểu             | User hiểu lý do chọn/bỏ                         |
| Cá nhân hóa         | Kết quả thay đổi hợp lý khi preference thay đổi |
| Minh bạch           | Uncertainty được cảnh báo đúng                  |
| Ổn định             | Tỷ lệ plan robust / fragile                     |

Các ngưỡng mục tiêu chỉ được đặt sau khi có baseline và pilot.

---

# 19. Baseline đánh giá

TripGuardian nên được so với ít nhất:

### Baseline 1 — Người dùng tự tìm

TikTok / Google Search / Google Maps / review.

### Baseline 2 — AI travel planner thông thường

Người dùng nhập yêu cầu và nhận itinerary trực tiếp.

### TripGuardian

```text
Understand
→ Verify
→ Compare
→ Select
→ Validate
→ Schedule
```

So sánh trên cùng một số tình huống để kiểm tra liệu TripGuardian có thực sự:

* giảm thời gian lập kế hoạch;
* giảm constraint violation;
* giảm số lần sửa itinerary;
* giúp user tự tin hơn khi chọn;
* tạo plan khả thi hơn.

---

# Tài liệu tham khảo

[1] J.-Y. Park and S. Jang, “Confused by too many choices? Choice overload in tourism,” *Tourism Management*, vol. 35, pp. 1–12, 2013.

[2] Traveloka and YouGov, “Travel Redefined: Understanding and Catering to the Diverse Needs of APAC Travellers,” 2024.

[3] Công an tỉnh Lâm Đồng, “Nâng cao ý thức chấp hành luật giao thông đường bộ trong các dịp lễ, Tết.”

[4] Cổng thông tin điện tử tỉnh Lâm Đồng, “Đà Lạt: Nỗ lực chống ùn tắc giao thông.”

[5] Wanderlog, “Wanderlog travel planner.”

[6] Mindtrip, “AI-powered travel, personalized to you.”

[7] Tripadvisor, “Plan your trip with Tripadvisor's AI travel assistant.”

[8] I. Kostric, K. Balog, and F. Radlinski, “Soliciting User Preferences in Conversational Recommender Systems via Usage-related Questions,” RecSys 2021.

[9] L. Ziegfeld, D. Di Scala, and A. H. M. Cremers, “The effect of preference elicitation methods on the user experience in conversational recommender systems,” *Computer Speech & Language*, 2025.

[10] F. Radlinski et al., “Subjective Attributes in Conversational Recommendation Systems: Challenges and Opportunities,” AAAI 2022.

[11] K. Christakopoulou, F. Radlinski, and K. Hofmann, “Towards Conversational Recommender Systems,” KDD 2016, pp. 815–824.

[12] M. Aliannejadi, H. Zamani, F. Crestani, and W. B. Croft, “Asking Clarifying Questions in Open-Domain Information-Seeking Conversations,” SIGIR 2019.

[13] X. Zhang, Y. Deng, Z. Ren, S.-K. Ng, and T.-S. Chua, “Ask-before-Plan: Proactive Language Agents for Real-World Planning,” Findings of EMNLP 2024.

[14] J. Xie et al., “TravelPlanner: A Benchmark for Real-World Planning with Language Agents,” ICML 2024.

[15] B. Z. Li, A. Tamkin, N. Goodman, and J. Andreas, “Eliciting Human Preferences with Language Models,” ICLR 2025 (arXiv:2310.11589).

[16] J. A. Krosnick et al., “The Impact of ‘No Opinion’ Response Options on Data Quality: Non-Attitude Reduction or an Invitation to Satisfice?,” *Public Opinion Quarterly*, vol. 66, no. 3, pp. 371–403, 2002.

[17] L. Chen and P. Pu, “Critiquing-based recommenders: survey and emerging trends,” *User Modeling and User-Adapted Interaction*, vol. 22, pp. 125–150, 2012.

[18] T. J. Reynolds and J. Gutman, “Laddering Theory, Method, Analysis, and Interpretation,” *Journal of Advertising Research*, vol. 28, no. 1, pp. 11–31, 1988.

[19] J. L. Crompton, “Motivations for Pleasure Vacation,” *Annals of Tourism Research*, vol. 6, no. 4, pp. 408–424, 1979.

[20] P. L. Pearce and U.-I. Lee, “Developing the Travel Career Approach to Tourist Motivation,” *Journal of Travel Research*, vol. 43, no. 3, pp. 226–237, 2005.

[21] J. Neidhardt, R. Schuster, L. Seyfang, and H. Werthner, “Eliciting the users' unknown preferences,” RecSys 2014.

[22] A. Delic et al., “Observing Group Decision Making Processes,” RecSys 2016.

[23] S. Darcy and T. Dickson, “A Whole-of-Life Approach to Tourism: The Case for Accessible Tourism Experiences,” *Journal of Hospitality and Tourism Management*, vol. 16, no. 1, pp. 32–44, 2009.

[24] D. Jannach, A. Manzoor, W. Cai, and L. Chen, “A Survey on Conversational Recommender Systems,” *ACM Computing Surveys*, vol. 54, no. 5, art. 105, 2021.

[25] B. P. Knijnenburg, N. J. M. Reijmer, and M. C. Willemsen, “Each to his own: How different users call for different interaction methods in recommender systems,” RecSys 2011.

[26] R. Mahmud, S. Berkovsky, M. Prasad, and A. B. Kocaballi, “Understanding User Preferences for Interaction Styles in Conversational Recommender Systems: The Predictive Role of System Qualities, User Experience, and Traits,” OzCHI 2025.

[27] S. Kim, J. Lee, and G. Gweon, “Comparing Data from Chatbot and Web Surveys: Effects of Platform and Conversational Style on Survey Response Quality,” CHI 2019.

[28] Z. Xiao et al., “Tell Me About Yourself: Using an AI-Powered Chatbot to Conduct Conversational Surveys with Open-ended Questions,” *ACM Transactions on Computer-Human Interaction*, vol. 27, no. 3, 2020.

[29] A. Gretry, C. Horváth, N. Belei, and A. C. R. van Riel, “‘Don't pretend to be my friend!’ When an informal brand communication style backfires on social media,” *Journal of Business Research*, vol. 74, pp. 77–89, 2017.

[30] A. P. Chaves, J. Egbert, T. Hocking, E. Doerry, and M. A. Gerosa, “Chatbots Language Design: The Influence of Language Variation on User Experience with Tourist Assistant Chatbots,” *ACM Transactions on Computer-Human Interaction*, 2022.

[31] A. P. Chaves and M. A. Gerosa, “How Should My Chatbot Interact? A Survey on Social Characteristics in Human–Chatbot Interaction Design,” *International Journal of Human–Computer Interaction*, vol. 37, no. 8, pp. 729–758, 2021.

[32] “Does Chatbot Language Formality Affect Users' Self-Disclosure?,” CUI 2022 (ACM Conference on Conversational User Interfaces), doi:10.1145/3543829.3543831.

[33] H. V. Luong, *Discursive Practices and Linguistic Meanings: The Vietnamese System of Person Reference*. Amsterdam: John Benjamins, 1990.
