# Dev log

Nhật ký thay đổi của **những gì đang có trong code**. Không phải nhật ký thiết kế.

**Lưu giữ:** mỗi mục chỉ giữ **Hiện tại** + **Trước đó**. Khi sửa mới, chuyển Hiện tại → Trước đó và **xóa** bản Trước đó cũ.

**Cách viết:** tiếng Việt, ngắn, chính xác, khớp code và luồng chạy thật. Trước khi lưu, đọc lại code (hoặc chạy thử) và bỏ mọi điều không đúng.

## Mẫu (chép cho mỗi tính năng / module)

```markdown
## <id> — <tên>

- file:
- cách kiểm chứng:

### Hiện tại (<ngày>)
- hành vi:

### Trước đó (<ngày>)
- hành vi:
```

Tính năng mới: chỉ điền Hiện tại; Trước đó = _không có_.  
Sửa sau này: chuyển Hiện tại sang Trước đó, viết Hiện tại mới, bỏ bản Trước đó cũ hơn.

---

## Các mục

## trip-agent-questions-2026-10-16 — Agent tự viết câu hỏi, app giữ lựa chọn

- file: `src/trip/domain/{deck,ask,taste_bank,readiness}.py`, `src/trip/agent/{prompt,tool_schemas,tools}.py`, `src/trip/api/engine.py`, `web/src/user/screens/Understand.tsx`, `web/src/user/screens/understand/{Ask,Composer,Deck}.tsx`, `web/src/user/css/{ask,workspace}.css`, `tests/trip/test_agent_questions.py`
- cách kiểm chứng: `pytest --collect-in-virtualenv tests/trip`; `tsc --noEmit` trong `web`; chạy tay: harness riêng + Vite riêng, nói "săn mây", gõ vào overlay ảnh, kéo ảnh biểu đồ vào khung chat

### Hiện tại (2026-10-16)
- hành vi: trong chat app không tự mở mục bắt buộc; agent hỏi qua `ask_required(topic, question)` (hoặc `record_fact.ask_question`) bằng lời bám mạch, app thêm phần trả lời; lời mặc định của mục chỉ ở cổng trước lập lịch. Mọi lựa chọn trên thẻ chạy agent một lần (`picked`), nên câu kế bám câu trả lời vừa bấm.
- hành vi: lựa chọn của `ask_user` do app đặt lời từ write (`taste_bank.py`), lựa chọn lạ hay chứa số người dùng chưa nói bị bỏ; thẻ sở thích hiện ảnh thật mỗi lựa chọn khi đủ ảnh; thẻ có thì lời agent không kèm câu hỏi thứ hai; thẻ xác nhận `confirm.*` đợi khi người dùng đang hỏi.
- hành vi (2026-10-17): app tự mở mục bắt buộc kế tiếp khi agent không hỏi gì hoặc đã hỏi riêng 3 lượt liền (`engine._due_required`, `meta.nudged`); `prepass.party_size` đọc "nhóm mình 6 đứa". Bench 5 persona: 23/35 lên 33/35 fact bắt buộc.
- hành vi: người yêu / vợ chồng, đi một mình không hỏi số người; nhóm khác hỏi số người sau khi chọn nhóm, có nút 2–6 người; thẻ chỉ hỏi số / ngày / chỗ ở không có dòng "Khác".
- hành vi: overlay ảnh gửi được chữ gõ ("Gửi ý của bạn"). Kéo thả file vào bất kỳ chỗ nào của khung chat; một ảnh mỗi tin nhắn. Ảnh reader không thấy nơi chốn và không khớp rõ ảnh corpus (biểu đồ, ảnh chụp màn hình) trả `NOT_PLACE_SAY`, không dựng thẻ sở thích.

### Trước đó (2026-10-16)
- _không có_

## corpus-online-contracts — Binding, budget, lodging và evidence xuyên module

- file: `src/corpus/releases/binding.py`, `src/trip/{api/tools,domain/resolve,infrastructure/catalog}.py`, `src/decision/{engine,tools,contracts}.py`, `src/planning/{engine,lodging,tools}.py`, `src/harness/{dispatch,contracts,server}.py`
- cách kiểm chứng: các regression binding/budget/evidence/lodging trong `tests/{normalization,trip,decision,planning,harness}`; kết quả tích hợp và release ở `docs/plans/CORPUS_NORMALIZATION_HANDOFF.md`

### Hiện tại (2026-10-15)
- hành vi: journey mới giữ binding xuyên Trip → Decision → Planning; restore/copy giữ release và version, missing/corrupt fail-closed. Factory capture hoặc nhận binding explicit; delayed index không theo pointer mới. Budget giữ amount/scope/nguồn/evidence, chỉ quy đổi khi đủ chiều; scalar tương thích vẫn VND/người/ngày.
- lodging: sàng bằng public requirements theo accommodation, eq/ne và unknown policy; không lấy giá/người làm giá/phòng/đêm. Decision recheck corpus lodging đã chọn/booked tại draft/confirm sau rebase; Planning giữ guard create/preview/confirm. Dữ liệu draft phục hồi và danh sách lodging thay thế vẫn đọc được, không tự bỏ selection.
- cache: preview bỏ log/wishlist/feasibility phụ, giữ dependency ảnh hưởng lịch. Immutable release dùng manifest hash; preview hit không sửa shared base; create rebind log sau pop ownership.
- retrieval: tìm tên Trip qua public Corpus trên eligible catalog; Decision có typed read evidence theo feature/context/binding, qua HTTP harness và capability read. UNKNOWN/UNCERTAIN không mượn vector quote; legacy null trả reason thiếu lineage. Evidence đọc theo yêu cầu, không ghi state/log/revision.
- wiring Agent: harness tạo một public RetrievalEngine theo binding cho cả ba factory. Trip cues dùng hybrid trong catalog ∩ within; Decision nhận tối đa ba nơi/hai feature/một quote mỗi feature, Planning proposal tối đa ba nơi/một feature. Payload giữ status, release, observation/source/time; thiếu evidence là unknown, validators giữ quyền quyết định.
- giới hạn: chưa có lineage lịch sử cho journey null, chưa có contract safety riêng cho address ngoài corpus, room occupancy/capacity chưa đủ để chứng minh tổng giá phòng cho nhóm. Chưa triển khai redesign ngày/buffer qua nửa đêm, grounded directions hoặc slot khám phá cho dữ liệu mỏng. Không chạy thêm model/vector/crawl trong đợt contract.

### Trước đó
_không có_

## corpus-retrieval — Module retrieval công khai cho online

- file: `src/corpus/retrieval/__init__.py`, `src/corpus/retrieval/engine.py`, `src/corpus/index/compile.py` (cột `served`), `src/corpus/index/query.py` (`served_only` param), `tests/index/test_index_query.py`, `tests/retrieval/test_retrieval_boundary.py`
- cách kiểm chứng: `.venv/bin/python -m pytest tests/index/test_index_query.py tests/retrieval/test_retrieval_boundary.py -q`

### Hiện tại (2026-10-15)
- hành vi: open/from_snapshot pin binding và version thật; tên qua typed public API, semantic/similar bắt buộc scope eligible. Evidence exact served value/status/observation, context chỉ khi có verdict; legacy null không giả lineage. Gate loại claim fail normalization, wrong/unsure_again kể cả unserved. Ontology chỉ boost vector hit có sẵn. Đã nối ba factory và Agent context; xem `corpus-online-contracts` và handoff cho kiểm chứng.
- giới hạn: vector stay còn mỏng; không có benchmark live hay đảm bảo precision toàn serving, chưa activation.

### Trước đó (2026-10-14)
- hành vi:
  - **Cột `served` trong span index:** `compile.py` gate trả span với `served=False` thay vì loại span không đỡ feature đang phục vụ. Lý do `stale_evidence` → `not_backing_served_feature`. Span hỏng (model lệch, nhãn `wrong`, `invalid_source_span`) vẫn loại hoàn toàn.
  - **`search_spans()` có `served_only`:** mặc định `True` (evidence lookup, chỉ span backing served feature); `False` cho vibe/semantic search, đọc cả 271k+ span mô tả vibe không gắn feature. `SpanHit` có field `served: bool`.
  - **`corpus.retrieval.RetrievalEngine`** (module mới): wrap `Index` + `Snapshot` + `Ontology` sau typed API. Mở bằng `RetrievalEngine.open(release_id, region)`. Read-only, thread-safe. Mọi kết quả mang `release_id`.
    - `search_names(q, within, limit)`: tìm theo tên, substring match, scope-safe.
    - `get_place(place_id)`: serving record từ snapshot region.
    - `semantic(q|bytes, within, mode, limit)`: hybrid cross-modal (bge-m3 span + SigLIP2 photo) + ontology feature boost + RRF merge. `mode="vibe"` đọc cả span `served=False`; `mode="evidence"` chỉ served. Bytes query (ảnh) chỉ photo space.
    - `similar(place_id, within, k)`: nơi tương tự (photo centroid).
    - `evidence(place_id, feature, limit)`: span backing served feature; chỉ `served=True`.
    - `coverage(place_ids)`: photo/span/style counts + missing lists.
  - **Ontology matching:** `_match_ontology()` so user query với hint/value trong ontology (không cần model). Feature match → boost additive 0.15 × confidence cho place có feature đó.
  - **Merge:** Reciprocal Rank Fusion (K=60) ghép span + photo channel; ontology boost additive trên RRF score. Không tạo hit mới từ ontology-only khi không có span/photo match tương ứng (trừ khi feature tồn tại).
- kiểm chứng: 28/28 test (7 index + 21 retrieval boundary). Boundary kiểm: scope enforcement (không ID ngoài `within`), evidence chỉ `served=True`, semantic score ≠ VERIFIED, `release_id` trên mọi kết quả, ontology matching cho `outdoor_seating` / `photo_friendly`, image query chỉ photo channel, coverage counts.
- giới hạn: chưa chuyển name search của Trip (`trip/domain/resolve.py:search`) sang `corpus.retrieval` (cần phối hợp Codex); chưa integrate vào Decision/Planning. Vector stay chỉ 3/1.510. `similar()` chưa test cross-modal (chỉ photo centroid). Gemma audit kết quả sửa chuẩn hóa chưa publish.


## trip-reader-root-binding — Snapshot và visual index cùng root

- file: `src/trip/api/tools.py`, `src/trip/__main__.py`, `src/trip/infrastructure/looks.py`, `tests/trip/test_normalized_readers.py`
- cách kiểm chứng: `python -m pytest tests/trip/test_normalized_readers.py tests/trip/test_catalog_snapshot.py tests/trip/test_vibes.py -q`

### Hiện tại (2026-10-15)
- hành vi: reader snapshot và Looks pin version theo binding; serving Catalog và hybrid scope đã có. Journey/handoff/factory/Agent giữ cùng release; xem `corpus-online-contracts`. Legacy null vẫn không có lineage lịch sử xác minh.

### Trước đó (2026-10-14)
- hành vi: giữ fix release resolver của Claude; factory/CLI resolve một lần, truyền cùng root vào snapshot và Looks. Index explicit không đọc pointer của root khác hoặc resolve lần nữa. Session CLI vẫn lưu ở root ban đầu.
- kiểm chứng: 29 test liên quan pass; có ca release/legacy, pointer đổi khi khởi tạo, thiếu manifest và root explicit. Review spec/code không còn issue cần xử lý.
- giới hạn: chưa thêm journey pinning, serving-only Catalog hay scope retrieval chung. Các phần này nằm trong proposal `docs/plans/NORMALIZED_CORPUS_RAG_ONLINE_PROPOSAL.md`; dừng triển khai tiếp theo yêu cầu người dùng.


## corpus-release-alignment — Trip, Decision, Planning đọc cùng một release corpus

- file: `src/trip/api/tools.py`, `src/trip/__main__.py`, `tests/trip/test_catalog_snapshot.py`
- cách kiểm chứng: `python -m pytest tests/trip/test_catalog_snapshot.py -q`; `python -m pytest tests/planning/test_planning_boundaries.py tests/live/test_boundaries.py -q`

### Hiện tại (2026-10-15)
- hành vi: cả ba factory capture binding hoặc nhận binding explicit, harness pin journey và chia sẻ public retrieval cùng binding; restore/copy/handoff giữ version. Pointer đổi không chuyển journey đã pin. Chưa active release/restart deployment; xem `corpus-online-contracts`.

### Trước đó (2026-10-14)
- hành vi: **cập nhật để khớp corpus mới (release chuẩn hóa)**. Trip mở snapshot qua `corpus.releases.resolve()` như Decision (`Data.load` → `snapshot.shared()`), Planning / Companion (`corpus.serving.load`) và semantic index (`Index.load`). Có `data/releases/current` thì cả bốn đọc snapshot / index của release đó; chưa có thì cùng về `data/snapshot`, `data/index` cũ.
- giới hạn: mỗi engine resolve một lần lúc tạo; journey chưa lưu `corpus_release_id`, nên đổi pointer khi server đang chạy cần khởi động lại cả harness. Ghim release theo journey vẫn là việc sau (spec chuẩn hóa §5.6).

## normalization-online-regressions — Ảnh đầu vào và draft theo chỗ ở

- file: `src/trip/api/engine.py`, `src/planning/engine.py`, `tests/trip/test_vibes.py`, `tests/planning/test_planning_consistency.py`, `tests/planning/test_planning_variants.py`, `tests/planning/golden/`, `tests/harness/test_dispatch.py`, `tests/harness/test_tools.py`
- cách kiểm chứng: `python -m pytest tests/trip tests/decision tests/planning tests/harness -q`; `python -m pytest tests/planning/test_planning_boundaries.py tests/live/test_boundaries.py -q`

### Hiện tại (2026-10-14)
- hành vi: ảnh upload được sanitize từ pixel trước Extractor/Embedder; giới hạn byte/pixel/cạnh theo `config/security.yaml`. Payload đính kèm bị loại; ảnh lỗi hoặc decompression bomb trả `BAD_PHOTO` trước xử lý lượt.
- hành vi: đổi chỗ ở khi chưa có global override tạo lại draft quá tải theo neo mới, giữ Decision selection. Nơi restored/locked/assigned không bị đưa vào `plan_dropped`; phương án vi phạm vẫn không chọn/chốt được. Đã kiểm timeline/metrics, chuyển phương án, replay và undo.
- test: setup harness dùng ý định café suy ra và contract `AIMessageChunk`; golden khớp thời lượng bữa/visit hiện hành và khoản giá bữa chưa biết. Fixture loại objective kiểm đúng nhánh thường, giữ constraint và assertion warning.
- kiểm chứng: toàn bộ Trip/Decision/Planning/Harness đạt 1.309 passed, 127 skipped, 4 deselected; boundary đạt 128 passed. Suite online chạy ngoài sandbox để asyncio thread shutdown hoàn tất. PostgreSQL chưa kiểm vì thiếu `TEST_DATABASE_URL`.
- giới hạn: release normalized chưa được kích hoạt; pin release, budget/time, stay constraints và cache dependency là phạm vi thảo luận tiếp theo trong spec normalization, chưa triển khai ở mục này.

