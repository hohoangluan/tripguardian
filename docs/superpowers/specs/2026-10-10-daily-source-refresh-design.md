# Thiết kế bootstrap nơi lưu trú và refresh nguồn hằng ngày

## Mục tiêu

1. Hoàn thiện dữ liệu GMaps cho toàn bộ nơi lưu trú trong `data/gmaps/list/dalat_stay.json` bằng cùng cơ chế lọc, crawl, kiểm chứng và xuất bản của corpus địa điểm thường.
2. Mỗi ngày phát hiện địa điểm và nội dung mới từ GMaps, video/comment mới từ TikTok, đồng thời làm nóng dữ liệu chuyến bay và xe khách theo cửa sổ ngày trượt.
3. Job chạy không người trực; lỗi đăng nhập, captcha hoặc một nguồn ngoài không làm mất dữ liệu cũ và không chặn các nguồn còn lại.

## Phạm vi

### Trong phạm vi

- Thành phố `dalat` và inventory lưu trú `dalat_stay` hiện có.
- Nơi lưu trú chỉ dùng GMaps; không dùng TikTok hay trang official làm bằng chứng.
- GMaps địa điểm thường tiếp tục dùng các phase hiện có.
- TikTok chỉ làm giàu địa điểm thường đã resolve về inventory GMaps.
- Google Flights giữ cửa sổ 30 ngày và Vexere giữ cửa sổ 14 ngày theo `config/live.yaml`.
- Tự động hóa bằng một lệnh vận hành chung để cron gọi mỗi ngày.

### Ngoài phạm vi

- Không đưa giá phòng, giá vé hoặc lịch chuyến vào Place Intelligence tĩnh.
- Không tự giải captcha, thay phiên đăng nhập hay vượt cơ chế chặn của nguồn.
- Không dùng TikTok cho nơi lưu trú.
- Không mở rộng ngoài Đà Lạt trong thay đổi này.

## Kiến trúc

Một daily orchestrator gọi bốn worker độc lập: `gmaps`, `tiktok`, `flights` và `buses`. Mỗi worker chỉ ghi vào thư mục dữ liệu của nguồn đó. Worker thất bại được ghi vào báo cáo nhưng orchestrator vẫn chạy các worker còn lại. Sau khi worker corpus (`gmaps` hoặc `tiktok`) tạo thay đổi, orchestrator mới chạy pipeline QC → observation → Judge → aggregate → serving. Việc xuất bản vẫn dùng ghi file atomic; pipeline lỗi thì bản serving trước đó còn nguyên.

Bootstrap nơi lưu trú là một lệnh riêng, resumable và chỉ đọc inventory `dalat_stay`. Nó dùng chung implementation GMaps với địa điểm thường, nhưng không trộn hàng đợi hai inventory. Dữ liệu của cùng một FID vẫn dùng thư mục chuẩn `data/gmaps/places/<fid_dir>/` để không tạo hai bản ghi địa điểm.

## Bootstrap nơi lưu trú

### Inventory và lọc

- Nguồn đầu vào là `data/gmaps/list/dalat_stay.json`, hiện có 1.524 nơi.
- Áp dụng cùng quy tắc corpus: trong vùng Đà Lạt, category lưu trú hợp lệ, ít nhất 30 review, gộp tên chuẩn hóa trong bán kính 1 km và giữ bản nhiều review hơn.
- CLI với scope `dalat_stay` chỉ lấy item của danh sách lưu trú. Nó không âm thầm ghép thêm `dalat.json`.

### Dữ liệu mỗi nơi

- Chi tiết: tên, category, địa chỉ, tọa độ, website, điện thoại, mô tả, giờ, trạng thái, thuộc tính, popular times, rating, số review, histogram và mức giá GMaps nếu có.
- Review: tối đa 300 review mới nhất, 50 review `relevant`, 30 review thấp nhất và 30 review cao nhất; gộp bằng `review_id`; không lấy phản hồi của chủ cơ sở.
- Keyword review chạy theo cùng bộ cấu hình corpus; category không áp dụng thì không sinh dữ liệu giả.
- Ảnh: 12 ảnh mới nhất mỗi nơi, tối đa 3 ảnh mỗi người đăng, bỏ ảnh quá 3 năm, lưu cạnh dài 768 px; giữ metadata người đăng đã băm, thời gian, owner và loại ảnh/video.
- Phase sau crawl: `qc`, `observe`, `photo_observe`, Judge, `aggregate`, `serving`.
- Ontology và gate giống corpus. Nhóm `stay` chỉ giữ `stay_features`; thiếu bằng chứng là `unknown`.

Mỗi nơi chỉ được xem là hoàn tất khi các file yêu cầu mang trạng thái hoàn tất. Trang bị giới hạn, số review đọc được bất thường hoặc ảnh tải dở không được đánh dấu hoàn tất. Lỗi một nơi được ghi lại và lần chạy sau tiếp tục nơi đó.

## Refresh GMaps hằng ngày

1. Chạy lại discovery cho query địa điểm thường và query × khu vực của nơi lưu trú.
2. Hợp nhất kết quả qua cùng filter/list hiện có; FID mới được đưa vào pipeline đầy đủ tương ứng với inventory của nó.
3. Với FID cũ, đọc lại phần chi tiết vận hành và so sánh hash để chỉ ghi khi nội dung đổi.
4. Review mới nhất được đọc đến khi gặp `review_id` đã lưu; review mới được merge vào dữ liệu thô theo ID. Nơi có số review thay đổi được đưa lại qua `relevant`, `extremes` và `keywords`, kết quả vẫn dedup theo ID.
5. Gallery mới nhất được đọc đến khi gặp `photo_id` đã lưu hoặc đủ chính sách 12 ảnh. Metadata và file mới được merge; giới hạn tuổi và số ảnh mỗi tác giả vẫn được áp dụng trên tập sau merge.
6. Chỉ các FID mới hoặc thay đổi mới đi qua QC/observation. Ledger hiện có quyết định prompt/rule nào thật sự cần chạy lại.

