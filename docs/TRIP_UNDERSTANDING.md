# Trip Understanding

Bước online đầu tiên: hiểu người dùng cần gì cho **chuyến này** trước khi tìm địa điểm. Trang này là bản tham chiếu; nguyên tắc sản phẩm, User Profile và ngân hàng câu hỏi nằm ở `docs/Project_Context.md` §6–12, vị trí trong luồng hệ thống ở `docs/ARCHITECTURE.md` §3.

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

Khi các nguồn mâu thuẫn, thứ tự ưu tiên cố định (`ARCHITECTURE.md` §3.4):

```text
Physical Constraint → User Hard Constraint → Override của chuyến này → Recent Interests → Demonstrated Preferences
```

Ví dụ: profile có `hiking = high`, chuyến này "đi với bố mẹ, mẹ đau gối" → hiking bị tắt **cho chuyến này**, không hỏi lại, không sửa long-term profile.

Kinh nghiệm (lần đầu / đã từng đến) và trạng thái bắt đầu (khám phá / đã lưu / anchor / lịch có sẵn) là hai trục độc lập (`ARCHITECTURE.md` §3.1–3.2). Kinh nghiệm quyết định **mức dẫn dắt**; trạng thái bắt đầu quyết định **luồng bắt đầu từ đâu**. Không trục nào trực tiếp quyết định địa điểm.

## 3. Trip State

```text
Trip State
├── Thông tin cơ bản   dates, duration, companions, base (chỗ ở), mobility
├── Anchor             nơi bắt buộc, booking, sự kiện giờ cố định, check-in/out, giờ rời Đà Lạt; độ ưu tiên
├── Constraint         physical constraint, user hard constraint
├── Sở thích           override của chuyến, session profile, mặc định từ long-term profile
├── Nhịp độ            thong thả | cân bằng | đi nhiều  +  travel tolerance, crowd tolerance
└── Novelty            theo gu quen | thử mới | trộn  (dựa trên Experience History)
```

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

## 4. Luồng xử lý

Luồng lặp theo từng lượt hội thoại, không phải một form tuần tự.

```text
① NẠP PRIOR        Profile (nếu đồng ý) + anchor/link đã có → Trip State nháp
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
| Tách field từ câu tự do, phát hiện từ chủ quan, sinh câu nối tiếp / laddering, diễn đạt theo giọng §12.5 | LLM | Ngôn ngữ tự do, mơ hồ |
| Chọn câu tiếp theo, điều kiện dừng, ghi Trip State, biên dịch Search Input | Rule tất định | Test được, tái lập được, không trôi hành vi khi đổi model |

LLM được đề xuất câu hỏi nối tiếp (nhóm I), nhưng câu trả lời luôn được chuẩn hóa về field của Trip State.

## 5. Chọn câu hỏi tiếp theo

Ba tầng, xét theo thứ tự. Ngân hàng câu hỏi nhóm A–I: `Project_Context.md` §12.2.

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

Feature trong Search Input dùng chung id với feature ontology của corpus (`CORPUS.md` §5), nên việc thử đáp án chạy thẳng trên serving record.

## 7. Điều kiện dừng

Dừng hỏi khi gặp một trong các điều kiện:

- `score` cao nhất còn lại dưới ngưỡng: không câu nào đổi tập ứng viên đáng kể.
- Hết ngân sách lượt: khoảng 3–5 lượt thích ứng sau thẻ mở đầu, trước đề xuất đầu tiên.
- User chọn `Không chắc` / `Bỏ qua` liên tiếp, hoặc trả lời cụt.
- User yêu cầu "xem gợi ý trước" (mixed initiative, được phép bất cứ lúc nào).

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

Output cuối cùng, đầu vào của Place Decision (`ARCHITECTURE.md` §6, `docs/PLACE_DECISION.md`).

```text
Search Input
├── context        dates, duration, base, mobility, companions
├── hard_filters   physical + user hard constraint            → loại ứng viên (fail-closed)
├── anchors        nơi bắt buộc + độ ưu tiên                  → giữ; đánh giá xung quanh chúng
├── soft_weights   sở thích đã làm rõ, theo feature id         → xếp hạng
├── pace           thong thả | cân bằng | đi nhiều + travel/crowd tolerance
├── novelty        quen | mới | trộn; danh sách nơi đã đi      → giảm / loại nơi đã đi khi muốn mới
└── unknowns       field chưa rõ                               → không lọc, xếp hạng trung tính, gắn cờ khi giải thích
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

Không chia persona với kịch bản hỏi riêng. Ngân hàng câu hỏi dùng chung; thứ thay đổi là mức hướng dẫn, dạng câu hỏi và độ sâu (`Project_Context.md` §12.4).

| Tín hiệu | Cách hỏi |
|---|---|
| Lần đầu đến | Hỏi theo cách dùng ("chuyến này để làm gì"), luôn có chip, cho "xem gợi ý trước" sớm |
| Đã từng đến | Hỏi thẳng tiêu chí; ưu tiên nhóm H (đã đi đâu, muốn mới hay quen) |
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
| Câu nhạy cảm (sức khỏe, ngân sách, ăn kiêng) | Giọng trung tính, nói rõ vì sao hỏi, luôn có `Bỏ qua` |

## 12. Ví dụ đầy đủ

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

## 13. Đánh giá

Mô phỏng offline: user giả lập bằng LLM, mỗi user có một Trip State ẩn biết trước. So với baseline form cố định.

| Chỉ số | Đo gì |
|---|---|
| Số lượt trước đề xuất đầu | Chi phí trải nghiệm |
| Field sai / thiếu so với Trip State ẩn | Độ hiểu đúng |
| Tỉ lệ `Không chắc` / `Bỏ qua` | Câu hỏi khó hoặc không đáng hỏi |
| Số lần user sửa bản hiểu nhu cầu | Suy luận sai |
| Constraint violation ở bước Planning | Hậu quả của hiểu sai hoặc bỏ sót |

Chỉ số thật từ pilot đi vào `Project_Context.md` §18–19.
