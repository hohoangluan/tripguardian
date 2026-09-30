# LLM Provider

Code gọi model theo **vai trò**, không gọi thẳng một model cố định. Vai trò (`Role`: biến env của key / endpoint / model) và mọi task (`Task`: vai trò, prompt, schema, `max_tokens`, `temperature`, `parallel`) khai báo ở `src/corpus/llm/` (`roles.py`, `tasks.py`); sửa prompt hay thiết lập ở đó. Định nghĩa và yêu cầu của từng vai trò: `docs/specs/CORPUS_SPEC.md`, mục Vai trò model. File này chỉ ghi model nào đang đảm nhận vai trò và cách kết nối.

| Vai trò | Model hiện tại | Đường mạng |
|---|---|---|
| ASR | ChunkFormer trên GPU local | Local |
| Extractor | Gemma 4 trên UIT API (miễn phí, nhận ảnh) | Trực tiếp trong mạng UIT |
| Judge | Gemma 4 trên UIT API (cùng model với Extractor) | Trực tiếp trong mạng UIT |

Judge và Extractor dùng chung model, tách vai trò bằng prompt chuyên biệt riêng cho từng vai trò; Judge bật thinking. Vì chung model nên lỗi hai bên không hoàn toàn độc lập: nếu nhãn review cho thấy Judge bỏ sót lỗi của Extractor, chuyển Judge sang họ model khác (chỉ đổi config, ví dụ `qwen3.8-27b` tại `https://llm.uit.edu.vn/qwen/v1`).

## UIT API

API tự host của UIT, tương thích OpenAI, tại `llm.uit.edu.vn`. **Chỉ truy cập được trong mạng campus UIT**, không có đường ra/vào Internet. Dùng chung một key, chung client SDK `openai`, chỉ đổi `base_url`.

| Model | Base URL | Giá trị `model` | Dùng trong dự án |
|---|---|---|---|
| Gemma 4 26B-A4B (Google, MoE) | `https://llm.uit.edu.vn/gemma/v1` | `gemma-4-26b` | Extractor, Judge |

Header xác thực: `Authorization: Bearer <LLM_API_KEY>`. Giới hạn: 32.768 token mỗi request (prompt + completion), tối đa 20 phút mỗi request.

Gemma: tối đa **40 request đồng thời mỗi key** (vượt → HTTP 429 "Too many concurrent requests"). Đo 2026-09-29 với `PLACE_FILTER` (prompt ngắn): 36 đồng thời → ~35 request/s, latency trung vị ~1 s, 0 lỗi; `Task.parallel` mặc định 36. Nhận ảnh (đã kiểm tra: chép đúng chữ trên ảnh).

Thinking: bật bằng `extra_body={"chat_template_kwargs": {"enable_thinking": True}}`. Server không tách phần suy nghĩ ra field riêng; nó nằm trong `content` trước câu trả lời, nên code lấy khối JSON cuối cùng của `content` rồi mới validate.

## Cấu hình

Cấu hình nằm trong `.env` ở root repo (đã gitignore), tạo từ mẫu `.env.example`:

| Biến | Dùng cho |
|---|---|
| `LLM_API_KEY` | Key UIT API (Extractor) |
| `EXTRACTOR_BASE_URL`, `EXTRACTOR_MODEL` | Endpoint và model của Extractor |
| `JUDGE_API_KEY`, `JUDGE_BASE_URL`, `JUDGE_MODEL` | Key, endpoint và model của Judge (hiện = UIT Gemma) |

Đọc qua `os.environ[...]` / `python-dotenv`. Không bao giờ hardcode key trong source, test, hay tài liệu.

Mọi model được gọi trực tiếp: UIT trong mạng campus, ASR trên GPU local.

## Chứng chỉ TLS

`llm.uit.edu.vn` dùng chuỗi chứng chỉ về **Sectigo Public Server Authentication Root E46**. CA store cũ (ví dụ Ubuntu 20.04, `ca-certificates` 2023) không có root này, nên gọi sẽ lỗi `unable to get local issuer certificate` dù đang ở trong mạng campus.

Cách sửa mà không tắt verify: `certs/sectigo-root-e46-cross-usertrust-ecc.pem` là E46 được cross-sign bởi **USERTrust ECC Certification Authority**, một root mà các store này đã tin. Thêm nó làm intermediate là đủ chuỗi.

```bash
# một lần mỗi máy (bundle đã gitignore)
cat /etc/ssl/certs/ca-certificates.crt certs/sectigo-root-e46-cross-usertrust-ecc.pem > certs/uit-ca-bundle.pem
```

Sau đó trỏ client vào bundle, ví dụ trong `.env`:

```bash
SSL_CERT_FILE=certs/uit-ca-bundle.pem   # Python ssl / httpx (openai SDK)
CURL_CA_BUNDLE=certs/uit-ca-bundle.pem  # curl
```

Không bao giờ dùng `verify=False` / `curl -k`. Máy có CA store mới không cần bước này.

## Grounding

Không dựa vào kiến thức sẵn có của model cho fact cụ thể hoặc thời sự. Luôn đưa văn bản nguồn vào prompt và yêu cầu model chỉ trả lời từ văn bản đó. Đây cũng là ranh giới dự án đã áp ở mức code: không bịa địa điểm, không có bằng chứng → không phải fact (xem `RULE.md`, `docs/Project_Context.md`).
