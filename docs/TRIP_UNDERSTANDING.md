# Trip Understanding

Bước online đầu tiên: hiểu người dùng cần gì cho **chuyến này** trước khi tìm địa điểm. Vị trí trong luồng: `docs/ARCHITECTURE.md` §3. Vì sao hỏi như vậy (nguyên tắc có căn cứ nghiên cứu) và User Profile: `docs/Project_Context.md` §6–11, §12.1.

Code: `src/trip/`. CLI và API ở §14.

## 1. Trip Understanding là gì

```text
PERSONAL CONTEXT ─┐
(User Profile)    │
                  ├──► TRIP STATE ──► HỎI LÀM RÕ ──► BẢN HIỂU NHU CẦU ──► SEARCH INPUT ──► PLACE DECISION
THÔNG TIN MANG ───┤    (nháp, mỗi     (chỉ phần còn    (user xem, sửa)     (filter, weight,
THEO (anchor,     │     field có       thiếu và đổi                         anchor, unknown)
link, lịch)       │     nguồn)         được kết quả)
                  │
NHU CẦU HIỆN TẠI ─┘
(câu user nói)
```

- Mục tiêu kép: **hiểu đủ để tìm đúng** và **hỏi ít nhất có thể**. Không có questionnaire cố định.
- Output là **Search Input** mà Place Decision dùng trực tiếp, không phải đoạn văn mô tả nhu cầu.
- Không bịa: field chưa biết giữ `unknown`, không tự điền, không suy thành "không thích".
- Chưa đề xuất địa điểm nào cho user trong bước này. Hệ thống được phép truy vấn Place Intelligence **ngầm** để quyết định câu hỏi nào đáng hỏi (§6).

## 2. Ba nguồn đầu vào

| Nguồn | Gồm | Vai trò | Độ tin |
|---|---|---|---|
| **Personal context** (User Profile, chỉ khi user đồng ý) | Demonstrated Preferences, Recent Interests, Experience History, Behavioral Defaults (`Project_Context.md` §6.2) | Giá trị **mặc định** (prior) | Thấp nhất; bị ghi đè dễ |
| **Thông tin mang theo** | Link TikTok / Maps đã lưu, nơi bắt buộc đến, booking, giờ xe / máy bay, lịch có sẵn | **Anchor** + tín hiệu gu ngầm (6 link đều là quán cà phê view đồi → gu rõ) | Trung bình – cao |
| **Nhu cầu hiện tại** | Câu user gõ, câu trả lời làm rõ, lựa chọn chip | **Sự thật của chuyến này** | Cao nhất |

Khi các nguồn mâu thuẫn, thứ tự ưu tiên cố định:

```text
Physical Constraint → User Hard Constraint → Override của chuyến này → Recent Interests → Demonstrated Preferences
```

Ví dụ: profile có `hiking = high`, chuyến này "đi với bố mẹ, mẹ đau gối" → hiking bị tắt **cho chuyến này**, không hỏi lại, không sửa long-term profile.

Trạng thái bắt đầu (khám phá / đã lưu / anchor / lịch có sẵn) và mức dẫn dắt là hai trục độc lập (`Project_Context.md` §3.1). Trạng thái bắt đầu có sẵn trong input và quyết định **luồng bắt đầu từ đâu**; mức dẫn dắt suy từ hành vi trong phiên và quyết định **cách hỏi**. Không trục nào trực tiếp quyết định địa điểm.

Việc user đã từng đến Đà Lạt hay chưa không đổi cách hỏi. Nó chỉ vào Trip State qua `visited` khi user nêu nơi đã đi, phục vụ Novelty.

## 3. Trip State

```text
Trip State
├── Thông tin cơ bản   start_date | month, days, companions, people, base (chỗ ở), mobility, budget_vnd
├── Điểm vào / ra      entry_point, exit_point — nơi chuyến đi vào và rời thành phố (bến xe, sân bay, tự lái)
├── Khung giờ          arrive_at, leave_at, day_end
├── Anchor             nơi bắt buộc, booking, sự kiện giờ cố định; độ ưu tiên must | want
├── Constraint         hard: physical constraint + user hard constraint
├── Sở thích           soft: override của chuyến, session profile, mặc định từ long-term profile
├── Nhịp độ            pace thong thả | cân bằng | đi nhiều  +  max_leg_min, crowd_tolerance
├── Novelty            theo gu quen | thử mới | trộn  +  visited (Experience History)
└── meta               start_with, guidance, effort_budget, control, lượt đã hỏi, đã bỏ qua, từ chủ quan còn chờ làm rõ
```

