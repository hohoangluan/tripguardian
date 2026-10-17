# Place Decision

Bước online thứ hai: từ **Search Input** của Trip Understanding và serving index của Place Intelligence, giúp người dùng chọn ra **tập địa điểm đã xác nhận** trước khi xếp lịch. Vị trí trong luồng: `docs/ARCHITECTURE.md` §3. Đầu vào: `docs/TRIP_UNDERSTANDING.md` §9. Nguyên tắc sản phẩm: `docs/Project_Context.md` §9, §14.

Code: `src/decision/`. CLI và API ở §18.

Factory nhận retrieval cùng binding. Context Agent bổ sung serving evidence tối đa ba nơi,
hai feature mỗi nơi và một quote mỗi feature (tối đa 500 ký tự), giữ status/release và
observation/source/time. Thiếu evidence giữ unknown; semantic không trở thành fact.


## 1. Place Decision là gì

```text
SEARCH INPUT ──┐
(Trip Under-   │
 standing §9)  ├──► RESOLVE ──► TRUY XUẤT ──► SÀNG LỌC ──► HỢP BỐI ──► XẾP HẠNG ──► SHORTLIST ──► NGƯỜI DÙNG ──► KHẢ THI ──► ĐỊA ĐIỂM
               │    anchor      ứng viên      constraint    CẢNH        + ĐA DẠNG    + SO SÁNH     TUYỂN CHỌN     TỔ HỢP      ĐÃ XÁC NHẬN
SERVING INDEX ─┘                              (fail-closed) (thô)                                                               → Planning
(Place Intelligence)
```

- Mục tiêu là **một tập quyết định nhỏ, hữu ích**, không phải danh sách dài. Hệ thống hỗ trợ chọn, không chọn thay.
- Constraint trước sở thích: profile và sở thích chỉ xếp hạng ứng viên đã qua sàng lọc (`docs/Project_Context.md` §14.2, §14.8).
- Không bịa: địa điểm thiếu bằng chứng cho một khía cạnh thì khía cạnh đó là `unknown`, không phải "không có".
- Chỉ đọc: Place Decision đọc serving record, không ghi Place Intelligence. Nó chỉ ghi Session Profile (từ thao tác tuyển chọn) và danh sách đã xác nhận.
- Chỉ dùng độ hợp không gian **thô**. Thời gian di chuyển thực tế, thời tiết, điều kiện tạm thời thuộc Live Context của bước Planning (`docs/PLANNING.md` §Live Context).

## 2. Đầu vào

### 2.1 Search Input

Mỗi field của Search Input (`TRIP_UNDERSTANDING.md` §9) được dùng ở một bước cố định:

| Field | Dùng ở | Cách dùng |
|---|---|---|
| `context` (dates, duration, base, mobility, companions) | Sàng lọc, Hợp bối cảnh, Khả thi | Ngày → giờ mở cửa trong chuyến; base + mobility → bán kính thô; companions → suitability |
| `hard_filters` | Sàng lọc | Loại ứng viên, fail-closed (§6) |
| `anchors` | Resolve, Hợp bối cảnh, Khả thi | Luôn giữ; làm tâm đánh giá không gian; chiếm thời gian cố định |
| `soft_weights` | Xếp hạng | Trọng số theo feature id |
| `pace` + travel / crowd tolerance | Hợp bối cảnh, Đa dạng, Khả thi | Bán kính chấp nhận, cỡ shortlist, số nơi mỗi ngày |
| `novelty` + danh sách đã đi | Xếp hạng | Giảm hoặc loại nơi đã đi |
| `wishes` (món, kiểu nơi, giống X), `vibes` (phong cách user chọn, `TRIP_UNDERSTANDING.md` §18) | Xếp hạng | Thành phần `wish` (§8); không loại nơi nào |
| `liked_groups` | Xếp hạng | `wish` mức thấp cho nơi thuộc nhóm đó; không ẩn nhóm khác |
| `context.purpose` | Xếp hạng | `wish` mức thấp nhất theo map trong config; là suy luận (✎ trên thẻ) |
| `unknowns` | Mọi bước | Không lọc, trọng số 0, gắn cờ khi giải thích |

Search Input có thể đổi giữa chừng (user sửa bản hiểu nhu cầu, trả lời thêm, Session Profile thay đổi). Khi đổi, luồng chạy lại từ bước sớm nhất bị ảnh hưởng (§14); lựa chọn đã khóa được giữ.

### 2.2 Serving record

Place Decision chỉ đọc serving record (`docs/CORPUS.md` §Bản ghi địa điểm), không duyệt đồ thị bằng chứng:

```text
Identity      id, POI | ZONE, category, vị trí / hình học, cụm / khu vực
Operation     giờ (Fact), giá (Fact), đặt chỗ, thời gian tham quan (Estimate: min / typical / long)
Experience    feature id + confidence
Environment   trong nhà / ngoài trời, độ đông theo bối cảnh (Signal), nhạy thời tiết
Effort        đi bộ, dốc, khó tiếp cận
Suitability   cặp đôi, gia đình, người lớn tuổi, …
Provenance    trạng thái theo khía cạnh, coverage theo khía cạnh, confidence 4 thành phần, tham chiếu bằng chứng
```

Chỉ record có trạng thái `VERIFIED`, `UNCERTAIN`, `OUTDATED` được dùng (`docs/CORPUS.md` §Trạng thái). `NEEDS_REVIEW` và `DISABLED` không bao giờ xuất hiện.

Place Decision đọc serving record qua snapshot (`corpus.snapshot`, `docs/CORPUS.md` §Place Decision dùng corpus thế nào). Bước ③–⑤ tính cho mọi nơi một lượt bằng bảng (`decision.frame`: `screen_table`, `fit_table`, `score_table`); thẻ, so sánh và `why_not` dựng bằng các hàm theo từng nơi (`screen.py`, `fit.py`, `rank.py`), vẫn là định nghĩa của các con số. Hai bên được giữ khớp bằng oracle test `tests/decision/test_equivalence.py` (`tests/decision/reference.py` là bản `run` theo từng nơi). Chỗ ở (`stay`) có trong snapshot cho Planning, nhưng không bao giờ là ứng viên của Decision, kể cả khi user chọn hay đặt làm neo.

## 3. Luồng xử lý

