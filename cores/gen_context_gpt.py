"""
gen_context_gpt.py
==================
Tạo Glossary qua ChatGPT Web thay vì Gemini Web.
Logic y hệt gen_context_v1.py — chỉ thay Gemini bằng ChatGPT.
"""

import os
import sys
import time

# Thêm thư mục gốc vào sys.path
root_dir = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
if root_dir not in sys.path:
    sys.path.insert(0, root_dir)

from cores.context_workflow import run_context_generation
from cores.runtime_config import int_option

if sys.stdout.encoding != "utf-8":
    try:
        sys.stdout.reconfigure(encoding="utf-8")
    except AttributeError:
        import io

        sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding="utf-8")

from cores.dich_utils import (
    CONTEXT_YAML,
    RAW_DIR,
    close_chatgpt_driver,
    generate_content_with_chatgpt,
    get_chatgpt_driver,
    setup_chatgpt_browser,
)

# ====== Cấu hình ======
CONTEXT_FILE = CONTEXT_YAML  # file context riêng của truyện đang chọn
BATCH_SIZE = int_option("batch_size", 30, minimum=1)


# ====== Hàm đọc/ghi YAML (chỉ dùng cho context.yaml) ======


# ====== Hàm gọi ChatGPT web tạo glossary ======
def generate_glossary(chapters, old_glossary):
    """chapters: list of chapter dict (từ load_md_chapter hoặc tương thích)."""
    content = "\n\n".join(
        [
            f"{c.get('title', '')}\n{c.get('content', '')}"
            for c in chapters
            if c.get("content")
        ]
    )

    if not content.strip():
        print("⚠️ Batch này không có content, bỏ qua.")
        return ""

    prompt = f"""
# 🧙 Vai trò
Bạn là **công cụ hỗ trợ dịch thuật chuyên cho truyện fantasy Hàn**.

---

# 🧾 Nhiệm vụ
Hãy **trích xuất và bổ sung BẢNG THUẬT NGỮ (Glossary)** từ văn bản sau:

---
{content}
---

---

# ⚙️ Yêu cầu chi tiết

1. **Trích xuất** tất cả các:
   - Thuật ngữ
   - Danh hiệu
   - Xưng hô
   - Tên riêng
   - Địa danh  
   trong đoạn **raw Hàn** ở trên.

2. **Bỏ qua** những từ:
   - Phổ thông, vật dụng đời thường.
   - Nghề nghiệp chung hoặc từ đã quen thuộc trong tiếng Việt.

3. **Chuyển đổi và dịch:**
   - Nếu là **tên riêng ngoại lai**, hãy **chuyển về dạng La-tinh gốc** → `卡洛斯 = Carlos`
   - Nếu là **thuật ngữ, danh hiệu, địa danh**, hãy **dịch sang phong cách tiếng Việt hiện đại**.

4. **Quy tắc viết hoa/thường tiếng Việt** (bắt buộc tuân thủ):
   - **Tên riêng người, địa danh**: Viết hoa chữ cái đầu của **mỗi âm tiết** → `Lăng Phàm`, `Gia Tộc Chasefield`, `Vương Quốc Cát`
   - **Danh hiệu, chức vị kèm tên riêng hoặc đứng như tên gọi**: Viết hoa mỗi âm tiết → `Kiếm Thánh`, `Hồng Y Xám`, `Đại Công Tước`, `Hầu Tước Anastasia`
   - **Tên kỹ năng/pháp thuật**: Viết hoa mỗi âm tiết → `Tâm Nhãn`, `Ngôn Linh`, `Cương Thể Thuật: Wind Talker`, `Long Tiêm`
   - **Danh từ chung / khái niệm thông thường**: Chỉ viết **thường** → `ma thú`, `dũng sĩ`, `hồi quy giả`, `ma lực`, `mana`, `tử khí`
   - **Chức vị/xưng hô thông thường không kèm tên riêng**: Viết **thường** → `hoàng tử`, `hoàng nữ`, `thần quan`, `kỵ sĩ`, `sứ đồ`
   - **Từ tiếng Anh/Latin**: Giữ nguyên quy tắc viết hoa của ngôn ngữ gốc → `Demon Hunter`, `Paladin`, `Death March`, `System Log`

---

## 📜 Glossary cũ để tham khảo (giữ nhất quán viết hoa/thường với các entry đã có)
{old_glossary}

---

# ⚠️ Định dạng đầu ra
> TUYỆT ĐỐI KHÔNG thêm bất kỳ câu giao tiếp nào (ví dụ: "Dưới đây là...", "Mình sẽ lọc...").
> KHÔNG dùng công cụ Python (Advanced Data Analysis) để đọc file, hãy đọc trực tiếp và in ra kết quả ngay lập tức trong 1 lần trả lời.
> Chỉ xuất **thuần văn bản**, mỗi dòng một mục, theo dạng:
原文 = Dịch

Bắt đầu glossary bằng dòng `###START###` và kết thúc bằng dòng `###END###`.
"""

    max_retries = 3
    for attempt in range(max_retries):
        if attempt > 0:
            print(f"🔄 Thử lại lần {attempt + 1}/{max_retries}...")
            driver = get_chatgpt_driver()
            driver.get("https://chatgpt.com/")
            time.sleep(3)

        resp = generate_content_with_chatgpt(prompt)
        if not resp:
            resp = ""

        if "###START###" not in resp or "###END###" not in resp:
            print(
                f"⚠️ Dữ liệu Glossary bị cắt ngang (thiếu START hoặc END) (lần {attempt + 1})."
            )
            if attempt < max_retries - 1:
                time.sleep(5)
                continue
            else:
                raise ValueError(
                    f"AI không trả về đủ START và END sau {max_retries} lần thử"
                )

        return resp.strip()

    return ""


# ====== Hàm merge glossary ======


# ====== Main ======
def main():
    return run_context_generation(
        engine_name="ChatGPT Web",
        setup_browser=setup_chatgpt_browser,
        close_browser=close_chatgpt_driver,
        generate_glossary=generate_glossary,
        raw_dir=RAW_DIR,
        context_file=CONTEXT_FILE,
        batch_size=BATCH_SIZE,
    )


if __name__ == "__main__":
    main()
