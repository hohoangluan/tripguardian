# TripGuardian Pitch Deck Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Dựng deck pitching TripGuardian 14 slide bằng HTML và xuất PowerPoint chỉnh sửa được, bám đúng sản phẩm, dữ liệu và thang điểm cuộc thi.

**Architecture:** Deck là một trang HTML tĩnh 1920 × 1080 dùng `deck-stage.js`; mỗi slide là một `<section>` trực tiếp để chữ, shape và animation vẫn chỉnh sửa được. Asset thật của sản phẩm được sao chép vào thư mục deck; một validator Node kiểm tra contract tĩnh, một script Playwright chụp từng slide qua HTTP, và exporter của `baoyu-design` tạo `.pptx` editable.

**Tech Stack:** HTML5, CSS, vanilla JavaScript, `deck-stage.js`, Node.js, `playwright-core`, Chromium cục bộ, `baoyu-design` `record-asset.mjs`, `gen-pptx`.

## Global Constraints

- Nội dung deck bằng tiếng Việt; code, comment, identifier và tên file bằng tiếng Anh.
- Kích thước 1920 × 1080, tỉ lệ 16:9; đúng 14 slide.
- Font hiển thị: Lora cho tiêu đề, Be Vietnam Pro cho nội dung, JetBrains Mono cho số liệu; khi xuất PPTX dùng Google Font tương ứng.
- Mọi text slide tối thiểu 24 px; tiêu đề tối thiểu 48 px.
- Nền chính chỉ gồm giấy `#FAF7F2` và xanh Thông đậm; Hồng sương và Nắng là điểm nhấn.
- Slide là HTML tĩnh; không dùng React hoặc script sinh DOM slide.
- Slide 7 và slide 11 là hai slide duy nhất có `data-anim`.
- Không có speaker notes, số traction, doanh thu, thị trường hoặc kết quả thử nghiệm không có nguồn.
- Số liệu lấy lại trực tiếp từ `data/serving/places.json` và `data/decision/eval.json` tại thời điểm dựng.
- Không sửa code sản phẩm ngoài `designs/tripguardian-pitch/`.
- Worktree đang có thay đổi và staged state của người dùng; mọi commit phải dùng đường dẫn tường minh và `git commit --only` để không cuốn thay đổi khác vào.

---

## File Structure

```text
designs/tripguardian-pitch/
├── TripGuardian Pitch.html       # deck 14 slide, toàn bộ copy và CSS
├── deck-stage.js                 # scaffold nguyên bản từ baoyu-design
├── scratchpad.md                 # title sequence, timing và nguồn claim
├── pptx.config.json              # cấu hình export 14 slide editable
├── _d_meta.json                  # asset index do record-asset tạo
├── assets/
│   ├── logo.webp                 # logo sản phẩm
│   ├── landing.png               # landing thật
│   ├── understand.png            # màn hiểu chuyến đi
│   ├── compare.png               # màn so sánh
│   └── plan.png                  # màn lịch trình có nội dung
├── scripts/
│   ├── validate-deck.mjs         # kiểm tra contract tĩnh
│   └── capture-deck.mjs          # chụp từng slide qua HTTP
├── shots/                        # 14 ảnh QA, không dùng làm slide
└── TripGuardian-Pitch.pptx       # PowerPoint editable
```

### Task 1: Scaffold và contract kiểm tra

**Files:**
- Create: `designs/tripguardian-pitch/scratchpad.md`
- Create: `designs/tripguardian-pitch/scripts/validate-deck.mjs`
- Create: `designs/tripguardian-pitch/deck-stage.js`
- Create: `designs/tripguardian-pitch/assets/logo.webp`
- Create: `designs/tripguardian-pitch/assets/landing.png`
- Create: `designs/tripguardian-pitch/assets/understand.png`
- Create: `designs/tripguardian-pitch/assets/compare.png`
- Create: `designs/tripguardian-pitch/assets/plan.png`

**Interfaces:**
- Consumes: spec `docs/superpowers/specs/2026-10-09-tripguardian-pitch-design.md`, asset hiện có trong `web/public/img/` và `web/shots/app/`.
- Produces: contract `validate-deck.mjs <html-path>` với exit 0 khi deck hợp lệ, exit 1 kèm danh sách lỗi khi sai.

- [ ] **Step 1: Tạo thư mục và sao chép scaffold/asset**

Run:

```bash
mkdir -p designs/tripguardian-pitch/assets designs/tripguardian-pitch/scripts designs/tripguardian-pitch/shots
cp /home/vannk/.codex/skills/baoyu-design/starter-components/deck-stage.js designs/tripguardian-pitch/deck-stage.js
cp web/public/img/logo.webp designs/tripguardian-pitch/assets/logo.webp
cp web/shots/app/01-landing.png designs/tripguardian-pitch/assets/landing.png
cp web/shots/app/04-understand-chat.png designs/tripguardian-pitch/assets/understand.png
cp web/shots/app/23-compare.png designs/tripguardian-pitch/assets/compare.png
cp web/shots/app/25-plan-choose.png designs/tripguardian-pitch/assets/plan.png
```

Expected: tám đường dẫn đích tồn tại; không file nào tham chiếu ngược ra ngoài `designs/tripguardian-pitch/`.

- [ ] **Step 2: Viết title sequence và nguồn claim**

Create `scratchpad.md` với nội dung đầy đủ:

```markdown
# TripGuardian pitch scratchpad

## Title sequence
1. TripGuardian — Chọn đúng nơi trước khi xếp lịch
2. Nhiều gợi ý hơn không làm chuyến đi dễ quyết định hơn
3. Người Việt đang tự nối mạng xã hội, Maps và review bằng tay
4. Các công cụ hiện tại dừng ở tìm kiếm hoặc sinh lịch
5. TripGuardian biến ý định thành quyết định có kiểm chứng
6. Một hành trình: hiểu → chọn → kiểm tra → xếp lịch
7. Luồng quyết định từ mục tiêu đến các phương án đánh đổi
8. Place Intelligence biến dữ liệu rời rạc thành bằng chứng
9. AI đề xuất; constraint và validator giữ kế hoạch khả thi
10. Kiến trúc tách tri thức địa điểm khỏi từng chuyến đi
11. Sản phẩm đã chạy trên dữ liệu Đà Lạt thực
12. Người dùng luôn là người quyết định cuối
13. Bước tiếp theo là tăng coverage trước khi mở rộng địa bàn
14. Từ hàng nghìn nơi đến một chuyến đi có thể tin

## Timing
00:30 · 01:00 · 01:00 · 01:00 · 01:00 · 01:15 · 01:30 · 01:15 · 01:15 · 01:15 · 01:15 · 01:15 · 00:45 · 00:30

## Sources
- Product scope and principles: docs/Project_Context.md, docs/ARCHITECTURE.md
- Current behavior: docs/log/DEV_LOG.md
- Current corpus metrics: data/serving/places.json
- Current evaluation: data/decision/eval.json
- UI screenshots: web/shots/app/
```

- [ ] **Step 3: Viết validator thất bại trước khi có deck**

Create `scripts/validate-deck.mjs`:

```js
import fs from "node:fs";
import path from "node:path";

const target = process.argv[2];
if (!target) {
  console.error("usage: node validate-deck.mjs <deck.html>");
  process.exit(64);
}

const htmlPath = path.resolve(target);
if (!fs.existsSync(htmlPath)) {
  console.error(`missing deck: ${htmlPath}`);
  process.exit(1);
}

const html = fs.readFileSync(htmlPath, "utf8");
const errors = [];
const sections = [...html.matchAll(/<section\b[^>]*data-label="([^"]+)"[^>]*>/g)];
const anims = [...html.matchAll(/\bdata-anim="([^"]+)"/g)];
const imageRefs = [...html.matchAll(/<img\b[^>]*src="([^"]+)"/g)].map((m) => m[1]);

if (!html.includes('<deck-stage width="1920" height="1080">')) errors.push("deck-stage must be 1920x1080");
if (!html.includes('<script src="deck-stage.js"></script>')) errors.push("deck-stage.js must be loaded");
if (sections.length !== 14) errors.push(`expected 14 slides, found ${sections.length}`);
if (new Set(sections.map((m) => m[1])).size !== 14) errors.push("slide labels must be unique");
if (anims.length < 8 || anims.length > 18) errors.push(`expected 8-18 meaningful builds, found ${anims.length}`);
if (!html.includes("section[data-label] > *:not(img):not(picture):not(video):not(svg):not(canvas)")) errors.push("missing slide wrapper fill rule");
if (!html.includes("--type-title: 64px")) errors.push("missing 64px title token");
if (!html.includes("--type-small: 24px")) errors.push("smallest text token must be 24px");
if (html.includes('id="speaker-notes"')) errors.push("speaker notes are out of scope");
if (/font-size:\s*(?:[0-9]|1[0-9]|2[0-3])px/.test(html)) errors.push("font size below 24px found");

for (const ref of imageRefs) {
  if (/^(?:https?:|\/\/|\.\.\/)/.test(ref)) errors.push(`non-local image reference: ${ref}`);
  const resolved = path.resolve(path.dirname(htmlPath), ref);
  if (!fs.existsSync(resolved)) errors.push(`missing image: ${ref}`);
}

if (errors.length) {
  console.error(errors.map((item) => `- ${item}`).join("\n"));
  process.exit(1);
}

console.log(`ok: ${sections.length} slides, ${anims.length} animations, ${imageRefs.length} local images`);
```

