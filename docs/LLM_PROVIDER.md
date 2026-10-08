# LLM Provider

Code gọi model theo **vai trò**, không gọi thẳng một model cố định. Vai trò (`Role`: biến env của key / endpoint / model / số call đồng thời) và các task corpus/turn (`Task`: vai trò, prompt, schema, `max_tokens`, `temperature`, `parallel` — bỏ trống thì lấy số của vai trò) khai báo ở `src/corpus/llm/` (`roles.py`, `tasks.py`). Task proposal nội bộ của Planning khai báo tại biên `src/planning/proposal.py`, dùng cùng role `AGENT`. Định nghĩa và yêu cầu của từng vai trò: `docs/CORPUS.md` §Vai trò model. File này chỉ ghi model nào đang đảm nhận vai trò và cách kết nối.

| Vai trò | Dùng ở | Model hiện tại | Đường mạng |
|---|---|---|---|
| ASR | `corpus` (TikTok) | ChunkFormer trên GPU local; ASR2 PhoWhisper-medium | Local |
| Extractor | `corpus` (observe, filter, qc, kiểm span, `asr_check`, `place_verify`, audit Gemma) | Gemma 4 trên host LAN (nhận ảnh); UIT API dự phòng | Mạng nội bộ |
| Judge | `corpus` (`judge audit / status / dedup`, kiểm địa điểm của `qc`) | Gemma 4 trên UIT API (cùng key / endpoint với Agent), 38 call đồng thời | Mạng UIT |
| Judge mạnh | giá trị cho phép, quyết định đóng cửa / gộp nơi | như Judge | Mạng UIT |
| Agent | `trip`, `decision` (lượt chữ), `planning` (proposal nội bộ) | Gemma 4 trên UIT API | Trực tiếp trong mạng UIT |

Judge khác họ model với Extractor (GPT / Claude / Gemini so với Gemma) nên lỗi hai bên độc lập.

## Judge (UIT API)

9router (proxy Codex) không chạy được trên server nên đã bỏ: không còn biến `JUDGE_API_KEY`, `JUDGE_BASE_URL`, `JUDGE_MODEL`, `JUDGE_STRONG_MODEL`. Ba vai trò Judge (`JUDGE`, `JUDGE_FIRST`, `JUDGE_STRONG`, `roles.py`) dùng `AGENT_API_KEY` / `AGENT_BASE_URL` / `AGENT_MODEL`, tức Gemma trên UIT (§UIT API), mặc định 38 call đồng thời trên key 40 call (hai slot còn lại cho Agent). Vì Gemma nhận `response_format`, Judge chạy guided như Extractor. Chỉ `JUDGE_FIRST_MODEL` còn là biến riêng (tên model trên endpoint này; trống = không có first reader). Hệ quả: Judge và Extractor cùng họ model nên lỗi không độc lập như thời Codex; precision vẫn đo bằng nhãn mạnh có sẵn (`CORPUS_HANDOFF.md` §Quy tắc đã chốt, mục 3).

## Host LAN (Extractor)

Server tương thích OpenAI trong mạng nội bộ, `http://192.168.20.150:8899/v1`, model `gemma-4-26b` (cùng model với UIT, nhận ảnh). Mọi task nhiều call và dài của corpus chạy ở đây; UIT giữ cho Agent và làm dự phòng (đổi lại ba biến Extractor trong `.env`).

Số call đồng thời: **`EXTRACTOR_PARALLEL=38`** (người dùng chốt 256 ngày 2026-10-06, hạ 218, 128, 64, 48 rồi 38 ngày 2026-10-07: host nghẽn, và ưu tiên chất lượng hơn tốc độ — xem "Sức chứa thật" dưới). Mọi task Extractor không tự đặt `parallel` dùng số này; `gmaps observe` lấy nó làm số slot tối đa. Đo 2026-10-06 (`logs/llm_probe.py`, client `max_retries=2`, 0 lỗi ở mọi mức):

