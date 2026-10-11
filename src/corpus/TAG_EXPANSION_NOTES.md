# Ghi chú: chuẩn hóa và mở rộng tag (feature ontology)

> **Tài liệu làm việc**, không phải tài liệu chính thức (`RULE.md` §0.1). Ghi lại các chỗ ontology v10 (`config/ontology.yaml`) chặn việc hiểu từ mơ hồ của người dùng (Laya v3, `system_one_model/dataset/`). Khi chốt thì gộp vào `docs/CORPUS.md` §5 và xóa file này.
>
> Đổi id hoặc giá trị → bump `version` → trích lại observation (`docs/CORPUS.md` §7) → lexicon và `catalog_version` mới của Laya → sinh lại dữ liệu. Vì vậy chốt ontology **trước** khi sinh dữ liệu quy mô lớn.

## 1. Vì sao cần

Laya hiểu từ chủ quan ("chill", "có vibe", "yên tĩnh nhưng đừng vắng quá") bằng cách ánh xạ **term → feature_id** (lexicon trong `catalog.json`). Runtime chỉ ghi được sở thích mềm `feature=value` với `value` cố định theo `FEATURE_VALUE` (`src/trip/turn.py`). Nếu ontology không có tag để ánh xạ, hoặc chỉ có một chiều giá trị, thì người dùng nói gì Laya cũng không ghi vào Trip State được.

## 2. Chuẩn hóa

| Vấn đề | Ví dụ | Đề xuất |
|---|---|---|
| Thang giá trị không đồng nhất | `present` một chiều · `good/mixed/poor` · `low/medium/high` · `present/absent` | Mỗi feature khai **loại thang**: `presence` (present/absent), `quality` (good/mixed/poor), `level` (low/medium/high). Feature chỉ có `present` thì không biểu diễn được "không cần view". |
| Lexicon chỉ trỏ tới feature, không trỏ tới giá trị | `crowd` luôn hiểu là `low` (`FEATURE_VALUE`) | Lexicon trỏ tới cặp `(feature_id, value)`. Khi đó "không quá đông, không quá vắng" ↦ `crowd=medium`, "nhộn nhịp, đông vui" ↦ `crowd=high`; ontology đã có sẵn `medium`/`high` (hint của `crowd` phân biệt rõ "không quá đông" = medium). |
| Tag chồng nghĩa | `long_stay_chill` (hint có cả "chill, thư giãn, làm việc") ↔ `laptop_friendly`; `cozy_decor` ("có gu") ↔ `photo_spot`; `nature` ("không khí trong lành") | Viết lại hint theo **điều quan sát được ở nơi đó**, không theo cảm xúc; bỏ "chill", "thư giãn", "làm việc" khỏi hint `long_stay_chill`. |
| Alias nằm rải rác | `src/trip/prepass.py` `LEXICON` (regex), lexicon trong `catalog.json`, brief §2.4 | Một nguồn alias duy nhất; prepass và catalog cùng đọc. |

## 3. Lớp tag nên có (ứng viên, chưa có trong v10)

Mỗi dòng là một cách nói hay gặp mà v10 không ánh xạ được.

| Người dùng nói | Tag ứng viên | Thang |
|---|---|---|
| nhộn nhịp, sôi động, đông vui, có không khí lễ hội | `lively` (hoặc dùng `crowd=high` khi lexicon trỏ được tới giá trị) | presence |
| riêng tư, kín đáo, không bị làm phiền | `privacy` | presence |
| mộc mạc, dân dã, chân chất, đúng chất Đà Lạt xưa | `rustic` | presence |
| sang chảnh, xịn, cao cấp ↔ bình dân, hạt dẻ | `price_level` | level (low/medium/high), tách khỏi `value_for_money` |
| thơ mộng, nên thơ, lãng mạn | hiện ghép `scenic_view` + `cozy_decor`; cân nhắc `romantic_setting` | presence |
| healing, chữa lành, nạp năng lượng | ghép `nature` + `noise=quiet` + `crowd=low`; không cần tag riêng | — |
| về đêm, đi chơi tối | `night_activity` (khác `contexts.time_of_day`) | presence |
| se lạnh, sương mù, lạnh mới đã | đã có `contexts.weather`; cần nối vào lexicon | — |
| hợp thú cưng | `pet_friendly` | presence |
| ít bậc nhưng vẫn có view | đã có `steep_or_stairs` + `scenic_view`; cần cặp đối nghịch trong dữ liệu, không cần tag | — |

## 4. Liên hệ với dữ liệu Laya v3

- v3 (`system_one_model/dataset/`) **không đổi ontology**: chỉ thêm alias và term mới trỏ vào feature v10, giữ `FEATURE_VALUE` hiện tại. Cặp kiểu "yên tĩnh nhưng đừng vắng quá" được gán nhãn theo quy ước tạm: `noise` (yên tĩnh) = A, `crowd` (ít người) = **B**, `trip.crowd_tolerance` = A.
- Khi §2 hàng 2 (lexicon trỏ tới giá trị) được chốt, các mẫu đó cần gán lại nhãn `crowd=medium`. Giữ `meta.mixed_level = true` trên các mẫu này để lọc lại được.