- [ ] **Step 4: Chạy validator để xác nhận fail đúng lý do**

Run:

```bash
node designs/tripguardian-pitch/scripts/validate-deck.mjs "designs/tripguardian-pitch/TripGuardian Pitch.html"
```

Expected: exit 1 và dòng `missing deck:`.

- [ ] **Step 5: Commit scaffold bằng đường dẫn tường minh**

Run:

```bash
git add designs/tripguardian-pitch/scratchpad.md designs/tripguardian-pitch/scripts/validate-deck.mjs designs/tripguardian-pitch/deck-stage.js designs/tripguardian-pitch/assets
git commit --only designs/tripguardian-pitch/scratchpad.md designs/tripguardian-pitch/scripts/validate-deck.mjs designs/tripguardian-pitch/deck-stage.js designs/tripguardian-pitch/assets -m "feat: scaffold TripGuardian pitch deck"
```

Expected: commit chỉ chứa các file vừa liệt kê; staged state khác vẫn còn nguyên.

### Task 2: Author deck HTML 14 slide

**Files:**
- Create: `designs/tripguardian-pitch/TripGuardian Pitch.html`

**Interfaces:**
- Consumes: `deck-stage.js`, năm asset local, title sequence và số liệu JSON hiện tại.
- Produces: `<deck-stage width="1920" height="1080">` có đúng 14 `<section data-label>` tĩnh; slide 7 và 11 có tổng 8–18 `data-anim` hợp lệ.

- [ ] **Step 1: Đọc lại số liệu ngay trước khi viết copy**

Run:

```bash
jq '.summary | {at, places, areas, feature_status}' data/serving/places.json
jq '.summary | {trips, shortlist, violations, unknown_in_main, uncertain_in_main, near_duplicate_rate, filled_rate, ms_max}' data/decision/eval.json
```

Expected tại snapshot 2026-10-08: `places=1696`, `areas=128`, `VERIFIED=28466`, `trips=30`, `filled_rate=0.967`, `violations=0`, `ms_max=273`. Nếu file đã đổi, dùng số mới trong deck và `scratchpad.md`.

- [ ] **Step 2: Viết base HTML/CSS và 14 slide tĩnh**

Create `TripGuardian Pitch.html` theo contract sau:

