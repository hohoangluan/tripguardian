# TripGuardian — Đặc tả UI/UX: Landing

Dành cho designer và người code landing (`/`). Máy tính (laptop, desktop, PC) thấy landing 3D (`web/src/user/screens/Landing.tsx`); điện thoại thấy trang **Dùng ứng dụng** (`web/src/user/screens/GetApp.tsx`, §5) ở mọi trang người dùng — web không có bản cho điện thoại. Hệ màu, chữ: `docs/UI_SPEC_USER_WEB.md` §8 — landing không thêm màu nào ngoài token có sẵn.

Đọc kèm: `docs/UX_Design_Brief.md` (nguyên tắc, cách hiển thị dữ liệu) · `docs/UI_SPEC_USER_WEB.md` (app sau khi bấm `Trải nghiệm đi`).

---

## 1. Nguyên tắc

1. **Landing không giải thích sản phẩm. Nó diễn sản phẩm.** Sân khấu là thung lũng Đà Lạt 3D lúc bình minh, dựng từ địa hình thật, tông hồng nhạt (trắng + hồng phấn + mận) — không khí du lịch, không phải sa bàn hay bản đồ chiến thuật; mỗi chương cuộn đặt cạnh nó một miếng UI thật thu nhỏ (thẻ thông tin chuyến đi, thẻ lý do, timeline, phiếu đánh giá), dùng chung CSS với app nên đổi app thì landing đổi theo.
2. **Ngân sách chữ cứng.** Mỗi chương: 1 nhãn (≤4 từ) + 1 tiêu đề (≤6 từ) + nhiều nhất 1 dòng phụ (≤16 từ).
3. **Thứ gì camera nói được thì không viết.**
4. **Con số và vị trí phải thật.** Số nơi lấy từ `web/src/user/landing/stats.json`; tên, ảnh, độ đông, bình luận, clip từ `places.json`; mỗi đốm sáng trong thung lũng là toạ độ thật của một nơi trong `points.json`. Cả ba sinh bằng `python web/scripts/pick_landing_places.py` từ `snapshot.json` + `covers.json`. Địa hình là thật: độ cao SRTM 30 m (lấy mẫu ~330 m), viền các hồ, đường trục chính, vùng rừng / nhà kính / phố và vị trí nhà từ OpenStreetMap, tải bằng `python web/scripts/export_landscape.py dem | osm | water` ra `web/scripts/landscape/{dem,osm}.json` (nguồn, chỉ dùng khi dựng), rồi dựng sẵn bằng `npm run bake:landscape --prefix web` ra `web/public/world/dalat.bin` (§3). Dữ liệu đã có sẵn trong repo; chỉ chạy lại khi muốn cập nhật bản đồ. Chỉ có **độ phóng đại chiều cao** (×~3 so với tỷ lệ ngang) và chi tiết nhiễu mịn trên lưới 330 m là minh họa; cây thông, mái nhà là biểu tượng, không phải từng cây từng nhà. Footer ghi rõ. Giờ giấc trong chương Lịch trình là minh họa, có tag *"Ví dụ minh họa"*; khoảng cách giữa các nơi tính từ toạ độ thật.

## 2. Cấu trúc (máy tính)

Một section cao ~6,4 màn hình; bên trong là sân khấu `sticky` cao 1 màn hình: canvas 3D (`web/src/user/landing/scene.ts`, địa hình `terrain.ts`), nhãn DOM bám theo bưu thiếp và khu, cột chữ bên trái, thanh bước bên phải. Cuộn kéo một timeline GSAP (`scrub`) đẩy trạng thái cảnh (camera, đốm sáng, bưu thiếp, tuyến) và đổi đoạn. Khung hình luôn lệch phải để chừa cột chữ. **Xoay 360°:** kéo chuột (hoặc ngón tay theo chiều ngang) trên mô hình để xoay cả cảnh quanh thung lũng, kéo dọc để nâng / hạ góc nhìn; thả tay có quán tính; camera không bao giờ chui xuống đất. Cuộn sang chương khác thì mô hình tự về góc nhìn của chương đó. **Khám phá tự do:** nút `Khám phá Đà Lạt 3D` (đoạn Mở đầu) hoặc nút la bàn cạnh ba nút xoay ẩn chữ, dừng cuộn trang và trao camera cho người dùng — kéo để xoay và nghiêng, chuột phải / Shift + kéo / hai ngón để dịch chuyển, cuộn chuột / chụm hai ngón để phóng to thu nhỏ (14–300 đơn vị), phím mũi tên / WASD dịch, `+` `-` zoom, Q E xoay, `Esc` hoặc `Thoát` để về câu chuyện (camera bay về góc của chương đang đứng). Chip `Trung tâm · Langbiang · Hồ Tuyền Lâm · Cầu Đất · Trại Mát` bay tới đúng toạ độ thật. Trong chế độ này hiện đủ nhãn khu, đốm sáng và 5 bưu thiếp; camera không chui xuống đất, tâm nhìn không rời bản đồ. Hướng dẫn: sau 2 giây cảnh tự lắc nhẹ một lần, nhãn `Kéo để xoay 360°` (biểu tượng vòng xoay có chấm trượt) nằm cạnh ba nút nhỏ `‹` `↻` `›` (xoay 45° mỗi lần, về góc ban đầu) — nhãn biến mất khi người dùng xoay lần đầu, ba nút ở lại cho người dùng bàn phím.

