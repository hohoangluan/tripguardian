# Bàn giao tiếp tục chuẩn hóa Corpus

Ngày cập nhật: 2026-10-15

## Mục đích

Tài liệu này ghi lại trạng thái thực tế sau khi triển khai thiết kế trong
`docs/superpowers/specs/2026-10-14-corpus-normalization-design.md`, các phần còn dang dở,
và thứ tự công việc cho agent tiếp theo. Không xem migration hoàn tất về mặt phát hành cho
đến khi xây dựng được release đầy đủ và kích hoạt release đó theo cơ chế atomic.

## Trạng thái tiếp tục mới nhất (2026-10-15)

Phần này thay các điểm dừng cũ bên dưới. Người dùng đã giao Codex sửa contract RAG rồi
nối ba module; phạm vi cuối là viết hai MD, bảo đảm RAG hoạt động rồi dừng. Không publish,
restart harness hoặc regenerate Web trong đợt này. `docs/TRIP_UNDERSTANDING_QA.md` do
người dùng sửa, không ghi đè.

- Contract RAG đã pin release thực, kiểm binding/scope/eligible, exact serving evidence và
  observation; index giữ unserved span hợp lệ nhưng loại claim fail normalization/judge.
- Harness chia sẻ một RetrievalEngine theo binding cho Trip, Decision, Planning. Trip tìm
  tên qua public Corpus và cues qua hybrid retrieval; ảnh/similar giữ visual adapter.
  Decision có evidence read qua HTTP và Agent context bounded; Planning proposal nhận
  binding và serving evidence bounded. Semantic không thay hard/physical validator.
- Decision draft/confirm recheck corpus lodging selected/booked sau rebase; Planning cho đọc
  lodging thay thế khi selection hiện tại fail, giữ guard create/preview/confirm.
- Full suite trước wiring cuối: **1.997 passed, 195 skipped, 12 deselected**, exit 0;
  `logs/run/corpus-continuation-tests.{status.json,log}`. Sau wiring: focused **33 passed**;
  adjacent **30 passed, 3 skipped** (không cộng suite chồng lắp).
- Rebuild **success**, release `r-f4f37dcb1a5d89ca04da70cb-ea26fde5`, normalization
  `f4f37dcb1a5d89ca04da70cb`: 3.208 eligible ID, 29.820 photo row, 370.303 span row,
  246.872 served, 1.041 styled. Snapshot `20261014T172322`, index
  `20261014T172357-ff124e58`; artifact/source/fingerprint kiểm đạt, model/network=0,
  `publish=false`. Kết quả: `logs/run/corpus-continuation-build.{status,report}.json`.
- Bộ cuối sau sửa CUDA/fixture: **185 passed, 6 skipped**, exit 0;
  `logs/run/corpus-continuation-rag-tests.{status.json,log}`. Review cuối xác nhận scope/
  binding/evidence/validator; lỗi CUDA đã có regression và graceful unavailable.
- Smoke release thật **pass, exit 0**: Trip tìm Zin’s Cafe → Decision select/confirm →
  Planning variant/confirm giữ ID/activity/binding; evidence giữ đúng serving value,
  observation/source/release và semantic có kết quả đúng scope. Một reader được inject
  vào cả ba factory. Coverage: photo **1.638/3.208**, span **1.691/3.208** (đếm nơi).
  Model/live được stub, model/network=0; chưa đo chất lượng embedding hoặc call LLM thật.
  Report: `logs/run/corpus-continuation-smoke.report.json`, script/log cùng tiền tố.
- **Dừng tại đây theo yêu cầu người dùng.** `data/releases/current` chưa tồn tại;
  chưa publish/restart/export Web. Không coi kiểm chứng code/stub là runtime đã deployment.
- Hai tài liệu yêu cầu: `ONLINE_MODULES_RAG_UPDATE_IDEAS.md` và
  `../NORMALIZED_CORPUS_RECHECK.md`. Audit strong/gold và ý nghĩa Gemma đã đối chiếu trong
  báo cáo; không nới matcher hoặc gọi model để hợp thức hóa claim.

Các mục từ đây là lịch sử bàn giao ngày 2026-10-14; số test, quyền giữ file và bước activation
cũ không ghi đè phạm vi mới nhất phía trên.

## Điểm tiếp tục: ba module online (2026-10-14)

**Code đã cập nhật, chưa hoàn tất phát hành/kiểm chứng cuối.** Người dùng đã cho phép tiếp tục
Trip Understanding, Decision và Planning; Claude giữ RAG. Yêu cầu mới nhất là ghi bàn giao
để phiên sau tiếp tục. Dừng sửa code và activation sau khi lưu tài liệu này.