### Trước đó
_không có_

## corpus-core — Nền tảng corpus (Phase 1, một phần)

- file: `config/cities.yaml` (còn lại; `src/corpus/core/`, `src/corpus/adapters/` đã xóa)
- cách kiểm chứng: _không còn test_

### Hiện tại (2026-09-29)
- hành vi: đã xóa `core/` và `adapters/` (cùng test, `docker-compose.yml`) theo yêu cầu: làm từ dữ liệu thô trước, thêm lớp khi dữ liệu cho thấy cần.

### Trước đó (2026-09-28)
- hành vi:
  - `core.types`: data model của spec bằng pydantic (frozen, cấm field lạ). `TikTokVideo.video_ref` trỏ tới file video đã tải (video được giữ lại để xem nội dung, không xóa sau ASR). Invariant nằm ngay trong type: observation bắt buộc có span, span text có `quote` khớp độ dài offset, fact có xung đột phải giữ `value = None` và ≥ 2 giá trị, derived cần ≥ 1 observation, relation cần span.
  - `core.ontology`: feature v0 (21 feature) + `FACT_KEYS`; feature `verify: always` khai báo `caution_values`.
  - `core.gate`: trả danh sách lý do trượt cho span (quote nguyên văn tại offset, timestamp trong segment), observation (feature / fact_key / giá trị), match (T, M, `T_min` cho Judge), derived (chỉ processor `aggregate`, observation id tồn tại).
  - `core.loop.bounded_loop`: vòng lặp có số bước tối đa, ngân sách, điều kiện dừng; model trả `None` là dừng.
  - `adapters.db`: Postgres qua pool async; bảng `record` (JSONB theo kind), `provider_place` tách riêng (`save` từ chối `ProviderPlace`), `ledger` (chạy lại khi thất bại hoặc khóa input/processor/prompt/ontology đổi), `llm_cache`.
  - `adapters.llm.Llm`: gọi model theo vai trò qua API tương thích OpenAI, output `json_schema` validate bằng pydantic, cache theo hash toàn bộ request, retry backoff lỗi mạng, sai schema thử lại 1 lần kèm lỗi rồi `InvalidOutput`.
  - Chưa có: adapter ASR, Google, TikTok, media, web; các bước discover → refresh; `api`.

## corpus-review — Trang review mục cần người

- file: `src/corpus/review/` (`decisions.py`, `queue.py`, `server.py`, `page.html`), `tests/review/`
- cách kiểm chứng: `python -m pytest -q tests/review`; `python -m corpus review` rồi mở `http://127.0.0.1:8765`

### Hiện tại (2026-10-02, chiều)
- hành vi: nhãn khóa theo nội dung (`key` = review / video id + feature + value + quote chuẩn hóa), không theo id observation: chạy lại observe không làm mất nhãn, nhãn của khẳng định mà lần chạy mới không còn tạo thì không vào thống kê; `migrate()` ghi key cho bản ghi cũ. Observation của mọi version ontology được tính khi giá trị còn trong ontology. Màn `Gán nhãn` hiện thêm bằng chứng: nghĩa của nhãn (claim + hint), sao / ngày / tác giả / mục chấm điểm Maps của review, các observation khác cùng nơi về feature đó (đồng ý / ngược lại), category / giá / thuộc tính / link Maps. Nguồn TikTok (`tiktok_segment` / `tiktok_caption` / `tiktok_frame`): transcript quanh quote, caption, link video, khung hình (`GET /api/labels/frame`). `stats` có `by_source`. Index cache theo từng file (lúc observe chạy lại không quét lại 1.437 file mỗi request). Kiểm chứng: 14 test review, `npm run build`, API thật.

### Trước đó (2026-10-02)
- hành vi: như bản trước, thêm: (1) `labels.py` + `GET /api/labels/next`, `POST /api/labels`, `GET /api/labels/stats`: lấy mẫu observation từ review chưa gán nhãn (giá trị ít nhãn nhất trước, bỏ observation do rule và file ontology cũ), nhãn `correct | wrong | unsure` ghi nối vào `data/review/labels.jsonl`, thống kê độ chính xác theo (feature, value) với cận dưới Wilson và ngưỡng (`GATE_MIN_N = 30`, `GATE_LOWER = 0.8`); (2) loại quyết định `feature_review` (accept / disable / report / refresh / undo, id `<fid>#<feature>`) và `GET /api/decisions?kind=`; (3) Admin Web (`web/`): màn `Gán nhãn` (`/admin/labels`, phím c / w / u / s), `decisions.ts` ghi quyết định về backend và đọc lại khi mở trang, Vite proxy `/api` tới `127.0.0.1:8765`. `aggregate` chưa đọc nhãn và quyết định. Kế hoạch tiếp: `docs/plans/CORPUS_QUALITY.md`. Kiểm chứng: 12 test review, chạy thật với Chrome không lỗi console, mẫu lấy từ 249.605 bằng chứng (lần đọc đầu ~4 giây).

## corpus-crawl — Crawl dữ liệu thô TikTok + Google Maps

- file: `src/corpus/crawl/` (`files`, `browser`, `tiktok`, `gmaps`), `src/corpus/__main__.py`, `config/queries.yaml`, `tests/crawl/`, `tests/fixtures/` (`capture.py` lưu lại fixture thật, đã che tài khoản)
- cách kiểm chứng: `python -m pytest -q`; smoke thật `python -m corpus {tiktok|gmaps} --city dalat --headed` với config thu nhỏ

### Hiện tại (2026-10-01)
- hành vi:
  - Lệnh, phase, layout file: `docs/CORPUS.md` §1 Discover (Dữ liệu thô). `python -m corpus login <source>` để đăng nhập lại.
  - Rời trang theo tín hiệu kết thúc (spec §1): TikTok `comments_complete` (mọi danh sách comment / reply trả `has_more=0`, không còn request chờ; body rỗng = bị chặn, dừng ngay); Maps review dừng khi ô loader cuối khung bị làm rỗng (`reviews_complete`); Maps search dừng ở dòng "Bạn đã xem hết danh sách này", ô không tới được dòng đó (`end=false`) thì chia nhỏ như ô đầy.
  - Trang TikTok tự tải lại ngay sau khi mở: item JSON đọc bằng vòng chờ (tối đa 20 s), lỗi "Execution context was destroyed" coi là chưa xong.
  - Maps: sắp xếp review "Mới nhất" được kiểm bằng nhãn nút (text dạng tổ hợp, so sánh sau `normalize('NFC')`), không áp dụng được thì lỗi + thử lại; cuộn bằng cách đưa mục cuối vào tầm nhìn (`scrollBy` / wheel hay không tải thêm); review layout lưu trú ("4/5", "… trước trên Google") đọc được; bỏ chữ icon-font khỏi `address` / `hours`; trang có link đăng nhập → `LoginRequired` (phiên hết hạn mà cookie `SID` vẫn còn).
  - `config/queries.yaml` TikTok `pause_s: [15, 30]`.
  - TikTok `filter` (sau `list`, trước `crawl`): Extractor đọc caption + hashtag (không đọc query / tác giả: model lấy query làm bằng chứng và cho `#comga20k` là liên quan), trả `yes | no | unsure`; `crawl` chỉ mở `yes` / `unsure`. Prompt và thiết lập model: `src/corpus/llm/` (`Role`, `Task`, `prompt_hash`); `gmaps qc` dùng `PLACE_QC` ở cùng chỗ. Lần chạy 2026-09-29 trên 273 video: 244 yes, 12 unsure (chủ yếu thời tiết), 17 no (couple / tâm trạng / thất nghiệp / tai nạn); prompt khắt khe hơn trước đó loại nhầm review quán, săn mây, vlog chuyến đi (35 no).
  - Đo 2026-09-29:
    - Maps (đăng nhập): 200 review / place trong ~22 s, 27/27 trong 9 s, đúng thứ tự mới nhất. Code cũ chỉ lấy 20–50 review, có place sai thứ tự; search cũ dừng ở vòng cuộn thứ 20 (~92 kết quả) nên ô đầy 120 không được chia. Đăng xuất: ô 116 kết quả chỉ còn 40 mà vẫn hiện dòng hết danh sách.
    - TikTok: ~15 video (nhịp cũ, không nghỉ) thì API comment trả body rỗng; hết chặn sau ~21 phút. Comment lấy được 81% `commentCount` (2.487 / 3.081 trên 32 video); phần thiếu là comment / reply TikTok ẩn (danh sách kết thúc `has_more=0` mà ít dòng hơn).
  - Phase 1 (2026-09-29): Maps là nguồn địa điểm; TikTok tạm ngoài phạm vi (code giữ, dữ liệu đã xóa theo yêu cầu). `search` không cần đăng nhập, mỗi lần thử một ô chạy trong context mới không cookie (Google giới hạn theo phiên); song song nhiều tab (`search_tabs`, AIMD; ô bị cắt ngang = bị chặn mềm → giảm tab, nghỉ, tìm lại; mỗi lần thử hỏng một mức tab thì lần thử sau ở mức đó cần gấp đôi chuỗi sạch, tối đa ×32), quét tới zoom 14 (chỉ chia ô khi số chỗ nằm trong chính ô đủ `full_at`: Maps lấp danh sách ngắn bằng chỗ ở thành phố khác, ~43% kết quả thô nằm ngoài area; `list` bỏ chúng), chạy xong từng category rồi mới sang category kế, đọc thêm `category`, `rating`, `reviews` từ thẻ kết quả (bỏ hậu tố "Đường liên kết đã truy cập" khỏi tên); `list` bỏ chỗ ở, xếp theo trung bình Bayes, giữ `top_per_category` = 100 mỗi category (spec §1, Phase 1). Config: 38 category du lịch (gộp loại trùng: nhà hàng → quán ăn, lẩu + nướng → quán lẩu nướng, bỏ làng hoa, cánh đồng hoa, điểm check in, thiền viện, đồi chè, đèo, quán kem, chợ đêm, cửa hàng lưu niệm, vườn cà phê, dinh thự, phòng tranh, công ty du lịch (đại lý / văn phòng, không phải nơi để đi)), bỏ khách sạn / homestay / resort / nhà nghỉ / villa / khu du lịch. Dữ liệu: đã xóa search định dạng cũ, `data/tiktok`, `data/review`; phase 1 chỉ lấy dữ liệu thô (`gmaps search`); lọc (`filter`, Gemma) và `list` để phase sau.
  - Maps `filter` (sau `search`, trước `list`; spec §1): Extractor (`PLACE_FILTER`) đọc tên + category Maps của mỗi FID trong `area`, không chỗ ở; `list` chỉ xếp `yes` / `unsure` (+ giữ / bỏ của người, loại review `place_filter`). Lần chạy 2026-09-29 trên 1.022 nơi: 963 yes, 56 no (công ty, cửa hàng gia dụng / điện máy, bãi xe, nhà vệ sinh, cứu hộ xe, trạm xe buýt, tháp viễn thông), 3 unsure, 0 lỗi; `list` ra 745 nơi.
  - Maps `filter` prompt siết (2026-09-30): chỉ giữ nơi du khách đến vì chính nơi đó; `no` cho mọi chỗ ở (kể cả có cafe / nhà hàng; khu cắm trại không tính là chỗ ở), công ty tour / đại lý du lịch / phòng vé, cửa hàng thường (trang sức, quần áo, điện thoại, siêu thị…); tên nói rõ loại nơi thì tên thắng category. Thử 19 ca mẫu đúng hết; chấm lại 5.956 nơi: 5.368 yes, 520 no, 68 unsure, 0 lỗi; list 1.485 → 1.438 nơi.
  - Maps `list` (2026-09-30): lọc = `filter` (liên quan du lịch) + `min_reviews` 50 + gộp cùng tên chuẩn hóa trong `same_name_m` 1000 m; không cắt theo rating / score / top mỗi category; FID từng mang category chỗ ở ở bất kỳ lần thấy nào bị bỏ (spec §1, Phase 1). Mỗi FID lấy lần thấy nhiều review nhất (thẻ thiếu số làm mất 213 nơi, vd Thung Lũng Vàng 4.712 review). Phase mới `counts`: Maps không đăng nhập đôi khi ẩn "(124)" trên thẻ và luôn ẩn trên trang chi tiết; mở 173 nơi bằng profile đăng nhập, đủ 173 số, 44 nơi ≥ 50. Profile hết phiên mà còn cookie SID → trang "chế độ bị hạn chế", không có số: `counts` dừng `LoginRequired` thay vì ghi rỗng. `is_lodging` chuẩn hóa NFC (410 category Maps gửi dạng NFD). Category `rừng thông` → `khu rừng thông` (query cũ mở thẳng một địa điểm). Search đủ 38/38 category, không thiếu ô. Lần chạy: 5.947 ứng viên, 282 filter bỏ, 52 bản trùng gộp, 4.128 dưới 50 review / không rating → 1.485 nơi. Kiểm độc lập 2 chiều: mọi nơi trong list liên quan du lịch, ≥ 50 review, trong area, không chỗ ở, FID duy nhất khớp URL; mọi nơi đạt điều kiện đều trong list trừ 7 bản trùng đã gộp.
  - TikTok theo địa điểm (2026-09-30): phase `place_search` → `place_filter` → `place_crawl` (spec §1, Phase 2; `config/queries.yaml`: `videos_per_place` 10, `place_search_tabs` 3, `place_search_pause_s`). `place_search` song song theo `Throttle` riêng (`tiktok/place_search_throttle.json`), danh sách không kết thúc → thử lại, lần cuối ghi `errors.jsonl`. `place_filter` chỉ giữ `yes` (video thành bằng chứng cho nơi đó). `place_crawl` dùng chung `crawl.crawl_videos`. Smoke 4 nơi: 40 video → 22 yes, 8 unsure, 10 no; `no` bắt đúng tiệm khác tên gần giống (xe máy "Vũ" / "Tài" với "Vy", Karaoke "Melya" với "Luxury"); `unsure` gồm video tả đúng quán nhưng không ghi tên (bị bỏ).
  - Maps `crawl` chốt số review (2026-09-30): phiên Google hết giữa chừng (nút "Đăng nhập", cookie `SID` còn) → trang chỉ hiện ~8 review; `check_signed_in` chạy lúc tiêu đề hiện nên chưa thấy link (thanh Google render sau) → 28 place lưu 8–20 review. Nay kiểm đăng nhập lại sau khi đọc review; `too_few` (review < nửa min(`review_count`, `max_reviews_per_place`) mà chưa gặp review quá tuổi, `reviews_age_cut`) → thử lại như bị chặn, không lưu; chỉ giữ review dưới 1 năm, tối đa 200 mới nhất, không sàn (`max_reviews_per_place` 200, `max_review_age_months` 11, `min_reviews_per_place` 0; thử bỏ trần thì nơi đông khách dừng giữa danh sách dài và không lưu được gì); dữ liệu cũ đã lọc: bỏ 8.937 review quá 11 tháng ở 385 place; `run` crawl lại place đã lưu mà `too_few`. Nút "Xem thêm" (`button.w8nwRe`) có cho cả review lẫn owner reply (`expandOwnerResponse`), `EXPAND_JS` chỉ bấm nút của review (owner reply không lấy nữa: không phải bằng chứng, spec §1 Dữ liệu thô); `reviews_complete=False` (hết 15 s không có đợt mới, mạng chậm) → thử lại, không giảm tab (giảm tab ở lỗi chậm từng kẹt throttle ở 1 tab: 8 place / 30 phút), lần cuối mới lưu kèm cờ + `errors.jsonl` (như TikTok); `tabs` 10; review kết thúc " …" mà không có nút là text Maps tự cắt, không mở thêm được trong khung này.
  - TikTok ASR + kiểm tra (2026-09-30): phase `asr` → `asr_check` → `place_verify` sau `place_crawl` (spec §1, Phase 2; layout `video.json`: spec Dữ liệu thô). Thử Gemma: transcript giả lập (tên nghe nhầm, lời nhạc nền, đoạn vô nghĩa) chấm đúng hết; trên output vô nghĩa, Gemma vẫn "sửa" "mry o dayay red vui" → "mọi người đi chơi vui" dù prompt cấm → chặn bằng code (`MIN_KEPT` 0,5). 5 video thật đầu tiên: ASR giọng người dùng được, Gemma sửa đúng tên ("siêu thị cô đà lạt" → "GO! Đà Lạt"); 2 video chỉ nhạc → `no_speech`; keyframe đọc được biển hiệu / logo / chữ overlay. Một video map vào 2 spa tên gần giống, cả hai `yes` → prompt nay kèm các nơi khác cùng video (`others`), bằng chứng hợp nơi khác thì không `yes`: chấm lại còn 1 `yes`, 1 `no`. `place_filter` trên 450 place đã search: 4.400 video, 2.717 cặp `yes`.
  - ASR sai và cách sửa (2026-10-01, 608 video đã kiểm: 288 good, 79 partial, 175 no_speech, 66 unusable; segment 2.282 ok, 1.428 fixed, 433 lyrics, 275 garbled): lỗi chính là từ mượn ("mátage" → massage), tên riêng ("PiNi" → "mini" / "pin đi"), nhầm dấu ("sân bay" → săn mây), nhạc nền có lời (cả rap tiếng Anh). Ca "Quỷ Núi" (khu trong quần thể PiNi): `asr_check` ép tên place "mini" → "Quỷ Núi", `place_verify` đọc biển "Pini Dalat" thành "Pin đi" → `no`. Sửa: keyframe + `screen_text` vào `asr_check`, `guard` hoàn tác chỗ thay không giống âm, phase `asr_alt` (PhoWhisper-medium) cho segment không tin được rồi Gemma ghép ASR + ASR2, prompt `place_verify` đọc chữ màn hình đúng như hiện và `unsure` khi quan hệ khu / quần thể không rõ, review loại `place_verify`. Thử lại 5 video: "mini" → "Pini" (theo biển), Quỷ Núi `yes`, ghép ASR2 thêm "phương thức" / "quần thể" và bỏ "bin laden" PhoWhisper bịa. Trang review chưa có tab cho `place_filter` (queue có tạo mục, `page.html` thiếu nhãn).
  - Còn phải làm: review dài không bấm được "Thêm" thì giữ text bị cắt; trang chặn `/sorry` của Google chưa chờ người giải (dừng với `LoginRequired`).
  - Maps (2026-10-01): `min_reviews_per_place` 40 — 40 review mới nhất luôn giữ dù quá `max_review_age_months`; `too_few` coi place bị cắt theo tuổi mà có dưới nửa min(40, số review Maps) là thiếu, nên `gmaps crawl` crawl lại (536 place lúc đổi).