`entry_point` / `exit_point` là nơi Planning neo ngày đầu và ngày cuối. Chỉ lưu text + `place_id`; geocode xảy ra ở Planning nên `trip` không phụ thuộc `live`. Thiếu → ngày đầu / cuối chỉ bị cắt theo `arrive_at` / `leave_at` và mang cờ "ước lượng ngày đầu / cuối kém chắc" (`docs/PLANNING.md` §Đầu vào).

Mỗi field không lưu giá trị trần mà lưu kèm nguồn và trạng thái:

```text
field
├── value
├── source       user | anchor | profile | inferred | default
├── confidence   high | medium | low
├── status       unknown | asked | confirmed | skipped
└── evidence     câu / lượt / anchor sinh ra giá trị (để giải thích và cho user sửa)
```

Bảng này quyết định hành động cho từng field:

| Trạng thái field | Hành động |
|---|---|
| `source = user`, `confirmed` | Dùng, không hỏi lại |
| `source = profile` hoặc `anchor` | **Xác nhận** 1 chạm, không hỏi mở ("Như mọi lần bạn thích đi sớm, giữ vậy nhé?") |
| `source = inferred`, confidence đủ | Dùng, đánh dấu ✎ trong bản hiểu nhu cầu |
| `source = inferred`, confidence thấp | Đưa vào mục "còn chưa chắc", hoặc hỏi nếu đổi kết quả |
| `unknown`, không đổi kết quả | Bỏ, giữ `unknown` |
| `skipped` | Không hỏi lại trong session |

### Tầng dữ liệu đầu vào

```text
Tầng 0  Trước khi gõ gì         không yêu cầu gì
Tầng 1  Chặn kiểm tra khả thi    days, start_date | month, companions + people, mobility, base
Tầng 2  Miễn phí nếu user mang   link đã lưu, booking, giờ xe / máy bay → anchor, entry/exit, gu ngầm
Tầng 3  Chỉ hỏi khi đổi kết quả  budget_vnd, pace, max_leg_min, crowd_tolerance, novelty, sở thích
Tầng 4  Fail-closed              physical constraint — hỏi ngay khi có tín hiệu, bất kể điểm §6
```

Tầng 1 gom vào **một thẻ chip ở lượt mở đầu**, không tách thành nhiều lượt hỏi. `base` để trống được; thiếu thì Planning mang cờ "ước lượng kém chắc".

Tối thiểu tuyệt đối trước đề xuất đầu tiên: `days`, `companions`, `mobility`. Mọi field khác được phép `unknown`.

Tài khoản và User Profile được xin sau khi user đã thấy kết quả đầu, không xin trước (`Project_Context.md` §6.1).

---

## 4. Luồng xử lý

Luồng lặp theo từng lượt hội thoại, không phải một form tuần tự.

```text
① NẠP PRIOR        Mẫu dài hạn đã lưu (nếu có user id, §17) + anchor/link đã có → Trip State nháp
② MỞ ĐẦU           Câu tự do + thẻ khung bằng chip (ngày · đi với ai · đi lại bằng gì)
③ TRÍCH XUẤT       LLM tách một câu thành nhiều field; phát hiện từ chủ quan ("chill", "yên tĩnh")
                   và tín hiệu nhạy cảm ("bố mẹ", "trẻ nhỏ", "đau gối", "say xe")
④ GỘP + XUNG ĐỘT   Nhu cầu hiện tại ghi đè profile theo thứ tự §2; xung đột rõ thì tự xử lý, không hỏi
⑤ TÌM LỖ HỔNG      Liệt kê field unknown / chưa chắc, xếp theo §5
⑥ CHỌN HÀNH ĐỘNG   HỎI · XÁC NHẬN · SUY · DỪNG
⑦ LẶP ③–⑥          Tới khi gặp điều kiện dừng (§7)
⑧ BẢN HIỂU NHU CẦU User xem và sửa trực tiếp (§8)
⑨ BIÊN DỊCH        Trip State → Search Input (§9)
```