### Đã làm

- Trip Catalog đọc serving records thay intel: membership, identity, giờ, feature/context,
  evidence cùng region. UNCERTAIN/missing/distribution mâu thuẫn không tăng count; OUTDATED
  giữ status/provenance. Looks lọc catalog ∩ within cả truy vấn, kết quả, clusters/photos/similar.
- Public `corpus.releases.Binding`, `bind`, `resolve_binding` giữ release ID, region, manifest
  hash và snapshot/index version; kiểm đường dẫn/manifest/artifact hash, không fallback khi
  release lỗi. Legacy reader mở version đã pin, không đọc lại pointer sau khi khởi tạo.
- Factory mặc định của cả ba module capture binding; caller có thể truyền explicit binding.
  `decision.Data.load` nhận root/version; `snapshot.shared` nhận pinned version. Trip Looks
  nhận index version cho delayed thread; thiếu index trong binding giữ unavailable.
- Harness Journey lưu binding và chọn bộ Tools theo journey cho restore/read/advance/rebase/
  copy/rollback. SearchInput, Trip snapshot, DecisionOutput, PlanOutput mang binding;
  adapter từ chối binding lệch. Journey cũ null giữ legacy, không tự suy release lịch sử.
- BudgetIntent giữ amount VND/scope/nguồn/evidence của amount và scope, guessed provenance.
  Scalar vẫn VND/người/ngày; `trip.group_budget` quy tổng nhóm/chuyến khi đủ chiều cần thiết.
  Thiếu dữ liệu quy đổi không làm mất amount gốc.
- Lodging dùng public requirements cho eq/ne/accommodation/unknown policy; physical,
  suitability và fit unknown fail-closed. Không dùng giá/người làm giá/phòng/đêm; cap dùng
  tổng nhóm/chuyến và explicit `trip.nights`, không suy occupancy/availability.
- Decision kiểm requirement khi chọn corpus lodging. Planning kiểm corpus lodging đã chọn/
  booked trước create/preview/prepare và kiểm lại lodging hiện tại khi confirm; corpus lodging
  thiếu identity/record bị từ chối. Address ngoài corpus chưa có contract safety riêng.
- Preview cache bỏ log/wishlist/feasibility phụ, giữ input feasibility thực sự composer đọc
  và dependency context/activity/requirement/config/live/record/release. Preview hit không
  mutate shared base; create rebind log sau pop ownership. Factory verified release truyền
  `immutable_records_version=manifest_sha256`; Engine mutable vẫn hash records.
  `live_dependency_version` cho caller invalidate callback data; thiếu token dùng TTL 900 giây.
- Đã sửa docs chính thức: TRIP_UNDERSTANDING, PLACE_DECISION, PLANNING, AGENT_HARNESS, CORPUS.
  Dev log và rà soát ARCHITECTURE/README còn cần hoàn tất.

### File chính

- `src/trip/{__init__,api/tools,domain/state,domain/compile,domain/budget}.py`,
  `src/trip/infrastructure/{catalog,looks}.py`.
- `src/decision/{pipeline,tools,contracts,output,engine}.py`.
- `src/planning/{tools,lodging,engine,output}.py`.
- `src/harness/{contracts,dispatch,__main__}.py`.
- `src/corpus/releases/{binding,__init__}.py`, `src/corpus/snapshot/read.py`.
- Regression mới: `tests/trip/test_budget_handoff.py`, `tests/harness/test_corpus_binding.py`,
  `tests/harness/test_bound_module_tools.py`, `tests/normalization/test_online_binding.py`,
  `tests/planning/test_planning_normalized_semantics.py`, `tests/decision/test_lodging_requirements.py`.
  Đã mở rộng reader tests và sửa fixture lodging cũ để có bằng chứng physical hợp lệ;
  không nới constraint để test pass.

### Kiểm chứng đã ghi nhận

Các suite chồng lắp, không cộng số test:

- Trip reader: 380 passed, 3 deselected, trước bổ sung pin version cuối.
- Harness + Decision + Trip: 723 passed, 133 skipped, 4 deselected, trước guard selected
  lodging/pin version cuối.
- Planning suite: 620 passed, trước guard selected lodging. Sau guard và cache fixes:
  nhóm lodging/engine/consistency/regression **95 passed**.
- Pin reader + binding regression: **21 passed** sau sửa delayed index/snapshot.
- Kiểm gần nhất: Decision lodging/engine + Harness + Trip normalized readers + online binding:
  **168 passed, 133 skipped** trong 38,18 giây.
