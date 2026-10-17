# TripGuardian — Đặc tả UI/UX: Landing

Dành cho designer và người code landing (`/`). Máy tính (laptop, desktop, PC) thấy landing 3D (`web/src/user/screens/Landing.tsx`); điện thoại thấy trang **Dùng ứng dụng** (`web/src/user/screens/GetApp.tsx`, §5) ở mọi trang người dùng — web không có bản cho điện thoại. Landing dùng cùng bộ màu và chữ với trang chủ app (trắng–đen từ `tokens.css`, Be Vietnam Pro, nút nâu, thẻ trắng bo 22 px); chỉ khác điểm nhấn là cam đất của logo (§2 *Chữ và màu*). Trang chủ là mốc: đổi vibe trang chủ thì đổi landing theo (`docs/UI_SPEC_USER_WEB.md` §8).

Đọc kèm: `docs/UX_Design_Brief.md` (nguyên tắc, cách hiển thị dữ liệu) · `docs/UI_SPEC_USER_WEB.md` (app sau khi bấm `Lên lịch chuyến của bạn`) · `docs/UI_SPEC_FLOW_LAYOUT.md` (luồng thật mà các chương kể lại).

---

## 1. Nguyên tắc

1. **Một câu cho cả trang:** kể chuyến đi trong vài phút → nhận lịch Đà Lạt từng giờ, chỉ gồm nơi có thật, có lý do và điều cần biết. Khối nào không phục vụ câu này thì không có trên trang.
2. **Landing diễn sản phẩm, không giải thích.** Màn đầu là thung lũng Đà Lạt 3D lúc bình minh, dựng từ địa hình thật, tông của trang chủ (nền xám nhạt, đá ấm, thông xám xanh, mái cam đất, nắng vàng), không khí du lịch chứ không phải sa bàn. Mỗi bước đặt cạnh chữ **một bản thu nhỏ của đúng màn thật** mà bước đó nói tới (§2): cùng chữ, cùng thứ tự, cùng loại số liệu với app. Đổi luồng hay chữ trong app thì sửa chương tương ứng.
3. **Ngân sách chữ:** mỗi bước có 1 nhãn (≤4 từ), 1 tiêu đề (≤2 câu), 1 đoạn phụ (≤2 câu). Một CTA duy nhất, lặp lại ở thanh trên, màn đầu, cuối chương Đánh giá và hộp cuối: `Lên lịch chuyến của bạn`.
4. **Con số và vị trí phải thật.** Số nơi lấy từ `web/src/user/landing/stats.json`; tên, ảnh, đánh giá, độ đông, giá, clip và **tín hiệu kèm số người nhắc** (`signals`) từ `places.json`; mỗi đốm sáng trong thung lũng là toạ độ thật của một nơi trong `points.json`. Cả ba sinh bằng `python web/scripts/pick_landing_places.py` từ `snapshot.json` + `covers.json`; `--signals-only` chỉ làm mới `signals`, giữ nguyên ảnh và số liệu đang có (covers.json hiện chỉ còn 1 ảnh mỗi nơi, chạy đầy đủ sẽ mất ảnh phụ). Địa hình là thật: độ cao SRTM 30 m (lấy mẫu ~330 m), viền các hồ, đường trục chính, vùng rừng / nhà kính / phố và vị trí nhà từ OpenStreetMap, tải bằng `python web/scripts/export_landscape.py dem | osm | water` ra `web/scripts/landscape/{dem,osm}.json`, rồi dựng sẵn bằng `npm run bake:landscape --prefix web` ra `web/public/world/dalat.bin` (§3). Chỉ có **độ phóng đại chiều cao** (×~3) và chi tiết nhiễu mịn là minh họa; cây thông, mái nhà là biểu tượng. Footer ghi rõ. Ngày ví dụ ở bước Lịch trình có tag *"Ví dụ"*: giờ đến và thời gian ở lại là minh họa, phút đi xe giữa hai nơi là ước tính thô từ toạ độ thật (cùng `road_factor`, `rough_speed_kmh` của `config/planning.yaml`), tên nơi là thật.
5. **Lời hứa về tài khoản phải đúng với `/app`:** khách vào được ngay (`docs/ACCOUNTS.md` §7), nên landing nói "Không cần tài khoản" và luôn kèm đường lưu chuyến ("Đăng nhập Google để lưu chuyến").

