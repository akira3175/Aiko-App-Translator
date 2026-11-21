# Novel Translator Studio - bản portable Windows

**Aiko App Translator · Tác giả: Akira Satoh (@akira3175) · Copyright © 2026**

Thông tin tác giả: GitHub https://github.com/akira3175 · Hako https://docln.sbs/thanh-vien/21133

Ứng dụng chính thức luôn miễn phí và chỉ được phát hành tại
https://github.com/akira3175/Aiko-App-Translator. Không trả tiền cho bên thứ ba để tải bản chính thức. Việc sử dụng và phân phối thương mại cần có sự cho phép bằng văn bản của tác giả. Xem `LICENSE`.

## Khởi động

1. Mở `Aiko-Launcher.exe` được phát hành riêng.
2. Lần đầu, chọn **Cài đặt Aiko** để launcher tải và cài app. Những lần sau, launcher sẽ kiểm tra cập nhật và mở ứng dụng.
3. App tự mở tại `http://127.0.0.1:8765`.

Launcher duy nhất này cũng cho phép khởi động lại, tắt server và tạo shortcut. Máy không cần cài Python hoặc Chrome.
Gói ZIP app không kèm launcher. Nếu cài thủ công, giải nén toàn bộ ZIP vào thư mục có quyền ghi và chạy `start_app.bat`.

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

### Ảnh SFACG khi đăng Hako

Khi đăng Hako, app tự nhận thẻ `[img=536,887]https://…[/img]` hoặc `[img]https://…[/img]`, kể cả URL bị escape thành `https\://…`. Ảnh được tải vào thư mục `image` của truyện, kiểm tra định dạng rồi đưa lên Cloudflare R2 bằng cấu hình Xuất bản hiện có. Ảnh giữ đúng vị trí trong nội dung và được lưu lại để tránh tải lại cùng URL. Nếu tải ảnh hoặc upload R2 thất bại, chương đó dừng đăng để tránh thiếu ảnh. Không cần sửa file bản dịch.

### Tự chuyển link Gemini Web / Google AI Studio Web

Trong tab cài đặt của từng dịch vụ, bật **Tự chuyển link**, nhập mỗi link trên một dòng và đặt ngưỡng phút hoặc số chương. Nhập `0` để bỏ qua một ngưỡng; cần ít nhất một ngưỡng lớn hơn `0`. Nếu đặt cả hai, ngưỡng nào đạt trước sẽ kích hoạt chuyển. Danh sách chỉ nhận link HTTPS của đúng dịch vụ, có thể là link tài khoản, cuộc trò chuyện, Gem hoặc prompt đã lưu.

Quy trình dịch bắt đầu từ link đầu, giữ link trong các bước xử lý chương và chỉ chuyển trước chương tiếp theo sau khi lưu thành công. Không tính chương bị lỗi lưu hoặc bị bỏ qua. Bật **Quay vòng danh sách** để trở về link đầu; tắt để giữ link cuối. Mỗi dịch vụ có bộ đếm riêng và bộ đếm bắt đầu lại mỗi lần chạy tác vụ. Các tác vụ riêng ngoài quy trình dịch dùng link đầu, không tự chuyển theo số chương hay thời gian.

Lưu cài đặt trước khi bắt đầu tác vụ mới. Hãy đăng nhập sẵn các tài khoản trong trình duyệt mà app sử dụng. App mở nguyên link đã nhập và tiếp tục gửi prompt/ngữ cảnh theo luồng hiện có; không tự tạo cuộc trò chuyện mới nếu link trỏ đến một cuộc trò chuyện đã lưu.

**Chuyển link khi gặp lỗi** là tùy chọn riêng trong mỗi tab Gemini Web / Google AI Studio Web, mặc định tắt. Có thể bật chỉ tùy chọn này và nhập danh sách link, không cần đặt ngưỡng phút/chương. Khi nhận diện thông báo hết usage/quota, app chuyển ngay; upload hoặc kết nối bị lỗi sẽ thử lại trên link hiện tại trước khi chuyển. App gửi lại nguyên prompt và tài liệu của bước đang chạy, không chạy lại những bước trước đó. Link thành công được giữ cho bước tiếp theo.

Trong mỗi đợt lỗi, mỗi URL chỉ được thử một lượt (với số lần thử lại nội bộ), kể cả khi bật quay vòng định kỳ. Hết danh sách thì dừng tác vụ và báo lỗi. Lỗi định dạng nội dung và lỗi lưu file không kích hoạt đổi link. Nhận diện quota dựa trên thông báo giao diện có thể đọc được; nếu dịch vụ đổi cách hiển thị, app có thể chỉ chuyển sau khi hết thời gian chờ. Kết quả bước trước được giữ trong lần chạy hiện tại; đây không phải chức năng lưu checkpoint để tiếp tục sau khi đóng app.

## Yêu cầu

- Windows 10/11 64-bit.
- Có kết nối internet khi dùng dịch AI và Google Translate.
- Giải nén trước khi chạy, không chạy trực tiếp bên trong file ZIP.
