# TripGuardian — Đặc tả UI/UX: Landing

Dành cho designer / Figma và cho người code landing. Landing **giữ nguyên kiến trúc hiện tại** (`web/src/pages/Landing.tsx`: thế giới 3D + 5 beat dính + GSAP ScrollTrigger + Lenis). Tài liệu này nói **đổi gì**: hệ màu sang trắng hồng, và cắt chữ xuống mức tối thiểu để **animation kể chuyện thay chữ**.

Đọc kèm: `docs/UX_Design_Brief.md` (nguyên tắc, cách hiển thị dữ liệu) · `docs/UI_SPEC_USER_WEB.md` (app sau khi bấm CTA).

---

## 1. Nguyên tắc của landing này

1. **Landing không giải thích sản phẩm. Nó diễn sản phẩm.** Mỗi beat là một miếng UI thật thu nhỏ, không phải hình minh hoạ tính năng.
2. **Ngân sách chữ cứng.** Mỗi màn cuộn chỉ được có: 1 nhãn bước (≤4 từ) + 1 tiêu đề (≤6 từ) + **nhiều nhất 1 dòng phụ** (≤16 từ). Hết. Không đoạn văn, không bullet, không lưới tính năng.
3. **Thứ gì animation nói được thì không viết.** "Quá nhiều lựa chọn" là 842 pin sáng rồi tắt còn 5 — không phải một câu nói rằng có quá nhiều lựa chọn.
4. **Bản đồ là hình nền.** Thế giới 3D không trang trí; nó mang pin, mang tuyến đường, và nối thẳng sang thẻ sản phẩm bằng đường dẫn.
5. **Con số phải thật.** Mọi số trên landing lấy từ build thật (`web/public/data/snapshot.json`, `build`), không bịa. Không có số thật thì bỏ con số đó đi.

## 2. Hệ màu — trắng hồng

| Vai trò | Giá trị | Dùng ở đâu |
|---|---|---|
| Nền trang | `#FFF9F8` | ngoài 3D |
| Bề mặt | `#FFFFFF` | thẻ, top bar, scrim sau chữ |
| Mực | `#3A2B32` | chữ chính |
| Hồng phấn | `#EFB8C4` | nút (chữ mận), nhãn bước |
| Hồng đậm | `#C97890` | pin, tuyến, dòng 2 headline (chỉ chữ ≥24px, 3.2:1) |
| Hồng nhạt | `#FCEEF1` | khối mềm, rãnh meter |
| Mận | `#6B3550` | footer, khối quy tắc cứng |
| Hổ phách | `#A8660F` | **chỉ** cảnh báo |
| Xanh mực | `#4A6488` | link, dòng nguồn dữ liệu |
| **Vàng dã quỳ** | `#F2B31B` | **đúng một chỗ trên toàn trang: đĩa mặt trời trong 3D.** Không dùng ở đâu khác |

Giữ vàng một chấm vì đó là màu nhận diện Đà Lạt; bỏ sạch thì landing mất chất địa phương, rải nhiều thì vỡ hệ trắng hồng.

### Thế giới 3D — nhuộm lại, không dựng lại

Hình học, camera, animation giữ nguyên. Chỉ đổi màu:

| File | Đổi |
|---|---|
| `web/src/scene/Terrain.tsx` §dải cao độ | bờ `#E8CFC6` · đồng `#DCB6AE` · sườn `#B98C92` · rừng sâu `#7E5A68` · đỉnh sương `#C9A7AE` |
| `web/src/scene/Terrain.tsx` §mặt hồ | `#F3DDE0`, giữ `metalness 0.25` |
| `web/src/scene/Pines.tsx` §`setHSL` | `0.42±.05 / .28–.40 / .13–.20` → `0.93±.03 / .10–.22 / .22–.32` (thông thành bóng mận xám) |
| `web/src/scene/Director.tsx` §MIST, CLEAR | `#F6E7E6`, `#FDF3F1` |
| `web/src/scene/Director.tsx` §đèn | hemisphere `#FFF9F8` / `#6B3550`; nắng `#FFD9CE`; **thêm một đĩa mặt trời `#F2B31B`** |
| `web/src/scene/Mist.tsx` §points | `#FCEDEC` |
| `web/src/scene/Pins.tsx` | pin thường `#A98E95` · pin đã chọn `#C97890` · nhãn `#FFFFFF` · quầng sáng `#F2B31B` chỉ quanh mặt trời |
| `web/src/scene/Route.tsx` | tuyến `#C97890`; đoạn lỗi `#B06A12` |
| `web/src/styles.css` §`:root` | giữ nguyên **tên** token, đổi giá trị sang bảng trên |

Rủi ro: hồng tương phản thấp hơn xanh–vàng cũ. Bắt buộc giữ **scrim trắng mềm** sau mọi chữ nằm trên 3D, và mực đậm `#3B2630`.

## 3. Cấu trúc — 7 màn cuộn

