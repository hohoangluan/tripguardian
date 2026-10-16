# Trip Understanding đọc cùng release và cùng bằng chứng

> Thực hiện trong phiên hiện tại bằng `superpowers:subagent-driven-development`; mỗi phần theo `superpowers:test-driven-development`, review và kiểm chứng trước khi hoàn tất.

**Mục tiêu:** Trip dùng snapshot và semantic index của cùng release; số nơi hợp và gợi ý chỉ dùng eligible ID và verdict được phục vụ.

**Kiến trúc:** resolve root một lần tại factory Trip, truyền root đó vào cả snapshot và Looks. Catalog từ snapshot lấy membership và bằng chứng từ serving record. Giữ API legacy `from_records` cho fixture / consumer độc lập.

**Công nghệ:** Python, dataclass, public API `corpus.releases`, `corpus.snapshot`, `corpus.serving`, `corpus.index`; pytest và stub, không model/network.

## Ràng buộc

- Tuân thủ `RULE.md`; không ghi corpus từ Trip, không đổi pointer trong cập nhật này.
- Không thêm suy luận hard, không biến unknown/conflict thành bằng chứng chắc chắn.
- Không sửa UI hay đổi bộ câu hỏi đã chốt trong spec redesign ở phần đọc dữ liệu này.
- Không reset, checkout hoặc commit các thay đổi khác đang có trong workspace.
- Pin release cho toàn journey, budget/time và stay/cache vẫn theo spec normalization tổng; root được resolve ở đây là nền tảng reader, chưa thay thế journey pinning.

## 1. Factory và index dùng cùng root

File: `src/trip/api/tools.py`, `src/trip/infrastructure/looks.py`, test mới `tests/trip/test_normalized_readers.py`.

- [ ] Test factory với root có `releases/current`, release có manifest; stub `shared` và senses ghi root. Snapshot phải nhận `<release>/snapshot`, Looks phải nhận `<release>`. Test root legacy vẫn dùng chính root explicit.
- [ ] Chạy `.venv/bin/python -m pytest tests/trip/test_normalized_readers.py -q`; xác nhận fail do factory còn đọc legacy / Looks chưa nhận root.
- [ ] Dùng `corpus.releases.resolve(data_root)` tại `create_engine`; mở snapshot từ root đã resolve. `senses(cfg, catalog, *, data_root=None)` truyền root vào `Looks(..., data_root=data_root)`; `_load` gọi `Index.load(data=self.data_root)`.
- [ ] Chạy lại test; factory không gọi model, không đọc corpus của root khác, missing release manifest vẫn fail-closed.

## 2. Catalog không vượt membership / serving verdict

File: `src/trip/infrastructure/catalog.py`, `tests/trip/test_catalog_snapshot.py`.

- [ ] Test snapshot có intel ngoài `region.ids`, video trỏ ngoài membership và feature raw có signal nhưng serving là UNCERTAIN / thiếu / khác giá trị. Không đếm feature như bằng chứng hợp gu; không dựng lại evidence từ raw cho place ngoài tập.
- [ ] Test feature serving VERIFIED / OUTDATED có đủ `n_min` giữ giá trị và context; không làm dữ liệu yếu thành không thích. Giữ test API legacy riêng.
- [ ] Chạy test để xác nhận fail trước sửa.
- [ ] Lọc intel/video theo `region.ids`; khi có evidence record, tạo `Known` từ feature của serving record qua public `corpus.serving.feature`, status VERIFIED/OUTDATED và `n_min`. Không promote signal raw.
- [ ] Chạy `.venv/bin/python -m pytest tests/trip/test_catalog.py tests/trip/test_catalog_snapshot.py tests/trip/test_requirement_scope.py tests/trip/test_effects.py -q`.

## 3. Visual search luôn có phạm vi eligible

File: `src/trip/infrastructure/looks.py`, `tests/trip/test_normalized_readers.py`.

- [ ] Test index có ID ngoài Catalog và request không truyền `within`; truy xuất vẫn phải được giới hạn vào Catalog. Request có `within` lấy giao hai tập; không trả ảnh/style/cluster hoặc nhận diện place ngoài tập này.
- [ ] Chạy test và xác nhận fail do code hiện chỉ truyền `within` từ caller.
- [ ] `Looks` tạo phạm vi từ `catalog.by_id`; áp dụng cho cues/photo/similar và lọc kinds/photo/name/style theo membership. Giữ trạng thái index unavailable không chặn lượt.
- [ ] Chạy test Trip liên quan, boundary và integration public adapter. Không tải embedder trong test.

## 4. Review, tài liệu và kiểm chứng

- [ ] Review từng phần và toàn diff, xử lý lỗi có bằng chứng; chạy các test liên quan mới trước suite rộng.
- [ ] Bổ sung §Sử dụng dữ liệu chuẩn hóa vào spec redesign, sửa tham chiếu API `openai_chat` đã bỏ thành `Chat` hiện hành. Giữ quyết định sản phẩm ở §2.
- [ ] Cập nhật hiện trạng reader trong `docs/TRIP_UNDERSTANDING.md`, dev log; ghi kết quả build nền vào handoff khi lỗi/thành công.
- [ ] Kiểm `git diff --check` và test Trip/Decision/Harness liên quan. Gộp nội dung đã làm vào tài liệu chính thức, xóa plan tạm khi hoàn tất.
