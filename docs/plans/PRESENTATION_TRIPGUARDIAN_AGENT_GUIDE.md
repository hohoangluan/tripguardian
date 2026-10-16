# Hướng dẫn Agent Local: Soạn nội dung Presentation — TripGuardian
**Dự án:** TripGuardian  
**Cuộc thi:** MLAI Hackathon 2026 — Decision Intelligence Challenge  
**Đội:** ARTIZ  
**Mục tiêu tài liệu:** Hướng dẫn agent chạy trên máy đọc mã nguồn hiện tại, tái kiểm chứng thông tin và soạn nội dung thuyết trình ngắn gọn, lịch sự, dễ hiểu cho ban giám khảo.

---

## 1. Nhiệm vụ

Hãy đọc repository TripGuardian đang có trên máy và tạo **bản nội dung presentation** cho phần thuyết trình vòng bảng. Không chỉ tóm tắt tài liệu cũ: phải kiểm tra lại các tuyên bố quan trọng với code, cấu hình, dữ liệu và test hiện tại.

Thời lượng thuyết trình vòng bảng theo hướng dẫn cuộc thi là **15 phút/đội**. Hãy thiết kế nội dung đủ gọn để trình bày trong khoảng **10–12 phút**, chừa thời gian cho demo, chuyển slide và phản biện. Nếu thời lượng thực tế hoặc format có thay đổi, ghi chú để người dùng xác nhận.

Ngôn ngữ đầu ra: **tiếng Việt**, văn phong lịch sự, rõ ràng, chuyên nghiệp; ưu tiên câu ngắn và giải thích theo ngôn ngữ sản phẩm. Chỉ dùng thuật ngữ kỹ thuật khi cần, kèm giải thích ngắn. Tránh phóng đại, khẩu hiệu chung chung, hoặc tuyên bố chưa có bằng chứng.

## 2. Nguồn cần đọc và thứ tự ưu tiên

1. **Mã nguồn hiện tại** — nguồn chính để xác minh hệ thống thực sự làm gì.
2. **Test hiện tại và kết quả chạy được** — xác minh hành vi, độ ổn định và phạm vi kiểm thử.
3. **Tài liệu kiến trúc mới nhất trên máy** — tìm các tài liệu như `TECHNICAL_REPORT.md`, `docs/PLANNING.md`, `docs/AGENT_HARNESS.md`, tài liệu Decision/Trip/Corpus/Live và README. Xác định phiên bản, ngày cập nhật nếu có.
4. **Báo cáo cập nhật gần đây** — ví dụ `OVERLOAD_THREE_PLANS_UPDATE_REPORT.md` và báo cáo implementation liên quan. Dùng để định hướng nơi cần kiểm tra, không mặc định mọi thông tin vẫn đúng.
5. **Tài liệu cuộc thi** — tiêu chí chấm và thời lượng thuyết trình trong tài liệu hướng dẫn MLAI Hackathon 2026.

Nếu tài liệu và code mâu thuẫn, **không tự chọn một bên rồi bỏ qua mâu thuẫn**. Ghi rõ: nội dung tài liệu, hành vi code hiện tại, cách đã kiểm chứng và kết luận an toàn để đưa lên slide. Không sửa code chỉ để làm cho báo cáo khớp.

## 3. Tiêu chí đánh giá cần được trả lời

Presentation cần cho ban giám khảo thấy rõ bằng chứng tương ứng với sáu tiêu chí sau:

| Tiêu chí | Điểm | Câu hỏi presentation cần trả lời |
|---|---:|---|
| Mức độ giải quyết vấn đề và tác động | 20 | Người dùng là ai? Họ đang gặp khó khăn gì? TripGuardian hỗ trợ quyết định nào và vì sao hữu ích? |
| Mức độ phù hợp với Việt Nam | 15 | Vì sao chọn Đà Lạt? Hệ thống xử lý tiếng Việt và dữ liệu địa phương ra sao? Các giới hạn thực tế là gì? |
| Tính sáng tạo và khác biệt | 20 | Điều gì vượt ra ngoài tìm kiếm địa điểm hoặc chatbot sinh lịch trình? Người dùng có quyền kiểm soát gì? |
| Đổi mới trong sử dụng dữ liệu & AI | 20 | Dữ liệu đến từ đâu, được kiểm chứng và biểu diễn thế nào? AI làm phần nào, code quyết định phần nào? Vì sao khuyến nghị được đưa ra? |
| Tính khả thi và sản phẩm thử nghiệm | 15 | Demo hiện tại chạy được những luồng nào? Kiến trúc có ranh giới rõ không? Test nào đã chạy? Điều gì chưa được xác minh? |
| Trình bày và trải nghiệm người dùng | 10 | UI có dễ hiểu không? Demo có thể cho thấy quyết định, giải thích, chỉnh sửa và kiểm tra tính khả thi như thế nào? |

