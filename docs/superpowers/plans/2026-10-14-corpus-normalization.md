# Kế hoạch chuẩn hóa và tổ chức Corpus

> Thực hiện tuần tự trong phiên hiện tại bằng `superpowers:executing-plans`; kiểm chứng theo `superpowers:test-driven-development`.

**Mục tiêu:** chuẩn hóa đầu vào mỗi lần aggregate; dựng release offline từ dữ liệu đã lưu, giữ nguồn gốc và chỉ publish sau kiểm chứng.

**Kiến trúc:** nguồn thô giữ tại `data/<source>/`. Bản chuẩn hóa nằm trong `data/normalization/<id>/<source>/`; manifest ghi hash, membership, phiên bản và lỗi. Artifact dẫn xuất nằm trong `data/releases/<id>/`; online đọc release được publish. Không thay PostgreSQL.

**Công nghệ:** Python, Pydantic, JSON, LanceDB; dùng vector đã lưu.

## Ràng buộc

- Tuân thủ `RULE.md`; tài liệu tiếng Việt, code tiếng Anh.
- Không sửa/xóa raw, observation, nhãn hoặc vector gốc; không tự khôi phục backup.
- Không crawl hoặc gọi model trong migration hiện tại. Build thường vẫn có quyền Extractor/Judge theo cấu hình.
- Giữ ID, version, sample, author, span và provenance; thiếu bằng chứng giữ unknown.
- Không gộp payload giữa các nguồn. Chỉ manifest chứa reference chung.
- Không đổi pointer đang phục vụ trước khi các artifact đã dựng và kiểm xong.
- Thay đổi Journey pinning, budget/time và cache của các module online thuộc các bước riêng trong spec tổng; đợt này chỉ triển khai đường Corpus và projection.

## 1. Contract và normalization

File: `src/corpus/normalize/{__init__,schema,run}.py`, `tests/normalization/test_normalize.py`.

API: `normalize(city: str, root: Path | None = None, canonical: dict[str, str] | None = None) -> Normalization`; kết quả có `id`, `root`, `manifest` và `documents()` trả `(input_path, normalized_document)`.

- [ ] Test bảo toàn hash input, ID/nhãn/version, missing context, malformed JSON, duplicate scoped ID, membership và backup.
- [ ] Chạy test, xác nhận fail do API chưa tồn tại.
- [ ] Adapter có kiểu: validate observation; context thiếu thành unknown; document container null thành container rỗng; trường không parse được báo issue. Giữ payload gốc riêng.
- [ ] Inventory lấy từ list của city và stay, resolve approved merge; raw ngoài inventory chỉ historical. Nếu thiếu inventory, giữ chế độ legacy có nhãn rõ để API/test độc lập tiếp tục hoạt động.
- [ ] Hash input/config và manifest; output deterministic, đổi input sinh ID khác. Viết bản normalized theo nguồn; báo compatibility cũ cần kiểm, không giả mạo version mới.
- [ ] Test pass và chạy lần hai không nhân đôi dữ liệu.

## 2. Tự động trong aggregate và dựng release an toàn

File: `src/corpus/aggregate/place.py`, `serving/run.py`, `snapshot/{compile,read}.py`, `src/corpus/releases/{__init__,run}.py`, `src/corpus/__main__.py`; test `tests/normalization/test_release.py`.

API mở rộng: `aggregate.run(city, *, output_root=None)`; `serving.run(city, *, root=None, publish=True)`; `compile_snapshot(city, root=None, *, source_root=None, publish=True)`; `rebuild(city, root=None, *, publish=False) -> dict`.

- [ ] Test aggregate tự normalization sau khi input đổi; exclusion có lý do; đường output staging không xóa intel hiện hành.
- [ ] Test build lỗi giữ nguyên pointer; snapshot staging không prune; release chứa bản intel/serving bất biến.
- [ ] Aggregate đọc manifest thay glob nguồn; giữ đường input gốc trong provenance. Ghi output vào root explicit khi rebuild.
- [ ] Rebuild tạo release staging, aggregate và serving/snapshot tại staging, tái đóng gói vector tương thích; kiểm IDs và snapshot đọc lại được.
- [ ] Publish atomic một pointer release; reader default resolve release, reader root explicit giữ API độc lập. Retention không xóa snapshot release còn tham chiếu.
- [ ] CLI `python -m corpus normalize [--rebuild] [--publish] --city dalat`; publish chỉ hợp lệ cùng rebuild.

## 3. Index, projection và đóng gói

File: `src/corpus/index/compile.py`, `query.py`, `web/scripts/export_snapshot.py`, `scripts/pack_data.py` và test liên quan.

- [ ] Test model/vector dimension, missing media, stale evidence; không sinh embedding mới.
- [ ] Index compile nhận source/output root explicit; release chỉ dùng ID served. Span phải còn trong intel đã qua gate; model/dimension không tương thích được báo và bỏ.
- [ ] Default index reader resolve cùng release với snapshot.
- [ ] Web serving projection lấy đúng tập eligible của release; admin export có view riêng và vẫn xem inventory.
- [ ] Packaging exclude normalization/staging/backup/user data; chỉ đóng gói release active và artifacts được tham chiếu, giữ media theo nguồn.

## 4. Migration dữ liệu hiện có và kiểm chứng

- [ ] Chạy test Corpus liên quan trên fixture trước khi đụng dữ liệu hiện hành.
- [ ] Chạy normalize/rebuild offline; so baseline membership, feature và semantic coverage; ghi report và mọi ID bị bỏ.
- [ ] Kiểm hash input trước/sau, source references, đọc lại snapshot/index, zero model/network call.
- [ ] Publish release đã kiểm; export web serving và admin view từ cùng release.
- [ ] Chạy lại normalization để kiểm idempotency; kiểm regression Trip/Decision/Planning/Harness không gọi live/model.
- [ ] Gộp hiện trạng vào `docs/CORPUS.md`, sửa lệnh ở README; xóa plan này khi hoàn tất. Spec tổng giữ đến khi các contract online còn lại được triển khai.
