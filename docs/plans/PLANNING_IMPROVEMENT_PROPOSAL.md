# Đề xuất cải tiến Module Planning --- TripGuardian

> **Mục tiêu:** cải tiến module Planning theo hướng data-driven, dễ kiểm
> thử và có thể triển khai từng phần; kết hợp heuristic, System One
> (Clef), LLM và thuật toán tối ưu lịch trình mà chưa cần huấn
> luyện một model ML riêng.

## 1. Định hướng thiết kế

Không giao toàn bộ việc lập lịch cho một LLM. Chia bài toán thành các
phần có trách nhiệm rõ ràng:

1.  **Dữ liệu và heuristic:** tính toán định lượng, lọc điều kiện cứng,
    tạo điểm khởi đầu.
2.  **System One --- Clef/Laya:** suy luận nhanh trên yêu cầu ngôn ngữ,
    chuẩn hóa sở thích và phân loại trường hợp đơn giản.
3.  **LLM tổng quát:** xử lý yêu cầu mơ hồ, mâu thuẫn hoặc trường hợp mà
    System One chưa xử lý tốt.
4.  **Bộ tối ưu lịch trình:** chọn địa điểm, thứ tự và giờ ghé thăm sao
    cho khả thi và phù hợp với người dùng.
5.  **Validator:** kiểm tra kết quả cuối cùng trước khi trả về người
    dùng.

Clef được gọi qua API và hiện không cần tối ưu xoay quanh rate limit.
Tuy nhiên, vẫn cần đo latency, chi phí, độ ổn định và chất lượng; thêm
một lượt gọi model không mặc nhiên làm hệ thống nhanh hơn.

## 2. Kiến trúc pipeline đề xuất

``` text
Yêu cầu người dùng
        |
        v
[1. Parse đầu vào + lấy hồ sơ chuyến đi]
        |
        v
[2. Heuristic và dữ liệu địa điểm]
  - lọc theo vị trí, ngân sách, ngày đi
  - kiểm tra giờ mở cửa
  - thống kê khách theo khung giờ
  - ước lượng thời lượng tham quan
        |
        v
[3. System One: Clef/Laya]
  - phân loại ý định
  - trích xuất sở thích
  - xác định ưu tiên / điều cần tránh
  - đánh giá mức độ bất định
        |
        +---------------------------+
        |                           |
        v                           v
 [Kết quả hợp lệ, đủ tin cậy]  [Mơ hồ / mâu thuẫn / thiếu dữ kiện]
        |                           |
        |                           v
        |                    [4. LLM fallback]
        |                    - diễn giải ngữ cảnh
        |                    - làm rõ xung đột
        |                    - không tự bịa dữ kiện
        |                           |
        +-------------+-------------+
                      |
                      v
[5. Candidate scoring / xếp hạng địa điểm]
                      |
                      v
[6. Bộ tối ưu lịch trình: OR-Tools hoặc heuristic]
                      |
                      v
[7. Validator + sửa / tối ưu lại nếu cần]
                      |
                      v
Lịch trình + lý do đề xuất + các giả định
```

**Nguyên tắc:** không bắt buộc mọi yêu cầu phải gọi tất cả thành phần.
Heuristic xử lý điều chắc chắn; System One xử lý phần suy luận có cấu
trúc; LLM chỉ tham gia khi giá trị kỳ vọng của nó lớn hơn chi phí và độ
trễ bổ sung.

## 3. Tận dụng dữ liệu địa điểm hiện có

Hiện có hai nhóm dữ liệu quan trọng:

-   Lượng khách hoặc số lượt ghé theo các khung giờ: sáng, trưa, chiều,
    tối.
-   Thời gian vào/ra hoặc thời lượng lưu lại tại địa điểm.

### 3.1. Chuẩn hóa mức độ phổ biến theo giờ

Với địa điểm `i`, khung giờ `t`, số lượt khách `N[i,t]`, có thể tính:

