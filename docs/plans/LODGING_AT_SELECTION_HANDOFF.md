# Bàn giao — chỗ ở ở bước Lựa chọn

File làm việc tạm (RULE §0.1): khi xong hết, gộp phần còn giá trị vào tài liệu chính thức rồi xóa file này. Tài liệu chính thức đã sửa cho khớp code: `PLANNING.md` ⓐ, `PLACE_DECISION.md` §12.1 §15, `TRIP_UNDERSTANDING.md` §Hậu cần, `AGENT_HARNESS.md`, `CORPUS.md`, `UI_SPEC_USER_WEB.md`, `Role_Web_Functional_Design.md`, `log/DEV_LOG.md` (mục `detail-logistics`).

## 0. Đọc trước khi làm

- Working tree **dùng chung**, đang lẫn việc của nhiều session (Codex, Claude). Đọc `git status` trước; **không commit, không `git add -A`**. Chưa có gì của việc này được commit.
- `corpus build --city dalat --skip gmaps photo_observe` (pid 3685854 lúc viết) và 2 `gmaps crawl` shard là của **session khác**; không kill. Đừng chạy `aggregate` / `serving` / `build` song song với nó.
- Không đụng `.browser/` (phiên đăng nhập Google), không build vào `web/dist` (đang phục vụ live, `docs`/memory `prod-deploy-runbook`). Chưa deploy.
- Test fail sẵn vì phần **bữa ăn đang dở của session khác**, không liên quan: `test_planning_golden`, `test_planning_lodging_golden` (chỉ lệch giờ ăn, phần chỗ ở của tôi đã vá vào golden), `test_planning_variants::test_a_variant_that_does_not_fit_the_days_is_dropped_and_named` (fail y hệt trên bản trước thay đổi của tôi), 5 test trong `tests/harness/test_{dispatch,tools}.py` (`no open question 'meal:…'`), `tests/trip/test_eval_conversations.py` (KeyError `conversations`).

## 1. Yêu cầu của người dùng (nguyên tắc)

1. Lựa chọn **không bao giờ chặn** người dùng: chỉ thông báo, họ tự quyết (memory `never-block-user-choices`). Hỏi xác nhận khi đổi chỗ ở là ngoại lệ do chính họ yêu cầu.
2. Bỏ luồng cào Maps trực tiếp khi chạy; ưu tiên tìm trong corpus của mình.
3. Bỏ luồng chọn chuyến xe / vé máy bay; chỉ hỏi tới Đà Lạt bằng gì; điểm xuất phát (nhà) cho chọn; **mọi ngày bắt đầu và kết thúc ở chỗ ở**.
4. Bỏ màn "Bạn ở đâu?" ở Bước 3; chọn chỗ ở ở tab "Chỗ ở" của Lựa chọn. Bước 1 chỉ hỏi đã có chỗ ở chưa.
5. **Cả chuyến một chỗ ở.** Đã có (đã đặt lúc hỏi, hoặc đã chọn ở tab) mà đổi → cảnh báo, người dùng bấm xác nhận mới đổi.
6. Bỏ khối "X và Y khá giống nhau" khỏi lưới; thiếu dữ liệu (ảnh khách sạn, giá) thì bổ sung đủ.

## 2. Đã xong (chưa commit) — đừng làm lại

