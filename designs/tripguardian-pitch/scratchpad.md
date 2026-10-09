# TripGuardian pitch scratchpad

## Title sequence

1. TripGuardian — Chọn đúng nơi trước khi xếp lịch
2. Người dùng không thiếu gợi ý; họ thiếu một quyết định có thể kiểm tra
3. Ở Việt Nam, một quyết định du lịch phải ghép nhiều nguồn
4. Các công cụ hiện tại giải quyết những phần khác nhau của hành trình
5. Khoảng trống nằm ở bước chốt lựa chọn dưới ràng buộc
6. TripGuardian bắt đầu từ quyết định, không bắt đầu từ một lịch sinh sẵn
7. Từ một câu kể đến danh sách địa điểm do người dùng chốt
8. Trước khi xếp lịch, mỗi lựa chọn đi qua bốn lớp kiểm tra
9. Mỗi kết luận giữ nguyên loại bằng chứng và độ chắc chắn
10. AI hiểu ngôn ngữ; rule và validator giữ ranh giới
11. Kiến trúc tách tri thức địa điểm khỏi bối cảnh chuyến đi
12. Bản thử nghiệm chạy trên dữ liệu địa điểm Đà Lạt và bài đo offline
13. Ba màn hình cho thấy người dùng kiểm soát quyết định
14. Những gì đã chứng minh — và chưa chứng minh
15. Từ hàng nghìn nơi đến một chuyến đi có thể tin
16. Nguồn và ranh giới so sánh

## Timing

00:25 · 00:55 · 00:55 · 01:25 · 01:05 · 00:50 · 01:00 · 01:25 · 01:00 · 01:10 · 01:00 · 01:10 · 01:00 · 00:50 · 00:25 · phụ lục

Tổng nội dung chính: khoảng 14 phút 35 giây.

## Public sources

- Vietnam travel behavior: `https://dam.cnt.traveloka.com/d/01jex2fdn47hrz16k4gtwxm8ga.pdf`
- Google Maps: `https://support.google.com/maps/answer/3184808?hl=en`
- Traveloka: `https://www.traveloka.com/en-vn/how-to/bookhotel`
- Wanderlog: `https://wanderlog.com/` and `https://help.wanderlog.com/hc/en-us/articles/13545624787867-Optimize-route`
- Tripadvisor AI: `https://www.tripadvisor.com/AIAssistant`
- Mindtrip: `https://resources.mindtrip.ai/travelers/help/traveler-faqs`
- Layla: `https://layla.ai/`
- Accessed: 2026-10-09

## Internal evidence

- Product scope and principles: `docs/Project_Context.md`, `docs/ARCHITECTURE.md`
- Current corpus metrics: `data/serving/places.json`, build 2026-10-08
- Current offline evaluation: `data/decision/eval.json` and `config/eval_trips.yaml`
- UI screenshots: `web/shots/app/`

## Claim boundaries

- **Đã triển khai:** pipeline Place Intelligence → Trip Understanding → Place Decision → Planning; evidence state; hard constraint; fail-closed; UI hiện tại.
- **Đã đo offline:** 30 Trip State mô phỏng offline chạy trên serving data; không phải 30 người dùng hoặc 30 chuyến thực địa.
- **Chưa chứng minh với người dùng:** thời gian tiết kiệm, mức tin tưởng, retention, conversion và tác động hành vi.
- So sánh cạnh tranh chỉ mô tả định vị và luồng từ tài liệu công khai; không phải benchmark chất lượng đối đầu và không chứng minh cơ chế đối thủ không tồn tại.