### Trước đó (2026-09-29, tối)
- hành vi:
  - Lệnh, phase, layout file: `docs/CORPUS.md` §1 Discover (Dữ liệu thô). `python -m corpus login <source>` để đăng nhập lại.
  - Rời trang theo tín hiệu kết thúc (spec §1): TikTok `comments_complete` (mọi danh sách comment / reply trả `has_more=0`, không còn request chờ; body rỗng = bị chặn, dừng ngay); Maps review dừng khi ô loader cuối khung bị làm rỗng (`reviews_complete`); Maps search dừng ở dòng "Bạn đã xem hết danh sách này", ô không tới được dòng đó (`end=false`) thì chia nhỏ như ô đầy.
  - Trang TikTok tự tải lại ngay sau khi mở: item JSON đọc bằng vòng chờ (tối đa 20 s), lỗi "Execution context was destroyed" coi là chưa xong.
  - Maps: sắp xếp review "Mới nhất" được kiểm bằng nhãn nút (text dạng tổ hợp, so sánh sau `normalize('NFC')`), không áp dụng được thì lỗi + thử lại; cuộn bằng cách đưa mục cuối vào tầm nhìn (`scrollBy` / wheel hay không tải thêm); review layout lưu trú ("4/5", "… trước trên Google") đọc được; bỏ chữ icon-font khỏi `address` / `hours`; trang có link đăng nhập → `LoginRequired` (phiên hết hạn mà cookie `SID` vẫn còn).
  - `config/queries.yaml` TikTok `pause_s: [15, 30]`.
  - TikTok `filter` (sau `list`, trước `crawl`): Extractor đọc caption + hashtag (không đọc query / tác giả: model lấy query làm bằng chứng và cho `#comga20k` là liên quan), trả `yes | no | unsure`; `crawl` chỉ mở `yes` / `unsure`. Prompt và thiết lập model: `src/corpus/llm/` (`Role`, `Task`, `prompt_hash`); `gmaps qc` dùng `PLACE_QC` ở cùng chỗ. Lần chạy 2026-09-29 trên 273 video: 244 yes, 12 unsure (chủ yếu thời tiết), 17 no (couple / tâm trạng / thất nghiệp / tai nạn); prompt khắt khe hơn trước đó loại nhầm review quán, săn mây, vlog chuyến đi (35 no).
  - Đo 2026-09-29:
    - Maps (đăng nhập): 200 review / place trong ~22 s, 27/27 trong 9 s, đúng thứ tự mới nhất. Code cũ chỉ lấy 20–50 review, có place sai thứ tự; search cũ dừng ở vòng cuộn thứ 20 (~92 kết quả) nên ô đầy 120 không được chia. Đăng xuất: ô 116 kết quả chỉ còn 40 mà vẫn hiện dòng hết danh sách.
    - TikTok: ~15 video (nhịp cũ, không nghỉ) thì API comment trả body rỗng; hết chặn sau ~21 phút. Comment lấy được 81% `commentCount` (2.487 / 3.081 trên 32 video); phần thiếu là comment / reply TikTok ẩn (danh sách kết thúc `has_more=0` mà ít dòng hơn).
  - Phase 1 (2026-09-29): Maps là nguồn địa điểm; TikTok tạm ngoài phạm vi (code giữ, dữ liệu đã xóa theo yêu cầu). `search` không cần đăng nhập, mỗi lần thử một ô chạy trong context mới không cookie (Google giới hạn theo phiên); song song nhiều tab (`search_tabs`, AIMD; ô bị cắt ngang = bị chặn mềm → giảm tab, nghỉ, tìm lại; mỗi lần thử hỏng một mức tab thì lần thử sau ở mức đó cần gấp đôi chuỗi sạch, tối đa ×32), quét tới zoom 14 (chỉ chia ô khi số chỗ nằm trong chính ô đủ `full_at`: Maps lấp danh sách ngắn bằng chỗ ở thành phố khác, ~43% kết quả thô nằm ngoài area; `list` bỏ chúng), chạy xong từng category rồi mới sang category kế, đọc thêm `category`, `rating`, `reviews` từ thẻ kết quả (bỏ hậu tố "Đường liên kết đã truy cập" khỏi tên); `list` bỏ chỗ ở, xếp theo trung bình Bayes, giữ `top_per_category` = 100 mỗi category (spec §1, Phase 1). Config: 38 category du lịch (gộp loại trùng: nhà hàng → quán ăn, lẩu + nướng → quán lẩu nướng, bỏ làng hoa, cánh đồng hoa, điểm check in, thiền viện, đồi chè, đèo, quán kem, chợ đêm, cửa hàng lưu niệm, vườn cà phê, dinh thự, phòng tranh, công ty du lịch (đại lý / văn phòng, không phải nơi để đi)), bỏ khách sạn / homestay / resort / nhà nghỉ / villa / khu du lịch. Dữ liệu: đã xóa search định dạng cũ, `data/tiktok`, `data/review`; phase 1 chỉ lấy dữ liệu thô (`gmaps search`); lọc (`filter`, Gemma) và `list` để phase sau.
  - Maps `filter` (sau `search`, trước `list`; spec §1): Extractor (`PLACE_FILTER`) đọc tên + category Maps của mỗi FID trong `area`, không chỗ ở; `list` chỉ xếp `yes` / `unsure` (+ giữ / bỏ của người, loại review `place_filter`). Lần chạy 2026-09-29 trên 1.022 nơi: 963 yes, 56 no (công ty, cửa hàng gia dụng / điện máy, bãi xe, nhà vệ sinh, cứu hộ xe, trạm xe buýt, tháp viễn thông), 3 unsure, 0 lỗi; `list` ra 745 nơi.
  - Maps `filter` prompt siết (2026-09-30): chỉ giữ nơi du khách đến vì chính nơi đó; `no` cho mọi chỗ ở (kể cả có cafe / nhà hàng; khu cắm trại không tính là chỗ ở), công ty tour / đại lý du lịch / phòng vé, cửa hàng thường (trang sức, quần áo, điện thoại, siêu thị…); tên nói rõ loại nơi thì tên thắng category. Thử 19 ca mẫu đúng hết; chấm lại 5.956 nơi: 5.368 yes, 520 no, 68 unsure, 0 lỗi; list 1.485 → 1.438 nơi.
  - Maps `list` (2026-09-30): lọc = `filter` (liên quan du lịch) + `min_reviews` 50 + gộp cùng tên chuẩn hóa trong `same_name_m` 1000 m; không cắt theo rating / score / top mỗi category; FID từng mang category chỗ ở ở bất kỳ lần thấy nào bị bỏ (spec §1, Phase 1). Mỗi FID lấy lần thấy nhiều review nhất (thẻ thiếu số làm mất 213 nơi, vd Thung Lũng Vàng 4.712 review). Phase mới `counts`: Maps không đăng nhập đôi khi ẩn "(124)" trên thẻ và luôn ẩn trên trang chi tiết; mở 173 nơi bằng profile đăng nhập, đủ 173 số, 44 nơi ≥ 50. Profile hết phiên mà còn cookie SID → trang "chế độ bị hạn chế", không có số: `counts` dừng `LoginRequired` thay vì ghi rỗng. `is_lodging` chuẩn hóa NFC (410 category Maps gửi dạng NFD). Category `rừng thông` → `khu rừng thông` (query cũ mở thẳng một địa điểm). Search đủ 38/38 category, không thiếu ô. Lần chạy: 5.947 ứng viên, 282 filter bỏ, 52 bản trùng gộp, 4.128 dưới 50 review / không rating → 1.485 nơi. Kiểm độc lập 2 chiều: mọi nơi trong list liên quan du lịch, ≥ 50 review, trong area, không chỗ ở, FID duy nhất khớp URL; mọi nơi đạt điều kiện đều trong list trừ 7 bản trùng đã gộp.
  - TikTok theo địa điểm (2026-09-30): phase `place_search` → `place_filter` → `place_crawl` (spec §1, Phase 2; `config/queries.yaml`: `videos_per_place` 10, `place_search_tabs` 3, `place_search_pause_s`). `place_search` song song theo `Throttle` riêng (`tiktok/place_search_throttle.json`), danh sách không kết thúc → thử lại, lần cuối ghi `errors.jsonl`. `place_filter` chỉ giữ `yes` (video thành bằng chứng cho nơi đó). `place_crawl` dùng chung `crawl.crawl_videos`. Smoke 4 nơi: 40 video → 22 yes, 8 unsure, 10 no; `no` bắt đúng tiệm khác tên gần giống (xe máy "Vũ" / "Tài" với "Vy", Karaoke "Melya" với "Luxury"); `unsure` gồm video tả đúng quán nhưng không ghi tên (bị bỏ).
  - Maps `crawl` chốt số review (2026-09-30): phiên Google hết giữa chừng (nút "Đăng nhập", cookie `SID` còn) → trang chỉ hiện ~8 review; `check_signed_in` chạy lúc tiêu đề hiện nên chưa thấy link (thanh Google render sau) → 28 place lưu 8–20 review. Nay kiểm đăng nhập lại sau khi đọc review; `too_few` (review < nửa min(`review_count`, `max_reviews_per_place`) mà chưa gặp review quá tuổi, `reviews_age_cut`) → thử lại như bị chặn, không lưu; chỉ giữ review dưới 1 năm, tối đa 200 mới nhất, không sàn (`max_reviews_per_place` 200, `max_review_age_months` 11, `min_reviews_per_place` 0; thử bỏ trần thì nơi đông khách dừng giữa danh sách dài và không lưu được gì); dữ liệu cũ đã lọc: bỏ 8.937 review quá 11 tháng ở 385 place; `run` crawl lại place đã lưu mà `too_few`. Nút "Xem thêm" (`button.w8nwRe`) có cho cả review lẫn owner reply (`expandOwnerResponse`), `EXPAND_JS` chỉ bấm nút của review (owner reply không lấy nữa: không phải bằng chứng, spec §1 Dữ liệu thô); `reviews_complete=False` (hết 15 s không có đợt mới, mạng chậm) → thử lại, không giảm tab (giảm tab ở lỗi chậm từng kẹt throttle ở 1 tab: 8 place / 30 phút), lần cuối mới lưu kèm cờ + `errors.jsonl` (như TikTok); `tabs` 10; review kết thúc " …" mà không có nút là text Maps tự cắt, không mở thêm được trong khung này.
  - TikTok ASR + kiểm tra (2026-09-30): phase `asr` → `asr_check` → `place_verify` sau `place_crawl` (spec §1, Phase 2; layout `video.json`: spec Dữ liệu thô). Thử Gemma: transcript giả lập (tên nghe nhầm, lời nhạc nền, đoạn vô nghĩa) chấm đúng hết; trên output vô nghĩa, Gemma vẫn "sửa" "mry o dayay red vui" → "mọi người đi chơi vui" dù prompt cấm → chặn bằng code (`MIN_KEPT` 0,5). 5 video thật đầu tiên: ASR giọng người dùng được, Gemma sửa đúng tên ("siêu thị cô đà lạt" → "GO! Đà Lạt"); 2 video chỉ nhạc → `no_speech`; keyframe đọc được biển hiệu / logo / chữ overlay. Một video map vào 2 spa tên gần giống, cả hai `yes` → prompt nay kèm các nơi khác cùng video (`others`), bằng chứng hợp nơi khác thì không `yes`: chấm lại còn 1 `yes`, 1 `no`. `place_filter` trên 450 place đã search: 4.400 video, 2.717 cặp `yes`.
  - ASR sai và cách sửa (2026-10-01, 608 video đã kiểm: 288 good, 79 partial, 175 no_speech, 66 unusable; segment 2.282 ok, 1.428 fixed, 433 lyrics, 275 garbled): lỗi chính là từ mượn ("mátage" → massage), tên riêng ("PiNi" → "mini" / "pin đi"), nhầm dấu ("sân bay" → săn mây), nhạc nền có lời (cả rap tiếng Anh). Ca "Quỷ Núi" (khu trong quần thể PiNi): `asr_check` ép tên place "mini" → "Quỷ Núi", `place_verify` đọc biển "Pini Dalat" thành "Pin đi" → `no`. Sửa: keyframe + `screen_text` vào `asr_check`, `guard` hoàn tác chỗ thay không giống âm, phase `asr_alt` (PhoWhisper-medium) cho segment không tin được rồi Gemma ghép ASR + ASR2, prompt `place_verify` đọc chữ màn hình đúng như hiện và `unsure` khi quan hệ khu / quần thể không rõ, review loại `place_verify`. Thử lại 5 video: "mini" → "Pini" (theo biển), Quỷ Núi `yes`, ghép ASR2 thêm "phương thức" / "quần thể" và bỏ "bin laden" PhoWhisper bịa. Trang review chưa có tab cho `place_filter` (queue có tạo mục, `page.html` thiếu nhãn).
  - Còn phải làm: review dài không bấm được "Thêm" thì giữ text bị cắt; trang chặn `/sorry` của Google chưa chờ người giải (dừng với `LoginRequired`).

