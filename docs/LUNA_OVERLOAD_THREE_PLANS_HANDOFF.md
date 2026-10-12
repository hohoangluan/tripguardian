# Bàn giao Luna 6.0: Planning quá tải và ba kế hoạch

Ngày: 2026-10-11. Đây là tài liệu bàn giao công việc, không phải mô tả tính năng đã hoàn thành.

## Phân công đã được người dùng yêu cầu

- **Luna 6.0:** sửa các lỗi được review, hoàn thành implementation backend/frontend, bổ sung regression test và cập nhật tài liệu chính thức.
- **Sol 6.1:** sau khi Luna hoàn thành, kiểm thử độc lập, review tính đúng đắn và đối chiếu yêu cầu. Sol không tiếp tục làm phần implementation đã bàn giao cho Luna. Nếu kiểm chứng thất bại, Sol ghi reproduction và chuyển lại Luna sửa.
- Không xóa file, không kill/dừng tiến trình. Người dùng cho phép các lệnh bash cần thiết ngoài hai việc đó. Vẫn tuân thủ quyền sandbox khi cần chạy ngoài sandbox.
- Không tự triển khai production. Không stage/commit hoặc ghi đè các thay đổi có sẵn của người dùng.

Repo: `/workingspace_aiclub/WorkingSpace/Personal/vannk/tripguardian`. Đọc `AGENTS.md`, `RULE.md` trước khi sửa. Tài liệu tiếng Việt; code, comment, identifier và tên file tiếng Anh. Module khác chỉ được gọi qua public API.

## Yêu cầu đã duyệt

Nguồn ý tưởng: [OVERLOAD_AND_THREE_PLANS_IDEAS.md](OVERLOAD_AND_THREE_PLANS_IDEAS.md). Thiết kế được người dùng duyệt bằng “Agree”: [/tmp/tripguardian-overload-three-plans-design.md](/tmp/tripguardian-overload-three-plans-design.md). Kế hoạch làm việc: [/tmp/tripguardian-overload-implementation-plan.md](/tmp/tripguardian-overload-implementation-plan.md).

Người chọn quá nhiều nơi phải nhận cảnh báo và vẫn được vào Planning để xem ba hướng có lịch, định nghĩa và trade-off:

| Hướng | Định nghĩa | Cái giá chấp nhận |
|---|---|---|
| Tiết kiệm (`low_cost`) | Giảm chi phí ước tính trong các phương án giữ ít nhất `alpha = 0,7` utility của selection | Có thể bỏ nơi đắt hoặc đi xa hơn để tiết kiệm |
| Trải nghiệm tốt nhất (`diverse`) | Đáp ứng mong muốn có bằng chứng, không vội, đa dạng cả chuyến, mới theo gu, đúng giờ và đủ độ vững | Có thể ít nơi hơn, tốn tiền hoặc travel nhiều hơn |
| Gọn tuyến (`least_travel`) | Ưu tiên số nơi, rồi tỷ lệ `visit / (visit + travel)`, rồi utility và ID | Có thể ít đa dạng, visit ngắn hơn |

Ba hướng bật khi ước lượng tải từ 0,8, có xung đột tải hoặc lịch Giữ tất cả không hợp lệ/mong manh. Chuyến khác giữ cách chọn objective hiện có. Không dựng ba lịch khác nhau giả tạo: nếu trùng, ghi rõ. Nếu không tìm được lịch đạt định nghĩa một hướng, hiện hướng đó với lý do và không cho chọn/xác nhận.

`must ⊆ kept ⊆ selection`. Must gồm anchor, locked, priority bắt buộc và nơi người dùng khôi phục khi tối ưu lại. Không tự thêm nơi ngoài selection. Mỗi nơi bỏ phải có lý do và đường khôi phục.

`rho = 0,9` giới hạn tải theo dòng thời gian; tính cả travel, visit, wait, buffer, rest và meal, không tính khoảng trống là tải. Trải nghiệm giữ thời lượng theo pace (`allow_shrink=False`), giới hạn `per_day[pace]` và độ vững tối thiểu Khả thi. Hai hướng khác dùng `per_day_max`; không bỏ must để đạt giới hạn.

Validator hiện có vẫn quyết định tính khả thi. Không nới hard/physical constraint. Ước lượng Decision chỉ nói “có vẻ không đủ”; Planning nêu lỗi thật của lịch Giữ tất cả, không tuyên bố một lần tìm thất bại chứng minh mọi lịch đều bất khả thi.

