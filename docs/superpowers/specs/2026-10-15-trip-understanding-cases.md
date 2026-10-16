# Trip Understanding: ma trận case từ đóng vai người dùng

Spec làm việc (tạm thời, `RULE.md` §0.1), đi cùng `2026-10-13-trip-understanding-redesign-design.md`. Ghi lại các case đã chạy thật để thiết kế "hỏi như Claude" có bằng chứng; khi xong, các case thành bộ đo ở `src/bench` / `config/eval_trips.yaml` rồi xóa file này.

## 1. Cách làm

- Engine giống harness (`trip.api.tools.create_engine`), Gemma LAN (vai Agent) + Clef thật, corpus active (3.208 nơi). Server riêng, session lưu ngoài repo; không đụng prod.
- 77 persona, ~110 lượt, ngày 15/10/2026: 57 persona phủ 8 trục ở §2, 20 persona về nhịp ngày (§7); mỗi persona 1–3 lượt như user thật (kể cả cáu, vội, đổi ý).
- Đọc kết quả bằng `state` + `tools` của từng lượt, không bằng lời agent.

## 2. Trục phủ

| Trục | Giá trị đã chạy |
|---|---|
| Ai đi | một mình · người yêu / vợ chồng / trăng mật · bạn bè 2–8 · sinh viên · đồng nghiệp 18 người · gia đình có bé 2 / 4–6 / 8–11 tuổi · 3 thế hệ · ông bà 70–80 · mẹ xe lăn · vợ bầu · em họ tuổi teen · thú cưng · nhóm hỗn hợp (2 cặp + bé + ông) · khách Hàn / Tây |
| Mục đích | chill · săn mây · chụp ảnh / film · ăn (food tour, đặc sản) · mua quà · về đêm · trekking / cắm trại · tâm linh · nghỉ dưỡng sang · workcation 2 tuần · chữa lành · sinh nhật bất ngờ · team building · trẻ em vận động |
| Ràng buộc | ăn chay / thuần chay / halal / dị ứng đậu phộng · đau gối · xe lăn · bầu · say xe · sợ độ cao · không leo dốc · xe đẩy · ngân sách 800k → 30 triệu → "không quan tâm giá" |
| Thời gian | ngày cụ thể · khoảng ngày · tháng · đầu/giữa/cuối tháng · tuần sau · cuối tuần này / sau · chủ nhật này · Tết dương lịch · 30/4 · Giáng sinh · mùa mưa · mùa hoa · đi trong ngày |
| Hậu cần | tự lái / thuê xe / taxi / Grab / xe khách / máy bay · tới 4h sáng · đã đặt khách sạn · về chiều chủ nhật · xuất phát Nha Trang |
| Kiểu gõ | dài kể chuyện · cụt ("dl 2n1đ", "ny", "xm") · không dấu · teencode, sai chính tả · giọng nói lan man · tiếng Anh |
| Thái độ | vội ("gợi ý luôn") · lưỡng lự ("sao cũng được") · đổi ý 2 lần · mâu thuẫn ("nhiều chỗ" + "thong thả") · mơ hồ ("đẹp như phim") |
| Ngoài kể chuyến | hỏi ngược (giờ mở cửa, khoảng cách, giá phòng, mùa hoa, thời tiết, độ đông lễ) · chào hỏi · prompt injection |

## 3. Lỗi mất dữ liệu (guard, trích xuất)

| Lỗi | Persona | Nguyên nhân / chỗ |
|---|---|---|
| Từ chối người đi cùng có thật: "bồ", "ny", "ngừi iu", "vợ", "wife", "với mẹ", "cả nhà", "bé 6 tuổi", "2 bé 8 và 11", "tụi tui 4 đứa", "5 đứa sinh viên", "2 đứa bạn thân", "2 cặp đôi" | 17/57 | `guard.names_group` khớp từ điển đóng `config/companions.yaml` |
| Fact soft/hard hợp lệ bị bỏ vì metadata `requirement` sai một trường (`noise=quiet`, `steep_or_stairs`, `animals`, `cloud_hunting`, `vegetarian_options`) | 6 | `guard.record_fact` validate `RequirementIntent` rồi từ chối cả fact |
| Fact nói ở lượt trước không ghi lại được ("3 ngày", "ăn chay", "bé 2 tuổi") | 3 | quote chỉ được lấy từ tin nhắn mới nhất |
| Phương tiện: Grab → `car`; "đi bộ" ghi `walking`; taxi, xe khách bị từ chối, hỏi lại | 7 | prompt liệt kê `mobility: motorbike \| car` (thiếu `walk`), không có đường cho "đi bằng gì tới" |
| Ngày tương đối không ra ngày: Tết dương lịch, cuối tuần này/sau, tuần sau, chủ nhật này, thứ 6 tuần sau | 6 | agent không gọi `resolve_relative_date` hoặc hỏi lại "thứ mấy" |
| Hiểu sai nghĩa: thú cưng → `animals=present` (nơi có thú để xem); "giống Túi Mơ To" → anchor bắt buộc; khách sạn đã đặt → anchor; danh sách món → anchor; "dorm" → `base` là một `place_id` bất kỳ; "mưa thì đi đâu" → hard `weather_exposed` | 6 | prompt thiếu phân biệt; `base` resolve theo tên mờ |
| Số đêm sai ("ở 3 ngày, cắm trại 1 đêm" → `nights = 1`) | 1 | — |
| Bỏ bố mẹ sau khi thêm, signal `elderly` vẫn còn và khóa an toàn | 1 | signal suy luận không gỡ theo companions |
| Đổi cà phê → trà: không ghi gì nhưng lời đáp nói "sẽ ưu tiên trà" | 1 | lời đáp không đối chiếu tool |
| Giờ tới (máy bay 10h, xe khách 4h) bị ghi vào `checkin_at` dạng JSON rồi bị từ chối | 2 | không có field giờ tới; `checkin_at` là giờ khách sạn |
| Mâu thuẫn ghi cả hai (`explore` + `slow`), không hỏi | 1 | — |
| Sở thích theo từng người ("người thích cà phê, người thích leo núi") gộp chung | 1 | soft không có subject |

