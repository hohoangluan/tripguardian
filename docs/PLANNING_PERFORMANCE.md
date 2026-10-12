# Báo cáo phạm vi chuyến dài và hiệu năng Planning

Báo cáo này ghi lại hai thay đổi phối hợp trong Planning: tăng tốc tìm thứ tự điểm trong từng ngày cho chuyến bảy ngày, và hỗ trợ chia chuyến dài thành các tuần tối đa bảy ngày. Phạm vi được đối chiếu với mã hiện tại trong `src/planning/`, `config/planning.yaml`, các test `tests/planning/` và tài liệu `docs/PLANNING.md`.

## Kết luận về tương thích

Hai thay đổi làm việc ở hai cấp khác nhau. Với chuyến tối đa bảy ngày, Planning dùng thuật toán chia ngày hiện tại và vẫn vét cạn thứ tự tới `exact_n = 7` điểm/ngày. Route cache mới chỉ lưu các phép tính lặp trong **một lần** tìm thứ tự của một ngày. Với chuyến dài hơn bảy ngày, `prepare()` giảm giới hạn vét cạn xuống `long_trip_exact_n = 5`; sau đó `schedule_trip()` phân điểm vào từng tuần bảy ngày rồi chia và xếp lịch trong phạm vi từng tuần. Mỗi lần `order_day()` vẫn dùng route cache cục bộ theo chính `DayCtx` của ngày đó.

Điều kiện chuyển giới hạn là `days > chunk_days`, với `chunk_days = 7`. Vì vậy chuyến đúng bảy ngày không chuyển sang giới hạn năm điểm. Test `test_long_routes_have_a_small_exact_bound_but_week_trips_keep_existing_bound` kiểm tra cả hai nhánh: chuyến 14 ngày có `exact_n = 5`, chuyến bảy ngày giữ giới hạn cấu hình gốc. Test tuần còn kiểm tra nơi ở đúng tuần được gán, biên ngày đầu/cuối, di chuyển một nơi giữa hai tuần, giữ giới hạn ngân sách theo ngày và làm lộ vi phạm khi một tuần quá tải.

Route cache kết thúc khi lời gọi `order_day()` kết thúc. Cache gồm giờ mở theo thứ, cửa sổ ghim, quy tắc giờ phù hợp, điểm chấm theo `(place_id, start, end)` và chặng đi có hướng `(from_id, to_id)`. Hai bảng kết quả dùng giới hạn `cache_entries`; cấu hình hiện tại là 128 phần tử mỗi bảng. Phép kiểm constraint cuối vẫn gọi validator độc lập. Vì thế cache này không được tái sử dụng sau khi đổi ngày, pace, ưu tiên giờ, thời tiết, địa điểm hay ma trận di chuyển.

## Thay đổi trong Planning cho chuyến dài

`chunk_days = 7` đặt độ dài một tuần trong lịch. Với hành trình dài hơn bảy ngày, Planning giữ phân công tuần đã có trong Decision Output. Nếu dữ liệu đầu vào cũ không có phân công đầy đủ, Planning tạo một phân bổ thô một lần rồi dùng chung phân bổ đó qua các mục tiêu và biến thể chỗ ở. Sau đó từng tuần được chia cụm và xếp vào các ngày thuộc tuần đó; một điểm không bị thử phân bổ lại qua mọi tuần.

Mỗi ngày vẫn giữ cửa sổ giờ riêng của mình. Ngày đầu dùng giờ đến, ngày cuối dùng giờ rời, còn ngày giữa chuyến dùng cửa sổ ngày thông thường. Các lần sửa lịch qua tuần chỉ tính lại ngày nguồn và ngày đích; ma trận di chuyển của chuyến được giữ lại. View và Plan Output có `chunk_assignments` và thông tin `chunks`; giao diện có chọn tuần, điều hướng ngày theo tuần, cảnh báo chuyến dài, và chọn ngày cho một điểm có thể di chuyển.

Chuyến dài được khuyến nghị đến 14 ngày, cho phép đến 30 ngày. Trên 14 ngày hệ thống gắn cảnh báo rằng khả năng xử lý chưa được kiểm chứng và có thể lâu hơn. Đây là giới hạn khuyến nghị, không phải giới hạn cứng cho lựa chọn thời lượng.

## Thay đổi tăng tốc tìm thứ tự

Trước tối ưu, mỗi hoán vị gọi mô phỏng ngày và lặp lại các phép tính giờ mở, cửa sổ ghim, luật giờ ưu tiên, điểm số giờ ghé và chặng di chuyển. Với bảy điểm, tìm kiếm vét cạn xét tối đa `7! = 5.040` thứ tự cho một ngày.