- `git diff --check` pass trước cập nhật handoff cuối; cần kiểm lại sau ghi tài liệu.
- Cache-key benchmark trên 3.208 records: full fingerprint khoảng 0,91–1,22 giây;
  immutable token khoảng 0,50 ms. Chỉ là key latency, không phải end-to-end/RAG/model.

Full `.venv/bin/python -m pytest -q` chạy ngoài sandbox, unified exec session **27017**.
Lần poll gần nhất trước ghi handoff còn chạy khoảng 28%, chưa có kết quả cuối. Không có
logfile riêng. Phiên sau thu output nếu session còn, hoặc kiểm process trước rerun để tránh
job trùng; không ghi full suite pass khi chưa có exit code/output cuối.

### Dữ liệu: chưa activation

Đã chạy lại public `corpus.releases.validate` trên
`r-761a156dfffa4bc5d8bbc30b-6481f4ed`: **pass**, 3.208 eligible IDs, 3.326 artifact.
Sandbox timeout 45 giây khi mở LanceDB; cùng lệnh ngoài sandbox pass. Không crawl/model,
sinh vector mới, sửa nguồn hoặc rebuild release trong đợt online này.

Pointer kiểm trước ghi handoff:

```text
data/releases/current   chưa tồn tại
data/snapshot/current   20261013T201524
data/index/current      20261013T025416
```

**Chưa publish, restart harness, export/split lại Web snapshot.** Runtime đang chạy chưa
được chứng minh dùng corpus chuẩn hóa mới; factory mới chỉ nhận release active khi khởi tạo.

### Việc tiếp theo, theo thứ tự

1. Thu kết quả full suite session 27017; kiểm process trước rerun. Re-review đã gửi agent
   `online_review`, report tạm `/tmp/tripguardian-online-review.md` có thể được cập nhật.
   Không nới test/golden để che failure.
2. Review task diff. Ba finding đầu đã sửa: default factory binding null, preview shared
   mutation, delayed legacy reader đổi pointer. Xác nhận re-review cuối, xem coverage copy
   journey sau restart/release. **Decision.confirm chưa tự recheck lodging sau rebase hard
   filters**; Planning hiện chặn đầu vào này. Cần kiểm guard Decision confirm/draft để lỗi
   xuất hiện tại đúng module.
3. Chốt các giới hạn: legacy null không có lineage lịch sử xác minh; address lodging unknown
   safety; tổng chi phí vé/người và phòng/đêm chưa có room occupancy/capacity contract đầy đủ.
   Trần lodging là tham khảo, không chứng minh đủ phòng/tiền cho nhóm. Redesign ngày/buffer
   qua nửa đêm chưa được triển khai trong đợt này.
4. Sau test/review sạch, activate release hoàn chỉnh bằng public API atomic:

   ```bash
   PYTHONPATH=src .venv/bin/python -c 'from pathlib import Path; from corpus.releases import publish; m=publish("r-761a156dfffa4bc5d8bbc30b-6481f4ed", Path("data")); print(m["release_id"], len(m["eligible_ids"]))'
   ```

   LanceDB đã timeout trong sandbox; dùng escalation đúng cơ chế nếu cần. Người dùng đã cho
   phép cập nhật ba module/data; không hỏi lại scope đã cho phép. Giữ release cũ/standalone
   artifacts cho restore/rollback; không publish staging thiếu manifest.
5. Smoke dữ liệu thật cùng binding cho Trip/Decision/Planning, đối chiếu membership snapshot/
   index/serving; chọn nơi thật → handoff → confirm giữ selection/activity/release. Stub
   model/live, không tự warm embedding/crawl/network. Sau activation chạy
   `python web/scripts/export_snapshot.py --view both`; kiểm workflow split snapshot Web.
   Các bước này chưa chạy trong phiên hiện tại.
6. Hoàn tất dev log, ARCHITECTURE/README nếu contract còn lệch; sửa status proposal/phối hợp
   Claude. Claude giữ public retrieval/evidence/semantic API (RAG). Grounded directions/
   counterfactual câu mềm mới, summary/time redesign và retrieval benchmark chưa được Codex
   triển khai ở đợt này; không đánh dấu bước B/D hoàn tất.
7. Chạy kiểm cuối đủ cho thay đổi và `git diff --check`, ghi kết quả thật/activation. Plan
   tạm chỉ xóa theo RULE §0.1 sau khi thực hiện xong và gộp giá trị vào docs chính thức.

Workspace có nhiều thay đổi người dùng/Claude từ trước; chưa commit/merge/push. Không reset,
checkout/clean hoặc stage toàn repo. Baseline riêng 20 file trước task:
`/tmp/tripguardian-online-baseline`; diff tạm `/tmp/tripguardian-online-review-final.diff`.
Các report `/tmp` hỗ trợ review; tài liệu này là điểm tiếp tục nếu chúng không còn.

