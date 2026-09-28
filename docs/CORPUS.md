# Corpus Place Intelligence

Kho tri thức xây offline mà planner đọc. Trang này là bản tham chiếu ngắn; thiết kế đầy đủ (vai trò, gate, định tuyến, data model, các phase) nằm ở `docs/specs/CORPUS_SPEC.md`.

## 1. Corpus là gì

```text
SOURCE ──► OBSERVATION ──► FACT / SIGNAL / ESTIMATE ──► PLACE INTELLIGENCE ──► SERVING INDEX
(video,     (một nhận định   (rule tổng hợp từ           (theo địa điểm,         (thứ planner
 comment,    + span + bối     nhiều observation)          theo khía cạnh)         đọc)
 trang,      cảnh)
 provider)
```

- Agent xây từ đầu đến cuối. Gate tất định kiểm soát mọi lần ghi. Người chỉ duyệt một hàng đợi nhỏ, xếp theo rủi ro, ở cuối.
- Mọi giá trị được phục vụ đều truy về một span nguồn. Không có span thì không có observation. Không có observation thì không có giá trị.
- Corpus không lưu dữ liệu người dùng và không coi input hay hành vi của người dùng là bằng chứng về địa điểm.

## 2. Nguồn và mỗi nguồn được chứng minh điều gì

| Nguồn | Dùng cho | Không bao giờ dùng cho |
|---|---|---|
| Video TikTok (segment: transcript, chữ trên màn hình, mô tả hình ảnh) | Khám phá; trải nghiệm, môi trường, mức vận động | Fact vận hành nếu chỉ có một mình nó (giá đọc được từ video chỉ là observation) |
| Comment TikTok | Tín hiệu trải nghiệm lặp lại (độ đông, yên tĩnh, đường đi) | Fact; hiển thị một comment đơn lẻ như sự thật |
| Google Places | Định danh, vị trí, loại, giờ mở cửa, trạng thái, website | Nhận định trải nghiệm. Không lưu rating và review |
| Website / trang chính thức | Giờ, giá, vé, đặt chỗ, quy định, đóng cửa tạm | — |

Video chỉ được tải tạm để trích xuất rồi xóa. Corpus giữ transcript, timestamp segment, keyframe nhỏ, và URL embed TikTok; bằng chứng phát qua embed tại timestamp của segment.

Nội dung Google Places nằm trong một **provider store** riêng, không trộn vào bảng của corpus, và chỉ hiển thị kèm bản đồ Google.

## 3. Luồng xây dựng

```text
DISCOVER     query TikTok theo nhóm  +  lưới category × khu vực trên Google Places
   ↓
EXTRACT      video tạm → segment → ASR → chữ trên keyframe + mô tả hình ảnh → xóa video
             → mention địa điểm có span, loại POI / ZONE, quan hệ không gian được nói rõ
   ↓
RESOLVE      chuẩn hóa tên → match với Google trong vùng
             match rõ → POI · khu vực / con đường / cảnh quan → ZONE
             chưa rõ → Judge chọn một phương án có sẵn hoặc bỏ phiếu trắng · không có → UNRESOLVED
   ↓
OBSERVE      segment, comment, trang official → observation (feature | fact_key,
             value, stance, context, span)
   ↓
AGGREGATE    chỉ bằng rule → Fact · Signal · Estimate, kèm các thành phần confidence
   ↓
CHECK        gate → định tuyến theo rủi ro → Judge audit entity rủi ro cao
   ↓
PUBLISH      rủi ro thấp + Judge pass → serving index · phần còn lại → hàng đợi review
   ↓
REFRESH      ledger chỉ chạy lại input đã đổi; nguồn quá hạn được tải lại
```

Một địa điểm là **POI** (một điểm xác định được) hoặc **ZONE** (khu vực, con đường, hay cảnh quan trải nghiệm, ví dụ khu săn mây Cầu Đất). Zone nối với POI qua quan hệ, nên "khu này hợp săn mây" không bao giờ thành "nông trại này là chỗ săn mây". Xuất hiện trong cùng một video không bao giờ là bằng chứng hai nơi gần nhau.

## 4. Các loại output

| Loại | Ví dụ | Rule | Hiển thị |
|---|---|---|---|
| Fact | giờ, giá, đặt chỗ, quy định vào cửa | Official > provider; bất đồng → `uncertain` + giữ xung đột | Một giá trị, hoặc "chưa xác nhận" kèm cả hai giá trị |
| Signal | độ đông theo thời điểm, yên tĩnh / sôi động, view, đường dốc | Phân phối trên các observation liên quan | Một xu hướng kèm mẫu ("62% trong 123 comment về độ đông, 30 creator") |
| Estimate | thời gian tham quan min / typical / long | Rule trên observation | Luôn là một khoảng |