## corpus-observe — Observation từ review Google Maps

- file: `config/ontology.yaml`, `src/corpus/ontology.py`, `src/corpus/observe/` (`__init__.py`, `gmaps/details.py`, `gmaps/place_rules.py`, `gmaps/prep.py`, `gmaps/gate.py`, `gmaps/extract.py`), `REVIEW_OBSERVE` + `REVIEW_VERIFY` trong `src/corpus/llm/tasks.py`, `scripts/observe_prompt_eval.py`, `scripts/rerun_observe.sh`, `tests/test_ontology.py`, `tests/observe/`
- cách kiểm chứng: `python -m pytest -q tests/test_ontology.py tests/observe`; `python -m corpus gmaps observe --limit 20` (mạng UIT)

### Hiện tại (2026-10-02)
- hành vi: ontology v6 (54 feature): `condition_change` chỉ còn `declined` (`improved` đúng ~30%, đa số "xe mới" của tiệm thuê xe); `long_walk` cần lời nói về đi bộ / khoảng cách / thời gian đi bộ; `weather_exposed` `sheltered` cần mái che / trong nhà của chính nơi đó (không phải nhân viên che dù, xe thuê); thêm phản ví dụ cho `booking_needed` (đặt bàn được xác nhận), `visit_duration` (liệu trình spa), `steep_or_stairs` absent ("đi thẳng xe lên"); `entry_fee` giữ số tiền trong quote; feature mới `tasting_available`, `costume_rental`, `small_space`, `toilet`, `mosquitoes` (đề xuất ≥ 50 lần trong `proposed_top`). Rule v4: `place_facts.tickets` (giá vé US$ của Maps); category lấy từ `list` khi trang place không có (41 nơi). Kiểm chứng: `scripts/observe_prompt_eval.py` 29/29 (thêm 8 câu cho lỗi v5, thoát mã 1 khi lỗi cũ quay lại); chạy lại toàn bộ bằng `scripts/rerun_observe.sh` (chờ mạng UIT, chặn nếu eval trượt, giữ bản cũ ở `data/gmaps/observations_before_v6`). Thử 9router (`cx/gpt-5.6-*`) làm extractor: 3–4 phút cho một lô 16 câu và `REVIEW_VERIFY` trả lỗi, không dùng cho 8.500 lô.

### Trước đó (2026-10-01, đêm)
- hành vi: ontology v5 (49 feature, 6 nhóm): thêm nhóm `operation` với `visit_duration` (Estimate); `steep_or_stairs` / `long_walk` thêm `absent`, `weather_exposed` thêm `sheltered`; `check: span` thêm `booking_needed`, `weather_exposed`; hint loại câu kể của người viết ("mình đặt bàn trước", "đường đi hơi xa", "xe mới"). Prompt: phủ định không bao giờ thành `present`. Rule v3: thêm attribute sân thượng, sân chơi, nhạc sống, đi bộ đường dài; `place_facts.hours` / `closure`; file observation có `place` và `voices`. Lý do: kiểm tay ~150 observation v4: `booking_needed` ~50%, `weather_exposed` ~60% (đảo nghĩa "mái che kín"), `long_walk` ~65%. Kiểm chứng: 16 câu chuẩn 18/18 đúng; 6 place thật v4 → v5: bỏ 3/3 `booking yes` sai ở một quán, weather sai giảm 7 → 3, recall effort gần như giữ; `absent` vẫn hiếm (1 / 6 place).

## corpus-aggregate — Signal + xu hướng theo địa điểm

- file: `src/corpus/aggregate/` (`__init__.py`, `place.py`, `estimates.py`), `config/category_defaults.yaml`, `tests/aggregate/`
- cách kiểm chứng: `python -m pytest -q tests/aggregate`; `python -m corpus aggregate`

### Hiện tại (2026-10-02)
- hành vi: mỗi feature có `quality` (độ chính xác đo bằng nhãn của giá trị đứng đầu), `servable` (nguồn thẩm quyền, qua ngưỡng nhãn, hoặc người `accept`), `review_decision`; quyết định `feature_review` của người: `disable` → `status = disabled`, `accept` bỏ `needs_review`, `report` / `refresh` đặt `needs_review`. File observation ontology cũ vẫn được đọc tới khi observe chạy lại (trước đây bị bỏ: đổi ontology là xóa sạch intel); intel ghi `observation_versions`. `estimates` (`aggregate/estimates.py`, `config/category_defaults.yaml`): nhóm category, thời gian tham quan [ngắn, thường, dài] (review khi ≥ 3 tác giả đồng ý, còn lại mặc định theo category), giá vé VND (số tiền trong quote `entry_fee`, mỗi tác giả một giá trị lớn nhất, hoặc vé Maps), `usable_as` mặc định, `effort_hint` (chỉ để xếp hạng: dốc có ở 16% nhà hàng, 37% quán cà phê đã có bằng chứng). Lần chạy: 1.437 nơi, 100% có thời gian tham quan (51 từ review), 241 có giá vé.

### Trước đó (2026-10-01, đêm)
- hành vi: thêm `mention_rate` mỗi feature (tác giả nói / `voices`), `identity` (category, lat, lng, address), `operation.hours` / `closure`. Lý do: feature chỉ `present` có `agreement` luôn 1 (1/250 review nói view đẹp vẫn là "có view"); Place Decision cần giờ mở cửa, đóng cửa, vị trí. Quy tắc: `docs/CORPUS.md` §5 Aggregate.

## corpus-observe-tiktok — Observation từ video TikTok

- file: `src/corpus/observe/tiktok/extract.py`, `VIDEO_OBSERVE` + `VIDEO_VERIFY` trong `src/corpus/llm/tasks.py`, `tests/observe/tiktok/`
- cách kiểm chứng: `python -m pytest -q tests/observe/tiktok`; `python -m corpus tiktok observe --limit 5` (mạng UIT)

### Hiện tại (2026-10-02)
- hành vi: mỗi cặp (video, địa điểm) trong `place_verify.evidence_pairs()` → một call đọc caption, segment transcript `ok` / `fixed` (đánh số, có giây) và 4 keyframe khi video chỉ nói về nơi đó. Gate: quote lời nói phải nằm trong đúng segment, quote caption trong caption / hashtag, observation từ khung hình chỉ cho giá trị ảnh chứng minh được (`FRAME_VALUES`: bậc thang, trong nhà / ngoài trời, đông, view, hoa, thiên nhiên, chỗ ngồi ngoài trời, decor, cắm trại, đường xấu; không `absent`, không suitability, không "vắng" vì video quảng cáo quay phòng trống). Feature `check: span` đọc lại (`VIDEO_VERIFY`: segment quanh quote hoặc đúng khung hình). Một phiếu mỗi người đăng, ngày = ngày đăng. Ghi `data/tiktok/observations/<fid_dir>.json`; `aggregate` đọc không đổi code (loại nguồn `video`). Thử 5 nơi: trích đúng "giá cả rất là bình dân", "nằm trong căn nhà cổ hơn trăm năm tuổi", "nhớ đặt lịch trước"; lỗi đã sửa: cầu thang trong ảnh bị gán `nature`, chó trong ảnh thành `animals`. Chạy chung key Gemma với `gmaps observe` gặp 429 → `scripts/after_rerun.sh` chạy sau khi observe Maps xong.

### Trước đó
_không có_

## corpus-serving — Serving record cho Place Decision

- file: `src/corpus/serving/` (`record.py`, `groups.py`, `run.py`), `config/serving.yaml`, `config/eval_trips.yaml`, `tests/serving/`
- cách kiểm chứng: `python -m pytest -q tests/serving`; `python -m corpus serving` rồi `python -m decision evaluate`

### Hiện tại (2026-10-02)
- hành vi: `serving` đọc intel → `data/serving/places.json`: trạng thái theo khía cạnh (`VERIFIED` khi `servable` và còn mới; chưa đo / xung đột / đồng thuận thấp → `UNCERTAIN` kèm lý do; quá cửa sổ độ mới → `OUTDATED`; `NEEDS_REVIEW`, `DISABLED` không xuất hiện), nơi đóng cửa (tạm hoặc hẳn) không vào; giờ / giá là fact có độ mới, thời gian tham quan / giá vé / `effort_hint` là estimate; `usable_as` = mặc định category trừ `experience` khi coverage `NONE`; `check()` fail-closed (pass cần giá trị chắc chắn mà không ai nói ngược). Khu vực: leader clustering bán kính 1,2 km quanh nơi đông nhất (118 khu). Gần trùng: cùng nhóm category + vai trò, Jaccard ≥ 0,6 trên feature "loại nơi" được ≥ 2 người và ≥ 3% người viết nhắc, so với leader (không nối chuỗi: single linkage cho một nhóm 416 nơi). MMR. 1.394 nơi trong ~11 s.
- đo: `serving/evaluate.py` đã bỏ; `python -m decision evaluate` chạy đúng pipeline thật thay nó. Lần chạy gần nhất: 0 vi phạm ràng buộc cứng, 0 `unknown` trong danh sách chính, gần trùng 0%; 18/30 chuyến không đủ 8 nơi vì mọi điều kiện effort / thời tiết / chặt chém chưa có giá trị `pass` nào được đo (chưa có nhãn, `absent` hiếm).

### Trước đó
_không có_

## corpus-photos — Ảnh Google Maps làm bằng chứng

- file: `src/corpus/crawl/gmaps/photos.py`, `src/corpus/observe/gmaps/photos.py`, `PHOTO_OBSERVE` + `PHOTO_VERIFY` trong `src/corpus/llm/tasks.py`, `src/corpus/crawl/common/browser.py` (user agent), `scripts/after_photos.sh`, `tests/crawl/gmaps/test_gmaps_photos.py`, `tests/observe/gmaps/test_gmaps_photo_observe.py`
- cách kiểm chứng: `python -m pytest -q tests/crawl/gmaps tests/observe/gmaps`; `python -m corpus gmaps photos --limit 5` rồi `python -m corpus gmaps photo_observe --limit 5` (mạng UIT)

### Hiện tại (2026-10-02)
- hành vi: quy tắc ở `docs/CORPUS.md` §4 Observe (Ảnh Google Maps). Phát hiện khi dò: Chrome headless bị Google cho Maps "chế độ bị hạn chế" (không tab review / ảnh) dù đăng nhập → `open_profile` / `open_sessions` dùng user agent Chrome thường, `check_signed_in` dừng khi gặp thông báo. Thử 4 nơi: lần đầu `setting` suy từ ảnh món ăn, một ảnh vừa `indoor` vừa `outdoor`, "vài bậc ở cửa" thành `steep_or_stairs` → prompt chỉ cho `setting` từ khu khách ngồi / đi, bậc thang phải là leo dài, gate bỏ ảnh có hai giá trị. Ảnh cận cảnh vẫn đôi khi thành `indoor` (yếu; aggregate đếm theo người đăng). Thư viện "Tất cả" của nhiều nơi phần lớn là ảnh cũ (một nơi 30 ảnh cũ / 0 giữ). Tốc độ crawl ~2,6 nơi/phút ở 3 tab.

### Trước đó
_không có_

## corpus-ontology-v7 — Giá trị phủ định cho ràng buộc cứng

- file: `config/ontology.yaml`, `REVIEW_OBSERVE` trong `src/corpus/llm/tasks.py`, `scripts/observe_prompt_eval.py`
- cách kiểm chứng: `python scripts/observe_prompt_eval.py` (37/37, 2026-10-02)