```text
①  RESOLVE          anchor + địa điểm đã lưu / nhập tay → entity (§4)
②  TRUY XUẤT        tập ứng viên từ serving index + anchor + nơi user thêm (§5)
③  SÀNG LỌC         physical → user hard; ghi lý do loại (§6)
④  HỢP BỐI CẢNH     vị trí, cụm, đường vào, độ đông theo bối cảnh, anchor (§7)
⑤  XẾP HẠNG         điểm = bối cảnh + sở thích + tính mới + kinh nghiệm − bất định (§8)
⑥  ĐA DẠNG          gom nơi gần trùng thành nhóm; cắt shortlist theo cỡ (§9)
⑦  SO SÁNH          trong mỗi nhóm: A hơn ở đâu, B hơn ở đâu, hy sinh gì (§10)
⑧  TUYỂN CHỌN       user thêm / bỏ / khóa / so sánh → Session Profile → xếp hạng lại (§12)
⑨  KHẢ THI          đánh giá tổ hợp đã chọn, trực tiếp theo từng thao tác (§13)
⑩  XÁC NHẬN         danh sách đã xác nhận + pool dự phòng → Planning (§15)
```

⑧ ↔ ⑨ là vòng lặp chính. Planning không xếp được thì quay về ⑧ (`docs/ARCHITECTURE.md` §6).

Phân vai:

| Việc | Ai làm | Lý do |
|---|---|---|
| Resolve, truy xuất, sàng lọc, chấm điểm, đa dạng, khả thi | Rule tất định | Test được, tái lập được; AI không tự xác nhận khả thi (`docs/Project_Context.md` §14.7) |
| Chọn cặp so sánh, tính khác biệt giữa hai nơi | Rule tất định | Chỉ so trên khía cạnh có bằng chứng |
| Diễn đạt "vì sao phù hợp", "đánh đổi", lý do bỏ thành câu | LLM | Chỉ diễn đạt lại field của serving record và kết quả rule; không thêm nhận định mới |
| Hiểu lý do bỏ / critique nhập tự do ("xa quá", "muốn chỗ ít người hơn") | LLM | Chuẩn hóa về field của Search Input / Session Profile |

## 4. Resolve địa điểm của người dùng

Anchor, địa điểm đã lưu, địa điểm nhập tay đi qua cùng bộ matcher của corpus (`docs/CORPUS.md` §3 Resolve). Input của người dùng không bao giờ thành bằng chứng về địa điểm.

| Kết quả | Xử lý tiếp |
|---|---|
| Match chính xác | Địa điểm đã xác minh; dùng serving record |
| Match mơ hồ | Hỏi user chọn giữa các định danh (tên, khu vực, ảnh); không đoán |
| Match chắc với nhà cung cấp bản đồ nhưng chưa có trong registry | Dùng định danh + vị trí + giờ; các khía cạnh khác `unknown`; xếp hàng làm giàu dữ liệu |
| Không match | Địa điểm chưa xác minh; vẫn giữ nếu user muốn, mọi khía cạnh `unknown` |

Anchor không bị sàng lọc loại âm thầm. Nếu anchor vi phạm constraint, hệ thống cảnh báo và hỏi (§6.3). Input của user không bao giờ thành bằng chứng về địa điểm.

## 5. Truy xuất ứng viên

```text
nguồn ứng viên
├── khám phá từ serving index   theo feature id trong soft_weights, category, cụm quanh base / anchor
├── địa điểm đã lưu             sau resolve
├── nơi bắt buộc đến            sau resolve, luôn vào tập
├── lịch trình có sẵn           các nơi trong lịch, sau resolve
└── tìm kiếm của user           tìm tên / feature trong phiên
```

- Luồng bắt đầu theo **trạng thái bắt đầu** (`docs/TRIP_UNDERSTANDING.md` §2): khám phá → truy xuất rộng; đã lưu → tập = danh sách đã lưu, truy xuất thêm chỉ để có phương án thay thế; lịch có sẵn → đi thẳng tới ⑨ để phát hiện xung đột.
- Truy xuất rộng hơn shortlist nhiều lần để sàng lọc và đa dạng còn đủ chỗ chọn; cỡ nằm trong config.
- Coverage giới hạn vai trò: địa điểm `experience = NONE` chỉ được dùng làm chỗ ăn, anchor, hoặc dự phòng, không được gợi ý như một trải nghiệm (`docs/CORPUS.md` §Ba loại output).
- Không có chỗ ở trong ứng viên: chỗ ở không nằm trong Place Intelligence, Planning tra live theo request (`docs/PLANNING.md` §Chỗ ở (crawl live)).

## 6. Sàng lọc constraint

### 6.1 Thứ tự

```text
ứng viên
    ↓
physical constraint?   vi phạm → loại (không nới được)
    ↓
user hard constraint?  vi phạm → loại · anchor / nơi user khóa → giữ + hỏi nới (§6.3)
    ↓
unknown bằng chứng?    → không coi là an toàn (§6.2)
    ↓
qua sàng lọc
```

| Loại | Ví dụ ở bước này | Nguồn kiểm tra |
|---|---|---|
| Physical | `DISABLED` / đóng cửa hẳn; đóng cửa mọi ngày của chuyến; cấm loại phương tiện của user | Operation (Fact) × `context.dates`, `mobility` |
| User hard | dốc / bậc; đi bộ ≤ N phút; ngân sách trần; ăn kiêng; không hợp trẻ nhỏ | Effort, Suitability, Operation × `hard_filters` |

Khoảng cách và thời gian di chuyển chưa phải constraint ở đây; chúng thuộc Hợp bối cảnh (§7) và Khả thi (§13).

### 6.2 Ba giá trị của một kiểm tra

`requirements.hard_result` kiểm tra applicability theo `SearchInput.activities` rồi bằng chứng. Yêu cầu không liên quan trả `not_applicable` và không loại ứng viên; dietary chỉ áp dụng khi eating. Với yêu cầu có áp dụng, kết quả là `pass | fail | unknown`:

| Kết quả | Ứng viên thường | Anchor / nơi user khóa |
|---|---|---|
| `pass` | Tiếp tục | Tiếp tục |
| `fail` | Loại, ghi lý do | Giữ, cảnh báo, hỏi nới (§6.3) |
| `unknown` (thiếu bằng chứng effort / suitability / giá) | Không vào danh sách chính; hiển thị ở mục "chưa xác minh được" nếu user muốn xem | Giữ, gắn cờ "chưa xác minh được [constraint]" |
| Giá trị `UNCERTAIN` (bằng chứng xung đột) | Như `unknown` với constraint an toàn / tiếp cận; như `pass` kèm cảnh báo với constraint khác | Giữ + cảnh báo |