**Bối cảnh quan trọng.** "Đông vào sáng cuối tuần" được lưu là `crowd × weekend × morning`, không phải "đông".

**Confidence** giữ bốn thành phần, không gộp thành một số ẩn: số nguồn độc lập, mức đồng thuận, độ mới, loại nguồn.

**Coverage** theo khía cạnh (`identity`, `operation`, `experience`, `environment`, `effort`, `suitability`): `COMPLETE | PARTIAL | NONE`. Địa điểm không có bằng chứng trải nghiệm (chỉ tìm thấy qua lưới Maps) được dùng làm chỗ ăn, anchor, hoặc phương án dự phòng, không được gợi ý như một trải nghiệm.

## 5. Bản ghi địa điểm

```text
Place
├── Identity      tên, alias, loại (POI | ZONE), category, vị trí / hình học
├── Operation     giờ, giá, đặt chỗ, thời gian tham quan (khoảng)
├── Experience    feature (thiên nhiên, view, cà phê, chụp ảnh, hoạt động, …)
├── Environment   trong nhà / ngoài trời, độ đông theo bối cảnh, yên tĩnh / sôi động, nhạy thời tiết
├── Effort        đi bộ, dốc, khó tiếp cận   (thuộc tính của địa điểm, không phải của chuyến đi)
├── Suitability   cặp đôi, gia đình, bạn bè, đi một mình, người lớn tuổi
└── Provenance    tham chiếu bằng chứng, thành phần confidence, độ mới, xung đột, coverage, trạng thái
```

Feature lấy từ một **feature ontology** có version, dùng chung với User Profile. Hai bên dùng chung id, không dùng chung bản ghi: địa điểm lưu "có forest_view, kèm confidence"; profile lưu "thích forest_view, kèm affinity".

## 6. Trạng thái (một bộ chung cho corpus, Admin Web, User Web)

| Trạng thái | Ý nghĩa | Hiển thị cho người dùng? |
|---|---|---|
| `VERIFIED` | Qua gate và, nếu rủi ro cao, qua Judge hoặc người | Có |
| `UNCERTAIN` | Có xung đột hoặc bằng chứng yếu | Có, hiển thị là chưa chắc chắn |
| `OUTDATED` | Quá hạn độ mới | Có, kèm cảnh báo, cho đến khi được làm mới |
| `NEEDS_REVIEW` | Judge đánh dấu, hoặc đang chờ người kiểm tra bắt buộc | Không |
| `DISABLED` | Đã đóng cửa, trùng, không hợp lệ, hoặc bị người từ chối | Không |

Trạng thái giữ theo từng khía cạnh, nên một địa điểm có thể có định danh đã xác minh nhưng giờ mở cửa chưa chắc chắn.

## 7. Người duyệt

Bước duy nhất có người, sau mỗi lần build. Hàng đợi gồm: mục `NEEDS_REVIEW`, giá trị về an toàn / tiếp cận / đối tượng phù hợp (luôn cần người kiểm tra), ứng viên chưa resolve, feature mới được đề xuất, và một mẫu ngẫu nhiên ẩn ~5% các giá trị đã tự publish. Mẫu này là cách đo chất lượng.

Thao tác của người duyệt: **Accept · Disable · Report error**. Không sửa giá trị bằng tay; lỗi được báo sẽ kích hoạt build lại từ bằng chứng. Mọi quyết định được lưu thành nhãn để hiệu chỉnh và làm regression test.

## 8. Planner dùng corpus thế nào

```text
Sở thích người dùng → truy xuất địa điểm (serving index) → địa điểm được gợi ý
   → Vì sao phù hợp: feature → segment video (embed tại timestamp) + xu hướng comment (kèm cỡ mẫu)
   → Giờ / giá / vị trí: bằng chứng official hoặc Google, không trộn với bằng chứng trải nghiệm TikTok
```

Planner chỉ đọc serving record; không bao giờ duyệt đồ thị bằng chứng. Thời tiết, giao thông, thời gian di chuyển thực tế được lấy theo từng request và không bao giờ thành dữ liệu corpus.

Khi người dùng nhập một địa điểm chưa có trong registry, cùng bộ matcher chạy theo yêu cầu. Match chắc chắn thì trả về và xếp hàng làm giàu dữ liệu; nếu không, người dùng chọn từ các phương án. Không đoán gì cả.
