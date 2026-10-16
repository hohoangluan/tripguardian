# TripGuardian — Đặc tả UI/UX: Landing

Dành cho designer và người code landing (`/`). Máy tính (laptop, desktop, PC) thấy landing bản đồ hành trình sống (`web/src/user/screens/Landing.tsx`); điện thoại thấy trang **Dùng ứng dụng** (`web/src/user/screens/GetApp.tsx`, §5) ở mọi trang người dùng — web không có bản cho điện thoại. Hệ màu, chữ: `docs/UI_SPEC_USER_WEB.md` §8 — landing dùng đúng token và chữ của app (trắng–đen, Be Vietnam Pro), điểm nhấn đất nung `--tg-brand`.

Đọc kèm: `docs/UX_Design_Brief.md` (nguyên tắc, cách hiển thị dữ liệu) · `docs/UI_SPEC_USER_WEB.md` (app sau khi bấm `Lên lịch chuyến của bạn`).

---

## 1. Nguyên tắc

1. **Một câu cho cả trang:** kể chuyến đi trong khoảng 2 phút → nhận lịch Đà Lạt từng giờ, chỉ gồm nơi có thật, có lý do và điều cần biết. Khối nào không phục vụ câu này thì không có trên trang.
2. **Landing diễn sản phẩm, không giải thích.** Sân khấu là **bản đồ hành trình Đà Lạt sống**: tờ bản đồ giấy kem vẽ từ dữ liệu thật, yên và ít chi tiết, với **linh vật đám mây TripGuardian** (logo) bay to ở tiền cảnh dẫn người xem qua từng bước — nền lặng, nhân vật nổi, như video mẫu cá bơi (2026-10-15). Màu trời đổi theo giờ của ngày ví dụ, nên màu là đồng hồ của chuyến đi. Các phần sau là trang giấy thường; mỗi bước đặt cạnh chữ một miếng UI thật thu nhỏ (chat và thẻ chuyến đi, thẻ lý do, timeline), dùng chung CSS với app nên đổi app thì landing đổi theo.
3. **Ngân sách chữ:** mỗi bước có 1 nhãn (≤4 từ), 1 tiêu đề (≤2 câu), 1 đoạn phụ (≤2 câu). Một CTA duy nhất, lặp lại ở thanh trên, màn đầu và hộp cuối: `Lên lịch chuyến của bạn`.
4. **Con số và vị trí phải thật.** Số nơi lấy từ `web/src/user/landing/stats.json`; tên, ảnh, đánh giá, độ đông, clip từ `places.json`; mỗi đốm vàng trên bản đồ là toạ độ thật của một nơi trong `points.json`. Cả ba sinh bằng `python web/scripts/pick_landing_places.py` từ `snapshot.json` + `covers.json`. Địa hình là thật: độ cao SRTM 30 m (lấy mẫu ~330 m), viền các hồ, đường trục chính, vùng rừng / nhà kính / phố và vị trí nhà từ OpenStreetMap, tải bằng `python web/scripts/export_landscape.py dem | osm | water` ra `web/scripts/landscape/{dem,osm}.json` (nguồn, chỉ dùng khi dựng), rồi dựng sẵn bằng `npm run bake:landscape --prefix web` ra `web/public/world/dalat.bin` (§3). Dữ liệu đã có sẵn trong repo; chỉ chạy lại khi muốn cập nhật bản đồ. Bản đồ vẽ phẳng: lớp phủ (rừng, ruộng / nhà kính, phố) và dải độ cao được pha nhạt vào màu giấy, độ cao hiện bằng đường đồng mức (100 m, đậm hơn mỗi 500 m). Footer ghi rõ nguồn. Ngày ví dụ ở bước Lịch trình có tag *"Ví dụ minh họa"*: giờ đến và thời gian ở lại là minh họa, phút đi xe giữa hai nơi là ước tính thô từ toạ độ thật (cùng `road_factor`, `rough_speed_kmh` của `config/planning.yaml`), tên nơi là thật.
5. **Lời hứa về tài khoản phải đúng với `/app`:** khách vào được ngay (`docs/ACCOUNTS.md` §7), nên landing nói "Không cần tài khoản" và luôn kèm đường lưu chuyến ("Đăng nhập Google để lưu chuyến").