Phân vai:

| Việc | Ai làm | Lý do |
|---|---|---|
| Tách field từ câu tự do, phát hiện từ chủ quan, sinh câu nối tiếp / laddering, diễn đạt theo giọng §13 | LLM | Ngôn ngữ tự do, mơ hồ |
| Chọn câu tiếp theo, điều kiện dừng, ghi Trip State, biên dịch Search Input | Rule tất định | Test được, tái lập được, không trôi hành vi khi đổi model |

LLM được đề xuất câu hỏi nối tiếp (nhóm I), nhưng câu trả lời luôn được chuẩn hóa về field của Trip State.

## 5. Chọn câu hỏi tiếp theo

Ba tầng, xét theo thứ tự. Ngân hàng câu hỏi nhóm A–I: §12.

```text
Tầng 1 — BẮT BUỘC (rule, không chấm điểm)
   Tín hiệu an toàn / thể chất xuất hiện       → nhóm C
   Field chặn kiểm tra khả thi còn thiếu       → nhóm A (ngày, base, phương tiện)
   User dán link / nêu nơi cụ thể              → nhóm E (xác nhận anchor, độ ưu tiên)

Tầng 2 — ĐI THEO MẠCH USER
   Câu tiếp theo bám vào điều user vừa mở ra
   Từ chủ quan → làm rõ nghĩa · nêu nơi cụ thể → hỏi "vì sao" (tối đa 1–2 bậc)

Tầng 3 — GIÁ TRỊ THÔNG TIN (chấm điểm, §6)
   Trong các câu còn lại, chọn câu làm tập ứng viên đổi nhiều nhất trên mỗi đơn vị công sức
```

Sau tầng 1, nếu phiên có prior từ mẫu dài hạn, **một thẻ xác nhận** (`prior`, §17) đứng trước mọi câu thích ứng: giữ cả nhóm một chạm thay vì hỏi từng field.

Nhóm C nằm ở tầng 1 vì câu an toàn có thể có điểm thấp ở tầng 3 (hiếm gặp) nhưng sai thì hậu quả nặng. Constraint cứng vẫn fail-closed.

## 6. Đo "câu hỏi có đổi kết quả không"

Place Intelligence được xây offline nên truy vấn rẻ. Hệ thống thử ngầm từng đáp án khả dĩ trên serving index:

```text
với mỗi field chưa biết f:
    với mỗi đáp án khả dĩ a (các chip của câu hỏi):
        TopK(a) = lọc + xếp hạng ứng viên giả sử f = a
    impact(f) = Σ P(a) · distance(TopK(a), TopK_hiện_tại)
    score(f)  = impact(f) / cost(f)
```

| Thành phần | Nguồn |
|---|---|
| `P(a)` | Profile nếu có; cold start dùng phân bố chung của user, không có thì phân bố đều |
| `distance` | Jaccard trên top-K, hoặc tỉ lệ ứng viên bị loại |
| `cost(f)` | Độ khó trả lời + độ nhạy cảm (ngân sách, sức khỏe cost cao hơn nhịp độ) |

Ví dụ: 6 anchor rải rác → `travel tolerance` chia top-K mạnh → score cao. Chỉ 1 anchor ở trung tâm → câu đó gần như không đổi gì → bỏ.

Feature trong Search Input dùng chung id với feature ontology của corpus (`docs/CORPUS.md` §Bản ghi địa điểm), nên việc thử đáp án chạy thẳng trên serving record.

## 7. Điều kiện dừng

Dừng hỏi khi gặp một trong các điều kiện:

- `score` cao nhất còn lại dưới ngưỡng: không câu nào đổi tập ứng viên đáng kể.
- Hết ngân sách lượt (`turn_budget`, mặc định 5 lượt thích ứng sau thẻ mở đầu, trước đề xuất đầu tiên): ngân sách là sức người dùng chịu trả lời.
- `idle_limit` câu thích ứng liên tiếp không thêm gì vào Trip State (trả lời không đổi field nào, kể cả `Bỏ qua`): câu hỏi lặp mà không sinh thông tin thì dừng sớm.
- User chọn `Không chắc` / `Bỏ qua` liên tiếp, hoặc trả lời cụt.
- User yêu cầu "xem gợi ý trước" (mixed initiative, được phép bất cứ lúc nào).