## 4. Lỗi cách hỏi

| Lỗi | Persona |
|---|---|
| Câu rập khuôn "lãng mạn riêng tư hay bạn bè thân thiết?" (kể cả khi user nói "vợ", "mẹ", "bé 6 tuổi") | 14 |
| Hỏi lại điều vừa nói (xe máy, tháng đi hỏi 2 lần, câu lãng mạn hỏi 2 lần) | 5 |
| User vội ("gợi ý luôn đi") bị giảng giải dài vì sao cần hỏi | 1 |
| User lưỡng lự nhận thêm câu hỏi mở; 3 lượt không ghi được gì | 2 |
| Lộ tên field: "Mình đã ghi lại (budget_scope, people…)", "(signal)", "(ý này)" | 6 |
| Nói sai: "đã ghi nhận link TikTok" khi anchor `missing` | 1 |
| User nói tiếng Anh, trả lời tiếng Việt | 2 |
| Thẻ `care` hỏi lại đau gối đã xử lý | 1 |
| Không persona nào thấy ảnh; "vintage", "giống Hàn Quốc có tuyết", "đẹp như phim" thành `unmapped` + câu hỏi chữ | 4 |
| Câu hỏi của user bị trả lời bằng câu cố định "chưa có số liệu…" | 8 |
| Lượt đầu ~8 s (mục tiêu ≤ 3 s) | tất cả |

## 5. Trường lạ: corpus có gì để khắc phục

| Mong muốn | Có ở corpus | Bậc khắc phục |
|---|---|---|
| Món: bánh căn, lẩu gà lá é, sữa đậu nành, nem nướng, BBQ, trà | `corpus.serving.dishes.search` 20 nơi mỗi món | món ăn |
| karaoke (11), bar (24), chợ đêm, khu cắm trại (18), spa (~100), khách sạn 5 sao (10), cửa hàng đặc sản (36), thuê xe máy (43), chùa / nhà thờ (61) | category của serving record | loại nơi |
| vintage, giống Hàn Quốc, đẹp như phim, ánh sáng film | index ảnh (§6) | look có ảnh |
| xe đẩy, đoàn đông, cho mang chó | `stroller_access`, `groups`, `pets` | feature (agent chưa dùng) |
| mai anh đào, dã quỳ, tháng nào đẹp | `timing.best_months` có ở 16 nơi săn mây; còn lại web | feature + web |
| giá phòng, 800k đủ không | giá chỗ ở trong corpus | trả lời câu hỏi |
| giờ chợ đêm, khoảng cách tới đồi chè | giờ mở cửa, tọa độ | trả lời câu hỏi |
| halal, dị ứng đậu phộng, bồn tắm, ổ cắm, chụp ảnh cưới, nơi hợp buổi nào | **không có** | báo user + `data/trip/gaps.jsonl` |
| tránh cáp treo / leo đỉnh, "không đi xa trung tâm" | không có activity / khoảng cách tới tâm | báo user + gap; khoảng cách có thể từ tọa độ |

## 6. Khoan sâu bằng ảnh: index có làm được không

`Index.search_photos` trong tập nơi của sở thích cha, ngưỡng `min_text_photo` 0,08; chọn 3 biến thể theo `số nơi × điểm ảnh tốt nhất`.