## 2. Cấu trúc (máy tính)

Thanh trên cố định (`Cách hoạt động` · `Địa điểm` · `Hỏi nhanh`, `Đăng nhập`, `Lên lịch chuyến của bạn`), rồi các phần theo thứ tự:

| Phần | Nội dung |
|---|---|
| **Màn đầu** | Bản đồ sống (`web/src/user/landing/scene.ts`, dữ liệu `terrain.ts`, linh vật `mascot.ts`) cao `min(100vh, 900px)`, chữ bên trái, khung lệch phải để chừa cột chữ. Nhãn `TripGuardian · Đà Lạt`, tiêu đề `Lịch trình Đà Lạt vừa với bạn.`, một câu phụ có số nơi thật, nút `Lên lịch chuyến của bạn`, link `Xem cách hoạt động`, ba cam kết (`Miễn phí` · `Không cần tài khoản` · `Chỉ gồm nơi có thật`). Góc phải dưới: nút `Khám phá bản đồ Đà Lạt` kèm lời giải thích hiện sẵn. Chân màn: nút nổi `Cuộn xuống để xem cách hoạt động` (mũi tên nhấp nhô, bấm để tới bước đầu) |
| **Tìm hiểu** | `Cứ kể như kể với bạn đi cùng.` Một lời kể của người dùng (bong bóng `Bạn`, các cụm được hiểu tô nền đất nung nhạt) và ghi chú `TripGuardian ghi lại` có avatar linh vật: `2 người · 3 ngày · xe máy`, `Phải giữ` (con dấu khóa), `Có thì vui` (chip viền đứt) |
| **Lựa chọn** | `Còn 6 chỗ hợp với bạn.` (số đếm lùi từ tổng số chỗ) + chú thích chấm / ảnh / đường chấm. **Lựa chọn · vì sao:** `Chỗ nào cũng có lý do.` + thẻ gợi ý một chỗ thật như bạn bè giới thiệu: ảnh nhỏ, tên, đánh giá Google, `Hợp bạn vì`, `Nên biết` (khung đông nhất cuối tuần từ `crowd` và giờ lịch đã đặt để né), `Người ta quay ở đây` (clip TikTok thật) |
| **Lịch trình** | `Cả ngày xếp sẵn, bạn chỉ việc đi.` + timeline một ngày (tag `Ví dụ`): mỗi chỗ một dòng (giờ, tên, nhãn bữa, `N phút xe` từ chỗ trước), giờ linh vật đang tới sáng đất nung; dòng `Đã kiểm tra: …`. **Đánh giá:** `Đi về, kể lại vài câu.` + lời kể sau chuyến và ghi chú `Đã nhớ cho chuyến sau`, rồi CTA |
| **Ảnh thật của chỗ thật** | 4 ảnh Google Maps ban ngày, rõ đặc trưng nơi đó, mỗi ảnh ghi tên và nguồn lấy từ `credit` của chính ảnh |
| **Hỏi nhanh** | 5 câu hỏi; một dòng `Sắp có` |
| **CTA cuối** + footer | `Bắt đầu chuyến Đà Lạt của bạn.`; footer nói rõ phần nào là ước tính |

Thanh bước bên phải hiện chữ cả 3 bước (`Tìm hiểu` · `Lựa chọn` · `Lịch trình`), theo dõi phần đang xem và bấm được để nhảy tới.

**Xoay (màn đầu):** kéo chuột (hoặc ngón tay theo chiều ngang) trên bản đồ để xoay quanh điểm đang nhìn, kéo dọc để nâng / hạ góc nhìn; thả tay có quán tính; cuộn sang bước khác thì camera về lại góc của bước đó. **Khám phá tự do:** nút `Khám phá bản đồ Đà Lạt` dừng cuộn trang và trao camera cho người dùng: kéo để xoay và nghiêng, chuột phải / Shift + kéo / hai ngón để dịch chuyển, cuộn chuột / chụm hai ngón để phóng to thu nhỏ (14–300 đơn vị), phím mũi tên / WASD dịch, `+` `-` zoom, Q E xoay, `Esc` hoặc `Thoát` để về màn đầu. Chip `Trung tâm · Langbiang · Hồ Tuyền Lâm · Cầu Đất · Trại Mát` bay tới đúng toạ độ thật. Trong chế độ này hiện đủ nhãn khu, đốm vàng và các bưu thiếp của ngày ví dụ (thu nhỏ); linh vật lùi về góc dưới phải, mắt theo con trỏ; tâm nhìn không rời bản đồ.

