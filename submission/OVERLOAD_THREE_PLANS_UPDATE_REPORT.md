# TripGuardian — Overload & Three Plans Update Report

> Báo cáo cập nhật Planning quá tải và ba hướng lập lịch. Bố cục theo `TECHNICAL_REPORT.md`: phạm vi, yêu cầu, thiết kế, kiểm chứng và giới hạn. Số liệu dưới đây là kết quả kiểm thử của đợt sửa này; không phải đánh giá với người dùng thật hoặc benchmark dịch vụ live.

---

## 1. Scope & Requirements — Phạm vi cập nhật

Khi danh sách đã chọn quá tải, TripGuardian cần cho người dùng so sánh **Tiết kiệm**, **Trải nghiệm tốt nhất** và **Gọn tuyến**, biết mỗi hướng giữ/bỏ nơi nào, rồi tự chọn và chỉnh lịch. **Giữ tất cả** là lịch đối chiếu riêng, có kết luận validator và độ vững của chính nó.

Đợt này kiểm tra phần Luna triển khai theo `docs/OVERLOAD_AND_THREE_PLANS_IDEAS.md` và sửa các lỗi được ghi trong báo cáo implementation. Phần composer, session và UI đã có được giữ lại; các thay đổi tập trung vào lỗi runtime và đường đi thật từ Decision qua harness đến Planning/Web.

| Yêu cầu liên quan trong báo cáo kỹ thuật | Nội dung cập nhật |
|---|---|
| FR-07 — khả thi của tổ hợp | Handoff giữ selection gốc; cảnh báo overload dẫn đến màn chọn ba hướng |
| FR-08 — dựng lịch | Chọn profile dùng cấu hình mục tiêu có thật; `keep_all` có đường xử lý riêng |
| FR-09 — validator trước khi chốt | Chốt bị chặn khi timeline hoặc điều kiện active profile không đạt |
| FR-10 — độ vững và dự phòng | Giữ phần đối chiếu độ vững; backup edit không làm hỏng metrics |
| FR-12 — sửa lịch, hoàn tác | Preview gắn với action/context; kiểm undo/redo/replay và make-room nguyên tử |
| NFR — giải thích, tính đúng, độ tin cậy | Hiện delta, nguồn utility đúng, loại response cũ và kiểm owner ở HTTP |

Không nới hard/physical constraint; không thay Places Intelligence hoặc cấu hình model.

## 2. Error Analysis & Resolution — Lỗi và cách xử lý

| Vấn đề xác minh được | Nguyên nhân / ảnh hưởng | Xử lý |
|---|---|---|
| Chọn profile ném `KeyError: balance` | Nhánh rebuild truy cập mục tiêu không có trong config; năm test edit có sẵn fail trước khi thao tác được thực hiện | Fallback dùng `least_travel`; giữ mục tiêu của profile khi có cấu hình |
| Backup metrics | Backup không thuộc selection gốc; nguồn utility phải phân biệt score Decision và giá trị theo sở thích | Backup không góp vào tỷ lệ utility selection giữ lại; nguồn fallback là `selection_and_preferences` |
| Make-room thiếu kiểm preview | Cần ràng buộc thao tác bỏ nhiều nơi với đúng thay đổi đã xem | Boundary public bắt buộc token; regression kiểm token sai và sửa nested action/drop list; replay dùng action public |
| Preview cũ ghi đè panel hoặc lỗi | Read chưa có revision hành trình; request đang chờ có thể trả sau mutation hoặc đổi context | Harness trả revision; provider giữ preview và kiểm thứ tự request, journey, session, revision, captured View ở cả success/catch |
| Giữ tất cả chưa chọn/chốt được | Một số nhánh selection, scoring và confirm chỉ duyệt ba profile | Hoàn thiện `keep_all` trong selection/rebuild/metrics/confirm/replay; không gán baseline thành profile Trải nghiệm |
| UI chưa chặn đủ đường thao tác | Card, tab, bảng so sánh và nút chốt cần cùng phản ánh trạng thái hợp lệ | Khóa profile unavailable; khóa chốt khi validator hoặc active profile không đạt; bảng so sánh khóa khi mutation đang chạy |
| Ba thẻ bị bỏ qua ở handoff | `toPlan → recommend` tự chọn profile đầu trước khi mở Planning; lỗi này được browser phát hiện | Web bỏ automatic recommend với overload; server trả `choose_overload_profile` khi chưa có lựa chọn |
| Thiếu thông tin so sánh | Người dùng cần thấy thay đổi so với selection và phần dữ liệu chưa biết | Hiện delta của lịch hiện tại, lý do trên card, tỷ lệ utility/mong muốn và số nơi chưa có giá |