## 2. Cấu trúc (máy tính)

Thanh trên cố định (`Cách hoạt động` · `Địa điểm` · `Hỏi nhanh`, `Đăng nhập`, `Dùng thử khách` khi đang đăng nhập, `Lên lịch chuyến của bạn`), rồi các phần theo thứ tự:

| Phần | Nội dung | Màn thật được kể lại |
|---|---|---|
| **Màn đầu** | Cảnh 3D (`web/src/user/landing/scene.ts`, địa hình `terrain.ts`), chữ bên trái, mô hình lệch phải. Nhãn `TripGuardian · Đà Lạt`, tiêu đề `Lịch trình Đà Lạt vừa với bạn.`, câu phụ có số nơi thật, nút `Lên lịch chuyến của bạn`, link `Xem cách hoạt động`, ba cam kết (`Miễn phí` · `Không cần tài khoản` · `Chỗ nào cũng có thật`). Góc phải dưới: nút `Xoay thử Đà Lạt 3D`. Chân màn: nút nổi `Cuộn xuống để xem cách hoạt động` | — |
| **Tìm hiểu** | `Cứ kể như kể với bạn đi cùng.` Một khung chat: bong bóng lời kể của người dùng (phải); avatar TripGuardian hỏi lại bằng ảnh `Bạn thích không gian quán nào hơn?` + `Vì bạn nói "cà phê chill"`, 3 ảnh quán thật, mỗi ảnh mang một gu người ta thật sự nhắc ở quán đó, chữ theo `taste_bank` (`Không gian rộng, thoáng` đang chọn · `Yên tĩnh` · `Ngồi ngoài trời`); dưới cùng vòng `3/7 thông tin` và 7 ô thông tin bắt buộc (`Ngày đi` · `Đi với` · `Phương tiện` đã ghi, `Lưu ý` · `Nhịp độ` · `Ngân sách` · `Nơi lưu trú` viền đứt) | Tìm hiểu: chat, thẻ hỏi bằng ảnh, cột *Thông tin chuyến* |
| **Lựa chọn** | `Chọn ra 6 chỗ, không phải lục cả nghìn.` (số đếm lùi từ tổng số chỗ) + chú thích chấm / tuyến, rồi thanh tóm tắt như thanh dưới của Lựa chọn: `Đi kịp · 6 nơi · 7 giờ 30 tham quan · ≈ 1 giờ 38 đi lại · Lập lịch` (cộng từ ngày ví dụ) | Lựa chọn: thanh "Đã chọn" |
| **Lựa chọn · vì sao** | `Chỗ nào cũng có lý do.` + thẻ một nơi y như thẻ ở Lựa chọn: ảnh (nhãn loại, `Ảnh: Google Maps`), tên, khu · ★ · số đánh giá Google, 3 dòng tích `<gu>, N người nhắc` (đúng gu người dùng vừa kể/chọn), hộp `Đánh đổi: <điều bất lợi đầu tiên người ta nhắc>, N người nhắc`, dòng phụ thời gian ở lại · giá · khung đông nhất cuối tuần | Lựa chọn: `PlaceCard` |
| **Lịch trình** | `Cả ngày xếp sẵn, bạn chỉ việc đi.` + câu nói về bước đọc lại trước khi xếp; dải 3 phương án khi chọn nhiều hơn số ngày (`Giữ nơi hợp gu nhất` · `Ít đi lại` · `Tiết kiệm`); timeline một ngày (tag `Ví dụ`): giờ, tên, nhãn bữa, `≈ N phút xe máy từ chỗ trước` | Đọc lại trước khi lập lịch; Chọn phương án; Lịch trình theo ngày |
| **Đánh giá** | `Chốt lịch, chấm vài câu là xong.` + thẻ `Kế hoạch đã chốt.` với một câu `Gợi ý có đúng gu của bạn?` thang 1–5 (`Chưa đúng` … `Rất đúng`), rồi CTA | Phản hồi (`/app/done`) |
| **Ảnh thật của chỗ thật** | 4 ảnh Google Maps ban ngày, mỗi ảnh ghi tên và nguồn lấy từ `credit` của chính ảnh | — |
| **Hỏi nhanh** | 5 câu hỏi (`web/src/user/faq.ts`, dùng chung với trang Hỗ trợ); một dòng `Sắp có` | — |
| **CTA cuối** + footer | `Bắt đầu chuyến Đà Lạt của bạn.`; khi đang đăng nhập thêm link dùng thử khách; footer nói rõ phần nào là ước tính | — |