Giữ tất cả là đối chiếu riêng: timeline, violations, độ vững, giá và travel cùng basis. Nếu baseline thiếu dữ liệu thì delta tương ứng là unknown. Giữ lịch hợp lệ cho người dùng lựa chọn; lịch vi phạm không được xác nhận.

Chuyến dài giữ phân công tuần đã có; chỉ giảm tải tuần cần giảm. Không bỏ nơi ở tuần nhẹ để giải quyết tuần khác.

## Trạng thái bàn giao: chưa hoàn thành tính năng

### Đã sửa và đã có kiểm chứng

**Decision handoff:**

- `src/decision/engine.py`: `_confirmable` dùng chung cho `draft`/`confirm`, cho qua đúng các conflict `time`, `per_day`, `far_areas`, `time_windows`, `budget`. Conflict đóng cửa, hard, relax hoặc check lạ vẫn chặn. Một số conflict tải ước lượng có `physical=True`, nên không mở rộng allowlist chỉ theo cờ này.
- `src/decision/output.py` và `contracts.py`: `utility` từ `Cand.score` thực, `utility_source="decision_score"`; nhận dữ liệu cũ thiếu trường. Không có trường novelty độc lập trong Cand nên không bịa.
- Test public Decision và harness handoff. Test harness này dùng adapter Planning, chưa chứng minh Engine Planning thật tạo được ba hướng.

**Composer ban đầu:**

- File mới `src/planning/composer.py` và `tests/planning/test_planning_composer.py`.
- `schedule_trip(trip, weights=None, *, kept=None, allow_shrink=None)` hỗ trợ tập con.
- `DayCtx.allow_shrink=True` mặc định; `simulate` tôn trọng cờ này; cờ tham gia cache key.
- `Settings.composer`/`config/planning.yaml` có alpha, rho, ngưỡng chặt, per-day caps, giới hạn search và bảng transport rate rỗng.
- `build_variants`/`build_lodging_variants` gọi composer; nhánh lodging còn lỗi phải sửa ở phần dưới.
- Test ngày quá tải trước đây kỳ vọng không có variant đã được cập nhật theo yêu cầu mới: Giữ tất cả vẫn vi phạm, nhưng có hướng trimmed hợp lệ.

### Chưa triển khai

- Engine Planning của ứng dụng chưa gọi composer; session chưa tách plan drops và user drops.
- Chưa có preview edit/stale token/make-room/reoptimize hoàn chỉnh.
- UI vẫn có điều kiện chặn overload và chưa hiện ba hướng mới, dropped places, định nghĩa hoặc trade-off edit.
- Chưa hoàn thành output chốt, lodging cho overload và tài liệu chính thức.
- `tests/planning/test_planning_overload_edits.py` mới chỉ có bản test khởi đầu, chưa RED hành vi: thiếu trong manifest và một giả định sai về shape itinerary. Luna phải sửa test setup rồi xác nhận RED trước implementation.

## Kết quả test đã có, không coi là nghiệm thu toàn tính năng

| Phạm vi | Kết quả | Giới hạn |
|---|---|---|
| Baseline variants + Engine/session | 56 passed | Trước tích hợp composer vào Engine |
| Test mới composer | 7 passed, 8,15 giây | Có overload, must, giá unknown, no-shrink, deterministic và tuần nhẹ |
| Focused Planning cuối cùng | **61 passed, 9,87 giây** | Composer + variants + hai golden + build + route; chưa kiểm UI/Engine edit mới |
| Decision + harness dispatch | 174 passed, 16 skipped, 1 deselected, 4,39 giây | Theo báo cáo Decision; lần sandbox lỗi bind localhost đã được chạy lại ngoài sandbox |

Lệnh focused Planning cuối cùng:

```bash
PYTEST_DISABLE_PLUGIN_AUTOLOAD=1 /tmp/tripguardian-requirements-venv/bin/python /tmp/tripguardian_direct_import.py pytest tests/planning/test_planning_composer.py tests/planning/test_planning_variants.py tests/planning/test_planning_golden.py tests/planning/test_planning_lodging_golden.py tests/planning/test_planning_build.py tests/planning/test_planning_route.py -q --noconftest -p no:cacheprovider
```

Review đã kết luận **cần sửa**. Các test đang xanh chưa bao phủ đủ các lỗi dưới đây.

## Việc Luna cần thực hiện, theo thứ tự

