# BRIEF chung — Báo cáo "Proposal & Tech Spec" TripGuardian

Repo: `/workingspace_aiclub/WorkingSpace/Personal/vannk/tripguardian` (gọi tắt REPO).
Đầu ra cuối: một file PDF nộp ban giám khảo cuộc thi (TMA Decision Intelligence Challenge · MLAI Hackathon 2026), kèm link GitHub code. Vòng chung kết 17/10/2026.

## Người đọc
Ban giám khảo kỹ thuật + nghiệp vụ. Họ sẽ mở repo để đối chiếu. Họ chấm theo 6 tiêu chí (thang 100):

| TC | Tiêu chí | Điểm | Chi tiết |
|---|---|---|---|
| TC1 | Mức độ giải quyết vấn đề và tác động | 20 | Xác định rõ người dùng và quyết định cần hỗ trợ; giải quyết đúng nhu cầu thực tế, có tiềm năng tác động |
| TC2 | Mức độ phù hợp với Việt Nam | 15 | Khai thác đặc thù địa phương, tương thích dữ liệu, hạ tầng mạng và ngôn ngữ tiếng Việt |
| TC3 | Tính sáng tạo và khác biệt | 20 | Cách tiếp cận mới mẻ, vượt ra ngoài tính năng tìm kiếm hoặc chatbot thông thường |
| TC4 | Đổi mới trong sử dụng Dữ liệu & AI | 20 | Chiến lược dữ liệu minh bạch; AI được ứng dụng tối ưu, có giải thích rõ ràng lý do đưa ra khuyến nghị |
| TC5 | Tính khả thi và sản phẩm thử nghiệm | 15 | Ứng dụng hoạt động ổn định, kiến trúc hệ thống bài bản, có khả năng tích hợp dữ liệu thực tế |
| TC6 | Trình bày và Trải nghiệm người dùng | 10 | Giao diện UI/UX trực quan, dễ sử dụng; thuyết trình và phản biện thuyết phục |

## Bố cục toàn báo cáo (mỗi agent chỉ viết phần được giao)
- Mở đầu: tổng quan điều hành, khẩu hiệu, tóm tắt, kỷ luật tuyên bố (do người điều phối viết)
- PHẦN A — PROPOSAL: §1 Bài toán & tác động [TC1] · §2 Phù hợp Việt Nam [TC2] · §3 Sáng tạo & khác biệt [TC3] · §4 Đổi mới Dữ liệu & AI [TC4]
- PHẦN B — TECH SPEC [TC5]: §5 Yêu cầu · §6 Kiến trúc tổng thể · §7 Đặc tả từng giai đoạn P1–P5 · §8 Schema dữ liệu chính · §9 Tích hợp dữ liệu thực & API · §10 Triển khai & vận hành · §11 Bảo mật & quyền riêng tư · §12 Kiểm thử & đánh giá · §13 Giới hạn & sổ rủi ro
- PHẦN C — SẢN PHẨM & TRẢI NGHIỆM [TC6]: §14 Luồng màn hình · §15 Kịch bản demo cho giám khảo · §16 Nghiên cứu người dùng
- Kết: §17 Lộ trình & kết luận · §18 Đối chiếu tiêu chí (người điều phối) · Phụ lục A Hướng dẫn chạy · Phụ lục B Bản đồ repo · Phụ lục C Tài liệu tham khảo

Phân vai: Phần A giải thích *vì sao / cái gì / khác gì* ở mức quyết định; Phần B giải thích *xây thế nào* với contract, module, file. Phần A được trỏ sang Phần B ("xem §7.3") thay vì chép chi tiết. Không chép lại nội dung mục khác.