Ví dụ được chọn để các chương nối nhau: gu `Không gian rộng, thoáng` chọn ở Tìm hiểu là dòng đầu của thẻ Tiệm cà phê Thênh Thang ở Lựa chọn · vì sao, và quán đó là điểm 08:45 của lịch. Thẻ trên landing không bấm được (chỉ minh họa, `role="img"` khi là số liệu tổng).

**Ảnh màn thật:** chương Tìm hiểu, Lựa chọn · vì sao, Lịch trình và Đánh giá hiện ảnh chụp màn thật của app (`Shot` trong `Landing.tsx`, tệp `web/src/user/landing/shots/app-{understand,choose,plan,feedback}.webp`, chú thích `Giao diện thật · …`). Thiếu tệp nào thì chương đó hiện bản dựng HTML mô tả ở bảng trên. Chụp bằng một chuyến khách thật trên bản live ở 1440×900, `deviceScaleFactor` 2, cắt sát phần cần xem, rộng tối đa 940 px, WebP ~85; không có thông tin cá nhân. Hiện có: câu hỏi bằng ảnh `Bạn muốn săn mây ở kiểu chỗ nào?`, thẻ một nơi ở Lựa chọn, bảng đọc lại `Bạn nói …` trước khi lập lịch, màn `Kế hoạch đã chốt.` Đổi màn trong app thì chụp lại.

Thanh bước bên phải theo dõi phần đang xem (`Mở đầu` · `Tìm hiểu` · `Lựa chọn` · `Lịch trình` · `Đánh giá`) và bấm được để nhảy tới.

**Xoay 360° (màn đầu):** kéo chuột (hoặc ngón tay theo chiều ngang) trên mô hình để xoay quanh thung lũng, kéo dọc để nâng / hạ góc nhìn; thả tay có quán tính; camera không chui xuống đất. **Khám phá tự do:** nút `Xoay thử Đà Lạt 3D` dừng cuộn trang và trao camera cho người dùng: kéo để xoay và nghiêng, chuột phải / Shift + kéo / hai ngón để dịch chuyển, cuộn chuột / chụm hai ngón để phóng to thu nhỏ, phím mũi tên / WASD dịch, `+` `-` zoom, Q E xoay, `Esc` hoặc `Thoát` để về màn đầu. Chip `Trung tâm · Langbiang · Hồ Tuyền Lâm · Cầu Đất · Trại Mát` bay tới đúng toạ độ thật.

**Cảnh:** bầu trời bình minh (xám nhạt → trắng → xám ấm ở chân trời, quầng nắng vàng phía đông), sương trong các lòng chảo thật, đồi thông xám xanh theo vùng rừng thật, các hồ theo viền thật, đường trục chính trắng kem, phố mái cam đất theo vị trí nhà thật, nhà thờ Con Gà, đỉnh Langbiang. Mỗi địa điểm là một đốm sáng vàng nhỏ. Các nơi của ngày ví dụ là **bưu thiếp** in ảnh thật (thumbnail Google Maps, ưu tiên ảnh ban ngày) cắm trên que trắng; tuyến đi là đường chấm trên mặt đất.