Không cần ép tất cả thông tin kỹ thuật lên slide. Mỗi tiêu chí nên có một thông điệp chính và ít nhất một bằng chứng, ví dụ từ UI, luồng chạy, dữ liệu hoặc test. Nếu chưa có bằng chứng thì đánh dấu thiếu, không tự bịa.

## 4. Định vị sản phẩm cần kiểm tra

Tài liệu hiện có mô tả TripGuardian không đơn thuần là “AI tạo lịch trình”. Định vị đề xuất để kiểm tra với code:

> **TripGuardian hỗ trợ người đi du lịch tự túc chọn địa điểm phù hợp trước, hiểu lý do lựa chọn, rồi kiểm tra các địa điểm đã chọn có thể ghép thành một lịch trình khả thi hay không.**

Ba câu hỏi trung tâm:
- Nơi nào phù hợp với chuyến đi này?
- Vì sao hệ thống đề xuất nơi đó hoặc không đề xuất một nơi khác?
- Các địa điểm đã chọn có thực sự đi được cùng nhau trong giới hạn thời gian và các điều kiện của chuyến đi không?

Phạm vi được mô tả trong tài liệu hiện có là **Đà Lạt**, chuyến tự túc thường 2–4 ngày (hệ thống nhận đến 7 ngày). Phải kiểm tra lại phạm vi demo hiện tại và không tuyên bố đã kiểm chứng ở thành phố khác nếu chưa có bằng chứng.

## 5. Quy trình tái kiểm chứng bắt buộc

Trước khi soạn slide:

1. Xác định repository root và branch/commit hiện tại nếu có thể.
2. Tìm các tài liệu kiến trúc mới nhất; ghi đường dẫn, ngày cập nhật và những tài liệu cũ có nguy cơ gây nhầm lẫn.
3. Lập bản đồ các luồng người dùng chính từ UI → API/harness → module → dữ liệu → kết quả UI.
4. Kiểm tra code của các tính năng định đưa vào presentation. Không chỉ dựa vào tên module hoặc comment.
5. Chạy hoặc đọc kết quả các test liên quan; ưu tiên test tích hợp/browser cho luồng demo nếu môi trường cho phép.
6. Ghi lại lệnh test, số pass/fail/skip và phạm vi. Phân biệt test tập trung với tổng test suite; không cộng các nhóm test chồng lặp.
7. Kiểm tra những phụ thuộc ngoài như model API, dịch vụ định tuyến, thời tiết, nguồn crawl và cơ sở dữ liệu. Nêu rõ đang dùng live service, cache, fixture hay mock.
8. Chỉ lấy số liệu từ kết quả có thể truy nguyên tới file, lệnh, log hoặc fixture. Mỗi số liệu trên slide phải có nguồn nội bộ ghi trong speaker notes hoặc phần evidence.
9. Nếu không chạy được một kiểm chứng, ghi rõ lý do và không biến “chưa chạy” thành “đã pass”.

## 6. Cấu trúc presentation đề xuất

Tạo khoảng **8–10 slide**, điều chỉnh theo lượng bằng chứng thật. Nội dung dưới đây là khung, không phải yêu cầu phải giữ nguyên nếu code cho thấy cách trình bày khác tốt hơn.

### Slide 1 — Tên dự án và lời hứa giá trị
- Tên TripGuardian, đội ARTIZ, MLAI Hackathon 2026.
- Một câu mô tả dễ nhớ về giá trị sản phẩm.
- Hình giao diện hoặc sơ đồ tối giản nếu có ảnh chụp thật từ sản phẩm.
- Không mở đầu bằng danh sách công nghệ.

### Slide 2 — Vấn đề và người dùng mục tiêu
- Người tự lên kế hoạch chuyến đi, đi cá nhân/cặp đôi/nhóm nhỏ, tự di chuyển.
- Nỗi đau cần chứng minh: khó chọn giữa nhiều nơi, thông tin phân tán, lịch ghép không khả thi, khó hiểu vì sao một lựa chọn phù hợp.
- Nêu rõ đây là vấn đề mà hệ thống nhắm tới; không khẳng định đã chứng minh mức độ phổ biến nếu chưa có nghiên cứu hoặc khảo sát.

### Slide 3 — Giải pháp và khác biệt
- Luồng khái quát: hiểu chuyến đi → chọn địa điểm → kiểm tra tổ hợp → lập và kiểm chứng lịch → người dùng chỉnh sửa.
- Nêu rõ người dùng vẫn quyết định chọn địa điểm; hệ thống hỗ trợ, giải thích và phát hiện xung đột.
- So sánh ngắn với tìm kiếm/chatbot thông thường, chỉ khi so sánh được bằng tính năng thật.

