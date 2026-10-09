# Font của deck TripGuardian

Deck dùng ba họ font: **Lora**, **Be Vietnam Pro** và **JetBrains Mono**. Các file TTF trong thư mục này được lấy từ kho Google Fonts chính thức; giấy phép OFL của từng họ font được lưu kèm bên cạnh.

## Khi mở file HTML

Không cần cài font. `TripGuardian Pitch.html` nạp trực tiếp các file local bằng `@font-face` và không phụ thuộc mạng.

## Khi mở file PowerPoint

Exporter tạo text và shape chỉnh sửa được nhưng **không nhúng font vào PPTX**. Cần cài toàn bộ tám file `.ttf` trước khi mở `TripGuardian-Pitch.pptx`; nếu không, PowerPoint hoặc LibreOffice có thể thay font, làm thay đổi xuống dòng và bố cục.

### Windows

1. Chọn toàn bộ file `.ttf`.
2. Nhấp chuột phải và chọn **Install for all users** hoặc **Install**.
3. Đóng rồi mở lại PowerPoint.

### macOS

1. Mở **Font Book**.
2. Chọn **File → Add Fonts to Current User**.
3. Chọn toàn bộ file `.ttf`, sau đó mở lại PowerPoint.

### Linux

Sao chép các file `.ttf` vào thư mục font của người dùng, chạy `fc-cache -f`, rồi mở lại LibreOffice hoặc ứng dụng trình chiếu.

## Danh sách file

- Lora: Regular, SemiBold
- Be Vietnam Pro: Regular, Medium, SemiBold, Bold
- JetBrains Mono: Medium, Bold