Những sửa trước đó của Luna về wish theo giờ, dữ liệu thiếu, lodging overload, directed transport, severe-weather fail-closed và reoptimize được kiểm lại trong suite liên quan. Không nhận các phần đó là implementation mới của đợt sửa này.

## 3. Component Design — Thiết kế và contract hiện tại

### 3.1. Handoff và quyền lựa chọn

```text
Decision xác nhận selection gốc
    → Harness advance
    → Planning có overload
    → Web hiện ba thẻ và lịch Giữ tất cả để đối chiếu
    → User chọn profile available hoặc Giữ tất cả hợp lệ
    → Sửa / preview / apply
    → Validator + điều kiện profile
    → Confirm → Plan Output
```

`recommend` không tự chọn một hướng overload khi user chưa chọn. Luồng không overload giữ automatic recommendation hiện có.

### 3.2. Preview và apply

Read HTTP `planning/preview-act?action=<JSON>` kiểm đăng nhập, owner, JSON object và giới hạn 8.192 ký tự. Response có revision hành trình; read không tăng revision hoặc ghi session snapshot.

Preview tạo draft trên bản sao runtime. Token ràng buộc action và context của phiên; apply với token sai, stale hoặc action bị sửa bị từ chối. `make_room` bắt buộc token tại boundary public. Các act legacy vẫn dùng được không cần preview.

Provider giữ panel preview. Response từ request cũ, revision cũ hoặc View/Planning session cũ không được mở panel hay ghi lỗi vào context mới. Apply gửi đúng action/token đang hiển thị.

### 3.3. Utility, metrics và Giữ tất cả

Tỷ lệ giữ giá trị selection được tính theo:

```text
value_share = utility của các nơi selection còn trong lịch
              / utility của toàn selection gốc
```

Backup không vào tử số này. Utility theo sở thích của backup không được gắn nhãn `decision_score`. Test bao phủ swap và add-from-backup qua cả ba profile.

Giữ tất cả có timeline, violations, robustness và chi phí địa điểm đã biết để đối chiếu. API cho mở draft lỗi để kiểm tra; confirm vẫn từ chối timeline vi phạm hoặc nơi chưa xếp được. Web cho chọn baseline hợp lệ. Sau edit, khả năng confirm được tính lại; delta thiếu dữ liệu hoặc khác home/basis không so được là `unknown`.

Contract chi tiết và hành vi runtime chỉ duy trì tại `docs/PLANNING.md` §Vòng người dùng sửa và góp ý; revision/HTTP tại `docs/AGENT_HARNESS.md`.

## 4. Testing & Validation — Kiểm chứng

### 4.1. Kết quả đã chạy

| Phạm vi | Kết quả | Bằng chứng / giới hạn |
|---|---:|---|
| Planning + Decision + Harness | **791 passed, 98 skipped, 1 deselected** | 276,51 giây; suite bị ảnh hưởng, không phải toàn repo |
| Overload edits | 16 passed | Backup qua ba profile; keep-all, make-room, undo/redo/replay |
| Edits + real overload handoff | 17 passed, 1 skipped | Decision và Planning thật; automatic recommend không tự chọn profile |
| Preview HTTP | 1 passed, 1 skipped | Owner đúng/sai, chưa đăng nhập, JSON sai, query vượt giới hạn, read-only revision/snapshot |
| Preview state Web | 5 passed | Thứ tự request, edit/revision, đổi journey và reload View/session trong cùng journey |
| Browser tổng hợp | 1 passed, 1 skipped | 91,56 giây; Chromium và HTTP/Decision/Planning thật, nguồn live và đăng nhập giả lập |
| Web build | Pass | TypeScript + Vite; còn cảnh báo config và chunk size có sẵn |

Các hàng focused là phạm vi kiểm bổ sung, **không cộng** vào số pass của suite tổng để tạo một tổng mới. Chi tiết lệnh chạy và RED/GREEN nằm trong `docs/LUNA_OVERLOAD_THREE_PLANS_IMPLEMENTATION_REPORT.md` §Kiểm chứng.

### 4.2. Kịch bản hồi quy

