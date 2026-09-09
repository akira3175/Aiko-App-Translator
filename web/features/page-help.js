export const pageHelp = {
  workspace: [
    ['Đọc và biên tập', 'Chọn truyện và chương trước khi làm việc. Dùng chế độ song song để đối chiếu bản gốc với bản dịch; chuyển chế độ khi muốn tập trung vào một bên.'],
    ['Các công cụ', 'Dùng tìm kiếm chương và nút trước/tiếp để chuyển chương. Tìm trong truyện tìm nội dung trên nhiều chương; Ctrl+F và Ctrl+H thao tác trong editor đang chọn. Chế độ tập trung mở rộng vùng đọc.'],
    ['Lưu và chạy AI', 'Lưu bản dịch bằng nút Lưu bản dịch. Khi bật tự động lưu, theo dõi trạng thái đồng bộ. Dịch lại và Hiệu đính chạy trên chương hiện tại; kiểm tra provider trước khi bắt đầu.'],
    ['Review và nhật ký', 'Mở review để đọc lỗi và đề xuất, lưu nội dung đã sửa trước khi review lại. Nhật ký AI dùng để xem yêu cầu và phản hồi của các lượt gọi được ghi nhận.'],
    ['Chú thích (note: ...) dành riêng cho Hako', 'Trong bản dịch, viết (note: nội dung chú thích) ngay tại vị trí muốn đặt chú thích. Ví dụ: Anh khoác haori(note: Áo khoác truyền thống của Nhật Bản). Có thể thêm nhiều chú thích trong cùng chương.'],
    ['Xuất bản chú thích bằng app', 'Lưu bản dịch, rồi đăng chương qua tác vụ xuất bản Hako trong Quy trình AI hoặc cập nhật bằng Edit chương Hako. App tạo ghi chú trên Hako và thay từng đoạn (note: ...) bằng mã ghi chú tại đúng vị trí. Bạn không cần tự tạo hoặc nhập ID ghi chú. Cơ chế này dành cho quy trình xuất bản Hako trong app; dán văn bản trực tiếp lên Hako không thực hiện bước chuyển đổi này.'],
    ['Cách viết nội dung chú thích', 'Không để nội dung chú thích trống. Không lồng dấu ngoặc tròn trong chú thích: app kết thúc chú thích ở dấu ) đầu tiên. Nếu cần phân tách ý bên trong, dùng dấu gạch ngang hoặc ngoặc vuông. Trong Không gian dịch, bạn vẫn soạn và đọc cú pháp (note: ...); việc chuyển thành ghi chú Hako diễn ra khi xuất bản.'],
  ],
  chapters: [
    ['Tìm và mở chương', 'Chọn truyện ở thanh bên. Nhập tên chương hoặc mã file vào ô tìm kiếm để lọc danh sách, rồi bấm một chương để mở trong Không gian dịch. Trạng thái từng dòng cho biết tiến độ dịch.'],
    ['Thêm chương', 'Bấm + Thêm chương, chọn EPUB/TXT và phân tích file. Kiểm tra khoảng chương nguồn, volume đích, số chương bắt đầu và cách xử lý chương trùng trước khi xác nhận nhập.'],
    ['Xuất truyện', 'Chọn EPUB, DOCX hoặc Markdown; chọn bản dịch, bản gốc hoặc song ngữ và phạm vi xuất. Kiểm tra phần tổng kết trước khi tải file.'],
    ['Chương trùng', 'Chọn bỏ qua nếu muốn giữ dữ liệu hiện có. Chỉ chọn ghi đè khi đã kiểm tra ánh xạ nguồn và đích trong cửa sổ nhập.'],
  ],
  terminology: [
    ['Thuật ngữ của truyện', 'Trang này quản lý glossary và ghi chú phong cách của truyện đang mở. Tìm theo nguyên văn hoặc bản dịch để định vị mục cần sửa.'],
    ['Thêm, sửa và lưu', 'Bấm + Thêm để tạo mục, hoặc sửa trực tiếp mục hiện có. Bấm Lưu thay đổi sau khi chỉnh; kiểm tra trạng thái lưu trước khi chuyển truyện.'],
    ['Nạp glossary', 'Dán mỗi thuật ngữ trên một dòng theo dạng Raw = Dịch. Mục trùng được cập nhật, vì vậy hãy kiểm tra bản dịch của các thuật ngữ đã có.'],
    ['Chỉnh context', 'Dùng các tab để sửa tiến độ context, ghi chú phong cách, prompt dịch, prompt hiệu đính hoặc glossary. Đọc chú thích từng trường; bấm Kiểm tra và lưu an toàn để xác nhận.'],
  ],
  characters: [
    ['Hồ sơ nhân vật', 'Hồ sơ thuộc truyện đang mở. Ghi tên, đặc điểm, vai trò và quan hệ bằng Markdown để tiện đọc và chỉnh sửa.'],
    ['Soạn thảo và xem trước', 'Soạn thảo cho phép sửa văn bản; Preview Markdown hiển thị cách trình bày. Bấm Lưu hồ sơ để lưu nội dung đã chỉnh.'],
    ['Phân tích bằng AI', 'Mở cấu hình tác vụ bằng nút Phân tích bằng AI. Kiểm tra phạm vi segment, provider và tùy chọn chạy lại trước khi bắt đầu. Theo dõi kết quả trong nhật ký tác vụ.'],
  ],
  pronouns: [
    ['Tìm cặp nhân vật', 'Tìm tên hoặc lọc tất cả, đã khóa, có thay đổi. Chọn một cặp để xem cách gọi hiện tại và lịch sử.'],
    ['Chiều nói', 'Kiểm tra người nói và người nghe trước khi sửa: cách A gọi B có thể khác cách B gọi A. Nhập cách tự xưng, gọi đối phương, quan hệ và giọng điệu cho đúng chiều.'],
    ['Khóa và lưu', 'Khóa quy tắc khi bạn đã xác nhận cách xưng hô để AI ưu tiên quy tắc đó. Bấm Lưu quy tắc trong biểu mẫu sau khi chỉnh.'],
    ['Dữ liệu nâng cao', 'Phần JSON dùng để kiểm tra hoặc sao chép. Dùng biểu mẫu chỉnh sửa để giữ đúng cấu trúc dữ liệu.'],
  ],
  pipeline: [
    ['Chọn nhóm công việc', 'Các tab chia tác vụ thành dịch thuật, bộ nhớ, kiểm tra chất lượng và xuất bản. Đọc tên tác vụ rồi bấm Chạy tác vụ để mở cấu hình.'],
    ['Trước khi chạy', 'Chọn truyện, kiểm tra provider, model, phạm vi chương và tùy chọn chạy lại. Tác vụ API cần cấu hình API phù hợp; tác vụ Web cần phiên trình duyệt đã đăng nhập.'],
    ['Theo dõi tiến độ', 'Nhật ký tác vụ hiển thị tiến trình và lỗi. Khi gặp lỗi, đọc thông báo để kiểm tra cấu hình hoặc phiên đăng nhập trước khi chạy lại.'],
    ['Dừng tác vụ', 'Dừng sau chương này cho phép hoàn tất chương hiện tại. Dừng ngay yêu cầu ngắt xử lý hiện tại. Kiểm tra nhật ký và dữ liệu đã lưu trước khi tiếp tục.'],
  ],
  sharing: [
    ['Chuẩn bị', 'Cài đặt R2 share mở cấu hình lưu trữ dùng cho bản đọc. Hoàn tất cấu hình trước khi tạo bản share.'],
    ['Tạo bản đọc', 'Nhập tên bản share, người nhận/watermark và số ngày hết hạn. Chọn các chương đã dịch rồi bấm Tạo bản share. Chọn tất cả giúp chọn nhanh danh sách chương.'],
    ['Quản lý bản share', 'Dùng danh sách bản share để kiểm tra bản đã tạo. Khu vực chương đang share cho phép thu hồi chương hoặc đóng bản share; kiểm tra đúng bản và chương trước khi thao tác.'],
  ],
  hakoEdit: [
    ['Tải danh sách', 'Kiểm tra tài khoản trong Cài đặt tài khoản. Dán URL trang truyện Hako và bấm Tải danh sách Hako.'],
    ['Đối chiếu chương', 'Chọn khoảng chương local và chương Hako bắt đầu tương ứng. Bấm Tạo bảng đối chiếu rồi kiểm tra từng cặp tiêu đề nguồn và đích.'],
    ['Cập nhật', 'Chọn các chương cần cập nhật, xác nhận đã đối chiếu đúng rồi bấm Cập nhật các chương đã chọn. Đây là thao tác ghi nội dung lên Hako; không xác nhận khi ánh xạ còn sai.'],
  ],
  r19: [
    ['Phạm vi cấu hình', 'Trang này quản lý danh sách từ dùng chung. Công tắc cho biết tính năng đang bật hay tắt; cấu hình áp dụng toàn cục, không riêng truyện đang mở.'],
    ['Chỉnh danh sách', 'Kiểm tra nội dung từng dòng và định dạng raw = dịch được ghi dưới ô nhập. Bấm Lưu cấu hình để lưu thay đổi; theo dõi trạng thái lưu ở đầu danh sách.'],
  ],
  settings: [
    ['Chọn nhóm cài đặt', 'Chuyển tab để cấu hình API, provider, model, xuất bản hoặc giao diện. Đọc nhãn và chú thích ngay dưới từng trường để biết phạm vi áp dụng.'],
    ['Lưu và khôi phục', 'Sau khi sửa cấu hình, bấm Lưu cấu hình. Khôi phục mặc định dùng khi muốn đưa thiết lập về giá trị mặc định; kiểm tra các trường trước khi lưu lại.'],
    ['API và trình duyệt', 'Quản lý khóa API trong nhóm tương ứng. Với provider Web, kiểm tra tài khoản đăng nhập và thiết lập trình duyệt. Kiểm tra model của từng công đoạn nếu dùng cấu hình riêng.'],
    ['Giao diện và tiện ích', 'Nhóm workspace có bảng màu, tự động lưu, truy cập cùng Wi-Fi và cập nhật ứng dụng. Đọc trạng thái hiển thị sau khi thay đổi hoặc kiểm tra cập nhật.'],
  ],
  help: [
    ['Tra cứu', 'Chọn chủ đề ở danh sách hoặc nhập công việc vào ô tìm kiếm để lọc nội dung hướng dẫn.'],
    ['Thực hiện', 'Các nút trong từng chủ đề mở trang hoặc tác vụ tương ứng. Trên mỗi trang, nút dấu hỏi cạnh tiêu đề giải thích các thao tác của chính trang đó.'],
  ],
};

const trigger = document.querySelector('#pageHelpButton');
const dialog = document.querySelector('#pageHelpDialog');
trigger.addEventListener('click', () => {
  const active = document.querySelector('.view.active');
  const key = active?.id.replace(/View$/, '');
  const sections = pageHelp[key];
  if (!sections) return;
  document.querySelector('#pageHelpTitle').textContent = 'Hướng dẫn · ' + document.querySelector('#viewTitle').textContent;
  const body = document.querySelector('#pageHelpBody');
  body.replaceChildren();
  for (const [title, text] of sections) {
    const section = document.createElement('section');
    const heading = document.createElement('h3');
    const paragraph = document.createElement('p');
    heading.textContent = title;
    paragraph.textContent = text;
    section.append(heading, paragraph);
    body.append(section);
  }
  dialog.showModal();
});
document.querySelector('#closePageHelp').addEventListener('click', () => dialog.close());
dialog.addEventListener('close', () => trigger.focus());
dialog.addEventListener('keydown', event => event.stopPropagation());
