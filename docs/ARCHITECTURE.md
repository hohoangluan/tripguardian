# Kiến trúc — TripGuardian

Bản đồ hệ thống: có những phần nào, chúng nối với nhau ra sao, quy tắc nào áp cho mọi phần. Chi tiết từng phần nằm ở tài liệu của chính phần đó; trang này không chép lại.

Phạm vi kiểm chứng ban đầu: **Đà Lạt**. Nguyên tắc sản phẩm (vì sao, cho ai): `docs/Project_Context.md` §14.

---

## 1. Nguyên tắc ở mức hệ thống

* Thiếu bằng chứng thì giữ `unknown`; hệ thống không bao giờ bịa fact.
* Input của người dùng mô tả **chuyến đi**, không mô tả bản thân địa điểm.
* Live context chỉ dành cho từng request và không trở thành tri thức lâu dài về địa điểm.
* Điều bất khả thi về vật lý không thể bị ghi đè.
* Offline **ghi** Place Intelligence. Online chỉ **đọc** nó; online chỉ ghi lịch trình và user / session profile.

---

## 2. Mô hình constraint

Ba loại quy tắc quyết định, dùng xuyên suốt cả bốn giai đoạn:

| Loại | Ý nghĩa | Nới được không? | Xử lý khi vi phạm |
|---|---|---|---|
| Physical constraint | Điều bất khả thi trong thực tế | **Không** | Loại, hoặc giữ ở wishlist kèm lý do; không có đường code nào nới |
| User hard constraint | Yêu cầu rõ ràng của người dùng | Chỉ khi người dùng xác nhận | Hỏi có nới không, **luôn kèm cái giá đã tính** |
| Soft preference | Sở thích dùng để xếp hạng | Có | Chỉ đổi thứ tự, không loại |

```text
Địa điểm đóng cửa 17:00, sớm nhất đến được 18:10   → physical  → không tạo lịch hợp lệ
Người dùng đặt trần 30 phút mỗi chặng, cần 42 phút → user hard → "nới lên 42 phút?" kèm hệ quả
```

Mỗi kiểm tra trả **ba** giá trị, không phải đúng / sai: `pass | fail | unknown`. Thiếu bằng chứng cho một hard constraint thì không được nói địa điểm là an toàn — fail-closed (`docs/PLACE_DECISION.md` §6.2).

---

## 3. Bốn giai đoạn

```text
        ┌──────────────────────┐
        │  PLACE INTELLIGENCE  │  offline, không biết chuyến đi nào
        │  docs/CORPUS.md      │  địa điểm → fact / signal / estimate có bằng chứng
        └──────────┬───────────┘
                   │  serving index (chỉ đọc)
                   ▼
        ┌──────────────────────┐
        │  TRIP UNDERSTANDING  │  người dùng cần gì cho CHUYẾN NÀY
        │  docs/TRIP_...md     │  → Trip State → Search Input
        └──────────┬───────────┘
                   │  Search Input
                   ▼
        ┌──────────────────────┐
        │    PLACE DECISION    │  chọn đúng địa điểm TRƯỚC khi xếp lịch
        │  docs/PLACE_...md    │  → shortlist → người dùng tuyển chọn → Decision Output
        └──────────┬───────────┘
                   │  Decision Output  +  Live Context
                   ▼
        ┌──────────────────────┐
        │ PLANNING & VALIDATION│  tổ hợp đã chọn có đi được cùng nhau không
        │  docs/PLANNING.md    │  → phương án, chỗ ở, độ vững → Plan Output
        └──────────────────────┘
```

| Giai đoạn | Code | Tài liệu | Contract ra |
|---|---|---|---|
| Place Intelligence | `src/corpus/` | `docs/CORPUS.md` | serving record (`CORPUS.md` §Bản ghi địa điểm) |
| Trip Understanding | `src/trip/` | `docs/TRIP_UNDERSTANDING.md` | Search Input (§9 của nó) |
| Place Decision | `src/decision/` | `docs/PLACE_DECISION.md` | Decision Output (§15 của nó) |
| Planning & Validation | `src/planning/`, `src/live/` | `docs/PLANNING.md` | Plan Output (§Plan Output của nó) |

Mỗi giai đoạn là một package độc lập, giao tiếp **chỉ** qua public API (`__init__.py`) của package khác (`RULE.md` §2). Phụ thuộc một hướng:

```text
corpus   ──►  (không phụ thuộc gì)
trip     ──►  corpus.serving, corpus.ontology
decision ──►  corpus.serving, corpus.ontology
live     ──►  corpus.crawl            (chỉ 3 tên: open_sessions, maps_search, LoginRequired)
planning ──►  live, decision, trip, corpus.serving, corpus.ontology
agents   ──►  corpus.llm
harness  ──►  trip, decision, planning, agents
```

Agent của module dùng runtime public `agents`; `harness` gọi `Tools` public của module, router chọn module theo stage. Hành trình, capability và persistence: `docs/AGENT_HARNESS.md`.

`live` không biết `planning`. `corpus` không biết giai đoạn nào ở sau nó. Test khẳng định các ranh giới này (`tests/planning/test_planning_boundaries.py`, `tests/live/test_boundaries.py`).

---

## 4. Vai trò model

Code gọi model theo **vai trò**, không gọi thẳng một model cố định: **ASR** (âm thanh → transcript), **Extractor** (mọi việc khối lượng lớn), **Judge** (chốt chặn trước người), **Agent** (hiểu câu tự do trong Trip/Decision và đề xuất bố trí nội bộ trong Planning). Định nghĩa và yêu cầu từng vai trò: `docs/CORPUS.md` §Vai trò model. Model nào đang đảm nhận vai trò nào: `docs/LLM_PROVIDER.md`.

Agent online dùng runtime chung: output validate theo schema và guard nghiệp vụ kiểm quyền/grounding trước khi chạy act. Heuristic xử lý input đơn giản hiểu trọn vẹn; Trip/Decision dùng `policy.py` khi call lỗi hoặc chậm, Planning nội bộ giữ baseline đã kiểm. Solver/validator quyết định khả thi. Chi tiết: `docs/AGENT_HARNESS.md` §1, §5 và `docs/PLANNING.md` §Agent đề xuất nội bộ. Model không ghi fact hoặc tạo địa điểm.

---

## 5. Cấu hình và dữ liệu

Mọi ngưỡng nằm trong `config/`, không trong code:

| File | Của ai | Nội dung |
|---|---|---|
| `cities.yaml`, `queries.yaml` | corpus | thành phố, vùng quét, category, trần crawl |
| `ontology.yaml` | corpus + profile | feature ontology có version (dùng chung id) |
| `category_defaults.yaml` | corpus | mặc định theo nhóm category cho estimate |
| `serving.yaml` | corpus | ngưỡng của serving record |
| `trip.yaml` | trip | ngân hàng câu hỏi, ngưỡng dừng hỏi |
| `agents.yaml` | agents | giới hạn call và queue của runtime trong tiến trình |
| `decision.yaml` | decision | trọng số xếp hạng, cỡ shortlist, ngưỡng sàng |
| `planning.yaml` | planning | nhịp độ, cụm, ngày, mục tiêu, độ vững, dự phòng, chỗ ở |
| `live.yaml` | live | endpoint và TTL từng nguồn live |
| `climate.yaml`, `holidays.yaml` | live | khí hậu Đà Lạt theo tháng, lễ Việt Nam (nhập tay) |
| `eval_trips.yaml` | decision + planning | 30 Trip State ẩn, dùng chung để đo cả hai bước |

Dữ liệu: `data/<nguồn>/` thô và observation, `data/intel/` + `data/serving/` Place Intelligence (`docs/CORPUS.md` §Data model); `data/live/` cache live có TTL (`docs/PLANNING.md` §Ranh giới module). Không nguồn nào gộp với nguồn khác, cả trong code lẫn trong thư mục dữ liệu (`RULE.md` §2).

User Web dùng journey chung; harness lưu snapshot các module, revision và receipt cùng file tại `data/harness/sessions/` (`docs/AGENT_HARNESS.md` §3). CLI/API module độc lập mirror state vào `data/{trip,decision,planning}/sessions/`. Một act sinh `State` mới; `scope.py` quyết định phần nào phải tính lại.

---

## 6. Các vòng phản hồi

Hệ thống không phải pipeline một chiều. Bốn vòng, mỗi vòng thuộc về một tài liệu:

```text
Vòng lựa chọn       Shortlist → tuyển chọn → khả thi → xung đột → tuyển chọn
                    (PLACE_DECISION.md §13, §14)

Vòng xếp lịch       Planning không xếp được một nơi → quay về tuyển chọn → thay / bỏ / nới → Planning
                    (PLACE_DECISION.md §14 dòng cuối, PLANNING.md ⓔ)

Vòng kiểm tra       Lịch → validate + độ vững → vấn đề → sửa / phương án thay → kiểm lại
                    (PLANNING.md ⓔ ⓕ, §Vòng người dùng sửa và góp ý)

Vòng cá nhân hóa    Profile → gợi ý → quyết định của người dùng → Session Profile → gợi ý thích nghi
                    → kết quả chuyến đi → bằng chứng lặp lại / mạnh? → chỉ session | Long-term Profile
                    (Project_Context.md §8, §10)
```

Hai vòng đầu là lý do Place Decision và Planning tách nhau mà vẫn nối được: Decision ước lượng **thô** để chọn nhanh, Planning tính **thật** rồi trả ngược nơi gây lỗi.

---

## 7. Giao diện và cổng

```text
web (Vite, :5173)  /landing  giải thích vấn đề, một CTA
                   /app      User Web   → harness :8769 → trip · decision · planning
                   /admin    Admin Web  → review :8765
```

Chức năng từng màn theo vai trò: `docs/Role_Web_Functional_Design.md`. Nguyên tắc hiển thị và hệ thị giác: `docs/UX_Design_Brief.md`. Đặc tả trang cho designer: `docs/UI_SPEC_USER_WEB.md`. Cách chạy cả stack: `README.md`.

---

## 8. Các quyết định thiết kế chính

| Quyết định | Lý do |
| --- | --- |
| Place Intelligence tách khỏi bối cảnh chuyến đi | Tri thức địa điểm và nhu cầu từng chuyến có vòng đời khác nhau |
| Khám phá và bằng chứng tách riêng | Nguồn giúp tìm ra địa điểm chưa chắc đáng tin cho mọi nhận định |
| Trạng thái bắt đầu và mức dẫn dắt độc lập | Trạng thái bắt đầu có sẵn trong input nên không cần hỏi; mức dẫn dắt phải suy từ hành vi nên không thể hỏi trước |
| Địa điểm của người dùng được resolve trước khi đánh giá | Tên đã lưu có thể là alias, bị trùng, hoặc là nơi chưa biết |
| Physical, user-hard, và soft constraint tách riêng | Chúng cần cách xử lý xung đột khác nhau |
| Chọn dùng độ hợp không gian thô; xếp lịch dùng thời gian di chuyển thực tế | Tránh tính kế hoạch chi tiết tốn kém trước khi biết shortlist |
| Người dùng tuyển chọn trước khi xếp lịch cuối | TripGuardian hỗ trợ quyết định thay vì quyết định thay |
| Khả thi đánh giá theo tổ hợp | Các nơi hợp lệ riêng lẻ vẫn có thể tạo thành chuyến đi bất khả thi |
| Nhịp độ và mục tiêu tối ưu tách riêng | "Thư thả" mô tả cường độ chuyến đi; "tiết kiệm" hay "ít di chuyển" mô tả mục tiêu lập kế hoạch |
| Kiểm tra là tất định | Một kế hoạch trông hợp lý là chưa đủ |
| Độ vững đi sau khả thi | Kế hoạch đúng về toán vẫn có thể dễ đổ vỡ trong thực tế |
| Phương án dự phòng dùng lại các ứng viên bị loại | Phương án thay thế giải thích được và hợp bối cảnh |
| Chỗ ở không vào Place Intelligence, chỉ tra live theo request | Giá và tình trạng phòng đổi theo ngày; nó là biến trong bài tối ưu, không phải tri thức về địa điểm |
| User Profile là prior, xếp hạng sau constraint | Hành vi trong quá khứ không được lấn át chuyến đi hiện tại hay constraint của nó |
| Session profile và long-term profile tách riêng | Sở thích có thể thay đổi trong một chuyến mà không viết lại gu dài hạn |
| Lịch sử trải nghiệm tách khỏi sở thích | Đã đến không có nghĩa là thích; chưa trải nghiệm không có nghĩa là không thích |
| Dữ liệu địa điểm do agent xây, được kiểm tra bằng gate và định tuyến rủi ro | Mở rộng theo số địa điểm; công sức của người tăng theo rủi ro, không theo kích thước corpus |
| Cố định vai trò model, không cố định model | Đổi model bằng config khi nhãn review cho thấy model tốt hơn hoặc rẻ hơn |
| Phiên là `State` có phiên bản + một hàm thuần sinh `State` mới | Undo / redo thật, và mỗi act chỉ chạy lại đúng phần bị ảnh hưởng (`scope.py`) |