**Cảnh (bản đồ hành trình):** tờ giấy kem `#f6efe2`; lớp phủ và dải độ cao nướng sẵn trong `dalat.bin` pha 58% vào màu giấy (rừng xanh xám nhạt, đồi nâu đất nhạt); đường đồng mức mảnh; các hồ phẳng xám xanh `#c6d4dc` viền đậm hơn; đường trục chính là dải trắng trên viền be; lưới kinh vĩ 0,02° rất mờ. Mỗi địa điểm là một **đốm vàng** nhỏ (màu vàng duy nhất). Các nơi của ngày ví dụ là **bưu thiếp** in ảnh thật (thumbnail Google Maps, ưu tiên ảnh ban ngày) cắm trên que trắng; tuyến là **đường chấm đất nung** `--tg-brand` vẽ trên mặt giấy. Không cây, nhà, hoa, cánh hoa: nền phải lặng để linh vật nổi.

**Ảnh giao diện thật trong các chương:** mỗi chương 1, 3, 4, 5 có sẵn một khung ảnh (`Shot` trong `Landing.tsx`). Thả ảnh vào `web/src/user/landing/shots/` rồi build lại; chưa có tệp thì chương giữ thẻ vẽ bằng HTML, không phát sinh request.

| Tệp | Chương | Nên chụp |
|---|---|---|
| `app-understand.webp` | Tìm hiểu | cột chat của màn Tìm hiểu: lời kể của người dùng và câu đáp đầu tiên |
| `app-choose.webp` | Lựa chọn · vì sao | một thẻ nơi ở bước Lựa chọn (lý do, đánh đổi, độ đông) |
| `app-plan.webp` | Lịch trình | lịch một ngày |
| `app-feedback.webp` | Đánh giá | màn Đánh giá sau chuyến |

Chụp ở 1440 px với `deviceScaleFactor` 2, cắt sát phần cần xem, WebP chất lượng ~85. Khung rộng bằng cột chữ (~470 px), cao tối đa `min(52vh, 460px)`, ảnh cắt từ trên xuống. Chỉ dùng dữ liệu chuyến mẫu, không có thông tin cá nhân.

**Giờ trong ngày:** `SceneState.hour` (0 bình minh, 0,5 trưa, 1 hoàng hôn) đi theo ngày ví dụ (05:30 Săn Mây → 17:15 Hoàng hôn 3000): nhuộm cả tờ bản đồ (đào nhạt → trắng → cam đất), đổi màu trời / sương ở mép bản đồ và ánh sáng trên linh vật. Chỉ đổi màu, không dựng lại gì.

| Nhịp | `hour` | Linh vật (`mascot.ts`) | Camera trên bản đồ |
|---|---|---|---|
| 0 Mở đầu | 0 | `hover`: lơ lửng bên phải, mở bản đồ, mắt theo con trỏ | phố và các hồ, từ phía nam |
| 1 Tìm hiểu | 0,15 | `listen`: đội tai nghe, bong bóng "…" | lượn quanh Hồ Xuân Hương |
| 2 Lựa chọn | 0,3 | `pick`: giơ bản đồ lên khi 6 bưu thiếp mọc | nâng cao thấy cả ngày |
| 3 Lựa chọn · lý do | 0,4 | quay sang bưu thiếp đang nói, đứng phía dưới nó | ngang tầm bưu thiếp Thênh Thang |
| 4 Lịch trình | 0,45 → 1 | `walk`: hạ xuống bản đồ rồi đi bộ trên tuyến, vừa đi vừa đọc bản đồ trên tay; quay theo hướng tuyến | bám theo điểm đang tới trên tuyến; giờ trên timeline sáng theo điểm đó |
| 5 Đánh giá | 1 | `stamp` dấu "Đúng gu" lên bản đồ, rồi `wave` | điểm cuối lúc hoàng hôn |