| Đồng thời | Prompt ngắn (~250 token vào, ~60 ra) | Prompt cỡ observe (~2k vào, 300 ra) |
|---|---|---|
| 128 | ~4.600 req/phút, p95 1,8 s | ~1.130 req/phút, p95 7 s |
| 192 | ~5.400 req/phút, p95 2,7 s | ~1.290 req/phút, p95 9 s |
| 256 | ~5.600 req/phút, p95 3,2 s | ~1.480 req/phút, p95 11 s |

Không có retry, 256 đồng thời rớt ~5% call vì lỗi kết nối, nên client giữ retry. Con số là cho **cả host**: hai lệnh nặng chạy cùng lúc thì chia nhau (đặt `EXTRACTOR_PARALLEL` thấp hơn cho lệnh phụ qua biến môi trường).

**Sự cố 2026-10-07 (host LAN chậm, chưa giải quyết).** Từ khoảng 07:00 giờ VN, call sinh chữ 3 token tới host timeout >90 s (UIT vẫn 0,1 s), `gmaps observe` ghi ~1 file/phút (hôm trước ~18 nơi/phút) và nhiều nơi lỗi `APITimeoutError`. `GET /v1/models` vẫn 200 trong 6 ms vì chỉ chạm web server, không chứng minh engine còn sinh được. Chẩn đoán từ `GET /metrics` của vLLM (không cần key; đo 08:54): chạy 55 request, xếp hàng 71 (lý do `deferred`, không phải `capacity`), **KV cache 97%**, **667 lần preemption**. Tức bộ nhớ KV của GPU đầy, vLLM đẩy request ra rồi tính lại, nên chỉ ~50 request chạy cùng lúc dù client gửi 128 / 218 / 256. Hạ `EXTRACTOR_PARALLEL` 256 → 218 → 128 không đổi tốc độ, nên nút cổ chai là bộ nhớ host, không phải số kết nối. Chưa biết có người khác dùng chung host hay không. Việc thử tiếp: hạ về ~48, hoặc giảm token mỗi lô observe (~2k vào, ~2,5k ra), hoặc chủ host tăng bộ nhớ KV / chỉnh `max-num-seqs`. Kiểm nhanh: `curl -s http://192.168.20.150:8899/metrics | grep -E "num_requests_(running|waiting)|kv_cache_usage|preemptions"`.

**Sức chứa thật (đo 2026-10-07 10:00–11:30, host không ai khác dùng).** Sau khi chủ host đổi cấu hình, `/metrics` báo `kv_cache_size_tokens` **52.058** (trước ~240.000). Một call `review_observe` 15 review tốn ~4,8k token vào + ~3k token ra, nên host chỉ chạy thật ~35 call; phần thừa chỉ xếp hàng (thời gian chờ tính vào timeout 240 s của client). Host bị giới hạn ở **sinh token**: ~30 token/s mỗi chuỗi, call trung vị ~96 s. Số đo (`logs/prefix_tput.py`, vòng kín 240 s, token sinh/giây của cả host):

| Cấu hình | Token sinh/s | Chạy thật / chờ | KV |
|---|---|---|---|
| template hiện tại, 24 đồng thời | 624 | 25 / 12 | 98% |
| template hiện tại, 48 | 749 | 35 / 36 | 100% |
| dòng `Place:` dời xuống ngay trước `Reviews:`, 24 | 724 | 24 / 0 | 57% |
| như trên, 48 | 942 | 48 / 11 | 100% |
| như trên, 72 | 937 | 56 / 34 | 100% |

