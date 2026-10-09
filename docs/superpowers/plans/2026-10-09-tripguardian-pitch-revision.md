# TripGuardian Pitch Deck Revision Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Chỉnh toàn bộ deck TripGuardian thành 15 slide trình bày và một slide phụ lục, làm rõ luồng đối thủ, ranh giới claim, cơ chế quyết định, bằng chứng nội bộ và xuất lại PowerPoint editable với bộ font local đi kèm.

**Architecture:** Deck vẫn là HTML tĩnh 1920 × 1080 dùng `deck-stage.js`; mọi chữ, shape và connector quan trọng là phần tử HTML để exporter giữ khả năng chỉnh sửa. Font thương hiệu được đóng gói local và nạp bằng `@font-face`; validator kiểm tra contract 16 slide, nội dung bắt buộc và cấm tài nguyên từ xa; Playwright chụp từng slide và LibreOffice render lại PPTX trong fontconfig trỏ vào bộ font local.

**Tech Stack:** HTML5, CSS, vanilla JavaScript, `deck-stage.js`, Node.js, `playwright-core`, Chromium, Google Fonts TTF/OFL, `baoyu-design` exporter `gen-pptx`, LibreOffice headless, Poppler.

## Global Constraints

- Nội dung tài liệu và slide viết tiếng Việt; code, comment, identifier và tên file viết tiếng Anh.
- Deck có đúng 16 slide: 15 slide chính và một phụ lục A1; phần chính dài khoảng 14 phút 35 giây.
- Slide 4 phải có Google Maps, Traveloka, Wanderlog, Tripadvisor AI, Mindtrip và Layla, chỉ dựa trên tài liệu công khai.
- Không tuyên bố độc quyền, benchmark chất lượng, traction, tác động người dùng hoặc dữ liệu thị trường chưa có bằng chứng.
- Phải ghi rõ 30 Trip State là mô phỏng offline, không phải 30 người dùng hay 30 chuyến thực địa.
- Font giữ nguyên Lora, Be Vietnam Pro và JetBrains Mono; không thay bằng Arial; HTML không gọi Google Fonts.
- Mọi font hiển thị trên slide tối thiểu 24 px; tiêu đề tối thiểu 48 px.
- Cover dùng `web/public/img/landing-poster.webp`, không dùng screenshot landing có chữ/nút làm nền.
- PPTX có 16 slide, text/shape editable; exporter không nhúng font nên bundle phải có TTF, OFL và hướng dẫn cài font.
- Không sửa code sản phẩm ngoài `designs/tripguardian-pitch/` và hai tài liệu spec/plan liên quan.
- Worktree có thay đổi của người dùng; mọi commit dùng `git commit --only` với đường dẫn tường minh.

---

## File Structure

```text
designs/tripguardian-pitch/
├── TripGuardian Pitch.html        # deck 16 slide, copy và CSS hoàn chỉnh
├── TripGuardian-Pitch.pptx        # PowerPoint editable đã export lại
├── scratchpad.md                  # title sequence, timing, nguồn và ranh giới claim
├── pptx.config.json               # cấu hình export 16 slide
├── _d_meta.json                   # metadata asset sau record
├── assets/
│   ├── landing-poster.webp        # cover không có lớp UI
│   ├── logo.webp
│   ├── understand.png
│   ├── compare.png
│   └── plan.png
├── fonts/
│   ├── Lora-Regular.ttf
│   ├── Lora-SemiBold.ttf
│   ├── BeVietnamPro-Regular.ttf
│   ├── BeVietnamPro-Medium.ttf
│   ├── BeVietnamPro-SemiBold.ttf
│   ├── BeVietnamPro-Bold.ttf
│   ├── JetBrainsMono-Medium.ttf
│   ├── JetBrainsMono-Bold.ttf
│   ├── OFL-Lora.txt
│   ├── OFL-BeVietnamPro.txt
│   ├── OFL-JetBrainsMono.txt
│   └── README.md
├── scripts/
│   ├── validate-deck.mjs          # contract 16 slide và content assertions
│   └── capture-deck.mjs           # chụp số slide động
└── shots/                          # ảnh QA browser, không dùng làm slide
```

### Task 1: Bundle font và cover đúng

**Files:**
- Create: `designs/tripguardian-pitch/fonts/*.ttf`
- Create: `designs/tripguardian-pitch/fonts/OFL-*.txt`
- Create: `designs/tripguardian-pitch/fonts/README.md`
- Create: `designs/tripguardian-pitch/assets/landing-poster.webp`

**Interfaces:**
- Consumes: Google Fonts repository files and `web/public/img/landing-poster.webp`.
- Produces: các đường dẫn local dùng trực tiếp bởi `@font-face` và bộ font người nhận có thể cài trước khi mở PPTX.

- [ ] **Step 1: Tải đúng static TTF và OFL từ Google Fonts**

Run eight `curl -fL` commands for the TTF files and three commands for the OFL files against `raw.githubusercontent.com/google/fonts/main/ofl/{lora,bevietnampro,jetbrainsmono}/...`; save them with the filenames listed in File Structure.

