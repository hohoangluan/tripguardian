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
├── Hậu cần            origin, arrival_mode, inbound, outbound, lodging_booked, lodging (§Hậu cần)
├── Khung giờ          arrive_at, leave_at, day_end
├── Anchor             nơi bắt buộc, booking, sự kiện giờ cố định; độ ưu tiên must | want
├── Constraint         hard: physical constraint + user hard constraint
├── Sở thích           soft: override của chuyến, session profile, mặc định từ long-term profile
├── Nhịp độ            pace thong thả | cân bằng | đi nhiều  +  max_leg_min, crowd_tolerance
├── Novelty            theo gu quen | thử mới | trộn  +  visited (Experience History)
└── meta               start_with, guidance, effort_budget, control, lượt đã hỏi, đã bỏ qua, từ chủ quan còn chờ làm rõ
```

`entry_point` / `exit_point` là nơi Planning neo ngày đầu và ngày cuối. Lưu text + `place_id`, hoặc tọa độ khi điểm được chọn từ ô tìm (`origin`, `lodging`: `Base.lat/lng/province/kind`); geocode phần còn lại xảy ra ở Planning nên `trip` không phụ thuộc `live`. Thiếu → ngày đầu / cuối chỉ bị cắt theo `arrive_at` / `leave_at` và mang cờ "ước lượng ngày đầu / cuối kém chắc" (`docs/PLANNING.md` §Đầu vào).

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

Tầng 1 lấy trước từ phần trò chuyện mở đầu (câu `frame`, §5); phần còn thiếu mới hỏi bằng thẻ ngắn. `base` (chỗ ở) hỏi ở §Hậu cần, để trống được; thiếu thì Planning mang cờ "ước lượng kém chắc".

Tối thiểu tuyệt đối trước đề xuất đầu tiên: `days`, `companions`, `mobility`. Mọi field khác được phép `unknown`.

Tài khoản và User Profile được xin sau khi user đã thấy kết quả đầu, không xin trước (`Project_Context.md` §6.1).

---

## 4. Luồng xử lý

Luồng lặp theo từng lượt hội thoại, không phải một form tuần tự. **Agent quyết định hỏi gì và hỏi bằng gì; người dùng quyết định khi nào sang bước sau (nút Next)**; code chỉ kiểm bằng chứng trước khi ghi Trip State và giữ điều kiện tối thiểu của Next.

```text
① NẠP PRIOR        Mẫu dài hạn đã lưu (nếu có user id, §17) + anchor/link đã có → Trip State nháp
② MỞ ĐẦU           Một câu hỏi mở, không chip: kể về chuyến đi mơ ước sắp tới
③ MỖI LƯỢT         Agent đọc câu user + CURRENT CONTEXT, gọi tool (ghi fact, tra cứu), rồi dừng bằng
                   hỏi một thẻ hoặc trả lời chữ. Câu trả lời chip quay lại agent dưới dạng chữ
