# TripGuardian — Hỗ trợ lựa chọn địa điểm và lập lịch trình cá nhân hóa

**Đội ARTIZ**

Bản nội dung thuyết trình theo mạch: **Bài toán → Vấn đề → Giải pháp hiện nay → Hạn chế → TripGuardian → Phù hợp Việt Nam → Sáng tạo và khác biệt → Dữ liệu và AI → Khả thi và thực nghiệm → Trải nghiệm người dùng.**

Phạm vi triển khai và kiểm chứng ban đầu: **Đà Lạt**. Các mục khảo sát và phản hồi người dùng để trống để nhóm bổ sung từ Google Form.

## 1. Bài toán: từ mong muốn đi chơi đến một kế hoạch cụ thể

Người muốn đi chơi hoặc du lịch tự túc cần quyết định đi đâu, làm gì, vào lúc nào và di chuyển ra sao. Họ có thể bắt đầu từ một ý tưởng còn mơ hồ, một vài địa điểm đã lưu hoặc một danh sách những nơi nhất định muốn ghé.

Đầu ra họ cần là một kế hoạch phù hợp với quỹ thời gian, ngân sách, sở thích, phương tiện và người đồng hành; đủ rõ để cân nhắc và điều chỉnh trước chuyến đi.

TripGuardian hướng tới người tự lên kế hoạch: cá nhân, cặp đôi, gia đình và nhóm nhỏ. Tình huống trọng tâm để trình diễn là chuyến đi Đà Lạt ngắn ngày.

> **Tình huống minh họa xuyên suốt:** Một người lên kế hoạch đi Đà Lạt ba ngày cùng bố mẹ, di chuyển bằng ô tô, thích thiên nhiên và cà phê, muốn lịch nhẹ, tránh đi bộ nhiều và kết thúc mỗi ngày trước 18 giờ. Người này đã lưu một số địa điểm nhưng chưa biết nơi nào phù hợp và có ghép được vào cùng chuyến đi hay không.

Đây là tình huống minh họa sản phẩm, chưa phải kết quả quan sát người tham gia khảo sát.

## 2. Vấn đề: nhiều thông tin nhưng vẫn phải tự ra quyết định

Từ danh sách gợi ý đến chuyến đi thực tế còn nhiều bước phải làm. Những khó khăn TripGuardian tập trung giải quyết gồm:

| Khó khăn | Hệ quả đối với việc lên kế hoạch |
|---|---|
| Thông tin rải rác giữa video, bản đồ, review và website | Phải mở nhiều nguồn, ghi nhớ và đối chiếu lại |
| Địa điểm đẹp hoặc nổi tiếng chưa chắc phù hợp chuyến này | Dễ bỏ sót nhu cầu người đồng hành và các điều kiện bắt buộc |
| Giờ, giá và trải nghiệm có thể thiếu, cũ hoặc mâu thuẫn | Khó biết nên tin thông tin nào và cần xác minh gì thêm |
| Các nơi phù hợp riêng lẻ chưa chắc đi được cùng nhau | Có thể vượt giờ, di chuyển quá nhiều hoặc thiếu thời gian nghỉ |
| Thay một lựa chọn làm ảnh hưởng các phần còn lại | Phải kiểm tra lại thứ tự, giờ ghé, chi phí và các điểm đã chốt |

Trong tình huống minh họa, người dùng cần biết một nơi có phù hợp với bố mẹ và yêu cầu tránh đi bộ nhiều hay không, trước khi cân nhắc vẻ đẹp hoặc độ nổi tiếng. Sau khi chọn, họ còn phải kiểm tra cả ngày có kết thúc trước 18 giờ không.

**Vấn đề cốt lõi là hỗ trợ ra quyết định dưới nhiều ràng buộc: chọn nơi phù hợp, hiểu đánh đổi và kiểm tra tổ hợp đã chọn.** Mức độ phổ biến và mức mất công thực tế của các khó khăn này cần được bổ sung bằng khảo sát.

## 3. Các giải pháp hiện nay: người dùng đang giải quyết như thế nào?