**Linh vật:** dựng bằng code (không tệp model, < 8 nghìn tam giác, ≤ 12 lượt vẽ): thân mây từ các khối cầu, chất liệu toon 3 nấc, viền đất nung bằng vỏ lộn ngược (nét như logo), mũ có máy bay, mắt chớp ngẫu nhiên 3–5 s, má hồng đất, hai tay cầm bản đồ gập có bản lề; tai nghe, bong bóng và con dấu chỉ hiện ở trạm của nó. Mọi chuyển động là thủ tục (sin, nội suy, lò xo nén giãn khi đáp). Linh vật luôn ở không gian camera: mỗi nhịp có một chỗ đậu, quanh đó nó trôi chậm như cá bơi; giữa hai nhịp nó vút theo vòng cung. Từ nhịp 3 trở đi chỗ đậu nằm dưới giữa khung để không che bưu thiếp đang nói; nhãn DOM rơi vào linh vật thì ẩn. Linh vật không bị sương làm nhạt.

**Chân và bước đi (từ nhịp 4):** linh vật có hai chân ngắn (thân chân trắng, giày nâu, cùng nét viền). Ở các nhịp bay chân buông thõng và đung đưa nhẹ. Từ nhịp Lịch trình nó rời không gian camera và **đứng trên tờ bản đồ**: chân đặt đúng trên tuyến, cỡ theo bản đồ (≈ 7,5% khoảng cách camera), thẳng đứng, ngả nhẹ về phía camera, mặt quay theo hướng đi nhưng luôn còn thấy. Bước đi **khoá theo quãng đường đã đi** (một chu kỳ = 0,4 đơn vị thân; chân chống 60%, chân đưa 40%, nhấc chân 0,075, bàn chân lăn gót → mũi), nên chân không trượt trên giấy; cuộn dừng thì nó dừng và chân về thế đứng, cuộn nhanh thì nhịp bước bị chặn ở 2,4 chu kỳ/giây. Thân chỉ nhún rất nhẹ để bản đồ dễ đọc; cứ 5,5 s đầu cúi nhìn bản đồ ~1,3 s rồi ngẩng nhìn đường. Dưới thân và mỗi bàn chân có bóng mềm trên giấy. Bưu thiếp đứng giữa camera và linh vật mờ đi (còn ~18%) để nó không bị che. Ở trạm cuối nó bước ra trước bưu thiếp để đóng dấu. Thiết kế chu kỳ bước do sol 6.1 đề xuất; mã ở `web/src/user/landing/mascot.ts` (`gait`) và `scene.ts` (`stage`).

**Giọng văn:** viết như người nói, không như máy: câu ngắn, từ thường ngày ("chỗ", "chạy xe", "có thì vui"), không ẩn dụ bay bổng, không ký hiệu (≤, ~). Đọc lại mỗi câu với vai người mới vào trang: hiểu ngay không, có đúng sự thật không. Landing gọi sản phẩm là "TripGuardian" và người đọc là "bạn" (không dùng "mình" hay "chúng tôi" để khỏi lẫn ai đang nói). Câu hỏi trong Hỏi nhanh viết bằng giọng người dùng.

**Chữ và màu:** landing dùng Be Vietnam Pro cho cả tiêu đề và thân như homepage (`home.css`), token trắng–đen của app, nút chính nâu `--tg-brown`; đất nung `--tg-brand` chỉ là điểm nhấn (nhãn đầu, chấm bước đang xem, số ghim, chấm giờ đang tới, tuyến). Không hồng, không Lora (bỏ 2026-10-15) để sang `/app` không như đổi sang web khác. Số dùng chữ số đều (`tabular-nums`).

Landing không có ô nhập. Mọi nút `Lên lịch chuyến của bạn` mở phiên khách nếu chưa có phiên (không có màn đăng nhập chặn; khách không mở được thì `/app` hiện trang đăng nhập) rồi chuyển sang `/app` (Khám phá); câu hỏi chỉ bắt đầu ở đó, khi người dùng kể chuyến đi.

## 3. Animation và hiệu năng