④ BẢN HIỂU NHU CẦU User xem và sửa trực tiếp (§8); bấm Next khi `ready` (§6)
⑤ BIÊN DỊCH        Trip State → Search Input (§9)
```

Phân vai:

| Việc | Ai làm | Lý do |
|---|---|---|
| Tách field từ câu tự do (ghi mọi fact mỗi lượt), phát hiện từ chủ quan và tín hiệu nhạy cảm, chọn câu hỏi và lựa chọn, diễn đạt theo giọng §13 | Agent (LLM) | Ngôn ngữ tự do, mơ hồ |
| Phân loại lượt gõ **trước** Agent (lạc đề, phá hoại, câu hỏi số liệu mà bước này không có) và trả câu cố định, không gọi Agent | Clef (`infrastructure/clef.py`, Cloudflare Workers AI `clef-flash`, chạy tuần tự, ~0,5 giây) | Nhanh và rẻ hơn gọi model; lỗi hoặc chậm quá `clef_timeout_s` thì không quyết định gì (fail-open) |
| Kiểm `quote` là lời của user, chuẩn hóa giá trị, tính `ready` / `missing` (§6), ghi Trip State, biên dịch Search Input | Code (`domain/guard.py`, `domain/readiness.py`, `agent/tools.py`) | Test được, tái lập được, không trôi hành vi khi đổi model |

Tool của agent (`agent/tools.py`, function calling gốc trên role Agent, `docs/LLM_PROVIDER.md`):

| Tool | Việc | Code kiểm |
|---|---|---|
| `record_fact(field, op, value, quote, how)` | Ghi một fact | `quote` phải có nguyên văn trong tin nhắn; `values.parse` hợp lệ. Bị từ chối (kể cả feature sai hoặc sai định dạng) thì trả lỗi kèm định dạng đúng lại cho agent để sửa trong cùng lượt. Mong muốn không feature nào diễn đạt được thì **agent chủ động** ghi `field = unmapped` |
| `resolve_relative_date`, `search_places` | Tra cứu chỉ đọc | argument phải là span trong câu user; chỉ đọc catalog |
| `search_features(query)` | Tra feature ontology khớp một mong muốn ("thú cưng" → `animals`), tối đa 5 | chỉ đọc ontology; bỏ qua từ quá chung chung |
| `ask_choice(text, options, multi, reason)` | Thẻ multiple choice 2–6 lựa chọn ≤ 40 ký tự | Dừng lượt |
| `ask_text(text)` | Câu hỏi mở: thẻ có câu hỏi làm tiêu đề và ô gõ, không chip | Dừng lượt |

Vòng lặp (`agent/loop.py`) gọi model tối đa `tool_steps` lần mỗi lượt; một lần gọi có thể trả nhiều tool call. Kết quả mỗi tool quay lại model (message `tool`). Vòng dừng khi một tool dừng thành công, khi một mong muốn bị `unmapped`, khi model trả chữ không kèm tool, hoặc hết `tool_steps`. Agent không có cách kết thúc hội thoại. Khi một lượt có mong muốn `unmapped`, vòng dừng và `say` là câu cố định `UNMAPPED_SAY` (nêu lại mong muốn, nói rõ chưa dùng để lọc địa điểm) thay cho lời model, để không hứa điều tìm kiếm không làm được. Phần chữ model viết trước tool được stream thành `say`; `say` bị thay bằng rỗng nếu nêu số user chưa nói hoặc tên nơi user chưa nhắc (`guard.bad_say`).

Kết quả của lượt thành thẻ cho web (`api/engine.py`): `ask_choice` / `ask_text` → thẻ `custom` (qid `ask:<lượt>`, `ask_text` không có chip; chip hoặc chữ trả lời đi lại qua agent như chữ, `Bỏ qua` / `Không chắc` thành câu "Bỏ qua câu này." / "Mình chưa chắc."); Lượt chỉ trả lời chữ → ô gõ tự do không tiêu đề (`conversation`), không ép câu nào; web chỉ vẽ khung chat cho `frame` / `conversation` trước tin đầu tiên. User không muốn tiếp thì agent trả lời chữ và không hỏi. Lượt không hỏi gì mới (trả lời chữ, mong muốn `unmapped`, agent lỗi) thì thẻ đang mở giữ nguyên thay vì thành ô trống. Phần agent viết trước câu hỏi trong `text` của thẻ (nhận xét, câu trả lời cho user) được tách ra thành chữ trong chat (`guard.split_lead`), thẻ chỉ giữ câu hỏi; lời bị guard từ chối (số liệu user chưa nói, tên nơi chưa nhắc) được thay bằng một câu trung thực `UNSURE_SAY`, không để trống. Agent lỗi (mạng, hết `total_s`): các fact đã ghi giữ nguyên, user nhận câu `FALLBACK_SAY` và ô gõ tự do; `prepass` (từ khóa, link, danh sách nơi) vẫn ghi giá trị ✎ trước khi gọi agent nên không mất thông tin cơ bản.

**Clef trước Agent.** Mỗi lượt gõ (không áp cho `refine`), `Engine._fixed_reply` hỏi Clef hai câu kèm thẻ đang mở: tin nhắn thuộc loại nào (liên quan / lạc đề / phá hoại) và người dùng có hỏi thông tin nằm ngoài những gì bước này có không. Câu hỏi này liệt kê sẵn thông tin đã có và các công cụ Agent tra được (`HAVE`, `TOOLS`, `MISSING` trong `infrastructure/clef.py`, giữ khớp với `agent/tools.py`); hỏi ngoài danh sách (thời tiết, giá, giờ mở cửa…) thì chặn. Lạc đề hoặc phá hoại với xác suất ≥ `clef_reject_min` (0,88: chặn nhầm tốn hơn bỏ sót) thì trả `REJECT_SAY`; câu hỏi số liệu ≥ `clef_data_min` thì trả `NODATA_SAY` (số liệu thật hiện ở bước Lựa chọn). Cả hai đều không gọi Agent, không ghi gì ngoài những gì bộ từ khóa đã đọc, thẻ đang mở giữ nguyên. Một manh mối bộ từ khóa đọc được thì không bị coi là lạc đề; một ngày hoặc tháng chỉ làm khung cho câu hỏi số liệu thì vẫn bị chặn.

**Clef quanh Agent (`Judge` trong `infrastructure/clef.py`).** Ngoài chặn trước Agent, Clef làm các kiểm tra có/không rẻ ở những chỗ trước đây phải tốn một vòng model hoặc dựa vào regex. Mọi kiểm tra đều fail open: Clef không cấu hình, chậm hoặc lỗi thì không chặn gì, Agent chạy như cũ. Ngưỡng nằm ở `config/trip.yaml` (`clef_*_min`); chỉ chặn khi Clef chắc, vì chặn nhầm tốn hơn bỏ sót.
- **Cắt prompt (`clef_plain_min`).** Cùng request với lượt chặn, Clef cho biết tin nhắn chỉ có thông tin chuyến đi (ngày, người, phương tiện…) hay có mong muốn / giới hạn. Chỉ có thông tin chuyến và bộ từ khóa không đọc ra sở thích, không có địa điểm so sánh: system prompt dùng bản không có danh sách FEATURES (hai bản cố định, đều cache được); Agent cần thì gọi `search_features`. Log `clef_lean`.
- **Gợi ý hỏi gì tiếp (`clef_next_min`).** Khi `still_needed` có từ hai mục, cùng request Clef chọn mục tự nhiên nhất để hỏi tiếp; Agent nhận `suggested_next` trong CURRENT CONTEXT như gợi ý, không phải lệnh.
- **`search_features`.** Bộ từ khóa không ra gì thì Clef xếp hạng các feature theo mô tả, có lựa chọn `none` để lối thoát cho mong muốn không feature nào diễn đạt được; chỉ lấy từ `clef_feature_min` (0,5; “cá heo bay” ra animals 0,46 nên bị loại). Lợi ích là độ phủ, không tiết kiệm lượt Agent. Log `clef_features`.
- **`record_fact` (soft, hard, chỉ khi `how` là inferred).** Sau khi câu trích đã khớp tin nhắn, Clef hỏi câu trích có nói điều này không; chắc là không (`clef_verify_min` 0,75: đo thật thì ca không liên quan ra B 0,8–0,9, ca đúng ra B ≤ 0,15; ca ngược nghĩa như “không thích đông” so với “muốn đông” chỉ ra B 0,41 nên Clef không bắt được) thì từ chối như mọi lần từ chối khác để Agent tự sửa. Log `clef_unsupported`.
- **Lời Agent viết.** Cạnh `bad_say` (số, tên địa điểm), Clef hỏi lời có hứa kết quả hoặc nêu sự thật người dùng chưa nói không (`clef_reply_min`); có thì thay bằng `UNSURE_SAY`.
- **`ask_choice` / `ask_text`.** Clef hỏi State đã trả lời câu này chưa (`clef_repeat_min`); rồi thì Agent nhận lỗi và hỏi điều khác. Log `clef_repeat`.

Chưa làm: bỏ qua Agent khi người dùng bấm chip. Chip do Agent viết là nhãn tự do (không có giá trị có cấu trúc) và câu hỏi tiếp theo cũng do Agent sinh, nên bỏ Agent ở đây cần ngân hàng câu hỏi, thứ đã bị bỏ.


Prompt là chuỗi chat: system prompt + ontology bất biến (`agent/prompt.py`; không chứa ngày hôm nay), transcript user/agent của phiên, một message `CURRENT CONTEXT` (Trip State chuẩn hóa kèm nguồn, thẻ đang mở, `keyword_hints` của prepass, `compared_places`, `still_needed`, ngày hôm nay), rồi câu user mới. `CURRENT CONTEXT` là nguồn sự thật khi transcript mâu thuẫn.

**So sánh với một nơi** ("không thích quán giống X", "kiểu X"): khi câu có "giống / kiểu / như / tương tự" và ngay sau đó là tên một nơi tra được trong catalog (`resolve.search`, tên đầy đủ có trong câu), `domain/traits.py` tính trước các **nét nổi bật** của nơi đó: feature đã phục vụ (`Known`) có giá trị khác giá trị phổ biến nhất của các nơi cùng category, xếp theo số người nhắc, tối đa 4 nét, tối đa 2 nơi mỗi câu. Chúng vào `CURRENT CONTEXT` dưới `compared_places`; không cần tool step. Agent viết soft `inferred`: "không thích giống X" → `<feature>=<value>:avoid` cho từng nét, "kiểu X" → `:love`. Guard bỏ soft `inferred` có quote nhắc X mà giá trị không nằm trong nét của X ở chính lượt đó, và cho `say` nhắc tên X (như anchor). Soft chỉ đổi thứ hạng, không loại nơi nào. X không có trong catalog → không có `compared_places`, agent nói không tìm thấy.

**Lượt `refine`** (`Engine.refine`, tool `trip.refine`): mong muốn người dùng gõ ở bước Chọn nơi, harness chuyển sang. Chạy như một lượt chữ, giữ nguyên thẻ đang mở của màn Hiểu chuyến đi (không phát `card`), rồi compile lại; đủ trường bắt buộc thì phát `done {search_input}`.

## 5. Chọn câu hỏi tiếp theo

Agent tự chọn, theo hướng dẫn trong system prompt: trước hết hỏi các mục `still_needed` (mỗi lượt một câu, thứ tự theo mạch người dùng kể), khi đã đủ thì tiếp tục hỏi về điều người dùng muốn từ chuyến đi (mục đích, sở thích, nhịp độ, giới hạn, ngân sách, nơi muốn đến) tới khi họ tự bấm Next; không hỏi lại điều đã biết. Mỗi lượt agent phải ghi mọi fact trong tin nhắn (kể cả điều suy ra và ý nghĩa của lựa chọn vừa bấm) bằng nhiều `record_fact`. `Bỏ qua` / `Không chắc` để trường là `unknown`.

Hai điều code giữ cứng, agent không nới được: (1) Next khóa cho tới khi đủ điều kiện tối thiểu và không còn tín hiệu sức khỏe / thể chất mở (§6, §7); (2) giá trị chỉ vào Trip State qua `record_fact` có bằng chứng.

**Câu mở `frame` là khung chat của web** (`docs/UI_SPEC_USER_WEB.md` Trang 3): người dùng kể, dán link hoặc đính kèm danh sách, nói bao nhiêu lượt cũng được, agent có thể hỏi lại ngay trong chat.

Từ chủ quan ("chill", "đẹp") agent không đoán feature mà hỏi nghĩa. `prepass` đưa các cách hiểu có thể thành `keyword_hints` để agent xác nhận.

### Hậu cần

`domain/logistics.py` giữ các hàm thuần cho điểm vào / ra và giờ giấc: `entry_road` (đèo theo hướng `origin`, `config/trip.yaml` `entry_roads`), `nearest_airport` (`config/airports.yaml`), `route` (IATA hoặc tỉnh của chuyến tới), `pick_transit` (một `Transit` đã chọn → `arrive_at` = giờ đến + `arrival_buffer_min`, `leave_at` = giờ đi − đệm, `entry_point` / `exit_point`). Không còn thẻ hậu cần cố định: agent hỏi bằng thẻ thường và ghi qua `record_fact` các trường `entry_point`, `exit_point`, `arrive_at`, `leave_at`, `day_end`, `base`; `origin`, `arrival_mode`, `inbound`, `outbound`, `lodging_booked`, `lodging` chưa có đường ghi từ agent, giữ `unknown` (vé chuyến vẫn sửa / xóa được các dòng này, `{kind: "edit", target, value | null}`).

`Transit` (`state.py`) chỉ đến từ crawl, không bao giờ do model viết: `{mode, carrier, depart_at, arrive_at (giờ VN "YYYY-MM-DDTHH:MM"), from_point, to_point, price_vnd | null, source, fetched_at}`.

## 6. Next do người dùng bấm

Agent không quyết định khi nào xong. Người dùng bấm Next (`{kind: "show"}`) bất cứ lúc nào view báo `understanding.ready = true`; web hiện nút "Xem gợi ý" ở cột "Đang hợp với bạn", Streamlit tester có nút Next.

`ready` do code tính (`domain/readiness.py`, `config/trip.yaml` `required`): mặc định `days`, `companions`, `mobility` và `when` (một `start_date` hoặc `month`) đã biết (giá trị suy ra từ từ khóa tính là biết, vẫn hiện ✎ để sửa), cộng không còn tín hiệu sức khỏe / thể chất mở (§7). View kèm `missing: [{target, label}]` để UI nói còn thiếu gì. `{kind: "show"}` khi chưa đủ không chuyển bước: engine trả câu `MISSING_SAY` nêu mục còn thiếu và giữ nguyên thẻ đang mở.

"Xem gợi ý" không biến `unknown` của hard constraint thành pass (fail-closed). Sau khi bấm, field còn thiếu giữ `unknown`; hệ thống chuyển sang đề xuất và học tiếp từ phản hồi: compare, critique, lý do bỏ (`Project_Context.md` §8.3–8.4).

## 7. Tín hiệu an toàn

Tín hiệu sức khỏe, cơ thể, ăn kiêng (`knee`, `elderly`, `kids`, `wheelchair`, `pregnant`, `motion_sick`, `height`, `vegetarian`) vào Trip State dưới dạng `signal`; mỗi signal chưa được xử lý là "mở". Khi còn signal mở: `ready` là false (mục `signal` trong `missing`), `{kind: "show"}` bị từ chối, `compile_search_input` ném `UnhandledSignal` (`domain/compile.py`). Bộ từ khóa (`prepass`) ghi `signal` và hard filter tương ứng ("đau gối", "không đi bộ xa") không phụ thuộc agent; một hard filter phủ tín hiệu thì signal được coi là đã xử lý. Không có đường code nào nới ràng buộc thể chất.

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
- Sở thích suy từ một nơi người dùng so sánh ghi nguồn `place:<id>` trong evidence; vé gộp chúng thành một dòng "Tránh: ồn, đông (giống X)", xóa dòng đó là xóa cả nhóm.
- "Đang hợp với bạn" = số nơi qua giới hạn cứng và hợp gu hiện tại (`understanding.matching`). Chip có `drafts` mang `effect` (số nơi tăng / giảm nếu chỉ chọn chip đó, `chip_effects`); thẻ do agent viết không có `drafts` nên không có `effect`.
- Sửa ở đây là override **của chuyến này**, không tự ghi vào long-term profile.
- Mục "Chưa rõ" hiển thị công khai, không giấu.

## 9. Search Input

Output cuối cùng, đầu vào của Place Decision (`docs/PLACE_DECISION.md` §2.1). Kiểu: `trip.SearchInput`. Mỗi `hard_filter` mang `unknown_policy` (`exclude` | `flag`) để Place Decision biết phải fail-closed tới mức nào.

```text
Search Input
├── context        start_date | month, days, base, entry_point, exit_point, mobility, companions,
│                  people, arrive_at, leave_at, day_end, budget_vnd, experience,
│                  origin, arrival_mode, inbound, outbound, lodging_booked, lodging
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

