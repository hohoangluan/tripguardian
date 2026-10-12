# TripGuardian — Đặc tả UI/UX: Landing

Dành cho designer và người code landing (`/`). Máy tính (laptop, desktop, PC) thấy landing 3D (`web/src/user/screens/Landing.tsx`); điện thoại thấy trang **Dùng ứng dụng** (`web/src/user/screens/GetApp.tsx`, §5) ở mọi trang người dùng — web không có bản cho điện thoại. Hệ màu, chữ: `docs/UI_SPEC_USER_WEB.md` §8 — landing không thêm màu nào ngoài token có sẵn.

Đọc kèm: `docs/UX_Design_Brief.md` (nguyên tắc, cách hiển thị dữ liệu) · `docs/UI_SPEC_USER_WEB.md` (app sau khi bấm `Lên lịch chuyến của bạn`).

---

## 1. Nguyên tắc

1. **Một câu cho cả trang:** kể chuyến đi trong khoảng 2 phút → nhận lịch Đà Lạt từng giờ, chỉ gồm nơi có thật, có lý do và điều cần biết. Khối nào không phục vụ câu này thì không có trên trang.
2. **Landing diễn sản phẩm, không giải thích.** Màn đầu là thung lũng Đà Lạt 3D lúc bình minh, dựng từ địa hình thật, tông hồng nhạt (trắng + hồng phấn + mận), không khí du lịch chứ không phải sa bàn. Các phần sau là trang giấy thường; mỗi bước đặt cạnh chữ một miếng UI thật thu nhỏ (chat và thẻ chuyến đi, thẻ lý do, timeline), dùng chung CSS với app nên đổi app thì landing đổi theo.
3. **Ngân sách chữ:** mỗi bước có 1 nhãn (≤4 từ), 1 tiêu đề (≤2 câu), 1 đoạn phụ (≤2 câu). Một CTA duy nhất, lặp lại ở thanh trên, màn đầu và hộp cuối: `Lên lịch chuyến của bạn`.
4. **Con số và vị trí phải thật.** Số nơi lấy từ `web/src/user/landing/stats.json`; tên, ảnh, đánh giá, độ đông, clip từ `places.json`; mỗi đốm sáng trong thung lũng là toạ độ thật của một nơi trong `points.json`. Cả ba sinh bằng `python web/scripts/pick_landing_places.py` từ `snapshot.json` + `covers.json`. Địa hình là thật: độ cao SRTM 30 m (lấy mẫu ~330 m), viền các hồ, đường trục chính, vùng rừng / nhà kính / phố và vị trí nhà từ OpenStreetMap, tải bằng `python web/scripts/export_landscape.py dem | osm | water` ra `web/scripts/landscape/{dem,osm}.json` (nguồn, chỉ dùng khi dựng), rồi dựng sẵn bằng `npm run bake:landscape --prefix web` ra `web/public/world/dalat.bin` (§3). Dữ liệu đã có sẵn trong repo; chỉ chạy lại khi muốn cập nhật bản đồ. Chỉ có **độ phóng đại chiều cao** (×~3 so với tỷ lệ ngang) và chi tiết nhiễu mịn trên lưới 330 m là minh họa; cây thông, mái nhà là biểu tượng, không phải từng cây từng nhà. Footer ghi rõ. Ngày ví dụ ở bước Lịch trình có tag *"Ví dụ minh họa"*: giờ đến và thời gian ở lại là minh họa, phút đi xe giữa hai nơi là ước tính thô từ toạ độ thật (cùng `road_factor`, `rough_speed_kmh` của `config/planning.yaml`), tên nơi là thật.
5. **Lời hứa về tài khoản phải đúng với `/app`:** khách vào được ngay (`docs/ACCOUNTS.md` §7), nên landing nói "Không cần tài khoản" và luôn kèm đường lưu chuyến ("Đăng nhập Google để lưu chuyến").

## 2. Cấu trúc (máy tính)

Thanh trên cố định (`Cách hoạt động` · `Địa điểm` · `Hỏi nhanh`, `Đăng nhập`, `Lên lịch chuyến của bạn`), rồi các phần theo thứ tự:

