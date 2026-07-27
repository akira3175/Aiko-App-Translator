# Novel Translator Studio - bản portable Windows

**Aiko App Translator · Tác giả: Akira Satoh (@akira3175) · Copyright © 2026**

Ứng dụng chính thức luôn miễn phí và chỉ được phát hành tại
https://github.com/akira3175/Aiko-App-Translator. Không trả tiền cho bên thứ ba để tải bản chính thức. Việc sử dụng và phân phối thương mại cần có sự cho phép bằng văn bản của tác giả. Xem `LICENSE`.

## Khởi động

1. Giải nén toàn bộ file ZIP vào một thư mục có quyền ghi.
2. Nhấp đúp `start_app.bat`.
3. App tự mở tại `http://127.0.0.1:8765`.

Không cần cài Python, package, Chrome hoặc ChromeDriver. Tất cả đã nằm trong thư mục `runtime`.

## Đăng nhập Gemini và ChatGPT

Lần đầu chạy engine Web, Chromium portable sẽ mở để bạn đăng nhập. Profile được lưu riêng tại:

```text
%LOCALAPPDATA%\NovelTranslatorStudio\profiles
```

Không chia sẻ thư mục profile này cho người khác.

## Gemini API

Nếu dùng engine V1, mở `apikeys.txt` và nhập mỗi API key trên một dòng. Không gửi file này cho người khác.

## Dữ liệu truyện

Mỗi truyện được lưu trong `truyen/<tên-truyện>`. Khi thêm truyện, có thể chọn EPUB hoặc TXT và chỉnh giới hạn segment (mặc định 5.000). Truyện Hàn/Trung/Nhật được giới hạn theo ký tự; ngôn ngữ dùng khoảng trắng như Anh/Việt được giới hạn theo từ. Gói phát hành ban đầu không chứa truyện, log, API key hoặc tài khoản của người đóng gói.

Trong **Cài đặt → Chung**, mục **Số chương trước làm ngữ cảnh dịch** quyết định số bản dịch liền trước được đưa vào prompt; mặc định là 3.

## Yêu cầu

- Windows 10/11 64-bit.
- Có kết nối internet khi dùng dịch AI và Google Translate.
- Giải nén trước khi chạy, không chạy trực tiếp bên trong file ZIP.
