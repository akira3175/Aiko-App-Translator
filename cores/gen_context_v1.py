import os
import sys
import time

import pyperclip
from selenium.common.exceptions import NoSuchElementException, TimeoutException
from selenium.webdriver.common.by import By
from selenium.webdriver.common.keys import Keys

# Thêm thư mục gốc vào sys.path
root_dir = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
if root_dir not in sys.path:
    sys.path.insert(0, root_dir)

from cores.context_workflow import run_context_generation
from cores.runtime_config import int_option

from cores.dich_utils import (
    CONTEXT_YAML,
    RAW_DIR,
    close_gemini_driver,
    get_gemini_driver,
    setup_gemini_browser,
)

# ====== Cấu hình ======
CONTEXT_FILE = CONTEXT_YAML  # file context riêng của truyện đang chọn
BATCH_SIZE = int_option("batch_size", 30, minimum=1)


def copy_response_text(driver, response_selectors):
    """Click nút Copy của Gemini response và lấy raw text từ clipboard

    Dựa trên HTML Gemini mới:
    - Nút copy có mat-icon với fonticon="content_copy"
    - Nằm trong model-response container (không phải user-query)
    - aria-label có thể là "Sao chép" hoặc "Copy"
    """
    try:
        from selenium.webdriver.common.action_chains import ActionChains

        # Tìm response element cuối cùng (model response)
        response_element = None
        for selector in response_selectors:
            try:
                elements = driver.find_elements(By.CSS_SELECTOR, selector)
                if elements:
                    response_element = elements[-1]  # Lấy response cuối cùng
                    break
            except:
                continue

        if not response_element:
            print("⚠️ Không tìm thấy response element")
            return None

        # Scroll đến response element và hover để hiện action buttons
        try:
            driver.execute_script(
                "arguments[0].scrollIntoView({block: 'center'});", response_element
            )
            time.sleep(0.3)
            ActionChains(driver).move_to_element(response_element).perform()
            time.sleep(0.8)  # Đợi buttons hiện ra
        except Exception as e:
            print(f"⚠️ Lỗi scroll/hover: {e}")

        copy_button = None

        # === PHƯƠNG PHÁP 1: Tìm trong model-response container ===
        # Dựa trên HTML: model-response chứa action buttons riêng
        model_response_copy_selectors = [
            # Nút copy trong model-response (không phải user-query)
            'model-response button mat-icon[fonticon="content_copy"]',
            'model-response button[aria-label*="Sao chép"]',
            'model-response button[aria-label*="Copy"]',
            # Response container actions
            '.model-response-text button mat-icon[fonticon="content_copy"]',
            'response-container button mat-icon[fonticon="content_copy"]',
        ]

        for sel in model_response_copy_selectors:
            try:
                elements = driver.find_elements(By.CSS_SELECTOR, sel)
                if elements:
                    # Nếu tìm thấy mat-icon, lấy parent button
                    elem = elements[-1]
                    if elem.tag_name.lower() == "mat-icon":
                        copy_button = elem.find_element(By.XPATH, "./ancestor::button")
                    else:
                        copy_button = elem
                    break
            except:
                continue

        # === PHƯƠNG PHÁP 3: XPath với loại trừ user-query ===
        if not copy_button:
            xpath_selectors = [
                # Nút copy KHÔNG nằm trong user-query-container
                '//button[contains(@aria-label, "Sao chép") and not(ancestor::*[contains(@class, "user-query")])]',
                '//button[contains(@aria-label, "Copy") and not(ancestor::*[contains(@class, "user-query")])]',
                # Fallback: tất cả nút sao chép, lấy cuối
                '//button[contains(@aria-label, "Sao chép")]',
                '//button[contains(@aria-label, "Copy")]',
            ]

            for xpath in xpath_selectors:
                try:
                    buttons = driver.find_elements(By.XPATH, xpath)
                    # Lọc: không lấy nút "Sao chép câu lệnh" (user prompt)
                    valid_buttons = [
                        b
                        for b in buttons
                        if "câu lệnh"
                        not in (b.get_attribute("aria-label") or "").lower()
                        and "prompt"
                        not in (b.get_attribute("aria-label") or "").lower()
                    ]
                    if valid_buttons:
                        copy_button = valid_buttons[-1]
                        break
                    elif buttons:
                        # Fallback: lấy cuối cùng
                        copy_button = buttons[-1]
                        break
                except:
                    continue

        # === CLICK VÀ LẤY TEXT ===
        if copy_button:
            try:
                # Scroll đến nút copy
                driver.execute_script(
                    "arguments[0].scrollIntoView({block: 'center'});", copy_button
                )
                time.sleep(0.3)

                # Hover trước khi click
                ActionChains(driver).move_to_element(copy_button).pause(
                    0.2
                ).click().perform()
                time.sleep(0.5)

                result = pyperclip.paste().strip()
                if result:
                    return result
                else:
                    print("⚠️ Clipboard rỗng sau khi click Copy")
                    return None
            except Exception as e:
                print(f"⚠️ Lỗi khi click nút Copy: {e}")
                return None

        print("⚠️ Không tìm thấy nút Copy")
        return None
    except Exception as e:
        print(f"⚠️ Lỗi khi copy: {e}")
        return None