## Trạng thái hiện tại

Phần chuẩn hóa dữ liệu đã chạy xong trên toàn bộ corpus. Hệ thống hiện có các lớp chính sau:

| Phần | Vị trí chính | Trạng thái |
|---|---|---|
| Schema và validation của normalized corpus | `src/corpus/normalize/schema.py` | Đã triển khai |
| Pipeline chuẩn hóa | `src/corpus/normalize/run.py` | Đã triển khai và chạy toàn bộ corpus |
| Release build và projection | `src/corpus/releases/run.py`, `src/corpus/releases/projection.py` | Build thật đã hoàn tất và validate ngoài sandbox; chưa publish |
| Aggregate, serving, snapshot và index | `src/corpus/aggregate`, `src/corpus/serving`, `src/corpus/snapshot`, `src/corpus/index` | Đã nối normalization provenance và kiểm tra fail-closed |
| CLI, pack/export và Web snapshot | CLI corpus, `scripts/pack_data.py`, Web snapshot worker/store | Đã cập nhật theo release layout |
| Test normalization/release/index/projection | `tests/normalization/` | Đã bổ sung |

Các thay đổi nằm trong worktree đang có nhiều sửa đổi khác của người dùng. Không reset, clean,
checkout hoặc hoàn tác các file không thuộc công việc này. Nhánh được quan sát gần nhất là
`fix/scoped-trip-requirements`.

## Kết quả migration toàn bộ corpus

Normalization đã hoàn thành với dữ liệu sau:

- Normalization ID: `761a156dfffa4bc5d8bbc30b`
- Manifest: `data/normalization/761a156dfffa4bc5d8bbc30b/manifest.json`
- Số file đầu vào: 7.703
- Số file đủ điều kiện: 7.703
- Số claim được giữ lại: 1.473.473
- Số canonical inventory ID: 3.280
- Số legacy version file: 861
- Số source reference: 42.399
- Thời gian chạy: 417,62 giây

Schema validation đã quét toàn bộ document sinh ra và ghi nhận 0 document không hợp lệ.

Các issue được ghi nhận trong normalization manifest:

| Loại issue | Số lượng | Ý nghĩa |
|---|---:|---|
| `classification_conflict` | 5 | Claim có tín hiệu phân loại xung đột, cần giữ để audit |
| `invalid_source_span` | 7.572 | Span nguồn không hợp lệ; claim tương ứng không được dùng như bằng chứng hợp lệ |
| `unsupported_source` | 7 | Nguồn chưa nằm trong loại được pipeline hỗ trợ |

Phân bố issue bị loại theo nguồn, lấy từ lần kiểm tra read-only:

- `gmaps_review`: 2.233
- `tiktok_segment`: 5.326
- `tiktok_frame`: 7
- `official_page`: 13

Một số feature có nhiều issue nhất: `food_quality` 967, `scenic_view` 526,
`local_specialty_food` 457, `service_attitude` 409, `heritage_architecture` 391,
`nature` 376, `photo_spot` 312, `value_for_money` 288, `drink_quality` 261,
`setting` 234 và `service_quality` 231.

## Release build hoàn tất (22:27, 2026-10-14)

- Release: `r-761a156dfffa4bc5d8bbc30b-6481f4ed`.
- Manifest: `data/releases/r-761a156dfffa4bc5d8bbc30b-6481f4ed/manifest.json`.
- Eligible serving/index IDs: 3.208; snapshot/index/projection/artifact hashes đã được release
  builder validate trước khi staging đổi thành release hoàn chỉnh.
- Semantic artifact: 29.820 photo row, 205.045 span row, 1.041 nơi có style; metadata index có
  đủ 3.208 ID. Coverage photo/span/style vẫn partial, tách 1.510 stay và 1.698 non-stay.
- Source hashes không đổi; không model/network call. Fingerprint config/code so lại sau build:
  không có dependency đổi trong lần chạy.
- Chạy ngoài sandbox: smoke LanceDB trong sandbox timeout tại connect; cùng smoke ngoài sandbox
  thành công. Dùng normalization hiện có, không chạy lại crawl/model hoặc sửa dữ liệu nguồn.
- `publish=false`; `data/releases/current` chưa có, pointer legacy vẫn giữ nguyên. Không restart
  harness vì release mới chưa được activate.
- Job đã kết thúc; status/log: `logs/run/corpus-normalization-background.status.json` và `.log`.