## Nguồn sự thật
- Tài liệu chính thức: `REPO/docs/` — `PROJECT_CONTEXT.md`, `ARCHITECTURE.md`, `P1_CORPUS.md` … `P5_COMPANION.md`, `AGENT_HARNESS.md`, `ACCOUNTS.md`, `ANALYTICS.md`, `SPEECH.md`, `LLM_PROVIDER.md`, `WEB.md`, `UI_DESIGN.md`, `plans/OPEN_TASKS.md`, `log/DEV_LOG.md`. Cùng `REPO/README.md`, `REPO/PRODUCT.md`, `REPO/config/*.yaml`, `REPO/src/`, `REPO/web/`, `REPO/tests/`.
- Khi tài liệu và code mâu thuẫn, **code thắng**; ghi chú mâu thuẫn trong báo cáo trả về cho người điều phối (không đưa vào văn bản).
- Mẫu hình thức do BTC gửi: `REPO/TMA__proposal_vi.docx.md` (dự án KHÁC, chỉ học văn phong/cấu trúc, KHÔNG lấy nội dung). Đọc dòng 1–135 là đủ cảm nhận văn phong; file rất dài, không đọc hết.

## Quy tắc viết (bắt buộc)
1. Tiếng Việt, văn phong báo cáo kỹ thuật trang trọng, súc tích, như mẫu BTC. Giữ nguyên identifier/thuật ngữ code (`SearchInput`, `DecisionOutput`, `unknown`, P1…P5) trong backtick.
2. Sản phẩm tên **TripGuardian**. Phạm vi kiểm chứng: **Đà Lạt**.
3. **Không bịa.** Mọi con số (số địa điểm, số test, độ chính xác, độ trễ, số nguồn, …) phải lấy từ file hoặc output lệnh trong repo. Ngay sau con số đặt chú thích nguồn dạng HTML comment: `<!-- src: docs/P1_CORPUS.md §5 -->` hoặc `<!-- src: lệnh `...` -->`. Chưa đo được → gắn nhãn **[Mục tiêu]** hoặc ghi rõ "chưa đo". Không chắc → không viết.
4. Không tuyên bố tính năng chưa có trong code. Tính năng đang làm dở → ghi vào "giới hạn" hoặc "lộ trình", gắn nhãn.
5. Tiêu đề mục dạng `## 4. Đổi mới trong sử dụng Dữ liệu & AI [TC4]`, mục con `### 4.1 ...`. Đúng số mục được giao.
6. Ưu tiên bảng và sơ đồ mermaid ngắn (flowchart/sequence/state, ít chữ, mỗi sơ đồ một ý) thay cho đoạn văn dài. Sơ đồ mermaid sẽ được render sang PDF — giữ cú pháp đơn giản, nhãn có ký tự đặc biệt đặt trong ngoặc kép.
7. Trỏ tới bằng chứng trong repo bằng đường dẫn tương đối trong backtick (`src/decision/...`), để giám khảo mở được.
8. Ảnh chụp màn hình chưa có: đặt placeholder `> **[ẢNH: <màn hình>, route `<...>`]**`.
9. Độ dài: theo ngân sách trang được giao (~400–450 từ/trang, bảng/sơ đồ tính vào trang).
10. Không dùng emoji. Không viết "trong tương lai sẽ…" ở phần mô tả hiện trạng; lộ trình để ở §17.

## Quy tắc an toàn (bắt buộc)
- Working tree dùng chung với nhiều phiên khác và có nhiều thay đổi chưa commit: **chỉ đọc** repo, **chỉ ghi** đúng file đầu ra được giao. Không sửa, không xóa, không format file nào khác. Không git add/commit/stash/checkout.
- Không chạy crawler, server, trình duyệt, Playwright, không gọi model/LLM (kể cả host Gemma trên LAN), không gọi mạng ra ngoài.
- Lệnh đọc (`cat`, `grep`, `ls`, `wc`, `python -c` đọc file JSON/YAML/SQLite chỉ-đọc) thì được. Venv/cache phải nằm trong repo; không cài gói.

## Trả về cho người điều phối (tin nhắn cuối, ngắn)
- Đường dẫn file đã viết, số từ ước tính.
- Danh sách con số đã dùng + nguồn.
- Những chỗ đã gắn [Mục tiêu]/placeholder.
- Mâu thuẫn tài liệu ↔ code phát hiện được, và điều gì cần người điều phối/người dùng xác nhận.