Không chia persona với kịch bản hỏi riêng. Cùng một agent cho mọi người dùng; thứ thay đổi là ba tham số `guidance`, `effort_budget`, `control` (`Project_Context.md` §3.3); căn cứ nghiên cứu ở `Project_Context.md` §12.1.

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
| Hỏi nhiều → mệt | Agent hỏi một câu mỗi lượt, chỉ điều đổi kết quả; không câu nào bắt buộc |
| Hỏi lại cái đã biết | Xác nhận 1 chạm thay vì hỏi mở |
| User không biết trả lời | Hỏi cách dùng, không hỏi thuộc tính; luôn có chip gợi ý + nhập tự do |
| `Không chắc` | Hợp lệ; ghi `unknown`, học tiếp qua đề xuất |
| Không hiểu vì sao bị hỏi | Nói lý do hoặc tác động ("để tránh chỗ leo dốc", "còn 38 → 14 nơi") |
| Hệ thống đoán sai | Bản hiểu nhu cầu đánh dấu ✎ phần suy luận / profile; sửa tại chỗ |
| Hệ thống nhớ gu từ các chuyến trước | Giá trị nhớ vào Trip State như mặc định ✎ để agent không hỏi lại; chỉ nhớ khi user đồng ý; xóa được (§17) |
| Câu nhạy cảm (sức khỏe, ngân sách, ăn kiêng) | Giọng trung tính, nói rõ vì sao hỏi, luôn có `Bỏ qua` |

