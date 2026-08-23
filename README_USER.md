# Novel Translator Studio - bản portable Windows

**Aiko App Translator · Tác giả: Akira Satoh (@akira3175) · Copyright © 2026**

Thông tin tác giả: GitHub https://github.com/akira3175 · Hako https://docln.sbs/thanh-vien/21133

Ứng dụng chính thức luôn miễn phí và chỉ được phát hành tại
https://github.com/akira3175/Aiko-App-Translator. Không trả tiền cho bên thứ ba để tải bản chính thức. Việc sử dụng và phân phối thương mại cần có sự cho phép bằng văn bản của tác giả. Xem `LICENSE`.

## Khởi động

1. Giải nén toàn bộ file ZIP vào một thư mục có quyền ghi.
2. Nhấp đúp `Aiko-Launcher.exe`.
3. Lần đầu, chọn **Cài đặt Aiko**. Những lần sau, launcher sẽ kiểm tra cập nhật và mở ứng dụng.

Launcher duy nhất này cũng cho phép khởi động lại, tắt server và tạo shortcut. Máy không cần cài Python hoặc Chrome.
3. App tự mở tại `http://127.0.0.1:8765`.

Lần đầu mở, bạn có thể chọn tạo shortcut ngoài Desktop. Bảng điều khiển launcher cho phép mở app, khởi động lại, tạo shortcut Desktop/Start Menu hoặc tắt server. Đóng bảng điều khiển chỉ ẩn cửa sổ; server vẫn tiếp tục chạy. `start_app.bat` được giữ làm cách khởi động dự phòng khi cần xem lỗi chi tiết.

Không cần cài Python, package, Chrome hoặc ChromeDriver. Tất cả đã nằm trong thư mục `runtime`.

## Dùng trên điện thoại cùng Wi-Fi

1. Trên máy tính, mở **Cài đặt → Chung**.
2. Chọn **Bật trong mạng LAN** tại mục truy cập điện thoại.
3. Nhập PIN 6–12 số, hoặc để trống để app tự sinh PIN, rồi lưu.
4. Mở bảng điều khiển launcher và chọn **Khởi động lại**.
5. Nếu Windows Firewall hỏi, chỉ cho phép trên **Private networks**.
6. Trên điện thoại cùng Wi-Fi, mở địa chỉ LAN hiển thị trong Cài đặt và nhập PIN.

Chế độ LAN mặc định tắt. Không chuyển tiếp cổng 8765 trên router và không public app trực tiếp ra Internet.

## Đăng nhập Gemini và ChatGPT

Lần đầu chạy engine Web, Chromium portable sẽ mở để bạn đăng nhập. Profile được lưu riêng tại:

```text
%LOCALAPPDATA%\NovelTranslatorStudio\profiles
```

Không chia sẻ thư mục profile này cho người khác.

## Gemini API

Nếu dùng Gemini API, mở `data/apikeys.txt` và nhập mỗi API key trên một dòng. Không gửi file này cho người khác. Khi cập nhật từ bản cũ, ứng dụng tự chuyển `apikeys.txt` và `r19_words.txt` ở thư mục gốc vào `data/`.

## Dữ liệu truyện

Mỗi truyện được lưu trong `truyen/<tên-truyện>`. Khi thêm truyện, có thể chọn EPUB hoặc TXT và chỉnh giới hạn segment (mặc định 5.000). Truyện Hàn/Trung/Nhật được giới hạn theo ký tự; ngôn ngữ dùng khoảng trắng như Anh/Việt được giới hạn theo từ. Gói phát hành ban đầu không chứa truyện, log, API key hoặc tài khoản của người đóng gói.

Trong **Cài đặt → Chung**, mục **Số chương trước làm ngữ cảnh dịch** quyết định số bản dịch liền trước được đưa vào prompt; mặc định là 3.

## Yêu cầu

- Windows 10/11 64-bit.
- Có kết nối internet khi dùng dịch AI và Google Translate.
- Giải nén trước khi chạy, không chạy trực tiếp bên trong file ZIP.