| Sở thích | Top 3 biến thể (số nơi · nơi đại diện) | Ghi chú |
|---|---|---|
| Săn mây (173) | sương sáng sớm 56 · Mộc Trà Farm; trời trong 62 · View Triệu Mây; hoàng hôn 47 · Kong Coffee | bình minh chỉ 8 nơi → tự rớt; `timing.by_time_of_day` rỗng 100% |
| Ngắm đồi | cỏ hồng 64; rừng thông 65; đồi chè 49 · Đồi Trà Cầu Đất | top-1 đúng loại |
| Cà phê (343) | view thung lũng 73; vintage 65 · Mọt Cafe & Books; nhà gỗ rừng thông 68 | |
| Chụp ảnh (728) | tiểu cảnh 74; đồi cỏ hồng 62; hồ sương 62 | |
| Thiên nhiên (576/957 có ảnh) | rừng thông 65; hồ 65; đỉnh núi 63 | |
| Cắm trại (117) | lều ven hồ 60; đồi thông 53; glamping 46 · Anstay | |
| Ăn uống | lẩu ấm cúng 73; nhà hàng sang 64; nướng ngoài trời 70 | |
| Về đêm | chợ đêm 65 · Chợ Đêm Đà Lạt; acoustic 59; bar cocktail 45 · NOBAR | |
| Tâm linh (69) | nhà thờ cổ 32; chùa thiền 35 | "chùa ve chai" top-1 là nhà thờ → cần ngưỡng điểm ảnh tối thiểu |
| Chỗ ở (1.475) | **3 nơi có ảnh** | không khoan sâu được → gap |

## 7. Nhịp ngày và khung giờ (đợt 2, 20 persona)

Trip State không có chỗ ghi các nhu cầu này; `time_preference` được ghi nhưng không gắn hoạt động nên Planning không dùng được.

| User nói | Trip hiện ghi | Planning cần |
|---|---|---|
| dậy muộn 9–10h; ông bà dậy 5h, ngủ 20h | `time_preference` trống nghĩa | giờ bắt đầu / kết thúc ngày |
| nghỉ trưa ở khách sạn; bé ngủ 12:00–14:30 và 19:30 | `unmapped` | khung bận lặp lại, tại chỗ ở |
| ngày 2 đi sớm về muộn, ngày 1 nhẹ; ngày 2 nghỉ ở resort | không ghi | nhịp theo từng ngày |
| cà phê 2 tiếng mỗi quán; check-in 20–30 phút; bé chán sau 1 tiếng | chỉ `pace` | thời lượng ghé theo loại nơi |
| mẹ đi 1 tiếng phải nghỉ 15–20 phút | không | nhịp nghỉ riêng |
| đặt bàn 19h thứ 7; tour 7h chủ nhật 4 tiếng | anchor `missing` | sự kiện giờ cố định, kể cả ngoài corpus |
| họp 8–17h thứ 2–6 | không | khung bận theo thứ |
| sáng thiên nhiên, chiều nghỉ, tối ăn + cà phê; ngoài trời buổi sáng vì chiều mưa; golden hour 6–7h, 16:30–17:30; spa mỗi tối; chợ sáng sớm | `time_preference` không có hoạt động | buổi ↔ loại nơi |
| ngày thường đi chỗ nổi tiếng, cuối tuần chỗ vắng | không | độ đông theo thứ / giờ |
| bay 16h ngày cuối | `checkout_at = 16:00` (sai: lịch chạy tới giờ bay) | giờ bay − đệm sân bay − thời gian ra sân bay |
| hạ cánh 8h; xe khách tới 5h, về 22h | `checkin_at` = giờ tới | giờ sẵn sàng = giờ tới + đệm + đường vào |
| lái tối đa 2 tiếng mỗi ngày | `max_leg_min = 120` (sai: mỗi chặng) | trần lái xe theo ngày |
| xen chỗ chơi cho bé với chỗ ngồi cho bố mẹ | không | mẫu xen kẽ |

Dữ liệu giờ trong corpus (3.208 nơi):

| Dữ liệu | Độ phủ |
|---|---|
| `operation.visit_minutes` | 3.169 là `category_default`, 39 từ review |
| `operation.hours` | quán ăn / cà phê 89%, attraction 76%, garden_farm 77%, religious 46%, nature 25%, camping 5% |
| `operation.crowd_by_time` (weekday / weekend × buổi) | quán 78%, nature 25%, garden_farm 32% |
| `timing.best_time` / `avoid_time` | 0 |
| `timing.best_months` | 29 |

## 8. Điều user thật cần (rút từ §3–7)

1. Nói một lần là đủ: mọi cách gọi người đi cùng, phương tiện, ngày tương đối đều được hiểu; không mất ý vì lỗi kỹ thuật.
2. Được hỏi đúng chữ mình dùng ("săn mây kiểu nào?"), bằng ảnh thật, một chạm, không chờ.
3. Vội thì được đi tiếp ngay với mặc định có ghi rõ; lưỡng lự thì được **cho xem** để chọn, không bị hỏi mở.
4. Hỏi gì được trả lời thật (corpus, web có nguồn), không bị gạt sang bước sau.
5. Điều hệ thống không có dữ liệu thì được nói thẳng, và ý đó không bị mất.
6. Nhóm hỗn hợp, đổi ý, mâu thuẫn được làm rõ bằng một câu chọn, không đoán.
7. Lịch theo đúng nhịp sống của nhóm: giờ dậy, giờ ngủ, nghỉ trưa, việc cố định, ngày nhẹ, ngày nghỉ.