### Hiện tại (2026-10-02)
- hành vi: `tourist_trap`, `rough_road_access`, `cash_only` có thêm `absent` ("không chặt chém, đúng giá niêm yết", "đường nhựa, xe vào tận cổng", "có chuyển khoản"); "giá rẻ, hợp lý" vẫn chỉ là `value_for_money`. Lý do: `evaluate` cho 0 ứng viên chính ở chuyến "không chặt chém" / "không đường xấu" vì im lặng không phải bằng chứng (người dùng chọn phương án thêm giá trị phủ định). Chạy lại observe toàn bộ từ 10:24.

### Trước đó
_không có_

## trip — Trip Understanding: hội thoại ngắn tới Search Input

- file: `src/trip/` (toàn bộ), `config/trip.yaml`, `tests/trip/`, `web/src/user/tu/`, `web/src/user/screens/Understand.tsx`, `web/src/user/screens/understand/`, `web/src/user/css/chat.css`, `web/src/user/css/ask.css`, `docker/searxng/`
- cách kiểm chứng: `python -m pytest --collect-in-virtualenv -q tests/trip tests/index`; `node logs/bench_trip/shots_ask.mjs` (thẻ một câu, khung ảnh, ảnh vào `frontend_images/`); `logs/bench_trip/converse.py` (5 người dùng mô phỏng trên sol); harness + `/app/understand` (Playwright: "vibe retro" → thẻ dấu hiệu → thẻ các kiểu → bảng nơi; gửi ảnh một nơi); `curl 'http://127.0.0.1:8888/search?q=retro&format=json'`

### Hiện tại (2026-10-15)
- hành vi: mỗi lượt một câu hỏi (`docs/TRIP_UNDERSTANDING.md` §5). Agent đào sâu lời người dùng (chữ, hoặc `ask_user` 2–3 lựa chọn) hoặc chọn mục bắt buộc kế bằng `ask_required`; app chỉ chọn khi agent không hỏi. Người dùng đi trước: agent hỏi/đào theo mạch của họ (kể cả khi họ xin gợi ý), mục bắt buộc chỉ đến khi mạch đó xong, không còn code chặn câu hỏi thứ ba; cổng đọc lại vẫn hỏi đủ mục bắt buộc trước khi lập lịch. Bấm thẻ mục bắt buộc hoặc thẻ ảnh không gọi model (`NOTED_SAY`, thẻ kế do app chọn); lựa chọn do agent viết vẫn để agent đọc. Ngày đã có trong `keyword_hints` thì agent ghi thẳng, không gọi tool tính ngày. Lời agent bỏ dấu `**` markdown. Deck ở màn chat chỉ còn một tab, tối đa 3 lựa chọn mỗi nhóm (`deck.best`); sheet đọc lại vẫn đủ. Chọn trên thẻ: code ghi, rồi agent chạy một lần (`picked`) để phản hồi và chọn câu kế.
- agent: role Agent chạy sol 6.1 qua 9router, reasoning `low`, `prompt_cache_key` mỗi task, httpx client riêng mỗi call (sửa lỗi "bound to a different event loop"). `record_fact` nhận danh sách fact kèm `say` và `ask_required`: lượt thường một call. Danh sách tool cố định giữa các lượt (cache). Mỗi tool gọi phát một dòng `progress` (khối suy nghĩ). Clef kiểm lời agent kèm lời người dùng; guard cho nhắc lại tên nơi người dùng đã nói, bỏ qua tên chỉ gồm từ chung ("Khu Vui Chơi").
- web: `Ask.tsx` thẻ một câu kiểu AskUserQuestion (câu hỏi là dòng chat, 3 lựa chọn đánh số, dòng 4 gõ `Khác`, chọn một gửi ngay) và `PhotoStage` (carousel ảnh, nền mờ, Esc để sau); `useDeckForm` dùng chung với sheet đọc lại; Board ghi `Ngày đi` một dòng.
- Clef: hướng dẫn `SCOPE` / `DATA` viết lại (chỉ chặn số liệu khi cả tin nhắn chỉ xin số liệu; nhờ gợi ý, kể về chuyến đi là liên quan; dò hướng dẫn là phá hoại); bộ ca có nhãn `tests/trip/clef_cases.yaml` + test live: 0/51 chặn nhầm (trước 4); `CLEF_TIMEOUT_S` 2 s.
- drill ảnh: code dựng thẻ từ `config/trip.yaml` `drills` (10 chủ đề, 3–5 biến thể) và ảnh thật, song song với lần gọi agent (chờ thêm tối đa 3 s); agent không viết biến thể nữa; agent vẫn hỏi bằng chữ thì câu hỏi nhường cho ảnh (`drill_first`). Đo trên index thật (GPU 3): cả 10 chủ đề ra thẻ, 30–200 nơi mỗi biến thể, ~1–1,7 s mỗi thẻ khi index đã nạp. Giữ mọi biến thể có ảnh thật (tối đa 6); khung ảnh lăn chuột để xoay, có dòng hướng dẫn.
- số đo (bench v16, 5 người dùng mô phỏng trên sol `low`; v6 đầu ngày trong ngoặc): đủ mục bắt buộc 4/5 (persona còn lại chỉ thiếu ngày vì không chốt); lượt gõ: chữ đầu tiên hiện sau p50 3,3 s (6,6 s), xong p50 6,8 s / p90 10,4 s (7,6 / 13,8 s); 1,06 call model mỗi lượt gõ; tổng thời gian chờ để xong 4 phiên 66 s (324 s); 0 câu bị thay sau khi hiện, 0 câu dự phòng, 0 fact bị từ chối. Lời của lượt chỉ chạy ra (từng chữ, `say_stream_s` 0,6 s) khi đã qua mọi kiểm tra, không bao giờ hiện rồi bị thay; bỏ kiểm lời bằng Clef (0,5–1,2 s sau mỗi call), guard code vẫn chặn số / nơi chưa nói; câu hỏi của thẻ nằm chung bubble với lời bot (`Turn.tsx`, bỏ dòng "why"); user sửa bằng chat 7/7 ca được cập nhật (số ngày, phương tiện, người đi, ngân sách, ngày đi, sở thích ngược — soft cùng feature giờ loại trừ nhau —, bỏ mong muốn); `find_dishes` / `find_kinds` không còn là tool (đi qua `record_fact` field `dish` / `kind`); fact sở thích bị từ chối giữ thành `unmapped` không gọi lại (`refusal_kept`). Mức suy luận không đổi tốc độ (một call ~5,5 s ở `low` / `minimal` / `none`), giữ `low`. A/B `cx/gpt-6-luna`: call ~3,2 s, tổng chờ 4 phiên 62–64 s (sol 112–121 s), trường cứng như nhau; luna từng ghi hard `local_specialty_food=present` từ "nhất định phải thử bánh căn" → guard giờ từ chối hard "phải có" cho feature trải nghiệm. Agent prod vẫn là sol. Thẻ ảnh ~20–50 ms nhờ điểm chấm offline (`python -m trip drills` → `data/trip/drill_scores.json`, nạp khi khóa khớp; không khớp thì chấm lúc khởi động bằng `drill-warm`) và cache `Looks.scored_by_cues` (trước ~2 s, ~10 s khi GPU bận). Thêm: tra sẵn món / loại nơi (`agent.lookups`, `record_fact` field `dish` / `kind`); `start_date` nhận chữ ngày của user; feature chọn theo nghĩa từ FEATURES, không gọi `search_features` trước; ngày prepass đã ghi đánh dấu `written`; "2 đứa nhỏ", "bà ngoại", "1 mình", "6 đứa" ghi được; câu hỏi riêng của agent nhường mục bắt buộc khi người dùng thôi dẫn mạch (`thread_done`); thẻ bắt buộc bị gác bằng lời thành `declined` (`put_off`); turn log có `t_call` / `t_agent` / `t_turn`.

### Trước đó (2026-10-13)
- hành vi: một khung chat theo `docs/design/desktop/v4-chat-cards/mock.html`, bỏ thanh Trò chuyện / Trắc nghiệm nhanh. Lời agent không hỏi gì (và chuyến đã được kể) thì câu kế tiếp của `quiz_queue` hiện thành nút trả lời nhanh; agent lỗi / Clef trả câu cố định thì chỉ có ô gõ. Gõ khi nút đang mở: other-gate đọc được thì ghi, không thì là tin nhắn chat (bỏ đường vòng `resolving_other`). Thẻ cũ còn trong `quiz_queue` vẫn trả lời được.
- phong cách và ảnh (`docs/TRIP_UNDERSTANDING.md` §18): tool `ask` (`look` với dấu hiệu + `where`, `this_or_that`), `web_search` / `web_read` (SearXNG tự host trong Docker, cache `data/web_cache`); `Vibe` trong Trip State; thẻ dấu hiệu → thẻ các kiểu (cụm ảnh thật từ `corpus.index`) → `vibes[].places`; ảnh user gửi (`kind: image`) qua Embedder + Extractor `PHOTO_CUES`, khớp rõ một nơi thì hỏi "có phải X?". Trả lời thẻ không gọi model. Search Input thêm `vibes` (chỉ vibe `done`); Decision cộng `vibe` (trọng số 0,8).
- sự kiện `progress` (các bước, nguồn) phát trực tiếp qua harness; `understanding.board` (24 nơi, nơi của vibe lên đầu) và `understanding.vibes`.
- web: chat trái (khối các bước co lại, thẻ co thành `✓ câu trả lời`), bảng nơi phải (số nơi chạy số, lọc theo loại, thẻ nơi mở PlaceSheet, ♡ lưu), ô nhắn kèm ảnh thu nhỏ ≤ 448 px; màu hồng `.tg-rose` chỉ cho trang này. Bỏ `TripChat.tsx`.
- giới hạn: `ask` do Gemma tự quyết (có lượt nó ghi `unmapped` trước rồi mới `ask`); với từ quen ("retro", "wabi sabi") agent không tìm web. Tên kiểu dùng tag phong cách khi đủ nơi mang tag, không thì "Kiểu như <nơi đầu>".

## corpus-index — Chỉ mục ngữ nghĩa (tag phong cách, vector ảnh và chữ)

- file: `src/corpus/index/` (`embedder.py`, `vectors.py`, `compile.py`, `query.py`), `src/corpus/observe/gmaps/styles.py`, `config/index.yaml`, `config/styles.yaml`, task `STYLE_OBSERVE` / `PHOTO_CUES` (`src/corpus/llm/tasks.py`), `tests/index/`
- cách kiểm chứng: `python -m pytest -q tests/index`; `python -m corpus gmaps style_observe`; `python -m corpus index`; truy vấn mẫu `Index.load().embed_text("đèn vàng, ghế gỗ, nhạc xưa")` → `search_photos` → `places_by_photos`

### Hiện tại (2026-10-13)
- hành vi: lớp B (tag phong cách từ ảnh Maps, ngoài ontology để không trích lại corpus) và lớp C (SigLIP2 cho 29.820 ảnh Maps + frame TikTok, bge-m3 cho 476.666 câu trích dẫn) của `docs/CORPUS.md` §Chỉ mục ngữ nghĩa; 8 GPU: ảnh Maps 376 s, frame 203 s, câu trích dẫn 70 s (2026-10-13; ảnh đọc từ ổ mạng là nút thắt, GPU dùng thấp). `compile` ghi `data/index/<version>/` (LanceDB) và `current`. API online: `search_photos`, `places_by_photos`, `similar_places`, `clusters`, `dominant_style`.
- `style_observe` chạy được trên UIT (`EXTRACTOR_ON_UIT=1`) hoặc host LAN; chung key với Judge thì 429, làm lại phần lỗi.
- chưa làm (`docs/superpowers/specs/2026-10-12-corpus-semantic-index-design.md`): lớp A (feature tiện ích), mask numpy / ma trận độ giống cho Decision, bộ câu khó để đo precision.

### Trước đó
- _không có_

## decision — Place Decision: Search Input tới Decision Output

- file: `src/decision/` (toàn bộ), `config/decision.yaml`, `config/eval_trips.yaml`, `tests/decision/`, `web/src/user/pd/`, `web/src/user/screens/{Shortlist,PlaceDetail,Compare,Curate,Feasibility}.tsx`
- cách kiểm chứng: `python -m pytest -q tests/decision`; `python -m pytest -m live tests/decision/test_decision_live.py`; `python -m decision serve` + `/app/shortlist`; `python -m decision evaluate`

### Hiện tại (2026-10-15)
- hành vi: như bản trước; mọi mong muốn của Trip quy về một thành phần điểm `wish` (`decision/wishes.py`) thay `vibe_fit`: món (`wishes.dishes`, mọi nơi có ghi món đó), kiểu nơi (`wishes.kinds`), phong cách ảnh (`vibes`), giống X (`wishes.like`, `corpus.serving.similarity` ≥ `like_min`, trừ X), `liked_groups`, `purpose` (map trong `config/decision.yaml` `wish`). `wish = 1 − Π(1 − a·strength)`, chỉ nâng, không loại, không âm; danh sách vẫn đủ mọi nơi qua sàng lọc. `rank.score` và `frame.score_table` cùng tính; memo thêm tầng `wishes`.
- lý do: `card.why` nêu mong muốn trước ("Có bánh căn bạn muốn · theo menu"), `purpose` mang ✎; thẻ không có lý do nào có một dòng dự phòng (thành phần lớn hơn giữa vị trí và số người viết). Lưới và đĩa xoay đọc cùng `ui/cardLines.ts` (3 lý do, đánh đổi, 2 cảnh báo); đĩa xoay bỏ mức "Rất hợp / Hợp" tự đếm ở web. `why_not` thêm mong muốn chưa khớp ("Chưa thấy ghi món …"). Nơi chưa có bản ghi không được cộng. "Giống X" khi X thiếu tên nói "nơi bạn nhắc tới". `rank.vibe_fit` đã bỏ.
- đo (snapshot 3.208 nơi, 30 chuyến eval + 3 món thật, 2 kiểu, 1 giống X, `liked_groups`, `purpose`; máy tải ~150): chạy đầu trung vị 64 ms, p95 78 ms; memo trúng trung vị 18,3 ms (không mong muốn: 16 ms; nguồn món cache trên `Cand`); dựng mong muốn 2,2 ms. Test: `tests/decision/test_wishes.py`, `test_wish_cases.py` (15 ca persona + bất biến), `test_wish_speed.py` (marker `corpus`).