### 1. Sửa năm finding trong composer trước khi tích hợp

1. **Wish theo giờ báo đáp ứng sai.** `_unpin` gỡ pins khỏi Place trong context; `_wishes` chỉ kiểm `unpinned` bên trong điều kiện `fid in p.pins`, nên có thể bỏ qua. `pin_window` chọn một pin cho Place thay vì pin của wish; một visit có thể bị tính đạt cả sunrise và sunset. Khi thiếu sun, all-day fallback không phải bằng chứng đạt wish theo giờ. Dùng requirement/pin gốc, cửa sổ riêng từng feature và unknown khi chưa xác minh được thời gian. Regression: unpinned, hai wish theo giờ cùng Place, thiếu sun.
2. **Utility của nơi thiếu dữ liệu bị mất khỏi mẫu số.** `utilities` đang chỉ duyệt `trip.by_place`; confirmed ở `trip.unplaced` phải vẫn góp utility của selection. Fixture utility 90 cho nơi thiếu dữ liệu và 10 cho nơi xếp được không được báo giữ 100%. Dropped reason phải là lỗi dữ liệu thật, không phải “đắt/xa”. Baseline không đầy đủ phải để delta không tính được là unknown.
3. **Lodging overload bị bỏ qua.** `build_lodging_variants` trả composer sớm trước lấy lodging candidates. Phải giữ workflow candidates, ma trận chung và chấm/kiểm tra trên home/cost basis đúng. Không trả candidates rỗng giả khi nguồn có chỗ ở phù hợp. Regression gọi public lodging builder với overload và fake lodging thật.
4. **Tiết kiệm chưa dùng đúng cost/value.** Bộ chọn hiện xếp unknown-count và tổng vé đã biết; transport/imputation chỉ ở metrics hiển thị. Dùng tiền tiết kiệm trên utility mất và so cost của scheduled trial trước khi nhận. Có regression directed matrix: bỏ điểm trung gian không được tăng transport rồi gọi là tiết kiệm. Giá unknown không thành miễn phí; imputation chỉ khi có dữ liệu cùng loại, total đã biết giữ tách riêng. Không tự đặt transport rate thiếu nguồn.
5. **Thiếu refinement bằng swap có giới hạn.** Sau removal chain chỉ có refill. Thêm trial swap để so wish coverage theo timeline cho Trải nghiệm và count/density cho Gọn tuyến, tie-break tất định. Giới hạn tổng scheduler trials từ config; không hứa tối ưu toàn cục. Với Gọn tuyến, số nơi ưu tiên trước travel tuyệt đối.

Review chi tiết: [/tmp/tripguardian-composer-review.md](/tmp/tripguardian-composer-review.md), diff tại `/tmp/tripguardian-composer-review.diff`.

### 2. Tích hợp Engine và state

Files chính: `src/planning/engine.py`, `session.py`, `scope.py`, `output.py`.

Interfaces composer đang có:

```python
compose(trip, *, force=False, must=(), banned=()) -> dict | None
profile_metrics(trip, sched) -> dict
profile_violations(trip, sched, preset) -> list[dict]
render_profile(trip, sched, preset, *, baseline=None) -> dict
must_places(trip) -> set[str]
```

`None` giữ legacy. Dict có `variants`, `overload`, `keep_all`, `warnings`, `comparison`, `ok`, `back_to_decision`. Variant có `preset`, `status` (`available`/`unavailable`), `definition`, `why`, `kept`, `dropped_by_plan`, `metrics`, `delta_vs_selection`, `violations`; private `_results`, `_ctxs`, `_home` chỉ dùng nội bộ.

- `_build_base` dùng composer khi cần; `_Base`/view/preview xuất overload và keep-all.
- Tách `State.plan_dropped` với user `State.dropped`; thêm restored/protected state. Đổi variant thay phần plan drops, giữ user drops/locks/assignment/khôi phục. Plan drops không ghi profile “không thích” hoặc tính vào `rethink_drops`.
- Sửa `_places_for`, `_members`, `_ctxs_for`, `_compute_results`, `_rebuild_variant` để membership và no-shrink không bị mất khi edit/replay.
- Active metrics/definitions/coverage/deltas phải tính trên lịch đang hiển thị, không dùng số của card cũ sau edit.
- Không cho pick hướng unavailable; confirm kiểm validator và những điều kiện được ghi như bắt buộc trên hướng đang chọn. Phân biệt xem draft vi phạm với xác nhận.
- Restore/swap cho nhận nơi selection bị plan bỏ, ngoài backup pool hiện có; bảo vệ must và locks.
- Undo/redo/restart giữ đúng nguồn drop và lựa chọn. Lodging đổi home kiểm lại lịch nhưng không silent trim.
- Nếu cho chọn Giữ tất cả, dùng một action rõ ràng và chỉ xác nhận khi timeline đạt validator; không giả vờ profile trải nghiệm đã đạt.