**Chuyển động**
- **Cuộn mượt:** Lenis (`lerp` 0,1). Từ phần Tìm hiểu trở xuống, mỗi khối (`.tg-rv`) hiện một lần khi lên tới 88% khung nhìn (GSAP `ScrollTrigger`, trượt lên 40 px và hiện dần, 0,9 s). Bản đồ sống nằm ở sân khấu sticky; phần dưới không phụ thuộc cuộn.
- **Sang `/app`:** bấm bất kỳ `Lên lịch chuyến của bạn` thì camera nâng nhẹ vào sương vàng, chữ mờ nhưng nút vừa bấm ở lại (~0,38 s); một ảnh logo đặt đúng chỗ linh vật 3D thay cho nó, rồi `startViewTransition(flushSync(navigate('/app')))` với lớp `html.tg-l2h` bay 3 cặp phần tử chung (0,56 s): `tg-l2h-frame` (sân khấu đang hiện, hoặc hộp CTA cuối nếu bấm ở đó) → ảnh hero `.tg-hm__cover`; `tg-l2h-mascot` (ảnh linh vật) → logo thanh trái; `tg-l2h-cta` (nút vừa bấm) → `Tạo chuyến đi`. Phần còn lại chỉ mờ chéo 0,22 s. Hộp CTA cuối dùng chính ảnh mây vàng của hero homepage làm nền. Trình duyệt không có View Transitions hoặc giảm chuyển động: chuyển thẳng.
- Bản đồ sống tự làm mượt theo thời gian thực (không phụ thuộc FPS), chỉ vẽ khi màn đầu trong màn hình và tab đang mở.
- `prefers-reduced-motion: reduce`: không Lenis, không hiệu ứng hiện dần; cảnh vẽ một khung tĩnh, mọi khối hiện sẵn.
- Cửa sổ máy tính hẹp hơn 1100 px: ẩn link giữa thanh trên, thanh bước và ghi chú góc; hẹp hơn 900 px: các khối xếp một cột.

**Máy không có GPU** (không WebGL, hoặc trình vẽ phần mềm như SwiftShader / llvmpipe / Microsoft Basic Render, phát hiện trong `index.html` trước khi tải gì): trang chạy **bản nhẹ**, không tải three.js và dữ liệu địa hình; màn đầu chỉ hiện ảnh nền `landing-poster.webp`, mỗi bước một ảnh `landing-p1..p5.webp` (chụp từ chính bản đồ sống, có linh vật). Máy chỉ có phần mềm vẽ được hiện nút `Khám phá bản đồ Đà Lạt` mở `?3d=on` (kèm cảnh báo có thể chậm). Máy có GPU nhưng quá yếu: bộ tự hạ chất lượng (mục 6) đã hết nấc mà vẫn chậm thì tự chuyển sang bản nhẹ. `?3d=off` buộc bản nhẹ, `?3d=on` buộc 3D (dùng khi kiểm thử).