\[ P\_{i,t} = `\frac{N_{i,t}}{\sum_t N_{i,t}}`{=tex} \]

Chỉ số này thể hiện **tỷ trọng lượt khách**, không nhất thiết phản ánh
mật độ đông thực tế. Nếu có dữ liệu sức chứa, mật độ theo thời gian hoặc
quan sát hàng chờ, hãy dùng chúng để ước lượng mức đông riêng.

Không mặc định khung giờ ít lượt khách luôn là khung giờ tốt nhất. Một
địa điểm ngắm cảnh có thể phù hợp với thời điểm ánh sáng đẹp hơn; quán
cà phê có thể phù hợp buổi sáng; một điểm tham quan ngoài trời có thể bị
ảnh hưởng bởi thời tiết.

### 3.2. Ước lượng thời lượng tham quan

Từ thời điểm vào và ra, tính:

\[ d = t\_{`\text{exit}`{=tex}} - t\_{`\text{entry}`{=tex}} \]

Quy trình đề xuất:

-   Loại bản ghi lỗi, thời lượng âm hoặc bất hợp lý.
-   Dùng median làm ước lượng baseline ít nhạy với ngoại lệ.
-   Lưu thêm phân vị P25, P75, P90 để biểu diễn khoảng thời lượng.
-   Ghi lại số lượng mẫu và độ biến thiên để đánh giá độ tin cậy.
-   Nếu địa điểm có ít dữ liệu, fallback sang thống kê theo loại địa
    điểm hoặc heuristic.

Có thể tạo thời lượng cá nhân hóa mà chưa cần ML:

\[ d\_{`\text{user}`{=tex}} = d\_{`\text{baseline}`{=tex}}
`\times `{=tex}f\_{`\text{pace}`{=tex}}
`\times `{=tex}f\_{`\text{activity}`{=tex}} \]

Trong đó các hệ số cần được giới hạn trong khoảng hợp lý và hiệu chỉnh
qua thử nghiệm. Ví dụ, nhịp độ thong thả có thể tăng thời gian dự kiến;
nhu cầu chụp ảnh có thể tăng thời lượng ở điểm ngắm cảnh. Không nên dùng
cùng một hệ số cho mọi loại địa điểm.

Nếu dữ liệu đủ lớn về sau, có thể thử mô hình hồi quy hoặc quantile
regression; đây không phải điều kiện để triển khai phiên bản đầu.

### 3.3. Tách ba khái niệm

Không gộp những tín hiệu sau thành một chỉ số không rõ nghĩa:

-   **Popularity:** địa điểm/khung giờ được ghé nhiều đến đâu.
-   **Crowd level:** mức độ đông thực tế, nếu dữ liệu đủ để ước lượng.
-   **Time suitability:** mức phù hợp của khung giờ với hoạt động, điều
    kiện và sở thích.

Tách riêng giúp tránh kết luận sai từ dữ liệu và dễ giải thích vì sao
một khung giờ được đề xuất.

## 4. Heuristic scoring cho địa điểm và khung giờ

Với mỗi địa điểm `i` và khung giờ `t`, tính điểm phù hợp sơ bộ:

\[ S(i,t) = w_a A(i,t) + w_u U(i) + w_p
P\_{`\text{preference}`{=tex}}(i) - w_c C(i,t) - w_r R(i,t) \]

Trong đó:

-   `A(i,t)`: độ phù hợp của thời điểm với hoạt động (ví dụ, quán cà phê
    buổi sáng).
-   `U(i)`: độ phù hợp với sở thích người dùng.
-   `P_preference(i)`: mức ưu tiên địa điểm do người dùng hoặc hệ thống
    xác định.
-   `C(i,t)`: chi phí bất tiện hoặc mức đông, nếu có dữ liệu đáng tin
    cậy.
-   `R(i,t)`: rủi ro như thời tiết, thời gian di chuyển khó dự đoán hoặc
    dữ liệu kém tin cậy.