Sau tối ưu, `route.order_day()` tạo cache cục bộ cho ngày rồi truyền cache đó xuyên suốt mô phỏng các thứ tự ứng viên. Thuật toán vẫn xét cùng tập hoán vị, giữ tie-break theo thứ tự đầu tiên và trả cùng `DayResult`. Với số điểm vượt giới hạn vét cạn, nearest-neighbour, 2-opt và or-opt vẫn thử các ứng viên theo thứ tự cũ. Cải thiện chỉ loại bỏ tính toán lặp; không giảm số điểm được chọn, không đổi trọng số, không nới constraint và không bỏ bước kiểm cuối.

## Benchmark bảy ngày được tái sử dụng

Số dưới đây lấy từ `/tmp/tripguardian-seven-day-before.json` và `/tmp/tripguardian-seven-day-after.json`, do benchmark `tests/planning/bench_routes.py --runs 3` ghi lại. Benchmark chạy không mạng trên cùng fixture giả lập, đo median của ba lượt và so fingerprint kết quả trước/sau. Các fingerprint trùng nhau trong cả bốn trường hợp.

| Trường hợp | Trước tối ưu | Sau tối ưu | Tốc độ tương đối | Kết quả |
|---|---:|---:|---:|---|
| Tìm thứ tự bảy ngày, 4 điểm/ngày | 0,0207 giây | 0,0117 giây | 1,77× | Fingerprint trùng; 350 phút di chuyển; 0 vi phạm |
| Tạo kế hoạch 7 ngày, 28 điểm | 0,0768 giây | 0,0612 giây | 1,25× | Fingerprint trùng; `ok = true`; 1 phương án |
| Tìm thứ tự bảy ngày, 7 điểm/ngày | 7,8023 giây | 3,3855 giây | 2,30× | Fingerprint trùng; 560 phút di chuyển; 0 vi phạm |
| Tạo kế hoạch 7 ngày, 49 điểm | 1,6833 giây | 0,9336 giây | 1,80× | Fingerprint trùng; `ok = true`; 1 phương án |

Các trường hợp 4 và 7 điểm/ngày đo riêng việc xếp thứ tự trên bảy `DayCtx`. Các trường hợp 28 và 49 điểm đo tạo phiên/kế hoạch tổng hợp với bảy ngày. Thời gian này không gồm OSRM, mạng, crawl chỗ ở hay lời gọi Agent; benchmark dùng ma trận di chuyển giả lập. Do đó đây là số đo phần Planning tính toán thuần, không phải cam kết độ trễ end-to-end của ứng dụng. Số đo 7 điểm/ngày là trường hợp dày và đắt nhất trong benchmark này; nó không đại diện cho mọi chuyến bảy ngày.

## Benchmark chuyến 14 ngày được tái sử dụng

Các số sau lấy từ `/tmp/tripguardian_long_trip_after.json`, probe được phiên chuyến dài chạy trên 1.696 bản ghi corpus. Planning nhận ma trận giả lập và hàm geocode/sun giả lập; đây không phải đo thời gian mạng thật. `planning_s` là thời gian dựng lịch được probe ghi lại. Các kịch bản tổng hợp dùng bốn mức mật độ; hai kịch bản dữ liệu thực dùng 2 và 56 nơi đã chọn.

| Dữ liệu / mật độ | Số ngày | Số nơi chọn | Planning | Kết quả constraint và độ phủ |
|---|---:|---:|---:|---|
| Tổng hợp, rỗng | 14 | 0 | 0,004 giây | `ok = true`; không vi phạm; 14 ngày rỗng |
| Tổng hợp, thưa | 14 | 2 | 0,044 giây | `ok = true`; đặt đủ 2; không trùng; không vi phạm |
| Tổng hợp, cân bằng | 14 | 56 | 0,199 giây | `ok = true`; đặt đủ 56; không trùng; không vi phạm; có `days_fallback` |
| Tổng hợp, dày | 14 | 98 | 0,809 giây | Đặt đủ 98; không trùng; `ok = false` vì `day_window`; có `days_fallback` |
| Corpus, thưa | 14 | 2 | 0,116 giây | `ok = true`; 12 ngày rỗng; độ phủ `sparse`; 2 trải nghiệm trong mục tiêu 55; khoảng 10.034 phút rảnh ước tính |
| Corpus, cân bằng | 14 | 56 | 1,189 giây | `ok = true`; không vi phạm; độ phủ `enough`; 56 trải nghiệm trong mục tiêu 55; khoảng 1.996 phút rảnh ước tính |