### Trước đó (2026-10-08)
- hành vi: như bản trước, thêm ba điểm. (1) Không cắt ở shortlist nữa: mỗi nhóm hiển thị có thứ hạng đầy đủ (nơi đã chọn → nơi MMR `top` → mọi nơi còn lại theo `score`), view chỉ mang cửa sổ đang hiện (`window.py`, `State.shown`, `page_size` 24) kèm `total`; `read page` nối trang tiếp. Dữ liệu thật chuyến 3 ngày: 116 / 193 / 424 / 545 nơi, view 114 KB. (2) Dựng lại thì gộp ít xáo trộn: nơi còn khớp đứng nguyên ô, ô trống nhận nơi mới hợp nhất, cửa sổ phần lớn lỗi thời thì thay hết; view có `change` mỗi nhóm cho web chạy chuyển cảnh. `first_shortlist` = số card `top` + anchor. (3) Lượt chữ: op `soft` / `unmapped` thay bằng `trip`; engine phát event `trip`, harness chuyển cho Trip `refine` rồi `rebase` (`docs/AGENT_HARNESS.md` §2). Đo trên journey thật: "không thích quán giống Miền Du Mục" → 4 soft `avoid` từ nét của nơi đó, nhóm cà phê giữ 23 / thay 1, ăn uống giữ 22 / thay 2.
- web: lưới tự tải khi cuộn (3 thẻ khung, dòng "Đã xem hết"), nhãn "Hợp nhất", header "N nơi hợp… · Chat để thu hẹp" kèm "−N nơi" khi số đổi, tab "+N mới", chuyển cảnh `useStagedList` + FLIP. Đĩa xoay làm lại: nửa đĩa 180° quay vòng không có điểm đầu, cánh là mảnh vành khuyên khép thành vòng liền, tối đa 7 cánh để ảnh to, ít nơi thì cánh to hơn (180° / số nơi, tối đa 45°); lăn / kéo trên đĩa xoay đĩa, phần nội dung cuộn như trang; nhóm thành tab có chữ, bỏ hàng "Nơi trước / Nơi sau" (trước đây lăn ở đâu cũng xoay đĩa, cánh hình thang nhỏ, nút nhóm chồng nhau ở 1280×720, hàng điều hướng bị cắt ở 1440×900).
- sau lượt chat có mong muốn: câu trả lời kết bằng `diff(rebuilt=True)` ("Giữ 45 nơi, thay 3 nơi hợp hơn"); thay đổi không xê dịch gì thì không có câu báo (trước đây "0 nơi, 0 phút…"); `rebase` giữ lịch sử hoàn tác; `why-not` chỉ chỗ của nơi nằm dưới phần đã tải; prompt agent chỉ có lý do cho trang đầu mỗi nhóm. `backup_pool` và hai bản đo offline chỉ dùng nơi `top`.


## planning — Lịch trình từ Decision Output tới Plan Output

- file: `src/live/` (`osrm/`, `weather/`, `lodging/`, `geocode/`, `sun.py`, `holidays.py`, `events.py`, `advisories.py`, `cache.py`), `src/planning/` (toàn bộ), `config/planning.yaml`, `config/live.yaml`, `config/climate.yaml`, `config/holidays.yaml`, `config/events.yaml`, `config/advisories.yaml`, `tests/live/`, `tests/planning/`, `web/src/user/planning/`, `web/src/user/screens/Itinerary.tsx`
- cách kiểm chứng: `python -m pytest -q tests/live tests/planning`; `python -m planning build|variants|lodging <decision_output.json>`; `python -m planning serve` (web qua `/api/planning`); `python -m planning evaluate` (cần OSRM, không chạy trong CI)

### Hiện tại (2026-10-08)
- hành vi: như bản trước, sửa hai lỗi tìm thấy khi chọn một nơi: (1) phí chia ngày bằng nhau thì ngày sớm hơn nhận nơi (`days.assign_days`); trước đó DP trao cho ngày sau nên một nơi duy nhất rơi vào Ngày 2 và Ngày 1 trống. (2) Nơi có nhiều ghim theo giờ chỉ giữ ghim người dùng muốn (`build.prepare`): Đèo Mây Farm với "săn mây" giờ xếp 06:00 thay vì 16:03 (ghim hoàng hôn). Web mở Lịch trình ở ngày đầu tiên có điểm dừng.

### Trước đó (2026-10-07)
- hành vi: như bản trước, thêm điều kiện từng ngày (`planning/conditions.py`, `docs/PLANNING.md` §Điều kiện từng ngày). `Engine` gọi `conditions.fetch_live`: trước đây engine không lấy thời tiết nên kế hoạch online không xét mưa. Giờ mỗi ngày có `DayCond` từ Open-Meteo (mưa mm, gió giật, dông), `holidays.yaml`, `events.yaml` (lễ hội, Noel, Tết) và `advisories.yaml` (thông báo nhập tay có nguồn). Ngày dông / mưa lớn tính như ngày mưa; ngày rất xấu hoặc thông báo `severe` không cho xếp nơi bị ảnh hưởng (validate báo `hazard`, không ngày nào xếp được thì `back_to_decision`); nơi đông vào cuối tuần / lễ tăng thời gian chờ và đệm, bị phạt khi chia ngày (nặng hơn nếu người dùng tránh đông); dịp Tết có cờ đóng cửa và nơi ăn uống thành nơi nhạy cảm với dự phòng. Output thêm `day_conditions`, `crowd_tips`; Web hiện trên ngày đang chọn.
- không đổi: khi không có tín hiệu nào, lịch giống hệt trước (golden không đổi).
- sửa: kế hoạch hiện ra là hợp lệ nhưng không xác nhận được (`plan has unresolved violations`) khi bộ xếp lịch đã bỏ ghim giờ của một nơi: `DayResult.unpinned` ghi lại, `validate` tôn trọng. Plan Output đã chốt giữ `day_conditions`, `crowd_tips`. Phát hiện bằng `scripts/journey_sim.py` (mô phỏng 11 kiểu người dùng + hành vi ngẫu nhiên trên dữ liệu thật, không gọi model).
- giới hạn: thông báo thiên tai và lễ hội nhập tay (chưa có nguồn tự động; `advisories.yaml` rỗng không có nghĩa an toàn); ngưỡng thời tiết, hệ số đông khách là ước lượng chờ pilot; chưa kiểm cửa hàng đóng tạm thời trực tiếp (`place_live_status`).

## planning-schedule-cost — Lịch trình, chi phí và kiểm tra độc lập

- file: `src/planning/{composer,details,timefit,validate}.py`, `tests/planning/test_planning_{composer,details,validate}.py`; contract hiện tại: `docs/PLANNING.md` §Thuật toán và §Vòng người dùng sửa và góp ý.
- cách kiểm chứng: `python -m pytest -q tests/planning/test_planning_consistency.py tests/planning/test_planning_meal_timing.py tests/planning/test_planning_objectives.py tests/planning/test_planning_output.py tests/planning/test_planning_validate.py tests/planning/test_planning_details.py tests/planning/test_planning_timefit.py tests/planning/test_planning_schedule.py`; thêm `tests/planning/test_planning_composer.py` cho tìm phương án quá tải.

### Hiện tại (2026-10-12)
- hành vi: tiết kiệm ưu tiên giảm số giá hoàn toàn chưa ước lượng được trước khi so tổng chi phí; đổi một nơi lấy nơi khác vẫn giữ `composer.alpha` giá trị selection. Không nội suy giá từ nhóm khác hay coi giá thiếu là miễn phí.
- giờ ghé: thưởng/phạt từ review theo tỷ lệ toàn bộ khoảng ghé nằm trong khung tốt/xấu; phần bằng chứng mâu thuẫn triệt tiêu theo từng khoảng giao.
- validator: lịch đầy đủ kiểm bữa từ visit thực tế, không phụ thuộc `DayResult.order`; visit phải đạt `short`. Cache phụ thuộc record của visit và endpoint travel thực tế, nên đổi thời lượng/giờ mở/chặng không bỏ sót lỗi.
- kiểm chứng: 136 test tập trung pass, bỏ hai test composer nặng đã pass ở lần chạy trước; gồm 8 test hồi quy mới về giá thiếu, giá trị selection, khoảng giờ ghé và validator/cache. Kiểm tích hợp toàn Planning/Decision/Harness trong workspace đang sửa đồng thời: 838 pass, 105 skip, 28 fail; lần chạy lại nhóm lỗi sau thay đổi nguồn khách sạn có 8 fail (golden, chọn nhánh variants và handoff), 41 pass, 26 skip. Kết quả tích hợp là ảnh chụp tại thời điểm chạy, chưa kết luận toàn repo xanh.
- giới hạn dữ liệu: giờ mở cửa chưa biết vẫn được xếp kèm cảnh báo; budget kiểm phần giá địa điểm đã biết, chưa chứng minh được tổng chi phí khi còn khoản thiếu. Thời lượng fallback là ước lượng, không phải observation. Chưa có transition/fatigue cá nhân hóa hoặc benchmark hiệu chỉnh từ phản hồi người dùng thật.

### Trước đó
_không có_

## landing — Landing bản đồ hành trình (máy tính) + Dùng ứng dụng (điện thoại)

- file: `web/src/user/screens/{Landing,GetApp}.tsx`, `web/src/user/landing/{scene,mascot,terrain,device}.ts`, `web/src/user/landing/{places,points,stats}.json` (sinh bằng `web/scripts/pick_landing_places.py`), `web/scripts/landscape/bake.ts` → `web/public/world/dalat.bin`, `web/scripts/shots_plates.mjs` → `web/public/img/landing-{poster,p1..p5}.webp`, `web/src/user/css/{landing,motion,tokens}.css`, `web/src/user/UserApp.tsx`; phụ thuộc `three`, `gsap`, `lenis`
- cách kiểm chứng: `npx tsc --noEmit -p web`; mở `/` ở 1440×860 (`?3d=off` buộc bản nhẹ, `?3d=on` buộc bản đồ sống) và cuộn hết 6 nhịp; bấm `Lên lịch chuyến của bạn` ở màn đầu và ở hộp cuối, trong lúc chuyển `document.getAnimations()` có `::view-transition-group(tg-l2h-frame|tg-l2h-mascot|tg-l2h-cta)` 560 ms và `root` 220 ms; `prefers-reduced-motion` thấy mọi khối hiện sẵn; giả UA iPhone mở `/` phải thấy trang Dùng ứng dụng

### Hiện tại (2026-10-16)
- hành vi: sân khấu sticky là bản đồ hành trình Đà Lạt sống, tông giấy kem: lớp phủ và dải độ cao nướng sẵn pha nhạt vào giấy, đường đồng mức, hồ, đường trục chính, lưới kinh vĩ mờ, 1.773 đốm vàng, 6 bưu thiếp ảnh thật, tuyến chấm đất nung; không còn cây / nhà / hoa / cánh hoa / tia nắng / đom đóm. Linh vật đám mây (logo) dựng bằng three.js (`mascot.ts`: toon + viền đất nung, mũ, bản đồ gập, tai nghe, bong bóng "…", con dấu) luôn bay to ở tiền cảnh, trôi quanh chỗ đậu của từng nhịp và vút giữa các nhịp: `hover` → `listen` → `pick` → quay sang bưu thiếp Thênh Thang → `walk` dẫn theo tuyến (camera bám điểm đang tới, giờ trên timeline sáng theo) → `stamp` "Đúng gu" rồi `wave`. `hour` nhuộm bản đồ bình minh → trưa → hoàng hôn theo ngày ví dụ. Nhãn DOM rơi vào linh vật thì ẩn. Landing dùng token trắng–đen + Be Vietnam Pro của app, bỏ hệ hồng và Lora; nút chính nâu `--tg-brown`; điểm nhấn `--tg-brand` #b4532a. Bấm CTA: camera nâng vào sương, chữ mờ (nút vừa bấm ở lại), ảnh logo thay linh vật 3D, rồi 3 phần tử chung bay sang `/app` (sân khấu hoặc hộp CTA cuối → ảnh hero, linh vật → logo thanh trái, nút → `Tạo chuyến đi`); hộp CTA cuối nền ảnh mây vàng của hero. Bản nhẹ và ảnh nền chụp lại từ bản đồ mới. Chữ các chương viết lại như người nói (lời kể → ghi chú của TripGuardian; thẻ gợi ý một chỗ; timeline mỗi chỗ một dòng), chương Lựa chọn nói đúng việc bạn tự chọn chỗ. Chương 1, 3, 4, 5 có khung ảnh giao diện thật (`web/src/user/landing/shots/app-*.webp`, chưa có ảnh nào). Điện thoại không đổi: trang Dùng ứng dụng.

### Trước đó (2026-10-12)
- hành vi: máy tính thấy màn đầu là thung lũng Đà Lạt 3D sống (three.js thuần, tải lười; kéo để xoay, nút `Xoay thử Đà Lạt 3D` mở khám phá tự do), chữ `Lịch trình Đà Lạt vừa với bạn.`, một CTA `Lên lịch chuyến của bạn` (lặp ở thanh trên và hộp cuối) ba cam kết `Miễn phí` · `Không cần tài khoản` · `Chỉ gồm nơi có thật` và nút nổi `Cuộn xuống để xem cách hoạt động` ở chân màn. Dưới màn đầu là ba bước tĩnh: Tìm hiểu nhu cầu (khung chat + thẻ chuyến đi), Tìm địa điểm phù hợp (thẻ lý do của Thênh Thang từ `places.json`: đánh giá Google, khung đông nhất cuối tuần, clip TikTok), Lịch trình của bạn (ví dụ một ngày 6 nơi thật, phút đi xe tính thô từ toạ độ bằng `road_factor` / `rough_speed_kmh` của `config/planning.yaml`). Rồi `Địa điểm thật` (4 ảnh ban ngày, nguồn ghi theo `credit` của từng ảnh), Hỏi nhanh 5 câu cạnh một dòng `Sắp có`, CTA cuối, footer. Cuộn mượt bằng Lenis, mỗi khối hiện một lần khi tới (GSAP ScrollTrigger); giảm chuyển động tắt cả hai. Thanh bước bên phải hiện chữ cả 3 bước. Nút CTA mở phiên khách nếu chưa có phiên. Điện thoại không đổi: trang Dùng ứng dụng.

## user-web — Giao diện người dùng chính thức (landing + `/app`)

- file: `web/src/user/` (`UserApp.tsx`, `screens/`, `ui/`, `css/`, `store.ts`, `lib.ts`, `landing/`), `web/src/App.tsx`; backend `src/harness/{dispatch,server,session}.py` (`preview`, `summaries`, `feedback`, `report`), `src/planning/engine.py` (`preview`, cache theo hash Decision Output), `src/decision/{engine,tools}.py` (`draft`, `report`)
- cách kiểm chứng: `npm run build:prod --prefix web`; `python -m pytest -q tests/harness tests/planning tests/decision tests/trip`; chạy harness + Vite rồi `node web/scripts/shots_app.mjs <url>` (đi trọn luồng với agent thật, chụp `web/shots/app/`)