Hai chỗ phía client lãng phí host, **chưa sửa** vì đổi output (`logs/prompt_equiv.py`, 40 lô thật, temperature 0, khớp ở mức (review, feature, value) so với template hiện tại; chạy lại chính template hiện tại chỉ khớp 82,8% vì suy luận theo batch không tất định):
- **Prefix cache không dùng được.** vLLM bật `enable_prefix_caching`, nhưng `REVIEW_OBSERVE` đặt `Place: {name}` ở dòng 3, trước 3.842 token tĩnh (hướng dẫn + ontology 2.686 token), nên các nơi khác nhau chỉ chung 46 token (prefix hit 1–5%). Dời dòng đó xuống cuối: hit ~75%, +26% token/s ở mức trần. `VIDEO_OBSERVE`, `PHOTO_OBSERVE`, `REVIEW_VERIFY`, `ASR_CHECK`, `PLACE_VIDEO_VERIFY`, `OBS_AUDIT_GEMMA` cùng kiểu (biến trước phần tĩnh).
- **JSON pretty-print.** Model trả JSON thụt lề; cùng nội dung viết gọn chỉ tốn 52% token. Cờ grammar của server (`disable_any_whitespace`, `whitespace_pattern`) không có tác dụng trên host này (vLLM 0.30.0); thêm câu "Write the JSON compact on one line: no indentation, no line breaks." vào cuối prompt thì có: 3.012 → 1.528 token/call. Ba trường ngữ cảnh (`time_of_day`, `day_type`, `weather`) bắt buộc trong mỗi observation chiếm thêm ~19 token dù chỉ 1–7% observation đặt giá trị khác `unknown`.
- Khớp với template hiện tại: JSON gọn 76,5%, dời `Place` + JSON gọn 79,0% (mốc nhiễu 82,8%), số observation −4%. Lệch hơn mốc nhiễu một chút, không nói được tốt hay xấu hơn: phải đo ở mức (nơi, feature, value) với nhãn mạnh trước khi áp.

## UIT API

API tự host của UIT, tương thích OpenAI, tại `llm.uit.edu.vn`. **Chỉ truy cập được trong mạng campus UIT**, không có đường ra/vào Internet. Dùng chung một key, chung client SDK `openai`, chỉ đổi `base_url`.

| Model | Base URL | Giá trị `model` | Dùng trong dự án |
|---|---|---|---|
| Gemma 4 26B-A4B (Google, MoE) | `https://llm.uit.edu.vn/gemma/v1` | `gemma-4-26b` | Extractor, Judge |

Header xác thực: `Authorization: Bearer <LLM_API_KEY>`. Giới hạn: 32.768 token mỗi request (prompt + completion), tối đa 20 phút mỗi request.

Gemma: tối đa **40 request đồng thời mỗi key** (vượt → HTTP 429 "Too many concurrent requests"). Đo 2026-09-29 với `PLACE_FILTER` (prompt ngắn): 36 đồng thời → ~35 request/s, latency trung vị ~1 s, 0 lỗi; dùng UIT cho Extractor thì đặt `EXTRACTOR_PARALLEL=36` (cũng là mặc định khi thiếu biến). Nhận ảnh (đã kiểm tra: chép đúng chữ trên ảnh).

Thinking: bật bằng `extra_body={"chat_template_kwargs": {"enable_thinking": True}}`. Server không tách phần suy nghĩ ra field riêng; nó nằm trong `content` trước câu trả lời, nên code lấy khối JSON cuối cùng của `content` rồi mới validate.

`gmaps observe` kiểm tra endpoint bằng một call nhỏ khi bắt đầu (ngoài campus UIT trả trang chuyển hướng → dừng với thông báo rõ), rồi chạy `REVIEW_OBSERVE.parallel` (= `EXTRACTOR_PARALLEL`) call đồng thời; mỗi lô 15 review sinh ~2.500 token. Endpoint có thể dùng chung nên số slot tự điều chỉnh: gặp 429 → giảm còn 3/4 (tối thiểu 4), call đó chờ 20 s ngoài slot rồi thử lại (tối đa 30 lần, không đánh lỗi cả địa điểm); `cap` call liên tiếp thành công → thêm 1 slot, tối đa bằng số ban đầu. Mỗi call có timeout 240 s, tắt retry ngầm của SDK.

Biến môi trường của tiến trình (không đặt trong `.env`): `EXTRACTOR_ON_UIT=1` chuyển mọi task Extractor của tiến trình đó sang Gemma UIT (38 call); `EXTRACTOR_ALSO_UIT=1` cho `gmaps observe` dùng thêm UIT (38 slot) bên cạnh endpoint Extractor, các slot của hai endpoint chung một hàng như trên. Bật `EXTRACTOR_ALSO_UIT` thì không chạy Judge hay task `EXTRACTOR_ON_UIT` khác cùng lúc: key UIT chỉ nhận 40 call.