Đây là fail-closed: thiếu bằng chứng cho hard constraint thì không được nói địa điểm là an toàn. Field trong `unknowns` của Search Input không tạo kiểm tra nào.

**Bộ lọc cứng từ người đi cùng và xe.** Chip người đi cùng ghi kèm hard filter: `fit.baby`, `fit.parents`, `fit.pregnant`, `fit.wheelchair` `!= bad` (verdict của `details.fit[x]`, tên có tiền tố `fit.`), `pets != not_allowed` khi có thú cưng. Đi `car` với `people ≥ coach_min_people` (`config/trip.yaml`) thì Trip thêm `coach_access != no`, chính sách unknown mặc định `exclude`. Cả ba chạy qua `hard_result` như mọi feature; `fit.*` luôn là kiểm tra an toàn nên giá trị `UNCERTAIN` không bao giờ `pass`.

`eq` cần giá trị VERIFIED/OUTDATED phù hợp và distribution không mâu thuẫn; `ne` dùng cùng semantics cho Decision và Planning. Dietary thiếu evidence không thành `not_applicable`. Soft ranking loại yêu cầu không liên quan khỏi cả tử số, mẫu số và uncertainty. Wine preference đọc offering có evidence riêng, không suy việc user bắt buộc uống; coffee-only không bị wine requirement lọc. Contract ý định ở `docs/TRIP_UNDERSTANDING.md` §9.

### 6.3 Xung đột với địa điểm user chọn

```text
anchor / nơi khóa vi phạm
    ├─ physical   → không vào danh sách đã xác nhận; giữ ở wishlist; nói rõ lý do
    │               (ví dụ: đóng cửa mọi ngày 12–14/12)
    ├─ user hard  → hỏi có nới không, kèm cái giá cụ thể
    │               ("Nơi này có ~120 bậc thang. Giữ nó nghĩa là bỏ điều kiện tránh bậc cho riêng nơi này?")
    └─ unknown    → giữ, cảnh báo cần tự kiểm tra trước chuyến
```

Nới là quyết định của user, chỉ áp cho địa điểm đó trong chuyến này, không sửa `hard_filters` chung.

### 6.4 Lưu lý do loại

Mỗi ứng viên bị loại giữ `reason` (constraint, giá trị, bằng chứng). Dùng để:

- trả lời "vì sao không có nơi X?";
- dựng pool dự phòng cho Planning (`docs/PLANNING.md` ⓗ): ứng viên bị loại vì lý do theo ngữ cảnh (ví dụ ngoài trời) vẫn có thể là phương án thay thế trong điều kiện khác;
- đo chất lượng (§17).

## 7. Độ hợp bối cảnh

Đánh giá thô, rẻ, trước khi biết shortlist. Không gọi route service.

| Tín hiệu | Tính từ | Ví dụ |
|---|---|---|
| Khoảng cách tương đối | Vị trí × base / anchor, theo đường chim bay hoặc theo cụm | Xa mọi anchor và base → điểm thấp khi travel tolerance thấp |
| Khu vực / cụm | Cụm của Identity | Cùng cụm với anchor → cộng điểm |
| Đường vào | Effort, mobility | Đường đất dốc + xe máy số → cảnh báo |
| Độ đông dự kiến | Signal độ đông theo bối cảnh × ngày trong tuần / buổi của chuyến | `crowd × weekend × morning` cao + user muốn ít người → trừ điểm, gợi ý buổi khác |
| Nhạy mùa | Environment × tháng của chuyến | Ngoài trời vào mùa mưa → cờ "cần dự phòng" (không dùng dự báo thời tiết thật) |
| Anchor | Anchor có giờ cố định | Nơi xa anchor giờ cố định trong cùng ngày → trừ điểm |
| Hợp người đi cùng | `details.fit` của từng x trong chuyến: `companions`, x có hard filter `fit.<x>` (bà bầu, xe lăn), `large_group` khi `people ≥ coach_min_people`; cùng feature x cần | `good` đã xác minh cộng `good_bonus`; `bad` đã xác minh trừ `bad_penalty` và gắn cờ `fit_bad` kèm lý do; feature cần (trẻ / em bé: `kids_play_area`, `stroller_access`; bố mẹ: `rest_benches`, `toilet_available`) cộng `feature_bonus`. Giá trị chưa xác minh hoặc thiếu dữ liệu không đổi điểm (`details_fit` trong `config/decision.yaml`) |

Output: `context_fit` (điểm) + danh sách cờ. Ứng viên có `context_fit` dưới ngưỡng không vào shortlist nhưng vẫn giữ trong pool. Bán kính và ngưỡng theo `pace` và travel tolerance, trong config.

## 8. Xếp hạng

```text
score = w_ctx   · context_fit
      + w_pref  · preference_fit      Σ soft_weight(f) · có_feature(f) · confidence(f)
      + w_rec   · recent_interest     Recent Interests của profile (khi user đồng ý)
      + w_nov   · novelty             theo novelty + Experience History + Exploration Gap
      + w_exp   · experience_fit      visited rỗng: nơi đặc trưng được cộng; có visited: nơi khác visited được cộng
      + w_pop   · popularity          chỉ là một tín hiệu, trọng số nhỏ
      + w_wish  · wish                1 − Π(1 − a·strength) trên các mong muốn áp cho nơi đó (decision.wishes)
      − w_unc   · uncertainty         thiếu coverage / UNCERTAIN / OUTDATED ở khía cạnh quan trọng với user
```

Quy tắc:

- Feature id dùng chung với ontology của corpus (`docs/CORPUS.md` §Bản ghi địa điểm), nên `preference_fit` là phép khớp trực tiếp.
- Địa điểm **không có bằng chứng** cho một feature → đóng góp 0, không âm. Phần thiếu đi vào `uncertainty`, chỉ tính cho feature user quan tâm.
- Feature `off` cho chuyến này (ví dụ `hiking = off`) → không cộng; không loại trừ khi đó không phải hard filter.
- `novelty = high` → nơi trong Experience History bị giảm mạnh hoặc loại khỏi khám phá (không loại nếu user đưa vào anchor). Đã đến ≠ đã thích (`Project_Context.md` §11).
- Thứ tự ưu tiên khi hai nguồn trọng số mâu thuẫn giữ đúng `TRIP_UNDERSTANDING.md` §2.
- `wish` chỉ nâng, gom mọi mong muốn của Trip (`decision/wishes.py`): món (`place_ids` theo thứ tự, 1 → 0,5, mọi nơi có ghi món đó: quán cà phê có cà phê muối cũng được cộng), kiểu nơi (1), phong cách ảnh (1 → 0,5 theo hạng; độ giống ảnh không phải bằng chứng), giống X (`corpus.serving.similarity` ≥ `like_min`, trừ chính X; phần "nhưng" đã là `soft_weights`), `liked_groups` (cả nhóm, mức thấp), `purpose` (theo map, mức thấp nhất). Khớp nhiều mong muốn thì cao hơn; không khớp = 0, không âm, không loại; sàng lọc chạy trước; nơi chưa có bản ghi không được cộng. Mỗi ảnh user gửi và mỗi nơi tham chiếu là một mong muốn riêng. Mức `a`, `like_min`, map `purpose` ở `config/decision.yaml` `wish`. Danh sách mỗi nhóm vẫn đủ mọi nơi qua sàng lọc; không lọc theo ngưỡng điểm.
- Trọng số `w_*` nằm trong config, có version; mỗi điểm lưu kèm từng thành phần để giải thích và debug.
- **Né đông.** Khi user né đông (`profile.crowd_tolerance` hoặc `pace.crowd_tolerance` = `avoid`), mỗi tab xếp các nơi Google ghi là đông (≥ `crowd_busy_pct` ở khung giờ nào đó của loại ngày trong chuyến, hoặc cả hai loại ngày khi chưa biết ngày) sau mọi nơi còn lại, bất kể điểm; nơi không có popular times không bị coi là đông (`frame.busy_mask`).
- **Chế độ ăn** (`decision/diet.py`, chỉ tab `meal`, `snack`). Có yêu cầu chay (hard hoặc soft `vegetarian_options` / `vegan_options` = yes) hay ghi chú "dị ứng hải sản" ở `unmapped` (Trip không có feature dị ứng, chỉ giữ ghi chú): tab xếp theo bậc, rồi mới đến điểm. Bậc 0: nơi tự nhận là quán chay (tên hoặc category Google có "chay"). Bậc 1: không có gì trái chế độ (chay: đã verify `vegetarian_options` = yes). Bậc 2: chưa verify được món chay (chỉ xảy ra với yêu cầu soft; hard thì nơi này vào mục chưa xác minh). Bậc 3: tên hoặc category tự nhận là nơi nướng / thịt / hải sản… (chay) hoặc hải sản (dị ứng). Bậc ≥ 2 không bao giờ được "Hợp nhất"; bậc 3 không vào shortlist và thẻ có ghi chú; bậc 3 vẫn nằm trong tab (không có bằng chứng "chỉ có món mặn" ngoài tự nhận, nên không loại cứng). Thiếu bằng chứng là `unknown`, không bao giờ được xếp như "khớp".

## 9. Đa dạng và cỡ shortlist

### 9.1 Gom nơi gần trùng

Hai ứng viên là **gần trùng** khi cùng category, trùng phần lớn feature có bằng chứng, và vai trò trong chuyến như nhau (ví dụ hai quán cà phê view đồi, cùng kiểu ngồi lâu). Nơi gần trùng được gom thành một **nhóm**:

```text
Nhóm "cà phê view đồi, yên tĩnh"
├── đại diện  A   điểm cao nhất
└── thay thế  B, C   hiển thị khi mở nhóm hoặc so sánh
```

Chọn tiếp theo kiểu MMR (`corpus.serving.mmr`): mỗi lần chọn ứng viên có `score` cao nhưng khác nhất với các nơi đã chọn, để shortlist gồm các lựa chọn thực sự khác nhau.

### 9.2 Cỡ shortlist

```text
số chỗ cần ≈ số ngày khả dụng × số nơi mỗi ngày(pace) − số anchor
cỡ shortlist ≈ số chỗ cần × hệ số dư
```

| Pace | Nơi mỗi ngày (mặc định config) |
|---|---|
| thong thả | ít, ở lâu mỗi nơi |
| cân bằng | trung bình |
| đi nhiều | nhiều, vẫn không vi phạm physical |

Cỡ shortlist là số nơi MMR chọn ở mỗi vai trò; nó quyết định mỗi tab có bao nhiêu nơi mang `top: true` (web hiện nhãn "Hợp nhất", §9.3). Danh sách không dừng ở đó: mỗi tab có mọi nơi qua sàng lọc, xếp theo `score`. Nơi gần trùng vẫn có `alternatives` nhưng cũng nằm trong danh sách. View chỉ mang **trang đang hiện** của mỗi tab (§9.4) kèm `total` của tab. Ngưỡng "bỏ nhiều quá, nghĩ lại" (`first_shortlist`) = số card `top` + anchor của lần dựng đầu, không phải tổng số nơi.

### 9.3 Tab

Danh sách nằm trong các tab theo loại nơi (`config/decision.yaml` `tabs`: tab → nhóm category của corpus; nhóm không có trong tab nào → `sights`): Ăn uống, Ăn vặt và tráng miệng, Cà phê, Thiên nhiên và ngắm cảnh, Vườn và trang trại, Cắm trại, Điểm tham quan, Di tích / chùa / bảo tàng, Vui chơi, Bar và về đêm, Spa, Chợ và mua sắm (`frame.tabs`, `diversify.tab`). Tab không có nơi nào thì không hiện. Anchor luôn đứng đầu, tách riêng. `display_groups` (4 nhóm thô) chỉ dùng cho mong muốn `liked_groups` / `purpose` (§8 `wish`), không phải tab.

**Nơi quá xa bị ẩn** (fail-closed, không có đường nới): nơi có thời gian di chuyển từ tâm gần nhất trong các tâm của `fit` (chỗ ở / base nếu đã có, không thì tâm thành phố mà `fit.radius` đang dùng, cộng các nơi user đã đặt làm anchor; nơi gần một anchor thì với tới được) vượt `max_travel_min` (`config/decision.yaml`, mặc định 90 phút; công thức `geo.minutes`) không nằm trong tab nào, shortlist hay mục chưa xác minh. Ngoại lệ: nơi user đã chọn hoặc đặt làm anchor không bao giờ bị ẩn; nơi không có toạ độ không bị coi là xa (không có bằng chứng thì không loại). `why-not` của nơi bị ẩn nói rõ "Xa so với <tâm> (≈N phút, quá giới hạn 90 phút)" với N tính từ toạ độ thật. Số "N nơi hợp với chuyến" của Web là tổng `total` các tab nên đã không đếm nơi bị ẩn.

