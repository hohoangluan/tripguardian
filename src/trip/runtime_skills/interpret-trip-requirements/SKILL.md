---
name: interpret-trip-requirements
description: Dùng khi Trip Understanding diễn giải yêu cầu, sở thích hoặc hoạt động của người đi trong chuyến hiện tại.
---

# Diễn giải yêu cầu chuyến đi

Với mỗi ý định, xác định meaning (điều thực sự cần), strength (mandatory hay preference), subject (traveler, group, member, unspecified), scope (eating, drinking, sightseeing, accommodation, travel, all), evidence (câu nguyên văn), ambiguity (chỉ hỏi nếu các cách hiểu làm đổi kết quả).

Ghi qua `record_fact`: hard cho bắt buộc, soft cho sở thích; thêm object `requirement` gồm meaning, scope, subject, subject_count nếu có số người rõ. Quote nằm ở argument `quote`. Không suy sở thích thành bắt buộc hoặc đoán subject. Khi chưa rõ, hỏi một câu phân biệt các cách hiểu; không ghi hard từ ambiguity chưa giải quyết.

| Lời người dùng | Biểu diễn |
|---|---|
| “Trong nhóm có một người ăn chay” | hard `vegetarian_options=yes`; scope eating; subject member; subject_count 1 |
| “Thích đồ chay” | soft `vegetarian_options=yes:love`; scope eating |
| “Ăn thuần chay” | hard `vegan_options=yes`; scope eating; không thay bằng vegetarian |
| “Không uống rượu” | hard `activity!=alcohol_consumption`; scope all; không cấm quán có bán rượu |
| “Không muốn đi bar” | hard `venue_category!=bar`; scope all |
| “Thích thử rượu vang” | soft `wine_tasting_available=present:love`; scope drinking |
| “Bắt buộc có thử rượu vang” | hard `wine_tasting_available=present`; scope drinking |

Yêu cầu món chay áp dụng cho địa điểm được chọn để ăn, kể cả quán menu hỗn hợp. Không yêu cầu quán chuyên chay, công viên có món chay hay café chỉ uống cà phê có bữa chay. Không dùng thiếu vegetarian evidence để kết luận nhà hàng không liên quan: nhà hàng ăn vẫn chịu constraint; thiếu evidence vẫn unknown, không được hứa phù hợp.

Café và chợ có nhiều hoạt động. Khi người dùng nói rõ hoạt động tại địa điểm đã tra cứu, dùng field `activity`, value JSON với `place_id` thật và `activity`: eating, coffee, drinking, tasting, wine_tasting, alcohol_consumption, sightseeing, accommodation, travel. Quote phải gồm tên và lời chỉ hoạt động. “Ăn trưa ở café X” → eating; “uống cà phê ở X” → coffee; “tham quan chợ Y” → sightseeing. Chỉ ghi activity nếu người dùng thực sự chọn hoạt động tại nơi đó; thích wine tasting nói chung chưa xác nhận sẽ uống tại mọi venue.

`tasting_available` có thể là trà, cà phê, thức ăn hoặc rượu; không thay cho `wine_tasting_available`. `alcohol_required` nói việc tham gia phải uống, không nói quán có phục vụ rượu. Vegan cần evidence riêng. Scope eating/drinking không được đổi thành all; physical/access vẫn all. Không nới constraint hay tự đổi unknown_policy.

## Mục đích và giờ ghé

“Muốn đi chơi chụp ảnh” → purpose photo. Activity còn có photography, walking, nightlife: chỉ gán cho nơi đã được người dùng chọn và quote có tên thật. Không suy chụp ảnh luôn phải sáng, mọi chợ luôn là chợ đêm, hay mọi nhà hàng là bar.

Ưu tiên giờ mềm được ghi bằng field `time_preference`, value JSON gồm period (morning, midday, afternoon, evening, daytime, sunrise, sunset), place_id tùy chọn (ID danh mục thật), activity tùy chọn, weight 1 mặc định / 2 khi ưu tiên / 3 khi ưu tiên cao được nói rõ. Quote nguyên văn bắt buộc; ưu tiên theo địa điểm cần quote chứa tên địa điểm. Ví dụ “ưu tiên đi dạo buổi chiều” → value {"activity":"walking","period":"afternoon"}; “thích chụp ảnh tối tại X” → activity photography cho X và time_preference {"place_id":"<ID thật>","period":"evening"}. Không ghi các khung 8–11h hay nghỉ trưa thành fact người dùng nếu họ chưa nói; đó là heuristic của Planning.

time_preference luôn là sở thích mềm. Nếu người dùng bắt buộc đến một nơi vào giờ cụ thể hoặc nêu nhiều ưu tiên xung đột, không đổi thành ưu tiên mềm: hỏi rõ giới hạn, dùng giờ bắt đầu/kết thúc toàn ngày nếu đúng nghĩa, hoặc ghi unmapped nếu contract chưa diễn đạt được. Không đoán giờ mở cửa, thời lượng, độ đông, bình minh/hoàng hôn; các module sau đọc dữ liệu và kiểm chứng.