## Cấu hình

Cấu hình nằm trong `.env` ở root repo (đã gitignore), tạo từ mẫu `.env.example`:

| Biến | Dùng cho |
|---|---|
| `LLM_API_KEY` | Key của endpoint Extractor |
| `EXTRACTOR_BASE_URL`, `EXTRACTOR_MODEL` | Endpoint và model của Extractor |
| `EXTRACTOR_PARALLEL` | Số call đồng thời endpoint Extractor nhận (38 host LAN, 36 UIT; thiếu → 36) |
| `JUDGE_ENGINE`, `JUDGE_FIRST_MODEL` | `gemma`: audit chạy trên Extractor, một vòng; trống: audit chạy trên vai trò Judge. First reader tùy chọn |
| `AGENT_API_KEY`, `AGENT_BASE_URL`, `AGENT_MODEL` | Key, endpoint và model chung cho agent Trip/Decision và Planning nội bộ; thiếu thì lượt chữ dùng `policy.py`, proposal giữ baseline tất định |
| `CLOUDFLARE_API_TOKEN`, `CLOUDFLARE_ACCOUNT_ID` | Clef System 1 cấp allowlist tool đọc cho Trip |
| `CLEF_MODEL`, `CLEF_MODEL_ID`, `CLEF_TIMEOUT_S` | Model, Workers AI model id và timeout của Clef |
| `DATA_DIR` | Gốc dữ liệu thô (mặc định `data`) |
| `LIVE_CONTACT` | Liên hệ gửi trong User-Agent của request live context (Nominatim yêu cầu) |

Đọc qua `os.environ[...]` / `python-dotenv`. Không bao giờ hardcode key trong source, test, hay tài liệu.

`ASR_MODEL`: model ASR (Hugging Face id, hiện `khanhld/chunkformer-ctc-large-vie`), tải về lần đầu dùng. `ASR_ALT_MODEL`: ASR thứ hai, chỉ cho segment ASR chính sai (`asr_alt`, hiện `vinai/PhoWhisper-medium`).

Extractor gọi host LAN, Agent gọi UIT trong mạng campus, ASR trên GPU local, Judge gọi UIT (38 call).

Task `decision_turn` trả update `select | drop | lock | travel | crowd | price | trip | visited`; gu và mong muốn về chuyến luôn là `trip` (đi sang Trip Understanding qua harness), không có op gu riêng ở Decision. Task `trip_turn` nhận thêm `compared_places` trong `CURRENT CONTEXT` (nơi người dùng so sánh "giống X" kèm nét nổi bật lấy từ catalog) và chỉ được viết soft `inferred` từ đúng các nét đó (`docs/TRIP_UNDERSTANDING.md` §4).

Vai trò Agent chạy **trong một phiên người dùng**, có ngân sách thời gian: chờ token đầu `first_token_s` giây, cả call `total_s` giây (`config/trip.yaml`, `config/decision.yaml`, `config/planning.yaml`); quá thì Trip/Decision dùng `policy.py`, Planning nội bộ giữ baseline. Runtime chung `agents.run_structured` validate JSON/schema, giới hạn concurrency/queue qua `config/agents.yaml`; quota này chỉ trong tiến trình (`docs/AGENT_HARNESS.md` §5). Guard của module kiểm grounding/quyền; proposal Planning thử trên nháp rồi qua validator và điểm mục tiêu (`docs/PLANNING.md` §Agent đề xuất nội bộ).

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

Không dựa vào kiến thức sẵn có của model cho fact cụ thể hoặc thời sự. Luôn đưa văn bản nguồn vào prompt và yêu cầu model chỉ trả lời từ văn bản đó. Đây cũng là ranh giới dự án đã áp ở mức code: không bịa địa điểm, không có bằng chứng → không phải fact (xem `RULE.md`, `docs/ARCHITECTURE.md` §1).
