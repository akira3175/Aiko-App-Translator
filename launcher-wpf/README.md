# Launcher có tải và cập nhật

## Dùng bản thử

- Chạy `release/Aiko-Launcher.exe`. EXE đã nhúng ảnh dự phòng, không cần thư mục `Assets` bên cạnh.
- Chưa cài Aiko: chọn **Tải và cài Aiko**. Menu **⋯ → Chọn thư mục trống để cài mới** để đổi nơi cài.
- Đã có bản portable: chọn **⋯ → Chọn thư mục Aiko hiện có**, sau đó **Cập nhật Aiko** khi có bản mới.
- Có thể mở bản đang dùng từ **⋯ → Mở ứng dụng hiện tại**, kể cả khi chưa tải được thông tin GitHub.
- Lưu công việc và dừng các tác vụ trước khi cập nhật. Có nút **Hủy tải** trong lúc tải/giải nén. Giai đoạn thay file không cho đóng launcher giữa chừng.

## Cơ chế

### Ảnh, font và loading

Launcher ưu tiên avatar và bìa online đã lưu trong %LOCALAPPDATA%/Aiko Launcher/artwork. Nếu cache thiếu hoặc hỏng, dùng ảnh nhúng trong EXE làm dự phòng offline. Mỗi lần mở đều kiểm tra cả hai ảnh online ở nền; ảnh mới được lưu cho lần mở sau, không đổi hình giữa phiên. Font Be Vietnam Pro Medium được nhúng trong EXE, không cần Assets bên cạnh. Khung ghi chú cao cố định 206; nội dung dài cuộn bên trong. Khi kiểm tra phiên bản, hiện ba chấm chuyển động; ghi chú hiện nhẹ trong 180ms, không trượt bố cục.

Nguồn ảnh online:

- https://raw.githubusercontent.com/akira3175/Aiko-App-Translator/main/web/assets/anime/aiko-blue-logo.png
- https://raw.githubusercontent.com/akira3175/Aiko-App-Translator/main/web/assets/anime/aiko-launcher-background.png

### Cập nhật chương trình

Phần “Có gì mới” hiển thị Markdown bằng WPF: tiêu đề, danh sách, chữ đậm/nghiêng/gạch ngang, code, trích dẫn và liên kết HTTP/HTTPS. Không diễn giải HTML/XAML từ release. Nội dung chỉ dựng lại khi ghi chú thay đổi để giữ vị trí cuộn trong lúc tải.

Launcher dùng .NET để lấy release mới nhất từ `akira3175/Aiko-App-Translator`, tải gói Windows, kiểm tra kích thước và SHA-256 do GitHub cung cấp, giải nén riêng rồi thay phần chương trình. Không gọi PowerShell hoặc cmd trong luồng này. SHA-256 kiểm tra tính toàn vẹn; bản thử chưa có chữ ký số nhà phát hành.

Bản thử giữ cấu trúc portable hiện tại. Nó giữ nguyên `data`, `truyen`, các file dữ liệu cũ, cấu hình upload và EXE/ảnh của launcher đã cài. Không tự thay launcher đang chạy. Đường dẫn mã nguồn có `.git` bị từ chối cập nhật.

Trước khi thay file, launcher kiểm tra tiến trình giữ cổng 8765 thuộc đúng runtime đã chọn, không còn tác vụ chạy và server đã thoát. Sau đó nó chạy bản mới, kiểm tra phiên bản và PID giữ cổng. Nếu thất bại, nó dừng đúng tiến trình thử vừa tạo và khôi phục phần chương trình cũ.

Sao lưu được giữ trong `<thư mục Aiko>/.runtime/launcher-updates/<mã lần cập nhật>/backup`. Bản thử chưa tự dọn các bản sao lưu cũ. Cần chừa dung lượng cho gói tải, phần giải nén và bản sao lưu.

Nếu mất điện hoặc tiến trình bị kết thúc giữa lúc thay file, `launcher-update-pending.txt` trong `.runtime` ghi đường dẫn sao lưu và các mục đã bắt đầu thay. Launcher chặn mở/cập nhật tiếp để tránh chạy bản không hoàn chỉnh. Trường hợp này cần kiểm tra và khôi phục thủ công từ sao lưu; không xóa nhật ký hoặc sao lưu trước khi khôi phục xong.

Nút cập nhật trong giao diện web vẫn dùng updater hiện có. Luồng .NET mới nằm trong EXE launcher.

## Build và kiểm tra

```powershell
.\build_launcher.ps1
.\tests\test_launcher_updater.ps1
.\tests\test_launcher_artwork.ps1
.\tests\test_launcher_markdown.ps1
python -m unittest tests.test_launcher_service tests.test_update_service tests.test_update_ui
```

Kiểm tra mạng và runtime thật (tải khoảng 320 MB, lưu trong `release/launcher-tests`):

```powershell
.\tests\test_launcher_updater.ps1 -Live
```

Live test chỉ đổi cổng của bản sao controller/app thử thành 18765, dùng thư mục dữ liệu riêng và không đổi phiên Aiko đang chạy ở cổng 8765. Test thực hiện tải/kiểm tra gói thật, cài mới, khởi động Python, thay file chương trình và phục hồi sau lỗi khởi động có chủ đích. Các ca lỗi ZIP, digest, file khóa và dữ liệu được kiểm tra bằng fixture riêng.

Việc build có thể dùng PowerShell trên máy phát triển; người dùng không cần PowerShell cho tải/cập nhật từ launcher. Quét Defender sạch trên một máy không bảo đảm mọi máy hoặc SmartScreen đều chấp nhận EXE chưa ký số.