**Cảnh:** bầu trời bình minh (hồng phấn → trắng hồng → hồng đào ở chân trời, quầng nắng phía đông), sương nằm trong các lòng chảo thật (phố, Tuyền Lâm, Trại Mát, phía Đa Nhim), đồi thông ba lá hồng mận theo vùng rừng thật, các hồ theo viền thật (mỗi hồ một mực nước), đường trục chính màu trắng kem, phố mái hồng theo vị trí nhà thật, nhà thờ Con Gà, đỉnh Langbiang; địa hình xa mờ dần vào chân trời. Mỗi địa điểm là một đốm sáng vàng nhỏ (màu vàng duy nhất trong cảnh). Năm nơi được chọn là **bưu thiếp** in ảnh thật của nơi đó (thumbnail Google Maps), cắm trên que trắng; tuyến đi là **đường chấm trắng** trên mặt đất. Màu lấy từ token (pine, sun, paper và các tông nhạt).

Thanh bước bên phải theo đúng các bước sản phẩm: **Mở đầu · Tìm hiểu · Lựa chọn · Lịch trình · Đánh giá**. Đoạn lý do thuộc bước Lựa chọn.

| # | Đoạn (bước) | Chữ | Cảnh 3D |
|---|---|---|---|
| 0 | **Mở đầu** | `Hàng nghìn nơi ở Đà Lạt. Chỉ giữ nơi hợp với bạn.` + một dòng thơ + nút `Trải nghiệm đi` + nút `Khám phá Đà Lạt 3D` + dòng số thật | Camera thấp trên đồi phía nam nhìn lên thung lũng, thấy chân trời; đốm sáng hiện dần; nhãn khu (Trung tâm, Langbiang, Cầu Đất, Trại Mát, Tuyền Lâm); sương trôi; camera thở nhẹ và nghiêng theo chuột |
| 1 | **Tìm hiểu** | `Tách rõ điều bắt buộc và điều mong muốn.` + thẻ Thông tin chuyến đi | Camera lượn sang phía tây phố; con dấu `Bắt buộc` bay vào từ trái, chip `Mong muốn` viền đứt từ phải |
| 2 | **Lựa chọn** | `Còn lại <số đếm thật → 5> nơi hợp với bạn.` | Camera lên cao; đốm sáng mờ dần, 5 bưu thiếp mọc lên có nhãn số + tên, đường chấm vẽ dần |
| 3 | **Lựa chọn · lý do** | `Chọn nơi nào cũng có lý do.` + thẻ nơi | Camera bay ngang tầm bưu thiếp Thênh Thang; thanh độ đông chạy tới số thật, clip TikTok thật (bấm để mở), một bình luận Google gốc |
| 4 | **Lịch trình** | `Một ngày đi kịp từng điểm.` + timeline + `Đã kiểm tra` | Camera lùi ra cả tuyến; một chấm cam chạy dọc đường chấm theo cuộn |
| 5 | **Đánh giá** | `Chuyến sau hợp gu hơn chuyến này.` + 4 câu của màn Phản hồi (thang 5 chấm, giá trị minh họa) + `Lên lịch cho chuyến của bạn` | Camera nâng lên nhìn lại thung lũng về phía bình minh, cả tuyến và năm bưu thiếp |

Thứ tự đi theo luồng sản phẩm: tìm hiểu chuyến đi → lựa chọn (kèm lý do) → lịch trình → đánh giá sau chuyến (`web/src/user/screens/Done.tsx`).

**Giọng văn:** landing gọi sản phẩm là "TripGuardian" và người đọc là "bạn" (không dùng "mình" để khỏi lẫn ai đang nói). Câu hỏi trong Hỏi nhanh viết bằng giọng người dùng (`TripGuardian có quyết định thay tôi không?`).

**Chữ:** landing dùng Lora (tiêu đề, bộ dấu tiếng Việt đầy đủ, cân ở cỡ lớn) + Be Vietnam Pro (thân bài, thiết kế riêng cho tiếng Việt); ghi đè `--tg-display`, `--tg-sans` trên `.tg-landing`, màu giữ nguyên token. Số dùng chữ số đều (`tabular-nums`) thay cho phông mono.