### 3.1. Các cách tiếp cận trong bối cảnh Việt Nam

Một hành trình tự lên kế hoạch có thể kết hợp các bước: xem nội dung trên TikTok, Facebook hoặc YouTube để tìm cảm hứng; tra Google Maps để kiểm tra vị trí và đường đi; đọc review hoặc website để tìm thông tin; sau đó ghi lại vào ghi chú, bảng tính hoặc nhờ AI tổ chức kế hoạch.

Đây là các cách tiếp cận để đối chiếu, chưa phải kết luận về tỷ lệ sử dụng của người Việt Nam.

| Công cụ / cách làm | Giá trị đối với việc chuẩn bị chuyến đi |
|---|---|
| TikTok và nội dung cộng đồng | Xem hình ảnh, video và góc nhìn trải nghiệm; tìm ý tưởng muốn khám phá |
| Google Maps | Tìm địa điểm, đọc thông tin và review, xem đường đi, lưu và chia sẻ danh sách |
| Ghi chú, bảng tính và trao đổi trong nhóm | Tự tổng hợp lựa chọn, phân ngày và thống nhất với người đi cùng |
| ChatGPT | Trao đổi yêu cầu, tổng hợp và điều chỉnh kế hoạch bằng hội thoại; khi dùng tìm kiếm có thể tra thông tin hiện hành và dẫn nguồn |