-   `w_*`: trọng số cần được cấu hình và đánh giá, không nên coi là hằng
    số đúng cho mọi tình huống.

**Giờ mở cửa, ngày đóng cửa, thời lượng bắt buộc và thời hạn người dùng
là ràng buộc cứng**, không chỉ là thành phần trừ điểm. Nếu chưa có dữ
liệu để tính một thành phần, bỏ qua hoặc đánh dấu thiếu dữ liệu thay vì
bịa ra điểm chính xác.

Ban đầu, dùng quy tắc dễ hiểu và trọng số cấu hình. Chỉ cân nhắc học
trọng số khi đã có dữ liệu phản hồi hoặc lịch trình được đánh giá.

## 5. Vai trò của System One --- Clef/Laya

### 5.1. Những nhiệm vụ nên giao

System One phù hợp để thử nghiệm cho các tác vụ đầu ra ngắn, có schema
rõ ràng:

-   Phân loại ý định: tham quan, nghỉ dưỡng, ẩm thực, chụp ảnh, khám
    phá.
-   Trích xuất sở thích: nhịp độ, hoạt động ưu tiên, mức muốn tránh
    đông, ngân sách nếu người dùng nêu.
-   Phân loại yêu cầu thành đơn giản, mơ hồ hoặc có mâu thuẫn.
-   Xếp hạng sơ bộ các phương án đã được heuristic lọc.
-   Chuẩn hóa câu tự nhiên thành cấu trúc dữ liệu để các module sau
    dùng.

Không nên mặc định System One giỏi hơn heuristic ở tác vụ định lượng.
Thống kê khách, tính thời lượng trung vị, kiểm tra giờ mở cửa và tính
thời gian di chuyển nên do code/dịch vụ dữ liệu thực hiện.

### 5.2. Schema đầu ra gợi ý

``` json
{
  "activities": ["photography", "sightseeing"],
  "pace": "relaxed",
  "crowd_preference": "avoid_crowds",
  "budget_level": "moderate",
  "time_constraints": {
    "return_before": "17:00"
  },
  "must_visit": [],
  "avoid": [],
  "ambiguities": [],
  "needs_llm_review": false,
  "reason_codes": [
    "explicit_activity_preference",
    "explicit_time_constraint"
  ]
}
```

Schema chỉ là ví dụ. Chỉ điền trường có bằng chứng trong yêu cầu hoặc hồ
sơ người dùng. Trường không được đề cập nên để `null`, danh sách rỗng
hoặc trạng thái `unknown` theo quy ước; không suy diễn ngân sách hay sở
thích quá cụ thể.

### 5.3. Prompt và kiểm tra đầu ra

Trước khi fine-tune, nên thử theo thứ tự:

1.  Prompt có nhiệm vụ và nhãn đầu ra rõ ràng.
2.  Một số ví dụ đa dạng, bao gồm cách diễn đạt gián tiếp và câu phủ
    định.
3.  Yêu cầu JSON theo schema cố định.
4.  Kiểm tra schema, enum, trường bắt buộc và tính nhất quán bằng code.
5.  Ghi lại các lỗi theo nhóm để bổ sung ví dụ hoặc điều chỉnh prompt.

Nếu API không hỗ trợ JSON mode, hãy parse có kiểm soát và xử lý lỗi.
Không dùng điểm tự tin do model tự khai báo như xác suất đúng nếu chưa
hiệu chỉnh bằng tập kiểm thử.

### 5.4. Điều kiện fallback sang LLM lớn

Chuyển sang LLM khi một hoặc nhiều điều kiện sau xảy ra:

-   Đầu ra không hợp lệ sau lần sửa/parse được phép.
-   Người dùng đưa ra các ưu tiên xung đột.
-   Yêu cầu mới lạ hoặc không ánh xạ được vào schema.
-   Thiếu thông tin quan trọng có thể làm thay đổi lịch trình.
-   System One thất bại trên những loại trường hợp đã được benchmark xác
    định.