Đợt triển khai online mới và điểm dừng nằm ở §Điểm tiếp tục phía trên; release vẫn chưa activation.

## Lần build bị chặn trong sandbox (baseline)

Lần rebuild release đầy đủ đã tạo staging tại:

`data/releases/.staging-r-761a156dfffa4bc5d8bbc30b-71f611de/`

Staging này đã có 3.280 file intelligence và `serving/places.json`. Snapshot bắt đầu được tạo tại
`snapshot/20261014T105648/`, nhưng chưa có snapshot manifest, index hoàn chỉnh hoặc release
manifest. Không publish hoặc đổi active pointer sang staging này.

Build bị treo khi kết nối/ghi LanceDB. Một smoke test LanceDB chỉ có một row trong `/tmp` cũng
treo tại `lancedb.connect()`. Stack trace sau 30 giây cho thấy main thread chờ
`concurrent.futures.Future.result` trong `lancedb/background_loop.py`, còn background thread
chờ trong asyncio selector. Cả hai process đã được ngắt để tránh tiếp tục treo.

Log liên quan:

- `logs/run/corpus-normalization-rebuild.log` có thể thiếu phần cuối do stdout buffering và việc ngắt process.
- `logs/run/corpus-normalization-online-regressions.txt` chứa output đầy đủ gần nhất của 11 test fail.

Active release pointer không được thay đổi trong lần chạy này. Baseline quan sát lúc bắt đầu là
snapshot `20261013T201524` và index `20261013T025416`; agent tiếp theo phải đọc lại pointer hiện
tại trước khi làm gì với release.

## Kết quả kiểm tra đã ghi nhận

Baseline trước khi xử lý các failure bên dưới:

- Corpus-related suite: 192 passed, 28 cảnh báo deprecation từ LanceDB.
- Boundary suite: 128 passed.
- Web `npm run build`: passed, có cảnh báo Vite config/chunk.
- `git diff --check`: passed tại thời điểm kiểm tra.
- `compileall`: passed tại thời điểm kiểm tra.
- Online suite rộng: 1.295 passed, 11 failed, 127 skipped, 4 deselected trong 452,29 giây.
- Chạy lại riêng failure bằng `--lf`: 11 failed, 60 deselected trong 13,26 giây.

Lệnh corpus suite đã dùng:

```bash
.venv/bin/python -m pytest tests/normalization tests/index tests/aggregate tests/serving tests/review tests/judge tests/snapshot tests/web -q
```

Lệnh boundary suite đã dùng:

```bash
.venv/bin/python -m pytest tests/planning/test_planning_boundaries.py tests/live/test_boundaries.py -q
```

Lệnh online suite đã dùng:

```bash
.venv/bin/python -m pytest tests/trip tests/decision tests/planning tests/harness -q
.venv/bin/python -m pytest tests/trip tests/decision tests/planning tests/harness --lf --tb=short -q
```

## Chi tiết 11 test failure được bàn giao

Trạng thái xử lý hiện tại nằm ở §Kiểm tra và xử lý 11 failure; các hiện tượng bên dưới là
bằng chứng của lần chạy baseline.

Không sửa các test này bằng cách nới physical constraint, bỏ validation, cập nhật golden mù,
hoặc khôi phục API nội bộ đã lỗi thời. Cần xác định contract hiện tại rồi sửa fixture hoặc code
đúng tại ranh giới public API.

### 1. Photo vẫn truyền payload nằm sau JPEG

Test:

`tests/trip/test_vibes.py::test_photo_processing_receives_only_reencoded_pixels`

Hiện tượng: test nối `HIDDEN_PAYLOAD...` vào cuối byte JPEG. Dữ liệu downstream vẫn nhận được
payload này, nên assertion tại khoảng dòng 212 fail.

Điểm code liên quan: `src/trip/api/engine.py::_image()` khoảng dòng 965 chỉ base64-decode,
kiểm tra kích thước byte và gọi `Image.verify()`, sau đó vẫn truyền byte gốc. Hàm
`src/trip/infrastructure/images.py::sanitize_photo()` đã có logic decode rồi re-encode JPEG chỉ
từ pixel, nhưng chưa được gọi trên đường xử lý này.

Việc tiếp theo: trace đường public API nhận ảnh, đưa sanitize vào đúng boundary trước model và
embedder, rồi chứng minh downstream chỉ nhận ảnh re-encode. Không làm yếu assertion của test.

### 2. Ảnh có quá nhiều pixel không bị từ chối sớm

Test:

`tests/trip/test_vibes.py::test_photo_with_excessive_pixel_count_is_refused_before_model_or_embedder`

