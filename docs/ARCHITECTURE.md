# Kiến trúc — TripGuardian

Tài liệu này định nghĩa **luồng hệ thống và cấu trúc quyết định** của TripGuardian: điều gì xảy ra, theo thứ tự nào, dưới quy tắc nào.

Tài liệu không định nghĩa code, framework, API, schema database, hay chi tiết cài đặt.

TripGuardian gồm bốn phần nối với nhau:

```text
        ┌──────────────────────┐
        │  PLACE INTELLIGENCE  │
        └──────────┬───────────┘
                   │
                   ▼
        ┌──────────────────────┐
        │  TRIP UNDERSTANDING  │
        └──────────┬───────────┘
                   │
                   ▼
        ┌──────────────────────┐
        │    PLACE DECISION    │
        └──────────┬───────────┘
                   │
             Live Context
                   │
                   ▼
        ┌──────────────────────┐
        │ PLANNING & VALIDATION│
        └──────────────────────┘
```

Phạm vi ban đầu là **Đà Lạt**.

---

# 1. Nguyên tắc cốt lõi

Nguyên tắc sản phẩm: `docs/Project_Context.md` §14. Ở mức hệ thống, thêm:

* Thiếu bằng chứng thì giữ `unknown`; hệ thống không bao giờ bịa fact.
* Input của người dùng mô tả chuyến đi, không mô tả bản thân địa điểm.
* Live context chỉ dành cho từng request và không trở thành tri thức lâu dài về địa điểm.
* Điều bất khả thi về vật lý không thể bị ghi đè.

---

# 2. Place Intelligence

Place Intelligence được xây offline, độc lập với mọi chuyến đi. Agent xây; gate tất định kiểm soát mọi lần ghi; người chỉ duyệt một hàng đợi xếp theo rủi ro ở cuối. Chi tiết: `docs/CORPUS.md` và `docs/specs/CORPUS_SPEC.md`.

```text
Discover → Extract → Resolve → Observe → Aggregate → Check & route → Publish → Hàng đợi review
                                                                        ↑
                                         Refresh (chỉ input đã đổi mới chạy lại)
```

## 2.1 Khám phá

```text
Query TikTok theo nhóm      Lưới category × khu vực trên Google Places
          └──────────────┬──────────────┘
                         ↓
              mention / ứng viên địa điểm
```

Khám phá nội dung tìm ra trải nghiệm; lưới Maps tìm ra những nơi nội dung bỏ sót. Cả hai đổ vào một danh sách ứng viên. Ứng viên chỉ là địa điểm có thể có, chưa được tin.

## 2.2 Resolve

```text
ứng viên
    ↓
chuẩn hóa tên → match trong vùng (tên, category, vị trí, quan hệ được nói rõ)
    ├─ match rõ                        → POI
    ├─ khu vực / con đường / cảnh quan → ZONE (nối với các POI của nó)
    ├─ chưa rõ                         → Judge chọn một phương án có sẵn hoặc bỏ phiếu trắng
    └─ không match                     → UNRESOLVED (giữ lại, không phục vụ)
```

Nhiều mention → một địa điểm chuẩn với nhiều alias. Định danh không bao giờ được đoán. Xuất hiện trong cùng video không bao giờ là bằng chứng hai nơi gần nhau.

## 2.3 Bằng chứng

Mọi nguồn trở thành **observation**: một nhận định kèm span nguồn và bối cảnh (thời điểm trong ngày, loại ngày, thời tiết được nhắc tới). Không gì ghi thẳng vào địa điểm.

```text
trang chính thức → giờ, giá, đặt chỗ, quy định
Google Places    → định danh, vị trí, giờ, trạng thái
video TikTok     → trải nghiệm, môi trường, mức vận động
comment TikTok   → tín hiệu lặp lại (độ đông, yên tĩnh, đường vào)
```

Giá hay giờ chỉ thấy trong video vẫn chỉ là observation; không bao giờ thành fact nếu không có nguồn chính thức hoặc Google xác nhận.

## 2.4 Tổng hợp

Rule, không phải model, biến observation thành ba loại output:

```text
Fact       giờ, giá, đặt chỗ               đồng ý → giá trị · bất đồng → uncertain + giữ xung đột
Signal     độ đông theo bối cảnh, yên tĩnh  phân phối trên các observation liên quan
Estimate   thời gian tham quan              luôn là khoảng (min / typical / long)
```

Mỗi output mang các thành phần confidence (số nguồn độc lập, mức đồng thuận, độ mới, loại nguồn) và coverage theo khía cạnh. Thiếu bằng chứng thì giữ `unknown`.

## 2.5 Kiểm tra, publish, review

```text
gate (schema, span tồn tại, ontology id, ngưỡng match)
    ↓
định tuyến rủi ro
    ├─ rủi ro thấp → publish
    └─ rủi ro cao  → Judge audit → pass → publish
                                 → flag → NEEDS_REVIEW (không phục vụ) → hàng đợi review
```

Hàng đợi review còn nhận các giá trị về an toàn / tiếp cận và một mẫu ngẫu nhiên ẩn dùng để đo chất lượng. Người duyệt Accept, Disable, hoặc Report error; giá trị không bao giờ được sửa tay.

Trạng thái: `VERIFIED`, `UNCERTAIN`, `OUTDATED`, `NEEDS_REVIEW`, `DISABLED`, giữ theo từng khía cạnh.

## 2.6 Bản ghi Place Intelligence

```text
Place
├── Identity      tên, alias, POI | ZONE, category, vị trí
├── Operation     giờ, chi phí, đặt chỗ, thời gian tham quan (min / typical / long)
├── Experience    tính chất, hoạt động
├── Environment   trong nhà / ngoài trời, độ đông theo bối cảnh, nhạy thời tiết
├── Effort        đi bộ, dốc, khó tiếp cận
├── Suitability   hợp / không hợp (cặp đôi, gia đình, người lớn tuổi, …)
└── Provenance    bằng chứng, confidence, độ mới, xung đột, coverage, trạng thái
```

Effort ở đây là thuộc tính của địa điểm. Khoảng cách và thời gian di chuyển phụ thuộc chuyến đi và được tính online.

Place Intelligence là dữ liệu dẫn xuất và có thể build lại từ observation bất cứ lúc nào.

---

# 3. Hiểu chuyến đi

Luồng online bắt đầu bằng việc hiểu **người dùng đang xuất phát từ đâu**, không ép mọi người đi qua cùng một luồng lập kế hoạch.

```text
Người dùng
 ↓
Kinh nghiệm
 ↓
Trạng thái bắt đầu
 ↓
User Profile (prior, khi người dùng đồng ý)
 ↓
Thông tin cơ bản của chuyến đi
 ↓
Anchor
 ↓
Constraint
 ↓
Ghi đè riêng cho chuyến đi
 ↓
Sở thích + Nhịp độ
 ↓
Trip State đã chuẩn hóa
```

---

## 3.1 Kinh nghiệm

```text
Kinh nghiệm
├── Lần đầu đến
└── Đã từng đến / có kinh nghiệm
```

Kinh nghiệm quyết định mức độ dẫn dắt.

Nó không trực tiếp quyết định địa điểm nào được chọn.

---

## 3.2 Trạng thái bắt đầu

```text
Trạng thái bắt đầu
├── Khám phá từ đầu
├── Địa điểm đã lưu
├── Nơi bắt buộc đến / anchor
└── Lịch trình có sẵn
```

Trạng thái bắt đầu quyết định luồng quyết định bắt đầu từ đâu.

Ví dụ:

```text
Khám phá
→ khám phá và shortlist

Địa điểm đã lưu
→ resolve → so sánh → shortlist

Nơi bắt buộc đến
→ coi là anchor → đánh giá xung quanh chúng

Lịch trình có sẵn
→ kiểm tra → phát hiện xung đột → sửa
```

---

## 3.3 Trip State

Trip State đã chuẩn hóa gồm:

```text
Trip State
├── Thông tin cơ bản
│   ├── ngày đi
│   ├── số ngày
│   ├── nhóm đi
│   ├── chỗ ở / điểm xuất phát
│   └── phương tiện
│
├── Anchor
│   ├── nơi bắt buộc đến
│   ├── booking cố định (khách sạn, vé, hoạt động)
│   ├── sự kiện giờ cố định
│   └── giờ check-in/check-out, giờ phải rời Đà Lạt
│
├── Constraint
│   ├── physical constraint
│   └── user hard constraint
│
├── Sở thích
│   ├── ghi đè riêng cho chuyến đi
│   ├── session profile
│   └── mặc định từ long-term profile (khi người dùng đồng ý)
│
└── Nhịp độ
    ├── thư thả
    ├── cân bằng
    └── đi được nhiều nơi
```

Chỉ cần thu thập thông tin có khả năng làm thay đổi kết quả.

---

## 3.4 User Profile

Khi người dùng cho phép, User Profile cung cấp giá trị mặc định (sở thích đã thể hiện, mối quan tâm gần đây, lịch sử trải nghiệm, thói quen mặc định). Cấu trúc, cách cập nhật, và nguyên tắc: `docs/Project_Context.md` §6–11.

Trong luồng, profile chỉ là prior và đứng sau mọi constraint:

```text
Physical Constraint → User Hard Constraint → Ghi đè của chuyến đi → Mối quan tâm gần đây → Sở thích đã thể hiện
```

Session Profile (một chuyến, thích nghi ngay) và Long-term Profile (chỉ đổi khi có tín hiệu lặp lại, độc lập, hoặc phản hồi trực tiếp) tách riêng.

---

# 4. Mô hình constraint

TripGuardian tách ba loại quy tắc quyết định.

| Loại                 | Ý nghĩa                         | Có thể nới không?               |
| -------------------- | ------------------------------- | ------------------------------- |
| Physical constraint  | Điều bất khả thi trong thực tế  | Không                           |
| User hard constraint | Yêu cầu rõ ràng của người dùng  | Chỉ khi người dùng xác nhận     |
| Soft preference      | Sở thích dùng để xếp hạng       | Có                              |

Ví dụ:

```text
Địa điểm đóng cửa lúc 17:00
Sớm nhất đến được = 18:10
→ xung đột physical
→ không thể tạo lịch hợp lệ
```

Nhưng:

```text
Người dùng đặt giới hạn 30 phút di chuyển mỗi chặng
Cần di chuyển = 42 phút
→ xung đột user hard constraint
→ người dùng có thể chủ động nới
```

---

# 5. Resolve địa điểm của người dùng

Địa điểm đã lưu, nơi bắt buộc đến, và địa điểm nhập tay phải được resolve trước.

```text
Địa điểm người dùng
    ↓
match với Place Intelligence
    ↓
┌──────────────────────┐
│ match chính xác      │ → Địa điểm đã xác minh
│ match mơ hồ          │ → Hỏi / so sánh các định danh
│ không match          │ → Địa điểm chưa xác minh
└──────────────────────┘
```

Khi địa điểm chưa có trong Place Intelligence, bộ resolve chạy theo yêu cầu với nhà cung cấp bản đồ. Match chắc chắn thì trả về và xếp hàng làm giàu dữ liệu; nếu không, người dùng chọn từ các phương án.

Input của người dùng không bao giờ trở thành bằng chứng về địa điểm.

Địa điểm chưa xác minh vẫn có thể ở lại trong chuyến đi, nhưng hệ thống không được coi thông tin chưa biết là đã xác nhận.

---

# 6. Quyết định địa điểm

Place Intelligence và Trip State gặp nhau ở tầng quyết định.

```text
Trip State
    +
Place Intelligence
    ↓
Resolve địa điểm của người dùng
    ↓
Truy xuất ứng viên
    ↓
Sàng lọc constraint
    ↓
Độ hợp bối cảnh
    ↓
Xếp hạng theo sở thích
    ↓
Kiểm soát đa dạng
    ↓
Shortlist
    ↓
So sánh
    ↓
Người dùng tuyển chọn
    ↓
Khả thi của tổ hợp
    ↓
Địa điểm người dùng đã xác nhận
```

---

## 6.1 Truy xuất ứng viên

Ứng viên có thể đến từ:

```text
khám phá của PI
địa điểm đã lưu
nơi bắt buộc đến
lịch trình có sẵn
tìm kiếm của người dùng
```