Mỗi tab liệt kê **mọi** nơi còn lại qua sàng lọc của nó (kể cả nơi có `context_fit` dưới `min_context_fit`; ngưỡng đó chỉ áp cho pool của shortlist), kể cả nơi user đã chọn, xếp theo `score` (sau bậc chế độ ăn và quy tắc né đông ở §8; ngoài hai trường hợp đó không có tiêu chí nào khác). "Hợp nhất" (`top`) đánh dấu các nơi chưa chọn đứng đầu tab, đúng bằng số nơi MMR (§9.2) lấy từ tab đó.

### 9.4 Trang, tìm kiếm và lọc lại

Mỗi tab là thứ hạng của nó chia thành trang `page_size` nơi; user chọn trang (`State.page[tab]`, 0 = đầu; lưu trong phiên, không vào lịch sử hoàn tác). Ids trên màn nằm ở `State.shown[tab]`. View của tab mang `cards` (trang đang hiện), `total`, `page`, `pages`, `page_size`, `offset`. `Engine.page(sid, tab, n)` hiện trang `n` (1 = đầu; `None` = trang sau; quá cuối thì trang cuối).

Dựng lại (act, lượt chat, rebase) giữ số trang; trang được lấy lại từ thứ hạng mới (`window.window`). `change[tab] = {kept, added, removed, replaced_all}` so trang cũ với trang mới (`replaced_all` khi giữ dưới `replace_below` × trang cũ; tab chưa từng hiện thì không có thay đổi) để web chạy chuyển cảnh. Sau `rebase` (Search Input mới), `diff(..., rebuilt=True)` nói gọn điều đó: "Giữ 45 nơi, thay 3 nơi hợp hơn", "Danh sách đổi theo ý bạn: 24 nơi mới" hoặc "Các nơi đang gợi ý vẫn hợp, không cần đổi"; thay đổi không làm xê dịch gì thì `text` rỗng. `rebase` giữ lịch sử hoàn tác.

`Engine.search(sid, q)`: mỗi chữ gõ (bỏ dấu, hoa thường) phải là đầu một chữ trong tên, category Maps hoặc tên tab của nơi; tìm trên mọi tab và mục chưa xác minh, xếp theo `score`, tối đa 60 thẻ kèm `total`. `outside` = tối đa 8 nơi trong vùng có tên khớp mà không nằm trong danh sách (không tính chỗ ở), mỗi nơi kèm lý do của `why-not`.

`why-not` của một nơi có trong danh sách trả `listed: true` và vị trí ("xếp thứ 41/60; ở trang 2"), kèm mong muốn user đã nói mà nơi đó chưa khớp, khi tab của nó có nơi khớp ("Chưa thấy ghi món bánh căn ở nơi này", "Chưa khớp mong muốn “karaoke”"); thiếu dữ liệu không bao giờ thành "không bán". Nơi bị loại chỉ nêu điều kiện đã loại nó. Prompt của agent có mọi nơi trên màn, nhưng lý do chỉ cho trang đầu mỗi tab và nơi đã chọn. `page_size` = 24, `replace_below` = 0.3 trong `config/decision.yaml`.

## 10. So sánh

Chỉ tạo so sánh khi có lựa chọn thật: trong một nhóm gần trùng, hoặc giữa hai nơi cạnh tranh cùng một chỗ.

```text
A vs B
├── A hơn ở       feature / signal có bằng chứng ở cả hai, A tốt hơn
├── B hơn ở       ngược lại
├── giống nhau    không nêu (không phải lý do chọn)
├── chưa biết     khía cạnh một bên unknown → nói rõ, không coi là thua
└── hy sinh gì    hệ quả với chuyến: khoảng cách tới anchor / cụm, độ đông theo buổi, effort
```

So sánh có thêm hàng "Nổi tiếng vì" (khi một bên có `known_for`; bên kia "chưa biết") và "Tổng tiền mỗi người" (`cost.total_vnd.base`, ở mục hy sinh). Kiểm tra ngân sách của tổ hợp (§13) dùng `cost.total_vnd.base` thay cho giá vé ước tính khi có.

Ví dụ:

```text
A: gần cụm trung tâm, đông cuối tuần buổi sáng (62% trong 40 review nói đông)
B: yên tĩnh hơn, xa base hơn, cùng cụm với anchor TikTok 2
→ Chọn B nếu đi ngày 2 cùng TikTok 2; chọn A nếu muốn đi đâu cũng gần
```

Mỗi so sánh chỉ dùng giá trị trong serving record. Tác động di chuyển ở đây là **ước lượng thô** theo cụm; con số phút chính xác chỉ có sau Planning. Lựa chọn sau so sánh là tín hiệu mạnh cho Session Profile (§12).

## 11. Thẻ ứng viên

Mỗi ứng viên chỉ hiển thị thông tin phục vụ quyết định (`docs/Role_Web_Functional_Design.md` §2.5, `docs/UX_Design_Brief.md` §4):

| Mục | Nội dung | Nguồn |
|---|---|---|
| Vì sao phù hợp | Tối đa 3 dòng: mong muốn user nói ("Có bánh căn bạn muốn · theo menu", kiểu nơi, phong cách, giống X) → feature khớp `soft_weights` + bằng chứng (xu hướng review kèm cỡ mẫu) → `liked_groups` / `purpose` (✎) → vị trí. Không có dòng nào thì một dòng thật theo thành phần điểm lớn hơn (khoảng cách hoặc số người viết). Lưới và đĩa xoay cùng lấy dòng từ `web/src/user/ui/cardLines.ts`, chỉ khác cách vẽ | `wish`, Experience, Environment |
| Đánh đổi | Cờ từ §7, điểm thua trong so sánh | Hợp bối cảnh, So sánh |
| Thời gian ước tính | Khoảng min / typical / long | Estimate |
| Ảnh hưởng vị trí | "cùng cụm với X", "xa base", ước lượng thô | Hợp bối cảnh |
| Độ tin cậy | Trạng thái theo khía cạnh; `UNCERTAIN` / `OUTDATED` hiển thị rõ | Provenance |
| Phụ thuộc unknown | "Chưa biết ngân sách của bạn; giá nơi này khoảng …" | `unknowns` |
| Nổi tiếng vì | `known_for.headline` (cụm hiếm trong nhóm category) kèm số người nhắc | `details` |
| Tổng tiền | `cost.total_vnd` (một người: vé, gửi xe; kèm các khoản thêm) | `details` |