Hiện tượng: PNG 4.100 x 4.100, tương đương 16.810.000 pixel, vẫn đi tiếp và phát progress thay
vì chỉ trả `BAD_PHOTO`. Model/embedder đáng lẽ không được gọi.

Điểm code liên quan: `_image()` kiểm tra byte size nhưng chưa kiểm tra pixel count.
`sanitize_photo()` có `max_pixels` mặc định 16.000.000 lấy từ `config/security.yaml`.

Việc tiếp theo: dùng cùng một giới hạn bảo mật tại entry boundary, fail trước mọi model/embedder,
và giữ lỗi public ổn định là `BAD_PHOTO`.

### 3. Golden của trip variants không còn khớp

Test:

`tests/planning/test_planning_golden.py::test_the_variants_of_the_sample_trip_match_the_golden_file`

Fixture chính: rời lúc 20:00, ngân sách 1,5 triệu, ba địa điểm phía nam có weather exposure,
xác suất mưa 0,2/0,8. Output thực tế cho thấy `least_travel` có score `[30, 30.0]` và
`weather_robust` có score `[0.6, 30.0]`, nhưng toàn bộ cấu trúc không khớp golden.

Việc tiếp theo: tạo structural diff đầy đủ giữa actual và golden, xác định thay đổi đến từ score,
thứ tự, backup hay schedule. Chỉ cập nhật golden nếu contract mới được xác nhận là đúng.

### 4. Golden của lodging variants không còn khớp

Test:

`tests/planning/test_planning_lodging_golden.py::test_the_lodging_variants_of_the_sample_trip_match_the_golden_file`

Fixture chính: chuyến ba ngày, ngân sách 2 triệu, stay `h0` ở phía nam, rating 4,6, 30 voices,
giá 280.000 dưới cap 300.000. Output thực tế có `least_travel` score `[15, 15.0]`, nhưng variants
không khớp golden.

Việc tiếp theo: so sánh đầy đủ lodging/time/price/objective/backups và kiểm tra vì sao thứ tự hoặc
nội dung variant đổi. Không cập nhật golden chỉ để test xanh.

### 5. Variant không vừa số ngày vẫn không bị loại

Test:

`tests/planning/test_planning_variants.py::test_a_variant_that_does_not_fit_the_days_is_dropped_and_named`

Fixture chính: đến lúc 11:00, `max_leg=10`, không có `leave_at`, địa điểm phía nam bị ướt,
xác suất mưa 0,9 và config tùy chỉnh yêu cầu hai bữa ăn.

Expected chỉ có `least_travel`; actual vẫn có `least_travel`, `diverse` và `low_cost`. Các assertion
về warning phía sau chưa chạy tới.

Việc tiếp theo: trace feasibility theo ngày, objective construction và dedup/drop reason. Variant
không khả thi phải bị loại và nêu đúng tên/reason; không nới physical constraint.

### 6. Harness overload không còn câu hỏi meal đang mở

Test:

`tests/harness/test_dispatch.py::test_real_decision_overload_can_preview_and_advance_without_losing_selection[file]`

Hiện tượng: khi trả lời qid `meal:P0` bằng chip `no`, code ném
`ActionError: no open question 'meal:P0' with chip 'no'` tại `curation.py` khoảng dòng 123.

Việc tiếp theo: đọc public pending-question contract sau khi selection được thiết lập. Sửa fixture
nếu qid/chip cũ không còn hợp lệ, hoặc sửa hành vi nếu hệ thống làm mất một câu hỏi đáng lẽ còn
mở. Giữ nguyên guard chống trả lời câu hỏi không tồn tại.

### 7. Harness handoff mất ngay ở bước trả lời meal

Test:

`tests/harness/test_tools.py::test_real_decision_and_planning_tools_preserve_selection_on_handoff[file]`

Hiện tượng: cùng `ActionError`, lần này với `meal:place-1` và chip `no` tại khoảng dòng 36, trước
khi test tới các assertion về handoff.

Việc tiếp theo: dùng cùng kết luận về pending-question contract ở failure 6, sau đó tiếp tục kiểm
tra rằng selection được giữ nguyên qua handoff.

### 8. Không tìm được planning variant có thể confirm

Test:

`tests/harness/test_tools.py::test_real_overload_handoff_offers_profiles_and_confirms_only_valid_drafts[file]`

Hiện tượng: `StopIteration` tại khoảng dòng 74 khi test tìm một variant có thể confirm sau overload
16 địa điểm và đã chọn hotel.

Việc tiếp theo: in/đọc violations và confirmability của từng draft để xác định constraint nào làm
tất cả variant không hợp lệ. Không ép variant thành confirmable, bỏ validator hoặc làm mất selection.