| Phần | Ở đâu | Kiểm chứng |
|---|---|---|
| Bỏ dòng "khá giống nhau" | `web/src/user/screens/Explore.tsx`, `css/explore.css` | `tsc` |
| Tab "Chỗ ở" + xác nhận đổi (Radix Dialog) | `web/src/user/screens/Lodging.tsx` (`LodgingPanel`, `LODGING_TAB`), `Explore.tsx`, `ui/SelectedBar.tsx`, `pd/{api,types,decision}.ts(x)`, `css/plan.css` | `tsc`, `vite build` ra thư mục tạm; **chưa xem trên trình duyệt** |
| Plan không chặn, nhắc chọn chỗ ở, "Đổi chỗ ở" quay về tab | `web/src/user/screens/Plan.tsx` | `tsc` |
| Decision: `set_lodging` / `clear_lodging`, `view.lodging {booked, chosen, needed}`, `Output.lodging`; corpus lodging đọc tên / toạ độ / giá từ bản ghi `stay` (không tin client) | `src/decision/{session,curation,engine,pipeline,output,contracts,scope,tools}.py` | `tests/decision/test_decision_engine.py -k lodging` |
| Planning: ứng viên chỉ từ corpus, bỏ `lodging_fn`, `live_cards`, `refresh_prices`, `stay_min`; `booked()` ưu tiên `decision.lodging`; `Engine.lodging_options(decision)` (không phiên); không `require_lodging`; ngày home→home (bỏ `@entry/@exit`) | `src/planning/{lodging,engine,frame,build,variants,tools,server,logistics,evaluate}.py`, `config/planning.yaml` | `tests/planning/test_planning_lodging*.py`, `test_planning_frame.py`, `test_planning_build.py` |
| Harness: `read/decision/lodging` (dùng `draft` với `{any: true}`), bỏ `/transit` | `src/harness/{dispatch,server}.py`, `src/decision/{tools,engine}.py` | `tests/harness/test_dispatch.py -k lodging` |
| Trip: không hỏi chuyến; hỏi `origin` mọi chuyến | `src/trip/domain/questions.py`, web `Understand.tsx`, `tu/{api,types}.ts`, xóa `ui/TransitPick.tsx` | `tests/trip/test_logistics.py` |
| Corpus: giá một đêm `price_vnd/price_at` vào `list/dalat_stay.json` (741 / 1.524 nơi) → `place_facts.price_night` → `operation.price_night` → serving `price_per_night` | `src/corpus/{crawl/gmaps/listing,observe/gmaps/extract,aggregate/place,serving/record}.py` | `tests/{crawl,observe,aggregate,serving}` |
| Snapshot web có nhóm `stay` (mới sửa script, **chưa chạy**) | `web/scripts/export_snapshot.py` | — |

## 3. Việc còn lại (theo độ ưu tiên)

### 3.1 Dữ liệu — chặn kết quả thật
- **Serving đang không có chỗ ở nào** (`data/serving/places.json`: 0 bản ghi `stay`; `data/intel/places/`: 5 file). Danh sách "Chỗ ở" sẽ rỗng cho tới khi chạy `aggregate` → `serving`. 1.503 / 1.524 nơi đã có `observations/`. Chờ `corpus build` của session kia xong rồi **kiểm**: số bản ghi `stay` trong serving (≈ 1.400+), `operation.price_per_night` có ở ~740 nơi, ảnh bìa. Nếu build đó không phủ chỗ ở: `python -m corpus aggregate --city dalat && python -m corpus serving --city dalat` (hỏi người dùng nếu build kia còn chạy).
- **Ảnh khách sạn trên web:** chạy `python web/scripts/export_snapshot.py` → `python web/scripts/pick_covers.py --resume` (Gemma; **tạm dừng luồng TikTok** `logs/tiktok_lan_uit_lane.sh` trong lúc chạy, bật lại sau; memory `photo-ranking-gemma-pause-tiktok`) → `python web/scripts/make_thumbs.py`. Chỉ làm sau khi serving có `stay`; kiểm kích thước `snapshot.json` (hiện 27 MB) và `covers.json`.
- **Ảnh còn thiếu ở corpus:** 119 chỗ ở chưa có `photos.json`, 129 nơi có `photos.json` nhưng 0 ảnh dùng được (`too_old`, `no_metadata`). Cào bù bằng `python -m corpus gmaps photos --city dalat` (cần phiên Google đã đăng nhập, có captcha → **người dùng giải**, memory `crawl-captcha-person-solves`, `crawl-server-ops-lessons`; hỏi trước khi tăng tab > 64). `photos_per_place` hiện 12.
- Chỗ ở ngoài danh sách 1.524 (tên người dùng gõ) đi qua ô tìm: `lodging/suggest` ưu tiên corpus rồi `geosearch` → thành điểm `address`, không có ảnh / giá. Đủ dùng; không cào Maps.

### 3.2 Kiểm chứng giao diện
- Chưa chạy trình duyệt cho luồng mới. Dùng `node web/scripts/shots_app.mjs <base>` (đã lỗi thời: còn bước chọn chuyến và "Bạn ở đâu?", cần sửa theo luồng mới) hoặc Playwright (`playwright-on-gpu156`: dùng chromium-1169, không dùng headless_shell). Cần xem: tab "Chỗ ở" (chưa có / đã đặt / đã chọn), hộp thoại xác nhận đổi, "Bỏ lựa chọn", dải "Chưa chọn chỗ ở" ở Lịch trình, `SelectedBar`.
- Máy tính để bàn thôi (memory `no-phone-web`).