Sau sân khấu, trang giấy thường: **Ảnh thật** (bento 6 nơi thật, mỗi ô ghi tên + `Ảnh: Google Maps`) → **Hỏi nhanh** cạnh **Sắp có** (`chưa mở`) → CTA cuối → footer.

Điều hướng: thanh trên có `Cách hoạt động` · `Ảnh thật` · `Hỏi nhanh` (cuộn tới chỗ), `Đăng nhập`, `Trải nghiệm đi`. Thanh bước bên phải (5 chấm, nhãn hiện khi trỏ / đang ở) bấm được để nhảy tới bước. Nút `Cuộn để xem cách hoạt động` ẩn khi rời Mở đầu.

Landing không có ô nhập. Mọi nút `Trải nghiệm đi` (thanh trên, Mở đầu, đoạn Đánh giá, CTA cuối) chỉ chuyển sang trang home `/app` (Khám phá); câu hỏi chỉ bắt đầu ở đó, khi người dùng kể chuyến đi.

## 3. Animation và hiệu năng

**Chuyển động**
- **Chữ vừa màn hình:** mỗi chương tự thu nhỏ (`zoom`, tối thiểu 0,6) nếu cao hơn khung nhìn trừ 150 px; cỡ chữ tiêu đề theo cả `vh`, nên cửa sổ laptop thấp (~700 px) không bị cắt chữ. Mỗi chương nhiều nhất một dòng phụ.
- **Sang trang home:** bấm `Trải nghiệm đi` thì chữ nhấc lên và mờ, thung lũng phóng nhẹ (~0,4 s), rồi trình duyệt chuyển mờ dần sang `/app` bằng View Transitions (`startViewTransition` + `flushSync`, 0,5 s); trình duyệt không có thì chuyển thẳng. Giảm chuyển động: chuyển thẳng, không hiệu ứng.
- **Gợi ý cuộn:** ở mọi chương có một nút nổi ở chân sân khấu nói rõ còn gì ở dưới (`Cuộn để xem cách hoạt động` → `Cuộn tiếp: Lựa chọn` → … → `Còn nữa bên dưới: ảnh thật`), bấm là nhảy tới chương kế; cuối phần Ảnh thật và Hỏi nhanh có nút `Còn nữa: …` dẫn xuống phần sau.
- Mọi chuyển động dẫn bằng cuộn (`scrub` + Lenis); mỗi chương đủ hình trước khi tới điểm dừng của nó và giữ một nhịp trước khi đổi.
- Cảnh 3D tự làm mượt theo thời gian thực (không phụ thuộc FPS), chỉ vẽ khi sân khấu trong màn hình và tab đang mở.
- `prefers-reduced-motion: reduce`: không Lenis, không timeline; cảnh vẽ một khung tĩnh kể trọn câu chuyện (góc nhìn đoạn Đánh giá: đốm mờ + 5 bưu thiếp + tuyến), các đoạn 1–5 xếp lưới bên dưới ở trạng thái cuối.
- Nhãn không bao giờ nằm dưới cột chữ hay sát mép khung.
- Cửa sổ máy tính hẹp hơn 900px: chữ thành thẻ nền giấy ở đáy sân khấu, ẩn thanh bước.

**Máy không có GPU** (không WebGL, hoặc trình vẽ phần mềm như SwiftShader / llvmpipe / Microsoft Basic Render, phát hiện trong `index.html` trước khi tải gì): trang chạy **bản nhẹ** — không tải three.js và dữ liệu địa hình, sân khấu hiện 6 ảnh chụp từ chính mô hình 3D (`landing-poster.webp`, `landing-p1..p5.webp`, ~90 KB mỗi ảnh, tạo bằng `web/scripts/shots_plates.mjs`) đổi mờ dần theo chương kèm một chuyển động trôi chậm; chữ, cuộn, gợi ý và nút `Trải nghiệm đi` giữ nguyên, nút xoay / khám phá ẩn. Máy chỉ có phần mềm vẽ được hiện thêm nút `Thử bản 3D` (`?3d=on`). Máy có GPU nhưng quá yếu: bộ tự hạ chất lượng (mục 6) đã hết nấc mà vẫn chậm thì tự chuyển sang bản nhẹ. `?3d=off` buộc bản nhẹ, `?3d=on` buộc 3D (dùng khi kiểm thử).

