# BRIEF RESEARCH — chứng minh mọi luận điểm

Đọc `BRIEF.md` (cùng thư mục) trước; mọi quy tắc ở đó vẫn áp dụng. File này thêm yêu cầu của người dùng:

> Mọi đề xuất, mọi ý nói trong tài liệu đều phải được chứng minh hoặc có cơ sở lý thuyết — không phải "tôi thấy đúng / tôi nghĩ nên như vậy". Mọi lập luận phải chặt chẽ, tường minh, chính xác.

## 1. Phân loại mỗi luận điểm
Đọc phần được giao, bóc **mọi** câu khẳng định (sự thật, con số, nhận định về người dùng/thị trường/đối thủ, lý do chọn thiết kế, tuyên bố hiệu quả). Gán một loại:

| Loại | Nghĩa | Bằng chứng chấp nhận |
|---|---|---|
| E-code | Hệ thống làm X | file + dòng/hàm trong `src/`, `web/src`, `config/`, test chứng minh (`tests/...::test_name`) |
| E-data | Con số đo được | `submission/NUMBERS.md` (nếu có) hoặc file `data/...` + trường + ngày; lệnh tái lập |
| T | Nhận định khoa học / thị trường / hành vi người dùng / lý do thiết kế dựa trên lý thuyết | Tài liệu đã kiểm chứng (mục 3) |
| D | Quyết định thiết kế | Phải có lý do thuộc E hoặc T. "Chúng tôi cho rằng…" không đủ |
| X | Không chứng minh được | Viết lại thành giả thuyết / [Mục tiêu] / phát biểu có điều kiện, hoặc **xóa** |

Tránh từ ngữ tuyệt đối không chứng minh được ("đầu tiên", "duy nhất", "luôn luôn", "hoàn toàn", "tối ưu"). So sánh với đối thủ chỉ ở mức chức năng công khai kiểm chứng được (trích nguồn nếu có) và ghi rõ là đối chiếu chức năng.

## 2. Tra cứu bằng sol (gpt-6.1-sol, có web search thật)
```
python3 -I submission/tools/sol.py \
  --prompt-file <câu hỏi.md> [--context <file>] --out submission/research/sol/<tên>.md
```
- Script tự đọc key từ `.env`; KHÔNG in, chép, hay gửi key ở đâu khác. Không sửa script.
- Mỗi lần gọi mất 1–5 phút; đặt timeout lệnh 900000 ms. Gọi tuần tự, **tối đa ~12 lần** mỗi agent; gom 4–8 luận điểm cùng chủ đề vào một câu hỏi.
- Câu hỏi nên yêu cầu: nguồn học thuật bình duyệt (journal/hội nghị, có DOI) hoặc nguồn chính thức (cơ quan nhà nước, tổ chức ngành, báo cáo có phương pháp); tên tác giả, năm, tiêu đề, venue, DOI/URL; **trích nguyên văn đoạn chứng minh**; nêu rõ nếu không tìm thấy. Có thể hỏi bằng tiếng Anh, và tìm cả nguồn tiếng Việt cho số liệu Việt Nam.
- Chỉ gửi sol nội dung bản nháp/luận điểm; không gửi secret, dữ liệu người dùng, IP nội bộ.
- Có thể dùng sol như người phản biện: "tìm điểm yếu/phản ví dụ của lập luận này", rồi tự cân nhắc.

## 3. Kiểm chứng trích dẫn (bắt buộc — LLM có thể bịa)
Một tài liệu chỉ được đưa vào báo cáo khi:
1. URL của nó xuất hiện trong mục "Nguồn web (url_citation)" do sol trả về từ tìm kiếm thật, **hoặc** bạn tự mở được bằng WebFetch (DOI → trang nhà xuất bản / doi.org / Crossref `https://api.crossref.org/works/<DOI>`); và
2. Nội dung bạn dẫn khớp với nguồn (tiêu đề, tác giả, năm; con số/nhận định thật sự có trong nguồn — kiểm bằng WebFetch abstract/trang nguồn khi có thể).
Không qua được → không dùng. Ưu tiên: bài bình duyệt > báo cáo chính thức > báo cáo ngành có phương pháp > báo chí uy tín. Không dùng Wikipedia/blog làm nguồn chính.

## 4. Sản phẩm
1. **Sổ luận điểm** `submission/research/<mã phần>_claims.md`: bảng `# | Luận điểm (trích ngắn) | Loại | Bằng chứng (file:dòng / NUMBERS / tài liệu) | Trạng thái kiểm chứng | Xử lý (giữ / sửa / bỏ)`.
2. **Sửa trực tiếp file phần được giao** (chỉ file đó): thêm trích dẫn kiểu tác giả–năm `(Park & Jang, 2013)` ngay sau luận điểm; viết lại hoặc xóa luận điểm X; tách rõ "đã đo" và "[Mục tiêu]"; thêm câu lý do có cơ sở cho mỗi quyết định thiết kế. Giữ cấu trúc mục, giữ các `<!-- src: -->` hiện có (thêm `<!-- src: -->` cho bằng chứng code mới). Nếu thêm nội dung làm phần dài ra, cắt chỗ khác để giữ độ dài gần như cũ.
3. Cuối file phần: mục `### Tài liệu tham khảo của phần này` — mỗi mục: Tác giả (Năm). Tiêu đề. *Venue*, tập(số), trang. DOI/URL — kèm `<!-- verified: url_citation | webfetch -->`.

## 5. Trả về (ngắn)
Số luận điểm theo loại; số đã sửa/bỏ; danh sách tài liệu đã kiểm chứng; luận điểm quan trọng vẫn chưa chứng minh được (người dùng cần quyết định); số lần gọi sol.