### Hiện tại (2026-10-08, tối)
- hành vi: như bản trước; câu mở của Hiểu chuyến đi thành cuộc trò chuyện (`screens/TripChat.tsx`, `UI_SPEC_USER_WEB` §Trang 3 Mở đầu): AI hỏi, người dùng gõ (câu ở landing là tin nhắn đầu), lúc AI đọc hiện chấm gõ + lời stream + `“quote” → trường` từ sự kiện `preview`; xong thì dừng ở `Mình đã hiểu như này` (mỗi dòng có nguồn và nút sửa, giới hạn / nơi muốn đến bỏ được, chip sở thích có ×) + `Mình cần hỏi thêm một số ý` (`unknowns`), người dùng sửa bằng lời hoặc bấm `Đúng rồi, hỏi tiếp` mới sang chồng thẻ. Chuyển câu: thẻ rơi ngay khi bấm (trước: chờ 380 ms rồi mới gửi, thẻ cũ hiện lại và bị chia hai lần trong lúc chờ máy chủ), chồng thẻ nghiêng lên + chấm chờ trong lúc chờ, thẻ mới chờ thẻ cũ rơi xong; khoá thẻ theo lần nhận thẻ thay vì `hist.length` nên không chia lại khi lịch sử cập nhật; lượt trả lời vào lịch sử ngay nên `câu N` đúng từ lúc thẻ mới hiện; trang tự cuộn về đầu chồng thẻ khi thẻ mới khuất.

### Trước đó (2026-10-08, chiều)
- hành vi: như bản trước, tối ưu production: landing → hỏi chuyến không chờ snapshot (`/app/understand` tự render, landing tải trước snapshot lúc rảnh, covers + snapshot tải song song) — thẻ câu hỏi hiện sau ~0,4 s thay vì ~13 s qua Cloudflare. Câu gõ ở landing hiện thành thẻ "bạn kể" thay vì hỏi lại câu mở. Thẻ hỏi giữ một màu pine (trước đổi màu theo lượt). Ảnh dùng thumbnail WebP `/media/thumb` qua `srcset`, rơi về ảnh gốc khi thiếu. Thanh bước gọn một dòng trên điện thoại. Server: snapshot gọn + brotli (4,3 MB/10,5 s → 1,7 MB/0,9 s), ETag/304, keep-alive tới harness (README §Production).

## detail-logistics — Xem chi tiết, hiện hết gợi ý, hỏi hậu cần, chỗ ở theo gu

- file: `web/src/user/ui/{PlaceSheet,PlaceInput,SelectedBar}.tsx`, `web/src/user/screens/{Understand,Explore,Lodging,Plan}.tsx`, `web/src/user/pd/`, `web/src/user/tu/`, `web/scripts/{pick_covers,export_snapshot}.py`; `src/decision/{session,curation,engine,pipeline,output,contracts,scope}.py`; `src/trip/domain/questions.py`; `src/planning/{logistics,lodging,engine,frame,build,variants}.py`; `src/harness/{dispatch,server}.py`; `src/corpus/crawl/gmaps/listing.py`, `src/corpus/observe/gmaps/extract.py`, `src/corpus/aggregate/place.py`, `src/corpus/serving/record.py`
- cách kiểm chứng: `python -m pytest -q tests/planning tests/harness tests/decision tests/trip tests/crawl tests/serving tests/aggregate tests/observe`; `cd web && node_modules/.bin/tsc --noEmit -p .`

### Hiện tại (2026-10-12)
- hành vi:
  - "Xem chi tiết" là modal `PlaceSheet` như trước; Chọn nơi hiện hết ứng viên qua lọc, cuộn tải thêm; lưới không còn dòng "X và Y khá giống nhau".
  - Hậu cần ở Hiểu chuyến đi: tới Đà Lạt bằng gì, xuất phát từ đâu (mọi chuyến), đã có chỗ ở chưa. Không còn thẻ chọn chuyến bay / xe khách (bỏ `TransitPick`, `/api/harness/transit`).
  - Chỗ ở: chọn ở tab "Chỗ ở" của Chọn nơi (khi chưa có chỗ ở đã đặt). Danh sách là chỗ ở trong corpus (nhóm `stay`, 1.524 nơi Đà Lạt) quanh các nơi đã chọn, Planning xếp theo gu trước, vị trí sau (`read/decision/lodging`); chọn = Decision `set_lodging`, đi vào Decision Output `lodging`. Planning không cào Maps. Màn "Bạn ở đâu?" trước lịch đã bỏ; "Đổi chỗ ở" quay về tab đó.
  - Mọi ngày bắt đầu và kết thúc ở chỗ ở (bỏ neo `@entry` / `@exit`).
  - (2026-10-13) Tab "Chỗ ở" dùng thẻ cùng kiểu thẻ địa điểm, luôn hiện danh sách (chưa chọn nơi nào thì xếp theo gu + đánh giá, tối đa `lodging_list_k`); đã có chỗ ở thì thẻ khác hiện "Đổi sang chỗ này" và hỏi xác nhận; chỗ ở là một dòng đầu trong giỏ; chỗ ở đã chốt ở Hiểu chuyến đi (`booked.id`) hiện "Đã chọn"; câu hỏi chỗ ở đổi lời. Chưa xem trên trình duyệt.
  - Không chặn: "Lập lịch" luôn bấm được khi đã chọn ít nhất một nơi; quá tải / vướng / chưa có chỗ ở chỉ hiện thông báo; Planning không bắt buộc chỗ ở.
  - Giá một đêm của chỗ ở: thẻ danh sách khách sạn Maps (741 / 1.524 nơi có giá) → `list/dalat_stay.json` → `place_facts.price_night` → serving `operation.price_per_night`.

### Trước đó (2026-10-08)
- hành vi:
  - "Xem chi tiết" là một modal `PlaceSheet` (`?place=<id>`, Back / Esc đóng, ảnh bay vào chỗ bằng View Transitions / FLIP) mở từ đĩa, lưới, anchor, trợ lý, thanh "Đã chọn"; tab Hình ảnh hiện ≤ 12 ảnh/nơi do `pick_covers.py` chọn (YOLO + pHash + Gemma `photo_rank`; 1.704 nơi có gallery), thumbnail WebP cho mọi ảnh mới (`make_thumbs.py`).
  - Chọn nơi hiện hết ứng viên qua lọc: cuộn tải thêm 24 nơi/lần; chat thu hẹp giữ nơi còn khớp đúng chỗ (`docs/PLACE_DECISION.md` §9.2–9.4).
  - Trip Understanding hỏi hậu cần trước `ready` (`docs/TRIP_UNDERSTANDING.md` §Hậu cần); web: ô gõ có gợi ý cho xuất phát / chỗ ở, danh sách chuyến bay / xe khách thật (cache, thiếu thì crawl nền + SSE, lỗi thì mở trang đặt vé + nhập tay giờ), các dòng mới trên vé chuyến.
  - Chỗ ở: corpus có nhóm `stay` chỉ Planning đọc; Planning xếp chỗ ở theo gu trước, vị trí sau (`docs/PLANNING.md` ⓐ); chưa có chỗ ở thì web hiện "Bạn ở đâu?" một lần trước lịch; đã đặt thì lịch neo thẳng vào chỗ đó.
  - Đo 2026-10-08: chuyến bay SGN→DLI `pending` → `ready` sau ~18 s (5 chuyến), lần sau từ cache; xe khách ~1,5 s.

## tiktok-place-poi — Địa điểm TikTok (POI) của từng nơi Maps

- file: `src/corpus/crawl/tiktok/{place_poi,poi_crawl,clips}.py`, `crawl.py` (`poi_of`, `video.json.poi`), `place_filter.py` (`places_by_video` đọc `poi_crawl/`), `src/corpus/llm/tasks.py` (`PLACE_POI_MATCH`), `scripts/free_tiktok_clips.py`, `web/server.mjs` (mp4 có Range), `web/scripts/export_snapshot.py`, `web/src/user/ui/PlaceSheet.tsx` (`<video>` khi `local`), `tests/crawl/tiktok/test_tiktok_{place_poi,poi_crawl}.py`
- cách kiểm chứng: `python -m pytest tests/crawl/tiktok -q`; `python -m corpus tiktok place_poi --city dalat` rồi đọc mẫu `data/tiktok/place_poi/dalat.json`

### Hiện tại (2026-10-09)
- hành vi:
  - Mô tả phase và layout file: `docs/CORPUS.md` §1 (Phase 2, `place_poi/`). `video.json` mới có `poi`; video cũ đọc `poi` từ `info.json` (5.722 / 11.356 video có gắn).
  - Đo 2026-10-09, Đà Lạt: 983 nơi có ứng viên, 709 nơi được gán; 2 lần đọc lệch nhau ở 91 cặp (`unsure`). Một lần đọc đơn: 43 / 983 nơi đổi kết quả giữa hai lần chạy giống nhau, có ca sai kiểu "Nhà Hàng Datanla" = khu du lịch thác. Mẫu 20 nơi đã gán (trước luật một POI một nơi): 17 đúng rõ.
  - Thử trang POI (`tiktok.com/place/<slug>-<poi_id>`): mở được khi không đăng nhập, không captcha; `/api/poi/item_list/` trả 25–30 item / trang kèm `playAddr` h264 tải được bằng phiên ẩn danh; một quán 1.009 video / 44 trang trong ~6 phút, không bị chặn.
  - `poi_crawl` lô đầu 20 nơi: 90 video / nơi liệt kê trong 12–16 s, 187 video tải; 1 nơi dính 403 cả 10 lần tải cùng lúc, chạy lại thì được. Tỉ lệ `place_verify` = yes của video trang POI: chưa đo.

### Trước đó
- _không có_

## accounts — Tài khoản, Postgres (`docs/ACCOUNTS.md`)

- file: `src/db/`, `migrations/`, `src/accounts/`, `src/harness/server.py`, `run.sh` (`db`, `db-backup`), `web/src/user/{account.ts,screens/Auth.tsx,screens/Account.tsx,screens/Guest.tsx}`
- cách kiểm chứng: `./run.sh db` (chạy lại → `nothing new`); `TEST_DATABASE_URL=<DATABASE_URL> python -m pytest -q tests/db tests/accounts tests/harness`; walk Playwright với `TG_TEST_LOGIN=1` + `APP_BASE_URL` http; walk khách (CTA landing → `/app`, Hôm nay 403, kết thúc phiên) trên harness + schema tạm

### Hiện tại (2026-10-12)
- hành vi: Postgres riêng (container `tripguardian-pg`, 127.0.0.1:5433, role `tg_app` / `tg_analytics`, migration SQL đánh số). `/app` cần đăng nhập Google (code + PKCE, state server + cookie), cookie `tg_session` 30 ngày trượt, đồng ý điều khoản lần đầu. Hồ sơ (avatar 256 px WebP, tên, thành phố, phương tiện, người đi cùng) là prior `source = profile` cho Trip. Xóa tài khoản giữ dữ liệu ẩn danh. Mọi `/api/harness/*` cần phiên (401), mutation kiểm `Origin` (403), hành trình người khác 404; hành trình lưu ở bảng `journeys` (`PgStore`, kiểm revision khi ghi), feedback ở bảng `feedback`; `import-files` nạp file cũ. Khách (`users.kind = 'guest'`, migration 003): `POST /api/auth/guest` mở phiên 24 giờ trượt, lập chuyến như tài khoản (không giới hạn số chuyến, không prior hồ sơ, không học), không có Hôm nay / thông báo / Calendar / hồ sơ (403 `guest`); hết phiên thì xóa khách và chuyến, giữ `journeys` / `events` ẩn danh; đăng nhập Google chuyển chuyến của khách sang tài khoản; mỗi địa chỉ tối đa 20 khách / giờ.

### Trước đó (2026-10-09)
- hành vi: Postgres riêng (container `tripguardian-pg`, 127.0.0.1:5433, role `tg_app` / `tg_analytics`, migration SQL đánh số). `/app` cần đăng nhập Google (code + PKCE, state server + cookie), cookie `tg_session` 30 ngày trượt, đồng ý điều khoản lần đầu. Hồ sơ (avatar 256 px WebP, tên, thành phố, phương tiện, người đi cùng) là prior `source = profile` cho Trip. Xóa tài khoản giữ dữ liệu ẩn danh. Mọi `/api/harness/*` cần phiên (401), mutation kiểm `Origin` (403), hành trình người khác 404; hành trình lưu ở bảng `journeys` (`PgStore`, kiểm revision khi ghi), feedback ở bảng `feedback`; `import-files` nạp file cũ.

## companion — Đang đi, Calendar, thông báo (`docs/COMPANION.md`)

- file: `src/companion/`, `src/notify/`, `config/{companion,notifications}.yaml`, `web/src/user/{today.ts,notify.ts,screens/Today.tsx,screens/Inbox.tsx}`, `web/public/{sw.js,manifest.webmanifest}`
- cách kiểm chứng: `TEST_DATABASE_URL=… python -m pytest -q tests/companion tests/notify`; `python -m notify run --once`; walk màn Hôm nay ở 1440 và 390 px

### Hiện tại (2026-10-09)
- hành vi: chốt lịch tạo `trips` / `trip_stops`; màn `/app/today` với Đã đến tự nguyện, bỏ qua, Hợp / Không hợp, gợi ý "Ở đây" chỉ từ serving (hard filter fail-closed, giờ chưa xác nhận giữ nguyên), "Tôi đang ở nơi khác", dòng "Phần còn lại hơi chật" với phương án `on_delay` qua Planning khi người dùng xác nhận. Google Calendar: calendar riêng mỗi chuyến, không reminder, xem trước → xác nhận theo `preview_hash`, lệch thì chỉ báo `drifted`. Thông báo 9 loại, giờ yên lặng 22–7, 1 / 3 mỗi ngày, tạm im sau 3 lần bỏ qua, biến thể thiếu dữ liệu thì không gửi, bandit khi đủ 200 lượt; web push + hộp thông báo; worker `python -m notify run`.

### Trước đó
- _không có_

## analytics — Event và Analytics (`docs/ANALYTICS.md`)

