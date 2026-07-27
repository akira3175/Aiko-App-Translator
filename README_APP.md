# Novel Translator Studio

Web app cục bộ bọc quanh bộ script dịch hiện có.

Mỗi truyện nằm trong thư mục riêng: `truyen/<ten-truyen>/raw` và `truyen/<ten-truyen>/translated`. App tự nhận diện và cho phép đổi truyện từ thanh bên.

## Mở app

Nhấp đúp `start_app.bat`. Trình duyệt sẽ tự mở tại `http://127.0.0.1:8765`.

Hoặc chạy:

```powershell
python app.py
```

Không cần cài package web. Các pipeline AI vẫn dùng dependency của những script Python cũ.

## Module

- Không gian dịch: đọc bản gốc, biên tập và tự động lưu bản dịch.
- Kho chương: tìm kiếm, xem trạng thái và mở chương.
- Quy trình AI: chạy dịch, review, cập nhật nhân vật và xuất bản thảo.
- Engine dịch: V1 Gemini API, V2 Gemini Web, V3 Gemini Web batch và GPT ChatGPT Web.
- Có thể dịch lại chương đang mở; app sao lưu và tự khôi phục bản cũ nếu engine lỗi.
- Công cụ dự án: tạo context V1/GPT, glossary và tách review.
- Form trên web thay thế các câu hỏi `input()` của review, tách review và bước xác nhận đăng nhập trình duyệt.
- Review của chương được xem trực tiếp trong không gian dịch.
- Có thể thêm truyện mới bằng cách upload EPUB; app tự tạo project và split chương.
- Ảnh EPUB dùng ID thời gian duy nhất và hiển thị trực tiếp trong không gian dịch.
- Editor hỗ trợ Markdown `**in đậm**`, `*in nghiêng*`, Ctrl+B/Ctrl+I và xem trước ảnh ngay trong nội dung.
- Thuật ngữ: chỉ dẫn tới bộ nhớ thuật ngữ hiện có.
- Cài đặt: bật/tắt tự động lưu.
