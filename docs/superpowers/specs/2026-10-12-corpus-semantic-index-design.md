# Spec: chỉ mục ngữ nghĩa — phần còn lại (lớp A, mask cho Decision, đo chất lượng)

File làm việc tạm (`RULE.md` §0.1). Phần đã làm (lớp B tag phong cách, lớp C vector ảnh / chữ, `corpus.index`, vai trò Embedder) đã gộp vào `docs/CORPUS.md` §Chỉ mục ngữ nghĩa, `docs/TRIP_UNDERSTANDING.md` §18, `docs/LLM_PROVIDER.md`. Khi làm xong phần dưới: gộp vào `docs/CORPUS.md`, `docs/PLACE_DECISION.md` §5, §8 rồi xóa file này.

## 1. Lớp A: tiện ích (feature mới, nhóm `experience`, ontology v13)

Thứ kiểm chứng được và user hay hỏi kiểu "muốn đi chỗ có X". Đi đúng đường feature hiện có: observation có span → aggregate → `check()` fail-closed → lọc cứng được qua `hard_result`.

| Feature | Thang | Ghi chú |
|---|---|---|
| `swimming_pool` | `present / absent` | Hồ bơi nhân tạo; context `heated` khi có bằng chứng |
| `natural_swimming` | `present / absent` | Tắm suối / hồ / thác; cờ mùa (`docs/PLACE_DECISION.md` §7) và `fit.kids` |
| `waterfall`, `boat_ride`, `horse_riding`, `bbq_campfire`, `alpine_coaster`, `board_games` | `present` | |

Bump ontology làm mọi observation bị trích lại: chạy với `OBSERVE_KEEP_STALE=1` hoặc một pass riêng chỉ cho các feature mới (như `gmaps style_observe`), quyết khi làm.

## 2. Mask tất định cho Place Decision

Đã thay bằng `docs/superpowers/specs/2026-10-13-corpus-snapshot-design.md`.

## 3. Đo chất lượng của tìm kiếm ngữ nghĩa

Bộ ~50 câu khó (gồm "vibe retro", "hồ bơi, tắm suối", ảnh một nơi, ảnh phong cách; ảnh mẫu lấy từ corpus và ảnh ngoài), Judge chấm precision@10 theo ý câu, nhãn người trên một mẫu để đo độ tin của Judge. Chọn model Embedder (SigLIP2 so với jina-clip-v2) và ngưỡng `config/index.yaml` theo bộ này. Frame TikTok trùng nhau: đã bỏ theo cosine trong cùng video; cần đo lại khi có bộ câu.
