# Aiko App Translator

Ứng dụng hỗ trợ dịch, biên tập, review và xuất bản tiểu thuyết trong một workspace chạy cục bộ.

> **Aiko App Translator được phát hành chính thức hoàn toàn miễn phí. Không trả tiền cho bên thứ ba để tải bản chính thức.**

Nguồn phát hành chính thức duy nhất: [akira3175/Aiko-App-Translator](https://github.com/akira3175/Aiko-App-Translator).

## Tải và cài trên Windows

**[Tải Aiko Launcher (.exe)](https://github.com/akira3175/Aiko-App-Translator/releases/download/launcher-v1.0.3/Aiko-Launcher.exe)** · [Tải bản portable đầy đủ](https://github.com/akira3175/Aiko-App-Translator/releases/latest)

1. Tải `Aiko-Launcher.exe` và lưu ở nơi dễ tìm. Launcher dành cho Windows x64, không cần cài Python riêng.
2. Mở EXE, chọn **Tải và cài Aiko**. Có thể đổi nơi cài qua **⋯ → Chọn thư mục trống để cài mới**.
3. Cài xong, chọn **Mở Aiko** để sử dụng trong trình duyệt.

Nếu đã có bản portable, chọn **⋯ → Chọn thư mục Aiko hiện có**. Khi có phiên bản mới, dùng **Cập nhật Aiko**; lưu công việc và dừng các tác vụ trước khi cập nhật.

Launcher đã nhúng ảnh dự phòng và font, chỉ cần tải một file EXE. Phiên bản launcher được phát hành riêng; các bản cập nhật ứng dụng vẫn nằm trong release portable. Có thể tải file SHA-256 tại [trang phát hành launcher](https://github.com/akira3175/Aiko-App-Translator/releases/tag/launcher-v1.0.3).

## Chạy từ mã nguồn

Yêu cầu Python 3.10:

```powershell
python -m pip install -r requirements-portable.txt
python app.py
```

Sau đó mở `http://127.0.0.1:8765`.

## Bản portable

Chạy `build_release.ps1` để tạo gói Windows x64 trong thư mục `release`.

Dữ liệu truyện, cài đặt cục bộ và API key không được đưa vào repository hoặc gói phát hành.

## Giấy phép

Phần mã nguồn do dự án sở hữu được cấp phép theo [PolyForm Noncommercial 1.0.0](LICENSE): cho phép sử dụng, chỉnh sửa và phân phối vì mục đích phi thương mại; không cho phép khai thác thương mại khi chưa có sự đồng ý bằng văn bản. Thành phần bên thứ ba tiếp tục tuân theo giấy phép riêng.