### 3.3 Dọn code không còn dùng (người dùng bảo "bỏ luôn")
- `src/live/{flights,buses}/`, `scripts/prewarm_transit.py` (+ `./run.sh prewarm`), `config/live.yaml` `transit_prewarm`, đoạn và cron `prewarm` ở `README.md` (~dòng 89–92; cron production có thể đang chạy: tắt trên máy đó nếu xóa), `tests/live/test_{flights,buses}*`; `docs/PLANNING.md` Live Context còn ghi hai nguồn này "không còn trong luồng người dùng". Quyết định xóa hẳn hay giữ làm công cụ — hỏi người dùng.
- Trip: `Transit`, `pick_transit`, `inbound` / `outbound`, `entry_point` / `exit_point` vẫn nằm trong `state.py`, `compile.py`, `engine.py` (nhánh `q.qid in ("inbound","outbound")`), vé chuyến `Understand.tsx` (dòng `inbound`/`outbound`), `src/trip/domain/rental.py` (`ARRIVES_WITHOUT_A_VEHICLE`: giữ, câu thuê xe còn dùng). Không còn ai ghi chúng; cần xóa cả test (`tests/trip/test_{logistics,entry_exit}.py`). Làm tối thiểu, đừng refactor lan.
- `src/live/lodging` (`lodging_near`, `lodging_seen`) không còn ai gọi từ Planning; `tests/live/test_lodging.py` còn.

### 3.4 Quyết định đang chờ người dùng
- **Chặn cứng của Decision:** `_confirmable` (`src/decision/engine.py`) vẫn từ chối chốt khi có nơi đóng cửa mọi ngày của chuyến (`hours`) hoặc vi phạm điều kiện cứng đã có bằng chứng (`relax`, `physical`, `hard`). Đây là bất biến "hard constraint fail-closed" của `AGENTS.md`, mâu thuẫn với "không bao giờ cản". Đã hỏi, **chưa có trả lời**. Đừng đổi khi chưa được trả lời; nếu đổi phải sửa `tests/decision/test_decision_engine.py` (`test_blocking_conflict…`, `test_closed_and_hard_failed…`) và `docs/PLACE_DECISION.md`.
- Giá chỗ ở là giá danh sách khách sạn của Maps theo ngày mặc định (tham khảo); giá đúng ngày đi đã bỏ cùng đường cào. Nếu muốn lại, cần nguồn không cào lúc chạy.

### 3.5 Ghi chú kỹ thuật dễ vấp
- `view.lodging.needed` = chưa biết chỗ ở nào (`booked` rỗng **và** `chosen` rỗng); tab "Chỗ ở" luôn hiện, không phụ thuộc `needed`.
- Trong Decision Output `lodging.id` chỉ có nghĩa khi `kind = corpus`; Planning `booked()` đặt `place_id` chỉ khi `kind = corpus`.
- `Engine.lodging_options` cache theo (tập nơi, bối cảnh chuyến) trong `PREVIEW_TTL_S`; cache **không** phụ thuộc chỗ ở đang chọn (ứng viên không phụ thuộc nó).
- `read/decision/lodging` dùng `draft` với `{any: true}` để chỗ ở vẫn hiện khi lựa chọn chưa đi được.
- Golden `tests/planning/golden/{lodging_sample_trip,variants_wet_south}.json` đã vá tay phần chỗ ở (bỏ `amenities`, `entry_exit_unknown`, giá h0 = 280000). Khi session bữa ăn xong và tạo lại golden (`UPDATE_GOLDEN=1`), kiểm diff không làm hiện lại `amenities` / `entry_exit_unknown`.
- `web/src/user/screens/Lodging.tsx` có session khác từng sửa giữa chừng (đã gỡ `markAsked` / "Cứ xếp giúp"); file hiện là bản mới của việc này.

## 4. Đang làm

Không có tiến trình nào của việc này đang chạy. Việc dở duy nhất: §3.1 chờ build corpus của session khác xong.