Hệ thống không cần trả về nhiều địa điểm.

Mục tiêu là tìm một tập quyết định hữu ích.

---

## 6.2 Sàng lọc constraint

```text
ứng viên
    ↓
physical constraint?
    ├─ vi phạm → loại
    │
    └─ hợp lệ
         ↓
user hard constraint?
    ├─ vi phạm → loại / thương lượng
    └─ hợp lệ → tiếp tục
```

Nếu thiếu bằng chứng cần cho một hard constraint, địa điểm không được coi là đã xác minh an toàn.

---

## 6.3 Độ hợp bối cảnh

Trước khi tính lộ trình chi tiết, TripGuardian đánh giá độ hợp thô với chuyến đi:

```text
vị trí
khoảng cách tương đối
khu vực / cụm
đặc điểm đường vào
độ đông dự kiến
anchor của chuyến đi
```

Bước này ngăn các ứng viên rõ ràng không hợp lọt vào shortlist.

Thời gian di chuyển thực tế chính xác được xử lý sau.

---

## 6.4 Xếp hạng sở thích và đa dạng

Các ứng viên còn lại được so sánh bằng:

```text
độ hợp bối cảnh
+ độ hợp sở thích
+ mối quan tâm gần đây
+ tính mới (lịch sử trải nghiệm / khoảng trống khám phá)
+ độ hợp kinh nghiệm
+ phạt độ không chắc chắn
```

Tín hiệu từ profile chỉ xếp hạng các ứng viên đã qua sàng lọc constraint.

Độ phổ biến chỉ là một tín hiệu.

Các trải nghiệm gần trùng nhau được giảm bớt để shortlist thể hiện các lựa chọn thực sự khác nhau.

---

## 6.5 So sánh

Với các ứng viên giống nhau, TripGuardian giữ các phương án thay thế thay vì chỉ giữ người thắng.

```text
Địa điểm A
vs
Địa điểm B

→ A tốt hơn ở đâu
→ B tốt hơn ở đâu
→ phải hy sinh gì
```

Ví dụ:

```text
A: di chuyển ngắn hơn, đông hơn
B: yên tĩnh hơn, di chuyển xa hơn
```

Nhờ đó hệ thống giải thích được:

> Vì sao chọn nơi này thay vì nơi kia?

---

# 7. Người dùng tuyển chọn

Shortlist được trình bày theo các nhóm hữu ích.

```text
Shortlist
   ↓
Xem theo nhóm
   ↓
Người dùng thêm / bỏ / khóa địa điểm
   ↓
Tóm tắt khả thi trực tiếp
   ↓
Người dùng xác nhận lựa chọn
```

Với mỗi ứng viên, chỉ hiển thị thông tin liên quan đến quyết định:

```text
Vì sao phù hợp
Đánh đổi
Thời gian ước tính
Ảnh hưởng vị trí ước lượng
Độ tin cậy
```

Người dùng luôn có thể thêm địa điểm của riêng mình.

Thao tác tuyển chọn là tín hiệu cho Session Profile; trọng số theo độ mạnh, lý do khi bỏ, và cách học từ so sánh: `docs/Project_Context.md` §8.2–8.4.

---

# 8. Khả thi của tổ hợp

Tính khả thi đánh giá các địa điểm đã chọn **như một nhóm**, không đánh giá riêng lẻ.

```text
Địa điểm đã chọn
       ↓
kiểm tra:
- tổng thời gian có
- anchor
- khung giờ mở cửa
- thời gian tham quan ước tính
- tải di chuyển thô
- ngân sách
- số nơi mỗi ngày
       ↓
┌──────────────┬──────────────┬──────────────┐
│ Khả thi      │ Khả thi      │ Không        │
│              │ một phần     │ khả thi      │
└──────────────┴──────────────┴──────────────┘
```

### Khả thi

Chuyển sang lập kế hoạch.

### Khả thi một phần

```text
xác định địa điểm gây xung đột
        ↓
giải thích constraint
        ↓
cho thấy bỏ / thay chúng thì được gì
        ↓
người dùng chọn
```

### Không khả thi

Giải thích sự không khớp tổng thể:

```text
thời gian cần > thời gian có
thiếu ngân sách
anchor xung đột
quá nhiều cụm cách xa nhau
```

Rồi quay lại bước tuyển chọn.

### Địa điểm người dùng khóa

```text
địa điểm bị khóa gây xung đột
    ├─ chỉ vi phạm user constraint → hỏi có nới không, kèm cái giá cụ thể
    │                                ("di chuyển mỗi chặng từ 25 lên 42 phút")
    ├─ vi phạm physical constraint → không tạo lịch giả vờ khả thi;
    │                                giữ trong wishlist · đề xuất ngày khác · đổi các điểm trước
    └─ giờ mở cửa chưa chắc chắn   → cho giữ, kèm cảnh báo kiểm tra lại trước chuyến đi
```

---

# 9. Lập kế hoạch

Chỉ địa điểm người dùng đã xác nhận mới vào bước xếp lịch chi tiết.

```text
Địa điểm đã xác nhận
        +
Trip State
        +
Live Context
        ↓
Chia theo ngày
        ↓
Gom cụm theo địa lý
        ↓
Khớp khung giờ mở cửa
        ↓
Chọn thời gian tham quan
        ↓
Tối ưu lộ trình
        ↓
Thêm thời gian đệm
        ↓
Các phương án lịch
```

Live context có thể gồm:

```text
thời tiết
thời gian di chuyển thực tế
điều kiện tạm thời
```

Live context chỉ dành cho từng request và không trở thành Place Intelligence lâu dài.

---

# 10. Mục tiêu lập kế hoạch

Nhịp độ và mục tiêu tối ưu là hai thứ riêng.

### Nhịp độ

```text
Thư thả
Cân bằng
Đi được nhiều nơi
```

Người dùng chỉ chọn một mức; hệ thống tự đổi thành tham số:

* Thư thả: ít nơi, ở lâu mỗi nơi, đệm lớn.
* Cân bằng: cân giữa chất lượng trải nghiệm và số nơi.
* Đi được nhiều nơi: thêm điểm dừng nhưng vẫn không vi phạm physical constraint.

Nhịp độ ảnh hưởng đến:

* thời gian tham quan;
* số nơi mỗi ngày;
* thời gian nghỉ;
* độ lớn thời gian đệm;
* mức di chuyển chấp nhận.

### Mục tiêu lập kế hoạch

Các mục tiêu có thể gồm:

```text
Ít di chuyển
Chi phí thấp
Vững trước thời tiết
Đa dạng trải nghiệm
Hợp sở thích
```

Mục tiêu được chọn từ bối cảnh chuyến đi của người dùng, không cố định từ trước.

---

# 11. Kiểm tra cuối

Một lịch trình không được chấp nhận chỉ vì trông hợp lý.

```text
Lịch trình
   ↓
Kiểm tra
   ├── ngày đi
   ├── giờ mở cửa
   ├── chồng lấn
   ├── thời gian di chuyển
   ├── anchor
   ├── ngân sách
   ├── hard constraint
   └── địa điểm trùng
   ↓
đạt?
├── có    → tiếp tục
└── không → sửa → kiểm tra lại
```

Physical constraint không bao giờ bị nới một cách lặng lẽ.

Nếu không tạo được lịch hợp lệ, hệ thống quay lại tầng quyết định.

---

# 12. Độ vững

Một kế hoạch khả thi vẫn có thể quá mong manh.

```text
Lịch đã kiểm tra
        ↓
Kiểm tra độ vững
        ↓
┌──────────┬──────────┬──────────┐
│ Vững     │ Khả thi  │ Mong     │
│          │          │ manh     │
└──────────┴──────────┴──────────┘
```

* Vững: đủ đệm để chịu vài chậm trễ nhỏ.
* Khả thi: chạy được nếu phần lớn hoạt động đúng giờ dự kiến.
* Mong manh: vẫn đúng về toán nhưng một chậm trễ nhỏ có thể làm hỏng các điểm sau.

Việc kiểm tra xét các nhiễu nhỏ như:

```text
xuất phát trễ
tham quan lâu hơn
giao thông tăng
thông tin vận hành chưa chắc chắn
```

Ví dụ:

```text
trễ +30 phút
    ↓
điểm cuối không đến kịp
    ↓
kế hoạch = Mong manh
```

---

# 13. Kế hoạch dự phòng

Với các phần nhạy cảm của chuyến đi, TripGuardian có thể chuẩn bị phương án thay thế.

```text
Địa điểm nhạy cảm
      ↓
Lý do
├── thời tiết
├── thời gian
├── độ đông
├── khoảng cách
└── độ không chắc chắn
      ↓
Dự phòng
```

Ví dụ:

```text
Mưa
→ nơi ngoài trời → nơi trong nhà thay thế

Bị trễ
→ bỏ điểm có ưu tiên thấp nhất

Kẹt xe
→ dùng ứng viên gần đó

Giờ mở cửa chưa chắc
→ chuẩn bị nơi thay thế cùng khu vực
```

---

# 14. Output cuối cùng

```text
Kế hoạch đã kiểm tra
├── lịch trình
├── lộ trình
├── chi phí ước tính
├── tải di chuyển
├── lý do cho các lựa chọn chính
├── đánh đổi
├── cảnh báo
├── độ không chắc chắn
├── độ vững
└── phương án dự phòng
```

Kế hoạch phải giải thích được cả:

> Vì sao chọn những nơi này?

và:

> Đã phải hy sinh gì để chuyến đi khả thi?

---

# 15. Các vòng phản hồi chính

TripGuardian không phải một pipeline một chiều.

### Vòng lựa chọn

```text
Shortlist
   ↓
Người dùng tuyển chọn
   ↓
Khả thi
   │
 xung đột
   └──────────────→ Người dùng tuyển chọn
```

### Vòng xếp lịch

```text
Lập kế hoạch
   ↓
Có nơi không xếp được
   ↓
Quay lại tuyển chọn
   ↓
Thay / Bỏ / Nới
   ↓
Lập kế hoạch
```

### Vòng kiểm tra

```text
Lịch trình
   ↓
Kiểm tra / Độ vững
   ↓
Vấn đề
   ↓
Sửa / Phương án thay thế
   ↓
Kiểm tra lại
```

### Vòng cá nhân hóa

```text
User Profile
   ↓
Gợi ý
   ↓
Quyết định của người dùng
   ↓
Session Profile → Gợi ý thích nghi
   ↓
Kết quả chuyến đi (đã đến + phản hồi)
   ↓
Bằng chứng lặp lại / mạnh?
   ├─ không → chỉ trong session
   └─ có    → Cập nhật Long-term Profile
```

---

# 16. Kiến trúc tổng thể

```text
                     TRIPGUARDIAN


 ┌─────────────────────────────────────────────┐
 │             PLACE INTELLIGENCE              │
 │                                             │
 │ Khám phá                                    │
 │    ↓                                        │
 │ Trích xuất + Resolve địa điểm               │
 │    ↓                                        │
 │ Observe                                     │
 │    ↓                                        │
 │ Tổng hợp (rule)                             │
 │    ↓                                        │
 │ Kiểm tra + Định tuyến → Hàng đợi review     │
 │    ↓                                        │
 │ Place Intelligence (serving index)          │
 └──────────────────────┬──────────────────────┘
                        │
                        │
 ┌──────────────────────▼──────────────────────┐
 │              TRIP UNDERSTANDING             │
 │                                             │
 │ Kinh nghiệm + Trạng thái bắt đầu            │
 │    ↓                                        │
 │ User Profile (prior, khi đồng ý)            │
 │    ↓                                        │
 │ Thông tin cơ bản                            │
 │    ↓                                        │
 │ Anchor                                      │
 │    ↓                                        │
 │ Constraint                                  │
 │    ↓                                        │
 │ Ghi đè riêng cho chuyến đi                  │
 │    ↓                                        │
 │ Sở thích + Nhịp độ                          │
 │    ↓                                        │
 │ Trip State đã chuẩn hóa                     │
 └──────────────────────┬──────────────────────┘
                        │
                        ▼
 ┌─────────────────────────────────────────────┐
 │               PLACE DECISION                │
 │                                             │
 │ Resolve địa điểm của người dùng             │
 │    ↓                                        │
 │ Truy xuất ứng viên                          │
 │    ↓                                        │
 │ Sàng lọc constraint                         │
 │    ↓                                        │
 │ Độ hợp bối cảnh                             │
 │    ↓                                        │
 │ Xếp hạng sở thích + đa dạng                 │
 │    ↓                                        │
 │ So sánh phương án                           │
 │    ↓                                        │
 │ Người dùng tuyển chọn                       │
 │    ↓                                        │
 │ Khả thi của tổ hợp                          │
 │    ↓                                        │
 │ Địa điểm đã xác nhận                        │
 └──────────────────────┬──────────────────────┘
                        │
                  Live Context
                        │
                        ▼
 ┌─────────────────────────────────────────────┐
 │           PLANNING & VALIDATION             │
 │                                             │
 │ Chia theo ngày                              │
 │    ↓                                        │
 │ Gom cụm địa điểm                            │
 │    ↓                                        │
 │ Khớp khung giờ                              │
 │    ↓                                        │
 │ Chọn thời gian tham quan                    │
 │    ↓                                        │
 │ Tối ưu lộ trình                             │
 │    ↓                                        │
 │ Kiểm tra constraint                         │
 │    ↓                                        │
 │ Kiểm tra độ vững                            │
 │    ↓                                        │
 │ Kế hoạch dự phòng                           │
 │    ↓                                        │
 │ Kế hoạch đã kiểm tra                        │
 └─────────────────────────────────────────────┘
```