Refresh không xóa fact chỉ vì nguồn tạm thời không trả nó. Đóng cửa hoặc đổi thực thể vẫn đi qua gate/Judge hiện có.

## Refresh TikTok hằng ngày

- Input chỉ là `dalat.json`; `dalat_stay.json` bị loại rõ ràng ở biên worker.
- Tìm kết quả mới theo từng nơi và trang POI đã resolve; dừng khi gặp video ID đã lưu hoặc tín hiệu hết trang.
- Video mới đi qua đúng chuỗi `place_filter` → crawl → ASR → `asr_check` → `place_verify` → clip/observe.
- Comment của video đã verify được đọc tăng dần và dedup theo comment ID.
- Chỉ video `yes` sau verify mới làm bằng chứng. Nội dung `no`, `unsure` hoặc không có span không được xuất bản.
- Captcha, hết phiên hoặc block làm worker TikTok dừng có kiểm soát; không chuyển sang nguồn hoặc tài khoản giả định khác.

## Refresh chuyến bay và xe khách

- Tái sử dụng `scripts/prewarm_transit.py` và cache của `src/live`.
- Mỗi ngày tạo lại tập công việc theo ngày hiện tại: chuyến bay từ các sân bay cấu hình đến/đi DLI trong 30 ngày; xe khách từ các vùng Vexere cấu hình đến/đi Đà Lạt trong 14 ngày.
- Cache hợp lệ dưới TTL 26 giờ được dùng lại; ngày mới ở cuối cửa sổ được fetch. Bản ghi quá cửa sổ có thể giữ trên đĩa nhưng không được API trả cho request ngoài ngày yêu cầu.
- Không có kết quả hoặc nguồn lỗi trả `Unavailable`; không tạo chuyến giả.

## Trạng thái, khóa và báo cáo

- Orchestrator và từng worker dùng khóa tiến trình không chờ; cron mới gặp job cũ đang chạy sẽ ghi `already_running` rồi thoát an toàn.
- Checkpoint và báo cáo của từng nguồn nằm trong thư mục nguồn tương ứng, ví dụ `data/gmaps/refresh/` và `data/tiktok/refresh/`; live tiếp tục dùng thư mục cache riêng.
- Mỗi lần chạy ghi thời gian bắt đầu/kết thúc, số item phát hiện, mới, thay đổi, bỏ qua, lỗi, trạng thái đăng nhập/captcha và bước publish cuối cùng.
- Báo cáo tổng hợp có trạng thái theo nguồn. Exit code khác 0 nếu có nguồn thất bại, nhưng chỉ sau khi các nguồn còn lại đã chạy xong để cron có thể cảnh báo từ log/exit code.
- Không ghi cookie, token, URL có secret hay nội dung `.env` vào báo cáo.

## Giao diện vận hành

- Một lệnh bootstrap riêng cho nơi lưu trú, hỗ trợ `--limit`, `--shard` và resume.
- Một lệnh daily refresh chung, hỗ trợ `--only <source>` và `--dry-run` để xem hàng đợi mà không gọi mạng hay ghi dữ liệu nguồn.
- `run.sh` cung cấp entrypoint ổn định cho cron. README ghi lệnh cron, nơi xem báo cáo và cách đăng nhập lại thủ công.
- Daily job chạy headless. `LoginRequired`/captcha không mở cửa sổ hoặc chờ người.

## Kiểm thử

- Unit test scope `dalat_stay` không chứa FID chỉ có trong `dalat.json`.
- Fixture test merge review/photo/video/comment mới, dedup ID cũ và dừng cursor tại ID đã biết.
- Test giới hạn ảnh 12/nơi, 3/người và 3 năm sau khi merge.
- Test nơi mới đi qua filter/list và pipeline đầy đủ; nơi không đổi không gọi observation lại.
- Test một worker lỗi vẫn cho worker khác chạy, báo cáo đúng và exit code thất bại.
- Test lock chống hai job chạy đồng thời và `--dry-run` không ghi dữ liệu.
- Test transit tạo đúng cửa sổ 30/14 ngày, dùng cache hợp lệ và không bịa kết quả khi nguồn lỗi.
- Toàn bộ test tự động dùng fixture/mocking, không gọi mạng thật.

## Tiêu chí hoàn tất

- Mọi item trong `dalat_stay.json` có kết quả crawl hoàn tất hoặc lỗi có cấu trúc để retry; không có khoảng trống im lặng.
- Nơi lưu trú đã hoàn tất có review và tối đa 12 ảnh đúng chính sách khi nguồn có dữ liệu.
- Serving chứa nhóm `stay` đủ ngưỡng `stay_min` để Planning dùng corpus, nhưng Explore/Decision không gợi ý nơi lưu trú.
- Hai lần daily refresh liên tiếp với fixture không đổi không tạo bản ghi trùng hoặc chạy lại model không cần thiết.
- Captcha/login ở GMaps hoặc TikTok không làm mất serving cũ và không cản prewarm flights/buses.
- Tài liệu `P1_CORPUS.md`, `P4_PLANNING.md`, `README.md` và `OPEN_TASKS.md` phản ánh đúng code sau khi triển khai.
