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

## corpus-crawl — Crawl dữ liệu thô TikTok + Google Maps

- file: `src/corpus/crawl/` (`files`, `browser`, `tiktok`, `gmaps`), `src/corpus/__main__.py`, `config/queries.yaml`, `tests/crawl/`, `tests/fixtures/` (`capture.py` lưu lại fixture thật, đã che tài khoản)
- cách kiểm chứng: `python -m pytest -q`; smoke thật `python -m corpus {tiktok|gmaps} --city dalat --headed` với config thu nhỏ

### Hiện tại (2026-09-29)
- hành vi:
  - `python -m corpus login <source>` mở Chrome với profile `.browser/<source>/` để người đăng nhập; `tiktok` / `gmaps` crawl theo `config/queries.yaml`, ghi file vào `DATA_DIR` (layout: `docs/specs/CORPUS_SPEC.md` §1, Dữ liệu thô).
  - TikTok: bắt JSON API search; mỗi video ghi `info.json`, `comments.json` (comment + reply có `parent_id`, mặc định lấy hết trang; bỏ trùng theo `comment_id`; tác giả chỉ còn `author_hash`), rồi `video.mp4` tải từ `playAddr`. Video có `commentCount` > 0 mà lấy được 0 comment thì không đánh dấu xong.
  - Maps: search `<category> <tên thành phố>`, mở từng place bằng URL, mở bảng giờ, tab Giới thiệu, tab review sắp xếp Mới nhất; ghi `reviews.json` rồi `place.json`. Selector nằm trong `gmaps.py`.
  - Captcha: `--headed` chờ người giải tối đa 5 phút; headless dừng với `LoginRequired`. `errors.jsonl` chỉ giữ dòng đầu của lỗi (call log Playwright chứa cookie phiên).
  - Smoke 2026-09-29 (`--headed`): reply: 1 video 11/11 (7 comment + 4 reply, khớp `reply_count`, không reply mồ côi); TikTok 1 query → 3 video (3–52 MB), 12/30/100 comment (trần cũ 100), chạy lại không tải trùng; lấy hết comment trên 2 video: 276/347 comment cấp 1 (`commentCount` 571/606 gồm cả reply), TikTok gửi lặp trang nên bỏ trùng theo `comment_id`; Maps `thác` → 4 place, 3 place đủ 7 dòng giờ, 2 place có giờ cao điểm 7 ngày, mỗi place 10 review. Headless: Maps trả trang thiếu (0 review), TikTok hay gặp captcha.
  - TikTok: video của một lần search chạy song song `tabs` tab (mặc định 5); `LoginRequired` ở một tab hủy các tab còn lại.
  - **Google Maps chưa xong** (tạm dừng để hoàn thiện TikTok trước). Còn phải làm:
    - chưa chạy full crawl, mới smoke 1 category (`thác`, 4 place, 10 review/place);
    - headless trả trang thiếu, hiện phải chạy `--headed`;
    - trang chặn của Google (`/sorry`) chưa chờ người giải như TikTok, chỉ dừng với `LoginRequired`;
    - chưa kiểm: điểm dừng cuộn feed ("Bạn đã xem hết danh sách này"); `Thác Prenn` có 0 dòng giờ (chưa rõ do place không có giờ hay selector trượt);
    - `address` còn lẫn ký tự icon ở đầu; review dài không bấm được "Thêm" thì giữ text bị cắt;
    - lấy hết review (hiện trần `max_reviews_per_place`).

### Trước đó
_không có_