Nguồn mô tả chức năng: [Google Maps](https://www.google.com/maps/about/), [ChatGPT Search](https://help.openai.com/en/articles/9237897-searching-the-web-with-chatgpt). Chức năng cụ thể còn phụ thuộc khu vực, phiên bản và chế độ sử dụng.

### 3.2. Các sản phẩm hỗ trợ du lịch quốc tế

| Sản phẩm | Cách tiếp cận được công bố |
|---|---|
| [Layla](https://layla.ai/about) | Hội thoại để xây chuyến đi cá nhân hóa, điều chỉnh kế hoạch và hỗ trợ đặt dịch vụ; có lựa chọn kết hợp Travel Advisor |
| [Mindtrip](https://mindtrip.ai/) | Trợ lý du lịch ghi nhớ sở thích, hỗ trợ chọn dịch vụ, tổ chức chuyến đi và điều chỉnh theo bối cảnh |
| [Tripadvisor AI](https://www.tripadvisor.com/AIAssistant) | Đề xuất dựa trên nội dung đánh giá, so sánh lựa chọn và xây lịch theo ngày có thể chỉnh sửa |

Các sản phẩm này cho thấy cá nhân hóa, hội thoại và chỉnh sửa lịch đã có trên thị trường. TripGuardian cần làm rõ giá trị cụ thể hơn việc chỉ tạo được một lịch trình bằng AI.

Đối chiếu chức năng công khai ngày 15/10/2026; bảng này không phải kết quả thử nghiệm chất lượng giữa các sản phẩm.

## 4. Hạn chế và khoảng trống cần giải quyết

### 4.1. Từ nội dung khám phá đến quyết định cho cả chuyến đi

Video và review giúp hình dung trải nghiệm, nhưng một nội dung riêng lẻ không đủ xác nhận địa điểm đáp ứng toàn bộ yêu cầu của chuyến đi. Hình ảnh đẹp không chứng minh đường đi phù hợp người hạn chế vận động; giá từng được nhắc đến không tự trở thành giá hiện hành.

Bản đồ, danh sách và ghi chú giúp lưu thông tin, nhưng trong quy trình tự tổng hợp, người dùng vẫn phải nối đặc điểm địa điểm với nhu cầu chuyến đi và kiểm tra tính khả thi của cả danh sách.

### 4.2. Từ kế hoạch được đề xuất đến kế hoạch đã kiểm tra

Với ChatGPT hoặc AI travel planner, cần phân biệt việc đưa ra một câu trả lời có vẻ hợp lý với việc lịch trình đã được kiểm tra trên dữ liệu cụ thể. Các câu hỏi cần kiểm chứng gồm:

- Yêu cầu bắt buộc có được giữ đúng qua từng lượt trao đổi và chỉnh sửa không?
- Nhận định về địa điểm dựa trên bằng chứng nào? Khi thiếu dữ liệu, hệ thống thể hiện ra sao?
- Lịch có đủ thời gian di chuyển, tham quan và nghỉ trong cửa sổ ngày không?
- Khi phải bỏ hoặc đổi một nơi, người dùng có hiểu hệ quả và được quyết định không?

Đây là các tiêu chí đối chiếu với TikTok, Google Maps, ChatGPT, Layla và Mindtrip theo vai trò của từng công cụ; **chưa phải bằng chứng rằng các sản phẩm đó đều không xử lý được**. Muốn kết luận một sản phẩm làm chưa tốt cần có tình huống thử nghiệm và đầu ra lưu lại.

**Khoảng trống TripGuardian tập trung vào:** nối bằng chứng về địa điểm với yêu cầu chuyến đi, hỗ trợ người dùng tuyển chọn, rồi kiểm tra và giải thích tính khả thi của cả tổ hợp.

## 5. Giải pháp TripGuardian — Mức độ giải quyết vấn đề và tác động: 20 điểm

### 5.1. Chọn nơi phù hợp trước, lập và kiểm tra lịch sau

TripGuardian giúp người dùng trả lời ba câu hỏi:

1. **Nơi nào phù hợp với chuyến đi này?**
2. **Vì sao nên chọn, cân nhắc bỏ hoặc đổi nơi đó?**
3. **Những nơi đã chọn có đi được cùng nhau không?**

Luồng sản phẩm: **Hiểu chuyến đi → So sánh và tuyển chọn địa điểm → Lập và kiểm tra lịch → Chỉnh sửa → Xác nhận.**

| Vấn đề | Cách TripGuardian xử lý | Lợi ích hướng tới |
|---|---|---|
| Nhu cầu còn mơ hồ hoặc dễ bị hiểu sai | Làm rõ thông tin và cho xem bản hiểu chuyến đi | Giảm việc lập kế hoạch trên giả định sai |
| Khó nhận biết nơi phù hợp | Sàng lọc yêu cầu bắt buộc trước khi xếp hạng sở thích; giải thích lựa chọn | Hỗ trợ chọn theo bối cảnh thay vì chỉ theo độ nổi tiếng |
| Thông tin thiếu hoặc mâu thuẫn | Giữ nguồn, bằng chứng và trạng thái chưa chắc chắn | Biết điều gì cần kiểm tra thêm |
| Danh sách quá tải hoặc xung đột | Kiểm tra sơ bộ tổ hợp rồi kiểm tra dòng thời gian chi tiết | Phát hiện xung đột trước khi chốt |
| Khó sửa kế hoạch | Cho xem trước, áp dụng thay đổi và kiểm tra lại | Thấy hệ quả của quyết định và giữ quyền chủ động |

### 5.2. Minh họa trên chuyến đi Đà Lạt

Với yêu cầu đi cùng bố mẹ, lịch nhẹ và tránh đi bộ nhiều, hệ thống làm rõ yêu cầu bắt buộc rồi sàng lọc dựa trên dữ liệu hiện có. Nơi thiếu bằng chứng cho yêu cầu bắt buộc không được tự coi là đáp ứng; có thể được tách ra hoặc gắn cờ theo chính sách của yêu cầu.

Người dùng xem thông tin, so sánh và tuyển chọn. Planning tiếp tục kiểm tra giờ ghé, thời gian di chuyển, thời lượng tham quan và giờ kết thúc ngày. Nếu tổ hợp quá tải, hệ thống trình bày các hướng điều chỉnh cùng những lựa chọn giữ hoặc bỏ; phương án không hợp lệ không được chốt.

Người dùng có thể đổi hoặc bỏ nơi, chuyển ngày, thay cửa sổ giờ và xem trước kết quả. Những thay đổi ảnh hưởng lịch phải được kiểm tra lại.

### 5.3. Mức tác động có thể khẳng định

Sản phẩm đã có các cơ chế hỗ trợ lựa chọn và kiểm tra lịch. Tác động hướng tới là giảm công sức tổng hợp, giảm lỗi kế hoạch và tăng khả năng kiểm soát của người dùng.

Chưa dùng các phát biểu như “giảm X% thời gian”, “người dùng hài lòng hơn” hoặc “tốt hơn Layla” khi chưa có phép đo tương ứng. Số đo kỹ thuật hiện có nằm ở phần 9; kết quả người dùng sẽ bổ sung ở phần 10.

## 6. Mức độ phù hợp với Việt Nam — 15 điểm

### 6.1. Phù hợp ở ngôn ngữ, dữ liệu và ngữ cảnh chuyến đi

| Đặc điểm cần đáp ứng | Cách hệ thống xử lý |
|---|---|
| Người dùng diễn đạt nhu cầu bằng tiếng Việt | Hội thoại và giao diện tiếng Việt; nhu cầu được chuyển thành dữ liệu có cấu trúc |
| Ngân sách có nhiều cách nói | Biểu diễn VND và giữ phạm vi: cả chuyến, mỗi ngày, mỗi người hoặc mỗi người mỗi ngày; giữ dấu vết suy luận khi phạm vi được suy ra |
| Thông tin trải nghiệm nằm trong review và video địa phương | Pipeline riêng cho Google Maps và TikTok; ASR tiếng Việt, chữ và hình ảnh bổ sung bằng chứng |
| Đi cùng gia đình và sử dụng phương tiện khác nhau | Biểu diễn người đồng hành, phương tiện, mức vận động và yêu cầu liên quan |
| Trải nghiệm phụ thuộc thời điểm | Xét cửa sổ ngày, thời tiết và ngữ cảnh thời gian trong dữ liệu được hỗ trợ |

### 6.2. Vì sao chọn Đà Lạt để kiểm chứng?

Đà Lạt là phạm vi đủ cụ thể để xây dữ liệu, kiểm tra chất lượng và trình diễn việc phối hợp tham quan, cà phê, ăn uống và chỗ ở. Các tình huống về di chuyển, ngoài trời và khung giờ giúp kiểm chứng nhiều ràng buộc trong cùng một chuyến đi.

Lợi thế nhóm hướng tới là kiểm soát sâu dữ liệu và luồng quyết định trong một địa bàn cụ thể. Phạm vi ban đầu này chưa chứng minh khả năng bao phủ toàn Việt Nam hoặc chất lượng vượt sản phẩm quốc tế.

Để kết luận “phù hợp hơn”, cần so trên cùng tình huống Việt Nam: hiểu tiếng Việt, độ đầy đủ của bằng chứng địa phương, tính khả thi và công sức người dùng. Chưa có kết quả đối chứng thì chỉ khẳng định những yếu tố phù hợp đã xây dựng.

## 7. Tính sáng tạo và khác biệt — 20 điểm

### 7.1. Đóng góp tập trung vào chất lượng quyết định

Điểm nhóm muốn làm rõ là sự kết hợp giữa **tri thức địa điểm có bằng chứng, tuyển chọn do người dùng kiểm soát và kiểm tra khả thi ở cấp tổ hợp**.

| Trục đối chiếu | Cách tiếp cận của TripGuardian | Giá trị cần thể hiện qua demo / thực nghiệm |
|---|---|---|
| Từ nội dung đến bằng chứng | Tách fact vận hành, tín hiệu trải nghiệm và ước lượng; giữ nguồn và trạng thái | Có thể truy lại cơ sở của một nhận định |
| Từ gợi ý đến tuyển chọn | Cho người dùng so sánh, giữ, bỏ và khóa lựa chọn trước khi chốt lịch | Người dùng hiểu và kiểm soát lựa chọn |
| Từ hợp từng nơi đến hợp cả chuyến | Decision kiểm tra sơ bộ, Planning kiểm tra dòng thời gian chi tiết | Phát hiện xung đột chỉ xuất hiện khi ghép nơi |
| Từ tối ưu một chiều đến cân nhắc đánh đổi | Đưa phương án theo mục tiêu và giải thích hệ quả giữ / bỏ | Thấy được cái giá của mỗi phương án |
| Từ hiểu yêu cầu đến giữ đúng yêu cầu | Dùng contract chung qua các giai đoạn và kiểm tra lại sau thay đổi | Yêu cầu không bị mất khi bàn giao hoặc sửa lịch |

Các mục tiêu lập lịch có trong hệ thống gồm **Ít di chuyển, Chi phí thấp, Vững trước thời tiết, Đa dạng trải nghiệm, Hợp sở thích**. Mục tiêu được dùng tùy bối cảnh và dữ liệu; không phải mọi chuyến đều có đủ năm phương án khả dụng.

### 7.2. So với ai và mới ở mức nào?

So với quy trình tự ghép video, bản đồ và ghi chú, TripGuardian cung cấp một luồng chung từ bằng chứng đến lựa chọn và kiểm tra lịch.

So với ChatGPT, Layla hoặc Mindtrip, nhóm cần chứng minh cách xử lý bằng chứng, thiếu dữ liệu, yêu cầu bắt buộc và xung đột cụ thể. Cá nhân hóa, hội thoại, bản đồ hoặc chỉnh sửa lịch riêng lẻ không đủ để khẳng định tính mới vì thị trường đã có các chức năng này.

Đóng góp được trình bày ở mức **thiết kế và tích hợp hệ thống cho bài toán đã chọn**. Chưa khẳng định một thuật toán mới, “đầu tiên trên thị trường”, hay suy đoán vì sao đối thủ không làm. Phần nào không có thông tin về cơ chế nội bộ của đối thủ được ghi là chưa đủ cơ sở so sánh.

## 8. Đổi mới trong sử dụng dữ liệu và AI — 20 điểm

### 8.1. Xây tri thức địa điểm theo vai trò từng nguồn

Google Maps cung cấp tập địa điểm, định danh và thông tin địa điểm. Review, ảnh và TikTok bổ sung bằng chứng về trải nghiệm cho địa điểm đã xác định; nguồn chính thức được ưu tiên cho thông tin vận hành khi có.

TikTok không được dùng để tự tạo địa điểm mới, và một bình luận không được nâng thành fact. Dữ liệu mỗi nguồn có pipeline và nơi lưu riêng để giữ nguồn gốc và kiểm tra lỗi.

| Loại dữ liệu | Cách biểu diễn |
|---|---|
| **Fact** | Giờ, giá, quy định; có nguồn và giữ xung đột nếu chưa giải quyết được |
| **Signal** | Xu hướng trải nghiệm như độ đông, yên tĩnh, đường dốc; gắn bối cảnh và bằng chứng |
| **Estimate** | Khoảng thời gian tham quan được suy ra theo quy tắc |

Thiếu hoặc xung đột bằng chứng được giữ ở trạng thái tương ứng như `unknown` / `uncertain`; không tự chuyển thành đáp ứng hay không đáp ứng.

### 8.2. Bốn giai đoạn với trách nhiệm rõ ràng

```text
Offline:
Nguồn địa điểm → Trích xuất → Kiểm tra → Tổng hợp → Place Intelligence

Online:
Hiểu chuyến đi → Search Input
              → Place Decision → Người dùng tuyển chọn → Decision Output
              → Planning & Validation + ngữ cảnh live → Plan Output
```

| Giai đoạn | Trách nhiệm |
|---|---|
| Place Intelligence | Xây dữ liệu địa điểm có bằng chứng để dùng lại |
| Trip Understanding | Hiểu nhu cầu chuyến đi và thông tin còn cần làm rõ |
| Place Decision | Sàng lọc, xếp hạng, so sánh và kiểm tra sơ bộ tổ hợp |
| Planning & Validation | Chia ngày, xếp giờ, kiểm tra lịch, đánh giá độ vững và hỗ trợ sửa |

Offline ghi tri thức địa điểm; online đọc tri thức đó và lưu trạng thái chuyến đi, hồ sơ người dùng. Ngữ cảnh live như dự báo thời tiết không được tự ghi thành thuộc tính lâu dài của địa điểm.

### 8.3. AI hỗ trợ nhận thức; bộ kiểm tra quyết định tính hợp lệ

| Vai trò | Công việc |
|---|---|
| ASR | Chuyển tiếng nói trong video thành transcript có mốc thời gian |
| Extractor | Đọc chữ, hình ảnh và nội dung để trích thông tin có cấu trúc |
| Judge | Kiểm tra nhận định và xử lý các quyết định cần kiểm soát rủi ro |
| Embedder | Hỗ trợ truy xuất, xếp hạng và gom cụm; độ tương tự không thay thế bằng chứng |
| Agent | Hiểu hội thoại và đề xuất hành động trong phạm vi được phép |
| Code và validator | Tổng hợp, kiểm dữ liệu, quyền hành động, ràng buộc và dòng thời gian |

Model cụ thể được cấu hình theo vai trò. Trong Planning, đề xuất của Agent được kiểm tra trên nháp; lỗi, quá hạn hoặc không đạt điều kiện thì giữ baseline đã kiểm.

Ba loại điều kiện được xử lý riêng:

- **Physical constraint:** không có đường nới để làm một lịch bất khả thi thành hợp lệ.
- **User hard constraint:** chỉ thay đổi khi người dùng xác nhận, kèm hệ quả.
- **Soft preference:** dùng để xếp hạng và cân nhắc đánh đổi.

User Profile là thông tin gợi ý ban đầu; yêu cầu của chuyến đi hiện tại có ưu tiên cao hơn. Đã đến một nơi không đồng nghĩa đã thích, và chưa biết không đồng nghĩa không thích. Khả năng học sở thích dài hạn cần được đánh giá riêng, không suy ra từ một phiên gợi ý.

### 8.4. Kiểm soát chất lượng dữ liệu

Pipeline giữ tham chiếu bằng chứng, kiểm schema, chạy gate và định tuyến trường hợp rủi ro qua Judge hoặc người duyệt. Đánh giá cần tách độ chính xác của dữ liệu tự xuất bản, dữ liệu qua Judge, độ phủ từng khía cạnh và độ tin của chính Judge trên mẫu người kiểm tra.

Nhãn Judge hỗ trợ vận hành, chưa thay thế hoàn toàn nhãn kiểm chứng độc lập của con người. Chưa đưa tỷ lệ chính xác hoặc độ phủ toàn corpus khi chưa có báo cáo tương ứng.

Chi tiết kỹ thuật: [Kiến trúc](../ARCHITECTURE.md), [Place Intelligence](../CORPUS.md), [Trip Understanding](../TRIP_UNDERSTANDING.md), [Place Decision](../PLACE_DECISION.md), [Planning](../PLANNING.md).

## 9. Tính khả thi và thực nghiệm — 15 điểm

### 9.1. Sản phẩm thử nghiệm và bằng chứng triển khai

Nhóm đã xây dựng ứng dụng Web cùng các module xử lý cho luồng hiểu chuyến đi, tuyển chọn địa điểm, lập lịch và chỉnh sửa. Dữ liệu địa điểm được xử lý trước; các giai đoạn online dùng chung hành trình và trao đổi qua API công khai.

Bản thử nghiệm của nhóm: [TripGuardian](https://tripguardianfinal.visioncare-host.uk/).

Repo có các ca kiểm thử cho hành vi trọng yếu:

| Hành vi được kiểm tra | Bằng chứng trong repo |
|---|---|
| Lời giải thích giữ đúng bằng chứng và phiên bản dữ liệu; không mượn trích dẫn ngữ nghĩa cho thuộc tính chưa xác minh | [Kiểm thử bằng chứng Decision](../../tests/decision/test_evidence.py) |
| Ngân sách giữ số tiền, phạm vi và nguồn; không tự quy đổi khi thiếu dữ kiện | [Kiểm thử ngân sách bàn giao](../../tests/trip/test_budget_handoff.py) |
| Đổi địa điểm ăn uống vẫn giữ hoạt động và kiểm lại yêu cầu ăn kiêng | [Kiểm thử phạm vi yêu cầu Planning](../../tests/planning/test_planning_requirement_scope.py) |
| Xem trước không sửa trạng thái thật; chỉnh sửa được kiểm tra lại; lịch lỗi bị chặn khi chốt | [Kiểm thử sửa lịch quá tải](../../tests/planning/test_planning_overload_edits.py) |

Đây là bằng chứng có ca kiểm thử, không phải công bố toàn bộ test đang pass trên bản triển khai hay chứng minh hiệu quả với người dùng thật.

### 9.2. Số đo kỹ thuật đã được ghi nhận

[Báo cáo hiệu năng Planning](../PLANNING_PERFORMANCE.md) ghi nhận benchmark trước và sau tối ưu trên cùng fixture giả lập, lấy median ba lượt chạy:

| Trường hợp | Trước tối ưu | Sau tối ưu | Tốc độ tương đối |
|---|---:|---:|---:|
| Tạo kế hoạch 7 ngày, 28 điểm | 0,0768 giây | 0,0612 giây | 1,25× |
| Tạo kế hoạch 7 ngày, 49 điểm | 1,6833 giây | 0,9336 giây | 1,80× |

Fingerprint kết quả trước và sau trùng nhau trong các trường hợp này. Số đo dùng ma trận di chuyển giả lập, không gồm mạng, OSRM thật, dịch vụ live hoặc Agent. **Đây là hiệu năng tính toán Planning trong điều kiện đo đã nêu, không phải độ trễ toàn ứng dụng và không phải so sánh với đối thủ.**

### 9.3. Đánh giá chất lượng ngoài latency

Repo có cấu hình 30 tình huống chuyến đi dùng cho đánh giá Decision và Planning. Việc có bộ đánh giá không đồng nghĩa đã có kết quả đầy đủ; không điền tỷ lệ thành công khi chưa có output được kiểm chứng.

| Khía cạnh | Chỉ số cần báo cáo | Trạng thái bằng chứng |
|---|---|---|
| Hiểu nhu cầu | Đúng yêu cầu, phạm vi, ngân sách và thay đổi qua hội thoại | Có ca kiểm thử; chưa tổng hợp chỉ số tại đây |
| Tính khả thi | Tỷ lệ lịch đạt toàn bộ kiểm tra; loại và số vi phạm | Có validator và công cụ đánh giá; chưa tổng hợp tỷ lệ tại đây |
| Hoàn thành hữu ích | Tỷ lệ yêu cầu khả thi nhận được lịch đủ dùng | Cần báo cáo cùng tỷ lệ từ chối và thiếu dữ liệu |
| Có căn cứ | Tỷ lệ nhận định có bằng chứng và tỷ lệ sai khi kiểm tra độc lập | Có cơ chế lưu và kiểm bằng chứng; chưa có kết quả lấy mẫu tại đây |
| Sửa lịch | Giữ yêu cầu sau thay đổi; kiểm lại và chặn chốt khi lỗi | Có ca kiểm thử; chưa tổng hợp thành tỷ lệ |
| Hiệu năng | Thời gian tính toán, độ trễ từng lượt và toàn luồng | Có số đo Planning ở mục 9.2; chưa có số toàn luồng tại đây |

Các mục tiêu như “0 vi phạm hard constraint” phải được ghi là mục tiêu cho tới khi có phép đo. Một lịch rỗng, từ chối mọi yêu cầu hoặc âm thầm bỏ nơi bắt buộc không được tính là hoàn thành thành công.

### 9.4. Benchmark và đối chứng với sản phẩm khác

Lĩnh vực đã có benchmark như [TravelPlanner](https://proceedings.mlr.press/v235/xie24j.html), [ChinaTravel](https://github.com/LAMDA-NeSy/ChinaTravel) và [TripTailor](https://aclanthology.org/2025.findings-acl.503/). Chưa có kết quả TripGuardian trên các bộ này trong tài liệu này.

Chưa có điểm benchmark chung, công khai và tái lập giữa TripGuardian với Layla, Mindtrip hoặc Tripadvisor trong phạm vi đối chiếu hiện tại. Điều đó không giới hạn đánh giá ở feedback và latency: có thể tự tổ chức thử nghiệm cùng yêu cầu, cùng điều kiện và tiêu chí kiểm chứng độc lập.

Khi có đối chứng, cần lưu đầu vào, đầu ra, ngày thử, phiên bản / gói sản phẩm và số lượt được phép tương tác; phân biệt AI tự động với dịch vụ có người tư vấn. Địa điểm ngoài corpus TripGuardian vẫn phải được kiểm chứng độc lập, không tự chấm sai. Hiện chưa công bố kết quả thắng / thua giữa các sản phẩm.

### 9.5. Giới hạn hiện tại

- Phạm vi kiểm chứng ban đầu là Đà Lạt; chưa suy rộng chất lượng cho mọi điểm đến.
- Thời gian di chuyển chưa có traffic thời gian thực; profile xe máy dùng hệ số trên profile ô tô. Khi phải ước lượng thô, kết quả có cảnh báo.
- Giá, giờ và trạng thái vận hành phụ thuộc độ mới và độ phủ nguồn; thiếu dữ liệu không có nghĩa đã xác nhận đáp ứng.
- Dự án học tập, phi thương mại; dữ liệu thu thập và cách truy cập nguồn hiện tại chưa chứng minh sẵn sàng thương mại hóa.
- Kết quả pilot, khảo sát, mức hài lòng và cải thiện công sức người dùng chưa được bổ sung.

## 10. Trình bày và trải nghiệm người dùng — 10 điểm

### 10.1. Trình diễn một hành trình hoàn chỉnh

Phần demo dùng tình huống Đà Lạt ở phần 1 và các địa điểm thật đã có dữ liệu. Chuẩn bị trước trường hợp quá tải hoặc xung đột có thể tái hiện, không dựng nhận định về một địa điểm thiếu bằng chứng.

1. **Kể về chuyến đi:** nhập thời gian, người đồng hành, phương tiện, sở thích và yêu cầu bắt buộc; xem bản hệ thống đã hiểu.
2. **Xem và tuyển chọn:** mở một đề xuất, xem cơ sở phù hợp và thông tin còn chưa rõ; so sánh rồi chọn nơi.
3. **Xem lịch và xung đột:** hiển thị giờ ghé, thời gian di chuyển và vấn đề khi danh sách vượt khả năng của ngày.
4. **Cân nhắc phương án:** xem mục tiêu, những nơi giữ / bỏ và hệ quả của lựa chọn đang được đề xuất.
5. **Thử một thay đổi:** xem trước thao tác đổi / chuyển / bỏ nơi rồi áp dụng; cho thấy kết quả được kiểm tra lại.
6. **Xác nhận:** lịch đạt kiểm tra được chốt; nếu cố giữ lịch còn vi phạm, hệ thống nêu lý do chặn và hướng xử lý.

Qua demo, cần thể hiện người dùng biết hệ thống hiểu gì, gợi ý dựa trên gì, cần kiểm tra thêm điều gì và mình có thể thay đổi gì. Độ dễ sử dụng thực tế sẽ được đối chiếu với dữ liệu người dùng.

### 10.2. Câu hỏi và thông tin khảo sát

<!-- Để trống: bổ sung Google Form và nguyên văn câu hỏi do nhóm cung cấp. -->

### 10.3. Kết quả phản hồi người dùng

<!-- Để trống: bổ sung mẫu khảo sát, bối cảnh dùng thử, kết quả và phản hồi sau khi thu thập. -->

### 10.4. Đối chiếu phản hồi với mục tiêu sản phẩm

<!-- Để trống: chỉ rút ra kết luận mà câu hỏi khảo sát, tác vụ và dữ liệu thực tế hỗ trợ. -->