Một câu gõ khi thẻ đang mở chỉ tính là đã trả lời thẻ khi nó ghi được field của thẻ (thẻ do agent viết: thêm được bất cứ gì). Câu không trả lời (lạc đề, hỏi ngược) giữ thẻ mở và không tốn ngân sách lượt; câu thứ hai như vậy liên tiếp trên cùng thẻ thì thẻ tính là đã hỏi. Câu không thêm gì vẫn tính vào `idle_limit`.

Chip và câu gõ gửi cùng một lượt: giá trị câu gõ nêu rõ thay giá trị chip cho cùng field, và lời đáp nói rõ "Mình ghi theo câu bạn gõ: …" thay vì ghi đè lặng lẽ.

"Xem gợi ý" không biến `unknown` của hard constraint thành pass: câu bắt buộc còn thiếu vẫn được hỏi lại (fail-closed).

Sau khi dừng, field còn thiếu giữ `unknown`. Hệ thống chuyển sang đề xuất và học tiếp từ phản hồi: compare, critique, lý do bỏ (`Project_Context.md` §8.3–8.4).

## 8. Bản hiểu nhu cầu

Hiển thị trước khi tìm địa điểm. Mỗi dòng cho biết giá trị đến từ đâu.

```text
Chuyến     3 ngày 12–14/12 · ở trung tâm · ô tô riêng · đi với bố mẹ
Anchor     [TikTok 1] [TikTok 2]
Bắt buộc   tránh dốc/bậc · đi bộ ≤ 15 phút
Sở thích   yên tĩnh, có view, ngồi lâu · cà phê (từ profile ✎) · ưu tiên nơi chưa đi
Nhịp độ    thong thả (suy luận ✎)
Chưa rõ    ngân sách · ăn uống
```

- `✎` = từ profile hoặc suy luận. User sửa tại chỗ, kể cả phần lấy từ profile.
- Sửa ở đây là override **của chuyến này**, không tự ghi vào long-term profile.
- Mục "Chưa rõ" hiển thị công khai, không giấu.

## 9. Search Input

Output cuối cùng, đầu vào của Place Decision (`docs/PLACE_DECISION.md` §2.1). Kiểu: `trip.SearchInput`. Mỗi `hard_filter` mang `unknown_policy` (`exclude` | `flag`) để Place Decision biết phải fail-closed tới mức nào.

```text
Search Input
├── context        start_date | month, days, base, entry_point, exit_point, mobility, companions,
│                  people, arrive_at, leave_at, day_end, budget_vnd, experience
├── hard_filters   physical + user hard constraint            → loại ứng viên (fail-closed)
├── anchors        nơi bắt buộc + độ ưu tiên                  → giữ; đánh giá xung quanh chúng
├── soft_weights   sở thích đã làm rõ, theo feature id         → xếp hạng
├── pace           thong thả | cân bằng | đi nhiều + travel/crowd tolerance
├── novelty        quen | mới | trộn; danh sách nơi đã đi      → giảm / loại nơi đã đi khi muốn mới
├── unknowns       field chưa rõ                               → không lọc, xếp hạng trung tính, gắn cờ khi giải thích
└── unmapped       tên người dùng nêu mà chưa resolve được     → Place Decision hỏi lại
```

Từ chủ quan phải được biên dịch thành feature trước khi vào `soft_weights`:

| User nói | Sau khi làm rõ | Vào Search Input |
|---|---|---|
| "chill" | ít người + có view + ngồi lâu | `crowd_low↑`, `view↑`, `long_stay↑` |
| "đi với bố mẹ" + "mẹ đau gối" | tránh dốc/bậc | `hard_filters: effort.slope = none, walk ≤ 15'` |
| "lần này muốn khác" | thử mới | `novelty = high`, loại Experience History |
| "Không chắc" về ngân sách | — | `unknowns: budget` |

Quy tắc cho `unknown`: không dùng để lọc, không suy thành "không thích". Place Decision giải thích rõ khi một đề xuất phụ thuộc vào field chưa biết.

## 10. Điều chỉnh theo người dùng