```html
<!doctype html>
<html lang="vi">
<head>
  <meta charset="utf-8">
  <meta name="viewport" content="width=device-width,initial-scale=1">
  <title>TripGuardian Pitch</title>
  <link rel="preconnect" href="https://fonts.googleapis.com">
  <link rel="preconnect" href="https://fonts.gstatic.com" crossorigin>
  <link href="https://fonts.googleapis.com/css2?family=Be+Vietnam+Pro:wght@400;500;600;700&family=JetBrains+Mono:wght@500;700&family=Lora:ital,wght@0,500;0,600;0,700;1,500&display=swap" rel="stylesheet">
  <style>
    :root {
      --paper: #faf7f2;
      --ink: #183034;
      --pine: #0f6b5c;
      --pine-dark: #083f39;
      --mist: #dceceb;
      --rose: #a83f67;
      --rose-soft: #f2ced8;
      --sun: #d58a16;
      --sun-soft: #f5e5c4;
      --line: #cfc7bc;
      --type-display: 88px;
      --type-title: 64px;
      --type-subtitle: 44px;
      --type-body: 32px;
      --type-small: 24px;
      --pad-top: 88px;
      --pad-bottom: 76px;
      --pad-x: 100px;
      --gap-title: 44px;
      --gap-item: 28px;
    }
    * { box-sizing: border-box; }
    html, body { margin: 0; min-height: 100%; background: #102321; color: var(--ink); }
    body { font-family: "Be Vietnam Pro", sans-serif; }
    deck-stage:not(:defined) { visibility: hidden; }
    section[data-label] > *:not(img):not(picture):not(video):not(svg):not(canvas) { height: 100%; box-sizing: border-box; }
    .slide { position: relative; overflow: hidden; padding: var(--pad-top) var(--pad-x) var(--pad-bottom); background: var(--paper); }
    .slide--dark { background: var(--pine-dark); color: white; }
    .eyebrow { font-size: var(--type-small); font-weight: 700; letter-spacing: .12em; text-transform: uppercase; }
    h1, h2 { margin: 0; font-family: "Lora", serif; line-height: 1.08; }
    h1 { font-size: var(--type-display); }
    h2 { font-size: var(--type-title); }
    p, li { font-size: var(--type-body); line-height: 1.45; }
    .small { font-size: var(--type-small); line-height: 1.45; }
    .mono { font-family: "JetBrains Mono", monospace; }
  </style>
</head>
<body>
  <deck-stage width="1920" height="1080">
    <section data-label="Cover"><div class="slide slide--cover"><img src="assets/logo.webp" alt="TripGuardian"><h1>TripGuardian</h1><p>Chọn đúng nơi trước khi xếp lịch</p></div></section>
    <section data-label="Problem"><div class="slide"><h2>Nhiều gợi ý hơn không làm chuyến đi dễ quyết định hơn</h2><p>Người đi du lịch không thiếu gợi ý. Họ thiếu một cách để quyết định.</p></div></section>
    <section data-label="Vietnam context"><div class="slide"><h2>Người Việt đang tự nối mạng xã hội, Maps và review bằng tay</h2><p>Khám phá · Kiểm tra vị trí · Đọc trải nghiệm · Tự ghép thành quyết định</p></div></section>
    <section data-label="Market gap"><div class="slide"><h2>Các công cụ hiện tại dừng ở tìm kiếm hoặc sinh lịch</h2><p>TripGuardian kiểm tra lựa chọn trước khi xếp lịch.</p></div></section>
    <section data-label="Value proposition"><div class="slide slide--dark"><h2>TripGuardian biến ý định thành quyết định có kiểm chứng</h2><p>Nơi nào hợp? Vì sao? Có thực sự đi cùng nhau được không?</p></div></section>
    <section data-label="User journey"><div class="slide"><h2>Một hành trình: hiểu → chọn → kiểm tra → xếp lịch</h2><img src="assets/understand.png" alt="Màn hiểu chuyến đi"></div></section>
    <section data-label="Decision flow"><div class="slide"><h2>Luồng quyết định từ mục tiêu đến các phương án đánh đổi</h2><p data-anim="fade-in">Đầu vào → Place Intelligence → Place Decision → Planning</p></div></section>
    <section data-label="Place intelligence"><div class="slide"><h2>Place Intelligence biến dữ liệu rời rạc thành bằng chứng</h2><p>Fact · Signal · Estimate</p></div></section>
    <section data-label="Trust model"><div class="slide slide--dark"><h2>AI đề xuất; constraint và validator giữ kế hoạch khả thi</h2><p>pass · fail · unknown</p></div></section>
    <section data-label="Architecture"><div class="slide"><h2>Kiến trúc tách tri thức địa điểm khỏi từng chuyến đi</h2><p>Corpus → Trip → Decision → Planning</p></div></section>
    <section data-label="Evidence"><div class="slide"><h2>Sản phẩm đã chạy trên dữ liệu Đà Lạt thực</h2><p data-anim="zoom-in">1.696 địa điểm</p><p data-anim="zoom-in">28.466 trạng thái VERIFIED</p></div></section>
    <section data-label="User control"><div class="slide"><h2>Người dùng luôn là người quyết định cuối</h2><img src="assets/compare.png" alt="Màn so sánh địa điểm"><img src="assets/plan.png" alt="Màn lịch trình"></div></section>
    <section data-label="Next step"><div class="slide"><h2>Bước tiếp theo là tăng coverage trước khi mở rộng địa bàn</h2><p>Tăng nhãn · Pilot người dùng · Mở rộng có gate</p></div></section>
    <section data-label="Close"><div class="slide slide--dark"><img src="assets/logo.webp" alt="TripGuardian"><h1>Từ hàng nghìn nơi đến một chuyến đi có thể tin</h1><p>Sẵn sàng demo</p></div></section>
  </deck-stage>
  <script src="deck-stage.js"></script>
</body>
</html>
```