### 3. Preview edit và tối ưu lại

Files: `engine.py`, `tools.py`, `server.py`, `scope.py`; harness `server.py`/`dispatch.py` khi cần route.

Contract dự kiến:

```python
Engine.preview_act(sid, action) -> {
    "token": str, "action": dict, "view": dict,
    "delta": dict, "make_room": list
}
```

- Trial trên bản sao session/runtime; không ghi store/history/profile, không I/O/model/crawl lodging. Không để preview tác động caches/timing khiến state thật đổi ý nghĩa.
- Token ràng buộc exact action, phiên bản state và runtime context có ảnh hưởng (home/travel/conditions). Act có `_preview_token` từ chối stale/tampered/action khác; yêu cầu preview lại khi stale.
- Expose qua public Planning Tools và harness có kiểm owner. Có thể dùng read `planning/preview-act?action=<JSON>`; parse/validate ở boundary, giới hạn body/query hợp lý, không mở mutation bypass.
- Preview restore/swap/drop nêu chênh travel/visit/cost/wishes/robustness, violations và confirmability. Người dùng chủ động nhận edit làm draft hỏng vẫn nhìn thấy lỗi, không confirm được.
- Make-room thử tập bỏ nhỏ theo ngân sách tìm kiếm, bảo vệ must/locked/restored/nơi vừa thêm và assignment. Chỉ ghi “nhỏ nhất” nếu đã tìm hết các tập nhỏ hơn; trường hợp khác ghi cách sửa tìm được. Đề xuất phải được user chọn, không tự bỏ.
- `reoptimize`: dùng composer force với must gồm nơi khôi phục/locked, banned gồm user drops; áp lại assignment/day locks qua repair. Trial và replay phải cho cùng kết quả. Đây là thao tác toàn chuyến rõ ràng, không silent reshuffle.

### 4. UI thật của ứng dụng

Files chính: `web/src/user/ui/SelectedBar.tsx`, `screens/Plan.tsx`, `planning/types.ts`, `planning/planning.tsx`, `planning/api.ts`, `pd/types.ts`/`pd/decision.tsx` nếu cần.

- Nút mở Planning dùng cùng conflict allowlist như Decision, không chỉ `feasibility.status`. Giữ cảnh báo needed/available và distinction estimate/validated.
- Ba thẻ hiện definition/why/tradeoff/count/drops/value hoặc wishes/cost unknown/travel/duration loss. Hướng unavailable vẫn có explanation và disabled pick. Overload warning hiện trước thẻ.
- Nếu các hướng cùng lịch thì ghi rõ; không tạo khác biệt giả. Keep-all riêng để đối chiếu.
- Personalised order chỉ từ dữ liệu thật đã có. Budget ưu tiên Tiết kiệm, slow/novelty/wishes ưu tiên Trải nghiệm, packed/max-leg/chuyến ngắn ưu tiên Gọn tuyến. Không đủ dữ liệu thì theo robustness và nói rõ chưa biết ưu tiên.
- Panel preview edit cho restore/swap/drop/reoptimize; apply dùng đúng action/token đã xem. Hiện make-room để chọn riêng. Confirm disabled khi không đạt, server vẫn kiểm độc lập.
- Thanh chênh lệch so selection phải dùng active itinerary. Giữ UX legacy và xử lý revision/session change để response cũ không ghi đè.

### 5. Test và tài liệu trước khi bàn giao lại Sol

Viết test hành vi trước code; chạy RED đúng nguyên nhân rồi GREEN. Không chỉ xóa assertion cũ để suite pass. Khi expectation thay đổi do yêu cầu đã duyệt, vẫn giữ assertion hard constraints/baseline violations.

Regression cần thêm ngoài các finding:

- Public Decision → harness → **Engine Planning thật** tạo ba hướng khi overload, vẫn giữ selection gốc.
- Must/locked không mất; kept subset selection; không trùng visit; mỗi lịch xác nhận được qua validator.
- Alpha không bị giảm lặng lẽ; missing/unknown và impossible must có explanation.
- Experience no-shrink/full dwell, wish verified/timed, diversity, novelty theo gu, độ vững; Routing count trước density.
- Preview không mutation, token stale/tamper, invalid restore/swap không confirm; make-room được validate.
- Switch variant không leak plan drops, giữ user edits; undo/redo và store restart/replay giống kết quả live.
- 98 nơi/14 ngày có hướng trimmed hợp lệ khi must phù hợp; tuần nhẹ không mất nơi để chữa tuần nặng.
- Lodging cost/candidates thực trong overload; thay home không trim âm thầm.
- Same input → same output; cache phân biệt kept/no-shrink/conditions.
- Web type/build và test API/revision liên quan; thử giao diện end-to-end nếu môi trường cho phép.

Sửa tài liệu chính thức tiếng Việt tại `docs/PLANNING.md`, `PLACE_DECISION.md`, `AGENT_HARNESS.md`, `Role_Web_Functional_Design.md` đúng phần bị đổi. Không ghi số test/benchmark chưa chạy. Báo thời gian đo fixture là simulated, không phải tốc độ mạng hoặc lợi ích người dùng đã đo.

## Môi trường test và giữ thay đổi có sẵn

Checkout đang có nhiều dirty changes từ trước task; không coi toàn `git diff` là thay đổi của Luna/Sol. Snapshot source trước task ở `/tmp/tripguardian-overload-baseline` và `/tmp/decision-handoff-baseline`; đối chiếu theo file được giao. `composer.py` và test composer là file mới chưa commit. Không reset/clean/revert toàn repo hoặc xóa lock.

Pytest thông thường đã gặp stall filesystem; direct importer tại `/tmp/tripguardian_direct_import.py` đọc file theo `/tmp/tripguardian-source-manifest.txt`. Thêm đường dẫn tương đối của file `.py` mới vào manifest trước chạy, gồm `tests/planning/test_planning_overload_edits.py`. Đây là workaround cho môi trường, không ship vào source sản phẩm.

`--noconftest` chỉ thích hợp cho những test không cần conftest. Suite dùng fixtures conftest phải chạy với conftest hoặc snapshot giữ nguyên source/config/test cần thiết; không bỏ fixture/assertion để vượt lỗi môi trường. `-p no:cacheprovider` tránh lỗi quota cache từng xảy ra. Test bind localhost có thể cần chạy ngoài sandbox với quyền được cấp.

Lệnh suite mục tiêu khi môi trường cho phép:

```bash
cd /workingspace_aiclub/WorkingSpace/Personal/vannk/tripguardian
PYTEST_DISABLE_PLUGIN_AUTOLOAD=1 /tmp/tripguardian-requirements-venv/bin/python /tmp/tripguardian_direct_import.py pytest tests/planning tests/decision tests/harness -q -p no:cacheprovider
cd web
npm run build
```

## Luna phải bàn giao gì để Sol kiểm thử

Tạo `docs/LUNA_OVERLOAD_THREE_PLANS_IMPLEMENTATION_REPORT.md` gồm:

1. Các file thực sự sửa và từng yêu cầu đã xử lý; interface/API/action/state mới chính xác.
2. Lệnh test đầy đủ, kết quả RED/GREEN, số passed/failed/skipped và môi trường; nếu chưa chạy thì ghi rõ.
3. Năm finding review: reproduction/test mới và cách đã sửa từng finding.
4. Kịch bản UI/manual đã thử, với ID/fixture không chứa dữ liệu nhạy cảm; chưa thử phải ghi rõ.
5. Giới hạn còn lại, feature unavailable cases và lý do; không ghi “hoàn thành” nếu Engine/UI/preview chưa nối.
6. File diff hoặc danh sách baseline dùng để review thay đổi mới, tránh nhầm dirty changes cũ.

Sau khi có báo cáo Luna, **Sol 6.1** đọc code và chạy lại kiểm chứng độc lập: focused regression trước, suites bị ảnh hưởng và web build; đối chiếu từng tiêu chí trên. Sol gửi lỗi có test/reproduction cho Luna, rồi kiểm chứng lại phần đã sửa. Chỉ kết luận hoàn thành khi đường đi thật của ứng dụng hoạt động và các kiểm chứng cần thiết đã pass; giữ nguyên phân công implementation thuộc Luna.