Không chia persona với kịch bản hỏi riêng. Ngân hàng câu hỏi dùng chung; thứ thay đổi là ba tham số `guidance`, `effort_budget`, `control` (`Project_Context.md` §3.3); căn cứ nghiên cứu ở `Project_Context.md` §12.1.

| Tín hiệu | Cách hỏi |
|---|---|
| Trả lời ngắn, chưa nêu được tiêu chí, chủ yếu bấm chip | Hỏi theo cách dùng ("chuyến này để làm gì"), luôn có chip, cho "xem gợi ý trước" sớm |
| Tự nêu tiêu chí, gọi tên khu vực cụ thể, nhắc chuyến trước | Hỏi thẳng tiêu chí; ưu tiên nhóm H (đã đi đâu, muốn mới hay quen) |
| Chưa có ý tưởng | Nhiều câu mở + ví dụ, có thể chọn ảnh |
| Có địa điểm đã lưu / lịch sơ bộ | Bắt đầu từ xác nhận anchor + constraint; ít câu sở thích |
| Trả lời dài, tự nêu tiêu chí | Lựa chọn chi tiết, cho chỉnh từng tiêu chí |
| Trả lời cụt, nhiều `Không chắc` | Ít câu, chuyển sớm sang đề xuất rồi critique |

Chỉ dùng thông tin user đã cung cấp hoặc thể hiện trong hội thoại. Không suy đoán tuổi, giới tính hay đặc điểm cá nhân.

## 11. Trải nghiệm người dùng

| Vấn đề | Cách xử lý |
|---|---|
| Hỏi nhiều → mệt | Câu dễ gộp vào một thẻ chip; câu thích ứng có ngân sách lượt |
| Hỏi lại cái đã biết | Xác nhận 1 chạm thay vì hỏi mở |
| User không biết trả lời | Hỏi cách dùng, không hỏi thuộc tính; luôn có chip gợi ý + nhập tự do |
| `Không chắc` | Hợp lệ; ghi `unknown`, học tiếp qua đề xuất |
| Không hiểu vì sao bị hỏi | Nói lý do hoặc tác động ("để tránh chỗ leo dốc", "còn 38 → 14 nơi") |
| Hệ thống đoán sai | Bản hiểu nhu cầu đánh dấu ✎ phần suy luận / profile; sửa tại chỗ |
| Hệ thống nhớ gu từ các chuyến trước | Một thẻ "giữ như mọi lần / chuyến này khác" thay cho nhiều câu; chỉ nhớ khi user đồng ý; xóa được (§17) |
| Câu nhạy cảm (sức khỏe, ngân sách, ăn kiêng) | Giọng trung tính, nói rõ vì sao hỏi, luôn có `Bỏ qua` |

## 12. Ngân hàng câu hỏi