Giờ / giá / vị trí lấy từ bằng chứng official hoặc Google, không trộn với bằng chứng trải nghiệm (`docs/CORPUS.md` §Place Decision dùng corpus thế nào). Không hiển thị một review đơn lẻ như sự thật.

## 12. Người dùng tuyển chọn

### 12.1 Thao tác

| Thao tác | Tác động |
|---|---|
| Thêm | Vào tập đã chọn; nơi mới → resolve (§4) |
| Bỏ | Ra khỏi tập; hỏi lý do ngắn khi có ích (`Project_Context.md` §8.3) |
| Khóa | Giữ bắt buộc; xử lý xung đột theo §6.3, §13.3 |
| So sánh | Mở §10 |
| Thay | Đổi sang nơi thay thế trong nhóm |
| Xem thêm giống | Mở rộng nhóm / truy xuất thêm quanh feature đó |
| Chọn chỗ ở | Cả chuyến có **một** chỗ ở (`view.lodging`: `booked` = đã nói ở Hiểu chuyến đi, `chosen` = chọn ở đây, thay `booked`; `needed` = chưa biết). Tab "Chỗ ở" luôn có: chỗ ở trong corpus quanh các nơi đã chọn (Planning xếp, `docs/PLANNING.md` ⓐ). Chưa có chỗ ở thì chọn ngay; đã có (đã đặt hoặc đã chọn) mà muốn đổi thì Web hỏi xác nhận trước khi gửi action. `set_lodging` `{lodging: {kind: corpus, id}}` (tên, toạ độ, giá một đêm đọc từ bản ghi `stay`) hoặc một điểm từ ô tìm `{kind, text, lat, lng}`; `clear_lodging` bỏ. Không xếp hạng lại nơi nào |

Không thao tác nào bị chặn vì lựa chọn quá tải, vướng điều kiện hay chưa có chỗ ở: Web báo cái giá và để người dùng tự quyết (nút "Lập lịch" luôn bấm được khi đã chọn ít nhất một nơi).

### 12.2 Tín hiệu và thích nghi trong phiên

```text
thao tác → tín hiệu (độ mạnh theo Project_Context.md §8.2)
        → lý do (nếu có) → field tương ứng
              Xa quá          → travel tolerance ↓
              Đông quá        → crowd tolerance ↓
              Giá cao         → price sensitivity ↑
              Không hứng thú  → soft_weight feature đó ↓
              Đã từng đi      → Experience History
        → Session Profile → cập nhật soft_weights / pace của phiên → xếp hạng lại ⑤–⑥
```

- Chỉ ứng viên **chưa chọn** được xếp lại; nơi đã chọn / khóa không đổi vị trí.
- Không coi "không bấm" là không thích. Bỏ không lý do → chỉ giảm nơi đó, không suy ra feature.
- So sánh: học từ phần **khác nhau** giữa hai nơi, không từ phần giống (`Project_Context.md` §8.4).
- Mọi cập nhật chỉ ở Session Profile; Long-term Profile chỉ đổi theo `Project_Context.md` §8.6.

## 13. Khả thi của tổ hợp

Đánh giá các nơi đã chọn **như một nhóm**, chạy lại sau mỗi thao tác tuyển chọn và hiển thị trực tiếp.

### 13.1 Kiểm tra

| Kiểm tra | Cách tính (thô, tất định) |
|---|---|
| Tổng thời gian | Σ thời gian tham quan `typical` + ước lượng di chuyển theo cụm + đệm theo pace ≤ thời gian có (số ngày × khung ngày − anchor giờ cố định − giờ check-in/out, giờ rời Đà Lạt) |
| Anchor | Anchor giờ cố định không chồng nhau; nơi cùng ngày với anchor ở gần được |
| Giờ mở cửa | Mỗi nơi mở ít nhất một khung phù hợp trong các ngày của chuyến |
| Tải di chuyển | Số cụm cách xa ≤ số ngày; mỗi ngày không vượt travel tolerance thô |
| Ngân sách | Σ giá ước tính ≤ ngân sách (chỉ khi ngân sách đã biết; `unknown` → không kiểm, gắn cờ) |
| Số nơi mỗi ngày | Theo pace |

Giờ mở cửa `UNCERTAIN` / `OUTDATED` không làm fail; chúng tạo cảnh báo "kiểm tra lại trước chuyến".

### 13.2 Kết quả

```text
Khả thi           → cho xác nhận, chuyển Planning
Khả thi một phần  → chỉ ra nơi gây xung đột → constraint bị vượt → bỏ / thay thì được gì → user chọn
Không khả thi     → giải thích mất khớp tổng thể (thời gian cần > thời gian có, thiếu ngân sách,
                    anchor xung đột, quá nhiều cụm xa nhau) → quay lại tuyển chọn
```

Gợi ý sửa luôn kèm cái giá cụ thể, dựa trên cùng phép tính: "Bỏ C giúp ngày 2 bớt một cụm xa, khoảng 40 phút di chuyển (ước lượng)".

### 13.3 Nơi user khóa gây xung đột

Theo đúng mô hình constraint (`docs/ARCHITECTURE.md` §2): chỉ vi phạm user constraint → hỏi nới kèm cái giá; vi phạm physical → không tạo tổ hợp giả vờ khả thi (giữ wishlist, đề xuất ngày khác, bỏ nơi khác); giờ chưa chắc → cho giữ kèm cảnh báo.

## 14. Chạy lại khi đầu vào đổi

| Thay đổi | Chạy lại từ |
|---|---|
| Sửa `hard_filters`, ngày, mobility | ③ Sàng lọc |
| Thêm / đổi anchor, base | ① Resolve (anchor) rồi ④ |
| Sửa `soft_weights`, novelty, Session Profile | ⑤ Xếp hạng |
| Sửa pace | ⑥ Đa dạng (cỡ shortlist) + ⑨ Khả thi |
| Thêm / bỏ / khóa | ⑨ Khả thi; ⑤–⑥ cho phần chưa chọn |
| Planning báo không xếp được | ⑧ Tuyển chọn, kèm nơi gây lỗi |

Nơi đã chọn / khóa không bị loại âm thầm khi chạy lại; nếu chúng vi phạm điều kiện mới, hệ thống báo và hỏi.

## 15. Output

Output cuối cùng, đầu vào của Planning & Validation (`docs/PLANNING.md` §Đầu vào).