Mở rộng markup tối thiểu ở trên thành bố cục hoàn chỉnh theo bảng sau; giữ nguyên copy bắt buộc và viết mọi item lặp trực tiếp trong HTML:

| Slide | Copy bắt buộc | Hình thức |
|---|---|---|
| 1 | `TripGuardian`, `Chọn đúng nơi trước khi xếp lịch`, `Place intelligence + lập lịch trình cá nhân hóa · Đà Lạt` | Logo + crop landing, tiêu đề lớn |
| 2 | `Người đi du lịch không thiếu gợi ý. Họ thiếu một cách để quyết định.`; ba mảnh `Thông tin rời rạc`, `Đánh đổi khó thấy`, `Tổ hợp có thể bất khả thi` | Ba cột, không card viền trái |
| 3 | `Khám phá trên mạng xã hội`, `Kiểm tra vị trí trên Maps`, `Đọc review để đo trải nghiệm`, `Tự ghép tất cả thành quyết định` | Dòng nguồn dữ liệu hội tụ vào người dùng; footnote nguồn trong `Project_Context.md` |
| 4 | `Tìm kiếm trả thêm lựa chọn`; `Chatbot sinh một lịch nghe hợp lý`; `TripGuardian kiểm tra lựa chọn trước khi xếp lịch` | Bảng ba cột, cột cuối nổi bằng xanh Thông |
| 5 | Ba câu hỏi: `Nơi nào hợp với chuyến đi này?`, `Vì sao chọn nơi này thay vì nơi kia?`, `Các nơi đã chọn có thực sự đi cùng nhau được không?` | Nền tối, ba dòng đánh số |
| 6 | Câu người dùng `3 ngày ở Đà Lạt cho hai người, đi xe máy, thích chill, cà phê, săn mây`; bốn bước `Hiểu chuyến đi`, `Chọn nơi`, `Kiểm tra khả thi`, `Xếp lịch` | Timeline + screenshot understand |
| 7 | `Đầu vào chuyến đi` → `Place Intelligence` + `Trip Understanding` → `Place Decision` → `Giải thích & bất định` → `Planning & Validation`; đầu ra `Ít di chuyển`, `Cân bằng trải nghiệm`, `Có dự phòng`; footer `Con người quyết định cuối` | Sơ đồ khối–mũi tên giống logic ảnh tham chiếu; 6–10 build animation tuần tự |
| 8 | `Fact`: giờ, giá, đóng cửa; `Signal`: đông, yên tĩnh, view; `Estimate`: thời gian tham quan, effort; `Mọi nhận định cách bằng chứng một chạm` | Ba tầng bằng chứng + nguồn Maps/TikTok tách màu |
| 9 | `pass · fail · unknown`; `unknown không bị biến thành false`; `Physical constraint không có đường code nới`; `AI đề xuất — validator chốt khả thi` | Nền tối, ba trạng thái và guard rail |
| 10 | `Offline ghi Place Intelligence`; `Online chỉ đọc tri thức địa điểm`; bốn module `Corpus`, `Trip`, `Decision`, `Planning`; `Live context chỉ thuộc request hiện tại` | Kiến trúc bốn tầng, connector một chiều |
| 11 | Bốn số lấy từ JSON: địa điểm, VERIFIED, 30 chuyến ẩn / 96,7%, 0 hard violation / 273 ms; ghi ngày build | Bốn số lớn; 2–4 build animation theo nhóm |
| 12 | `Mình ghi lại điều bạn nói`, `Chỉ hiện khác biệt để dễ chọn`, `Cảnh báo nằm ngay tại quyết định`, `Không lặng lẽ bỏ nơi người dùng đã chọn` | Ba screenshot thật, caption ngắn |
| 13 | `Tăng coverage cho giá trị phủ định`, `Pilot với người tự lên chuyến 2–4 ngày`, `Mở rộng từng thành phố sau khi gate dữ liệu đạt` | Ba bước thẳng, nêu giới hạn minh bạch |
| 14 | `TripGuardian`, `Từ hàng nghìn nơi đến một chuyến đi có thể tin`, `Sẵn sàng demo` | Nền tối, logo, CTA tối giản |

- [ ] **Step 3: Chạy validator và sửa cho đến khi pass**

Run:

```bash
node designs/tripguardian-pitch/scripts/validate-deck.mjs "designs/tripguardian-pitch/TripGuardian Pitch.html"
```

Expected: validator báo 14 slide, từ 8 đến 18 animation và chỉ dùng ảnh local.