**Vào trang nhanh, không giật** (máy tính; điện thoại và `/app/...` không tải gì của landing)
1. **Ảnh nền có ngay:** `index.html` cho `html.tg-boot #root:empty` nền là `web/public/img/landing-poster.webp` (~50 KB, chụp từ chính bản đồ sống ở góc nhìn đầu, có linh vật, không chữ) và preload nó, nên trang không trắng trong lúc mã tải. Sân khấu giữ ảnh này (`.tg-l3__poster`), bản đồ sống mờ dần chồng lên sau khung hình đầu tiên (`is-live`). Không có WebGL: ảnh nền ở lại, các nút xoay ẩn.
2. **Tải song song:** `index.html` bắt đầu tải `/world/dalat.bin` ngay; `App.tsx` bắt đầu tải chunk `scene` và `points.json` ngay từ chunk vào, không chờ `UserApp`. Dữ liệu `covers.json` / snapshot (2,8 MB) chỉ tải sau khi cảnh đã vẽ, để không tranh băng thông.
3. **Bản đồ dựng sẵn:** mọi phép tính nặng (độ cao 122 nghìn đỉnh, màu theo lớp phủ và độ cao, đường, tam giác hóa mặt hồ; cây / nhà / hoa vẫn nằm trong tệp nhưng bản đồ không vẽ) chạy ngoại tuyến trong `web/scripts/landscape/bake.ts` (xác định, có hạt giống) ra một tệp nhị phân ~740 KB (~240 KB brotli); trình duyệt chỉ giải mã mảng (`landing/terrain.ts`, ~150 ms trên máy thử) và tính đường đồng mức (marching squares trên lưới cách 2 đỉnh). Độ cao và màu lưu theo bước chênh với đỉnh kề; cỡ, hướng xoay cây / nhà sinh bằng bộ số ngẫu nhiên có hạt giống, không lưu. Đổi bảng màu hay dữ liệu thì chạy lại `npm run bake:landscape`.
4. **Không bóng đổ:** bản đồ là giấy không chiếu sáng (`MeshBasicMaterial`, nhuộm theo giờ); chỉ linh vật có ánh sáng (bán cầu + nắng).
5. **Biên dịch shader không chặn trang:** `compileAsync` trước khung đầu tiên (trình duyệt có `KHR_parallel_shader_compile`).
6. **Tự hạ chất lượng khi máy yếu** (`DalatScene.govern`): sau 30 khung khởi động, nếu khung trung bình > 28 ms kéo dài, giảm lần lượt: độ phân giải về 1x, tắt đường đồng mức phụ; không bao giờ tăng lại. Màn hình ≥ 2x không bật khử răng cưa; độ phân giải tối đa 1,5x.
7. Tệp `/world/*`, `/img/*` được lưu đệm 1 ngày; `.bin` có sẵn bản `.br` / `.gz` (`web/scripts/prod_assets.mjs`). Phông chữ Google không chặn lần vẽ đầu (`media="print"` rồi đổi sang `all`).
8. Đo: `performance.mark` `tg-scene-start`, `tg-build:<bước>`, `tg-scene-built`, `tg-scene-first-frame` (bảng Performance của Chrome). Ngân sách: ảnh nền hiện < 1 s, bản đồ sống sẵn sàng < 3 s trên laptop trung bình, khung hình ổn định 50–60 FPS.

## 4. Ảnh

Ảnh nền CTA là ảnh sinh (`web/public/img/gen/`, `web/scripts/gen_ui_images.py`, prompt ở `web/scripts/ui_image_prompts.json`, nguồn gốc ghi trong `manifest.json`). Ảnh nền landing (`landing-poster.webp`) và ảnh bản nhẹ (`landing-p1..p5.webp`) là ảnh chụp từ chính bản đồ sống, có linh vật trong khung; chụp lại bằng `node web/scripts/shots_plates.mjs` (cần Vite dev) mỗi khi đổi cảnh. Ảnh sinh chỉ dùng cho không khí, không bao giờ đại diện một nơi có tên; ảnh một nơi có thật luôn là ảnh Google Maps / frame clip.

## 5. Điện thoại: Dùng ứng dụng

Điện thoại (UA di động, hoặc màn chỉ cảm ứng có cạnh ngắn < 600px — `web/src/user/landing/device.ts`) vào bất kỳ trang người dùng nào (`/`, `/app/...`, kể cả link được chia sẻ) đều thấy trang Dùng ứng dụng; không có lối vào bản web. `/admin` không đổi.

- Minh họa điện thoại (ảnh nền + 3 ghim + tuyến + `Lịch sẵn sàng`), nhãn `Trên điện thoại`, tiêu đề `Tải ứng dụng để dùng TripGuardian trên điện thoại.`
- Hai nút cửa hàng, nền tảng của máy đứng trước. Link lấy từ biến build `VITE_APP_IOS_URL`, `VITE_APP_ANDROID_URL` (`web/.env`):
  - có link: nút `Tải trên App Store / Google Play` mở cửa hàng;
  - chưa có: ô viền đứt `Sắp có trên …` + tag `chưa mở`, dòng phụ `Ứng dụng sẽ có trong thời gian tới. Hiện tại, bạn mở TripGuardian trên máy tính để có trải nghiệm tốt nhất.`
- `Gửi link sang máy tính`: chia sẻ đúng trang đang mở (link chuyến, link một nơi) qua bảng chia sẻ của máy, không có thì chép link và báo `Đã chép link…`.