Expected: all downloads return HTTP success; no HTML error page is saved as `.ttf`.

- [ ] **Step 2: Kiểm tra font binary**

Run:

```bash
file designs/tripguardian-pitch/fonts/*.ttf
fc-scan --format '%{family}\t%{style}\n' designs/tripguardian-pitch/fonts/*.ttf
```

Expected: mỗi file là TrueType font; family names are `Lora`, `Be Vietnam Pro`, and `JetBrains Mono` with the requested styles.

- [ ] **Step 3: Viết hướng dẫn cài font**

Create `fonts/README.md` stating that PowerPoint export references but does not embed fonts, and giving install steps for Windows, macOS, and Linux. State that the HTML deck needs no installation because it loads local font files.

- [ ] **Step 4: Sao chép cover sạch**

Run:

```bash
cp web/public/img/landing-poster.webp designs/tripguardian-pitch/assets/landing-poster.webp
```

Expected: the copied image is readable and has the same checksum as the source.

- [ ] **Step 5: Commit font bundle and cover**

Run `git commit --only` for `designs/tripguardian-pitch/fonts` and `designs/tripguardian-pitch/assets/landing-poster.webp` with message `feat: bundle TripGuardian pitch fonts`.

### Task 2: Strengthen the static contract before authoring

**Files:**
- Modify: `designs/tripguardian-pitch/scripts/validate-deck.mjs`
- Modify: `designs/tripguardian-pitch/scripts/capture-deck.mjs`
- Modify: `designs/tripguardian-pitch/scratchpad.md`

**Interfaces:**
- Consumes: existing HTML file.
- Produces: validator exit 1 when slide count/content/font rules are stale, and capture output for however many slide sections exist.

- [ ] **Step 1: Update validator expectations**

Set expected slide count and unique label count to 16. Add assertions that the HTML contains `Layla`, `Trip State mô phỏng offline`, `Planning & Validation`, and the public-source disclaimer; reject `fonts.googleapis.com`, remote image references, speaker notes, and pixel font sizes below 24.

- [ ] **Step 2: Run validator against current deck and observe failure**

Run:

```bash
node designs/tripguardian-pitch/scripts/validate-deck.mjs "designs/tripguardian-pitch/TripGuardian Pitch.html"
```

Expected: exit 1 with at least `expected 16 slides`, missing Layla, and remote font errors.

- [ ] **Step 3: Make capture count dynamic**

Replace the hard-coded loop bound with:

```js
const slideCount = await page.locator("deck-stage > section[data-label]").count();
for (let index = 0; index < slideCount; index += 1) {
  // Preserve existing navigation and screenshot behavior.
}
```

Expected: script names outputs `slide-01.png` through the last discovered slide.

- [ ] **Step 4: Rewrite scratchpad**

List the exact 16 titles from the revised spec, timing for slides 1–15, competitor primary-source URLs including Layla, the Vietnam survey source, internal data files, and the distinction between implemented, offline-evaluated, and unproven claims.

### Task 3: Re-author the 16-slide HTML deck

**Files:**
- Modify: `designs/tripguardian-pitch/TripGuardian Pitch.html`

**Interfaces:**
- Consumes: local assets/fonts, revised spec, current JSON metrics, and public-source claim boundaries.
- Produces: exactly 16 direct child `<section data-label>` elements under `<deck-stage width="1920" height="1080">`.

- [ ] **Step 1: Replace remote font loading with local font faces**

Define `@font-face` declarations for every TTF in `fonts/`; preserve the CSS families `Lora`, `Be Vietnam Pro`, and `JetBrains Mono`. Remove all Google Fonts `link`, `preconnect`, and `@import` declarations.

- [ ] **Step 2: Rewrite slides 1–5 around the listener's decision**

Author cover with `assets/landing-poster.webp`; add a concrete infeasible-choice example to slide 2; make slide 3 conclude that the traveler still integrates sources manually; render slide 4 as a two-column × three-row grid for Google Maps, Traveloka, Wanderlog, Tripadvisor AI, Mindtrip, and Layla; render slide 5 as the common journey `Khám phá → Lưu/thu hẹp → Kiểm tra tập đã chọn → Xếp lịch → Đặt dịch vụ/điều hướng` with the required public-source disclaimer.

- [ ] **Step 3: Rewrite slides 6–10 around the mechanism**

Slide 6 states the three decision questions and the claim boundary. Slide 7 annotates the real UI journey. Slide 8 uses a left-to-right flow `Trip State → Evidence → Decision → Planning & Validation`, with a visible explain/unknown branch and three trade-off outputs. Slide 9 separates evidence type from its decision rule. Slide 10 uses concrete pass/fail/unknown cases, including a closed-place failure and missing-opening-hours unknown.

- [ ] **Step 4: Rewrite slides 11–16 around feasibility and proof**