Nếu yêu cầu đơn giản và kết quả đã vượt qua validator, không cần gọi LLM
chỉ để diễn giải lại cùng thông tin.

## 6. Vai trò của LLM tổng quát

LLM nên tập trung vào phần cần hiểu ngữ cảnh:

-   Diễn giải câu tự nhiên phức tạp.
-   Xử lý xung đột giữa các sở thích.
-   Đề xuất câu hỏi làm rõ khi thiếu thông tin thực sự quan trọng.
-   Giải thích vì sao một nhóm địa điểm phù hợp với nhu cầu.
-   Phân tích trường hợp System One không xử lý tốt.

LLM không phải nguồn sự thật cho dữ liệu địa điểm. Tên, tọa độ, giờ mở
cửa, giá, thời lượng thực đo và thời gian di chuyển phải đến từ
database, API hoặc nguồn được kiểm chứng. Kết quả LLM cần được chuyển về
schema chuẩn trước khi dùng tiếp.

## 7. Bộ tối ưu lịch trình

### 7.1. Mô hình hóa

Sau khi có danh sách địa điểm ứng viên và điểm phù hợp, bộ tối ưu lựa
chọn:

-   Địa điểm nào nên ghé.
-   Thứ tự ghé thăm.
-   Giờ bắt đầu và kết thúc tại từng nơi.
-   Thời gian di chuyển giữa các nơi.
-   Thời lượng dự kiến ở mỗi nơi.
-   Khoảng nghỉ và thời gian dự phòng.

Có thể dùng **OR-Tools CP-SAT** để biểu diễn các ràng buộc thời gian và
lựa chọn địa điểm. Nếu bài toán ban đầu nhỏ, có thể bắt đầu bằng
heuristic như nearest-neighbor có xét time window, insertion heuristic
hoặc local search rồi nâng cấp khi cần.

### 7.2. Mục tiêu tối ưu

Một hàm mục tiêu ban đầu có thể là:

\[ `\max `{=tex}`\left`{=tex}( `\sum`{=tex}\_i x_i
`\cdot `{=tex}`\text{PreferenceScore}`{=tex}\_i -`\lambda`{=tex}\_1
`\cdot `{=tex}`\text{TravelTime}`{=tex} -`\lambda`{=tex}\_2
`\cdot `{=tex}`\text{ScheduleOverload}`{=tex} -`\lambda`{=tex}\_3
`\cdot `{=tex}`\text{CrowdCost}`{=tex} `\right`{=tex}) \]

Trong đó `x_i` cho biết địa điểm `i` có được chọn hay không. Chỉ đưa
`CrowdCost` vào nếu dữ liệu đông đúc đủ đáng tin cậy. Các hệ số `lambda`
phải được đánh giá bằng test case và phản hồi, không nên điều chỉnh tùy
tiện.

### 7.3. Ràng buộc cứng

-   Không lên lịch ngoài giờ mở cửa.
-   Không trùng thời gian giữa hai địa điểm.
-   Thời gian di chuyển phải được tính giữa các điểm liên tiếp.
-   Tôn trọng giờ bắt đầu/kết thúc và thời hạn người dùng.
-   Đáp ứng các địa điểm bắt buộc nếu lịch trình khả thi.
-   Không vượt ngân sách khi ngân sách là giới hạn cứng.
-   Thời lượng tham quan phải nằm trong khoảng hợp lý.
-   Có thể thêm thời gian nghỉ và buffer để giảm nguy cơ trễ.

Nếu không thể thỏa tất cả yêu cầu, không âm thầm trả về lịch trình vi
phạm. Hãy báo phần nào không khả thi và đề xuất nới lỏng ràng buộc ít
quan trọng hơn.

## 8. Validator và cơ chế sửa lịch trình

Sau khi optimizer tạo lịch trình, chạy kiểm tra độc lập:

-   Giờ mở cửa và ngày hoạt động.
-   Thời gian di chuyển, thời gian ghé thăm và thời gian kết thúc.
-   Địa điểm bắt buộc và địa điểm bị loại trừ.
-   Ngân sách và các giới hạn đã nêu.
-   Dữ liệu thiếu hoặc chưa xác minh.

Nếu lỗi có thể sửa bằng thuật toán, hãy sửa/ tối ưu lại. Không cần gọi
LLM cho lỗi tính toán có quy tắc rõ ràng. Chỉ gọi LLM khi lỗi bắt nguồn
từ yêu cầu mơ hồ hoặc cần thương lượng ưu tiên với người dùng.

## 9. Chiến lược triển khai theo giai đoạn

### Giai đoạn 1 --- Baseline không ML

-   Chuẩn hóa dữ liệu lượt khách và thời lượng tham quan.
-   Tạo heuristic theo loại địa điểm, khung giờ và sở thích.
-   Xây dựng validator.
-   Ghi lại giả định và độ tin cậy của từng trường dữ liệu.

**Kết quả mong đợi:** hệ thống tạo được lịch trình cơ bản, giải thích
được và có thể kiểm thử.

### Giai đoạn 2 --- Tích hợp System One

-   Dùng Clef/Laya để phân loại ý định và trích xuất sở thích.
-   Ép đầu ra theo schema.
-   Bổ sung fallback sang LLM khi cần.
-   Log latency, lỗi schema, tỷ lệ fallback và chất lượng theo từng nhóm
    câu hỏi.

**Kết quả mong đợi:** giảm số lần gọi LLM lớn khi tác vụ đơn giản được
xử lý tốt, mà không làm giảm chất lượng đáng kể.

### Giai đoạn 3 --- Tối ưu lịch trình

-   Bắt đầu bằng heuristic tìm kiếm cho phiên bản nhỏ.
-   Đưa ràng buộc vào OR-Tools khi cần tối ưu nhiều điểm hoặc nhiều
    khung giờ.
-   So sánh chất lượng lịch trình với baseline.
-   Kiểm tra các trường hợp không thể thỏa tất cả yêu cầu.

**Kết quả mong đợi:** lịch trình không chỉ có địa điểm phù hợp mà còn
khả thi về thời gian.

### Giai đoạn 4 --- Hiệu chỉnh theo dữ liệu

-   Thu thập phản hồi: địa điểm được chấp nhận/bỏ qua, thời lượng thực
    tế, mức hài lòng.
-   Điều chỉnh trọng số heuristic.
-   Chỉ thử ML/fine-tuning nếu lỗi lặp lại cho thấy rule và prompt không
    đủ.
-   Giữ một tập kiểm thử cố định để tránh tối ưu quá mức theo ví dụ đã
    biết.

## 10. Kế hoạch đánh giá

So sánh ít nhất ba cấu hình trên cùng một bộ tình huống:

  -----------------------------------------------------------------------
  Cấu hình                Thành phần              Mục tiêu
  ----------------------- ----------------------- -----------------------
  A --- Baseline          Heuristic + LLM +       Mốc chất lượng ban đầu
                          optimizer               

  B --- System One        Heuristic + Clef/Laya + Đo khả năng xử lý mà
                          optimizer               không cần LLM lớn

  C --- Hybrid            Heuristic + Clef/Laya + Cân bằng chất lượng, độ
                          LLM fallback +          trễ và chi phí
                          optimizer               
  -----------------------------------------------------------------------

### Chỉ số cần theo dõi

-   **Preference extraction accuracy:** trích xuất sở thích có đúng
    không.
-   **Schema-valid rate:** tỷ lệ đầu ra hợp lệ.
-   **Fallback rate:** tỷ lệ yêu cầu cần LLM lớn.
-   **Latency:** thời gian trung vị và p95 cho toàn pipeline, không chỉ
    thời gian model.
-   **Feasible itinerary rate:** tỷ lệ lịch trình vượt qua mọi ràng buộc
    cứng.