- [ ] **Step 4: Kiểm tra title sequence trong HTML khớp scratchpad**

Run:

```bash
rg -o '<h2[^>]*>[^<]+' "designs/tripguardian-pitch/TripGuardian Pitch.html"
```

Expected: slide 2–13 theo đúng thứ tự trong `scratchpad.md`; cover và close dùng `h1`.

- [ ] **Step 5: Commit deck source**

Run:

```bash
git add "designs/tripguardian-pitch/TripGuardian Pitch.html"
git commit --only "designs/tripguardian-pitch/TripGuardian Pitch.html" -m "feat: author TripGuardian pitch deck"
```

Expected: commit chỉ chứa file HTML.

### Task 3: Browser QA và sửa bố cục

**Files:**
- Create: `designs/tripguardian-pitch/scripts/capture-deck.mjs`
- Create: `designs/tripguardian-pitch/shots/slide-01.png` đến `designs/tripguardian-pitch/shots/slide-14.png`
- Modify: `designs/tripguardian-pitch/TripGuardian Pitch.html`

**Interfaces:**
- Consumes: URL `http://127.0.0.1:4311/tripguardian-pitch/TripGuardian%20Pitch.html` và Chromium `.cache/ms-playwright/chromium-1169/chrome-linux/chrome`.
- Produces: 14 screenshot 1920 × 1080 và deck không lỗi console/layout.

- [ ] **Step 1: Viết script capture có kiểm tra console và overflow**

Create `scripts/capture-deck.mjs`:

```js
import { chromium } from "../../../web/node_modules/playwright-core/index.mjs";
import fs from "node:fs/promises";
import path from "node:path";
import { fileURLToPath } from "node:url";

const here = path.dirname(fileURLToPath(import.meta.url));
const project = path.resolve(here, "..");
const browserPath = path.resolve(project, "../../.cache/ms-playwright/chromium-1169/chrome-linux/chrome");
const url = process.argv[2] || "http://127.0.0.1:4311/tripguardian-pitch/TripGuardian%20Pitch.html";
const browser = await chromium.launch({ headless: true, executablePath: browserPath });
const page = await browser.newPage({ viewport: { width: 1920, height: 1080 }, deviceScaleFactor: 1 });
const errors = [];
page.on("console", (msg) => { if (msg.type() === "error") errors.push(msg.text()); });
page.on("pageerror", (err) => errors.push(err.message));
await page.goto(url, { waitUntil: "networkidle" });
await page.evaluate(() => document.querySelector("deck-stage").setAttribute("noscale", ""));
await fs.mkdir(path.join(project, "shots"), { recursive: true });

for (let index = 0; index < 14; index += 1) {
  await page.evaluate((slide) => document.querySelector("deck-stage").goTo(slide), index);
  const target = page.locator("deck-stage > [data-deck-active]");
  const overflow = await target.evaluate((node) => ({
    x: node.scrollWidth > node.clientWidth,
    y: node.scrollHeight > node.clientHeight,
  }));
  if (overflow.x || overflow.y) errors.push(`slide ${index + 1} overflows: ${JSON.stringify(overflow)}`);
  await target.screenshot({ path: path.join(project, "shots", `slide-${String(index + 1).padStart(2, "0")}.png`) });
}

await browser.close();
if (errors.length) {
  console.error(errors.join("\n"));
  process.exit(1);
}
console.log("ok: captured 14 slides without console errors or section overflow");
```

- [ ] **Step 2: Mở HTTP server**

Run trong PTY và giữ session:

```bash
python3 -m http.server 4311 --directory designs
```

Expected: `Serving HTTP on 0.0.0.0 port 4311`.

- [ ] **Step 3: Capture toàn bộ slide**

Run:

```bash
node designs/tripguardian-pitch/scripts/capture-deck.mjs
```

Expected: `ok: captured 14 slides without console errors or section overflow` và đủ 14 PNG.

- [ ] **Step 4: Review ảnh theo nhóm và sửa HTML**

View lần lượt `slide-01.png`–`slide-14.png`. Mỗi slide phải đạt:

- không text tràn/cắt/chồng;
- tiêu đề đọc được ở thumbnail;
- nội dung tập trung ở 2/3 trên, đáy có khoảng thở;
- full-bleed/panel chạm đủ bốn cạnh;
- slide 7 connector không cắt qua chữ;
- slide 12 screenshot dùng `object-fit: contain`, không crop nội dung UI;
- không quá hai nền chính, không accent-border card, không icon/emoji tùy tiện.

