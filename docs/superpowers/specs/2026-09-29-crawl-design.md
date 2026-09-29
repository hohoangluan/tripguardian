# Crawl dữ liệu thô: TikTok + Google Maps — thiết kế làm việc

Spec làm việc, tạm thời (`RULE.md` §0.1). Xong thì gộp phần còn giá trị vào `docs/specs/CORPUS_SPEC.md`, `docs/CORPUS.md`, `README.md`, `docs/log/DEV_LOG.md` rồi xóa file này.

## Mục tiêu

Crawl lặp lại được dữ liệu thô của một thành phố (mặc định `dalat`) từ TikTok và Google Maps, lưu thành **file thường** (JSON, mp4), không dùng DB. Thư mục chia theo nguồn trước, dễ mở ra xem bằng tay.

Thành công khi:
- `python -m corpus tiktok --city dalat` và `python -m corpus gmaps --city dalat` chạy hết mà không cần người (sau khi đã đăng nhập một lần).
- Chạy lại không tải trùng; dừng giữa chừng rồi chạy lại thì tiếp tục đúng chỗ.
- Không bước nào xóa file.

Ngoài phạm vi: DB, ledger, record pydantic cho dữ liệu crawl, vòng mở rộng query, segment / ASR / keyframe, resolve, observation, MCP.

## Quyết định đã chốt

| Việc | Chọn | Lý do |
|---|---|---|
| Lưu trữ | File thường; không DB | Đơn giản, dễ xem; DB thêm khi có bước cần truy vấn |
| Search TikTok | Playwright, profile đã đăng nhập, bắt JSON của API search | Search ẩn danh bị captcha (đã thử); JSON bền hơn DOM |
| Tải TikTok | yt-dlp (bản mới nhất), cookie lấy từ profile | Tải mp4 + metadata + comment ổn định |
| Địa điểm | Cào Google Maps bằng Playwright, profile tài khoản Google phụ đã đăng nhập | Không dùng Places API; chế độ ẩn danh ẩn review và giờ cao điểm (đã thử) |
| Dữ liệu Maps | Thông tin cơ bản, thuộc tính, rating + số review, giờ cao điểm, review | Review và giờ cao điểm là nguồn trải nghiệm; rating chỉ tham khảo (không có span) |
| Tách nguồn | Mỗi nguồn một thư mục dữ liệu và một module code | `RULE.md` §2 |

## Layout dữ liệu

Gốc `DATA_DIR` (`.env`, mặc định `data/`, gitignored). Chia theo nguồn; mọi thứ của một video / một place nằm chung một thư mục, các bước sau (segment, ASR, …) ghi thêm file vào đúng thư mục đó.

```text
data/
  tiktok/
    search/<city>/<query_slug>.jsonl     append mỗi lần search: {at, query, items:[{video_id, url, author_id, desc}]}
    videos/<video_id>/
      info.json                          metadata thô của yt-dlp (không kèm comment)
      comments.json                      comment thô
      video.mp4                          ghi cuối cùng = đánh dấu video đã xong
    errors.jsonl                         {at, id, stage, error}
  gmaps/
    search/<city>/<category_slug>.jsonl  append: {at, query, items:[{fid, name, url}]}
    places/<fid_dir>/                    fid_dir = FID với ":" đổi thành "_" (Windows)
      reviews.json                       review thô
      place.json                         ghi cuối cùng = đánh dấu place đã xong
    errors.jsonl
```

- `.jsonl` chỉ append. File khác ghi ra `*.tmp` rồi `os.replace` (atomic), nên không bao giờ còn file hỏng dở.
- Mục đã xong = có file đánh dấu → bỏ qua. Thiếu → tải lại cả mục (ghi đè file dở của chính mục đó; không xóa gì khác).
- Profile trình duyệt: `.browser/<source>/` (gitignored).

## Code

