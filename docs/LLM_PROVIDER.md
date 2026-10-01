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

`gmaps observe` kiểm tra endpoint bằng một call nhỏ khi bắt đầu (ngoài campus UIT trả trang chuyển hướng → dừng với thông báo rõ), rồi chạy `REVIEW_OBSERVE.parallel` = 38 call đồng thời; mỗi lô 15 review sinh ~2.500 token, ~50 s. Key dùng chung với người khác: gặp 429 thì `Task.ask` chờ rồi thử lại.

## Cấu hình

Cấu hình nằm trong `.env` ở root repo (đã gitignore), tạo từ mẫu `.env.example`:

| Biến | Dùng cho |
|---|---|
| `LLM_API_KEY` | Key UIT API (Extractor) |
| `EXTRACTOR_BASE_URL`, `EXTRACTOR_MODEL` | Endpoint và model của Extractor |
| `JUDGE_API_KEY`, `JUDGE_BASE_URL`, `JUDGE_MODEL` | Key, endpoint và model của Judge (hiện = UIT Gemma) |

Đọc qua `os.environ[...]` / `python-dotenv`. Không bao giờ hardcode key trong source, test, hay tài liệu.

`ASR_MODEL`: model ASR (Hugging Face id, hiện `khanhld/chunkformer-ctc-large-vie`), tải về lần đầu dùng. `ASR_ALT_MODEL`: ASR thứ hai, chỉ cho segment ASR chính sai (`asr_alt`, hiện `vinai/PhoWhisper-medium`).

Mọi model được gọi trực tiếp: UIT trong mạng campus, ASR trên GPU local.

## ASR local

ChunkFormer (`src/corpus/llm/asr.py`) chạy GPU khi `torch.cuda.is_available()`, không thì CPU. Cài: torch bản CUDA (`--index-url https://download.pytorch.org/whl/cu128`; index chưa có bản mới nhất thì pip giữ bản CPU cùng số phiên bản, cần ghi rõ phiên bản + `--force-reinstall`), `pip install chunkformer --no-deps` (phụ thuộc `deepspeed` chỉ dùng cho train, build lỗi trên Windows) rồi các phụ thuộc còn lại, `silero-vad`, `soundfile`, và `ffmpeg` trong PATH. Đọc / ghi âm thanh bằng `soundfile` vì torchaudio ≥ 2.9 cần `torchcodec` cho file. Đo 2026-09-30 trên RTX 3050 4 GB: 14,7 s âm thanh → 2,5 s.

So model ASR trên đoạn khó (2026-10-01): không model nào nghe đúng tên thương hiệu / từ mượn ("PiNi": ChunkFormer "mini", PhoWhisper-medium "bebé"); PhoWhisper bắt được từ ChunkFormer bỏ sót ("quỷ núi", "phương thức") nên làm ASR2; Whisper large-v3-turbo không dùng được cho tiếng Việt (mọi đoạn ra cùng câu bịa "Hãy subscribe cho kênh Ghiền Mì Gõ"). Gemma 4 26B trên UIT không nhận audio (HTTP 400 "does not have an audio tower"), chỉ sửa từ text + ảnh. `Task.ask` thử lại tối đa 4 lần khi JSON hỏng (guided decoding thỉnh thoảng lặp khoảng trắng tới hết `max_tokens`) và khi HTTP 429 / lỗi mạng (key 40 đồng thời dùng chung giữa các lệnh; chờ 2 s, gấp đôi mỗi lần).

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
