# Novel Translator Studio

**Aiko App Translator · Tác giả Akira Satoh (@akira3175) · Copyright © 2026**

Thông tin tác giả: GitHub https://github.com/akira3175 · Hako https://docln.sbs/thanh-vien/21133

Bản chính thức được phát hành miễn phí tại https://github.com/akira3175/Aiko-App-Translator. Dự án sử dụng PolyForm Noncommercial License 1.0.0; xem `LICENSE`.

Web app cục bộ bọc quanh bộ script dịch hiện có.

Mỗi truyện nằm trong thư mục riêng: `truyen/<ten-truyen>/raw` và `truyen/<ten-truyen>/translated`. App tự nhận diện và cho phép đổi truyện từ thanh bên.

## Mở app

Tải và chạy `Aiko-Launcher.exe`. Launcher duy nhất này cài hoặc cập nhật gói portable, xác minh SHA-256, mở ứng dụng tại `http://127.0.0.1:8765`, khởi động lại, tạo shortcut và tắt server. Python, Chrome và dữ liệu ứng dụng được quản lý bên trong, người dùng không cần mở thêm launcher thứ hai.

Khi chạy trực tiếp từ mã nguồn, dùng `start_app.bat` hoặc:

```powershell
python app.py
```

Không cần cài package web. Các pipeline AI vẫn dùng dependency của những script Python cũ.

## Module

- Không gian dịch: đọc bản gốc, biên tập và tự động lưu bản dịch.
- Kho chương: tìm kiếm, xem trạng thái và mở chương.
- Quy trình AI: chạy dịch, review, cập nhật nhân vật và xuất bản thảo.
- Pipeline theo công đoạn: chọn riêng Gemini API, Gemini Web, OpenAI API hoặc ChatGPT Web cho từng bước được hỗ trợ.
- Có thể dịch lại chương đang mở; app sao lưu và tự khôi phục bản cũ nếu engine lỗi.
- Công cụ dự án: tạo context V1/GPT, glossary và tách review.
- Form trên web thay thế các câu hỏi `input()` của review, tách review và bước xác nhận đăng nhập trình duyệt.
- Review của chương được xem trực tiếp trong không gian dịch.
- Có thể thêm truyện mới bằng cách upload EPUB; app tự tạo project và split chương.
- Ảnh EPUB dùng ID thời gian duy nhất và hiển thị trực tiếp trong không gian dịch.
- Editor hỗ trợ Markdown `**in đậm**`, `*in nghiêng*`, Ctrl+B/Ctrl+I và xem trước ảnh ngay trong nội dung.
- Thuật ngữ: chỉ dẫn tới bộ nhớ thuật ngữ hiện có.
- Cài đặt: bật/tắt tự động lưu.