Confirm và draft khả thi kiểm lại chỗ ở corpus đã chọn hoặc đã đặt theo hard requirements
hiện tại, kể cả sau rebase. Không tự bỏ selection hoặc đổi chỗ ở khi kiểm fail/unknown;
confirm trả conflict, draft thường trả `None`. `draft(any=True)` giữ dữ liệu để tìm chỗ ở thay thế.

Read `Tools.read(sid, "evidence", {place, feature, context?})` trả public `PlaceEvidence`:
binding, value/status serving, quote/source/observation pointer và reason khi thiếu. Input validate
bằng `EvidenceInput`; không đọc corpus ngoài membership hoặc binding của phiên. UNCERTAIN/missing
không lấy semantic quote làm bằng chứng. Context thiếu verdict riêng giữ unknown; journey lịch sử
binding null trả `legacy_lineage_unavailable`. Lookup chỉ chạy khi được đọc, không ghi state/log.

```text
Decision Output
├── confirmed      nơi user xác nhận: entity id, vai trò (anchor | locked | selected),
│                  thời gian tham quan (khoảng), cờ cảnh báo, constraint đã nới (nếu có)
├── backup_pool    ứng viên cùng nhóm / bị loại vì lý do theo ngữ cảnh, kèm lý do → dùng cho dự phòng
├── wishlist       nơi user muốn nhưng vi phạm physical, kèm lý do
├── trip_context   Search Input tại thời điểm xác nhận (bản chụp)
├── decision_log   vì sao chọn, vì sao bỏ, đánh đổi user chấp nhận → để giải thích ở kế hoạch cuối
└── lodging        chỗ ở chọn ở tab "Chỗ ở" {kind, id?, text, lat, lng, price_vnd?} | null → nơi mọi ngày bắt đầu và kết thúc
```

`decision_log` giúp kế hoạch cuối trả lời "Vì sao chọn những nơi này?" và "Đã phải hy sinh gì?" (`docs/PLANNING.md` §Plan Output).

## 16. Ví dụ đầy đủ

Tiếp ví dụ `TRIP_UNDERSTANDING.md` §12. Search Input:

```text
context       12–14/12 · 3 ngày · base = trung tâm · ô tô riêng · bố mẹ
hard_filters  effort.slope = none · walk ≤ 15'
anchors       TikTok 1, TikTok 2
soft_weights  crowd_low↑ · view↑ · long_stay↑ · coffee↑ (profile) · hiking = off
pace          thong thả
novelty       mới; giảm Hồ Xuân Hương, Langbiang
unknowns      budget, dietary
```

```text
① Resolve       TikTok 1 → match chính xác, POI (quán cà phê, cụm A)
                TikTok 2 → mơ hồ giữa 2 định danh → user chọn → POI (cụm B)
② Truy xuất     ứng viên theo view, coffee, long_stay quanh trung tâm, cụm A, cụm B
③ Sàng lọc      nhiều nơi bị loại vì có dốc / bậc hoặc đi bộ > 15'
                một số nơi thiếu bằng chứng effort → "chưa xác minh được", không vào danh sách chính
                TikTok 1 có bằng chứng "nhiều bậc thang" → anchor vi phạm user hard
                → hỏi: "Giữ TikTok 1 nghĩa là bỏ điều kiện tránh bậc cho riêng nơi này?"  [Giữ · Bỏ]
                → user chọn Bỏ → TikTok 1 vào wishlist
④ Hợp bối cảnh  nơi cùng cụm B được cộng; nơi đông sáng cuối tuần bị trừ (13/12 là thứ Bảy)
⑤ Xếp hạng      Langbiang, Hồ Xuân Hương bị giảm (novelty); hiking không cộng
⑥ Đa dạng       4 quán cà phê view đồi gần trùng → 1 nhóm, đại diện + 3 thay thế
                shortlist nhỏ, chia nhóm: cà phê view · thiên nhiên dễ đi · ăn uống
⑦ So sánh       trong nhóm cà phê: A gần trung tâm nhưng đông; B yên tĩnh, cùng cụm TikTok 2
⑧ Tuyển chọn    user chọn B sau so sánh → tín hiệu mạnh: crowd_low > khoảng cách ngắn
                user bỏ một vườn hoa, lý do "Đông quá" → crowd tolerance ↓ → xếp lại phần chưa chọn
⑨ Khả thi       chọn 11 nơi, pace thong thả → khả thi một phần: ngày 2 dư thời gian cần
                gợi ý: bỏ 2 nơi ít điểm nhất ở cụm xa, hoặc chuyển sang ngày 3
                user bỏ 1, chuyển 1 → khả thi; cảnh báo: giờ mở cửa của 1 nơi là OUTDATED
⑩ Xác nhận      confirmed = TikTok 2 + 9 nơi · wishlist = TikTok 1 (bậc thang) · backup_pool = nhóm cà phê còn lại, …
```

Giá cả không được kiểm vì `budget` là `unknown`; thẻ ứng viên hiển thị khoảng giá để user tự cân nhắc.

## 17. Đánh giá — `python -m decision evaluate`

Mô phỏng offline trên các Trip State ẩn (dùng chung bộ mô phỏng với `TRIP_UNDERSTANDING.md` §13) + nhãn review của corpus. So với baseline trong `Project_Context.md` §19.

| Chỉ số | Đo gì |
|---|---|
| Hard constraint violation trong shortlist | Sàng lọc có fail-closed đúng không (mục tiêu: 0) |
| Unsupported claim rate trong thẻ / so sánh | Lời giải thích có bịa ngoài serving record không |
| Tỉ lệ user chọn được từ shortlist | Shortlist có hữu ích không |
| Số nơi user tự thêm từ ngoài | Truy xuất bỏ sót |
| Tỉ lệ nơi gần trùng trong shortlist | Kiểm soát đa dạng |
| Số vòng tuyển chọn ↔ khả thi trước khi xác nhận | Chi phí quyết định |
| Tỉ lệ tổ hợp "khả thi" bị Planning trả về | Độ chính xác của ước lượng thô |
| Kết quả đổi hợp lý khi đổi preference | Cá nhân hóa (`Project_Context.md` §18) |

---

## 18. CLI và API

```
python -m decision evaluate            # 30 Trip State ẩn ở config/eval_trips.yaml, trong tiến trình
python -m decision serve [--port 8767] # HTTP + SSE độc lập
```

