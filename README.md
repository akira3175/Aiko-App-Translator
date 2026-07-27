# Aiko App Translator

Ứng dụng hỗ trợ dịch, biên tập, review và xuất bản tiểu thuyết trong một workspace chạy cục bộ.

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