Bộ câu hỏi là **ngân hàng**, không phải form; nhóm A–I là nhóm chủ đề, **không phải thứ tự hỏi** (thứ tự do §5 quyết định). Hệ thống chỉ lấy câu còn thiếu và có khả năng đổi kết quả (`Project_Context.md` §12.1 #1); câu đã biết từ input, anchors hoặc User Profile thì hiển thị để xác nhận thay vì hỏi lại (`Project_Context.md` §7.1). Mọi câu đều có `Không chắc` và `Bỏ qua`.

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

**F. Nhịp độ và mức chịu đựng** — soft; lấy mặc định từ Behavioral Defaults nếu có (`Project_Context.md` §6.2).

| Câu hỏi mẫu | Lựa chọn gợi ý | Ghi vào |
| ----------- | -------------- | ------- |
| Chuyến này thiên về nghỉ ngơi hay khám phá nhiều nơi? | thong thả · cân bằng · đi nhiều | `pace` |
| Một chặng di chuyển tối đa bao lâu thì bạn vẫn thấy ổn? | ≤ 15 · ≤ 30 · ≤ 60 phút | `travel tolerance` |
| Chỗ đông người thì sao? | tránh · chấp nhận nếu đáng · không ngại | `crowd tolerance` |
| Bạn hay bắt đầu ngày lúc mấy giờ? | sớm (săn mây) · bình thường · muộn | Behavioral Defaults |
| Nếu trời mưa, bạn muốn? | đổi sang trong nhà · giữ nguyên nếu được · để hệ thống đề xuất | `trip-specific override` |

**G. Mục đích và kiểu trải nghiệm** — soft; hỏi theo cách dùng (`Project_Context.md` §12.1 #4).

| Câu hỏi mẫu | Lựa chọn gợi ý | Ghi vào | Căn cứ |
| ----------- | -------------- | ------- | ------ |
| Chuyến này chủ yếu để làm gì? | thoát khỏi nhịp thường ngày · thư giãn · gắn kết người đi cùng · thiên nhiên · văn hóa/ẩm thực địa phương · chụp ảnh · thử điều mới | preference của chuyến (`trip-specific override`) | [19], [20] |
| Bạn hình dung khoảnh khắc đáng nhớ nhất của chuyến này là gì? | nhập tự do | preference của chuyến | [8], [15] |
| Chọn vài ảnh bạn thấy "đúng chất" chuyến này. | lưới ảnh | preference của chuyến | [21] |

**H. Kinh nghiệm và mức mới lạ** — chỉ dùng khi user tự nhắc tới chuyến trước.

| Câu hỏi mẫu | Lựa chọn gợi ý | Ghi vào | Căn cứ |
| ----------- | -------------- | ------- | ------ |
| Bạn đã đến Đà Lạt chưa? Lần trước đã đi đâu? | chưa · rồi + chọn nơi đã đi | Experience History | [20] (động cơ đổi theo kinh nghiệm: người có kinh nghiệm thiên về trải nghiệm văn hóa địa phương, thiên nhiên) |
| Lần này muốn quay lại chỗ quen hay thử cái mới? | theo gu thường ngày · muốn thử điều mới · trộn | `trip-specific override` (novelty) | `Project_Context.md` §6.3, §7.1 |

**I. Câu hỏi nối tiếp** — chỉ xuất hiện khi được kích hoạt.

| Khi nào | Câu hỏi mẫu | Căn cứ |
| ------- | ----------- | ------ |
| User dùng từ chủ quan ("chill", "yên tĩnh") | Với bạn "chill" nghĩa là: ít người · có view · ngồi lâu được · nhạc nhẹ? | [10] |
| User nêu một địa điểm/hoạt động cụ thể | Điều gì ở nơi đó làm bạn muốn đến? | [18] |
| User chọn `Không chắc` nhiều câu liền | Bạn muốn xem vài gợi ý trước rồi chỉnh không? | [16], [17] |
| User bỏ một đề xuất | Vì sao bạn bỏ địa điểm này? (`Project_Context.md` §8.3) | [17] |

Cài đặt: `src/trip/questions.py` (ngân hàng + rule tầng 1), `config/trip.yaml` (`turn_budget`, `idle_limit`, `stop_score`, `top_k`, `patterns`). Căn cứ nghiên cứu của từng nguyên tắc đặt câu hỏi: `Project_Context.md` §12.1.

## 13. Giọng điệu

Mặc định: **gần gũi nhưng không suồng sã** — như một người hướng dẫn du lịch am hiểu, không như bạn thân.

Căn cứ nghiên cứu:

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
## 14. CLI và API

User Web gọi Trip qua harness bằng journey chung (`docs/AGENT_HARNESS.md`). Public API xuất `Tools`, `create_engine`, `SearchInput`; `tools.py` giữ snapshot do Trip sở hữu. `skills.yaml` khai báo quyền Trip; `agent.py` dùng runtime public `agents`. Heuristic trước Agent và điều kiện bypass: `docs/AGENT_HARNESS.md` §5.

API độc lập: `python -m trip serve [--port 8766]` bind `127.0.0.1`. Cần `AGENT_*` trong `.env` (`docs/LLM_PROVIDER.md`); thiếu thì lượt chữ cần suy luận chạy bằng `policy.py`.

```
POST   /api/trip/sessions          {experience?, start_with?, user_id?, remember?}  → phiên mới + thẻ mở đầu
DELETE /api/trip/profile/<user_id>  → {forgotten}  xóa mẫu đã lưu của user
GET    /api/trip/sessions/<id>
POST   /api/trip/sessions/<id>/turn  SSE: say(delta|replace) · view · done · error
GET    /api/trip/places?q=<tên>    tra địa điểm cho anchor / nơi đã lưu (chỉ đọc serving index)
```

Module:

```
src/trip/
  settings.py       ngưỡng từ config/trip.yaml
  text.py           so khớp tên bỏ dấu, bỏ dấu câu
  state.py          TripState (mỗi field có value, source, confidence, status, evidence), SearchInput
  catalog.py        đọc serving index: tên → place_id, coverage của hard filter
  prepass.py        rule tất định đọc câu người dùng trước khi gọi model
  resolve.py        tên người dùng nêu → place_id, hoặc unmapped
  values.py         chuẩn hóa giá trị về field của Trip State
  questions.py      ngân hàng câu hỏi (§12) + rule tầng 1 + chấm giá trị thông tin (§6)
  coverage.py       hard filter này có đủ bằng chứng trong corpus để đáng hỏi không
  patterns.py       phiếu bầu, phát hiện mẫu, nạp prior vào Trip State (§17)
  profile.py        lịch sử phiếu bầu theo user id: data/trip/profiles/<user_id>.json (§17)
  understanding.py  bản hiểu nhu cầu (§8)
  compile.py        Trip State → Search Input (§9)
  agent.py guard.py policy.py   một call mỗi lượt; guard; policy từ khóa khi agent lỗi
  engine.py sessions.py server.py  phiên có phiên bản, HTTP + SSE, cổng 8766
```

Test: `python -m pytest -q tests/trip`; gọi model thật: `python -m pytest -m live tests/trip/test_live.py`.


## 15. Ví dụ đầy đủ

**Có sẵn:** profile `cà phê = high`, `hiking = high`, Behavioral Defaults "dậy sớm"; Experience History: đã đi Hồ Xuân Hương, Langbiang.

**User gõ:** "Tháng 12 đi Đà Lạt 3 ngày với bố mẹ, muốn chill" + 2 link TikTok.

```text
③ Trích xuất   duration = 3 · tháng 12 · companions = bố mẹ · "chill" (chủ quan) · 2 anchor
④ Xung đột     bố mẹ → tắt hiking cho chuyến này (không hỏi)
               đã đi Langbiang → novelty nghiêng về mới (đưa vào bản hiểu nhu cầu để xác nhận)
⑤ Lỗ hổng      tầng 1: physical (tín hiệu người lớn tuổi), ngày cụ thể, base, phương tiện
               tầng 2: nghĩa của "chill"
               tầng 3: nhịp độ → score thấp vì "chill" + bố mẹ đã suy ra thong thả

Lượt 1 (thẻ chip)  Ngày cụ thể? · Ở khu nào? · Đi lại bằng gì?
Lượt 2             "Để tránh chỗ phải leo dốc: bố mẹ có ngại đi bộ xa hoặc bậc thang không?"
                   [Có · Không · Bỏ qua]
Lượt 3             "'Chill' với bạn là: ít người · có view · ngồi lâu được · nhạc nhẹ?"
→ Dừng: câu còn lại (ngân sách, ăn uống) không đổi top-K đáng kể
```

Bản hiểu nhu cầu: như ví dụ ở §8. Search Input tương ứng:

```text
context       12–14/12 · 3 ngày · base = trung tâm · ô tô riêng · bố mẹ
hard_filters  effort.slope = none · walk ≤ 15'
anchors       TikTok 1, TikTok 2
soft_weights  crowd_low↑ · view↑ · long_stay↑ · coffee↑ (profile) · hiking = off (chuyến này)
pace          thong thả
novelty       mới; giảm Hồ Xuân Hương, Langbiang
unknowns      budget, dietary
```

Ba lượt hỏi đủ tạo Search Input chính xác. Phần còn lại lấy từ profile, anchor và suy luận, và user thấy rõ phần nào là suy luận để sửa.

## 16. Đánh giá

Mô phỏng offline: user giả lập bằng LLM, mỗi user có một Trip State ẩn biết trước. So với baseline form cố định.

| Chỉ số | Đo gì |
|---|---|
| Số lượt trước đề xuất đầu | Chi phí trải nghiệm |
| Field sai / thiếu so với Trip State ẩn | Độ hiểu đúng |
| Tỉ lệ `Không chắc` / `Bỏ qua` | Câu hỏi khó hoặc không đáng hỏi |
| Số lần user sửa bản hiểu nhu cầu | Suy luận sai |
| Constraint violation ở bước Planning | Hậu quả của hiểu sai hoặc bỏ sót |

Chỉ số thật từ pilot đi vào `Project_Context.md` §18–19.

## 17. Học mẫu dài hạn

Cá nhân hóa cho lần hỏi sau: gu người dùng lặp lại qua nhiều chuyến trở thành **prior**, xác nhận một chạm thay vì hỏi lại (`Project_Context.md` §8.6, §11). Mặc định **tắt** (`patterns.enabled: false` trong `config/trip.yaml`) cho tới khi cơ chế cập nhật được kiểm bằng khảo sát người dùng.

**Điều kiện chạy.** Cần `patterns.enabled`, `user_id` trên phiên (chuỗi mờ 8–64 ký tự `A-Za-z0-9_-`; khi có đăng nhập sẽ gắn user id này vào tài khoản) và `remember = true` để **ghi**. Có `user_id` mà không `remember` thì chỉ đọc mẫu đã có. Xóa: `DELETE /api/harness/profile/<user_id>` (User Web), `DELETE /api/trip/profile/<user_id>` (API độc lập) hoặc `Engine.forget`.

**Phiếu bầu.** Lúc người dùng bấm xem gợi ý, `votes_from_state` lấy các lựa chọn **tường minh** của phiên: `purpose`, `pace`, `crowd_tolerance`, `novelty`; `soft` do user nói hay chọn (`love` | `avoid`); nơi đã khớp thành anchor. Phiên ghi một `Summary` (id phiên, ngày, phiếu), ghi lại cùng phiên thì thay chứ không cộng. Không bao giờ thành phiếu:

| Không bầu | Vì |
|---|---|
| Field im lặng, `unknown`, `Bỏ qua` | unknown ≠ không thích |
| `visited` | đã đến ≠ đã thích |
| Soft do suy luận / từ khóa đoán | chỉ lựa chọn tường minh |
| Giá trị chỉ được xác nhận từ mẫu đã lưu (`chip:prior`) | tránh vòng lặp tự củng cố; không có filter bubble |
| `signal` sức khỏe / cơ thể, hard filter, ngày, ngân sách, người đi cùng | chỉ ở phiên, không lưu dài hạn |

**Mẫu.** `detect` đọc `window` phiếu gần nhất của từng key. Thành mẫu khi cùng một lựa chọn xuất hiện ở ít nhất `min_sessions` phiên khác nhau, chiếm ít nhất `agreement` cửa sổ, và phiếu gần nhất vẫn là lựa chọn đó (đổi gu thì mẫu mất ngay). Phiếu cuối cũ hơn `stale_days` thì bỏ. Độ tin `medium`; `high` khi số phiên ≥ 2 × `min_sessions`.

**Prior.** `seed` ghi mẫu vào Trip State với `source = profile` (✎ trong bản hiểu nhu cầu); mọi thứ chuyến này nói đều ghi đè, vì chuyến hiện tại thắng profile. Mẫu thúc đẩy vận động (`hiking`, `adventure_activity`, `pace = packed`) bị bỏ ngay khi chuyến có giới hạn vận động (signal hay hard filter). Mẫu về nơi không tự vào chuyến: chỉ hiện thành chip "Thêm <tên>" (anchor `want`) và chỉ khi nơi còn trong serving index. Mẫu mà ontology không còn biết bị bỏ qua.

**Thẻ `prior`** (tier 2) nằm sau các câu bắt buộc và trước mọi câu thích ứng: "Ở các chuyến trước bạn hay chọn …. Giữ vậy cho chuyến này nhé?" với `Giữ như mọi lần`, `Chuyến này khác` (xóa prior, hỏi như thường; không coi là không thích) và chip nơi hay chọn. Hỏi một lần mỗi phiên; `Bỏ qua` giữ prior ở trạng thái ✎.

**Còn mở.** Chưa có giao diện xin `remember` và cho xem / xóa mẫu; mẫu `avoid` cho nơi chưa có nguồn phiếu (Decision `drop` chưa nối vào); ngưỡng `min_sessions`, `agreement` chờ số liệu khảo sát.