```text
src/corpus/
  crawl/
    files.py        data_dir(), write_json (atomic), append_jsonl, slug(), log_error()
    browser.py      open_profile(source, headed) → Playwright persistent context; pause(): nghỉ ngẫu nhiên 2–5 s; LoginRequired
    tiktok.py       parse_search(json) · search(page, query, limit) · download(url, dir) · run(city)
    gmaps.py        parse_feed(html) · parse_place(html) · parse_reviews(html) · search · place · reviews · run(city)
  __main__.py       python -m corpus {login <source> | tiktok | gmaps} --city <key> [--headed]
config/queries.yaml query TikTok theo nhóm spec + category Maps + trần số lượng
```

- `parse_*` là hàm thuần nhận HTML/JSON, test bằng fixture; các hàm còn lại chỉ lái trình duyệt / yt-dlp và ghi file.
- Selector DOM của Maps chỉ nằm trong `gmaps.py`. Tách thành package khi một file quá dài, không trước.
- Không dùng `corpus.adapters` (db, llm) và không đổi `corpus.core`. Thành phố đọc bằng `load_cities` có sẵn.

### `place.json`

```text
fid, name, url, lat, lng, category, address, phone, website, description,
hours[]            nguyên văn từng dòng bảng giờ
status             nguyên văn ("Đang mở cửa", "Đóng cửa vĩnh viễn", …)
attributes[]       nguyên văn aria-label tab Giới thiệu ("Lối vào cho xe lăn", …)
popular_times[]    nguyên văn aria-label ("Thường bận 45% lúc 9 giờ", …) — làm span cho observation crowd sau này
rating, review_count
fetched_at
```

### `reviews.json`

`[{review_id, author_hash, rating, text, published_text}]`. `author_hash` = sha256 id người review (không giữ tên). `published_text` giữ nguyên văn ("2 tuần trước").

## Giới hạn và lỗi

- Tuần tự, một trình duyệt mỗi nguồn, `pause()` giữa mọi lần tải trang.
- Trần trong `config/queries.yaml`: video mỗi query, comment mỗi video, place mỗi category, review mỗi place.
- Gặp captcha / trang đăng nhập → `LoginRequired`; dừng gọn, in "chạy `python -m corpus login <source>`". Không thử vượt captcha.
- Lỗi một mục → dòng trong `errors.jsonl`, đi tiếp mục sau; lần chạy sau thử lại vì mục chưa có file đánh dấu.

## Test

- `files`: ghi atomic (không còn `.tmp`), append giữ dòng cũ, `slug` và `fid_dir` hợp lệ trên Windows.
- Parser: fixture thật ở `tests/fixtures/tiktok/`, `tests/fixtures/gmaps/` (JSON search, HTML feed / place / reviews).
- `run`: hàm lái trình duyệt thay bằng giả → chạy 2 lần, lần 2 không tải lại; mục lỗi được ghi `errors.jsonl` và lần sau thử lại.
- Chạy thật: smoke test thủ công với `--headed`, ghi kết quả vào DEV_LOG.

## Dependency và thiết lập

`pyproject`: thêm `playwright`, `yt-dlp`. Thiết lập: `pip install -U yt-dlp`, `playwright install chromium`, `python -m corpus login tiktok`, `python -m corpus login gmaps`. `.gitignore`: `data/`, `.browser/`. `.env.example`: `DATA_DIR=data`.

## Tài liệu cập nhật khi xong

- `CORPUS_SPEC.md`: §1 Discover (Maps thay Places API), mục layout dữ liệu, bảng *Sai lệch cho bản demo* (cào Maps + TikTok có đăng nhập; lưu file thay DB ở giai đoạn crawl).
- `CORPUS.md` §2: dòng Google Maps — review và giờ cao điểm là nguồn trải nghiệm; rating chỉ tham khảo.
- `README.md`: thiết lập crawl. `DEV_LOG.md`: mục `corpus-crawl`.

## Rủi ro

- Tài khoản TikTok / Google phụ có thể bị khóa → dùng tài khoản phụ, giữ trần và delay.
- DOM Maps đổi → fixture test báo ngay; sửa chỉ trong `gmaps.py`.
- Vi phạm điều khoản Google Maps và TikTok: chấp nhận cho bản demo, ghi trong bảng sai lệch.