Sau mỗi sửa, chạy lại validator và capture đến khi cùng pass.

- [ ] **Step 5: Commit QA script và deck đã chỉnh**

Run:

```bash
git add designs/tripguardian-pitch/scripts/capture-deck.mjs "designs/tripguardian-pitch/TripGuardian Pitch.html"
git commit --only designs/tripguardian-pitch/scripts/capture-deck.mjs "designs/tripguardian-pitch/TripGuardian Pitch.html" -m "fix: polish TripGuardian pitch layouts"
```

Expected: commit chỉ gồm script QA và HTML.

### Task 4: Xuất PowerPoint chỉnh sửa được

**Files:**
- Create: `designs/tripguardian-pitch/pptx.config.json`
- Create: `designs/tripguardian-pitch/TripGuardian-Pitch.pptx`

**Interfaces:**
- Consumes: deck URL qua HTTP, 14 slide selector `deck-stage > [data-deck-active]`, navigation `document.querySelector('deck-stage').goTo(N)`.
- Produces: PPTX 14 slide với native text/shape/image và số animation bằng số phần tử `data-anim`.

- [ ] **Step 1: Viết config export 14 slide**

Create `pptx.config.json`:

```json
{
  "mode": "editable",
  "width": 1920,
  "height": 1080,
  "slides": [
    {"showJs":"document.querySelector('deck-stage').goTo(0)","selector":"deck-stage > [data-deck-active]"},
    {"showJs":"document.querySelector('deck-stage').goTo(1)","selector":"deck-stage > [data-deck-active]"},
    {"showJs":"document.querySelector('deck-stage').goTo(2)","selector":"deck-stage > [data-deck-active]"},
    {"showJs":"document.querySelector('deck-stage').goTo(3)","selector":"deck-stage > [data-deck-active]"},
    {"showJs":"document.querySelector('deck-stage').goTo(4)","selector":"deck-stage > [data-deck-active]"},
    {"showJs":"document.querySelector('deck-stage').goTo(5)","selector":"deck-stage > [data-deck-active]"},
    {"showJs":"document.querySelector('deck-stage').goTo(6)","selector":"deck-stage > [data-deck-active]"},
    {"showJs":"document.querySelector('deck-stage').goTo(7)","selector":"deck-stage > [data-deck-active]"},
    {"showJs":"document.querySelector('deck-stage').goTo(8)","selector":"deck-stage > [data-deck-active]"},
    {"showJs":"document.querySelector('deck-stage').goTo(9)","selector":"deck-stage > [data-deck-active]"},
    {"showJs":"document.querySelector('deck-stage').goTo(10)","selector":"deck-stage > [data-deck-active]"},
    {"showJs":"document.querySelector('deck-stage').goTo(11)","selector":"deck-stage > [data-deck-active]"},
    {"showJs":"document.querySelector('deck-stage').goTo(12)","selector":"deck-stage > [data-deck-active]"},
    {"showJs":"document.querySelector('deck-stage').goTo(13)","selector":"deck-stage > [data-deck-active]"}
  ],
  "resetTransformSelector": "deck-stage",
  "googleFontImports": ["Lora", "Be Vietnam Pro", "JetBrains Mono"],
  "filename": "TripGuardian-Pitch"
}
```

- [ ] **Step 2: Chuẩn bị exporter trong thư mục tạm**

Run:

```bash
cp -R /home/vannk/.codex/skills/baoyu-design/agents/gen-pptx /tmp/tripguardian-gen-pptx
cd /tmp/tripguardian-gen-pptx
npm ci
npx playwright install chromium
npm run build
```

Expected: `/tmp/tripguardian-gen-pptx/dist/cli.mjs` tồn tại. `npm ci` và tải Chromium cần xin quyền network/escalation nếu sandbox chặn.

- [ ] **Step 3: Xuất PPTX editable**

Run từ repo root khi HTTP server còn chạy:

```bash
node /tmp/tripguardian-gen-pptx/dist/cli.mjs --url "http://127.0.0.1:4311/tripguardian-pitch/TripGuardian%20Pitch.html" --config designs/tripguardian-pitch/pptx.config.json --out designs/tripguardian-pitch
```

Expected JSON: `ok=true`, `slides=14`, `animations` bằng kết quả `rg -o 'data-anim="' "designs/tripguardian-pitch/TripGuardian Pitch.html" | wc -l`; chỉ cảnh báo không có speaker notes là hợp lệ.