**Giọng văn:** viết như người nói: câu ngắn, từ thường ngày ("chỗ", "chạy xe"), không ẩn dụ, không ký hiệu (≤). Landing gọi sản phẩm là "TripGuardian" và người đọc là "bạn". Câu hỏi trong Hỏi nhanh viết bằng giọng người dùng. Đọc lại mỗi chương với vai người mới vào trang trước khi coi là xong.

**Chữ và màu:** landing dùng token của app (`tokens.css`: nền `#f6f6f6`, chữ `#111`, nút chính `--tg-brown`); `web/src/user/css/landing.css` chỉ đổi `--tg-sun` thành cam đất `#b4532a` (nhấn chữ, ghim, vòng, tuyến trong cảnh). Mọi chữ dùng Be Vietnam Pro (tiêu đề đậm 650, giãn chữ −0,03 em, giống tiêu đề trang chủ); không còn Lora. Số dùng chữ số đều (`tabular-nums`). Các thẻ chương (`.tg-lk*`) chỉ dùng token, nên đổi bộ màu landing là thẻ đổi theo.

Landing không có ô nhập. Mọi nút `Lên lịch chuyến của bạn` mở phiên khách nếu chưa có phiên (không màn đăng nhập chặn; khách không mở được thì `/app` hiện trang đăng nhập) rồi chuyển sang `/app` (Khám phá). `Dùng thử khách` mở phiên khách mới mà không đụng tới tài khoản đang đăng nhập.

## 3. Animation và hiệu năng

**Chuyển động**
- **Cuộn mượt:** Lenis (`lerp` 0,1). Các chương nằm trên sân khấu sticky, đổi theo một timeline GSAP gắn với cuộn; trong mỗi chương các phần của thẻ hiện lần lượt (lựa chọn ảnh, ô thông tin, dòng lý do, phương án, dòng lịch, thang điểm) và **xong trước khi chương đứng yên**, để dừng cuộn ở đâu cũng đọc được trọn thẻ. Phần dưới sân khấu (`.tg-rv`) hiện một lần khi lên tới 88% khung nhìn.
- **Sang `/app`:** bấm `Lên lịch chuyến của bạn` thì mọi thứ quanh nút vừa bấm nhấc lên và mờ, thung lũng phóng nhẹ (~0,38 s), rồi `startViewTransition` với lớp `html.tg-l2h` (`web/src/user/css/motion.css`) bay sân khấu (hoặc hộp CTA cuối) thành ảnh hero của trang chủ và nút vừa bấm thành `Tạo chuyến đi`; phần còn lại mờ chéo. Trình duyệt không có View Transitions hoặc giảm chuyển động: chuyển thẳng.
- Cảnh 3D tự làm mượt theo thời gian thực, chỉ vẽ khi màn đầu trong màn hình và tab đang mở.
- `prefers-reduced-motion: reduce`: không Lenis, không hiệu ứng hiện dần; cảnh vẽ một khung tĩnh, các chương xếp lưới hai cột, mọi thẻ hiện sẵn.
- Cửa sổ máy tính hẹp hơn 1100 px: ẩn link giữa thanh trên, thanh bước và ghi chú góc; hẹp hơn 900 px: các khối xếp một cột. Chương cao hơn khung nhìn thì tự thu nhỏ (`zoom`, tối thiểu 0,6).

**Máy không có GPU** (không WebGL, hoặc trình vẽ phần mềm như SwiftShader / llvmpipe / Microsoft Basic Render, phát hiện trong `index.html` trước khi tải gì): **bản nhẹ**, không tải three.js và dữ liệu địa hình; màn đầu hiện `landing-poster.webp`, mỗi chương một ảnh `landing-p1..p5.webp` chụp từ chính mô hình 3D. Máy chỉ có phần mềm vẽ được hiện nút `Xoay thử Đà Lạt 3D` mở `?3d=on`. Máy có GPU nhưng quá yếu: hết nấc hạ chất lượng mà vẫn chậm thì tự chuyển sang bản nhẹ. `?3d=off` buộc bản nhẹ, `?3d=on` buộc 3D (dùng khi kiểm thử).