def generate_content_with_selenium(prompt, max_retries=3):
    """Gửi prompt đến Gemini web và lấy response"""

    for attempt in range(max_retries):
        try:
            driver = get_gemini_driver()

            # Tìm ô nhập liệu
            input_selectors = [
                'div[contenteditable="true"]',
                'rich-textarea div[contenteditable="true"]',
                "textarea",
                ".ql-editor",
                'div[role="textbox"]',
            ]

            input_area = None
            for selector in input_selectors:
                try:
                    input_area = driver.find_element(By.CSS_SELECTOR, selector)
                    if input_area:
                        break
                except:
                    continue

            if not input_area:
                raise NoSuchElementException("Không tìm thấy ô nhập liệu!")

            # Click và nhập text - dùng clipboard cho prompt dài
            input_area.click()
            time.sleep(0.5)

            # Với prompt dài, dùng pyperclip + Ctrl+V
            if len(prompt) > 1000:
                pyperclip.copy(prompt)
                input_area.send_keys(Keys.CONTROL, "v")
            else:
                input_area.send_keys(prompt)

            time.sleep(1)

            # Click nút gửi - thử nhiều selectors
            send_selectors = [
                'button[aria-label*="Send"]',
                'button[aria-label*="Gửi"]',
                "button.send-button",
                'div[class*="send-button"] button',
                'button[data-test-id="send-button"]',
                'mat-icon[data-mat-icon-name="send"]',
            ]

            send_button = None
            for selector in send_selectors:
                try:
                    send_button = driver.find_element(By.CSS_SELECTOR, selector)
                    if send_button and send_button.is_enabled():
                        break
                except:
                    continue

            # Nếu không tìm thấy button, thử nhấn Enter
            if not send_button:
                input_area.send_keys(Keys.RETURN)
            else:
                send_button.click()

            print(f"📤 Đã gửi prompt ({len(prompt)} ký tự). Đang chờ response...")

            # Đợi response - đợi lâu hơn để Gemini bắt đầu streaming
            time.sleep(8)  # Đợi 8 giây cho response bắt đầu xuất hiện

            # Chờ cho đến khi response hoàn tất
            max_wait = 600  # Tối đa 10 phút cho response dài
            min_response_length = 100  # Response glossary có thể ngắn hơn translation
            start_time = time.time()
            last_text = ""
            stable_count = 0

            while time.time() - start_time < max_wait:
                # Thử lấy text từ response - dựa trên HTML thực tế của Gemini
                response_selectors = [
                    "message-content.model-response-text",
                    ".model-response-text",
                    "div.conversation-container .response-container",
                    "div.response-text",
                    ".markdown-main-container",
                ]

                # Trong vòng while, chỉ dùng .text để theo dõi streaming (không click Copy)
                current_text = ""
                for selector in response_selectors:
                    try:
                        elements = driver.find_elements(By.CSS_SELECTOR, selector)
                        if elements:
                            # Lấy element cuối cùng (response mới nhất)
                            current_text = elements[-1].text.strip()
                            if current_text:
                                break
                    except:
                        continue

                # Hiển thị tiến độ streaming
                current_len = len(current_text) if current_text else 0
                last_len = len(last_text) if last_text else 0
                if current_len > last_len:
                    print(f"\r📥 Đang nhận: {current_len} ký tự...", end="", flush=True)
                    stable_count = 0  # Reset khi có text mới

                # Kiểm tra xem response đã hoàn tất chưa (text không thay đổi)
                if current_text and current_text == last_text:
                    stable_count += 1

                    # Chỉ kết thúc khi: text ổn định 5 giây VÀ đủ dài
                    if stable_count >= 5 and current_len >= min_response_length:
                        print(f"\n✅ Streaming hoàn tất. Đang copy raw text...")
                        # SAU KHI streaming xong, click Copy để lấy raw text
                        final_text = copy_response_text(driver, response_selectors)
                        if final_text:
                            print(f"✅ Đã copy raw text ({len(final_text)} ký tự)")
                            return final_text
                        else:
                            print(
                                f"⚠️ Không copy được, dùng text thường ({len(current_text)} ký tự)"
                            )
                            return current_text
                    elif stable_count >= 5 and current_len < min_response_length:
                        # Response quá ngắn, có thể Gemini chưa bắt đầu streaming
                        print(
                            f"\r⏳ Response quá ngắn ({current_len}), chờ tiếp...",
                            end="",
                            flush=True,
                        )
                        stable_count = 0  # Reset để chờ thêm
                else:
                    stable_count = 0
                    last_text = current_text

                time.sleep(1)  # Kiểm tra mỗi 1 giây

            # Nếu hết thời gian nhưng có text đủ dài
            if last_text and len(last_text) >= min_response_length:
                print(f"\n⚠️ Timeout. Đang copy raw text...")
                final_text = copy_response_text(driver, response_selectors)
                if final_text:
                    return final_text
                return last_text

            raise TimeoutException(
                f"Response quá ngắn hoặc không nhận được ({len(last_text) if last_text else 0} ký tự)"
            )

        except Exception as e:
            print(f"\n⚠️ Lỗi Selenium lần {attempt + 1}/{max_retries}: {e}")
            if attempt < max_retries - 1:
                print("⏳ Thử lại sau 10s...")
                time.sleep(10)
                # Reset driver nếu lỗi nghiêm trọng
                close_gemini_driver()
            else:
                raise ValueError(
                    f"❌ Không lấy được response sau {max_retries} lần thử: {e}"
                )

    return ""


# ====== Hàm đọc/ghi YAML (chỉ dùng cho context.yaml) ======


# ====== Hàm gọi Gemini web tạo glossary ======
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
> Không thêm chú thích hay giải thích nào khác.  
> Chỉ xuất **thuần văn bản**, mỗi dòng một mục, theo dạng:
原文 = Dịch

Bắt đầu glossary bằng dòng `###START###` và kết thúc bằng dòng `###END###`.
"""

    # Mở chat mới trước mỗi batch
    driver = get_gemini_driver()
    driver.get("https://gemini.google.com/app")
    time.sleep(3)

    resp = generate_content_with_selenium(prompt)
    return resp.strip() if resp else ""


# ====== Hàm merge glossary ======


# ====== Main ======
def main():
    return run_context_generation(
        engine_name="Gemini Web",
        setup_browser=setup_gemini_browser,
        close_browser=close_gemini_driver,
        generate_glossary=generate_glossary,
        raw_dir=RAW_DIR,
        context_file=CONTEXT_FILE,
        batch_size=BATCH_SIZE,
    )


if __name__ == "__main__":
    main()