## 12. Nguyên tắc đặt câu hỏi

Không có ngân hàng câu hỏi: agent viết câu hỏi và lựa chọn mỗi lượt (`agent/prompt.py`). Nguyên tắc căn cứ nghiên cứu ở `Project_Context.md` §12.1 mà prompt áp: hỏi cách dùng ("chuyến này để làm gì"), không hỏi thuộc tính; chỉ hỏi điều đổi kết quả; một câu mỗi lượt; luôn có thể bỏ qua; không hỏi lại điều đã biết (từ user, anchor hay profile); từ chủ quan thì hỏi nghĩa; câu nhạy cảm nói rõ vì sao hỏi. Lựa chọn của thẻ chỉ là dữ liệu trả lại agent, không ghi thẳng vào Trip State.

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

User Web gọi Trip qua harness bằng journey chung (`docs/AGENT_HARNESS.md`). Public API xuất `Tools`, `create_engine`, `SearchInput`; `tools.py` giữ snapshot do Trip sở hữu. `skills.yaml` khai báo quyền Trip; `agent/` chạy vòng tool (§4). Heuristic trước Agent và điều kiện bypass: `docs/AGENT_HARNESS.md` §5.

API độc lập: `python -m trip serve [--port 8766]` bind `127.0.0.1`. Cần `AGENT_*` trong `.env` (`docs/LLM_PROVIDER.md`) trỏ tới endpoint nhận function calling; thiếu hoặc lỗi thì lượt chữ chỉ có phần `prepass` ghi (§4).