### 9. Test suggestion reader dừng trước phần revision/snapshot

Test:

`tests/harness/test_tools.py::test_real_planning_suggestion_read_preserves_snapshot_and_tags_journey_revision[file]`

Hiện tượng: cùng lỗi setup `meal:place-1`, nên test chưa tới hành vi suggestion reader.

Việc tiếp theo: sửa setup theo public pending-question contract. Sau đó vẫn phải giữ các assertion
về journey revision, session/token/status và tính bất biến của snapshot.

### 10. Test preview-act read-only dừng trước phần token

Test:

`tests/harness/test_tools.py::test_real_planning_preview_act_is_read_only_and_returns_a_bound_token[file]`

Hiện tượng: cùng lỗi setup `meal:place-1`, trước khi kiểm tra preview-act.

Việc tiếp theo: sửa setup dùng contract hiện tại, rồi xác nhận token/action/dropped draft được bind
đúng và snapshot gốc không bị thay đổi.

### 11. Harness còn import API agent đã lỗi thời

Test:

`tests/harness/test_tools.py::test_real_trip_compiles_clues_and_harness_advances_with_a_scripted_agent[file]`

Hiện tượng: `ImportError: cannot import Assistant, Call from trip.agent` tại khoảng dòng 165.

`trip.agent` hiện export contract `Chat`, `AgentError`, v.v. Loop hiện tại dùng contract
`AIMessageChunk`; code `Assistant`/`Call` chỉ còn xuất hiện trong phần backup/comment cũ.

Việc tiếp theo: cập nhật scripted fixture theo public `Chat`/tool-call contract hiện tại. Không deep
import và không khôi phục API cũ chỉ để thỏa test.

## Kiểm tra và xử lý 11 failure (2026-10-14)

Đã tái hiện đủ 11 failure trước khi sửa. Nhóm test chứa các failure đã đạt 77 passed,
30 skipped; nhóm kiểm bổ sung về chỗ ở / lock / assignment / replay / undo và cache đạt
86 passed, 10 skipped. Boundary suite: 128 passed. PostgreSQL bị skip vì chưa có
`TEST_DATABASE_URL`; các kết quả này chưa đại diện cho backend PostgreSQL.

Kiểm chứng cuối toàn bộ Trip/Decision/Planning/Harness: **1.309 passed, 127 skipped,
4 deselected trong 315,92 giây**. Chạy ngoài sandbox vì asyncio thread shutdown bị treo
trong sandbox; nhóm agent-loop độc lập ngoài sandbox đạt 21 passed. `compileall` cho các
file Python đã sửa và `git diff --check` đều pass. Review phát hiện thêm nguy cơ bỏ nơi locked /
assigned khi đổi thẻ sau recompose; đã sửa và kiểm cả hai trường hợp, phương án vi phạm
`profile_load` vẫn bị từ chối chọn. Không còn failure trong suite này.

| Failure | Nguyên nhân đã kiểm tra | Xử lý |
|---|---|---|
| 1–2 | `_image()` bỏ qua sanitizer, truyền byte gốc và không giới hạn pixel | Gọi `sanitize_photo()` trước mọi model/embedder; lỗi decoder hoặc decompression bomb trả `BAD_PHOTO` |
| 3–4 | Golden còn bữa trưa/tối và visit ăn 60 phút; config hiện dùng 90 phút, metrics có `meal_cost_unknown` | Structural diff chỉ ra thời lượng và các trường phụ thuộc; cập nhật golden theo contract hiện tại |
| 5 | Fixture có điểm meal bị chia ngày riêng; baseline chuyển sang nhánh overload/fragile | Dùng năm visit thường ở trung tâm, đến 10:00 và hai bữa cấu hình để kiểm đúng nhánh loại objective; giữ `max_leg=10` và assertion warning |
| 6–7, 9–10 | Decision suy ý định café là `coffee`, không còn mở câu hỏi `meal:*` | Bỏ answer lỗi thời khỏi setup; kiểm activity ở handoff, giữ assertion selection/revision/snapshot/token |
| 8 | Thẻ sau đổi chỗ ở chỉ xếp lại tập con cũ; các draft vượt giới hạn spare time 7/11 phút | Recompose draft theo neo mới khi chưa có global override; giữ nguyên Decision selection, kiểm validator và regression replay/undo |
| 11 | Scripted fixture dùng `Assistant`/`Call` đã bỏ | Dùng `AIMessageChunk` và `tool_call_chunks` theo contract `Chat`; phát delta qua `on_say` |