- file: `src/harness/events.py`, `src/analytics/`, `web/src/user/events.ts`, `web/src/admin/{analytics.ts,screens/Analytics.tsx,AnalyticsTabs.tsx,Sessions.tsx,Insights.tsx,Dashboard.tsx,Places.tsx}`
- cách kiểm chứng: `TEST_DATABASE_URL=… python -m pytest -q tests/analytics tests/harness/test_events.py`; `python -m analytics serve` rồi mở `/admin/analytics`

### Hiện tại (2026-10-09)
- hành vi: harness ghi event sau mỗi mutation (`<stage>.<operation>[.<act>]`, latency, path agent / fallback / heuristic, lỗi, chất lượng lịch khi chốt) và các event đọc; web gửi lô event allowlist (sendBeacon). Server analytics private :8770 với role chỉ đọc: phễu (so sánh phiên bản), Trip, Quyết định, Lịch trình, Thực tế, Thông báo, Agent, Chất lượng, phiên + phát lại, Hôm nay, Insights, nhu cầu một nơi; job `python -m analytics cluster` nhóm ý người dùng viết mỗi tuần.

### Trước đó
- _không có_ (Admin Analytics là khung tĩnh, Phiên chỉ đọc localStorage)

## place-details — Chi tiết địa điểm (13 mục)

- file: `config/{ontology,companions,seasons,serving,planning,decision,trip}.yaml`, `src/corpus/{ontology.py,observe/details_gate.py,observe/{gmaps,tiktok,official}/,aggregate/details.py,serving/details.py,judge/audit.py,review/labels.py}`, `src/requirements/`, `src/trip/domain/`, `src/decision/{fit,cards,compare,feasibility}.py`, `src/planning/{details,places,objectives,timefit,schedule,backup,output,variants}.py`, `web/scripts/export_snapshot.py`, `web/src/user/ui/{PlaceDetails,PlaceSheet}.tsx`
- cách kiểm chứng: `pytest tests/test_ontology.py tests/observe tests/aggregate tests/serving tests/review tests/judge tests/trip tests/decision tests/planning tests/web`

### Hiện tại (2026-10-12)
- ontology version 12: 14 feature enum mới + 15 kind `detail.<kind>`; `observation(detail=...)`, mảng `details` riêng trong file observation; gate `details_gate.py`.
- Maps, TikTok (lời nói + caption), official (`fee`, vé `senior`, `last_entry`) trích `details`; Judge đếm nhãn theo `(detail.<kind>, "*")`.
- aggregate gộp thành cụm theo kind; serving ghi khối `details`; `feature(record, "fit.<who>")` cho `check`.
- Trip: người đi cùng thêm `baby`, `pet`, `coworkers`, `companions_other`; hard filter `fit.<x>`, `pets`, `coach_access`. Decision: điểm mềm `details_fit`, thẻ và so sánh có `known_for`, `cost`. Planning: chi phí thật, giờ đẹp / tránh, `last_entry` official cứng, đường tối, mùa, dự phòng nơi vắng hơn, `checklist`. Web: các khối PlaceDetails, checklist ở màn Lịch trình.
- chưa chạy trên dữ liệu thật: dữ liệu hiện có chưa có `details`, nên mọi khối đều rỗng cho tới khi chạy lại `corpus build`.

### Trước đó (_không có_)
- _không có_

## corpus-snapshot — Snapshot corpus cho phần online

- file: `src/corpus/snapshot/`, `src/corpus/serving/{run,groups}.py`, `src/decision/{frame,pipeline,rank,diversify,engine}.py`, `src/requirements/checks.py` (`scope_allows`), `src/trip/infrastructure/catalog.py` (`from_snapshot`), `src/trip/domain/resolve.py`, `src/bench/latency.py`, `config/serving.yaml`, `tests/{snapshot,bench,decision}/`
- cách kiểm chứng: `pytest tests/snapshot tests/decision tests/trip tests/bench tests/serving`; `pytest -m corpus tests/decision/test_equivalence.py` (cần `python -m corpus snapshot`); `python -m bench latency --scale 1,5,20`

### Hiện tại (2026-10-13)
- `corpus serving` biên dịch thêm `data/snapshot/<version>/<region>/` (bảng LanceDB) và `current`; online (Decision, Planning, Companion, Notify, Trip, bench) chỉ đọc snapshot qua `corpus.snapshot.Region`; `serving.load()` đọc snapshot. Chỉ nơi `VERIFIED` / `UNCERTAIN` / `OUTDATED`, gồm cả chỗ ở.
- Place Decision tính sàng lọc, độ hợp, điểm cho mọi nơi bằng bảng (`decision.frame`, numpy), dựng `Cand` và thẻ chỉ cho nơi được hỏi; memo ba tầng theo phiên. Kết quả y hệt bản theo từng nơi: oracle `tests/decision/test_equivalence.py` (`reference.py`) pass, gồm 30 chuyến × 4 bước trên snapshot thật.
- Hành vi đổi có chủ đích: Trip `Catalog` chỉ còn nơi được phục vụ (không `DISABLED` / `NEEDS_REVIEW`). Decision không bao giờ gợi ý chỗ ở, kể cả khi được chọn làm neo.
- Đo (3.208 nơi, sau build v13; spec §9): `create` p50 trước / sau ≈ 90 / 50 ms, `select` p50 ≈ 90 / 15 ms, `Catalog` 12 s → 1,8 s. Chưa đạt ngân sách `create` ≤ 30 ms, `act` ≤ 15 ms và các mục ×20 (spec §9, phần so ngân sách).

### Trước đó (_không có_)
- _không có_

## home-social — Trang chủ mới, bạn bè, thư viện theo tài khoản (`docs/ACCOUNTS.md` §8–9)

- file: `web/src/user/home/`, `web/src/user/screens/{Discover,Recent}.tsx`, `web/src/user/social.ts`, `web/src/user/store.ts`, `web/src/user/css/home.css`, `src/social/`, `src/accounts/library.py`, `src/harness/{server,dispatch}.py` (`owns`, `copy`), `migrations/004_social.sql`
- cách kiểm chứng: `pytest tests/social tests/accounts tests/harness/test_harness_server.py tests/harness/test_dispatch.py -k "copy or social or nickname or friends"` (cần `TEST_DATABASE_URL`); duyệt hai tài khoản test: kết bạn, chat, gửi lịch trình, Lấy về

### Hiện tại (2026-10-13)
- hành vi: mọi trang ngoài luồng chuyến nằm trong khung toàn màn hình theo mẫu `ui_mock_for_design/designs/homepage` (thanh bên, cột Bạn bè ẩn được, còn một icon cạnh lời chào, thanh chuyến đang lập; nút trên ảnh lớn vào thẳng chat Tìm hiểu với chuyển cảnh ảnh nở thành khung chat). Bỏ Hôm nay khỏi điều hướng. Đã lưu (nơi + chủ đề) và Đã xem gần đây lưu theo tài khoản; nơi đã lưu cũ ở trình duyệt được chuyển lên một lần. Bạn bè: mời theo nickname, chỉ thấy online / offline, nhắn tin, gửi lịch trình; người nhận "Lấy về" thành bản sao độc lập (id phiên module mới, không mang transcript Trip).

### Trước đó
- _không có_

## stay-price — Giá chỗ ở từ trang chi tiết Maps

- file: `src/corpus/crawl/gmaps/stay_price.py`, `src/corpus/crawl/gmaps/listing.py` (`build_stay(detail_prices)`), `src/corpus/__main__.py` (`gmaps stay_price`), `config/queries.yaml` (`stay_price_tabs`)
- cách kiểm chứng: `pytest tests/crawl/test_gmaps_stay_price.py`; chạy `python -m corpus gmaps stay_price --limit 8` rồi xem `data/gmaps/stay_price/dalat.jsonl`

### Hiện tại (2026-10-13)
- hành vi: chỗ ở không có giá trên thẻ danh sách khách sạn thì mở trang chi tiết, đọc ô giá trên tab "Tổng quan" (chỉ có khi Maps có phòng trống trên các trang đặt phòng) và ghi giá một đêm kèm ngày. Không đọc danh sách "Tất cả mức giá" (lẫn dòng "các mức giá khác từ …"). 103 / 782 trang có giá; chỗ ở có giá 741 → 844 / 1.524. Dòng giới hạn 300 review mới nhất của chỗ ở trong `queries.yaml` đã bỏ (người dùng 2026-10-13), chỗ ở cào sâu như địa điểm.

### Trước đó
- hành vi: _không có_ (giá chỗ ở chỉ từ thẻ danh sách khách sạn; 741 / 1.524).

## lodging-browse — Chỗ ở: duyệt tự do ở Lựa chọn, gợi ý ở Lịch trình

- file: `src/planning/{engine,lodging,tools}.py` (`lodging_options(decision, offset, limit)`), `src/harness/dispatch.py` (`lodging`, `_page`), `web/src/user/screens/Lodging.tsx`, `web/src/user/screens/plan/parts.tsx` (`NoHotel`), `web/src/user/ui/SelectedBar.tsx`, `web/src/user/screens/Explore.tsx`
- cách kiểm chứng: `pytest tests/planning/test_planning_lodging_rank.py tests/harness/test_dispatch.py -k lodging`; với corpus thật: 1499 chỗ ở, trang 18, hai trang không trùng

### Hiện tại (2026-10-13)
- hành vi (thẻ, 2026-10-14): thẻ chỗ ở cùng markup và trường với thẻ Place Decision (`PlaceCard`): nhãn loại cụ thể, khu, điểm, `why` / `tradeoffs` từ đặc điểm VERIFIED có ≥ 2 người nhắc, phút từ trung tâm, `Trust`, nút tim; tab Chỗ ở có số đếm. Backend `Engine(card_cfg=…)`, `_lodging_card`; kiểm chứng `tests/planning/test_planning_lodging_rank.py`.
- hành vi: tab Chỗ ở hiện mọi chỗ ở qua được ràng buộc cứng và trần giá, theo trang (quanh các nơi đã chọn lên đầu, có `avg_min`), cả khi chưa chọn nơi nào; không còn nhãn "cần chọn", nút "Chưa chọn chỗ ở", câu "Bạn ở đâu?" hay ô tìm chỗ ở khác (tab giống các nhóm khác). Lịch trình chưa có chỗ ở thì gợi ý 3 chỗ, chọn ngay tại chỗ.

### Trước đó
- hành vi: tab Chỗ ở chỉ có tối đa 18 chỗ quanh các nơi đã chọn, trống khi chưa chọn nơi; Lựa chọn nhắc "cần chọn"; Lịch trình chỉ hiện lời nhắc chọn chỗ ở.

## ux-pass-2026-10-14 — hồ sơ, xóa chuyến, tóm tắt chuyến, đĩa xoay

- file: `web/src/user/screens/{Blog,Account,Understand,Explore,Lodging}.tsx`, `web/src/user/screens/understand/{Board,Turn}.tsx`, `web/src/user/ui/{Ticket,DiscPicker}.tsx`, `web/src/user/home/dialogs`, `src/harness/{dispatch,server}.py` (`discard`, `DELETE /api/harness/sessions/{id}`), `src/companion/service.py` (`forget`), `src/planning/engine.py` (`lodging_options` dựng thẻ theo trang)
- cách kiểm chứng: `pytest tests/harness/test_dispatch.py -k discard`, `pytest tests/planning/test_planning_lodging_rank.py`; `tsc --noEmit -p web`
- hành vi:
  - Chuyến của tôi: nút xóa từng chuyến (hỏi lại một lần); chuyến rời tài khoản (`user_id` NULL, số liệu giữ), dòng `trips` của Đang đi bị xóa.
  - Vé chuyến không còn là popover: tóm tắt chuyến (cả dòng chưa có, "Trả lời") nằm luôn trong bảng "Những nơi đang hợp" bên phải; số địa điểm vẫn hiện.
  - Chat bạn bè: chọn emoji, nút thích khi ô trống, tin chỉ có emoji vẽ lớn; chat Tìm hiểu có ảnh người dùng cạnh lời của họ.
  - Hồ sơ làm lại: thẻ tài khoản + số liệu, "Bạn bè nhìn thấy", "Gu đi chơi" (chạm là lưu); bỏ thẻ sở thích chuyến, thẻ iPhone, thẻ chuyến đang lập.
  - "Chỗ ở" đổi tên "Nơi lưu trú" ở tab và vé; danh sách dựng thẻ theo trang (trước đây dựng ~1500 thẻ mỗi lần), tab hiện số đếm / chỗ chờ; đĩa xoay nhỏ lại vừa màn hình và có tab Nơi lưu trú (chọn / đổi như ở lưới).

## auth-email-guest-smooth-2026-10-14 — đăng ký email, khách sạch, bỏ bước Đánh giá, Tổng quan đủ nội dung

- file: `src/accounts/service.py`, `src/harness/server.py`, `migrations/005_password.sql`, `web/src/user/{account.ts,trip.tsx,store.ts,UserApp.tsx,lib.ts}`, `web/src/user/screens/Auth.tsx`, `web/src/user/ui/{PlaceSheet,PlaceDetails,Shell}.tsx`, `web/src/data/{store.ts,snapshotWorker.ts}`
- cách kiểm chứng: `TEST_DATABASE_URL=<DATABASE_URL> pytest tests/accounts tests/harness/test_harness_server.py`; `tsc --noEmit` trong `web`; migration `005` phải được áp (`python -m db migrate`) trước khi bật form đăng ký ở môi trường thật

### Hiện tại (2026-10-14)
- hành vi: đăng ký / đăng nhập bằng email + mật khẩu (scrypt, giới hạn lần thử, chưa xác nhận email, chưa quên mật khẩu); Google nhận lại tài khoản email trùng và gỡ mật khẩu.
- hành vi: "khách" luôn là phiên mới, hồ sơ trống; phiên đang mở (tài khoản hay khách cũ) kết thúc và web xóa trạng thái cục bộ.
- hành vi: thanh bước còn Tìm hiểu · Lựa chọn · Lịch trình; snapshot tải ngầm sau khi vào app và đọc trong worker, nên vào Lựa chọn không khựng.
- hành vi: Tổng quan địa điểm mở bằng đoạn giới thiệu từ dữ liệu có thật, thêm "Tiện ích và dịch vụ", ẩn khối / dòng không có dữ liệu; tab Đánh giá hiện mọi lời đã thu, tải dần khi cuộn.

### Trước đó
- hành vi: chỉ đăng nhập Google; bấm khách khi đã có phiên thì giữ phiên cũ (`started: false`); thanh bước có thêm Đánh giá; snapshot parse trên luồng chính khi vào Lựa chọn; khối không có dữ liệu ghi "Chưa có thông tin"; tab Đánh giá tối đa 3 lời.