```
POST   /api/trip/sessions          {experience?, start_with?, user_id?, remember?}  → phiên mới + thẻ mở đầu
DELETE /api/trip/profile/<user_id>  → {forgotten}  xóa mẫu đã lưu của user
GET    /api/trip/sessions/<id>
POST   /api/trip/sessions/<id>/turn  SSE: say(delta|replace) · view · done · error
GET    /api/trip/places?q=<tên>    tra địa điểm cho anchor / nơi đã lưu (chỉ đọc serving index)
```

Qua harness, `Tools.apply` nhận thêm operation `refine {text}` (chỉ harness gọi, sau lượt chat ở Chọn nơi): say · state · done, không có card.

Module:

```
src/trip/
  domain/
    state.py        TripState (mỗi field có value, source, confidence, status, evidence), SearchInput
    card.py         thẻ trả lời: Question, Chip, thẻ mở đầu, ô gõ tự do
    guard.py        record_fact (kiểm bằng chứng), bad_say, drop_questions
    values.py       chuẩn hóa giá trị về field của Trip State
    prepass.py      rule tất định đọc câu người dùng (từ khóa, link) trước khi gọi model
    resolve.py      tên người dùng nêu → place_id, hoặc unmapped
    traits.py       nét nổi bật của nơi người dùng so sánh ("giống X"), chỉ từ catalog
    dates.py        ngày tương đối → ngày
    logistics.py    điểm vào / ra, chuyến tới, giờ giấc (§Hậu cần)
    coverage.py     hard filter có đủ bằng chứng trong corpus không
    patterns.py     phiếu bầu, phát hiện mẫu, nạp prior vào Trip State (§17)
    readiness.py    điều kiện tối thiểu của Next: `ready`, `missing` (§6)
    understanding.py bản hiểu nhu cầu (§8)
    compile.py      Trip State → Search Input (§9)
  agent/            loop.py (vòng gọi model + tool), tools.py, prompt.py
  api/              engine.py (một lượt, giao dịch phiên), server.py (HTTP + SSE, cổng 8766), tools.py (adapter harness)
  infrastructure/   catalog.py, sessions.py, profile.py (§17), settings.py (config/trip.yaml)
```