**Vào trang nhanh, không giật** (máy tính; điện thoại và `/app/...` không tải gì của landing)
1. **Ảnh nền có ngay:** `index.html` cho `html.tg-boot #root:empty` nền `landing-poster.webp` và preload nó. Sân khấu giữ ảnh này (`.tg-l3__poster`), cảnh 3D mờ dần chồng lên sau khung hình đầu tiên (`is-live`).
2. **Tải song song:** `index.html` bắt đầu tải `/world/dalat.bin` ngay; `App.tsx` bắt đầu tải chunk `scene` và `points.json` ngay từ chunk vào. Snapshot chỉ tải sau khi cảnh đã vẽ.
3. **Địa hình dựng sẵn:** mọi phép tính nặng (độ cao, màu theo lớp phủ, cây, nhà, đường, mặt hồ) chạy ngoại tuyến trong `web/scripts/landscape/bake.ts` ra một tệp nhị phân ~740 KB (~240 KB brotli); trình duyệt chỉ giải mã mảng (`landing/terrain.ts`). Đổi bảng màu hay dữ liệu thì chạy lại `npm run bake:landscape`.
4. **Bóng đổ vẽ một lần** (`shadowMap.autoUpdate = false`).
5. **Biên dịch shader không chặn trang:** `compileAsync` trước khung đầu tiên.
6. **Tự hạ chất lượng khi máy yếu** (`DalatScene.govern`): khung trung bình > 28 ms kéo dài thì giảm lần lượt độ phân giải, cánh hoa / tia sáng / đom đóm, một nửa cây; không tăng lại.
7. Tệp `/world/*`, `/img/*` được lưu đệm 1 ngày; `.bin` có sẵn bản `.br` / `.gz` (`web/scripts/prod_assets.mjs`).
8. Đo: `performance.mark` `tg-scene-start`, `tg-scene-built`, `tg-scene-first-frame`. Ngân sách: ảnh nền < 1 s, cảnh 3D sẵn sàng < 3 s trên laptop trung bình, 50–60 FPS.

## 4. Ảnh

Ảnh trong các thẻ chương là ảnh Google Maps của chính nơi đó (`places.json`, thumbnail khi có); ảnh minh họa không bao giờ đứng tên một nơi có thật. Ảnh nền landing và ảnh bản nhẹ (`landing-poster.webp`, `landing-p1..p5.webp`) chụp từ chính mô hình 3D. Ảnh nền hộp CTA cuối là gradient nâu–đen có quầng cam đất bằng CSS.

## 5. Điện thoại: Dùng ứng dụng

Điện thoại (UA di động, hoặc màn chỉ cảm ứng có cạnh ngắn < 600px — `web/src/user/landing/device.ts`) vào bất kỳ trang người dùng nào (`/`, `/app/...`, kể cả link được chia sẻ) đều thấy trang Dùng ứng dụng; không có lối vào bản web. `/admin` không đổi.

- Minh họa điện thoại (ảnh nền + 3 ghim + tuyến + `Lịch sẵn sàng`), nhãn `Trên điện thoại`, tiêu đề `Tải ứng dụng để dùng TripGuardian trên điện thoại.`
- Hai nút cửa hàng, nền tảng của máy đứng trước. Link lấy từ biến build `VITE_APP_IOS_URL`, `VITE_APP_ANDROID_URL` (`web/.env`):
  - có link: nút `Tải trên App Store / Google Play` mở cửa hàng;
  - chưa có: ô viền đứt `Sắp có trên …` + tag `chưa mở`, dòng phụ `Ứng dụng sẽ có trong thời gian tới. Hiện tại, bạn mở TripGuardian trên máy tính để có trải nghiệm tốt nhất.`
- `Gửi link sang máy tính`: chia sẻ đúng trang đang mở (link chuyến, link một nơi) qua bảng chia sẻ của máy, không có thì chép link và báo `Đã chép link…`.