Slide 11 adds each module's output contract and the offline-write/online-read boundary. Slide 12 splits real Da Lat place data from 30 simulated offline Trip States and explicitly says one scenario did not fill all eight places. Slide 13 explains fail-closed behavior and recovery. Slide 14 separates implemented, offline-evaluated, and not-yet-proven claims. Slide 15 closes. Slide 16 records public sources, internal evidence, access date, and comparison boundaries.

- [ ] **Step 5: Run static validation**

Run the validator again.

Expected: `ok: 16 slides`, all images local, no font under 24 px, no remote fonts, and an animation count within the configured meaningful-build range.

- [ ] **Step 6: Commit authored deck and QA scripts**

Use `git commit --only` for HTML, scratchpad, validator, and capture script with message `feat: strengthen TripGuardian pitch narrative`.

### Task 4: Browser visual QA and layout correction

**Files:**
- Modify if needed: `designs/tripguardian-pitch/TripGuardian Pitch.html`
- Generate: `designs/tripguardian-pitch/shots/slide-01.png` through `slide-16.png`

**Interfaces:**
- Consumes: validated HTML through a local HTTP server.
- Produces: screenshots at 1920 × 1080 with no overflow, clipping, collision, ghost text, or unreadable connector.

- [ ] **Step 1: Serve and capture**

Serve `designs` on port 4311 and run `capture-deck.mjs` with the existing Chromium binary.

Expected: 16 screenshots and no browser console errors.

- [ ] **Step 2: Inspect every slide at full size and thumbnail**

Check especially slide 4 density, slide 5 journey mapping, slide 8 connectors, slide 12 evidence distinction, slide 13 fail-closed explanation, and slide 16 sources. Verify the cover has no ghost UI.

- [ ] **Step 3: Correct issues and recapture**

Make only HTML/CSS changes that preserve the static structure and 24 px minimum. Re-run validator and capture until all 16 slides pass visual inspection.

### Task 5: Export and inspect editable PowerPoint

**Files:**
- Modify: `designs/tripguardian-pitch/pptx.config.json`
- Modify: `designs/tripguardian-pitch/TripGuardian-Pitch.pptx`
- Modify: `designs/tripguardian-pitch/_d_meta.json`

**Interfaces:**
- Consumes: final 16-slide deck URL and local font family names.
- Produces: a 16-slide PPTX retaining editable text/shapes and animation metadata.

- [ ] **Step 1: Update exporter config**

Set title, source URL, output path, and any slide-count metadata for 16 slides. Remove remote Google Font imports; keep explicit font-family mapping to Lora, Be Vietnam Pro, and JetBrains Mono.

- [ ] **Step 2: Export PPTX**

Run the existing built `gen-pptx` CLI against `http://127.0.0.1:4311/tripguardian-pitch/TripGuardian%20Pitch.html` and `pptx.config.json`.

Expected: export succeeds with 16 slides; the only acceptable warning is absence of speaker notes.

- [ ] **Step 3: Verify package structure**

Run:

```bash
unzip -t designs/tripguardian-pitch/TripGuardian-Pitch.pptx
unzip -l designs/tripguardian-pitch/TripGuardian-Pitch.pptx | rg 'ppt/slides/slide[0-9]+\.xml$' | wc -l
```

Expected: archive test passes and slide count is 16. Inspect XML to confirm the three font family names and native text/shape objects are present.

- [ ] **Step 4: Render PPTX with local fonts**

Create a temporary fontconfig that includes `/usr/share/fonts` and `designs/tripguardian-pitch/fonts`, run LibreOffice headless with a temporary user profile, convert to PDF, then render the PDF pages with `pdftoppm`.

Expected: 16 pages; no substitution to DejaVu for Lora, Be Vietnam Pro, or JetBrains Mono; no clipped or overlapping text.

- [ ] **Step 5: Record the final asset and commit**

Run the baoyu-design `record-asset.mjs` helper for the deck folder. Commit `pptx.config.json`, `TripGuardian-Pitch.pptx`, and `_d_meta.json` with `git commit --only` and message `feat: export revised editable TripGuardian pitch`.

### Task 6: Final verification

**Files:**
- Verify only; no expected product-code edits.

**Interfaces:**
- Consumes: committed deck source, font bundle, PPTX, screenshots, and repo state.
- Produces: evidence that the deliverables satisfy the revised spec without including unrelated user changes.

- [ ] **Step 1: Run all deck checks fresh**

Run validator, capture, PPTX archive test, slide-count check, font scan, and LibreOffice render again from the committed state.

- [ ] **Step 2: Build the existing web app**

Run the existing production build command from `web/` to ensure copied assets and deck changes did not disturb the product workspace.

- [ ] **Step 3: Review final diff and commit scope**

Use `git status --short` and `git diff --check`. Confirm deck commits contain only the exact spec, plan, and `designs/tripguardian-pitch/` files; leave all unrelated working-tree changes untouched.

- [ ] **Step 4: Deliver file links and verified limitations**

Report the HTML, PPTX, font README, and design spec. State that fonts must be installed before opening PPTX, that competitor comparison is positioning from public documentation rather than a benchmark, and that current evaluation is offline simulation rather than user evidence.