Test: `python -m pytest -q tests/trip`; model được thay bằng `ScriptedChat` (`tests/trip/trip_fixtures.py`), test không gọi mạng.


## 15. Ví dụ đầy đủ

**Có sẵn:** profile `cà phê = high`, `hiking = high`, Behavioral Defaults "dậy sớm"; Experience History: đã đi Hồ Xuân Hương, Langbiang.

**User gõ:** "Tháng 12 đi Đà Lạt 3 ngày với bố mẹ, muốn chill" + 2 link TikTok.

```text
③ Trích xuất   duration = 3 · tháng 12 · companions = bố mẹ · "chill" (chủ quan) · 2 anchor
④ Xung đột     bố mẹ → tắt hiking cho chuyến này (không hỏi)
               đã đi Langbiang → novelty nghiêng về mới (đưa vào bản hiểu nhu cầu để xác nhận)
⑤ Lỗ hổng      agent thấy: tín hiệu người lớn tuổi chưa xử lý, ngày cụ thể, base, phương tiện, nghĩa của "chill"
               nhịp độ không đáng hỏi vì "chill" + bố mẹ đã suy ra thong thả

Lượt 1 (thẻ do agent viết)  Ngày cụ thể? · Ở khu nào? · Đi lại bằng gì?
Lượt 2             "Để tránh chỗ phải leo dốc: bố mẹ có ngại đi bộ xa hoặc bậc thang không?"
                   [Có · Không · Bỏ qua]
Lượt 3             "'Chill' với bạn là: ít người · có view · ngồi lâu được · nhạc nhẹ?"
→ `ready` bật khi đủ điều kiện tối thiểu; agent vẫn hỏi tiếp về gu, người dùng bấm Next khi muốn
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

**Điều kiện chạy.** Cần `patterns.enabled`, `user_id` trên phiên (chuỗi mờ 8–64 ký tự `A-Za-z0-9_-`; qua User Web là id tài khoản, harness lấy từ phiên đăng nhập, `docs/ACCOUNTS.md`) và `remember = true` để **ghi**. Có `user_id` mà không `remember` thì chỉ đọc mẫu đã có. Xóa: `DELETE /api/harness/profile/<user_id>` (User Web), `DELETE /api/trip/profile/<user_id>` (API độc lập) hoặc `Engine.forget`.

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

**Prior trong hội thoại.** Không có thẻ xác nhận riêng: giá trị seed mang `source = profile` trong `CURRENT CONTEXT`, agent coi là mặc định và để lời user ghi đè. Mẫu về nơi (`meta.prior` giữ khóa `place:<id>`) hiện chưa được đưa cho agent.

**Còn mở.** Chưa có giao diện xin `remember` và cho xem / xóa mẫu; mẫu `avoid` cho nơi chưa có nguồn phiếu (Decision `drop` chưa nối vào); ngưỡng `min_sessions`, `agreement` chờ số liệu khảo sát.