| Phần | Nội dung |
|---|---|
| **Màn đầu** | Cảnh 3D (`web/src/user/landing/scene.ts`, địa hình `terrain.ts`) cao `min(100vh, 900px)`, chữ bên trái, mô hình lệch phải để chừa cột chữ. Nhãn `TripGuardian · Đà Lạt`, tiêu đề `Lịch trình Đà Lạt vừa với bạn.`, một câu phụ có số nơi thật, nút `Lên lịch chuyến của bạn`, link `Xem cách hoạt động`, ba cam kết (`Miễn phí` · `Không cần tài khoản` · `Chỉ gồm nơi có thật`). Góc phải dưới: nút `Xoay thử Đà Lạt 3D` kèm lời giải thích hiện sẵn. Chân màn: nút nổi `Cuộn xuống để xem cách hoạt động` (mũi tên nhấp nhô, bấm để tới bước đầu) |
| **Tìm hiểu nhu cầu** | `Kể cho TripGuardian về chuyến đi bạn mong muốn.` + khung chat (Chat / Chọn nhanh) và thẻ chuyến đi: `Không được vi phạm` (con dấu khóa) và `Bạn thích` (chip viền đứt) |
| **Tìm địa điểm phù hợp** | `Đà Lạt có rất nhiều nơi để đi. Nhưng đâu là nơi dành cho bạn?` + thẻ lý do của một nơi thật: ảnh, `Vì sao hợp bạn` (gu + đánh giá Google), `Cần biết trước` (khung đông nhất cuối tuần, lấy từ `crowd` của nơi đó, kèm giờ lịch đã đặt để né), clip TikTok thật (bấm để mở), nút `Giữ` / `Bỏ` |
| **Lịch trình của bạn** | `Bạn tận hưởng chuyến đi. TripGuardian lo lịch trình.` + timeline một ngày: giờ, tên nơi, thời gian ở, phút đi xe giữa hai nơi, nhãn bữa ăn, dòng `Đã kiểm tra` |
| **Địa điểm thật** | `Địa điểm thật, trải nghiệm thật`: 4 ảnh Google Maps ban ngày, rõ đặc trưng nơi đó, mỗi ảnh ghi tên và nguồn lấy từ `credit` của chính ảnh |
| **Hỏi nhanh** | 5 câu hỏi; một dòng `Sắp có` |
| **CTA cuối** + footer | `Bắt đầu chuyến Đà Lạt của bạn.`; footer nói rõ phần nào là ước tính |

Thanh bước bên phải hiện chữ cả 3 bước (`Tìm hiểu` · `Lựa chọn` · `Lịch trình`), theo dõi phần đang xem và bấm được để nhảy tới.

**Xoay 360° (màn đầu):** kéo chuột (hoặc ngón tay theo chiều ngang) trên mô hình để xoay cả cảnh quanh thung lũng, kéo dọc để nâng / hạ góc nhìn; thả tay có quán tính; camera không bao giờ chui xuống đất. **Khám phá tự do:** nút `Xoay thử Đà Lạt 3D` dừng cuộn trang và trao camera cho người dùng: kéo để xoay và nghiêng, chuột phải / Shift + kéo / hai ngón để dịch chuyển, cuộn chuột / chụm hai ngón để phóng to thu nhỏ (14–300 đơn vị), phím mũi tên / WASD dịch, `+` `-` zoom, Q E xoay, `Esc` hoặc `Thoát` để về màn đầu. Chip `Trung tâm · Langbiang · Hồ Tuyền Lâm · Cầu Đất · Trại Mát` bay tới đúng toạ độ thật. Trong chế độ này hiện đủ nhãn khu, đốm sáng và các bưu thiếp của ngày ví dụ; camera không chui xuống đất, tâm nhìn không rời bản đồ.