---

# 17. Các quyết định thiết kế chính

| Quyết định | Lý do |
| --- | --- |
| Place Intelligence tách khỏi bối cảnh chuyến đi | Tri thức địa điểm và nhu cầu từng chuyến có vòng đời khác nhau |
| Khám phá và bằng chứng tách riêng | Nguồn giúp tìm ra địa điểm chưa chắc đáng tin cho mọi nhận định |
| Kinh nghiệm và trạng thái bắt đầu độc lập | Người có kinh nghiệm vẫn có thể bắt đầu từ đầu; người lần đầu có thể đã lưu sẵn địa điểm |
| Địa điểm của người dùng được resolve trước khi đánh giá | Tên đã lưu có thể là alias, bị trùng, hoặc là nơi chưa biết |
| Physical, user-hard, và soft constraint tách riêng | Chúng cần cách xử lý xung đột khác nhau |
| Chọn dùng độ hợp không gian thô; xếp lịch dùng thời gian di chuyển thực tế | Tránh tính kế hoạch chi tiết tốn kém trước khi biết shortlist |
| Người dùng tuyển chọn trước khi xếp lịch cuối | TripGuardian hỗ trợ quyết định thay vì quyết định thay |
| Khả thi đánh giá theo tổ hợp | Các nơi hợp lệ riêng lẻ vẫn có thể tạo thành chuyến đi bất khả thi |
| Nhịp độ và mục tiêu tối ưu tách riêng | "Thư thả" mô tả cường độ chuyến đi; "tiết kiệm" hay "ít di chuyển" mô tả mục tiêu lập kế hoạch |
| Kiểm tra là tất định | Một kế hoạch trông hợp lý là chưa đủ |
| Độ vững đi sau khả thi | Kế hoạch đúng về toán vẫn có thể dễ đổ vỡ trong thực tế |
| Phương án dự phòng dùng lại các ứng viên bị loại | Phương án thay thế giải thích được và hợp bối cảnh |
| User Profile là prior, xếp hạng sau constraint | Hành vi trong quá khứ không được lấn át chuyến đi hiện tại hay constraint của nó |
| Session profile và long-term profile tách riêng | Sở thích có thể thay đổi trong một chuyến mà không viết lại gu dài hạn |
| Lịch sử trải nghiệm tách khỏi sở thích | Đã đến không có nghĩa là thích; chưa trải nghiệm không có nghĩa là không thích |
| Dữ liệu địa điểm do agent xây, được kiểm tra bằng gate và định tuyến rủi ro | Mở rộng theo số địa điểm; công sức của người tăng theo rủi ro, không theo kích thước corpus |
| Cố định vai trò model, không cố định model | Đổi model bằng config khi nhãn review cho thấy model tốt hơn hoặc rẻ hơn |