### Slide 4 — Demo luồng người dùng
- Dùng luồng thực tế đang chạy trên phiên bản hiện tại.
- Chọn một kịch bản đơn giản, nhất quán xuyên suốt presentation.
- Thể hiện input, gợi ý địa điểm, lý do/đánh đổi, xung đột hoặc tính khả thi, kết quả lịch.
- Không trình diễn tính năng chưa kiểm tra được hoặc phụ thuộc dịch vụ đang lỗi.
- Ghi rõ phương án dự phòng demo nếu API/mạng không hoạt động.

### Slide 5 — Dữ liệu địa phương và độ tin cậy
- Trình bày các nguồn dữ liệu thực sự đang được sử dụng và vai trò riêng của mỗi nguồn.
- Giải thích ngắn cách dữ liệu thô trở thành thông tin có cấu trúc và cách giữ nguồn bằng chứng/provenance.
- Chỉ sử dụng số lượng địa điểm, observation, trạng thái kiểm chứng… sau khi tái xác minh từ dữ liệu hiện có.
- Nêu giới hạn quan trọng: dữ liệu có thể cũ; độ phủ giữa các thuộc tính không đồng đều; thông tin chưa biết không nên được trình bày như sự thật.

### Slide 6 — AI và logic ra quyết định
- Nêu vai trò thực tế của model/agent: diễn giải yêu cầu, trích xuất hoặc đề xuất theo code hiện hành.
- Nêu phần code tất định đảm nhiệm: validation, hard constraints, tính điểm, kiểm tra timeline và quyết định có cho chốt lịch hay không — chỉ giữ các vai trò xác nhận được trong code.
- Giải thích nguyên tắc an toàn: thiếu bằng chứng có thể là `unknown`; hard constraint không được âm thầm bỏ qua.
- Tránh nói “AI tự hiểu mọi thứ” hoặc “hallucination-free”.

### Slide 7 — Kiến trúc và tính khác biệt kỹ thuật
- Một sơ đồ đơn giản, dễ đọc; không chụp nguyên sơ đồ quá phức tạp trong tài liệu kỹ thuật.
- Ưu tiên cho thấy các ranh giới: dữ liệu/Place Intelligence, Trip Understanding, Place Decision, Planning & Validation, Live Context, Agent runtime và Harness/Web.
- Giải thích bằng ngôn ngữ phổ thông: module nào nhận đầu vào, module nào trả kết quả, nơi nào kiểm tra trước khi chốt.
- Chỉ đưa các module đang tồn tại và đường đi được xác minh trong code. Không cần đưa mọi package phụ lên slide.

### Slide 8 — Kiểm thử và bằng chứng hiện tại
- Nêu các nhóm test đã chạy và kết quả chính xác, ngày/lệnh chạy nếu có.
- Chọn 2–4 bằng chứng mạnh nhất gắn với luồng người dùng, chẳng hạn kiểm tra ràng buộc, xử lý lịch quá tải, preview/apply, hoặc browser flow nếu các test tương ứng vẫn hợp lệ.
- Phân biệt test tự động, demo bằng fixture, kiểm thử offline và thử nghiệm người dùng thật.
- Không gọi test pass là bằng chứng chất lượng khuyến nghị ngoài đời; không dùng thời gian chạy test suite như latency người dùng.

### Slide 9 — Giới hạn và hướng phát triển
- Chỉ nêu các giới hạn quan trọng đã xác nhận.
- Ví dụ cần xác minh: phạm vi mới chỉ kiểm chứng ở Đà Lạt, dữ liệu live chưa đầy đủ, thiếu thử nghiệm với người dùng thật, hoặc một số dịch vụ chưa được kiểm thử thật.
- Nêu hướng tiếp theo cụ thể và gắn với giới hạn, không hứa hẹn tính năng chưa có.

### Slide 10 — Kết luận
- Nhắc lại vấn đề, cách tiếp cận và điểm khác biệt.
- Kết luận cân bằng: điều đã xây dựng và kiểm chứng, điều cần tiếp tục đánh giá.
- Chuẩn bị chuyển sang Q&A.

Nếu có demo trực tiếp, có thể gộp slide 4 với 3 hoặc rút số slide. Không nhồi quá nhiều chữ; mỗi slide chỉ nên có 1 thông điệp chính, 3–5 gạch đầu dòng tối đa.

## 7. Định dạng đầu ra cần tạo

Tạo file Markdown, đề xuất tên:

`PRESENTATION_TRIPGUARDIAN.md`

Tài liệu cần có các phần:

1. **Tóm tắt thông điệp chính** — 3–5 câu.
2. **Kịch bản thuyết trình theo slide** — mỗi slide gồm:
   - Tiêu đề slide.
   - Mục tiêu/thông điệp chính.
   - Nội dung ngắn hiển thị trên slide.
   - Gợi ý hình ảnh, sơ đồ hoặc màn hình demo (chỉ khi có thật hoặc có thể chụp từ app).
   - Speaker notes: lời trình bày tự nhiên, lịch sự, đủ để nói nhưng không dài dòng.
   - Thời lượng ước tính.
   - Evidence: đường dẫn file/code/test/log/dữ liệu đã dùng để xác minh.
   - Trạng thái: `Đã xác minh`, `Xác minh một phần`, hoặc `Cần người dùng bổ sung`.
3. **Bản demo đề xuất** — các bước click/input theo đúng UI hiện tại, kết quả mong đợi, điều kiện để demo thành công và phương án dự phòng.
4. **Bảng đối chiếu tiêu chí chấm** — mỗi tiêu chí, slide trả lời, bằng chứng, phần còn thiếu.
5. **Danh sách thông tin cần người dùng bổ sung** — chỉ các câu hỏi thực sự chưa thể trả lời từ repo/tài liệu.
6. **Danh sách claim không được phép dùng** — các tuyên bố nghe có vẻ hấp dẫn nhưng chưa đủ bằng chứng, ví dụ chất lượng tốt hơn đối thủ, tốc độ nhanh hơn, tăng hiệu quả cho người dùng, độ chính xác cao, hoặc đã sẵn sàng production nếu chưa được đo/triển khai.

## 8. Quy tắc xử lý thông tin thiếu

Khi thiếu dữ liệu, không tự suy đoán và không dừng toàn bộ công việc. Hãy:
- Viết nội dung có thể xác minh được trước.
- Đánh dấu phần thiếu bằng `[[CẦN NGƯỜI DÙNG BỔ SUNG: ...]]`.
- Ghi rõ vì sao cần thông tin đó và nó ảnh hưởng slide/tiêu chí nào.
- Nếu có thể, đưa ra cách xác minh thay thế bằng code, test, log hoặc demo.
- Không tự điền kết quả đánh giá chính thức của cuộc thi, feedback người dùng, số người dùng, benchmark đối thủ, hoặc chất lượng thực tế nếu repo không có bằng chứng.

Các nội dung có thể cần người dùng xác nhận nếu không tìm thấy nguồn:
- Link demo đang hoạt động và thông tin đăng nhập demo (không ghi secret vào Markdown).
- Tình trạng dịch vụ/API trong ngày thuyết trình.
- Kịch bản demo mong muốn và tính năng chắc chắn sẽ trình diễn.
- Khảo sát/feedback người dùng thật, nếu có.
- Các kết quả đánh giá chính thức của cuộc thi, nếu đã được ban tổ chức công bố.
- Thành viên và vai trò từng người, nếu muốn giới thiệu trong slide.

## 9. Văn phong và cách trình bày

- Lịch sự, tự tin nhưng không khoa trương.
- Giải thích lợi ích trước, kỹ thuật sau.
- Ưu tiên câu ngắn, từ ngữ phổ thông, tránh lạm dụng tiếng Anh.
- Không dùng “đầu tiên trên thế giới”, “đột phá”, “hoàn toàn chính xác”, “không hallucination”, “real-time” hoặc “production-ready” nếu không có bằng chứng tương ứng.
- Không biến danh sách module thành phần trình bày chính.
- Không vẽ Mermaid trong nội dung cuối nếu hình đó khó đọc trên slide. Nếu cần sơ đồ, tạo sơ đồ đơn giản bằng các khối và mũi tên, chỉ gồm luồng chính.
- Mọi con số cần có đơn vị, thời điểm đo và nguồn.
- Không đưa thông tin cá nhân, API key, token, mật khẩu hoặc nội dung crawl nhạy cảm vào file đầu ra.

## 10. Checklist trước khi hoàn tất

- [ ] Đã đọc code và tài liệu kiến trúc mới nhất, không chỉ dựa vào tài liệu cũ.
- [ ] Đã xác minh từng tính năng được đưa vào slide.
- [ ] Đã phân biệt dữ liệu thật, fixture/mock và dịch vụ live.
- [ ] Đã đối chiếu đủ sáu tiêu chí đánh giá.
- [ ] Đã kiểm tra các con số, lệnh test và phạm vi test.
- [ ] Đã ghi chú phần chưa đủ bằng chứng, không bịa nội dung.
- [ ] Nội dung có thể trình bày trong khoảng 10–12 phút, không tính Q&A.
- [ ] Demo có đường đi rõ ràng và phương án dự phòng.
- [ ] Đã lưu đầu ra thành `PRESENTATION_TRIPGUARDIAN.md` trong thư mục tài liệu phù hợp của repository.
- [ ] Cuối cùng, trả về bản tóm tắt ngắn: file đã tạo, các tài liệu/code đã đọc, test đã chạy, các mâu thuẫn phát hiện và các câu hỏi cần người dùng trả lời.