-   **Constraint violation count:** số lỗi về giờ mở cửa, thời lượng,
    ngân sách hoặc thời hạn.
-   **Acceptance / edit rate:** người dùng chấp nhận hoặc chỉnh sửa lịch
    trình ở mức nào.
-   **Estimated vs. actual dwell time error:** sai số thời lượng khi có
    dữ liệu thực tế.

Để xác định tác dụng thực của từng thành phần, làm ablation: heuristic
đơn thuần, thêm System One, thêm LLM fallback, thêm optimizer. Không kết
luận model nhanh hơn chỉ từ số lần gọi; cần đo thời gian end-to-end trên
cùng tập kiểm thử và điều kiện chạy.

## 11. Các nguyên tắc kỹ thuật cần giữ

1.  **Không cần train ML ngay:** bắt đầu từ thống kê, heuristic, prompt
    và thuật toán tối ưu.
2.  **Không dùng model cho phép tính chắc chắn:** giờ mở cửa, thời
    lượng, tổng chi phí và kiểm tra lịch trình do code thực hiện.
3.  **Không mặc định System One nhanh hơn:** đo latency và chi phí thực
    tế.
4.  **Không coi lượng khách là mật độ đông:** dùng đúng ý nghĩa của dữ
    liệu hiện có.
5.  **Không để LLM tự tạo dữ liệu địa điểm:** mọi dữ kiện thực tế phải
    có nguồn.
6.  **Tách soft preference và hard constraint:** sở thích có thể đánh
    đổi; ràng buộc cứng không được âm thầm vi phạm.
7.  **Có fallback rõ ràng:** đầu ra model sai định dạng hoặc bất định
    không được làm hỏng pipeline.
8.  **Giữ khả năng giải thích:** lưu các yếu tố đóng góp vào điểm xếp
    hạng và lý do chọn lịch trình.
9.  **Đo trước khi tối ưu:** ưu tiên những điểm nghẽn thực tế thay vì
    thêm model theo cảm tính.

## 12. Quyết định đề xuất

Phiên bản đầu tiên nên dùng:

-   `pandas` / `NumPy` để xử lý thống kê.
-   Heuristic để tạo điểm phù hợp theo giờ và cá nhân hóa thời lượng.
-   Clef/Laya API cho trích xuất sở thích và phân loại độ phức tạp.
-   LLM tổng quát làm fallback có điều kiện.
-   OR-Tools hoặc heuristic search để tối ưu thứ tự và thời gian.
-   Validator độc lập để bảo đảm tính khả thi.

Chưa cần fine-tune Laya/Clef hoặc huấn luyện model ML riêng. Trước tiên
hãy hoàn thiện baseline, xây dựng bộ test và đo hiệu quả từng thành
phần. Chỉ điều chỉnh prompt, trọng số hoặc fine-tune khi kết quả kiểm
thử chỉ ra vấn đề cụ thể.

------------------------------------------------------------------------

## Checklist triển khai

-   [ ] Chuẩn hóa dữ liệu khách theo khung giờ và dữ liệu vào/ra.
-   [ ] Tính median, P25, P75, P90 và số mẫu cho thời lượng.
-   [ ] Tách popularity, crowd level và time suitability.
-   [ ] Xây dựng heuristic scoring có trọng số cấu hình.
-   [ ] Định nghĩa schema đầu ra của Clef/Laya.
-   [ ] Viết validator cho đầu ra model.
-   [ ] Định nghĩa điều kiện fallback sang LLM.
-   [ ] Xây dựng bộ test cho câu đơn giản, câu mơ hồ và sở thích xung
    đột.
-   [ ] Thử heuristic search hoặc OR-Tools cho lập lịch.
-   [ ] Đo latency end-to-end, tỷ lệ fallback và tỷ lệ lịch trình khả
    thi.
-   [ ] Ghi log lý do chọn địa điểm/khung giờ để dễ debug.