| # | Màn | Chữ được phép | Animation làm việc gì |
|---|---|---|---|
| 0 | **Hero** | headline 2 dòng + 1 nút `BẮT ĐẦU` | Camera trôi rất chậm; sương bò trong thung lũng; **hàng chục pin mờ** rải khắp đồi = "nghìn chỗ đẹp" |
| 1 | **842 → 5** | `842 → 5` (số tự đếm) + 1 dòng | Pin sáng dồn, rồi **tắt dần còn 5 pin** sáng rõ có nhãn; tuyến bắt đầu nối |
| 2 | **Hiểu chuyến đi** | nhãn + tiêu đề ≤6 từ | Chip quy tắc (có khóa) và chip sở thích (viền đứt) **bay vào thẻ**; hai loại rơi vào hai vùng khác nhau |
| 3 | **Bằng chứng** | nhãn + `MỖI CÂU, MỘT CLIP.` | Một nhận định mở ra: thanh tỉ lệ chạy tới 74%, số comment **đếm lên**, 3 clip thật trượt vào; đường dẫn nối comment → clip |
| 4 | **Khả thi** | nhãn + `ĐI ĐƯỢC KHÔNG, NÓI THẲNG.` | Meter **tràn** qua vạch; chọn một cách sửa thì meter **co lại** vừa khung |
| 5 | **Lịch trình** | nhãn + `MỘT NGÀY ĐI ĐƯỢC TRÔNG NHƯ THẾ NÀY.` | Tuyến **vẽ dần** trên địa hình; thẻ timeline trượt vào; **đường dẫn từ pin số 2 chạy lên đúng dòng số 2** của thẻ |
| 6 | **CTA** | headline 2 dòng + nút + `Không cần tài khoản.` | Mặt trời lên hẳn, vệt nắng trải trên hồ; tuyến 5 điểm đã hoàn chỉnh |

Sau màn 6: **Hỏi nhanh** (4 dòng accordion, gập hết, mở sẵn 1) và footer mận. Khối "SẮP CÓ" (Khám phá Đà Lạt · Nhật ký chuyến đi · Thêm thành phố, đều gắn `chưa mở`) đặt **trước** CTA cuối — nó công bố lộ trình mà không hứa hão, và khớp 1-1 với các ô trong Trang chủ của app.

Những thứ **bỏ khỏi landing cũ**: đoạn mô tả dài ở mỗi beat, hai chú thích hai bên mỗi beat (giữ tối đa 2 chú thích **ngắn**, chỉ ở beat 3 và 5), dải 4 clip nhét trong hero (chuyển thành beat 3).

## 4. Animation — quy tắc

- **Dẫn động bằng cuộn, không tự chạy.** Người dùng cuộn tới đâu, cảnh chạy tới đó (ScrollTrigger `scrub`). Không có animation vô hạn ngoài sương và trôi camera.
- **Một ý một beat.** Mỗi beat chỉ có một chuyển động mang nghĩa; mọi thứ khác đứng yên.
- **Chuyển động phải nói được bằng lời nếu bị hỏi.** "Pin tắt còn 5" = *shortlist*. "Meter co lại" = *cách sửa có giá*. Chuyển động không giải thích được thì bỏ.
- **`prefers-reduced-motion: reduce`**: tắt scrub, tắt sương, tắt bay chip; mỗi beat về **một ảnh tĩnh ở trạng thái cuối** và vẫn đọc hiểu được trọn vẹn. Đây là bắt buộc, không phải tuỳ chọn.
- **Ngân sách hiệu năng:** 3D ở 60fps trên laptop tích hợp; rớt dưới ngưỡng thì hạ số pine instance trước, hạ sương sau, **không** hạ độ phân giải chữ.
- **Mobile:** không chạy 3D. Thay bằng một ảnh tĩnh của chính cảnh đó (render sẵn), các beat vẫn cuộn và vẫn đổi thẻ sản phẩm.

## 5. Ràng buộc nội dung

- Ảnh địa điểm trên landing là **frame clip thật** của chính nơi đó (`data/tiktok/videos/<id>/frames/`), luôn kèm `@creator` và link về clip gốc. Không ảnh stock, không ảnh AI vẽ nơi có thật.
- Video demo (`web/public/media/demo.mp4`) quay từ app **cũ** (giấy kem + xanh thông). Sau khi app restyle sang trắng hồng, **phải quay lại** bằng `web/scripts/record_demo.mjs`, nếu không landing hồng mà video xanh.
- Số trên landing lấy từ build thật. Nếu không có số đối chứng (ví dụ "độ chính xác mẫu kiểm") thì **bỏ ô đó**, không điền số đẹp.

## 6. Ảnh dựng thử

Trong `docs/design/desktop/v3-rose-photo/`:

| File | Là gì |
|---|---|
| `15-landing-hero-3d.png` | hero có 3D nhuộm hồng, bản còn nhiều chữ |
| `17-hero-min.png` | hero rút chữ tối thiểu + mặt trời vàng |
| `18-beat-pins.png` | beat `842 → 5`, gần như không chữ |
| `19-beat-evidence.png` | beat bằng chứng, clip thật |
| `16-landing-beat-3d.png` | beat lịch trình, đường dẫn pin → thẻ |
| `20-cta-min.png` | CTA cuối |
| `13-landing-close.png` | Hỏi nhanh + SẮP CÓ + footer |

Ảnh là **bản dựng ý tưởng**: bố cục, màu, mật độ chữ để duyệt — không phải asset dùng được.
