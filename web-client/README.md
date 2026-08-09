# Novel Translator Web Client

Bản Web Client chạy hoàn toàn trong trình duyệt. Dữ liệu dự án được lưu bằng IndexedDB và chỉ rời thiết bị khi người dùng gửi nội dung đến Gemini API hoặc tự xuất bản sao.

## Chức năng chính

- Nhập truyện từ EPUB theo thứ tự spine hoặc từ TXT có tiêu đề chương phổ biến.
- Thêm chương vào truyện đang mở bằng EPUB/TXT, dùng chương trùng làm điểm neo để đề xuất phần mới và cho duyệt range trước khi nhập.
- Lưu ảnh EPUB dạng Blob trong IndexedDB và hiển thị ngay trong Preview của chương.
- Biên tập song song bản gốc và bản dịch bằng CodeMirror.
- Dịch theo pipeline: tiêu đề và nội dung, hiệu đính, sửa chữ ngoại ngữ còn sót, cập nhật xưng hô và review.
- Dùng ba chương dịch gần nhất làm ngữ cảnh và chỉ gửi glossary liên quan đến chương hiện tại hoặc chương kế tiếp.
- Kiểm tra marker đầu ra, retry tối đa ba lượt và tự luân phiên nhiều Gemini API key.
- Chỉnh riêng model, giới hạn token và system prompt cho từng tác vụ AI.
- Mặc định dùng cùng model với app local; giới hạn token để trống cho Gemini tự chọn.
- Tạo hồ sơ nhân vật và cập nhật Context V1 bằng Gemini.
- Hồ sơ nhân vật chạy incremental theo batch tùy chỉnh 1–100 chương (mặc định 10), kiểm tra marker, merge theo tên và bảo toàn trường cũ.
- Glossary chạy incremental theo batch tùy chỉnh 1–100 chương (mặc định 30), yêu cầu START/END, merge theo nguyên văn và vẫn cho phép tìm/thêm/sửa/xóa thủ công.
- Sao lưu và khôi phục bằng ZIP tương thích dự án app local (`raw`, `translated`, `image`, `characters.md`, `char_index.yaml`, `context.yaml`, `pronouns.yaml`, `review.yaml`).

## Chạy cục bộ

```powershell
npm install
npm run dev
```

## Build

```powershell
npm run build
```

Thư mục phát hành là `dist`.

## Netlify

Kết nối repository với Netlify. File `netlify.toml` ở gốc repo đã đặt base directory là `web-client`, build command là `npm run build`, và publish directory là `dist`.

## API key

Mặc định API key chỉ tồn tại trong `sessionStorage` cho đến khi đóng tab. Nếu người dùng bật ghi nhớ, key được lưu trong IndexedDB trên thiết bị. Không nhúng API key chung vào mã client.