**Cảnh:** bầu trời bình minh (hồng phấn → trắng hồng → hồng đào ở chân trời, quầng nắng phía đông), sương nằm trong các lòng chảo thật (phố, Tuyền Lâm, Trại Mát, phía Đa Nhim), đồi thông ba lá hồng mận theo vùng rừng thật, các hồ theo viền thật (mỗi hồ một mực nước), đường trục chính màu trắng kem, phố mái hồng theo vị trí nhà thật, nhà thờ Con Gà, đỉnh Langbiang; địa hình xa mờ dần vào chân trời. Mỗi địa điểm là một đốm sáng vàng nhỏ (màu vàng duy nhất trong cảnh). Các nơi của ngày ví dụ là **bưu thiếp** in ảnh thật của nơi đó (thumbnail Google Maps, ưu tiên ảnh ban ngày), cắm trên que trắng; tuyến đi là **đường chấm trắng** trên mặt đất. Màu lấy từ token (pine, sun, paper và các tông nhạt).

**Giọng văn:** landing gọi sản phẩm là "TripGuardian" và người đọc là "bạn" (không dùng "mình" hay "chúng tôi" để khỏi lẫn ai đang nói). Câu hỏi trong Hỏi nhanh viết bằng giọng người dùng.

**Chữ:** landing dùng Lora (tiêu đề, bộ dấu tiếng Việt đầy đủ, cân ở cỡ lớn) + Be Vietnam Pro (thân bài, thiết kế riêng cho tiếng Việt); ghi đè `--tg-display`, `--tg-sans` trên `.tg-landing`, màu giữ nguyên token. Số dùng chữ số đều (`tabular-nums`) thay cho phông mono.

Landing không có ô nhập. Mọi nút `Lên lịch chuyến của bạn` mở phiên khách nếu chưa có phiên (không có màn đăng nhập chặn; khách không mở được thì `/app` hiện trang đăng nhập) rồi chuyển sang `/app` (Khám phá); câu hỏi chỉ bắt đầu ở đó, khi người dùng kể chuyến đi.

## 3. Animation và hiệu năng

**Chuyển động**
- **Cuộn mượt:** Lenis (`lerp` 0,1). Từ phần Tìm hiểu trở xuống, mỗi khối (`.tg-rv`) hiện một lần khi lên tới 88% khung nhìn (GSAP `ScrollTrigger`, trượt lên 40 px và hiện dần, 0,9 s). Cảnh 3D chỉ nằm ở màn đầu, không phụ thuộc cuộn.
- **Sang `/app`:** bấm `Lên lịch chuyến của bạn` thì chữ nhấc lên và mờ, thung lũng phóng nhẹ (~0,4 s), rồi trình duyệt chuyển mờ dần sang `/app` bằng View Transitions (`startViewTransition` + `flushSync`, 0,5 s); trình duyệt không có thì chuyển thẳng. Giảm chuyển động: chuyển thẳng, không hiệu ứng.
- Cảnh 3D tự làm mượt theo thời gian thực (không phụ thuộc FPS), chỉ vẽ khi màn đầu trong màn hình và tab đang mở.
- `prefers-reduced-motion: reduce`: không Lenis, không hiệu ứng hiện dần; cảnh vẽ một khung tĩnh, mọi khối hiện sẵn.
- Cửa sổ máy tính hẹp hơn 1100 px: ẩn link giữa thanh trên, thanh bước và ghi chú góc; hẹp hơn 900 px: các khối xếp một cột.

**Máy không có GPU** (không WebGL, hoặc trình vẽ phần mềm như SwiftShader / llvmpipe / Microsoft Basic Render, phát hiện trong `index.html` trước khi tải gì): trang chạy **bản nhẹ**, không tải three.js và dữ liệu địa hình; màn đầu chỉ hiện ảnh nền `landing-poster.webp` (chụp từ chính mô hình 3D). Máy chỉ có phần mềm vẽ được hiện nút `Xoay thử Đà Lạt 3D` mở `?3d=on` (kèm cảnh báo có thể chậm). Máy có GPU nhưng quá yếu: bộ tự hạ chất lượng (mục 6) đã hết nấc mà vẫn chậm thì tự chuyển sang bản nhẹ. `?3d=off` buộc bản nhẹ, `?3d=on` buộc 3D (dùng khi kiểm thử).

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