**Vào trang nhanh, không giật** (máy tính; điện thoại và `/app/...` không tải gì của landing)
1. **Ảnh nền có ngay:** `index.html` cho `html.tg-boot #root:empty` nền là `web/public/img/landing-poster.webp` (~70 KB, chụp từ chính cảnh 3D ở góc nhìn đầu, không chữ) và preload nó, nên trang không trắng trong lúc mã tải. Sân khấu giữ ảnh này (`.tg-l3__poster`), cảnh 3D mờ dần chồng lên sau khung hình đầu tiên (`is-live`). Không có WebGL: ảnh nền ở lại, các nút xoay ẩn.
2. **Tải song song:** `index.html` bắt đầu tải `/world/dalat.bin` ngay; `App.tsx` bắt đầu tải chunk `scene` và `points.json` ngay từ chunk vào, không chờ `UserApp`. Dữ liệu `covers.json` / snapshot (2,8 MB) chỉ tải sau khi cảnh đã vẽ, để không tranh băng thông.
3. **Địa hình dựng sẵn:** mọi phép tính nặng (độ cao 122 nghìn đỉnh, màu theo lớp phủ, 15 nghìn cây, 3 nghìn nhà, đường, tam giác hóa mặt hồ) chạy ngoại tuyến trong `web/scripts/landscape/bake.ts` (xác định, có hạt giống) ra một tệp nhị phân ~740 KB (~240 KB brotli); trình duyệt chỉ giải mã mảng (`landing/terrain.ts`, ~150 ms trên máy thử thay cho ~2 s trước đây). Độ cao và màu lưu theo bước chênh với đỉnh kề; cỡ, hướng xoay cây / nhà sinh bằng bộ số ngẫu nhiên có hạt giống, không lưu. Đổi bảng màu hay dữ liệu thì chạy lại `npm run bake:landscape`.
4. **Bóng đổ vẽ một lần** (`shadowMap.autoUpdate = false`): thung lũng không đổi; tuyến đi không đổ bóng.
5. **Biên dịch shader không chặn trang:** `compileAsync` trước khung đầu tiên (trình duyệt có `KHR_parallel_shader_compile`).
6. **Tự hạ chất lượng khi máy yếu** (`DalatScene.govern`): sau 30 khung khởi động, nếu khung trung bình > 28 ms kéo dài, giảm lần lượt: độ phân giải về 1x, tắt cánh hoa / tia sáng / đom đóm, bớt một nửa cây; không bao giờ tăng lại. Màn hình ≥ 2x không bật khử răng cưa; độ phân giải tối đa 1,5x.
7. Tệp `/world/*`, `/img/*` được lưu đệm 1 ngày; `.bin` có sẵn bản `.br` / `.gz` (`web/scripts/prod_assets.mjs`). Phông chữ Google không chặn lần vẽ đầu (`media="print"` rồi đổi sang `all`).
8. Đo: `performance.mark` `tg-scene-start`, `tg-build:<bước>`, `tg-scene-built`, `tg-scene-first-frame` (bảng Performance của Chrome). Ngân sách: ảnh nền hiện < 1 s, cảnh 3D sẵn sàng < 3 s trên laptop trung bình, khung hình ổn định 50–60 FPS.

## 4. Ảnh

Ảnh nền CTA là ảnh sinh (`web/public/img/gen/`, `web/scripts/gen_ui_images.py`, prompt ở `web/scripts/ui_image_prompts.json`, nguồn gốc ghi trong `manifest.json`). Ảnh nền landing (`landing-poster.webp`, §3) là ảnh chụp từ chính mô hình 3D; chụp lại bằng Playwright mỗi khi đổi cảnh. Ảnh sinh chỉ dùng cho không khí, không bao giờ đại diện một nơi có tên; ảnh một nơi có thật luôn là ảnh Google Maps / frame clip.

## 5. Điện thoại: Dùng ứng dụng

Điện thoại (UA di động, hoặc màn chỉ cảm ứng có cạnh ngắn < 600px — `web/src/user/landing/device.ts`) vào bất kỳ trang người dùng nào (`/`, `/app/...`, kể cả link được chia sẻ) đều thấy trang Dùng ứng dụng; không có lối vào bản web. `/admin` không đổi.

- Minh họa điện thoại (ảnh nền + 3 ghim + tuyến + `Lịch sẵn sàng`), nhãn `Trên điện thoại`, tiêu đề `Tải ứng dụng để dùng TripGuardian trên điện thoại.`
- Hai nút cửa hàng, nền tảng của máy đứng trước. Link lấy từ biến build `VITE_APP_IOS_URL`, `VITE_APP_ANDROID_URL` (`web/.env`):
  - có link: nút `Tải trên App Store / Google Play` mở cửa hàng;
  - chưa có: ô viền đứt `Sắp có trên …` + tag `chưa mở`, dòng phụ `Ứng dụng sẽ có trong thời gian tới. Hiện tại, bạn mở TripGuardian trên máy tính để có trải nghiệm tốt nhất.`
- `Gửi link sang máy tính`: chia sẻ đúng trang đang mở (link chuyến, link một nơi) qua bảng chia sẻ của máy, không có thì chép link và báo `Đã chép link…`.