Đối chiếu golden: trip có 330 phút bữa tự chọn, 5 khoản giá bữa chưa biết; lodging có
450 phút, 7 khoản chưa biết. Visit `r1` dài 90 phút. Không thay giờ mở, giá đã biết,
score mục tiêu, selection hay validator để làm test pass.

Release chưa được kích hoạt: `data/releases/current` chưa tồn tại; pointer legacy vẫn là
snapshot `20261013T201524` và index `20261013T025416`. Không sửa staging hay dữ liệu corpus.

Phần online normalization cần thảo luận trước khi triển khai vẫn theo spec tổng §6:
pin một release cho journey và ba module; contract budget/time có đơn vị và provenance;
hard constraint cho stay; cache Planning theo input ngữ nghĩa và dependency version.
Người dùng đã chọn hoàn tất các contract này trước, chưa mở rộng sang redesign agent/sản phẩm.

Các điểm đã xác nhận bằng code để thảo luận:

| Phạm vi | Contract còn thiếu |
|---|---|
| Chung cho journey và ba module | `Journey` chưa lưu release ID; cần restore/handoff theo cùng release và policy rõ cho phiên legacy |
| Trip Understanding | `compile_search_input()` xuất scalar budget/người/ngày; chưa bàn giao đầy đủ scope, đơn vị và provenance của phép đổi. `day_window()` so giờ dạng chuỗi, cần kiểm ngày/qua nửa đêm |
| Decision | Cần dùng eligible/canonical ID từ release đã pin và giữ ý định hoạt động, applicability, unknown policy trong handoff |
| Planning | `lodging.sieve()` chỉ kiểm `ne`, giữ unknown; `price_cap()` coi scalar budget như tổng chuyến. Cần contract đơn vị và kiểm stay qua API `requirements`. Cache preview phải tách input ngữ nghĩa khỏi log và xét dependency version |

Đề xuất thảo luận theo thứ tự contract xuyên module: release pinning → budget/time → stay/cache.
Mỗi contract được kiểm handoff/restore trước khi chuyển sang phần tiếp theo. Cách đổi đồng loạt
cả ba module ít bước chuyển tiếp hơn nhưng khó đối chiếu lỗi và rollback hơn.

## Thứ tự công việc đề xuất cho agent tiếp theo

1. Đọc `RULE.md`, spec normalization và implementation plan hiện có trước khi sửa.
2. Xác nhận active pointer; dùng release hoàn chỉnh `r-761a156dfffa4bc5d8bbc30b-6481f4ed`,
   không dùng staging cũ thiếu manifest.
3. Kiểm manifest/quality report và chạy corpus suite cần thiết ngoài sandbox; LanceDB smoke ngoài
   sandbox đã pass. Không chạy lại normalize/crawl/model chỉ để lấp coverage partial.
4. Thảo luận proposal RAG / contract online; quyết định activation sau kiểm chứng. Job hiện đã
   thành công nhưng không tự publish theo phạm vi đã chạy.
5. Nếu activate khi chưa có journey pinning, restart toàn harness để các module nạp cùng release;
   không restart chỉ vì một build `publish=false` hoàn tất.
6. Chạy corpus, boundary và online suites sau activation. 11 failure cũ đã được xử lý; reader
   factory/CLI cùng root được kiểm riêng với 29 test liên quan.
7. Kiểm online chỉ đọc release, rồi triển khai contract đã được thảo luận theo proposal; giữ
   selection, unknown và physical constraints qua handoff/restore.
8. Cập nhật tài liệu vận hành/dev log tiếng Việt và dọn spec/plan tạm khi phạm vi đã thực hiện xong.

## Các bất biến cần giữ

- Offline ghi Place Intelligence; online chỉ đọc Place Intelligence.
- Không có bằng chứng phải là `unknown`, không suy diễn thành `false`.
- Hard constraint và physical constraint phải fail-closed.
- Module chỉ giao tiếp qua public API trong `__init__.py`.
- Manifest/provenance phải trỏ đúng normalization root. Nếu intelligence khai báo normalization ID
  nhưng manifest tương ứng không tồn tại, index/release phải fail-closed.
- Release chỉ được kích hoạt sau khi toàn bộ artifact và manifest đã hợp lệ.

## Ghi chú về thay đổi provenance cuối cùng

Review gần nhất phát hiện index trước đó chỉ tìm normalization manifest trong source root. Phần này
đã được sửa bằng tham số `normalization_root`; release builder truyền `normalized.root`. Nếu summary
khai báo normalization ID nhưng manifest bị thiếu, build hiện phải fail-closed. Test đã được thêm cho
hai trường hợp: manifest bị thiếu và normalization nằm ngoài source root.