`Data.load(region=None, data_root=..., snapshot_version=...)` nạp một vùng của snapshot
(`default_region` khi không truyền) và làm nóng các cột bảng. Factory capture hoặc nhận public
corpus binding, đọc root/version đó; không chọn pointer độc lập. Thiếu snapshot trả lỗi.
`Data(records)` dựng một vùng trong RAM cho test. Mỗi phiên giữ memo ba tầng (screen, fit,
score) theo input của từng tầng (`frame.table`), nên `select` / `lock` / `undo` không tính lại
phần không đổi. `corpus.ontology.load` parse YAML một lần cho mỗi phiên bản file (theo mtime và kích thước): mỗi request validate Search Input nhiều lần, parse lại tốn ~1,4 s ở lượt tạo phiên đầu.

Search Input, snapshot và Decision Output giữ binding của journey; adapter từ chối binding
lệch Engine, kể cả restore/rebase. Decision Output validate binding khớp `trip_context`, giữ
activity explicit/inferred và budget intent/provenance. Chọn chỗ ở corpus vẫn kiểm requirement
theo activity accommodation; evidence không đủ cho physical/suitability bị loại. Pin/legacy:
`docs/AGENT_HARNESS.md` §3.

User Web gọi Decision qua harness bằng journey chung (`docs/AGENT_HARNESS.md`); `advance` lấy Decision Output trên server để tạo Planning. Public API xuất `Tools`, `create_engine`, `DecisionOutput`; `tools.py` sở hữu snapshot/rebase, `contracts.py` validate output ở biên, `skills.yaml` giới hạn quyền. Agent dùng runtime public `agents`; heuristic cho lệnh tên chính xác ở `docs/AGENT_HARNESS.md` §5.

`serve` độc lập bind `127.0.0.1`. Cần `AGENT_*` trong `.env` (`docs/LLM_PROVIDER.md`); thiếu thì lượt chữ cần suy luận chạy bằng `policy.py`.

```
POST   /api/decision/sessions                   {search_input, trip_session?}
GET    /api/decision/sessions/<id>
POST   /api/decision/sessions/<id>/act          tất định; 400 khi act sai (state không đổi)
POST   /api/decision/sessions/<id>/turn         {text} → SSE: say(delta|replace) · view · done · error
GET    /api/decision/sessions/<id>/compare?a=&b=
GET    /api/decision/sessions/<id>/why-not/<place_id>
POST   /api/decision/sessions/<id>/confirm      → Decision Output; 409 khi chưa chốt được
```

Lỗi: 400 act sai hoặc `text` rỗng / > 1000 ký tự, 404 không có phiên, 409 version ontology của Search Input khác corpus hoặc chưa chốt được.

Lượt chữ: agent trả các update `select | drop | lock | visited` (một nơi trên màn), `travel | crowd | price` (phản hồi chung) và `trip` — mong muốn về chuyến hoặc kiểu nơi ("yên tĩnh hơn", "không thích quán giống X"), quote là đúng lời người dùng. Engine áp các update nơi như act; các update `trip` không đổi phiên Decision mà phát event `trip {texts}` trước `view`. Harness chuyển chúng cho Trip Understanding (`refine`) rồi `rebase` Decision trên Search Input mới (`docs/AGENT_HARNESS.md` §2). Gu không bao giờ thành act `prefer` / `note` từ lượt chữ. Không gọi model khi: lệnh tên chính xác; toàn câu là phản hồi chung có sẵn ("ít đông", "yên tĩnh", "rẻ hơn", "gần trung tâm" → `feedback` crowded / pricey / far, `heuristics.common_wish`); hoặc câu không nêu nơi nào trên màn, không chọn / bỏ, không phải câu hỏi (`general_wish`): khi đó chuyển thẳng thành update `trip` cho Trip Understanding. Còn lại một lượt gọi model với prompt chỉ gồm nơi user nêu tên, nơi đã chọn và vài nơi đầu mỗi tab (`Engine._prompt_places`). Câu trả lời sau khi dựng lại danh sách nêu đúng số nơi ở tiêu đề trang (tổng các tab).

Act trên một địa điểm: `select`, `drop` (kèm `reason`: `far | crowded | pricey | dislike | visited`), `lock`, `unlock`, `swap`, `relax`, `wishlist`; ngoài ra `prefer`, `feedback`, `answer`, `undo`, `confirm`. `scope.replan_scope(act)` trả bước sớm nhất phải chạy lại theo bảng §14; `scope.input_scope(old, new)` làm điều đó khi người dùng sửa bản hiểu nhu cầu.

Module:

```
src/decision/
  model.py settings.py       kiểu dữ liệu; ngưỡng từ config/decision.yaml
  geo.py trip_days.py        khoảng cách thô theo cụm; các ngày của chuyến
  screen.py                  ③ sàng lọc fail-closed, nới theo từng nơi (§6)
  fit.py                     ④ độ hợp bối cảnh thô (§7)
  rank.py                    ⑤ điểm kèm từng thành phần (§8)
  wishes.py                  mong muốn của Trip → điểm wish (§8)
  diversify.py               ⑥ gom nơi gần trùng + MMR (§9)
  window.py                  trang của mỗi tab và thay đổi của nó sau khi dựng lại (§9.4)
  compare.py cards.py        ⑦ so sánh chỉ trên bằng chứng; thẻ ứng viên (§10, §11)
  curation.py                ⑧ act thuần sinh State mới + Session Profile nó dạy (§12)
  feasibility.py             ⑨ khả thi của tổ hợp (§13)
  frame.py                   ③–⑤ cho mọi nơi của một vùng bằng bảng; memo theo tầng (§2.2)
  pipeline.py                ① → ⑥ một đường, tất định
  output.py                  ⑩ Decision Output (§15)
  scope.py                   chạy lại từ bước nào (§14)
  agent.py guard.py policy.py  một call mỗi lượt chữ; guard; policy từ khóa khi agent lỗi
  engine.py session.py server.py  phiên có phiên bản, HTTP + SSE, cổng 8767
  evaluate.py                đo offline (§17)
```

Test: `python -m pytest -q tests/decision`; gọi model thật: `python -m pytest -m live tests/decision/test_decision_live.py`.

Web: `web/src/user/pd/` (`types.ts`, `api.ts`, `decision.tsx` — `DecisionProvider` + `useDecision()`), màn `screens/Explore.tsx`, `PlaceDetail.tsx`, `Compare.tsx` và `ui/SelectedBar.tsx` (khả thi + lịch ngầm), `ui/Assistant.tsx` (lượt chat). `Engine.draft` trả Decision Output nháp không lưu, cho lịch ngầm của harness. Chức năng từng màn: `docs/Role_Web_Functional_Design.md` §2.5–2.9.