- **Giữ tất cả:** chọn/chốt lịch hợp lệ; draft invalid không confirm; undo/redo và rebuild sau restart giữ lịch.
- **Backup:** preview không đổi snapshot; metrics giữ đúng mẫu số selection; swap/add không crash; replay nhất quán.
- **Make-room:** thiếu/sai token hoặc sửa nested edit/drop list bị từ chối; đúng token áp dụng nguyên tử và replay được.
- **Wish theo giờ:** fixture có sun `(360, 1050)`; một visit không đồng thời đáp ứng sunrise và sunset. Fixture thiếu sun vẫn kiểm unknown riêng.
- **Chuyến dài:** đúng 98 nơi/14 ngày có hướng trimmed hợp lệ, giữ must và không trùng visit; test tuần nhẹ được giữ riêng.
- **Handoff:** public Decision → Harness → Engine Planning thật tạo ba hướng và giữ selection gốc; chốt hướng hợp lệ.

Browser đã chạy: Chọn nơi quá tải → Xem 3 hướng → ba card → chọn hướng available → mở timeline Giữ tất cả → preview restore/make-room nếu cần → apply → đổi Gọn tuyến → preview reoptimize → đóng preview → chốt → `/app/done`. Không có page error trong lần pass.

### 4.3. Môi trường và diễn giải

Python 3.12 qua `.venv/bin/python`; browser dùng Chromium. HTTP test chạy ngoài sandbox do giới hạn localhost socket. Đây là kiểm thử với serving records và live fixtures tổng hợp; thời gian chạy suite không phải latency người dùng hoặc tốc độ dịch vụ live.

Browser lần đầu bắt được lỗi tự chọn profile. Lần sau test cố chọn Tiết kiệm unavailable; test được sửa để chọn một hướng available, giữ nguyên điều kiện fail-closed của sản phẩm.

## 5. Limitations — Giới hạn của kết luận

| Chưa có bằng chứng | Không được suy ra từ kết quả hiện tại |
|---|---|
| `TEST_DATABASE_URL` chưa được cấu hình | Không khẳng định persistence Postgres đã pass |
| Chưa chạy riêng browser swap, undo/redo hoặc đổi journey khi preview đang chờ | Engine/gate tests không thay thế bằng chứng E2E cho các bước đó |
| Không gọi model, OSRM thật hoặc lodging crawl thật | Không khẳng định chất lượng model hay độ chính xác nguồn live |
| Chưa đo confusion matrix Decision/Planning, p50/p95 composer hoặc thử nghiệm người dùng | Không khẳng định mức cải thiện chất lượng, tốc độ hay lợi ích thực tế |
| Đề xuất ý tưởng rộng hơn phạm vi sửa lỗi | Không tuyên bố toàn bộ `OVERLOAD_AND_THREE_PLANS_IDEAS.md` đã hoàn thành |

Không triển khai production, không stage/commit và không dọn các thay đổi dirty ngoài phạm vi. Review độc lập tìm thêm stale-error và regression đã được sửa; lượt đọc lại cuối của reviewer bị lỗi khởi tạo process nên không ghi là đã được reviewer xác nhận lại.

## Phụ lục A. Implementation Map — Các file cập nhật

| Nhóm | File |
|---|---|
| Planning runtime | `src/planning/engine.py`, `src/planning/composer.py` |
| Harness revision | `src/harness/dispatch.py` |
| Handoff Web | `web/src/user/pd/decision.tsx` |
| Preview/contract Web | `web/src/user/planning/api.ts`, `current.ts`, `planning.tsx`, `types.ts` |
| Màn Lịch trình | `web/src/user/screens/Plan.tsx` |
| Regression backend | `tests/planning/test_planning_overload_edits.py`, `test_planning_composer.py`; `tests/harness/test_tools.py`, `test_harness_server.py`, `test_overload_browser.py` |
| Regression Web | `web/scripts/test_planning_state.mjs`, `test_overload_ui.mjs` |
| Tài liệu runtime | `docs/PLANNING.md`, `docs/AGENT_HARNESS.md`, `docs/Role_Web_Functional_Design.md` |
| Báo cáo kiểm tra chi tiết | `docs/LUNA_OVERLOAD_THREE_PLANS_IMPLEMENTATION_REPORT.md` |

Danh sách này chỉ là phạm vi của đợt sửa; không nhận toàn `git diff` của checkout là thay đổi của task. Báo cáo này là phần bổ sung để tham khảo khi biên tập §13 và §17 của `TECHNICAL_REPORT.md`.
