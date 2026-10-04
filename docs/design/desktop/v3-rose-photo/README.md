# Bản dựng UI desktop — trắng hồng, ảnh thật (chốt 2026-10-04)

18 màn dưới đây là **bộ đã duyệt**. Khung 1440, hệ màu trắng hồng (`docs/UI_SPEC_USER_WEB.md` §8), ảnh bìa là **frame clip thật** từ `data/tiktok/videos/<id>/frames/` kèm `@creator` thật.

Đây là **bản dựng ý tưởng** để duyệt bố cục, mật độ chữ và màu — **không phải asset dùng được**: ảnh do model vẽ lại gần giống frame gốc, không phải pixel thật.

## App — 11 màn (`docs/UI_SPEC_USER_WEB.md`)

| File | Trang | Route |
|---|---|---|
| `14-home.png` | Trang chủ (chỉ người quay lại) | `/app` |
| `06-auth.png` | Vào ứng dụng | `/app` chưa đăng nhập |
| `07-start.png` | Bắt đầu — câu 2/2 | `/app` |
| `02-understand.png` | Hiểu chuyến đi | `/app/understand` |
| `01-shortlist.png` | Gợi ý | `/app/shortlist` |
| `03-place.png` | Chi tiết địa điểm | `/app/place/:id` |
| `08-compare.png` | So sánh | `/app/compare/:ids` |
| `04-feasibility.png` | Khả thi một phần | `/app/feasibility` |
| `05-plan.png` | Lịch trình | `/app/plan` |
| `09-profile.png` | Hồ sơ và dữ liệu | `/app/profile` |
| `10-feedback.png` | Phản hồi | `/app/feedback` |

## Landing — 7 màn (`docs/UI_SPEC_LANDING.md`)

| File | Màn cuộn | Animation gánh nghĩa |
|---|---|---|
| `17-hero-min.png` | 0 · Hero | pin mờ rải khắp đồi = "nghìn chỗ đẹp" |
| `18-beat-pins.png` | 1 · `842 → 5` | pin tắt dần còn 5 = shortlist |
| — | 2 · Hiểu chuyến đi | **chưa dựng** |
| `19-beat-evidence.png` | 3 · Bằng chứng | 16 nét hội tụ về một câu = tổng hợp nhiều nguồn |
| — | 4 · Khả thi | **chưa dựng** (bản cũ ở `_archive/v3-superseded/12-landing-beat.png`, chưa có 3D) |
| `16-landing-beat-3d.png` | 5 · Lịch trình | tuyến vẽ trên đất, đường dẫn pin → dòng thẻ |
| `21-beat-mosaic.png` | 6 · Ảnh thật | mosaic 6 nơi, màu gốc, tràn hai mép |
| `20-cta-min.png` | 7 · CTA | mặt trời lên, tuyến khép |
| `13-landing-close.png` | đuôi trang | Hỏi nhanh + SẮP CÓ + footer |

## Lỗi còn trong ảnh, phải sửa khi làm thật

| File | Lỗi |
|---|---|
| `19-beat-evidence.png` | 3/4 ảnh không phải Thung lũng hoa cẩm tú cầu — ảnh phải đúng nơi đang nói |
| `16-landing-beat-3d.png` | wordmark thành "Đà Lạt", mất nav |
| `14-home.png` | "Huế chậm rãi", "Phú Yên ven biển" — MVP chỉ có Đà Lạt |
| `13-landing-close.png` | footer wordmark thành "ĐÀ LẠT" |
| `04-feasibility.png` | cảnh báo mất icon hổ phách |

## Quy tắc rút ra từ bộ này

- **Ảnh thật không bao giờ chồng lên sương 3D** — hai thứ đánh nhau. Ảnh thật đứng trong khối trắng riêng hoặc tràn mép (`21`), không nằm trong hero.
- **Ảnh thật giữ nguyên màu gốc**, không nhuộm hồng; hồng chỉ ở khe hở, nhãn, tiêu đề.
- Mỗi màn cuộn của landing: 1 nhãn ≤4 từ + 1 tiêu đề ≤6 từ + tối đa 1 dòng phụ ≤16 từ.

## Bản cũ

`../_archive/v1-pine/` giấy kem + xanh thông · `../_archive/v2-rose-nophoto/` trắng hồng chưa có ảnh thật · `../_archive/v3-superseded/` landing bản nhiều chữ và bản chưa có 3D.

Sinh bằng 9router `cx/gpt-5.6-sol` (`/images/generations`, image-to-image với frame thật). Script: `scratchpad/gen_desktop_ui_v3.py`, `gen_landing_v2.py`, `gen_landing_v3.py`.