Với dữ liệu corpus cân bằng, phân bổ theo ngày là `[1, 4, 5, 5, 5, 4, 4, 4, 4, 5, 3, 5, 4, 3]`. Cả hai tuần đều có nơi, và không có vi phạm constraint trong kết quả được probe ghi. Số 1,189 giây là thời gian dựng Planning cho fixture đó; không bao gồm việc người dùng tương tác thêm, gọi Agent, hoặc dịch vụ mạng thật.

Kịch bản tổng hợp 98 nơi cố ý tải xấp xỉ bảy nơi mỗi ngày. Planner vẫn giữ toàn bộ 98 nơi, nhưng validator báo lịch vượt cửa sổ ngày. Đây là kết quả fail-closed đúng thiết kế, không phải mất điểm âm thầm hay bằng chứng rằng mọi chuyến 14 ngày đều dựng được. `days_fallback` xuất hiện ở các fixture cân bằng/dày khi số cụm vượt ngưỡng tìm chính xác; khi đó cách chia ngày tham lam được dùng và cảnh báo được giữ lại.

Probe ghi riêng các thời gian Decision trước khi vào Planning: corpus thưa có `create_s = 0,730`, `select_s = 0,983`; corpus cân bằng có `create_s = 0,536`, `select_s = 14,494`. Đây không phải thời gian Planning; thời gian Planning tương ứng là 0,116 và 1,189 giây. Không cộng ba con số thành độ trễ người dùng nếu chưa bao gồm trạng thái UI, Agent và mọi dịch vụ live.

## Kiểm thử và bằng chứng

Kết quả tối ưu bảy ngày được xác minh bằng 511 test Planning trong snapshot cô lập ở thời điểm tích hợp, gồm route, schedule và constraint. Snapshot được tạo do file `src/trip/agent/prompt.py` trong checkout dùng chung đang rỗng lúc đó; snapshot khôi phục bản prompt đã commit chỉ để Planning import được. Số 511 thuộc snapshot trước khi test riêng `test_planning_long_trips.py` của phiên chuyến dài có trong checkout. Review độc lập so sánh toàn bộ `DayResult` của 33 bối cảnh exact/heuristic với route baseline, gồm các ngày trong tuần, pace, mặt trời, preference, mưa, ma trận có hướng và `cache_entries` bằng 0, 1, 2 hoặc 128; tất cả đều trùng.

Probe chuyến dài ghi trong tiến trình khác có `Trip + Decision: 419 passed, 1 deselected` và `legacy cache: 42 passed`. Các số này được giữ nguyên như bản ghi từ phiên đó, không được tính lại từ lần kiểm hiện tại. Probe Planning 14 ngày được tóm tắt ở bảng trên.

Trong lượt rà soát hiện tại, `src/trip/agent/prompt.py` đã có nội dung. Lệnh `python -m pytest tests/planning -q` đã được khởi chạy trực tiếp trên checkout dùng chung nhưng chưa trả kết quả; tiến trình bị chặn ở trạng thái I/O không ngắt được (`D`, `path_openat`) khi đọc đường dẫn trên filesystem dùng chung. Vì vậy báo cáo không tính lần chạy này là pass hoặc fail. Số liệu test hoàn tất được tái sử dụng ở trên giữ nguyên theo các output của từng phiên.

## Giới hạn khi diễn giải số liệu

- Benchmark bảy ngày dùng fixture và ma trận di chuyển giả lập, ba lượt chạy, báo median; nó đo mã lập lịch cục bộ, không đo dịch vụ live hoặc Agent.
- Probe 14 ngày dùng 1.696 bản ghi corpus, nhưng dùng hàm giả lập cho ma trận di chuyển và một số dữ liệu ngày. Hai cấu hình density thưa/cân bằng phản ánh shortlist probe, không phải mẫu ngẫu nhiên đại diện cho mọi người dùng.
- Thời gian `Decision create/select` nằm trước Planning và biến động theo số nơi; không gộp vào thời gian dựng lịch.
- Trên 14 ngày có cảnh báo chưa kiểm chứng; 14 ngày là mức dài nhất có số đo corpus trong probe được lưu ở đây. Hỗ trợ tới 30 ngày là giới hạn được phép trong code, không phải bằng chứng benchmark đến 30 ngày.
- Một kế hoạch `ok = false` với `day_window` phải tiếp tục báo không khả thi. Tối ưu hiệu năng không được phép biến kết quả này thành `ok = true` bằng cách bỏ điểm hoặc nới giờ.