- [ ] **Step 4: Kiểm tra cấu trúc PPTX**

Run:

```bash
unzip -l designs/tripguardian-pitch/TripGuardian-Pitch.pptx | rg 'ppt/slides/slide[0-9]+\.xml$' | wc -l
unzip -t designs/tripguardian-pitch/TripGuardian-Pitch.pptx
```

Expected: dòng đầu `14`; dòng sau kết thúc bằng `No errors detected`.

- [ ] **Step 5: Commit config và deliverable**

Run:

```bash
git add designs/tripguardian-pitch/pptx.config.json designs/tripguardian-pitch/TripGuardian-Pitch.pptx
git commit --only designs/tripguardian-pitch/pptx.config.json designs/tripguardian-pitch/TripGuardian-Pitch.pptx -m "feat: export editable TripGuardian pitch"
```

Expected: commit chỉ gồm config và PPTX.

### Task 5: Record asset và kiểm chứng bàn giao

**Files:**
- Create: `designs/tripguardian-pitch/_d_meta.json`
- Modify: `designs/tripguardian-pitch/TripGuardian Pitch.html` chỉ khi QA cuối phát hiện lỗi.
- Delete after approval: `docs/superpowers/specs/2026-10-09-tripguardian-pitch-design.md`
- Delete after approval: `docs/superpowers/plans/2026-10-09-tripguardian-pitch.md`

**Interfaces:**
- Consumes: HTML/PPTX đã QA.
- Produces: asset index `needs-review`, URL preview và hai file bàn giao.

- [ ] **Step 1: Record deck trong project metadata**

Run:

```bash
node /home/vannk/.codex/skills/baoyu-design/agents/record-asset.mjs designs/tripguardian-pitch "TripGuardian Pitch.html" --name "TripGuardian Pitch" --subtitle "Deck pitching 15 phút" --status needs-review --width 1920 --height 1080 --section "Pitch deck"
```

Expected: `_d_meta.json` được tạo và asset `TripGuardian Pitch` có path `TripGuardian Pitch.html`.

- [ ] **Step 2: Chạy bộ kiểm chứng cuối**

Run:

```bash
node designs/tripguardian-pitch/scripts/validate-deck.mjs "designs/tripguardian-pitch/TripGuardian Pitch.html"
node designs/tripguardian-pitch/scripts/capture-deck.mjs
unzip -t designs/tripguardian-pitch/TripGuardian-Pitch.pptx
git diff --check -- designs/tripguardian-pitch
```

Expected: validator pass; capture 14 slide pass; PPTX không lỗi; `git diff --check` không có output.

- [ ] **Step 3: Commit metadata**

Run:

```bash
git add designs/tripguardian-pitch/_d_meta.json
git commit --only designs/tripguardian-pitch/_d_meta.json -m "chore: record TripGuardian pitch asset"
```

Expected: commit chỉ gồm `_d_meta.json`.

- [ ] **Step 4: Bàn giao để người dùng review**

Surface:

- HTML: `/workingspace_aiclub/WorkingSpace/Personal/vannk/tripguardian/designs/tripguardian-pitch/TripGuardian Pitch.html`
- URL: `http://127.0.0.1:4311/tripguardian-pitch/TripGuardian%20Pitch.html`
- PPTX: `/workingspace_aiclub/WorkingSpace/Personal/vannk/tripguardian/designs/tripguardian-pitch/TripGuardian-Pitch.pptx`

Không xóa spec/plan ở bước này; chờ người dùng duyệt deck.

- [ ] **Step 5: Sau khi người dùng duyệt, cập nhật trạng thái và dọn tài liệu tạm**

Run:

```bash
node /home/vannk/.codex/skills/baoyu-design/agents/record-asset.mjs designs/tripguardian-pitch "TripGuardian Pitch.html" --name "TripGuardian Pitch" --status approved --width 1920 --height 1080
git add designs/tripguardian-pitch/_d_meta.json docs/superpowers/specs/2026-10-09-tripguardian-pitch-design.md docs/superpowers/plans/2026-10-09-tripguardian-pitch.md
git commit --only designs/tripguardian-pitch/_d_meta.json docs/superpowers/specs/2026-10-09-tripguardian-pitch-design.md docs/superpowers/plans/2026-10-09-tripguardian-pitch.md -m "docs: finalize TripGuardian pitch deck"
```

Expected: asset status `approved`; hai tài liệu làm việc tạm bị xóa theo `RULE.md`; staged state không liên quan vẫn nguyên vẹn.
