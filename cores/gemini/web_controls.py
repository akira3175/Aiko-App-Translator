"""Gemini Web model controls."""

import time

from selenium.webdriver.common.by import By


def open_model_dropdown(driver):
    selectors = [
        '[data-test-id="bard-mode-menu-button"]',
        "bard-mode-switcher button.input-area-switch",
        "bard-mode-switcher button",
        ".pill-ui-logo-container button",
    ]
    model_button = None
    for selector in selectors:
        try:
            model_button = next(
                (
                    element
                    for element in driver.find_elements(By.CSS_SELECTOR, selector)
                    if element.is_displayed()
                ),
                None,
            )
            if model_button:
                break
        except Exception:
            continue
    if not model_button:
        print("⚠️ Không tìm thấy dropdown model, tiếp tục với model mặc định")
        return None, None

    current_text = ""
    try:
        current_text = model_button.find_element(
            By.CSS_SELECTOR, ".picker-primary-text"
        ).text.strip().lower()
    except Exception:
        pass
    if not current_text:
        try:
            aria = model_button.get_attribute("aria-label") or ""
            if "hiện tại là" in aria:
                current_text = aria.split("hiện tại là")[-1].strip().lower()
            elif "currently" in aria.lower():
                current_text = aria.lower().split("currently")[-1].strip()
        except Exception:
            pass
    if not current_text:
        current_text = model_button.text.strip().lower()
    return model_button, current_text


def click_menu_item(driver, keywords, label):
    selectors = [
        '[data-test-id="gem-mode-menu"] gem-menu-item[role="menuitem"]',
        '.cdk-overlay-pane gem-menu-item[role="menuitem"]',
        'gem-menu[role="menu"] gem-menu-item[role="menuitem"]',
        '[role="menuitem"]',
    ]
    target = None
    for selector in selectors:
        try:
            for element in driver.find_elements(By.CSS_SELECTOR, selector):
                if not element.is_displayed():
                    continue
                try:
                    text = element.find_element(
                        By.CSS_SELECTOR, "span.label"
                    ).text.strip().lower()
                except Exception:
                    text = element.text.strip().lower()
                if (element.get_attribute("value") or "") == "thinking_level":
                    continue
                if any(keyword.strip().lower() in text for keyword in keywords):
                    target = element
                    break
            if target:
                break
        except Exception:
            continue
    if not target:
        print(f"⚠️ Không tìm thấy option '{label}' trong menu")
        driver.execute_script("document.body.click();")
        return False
    driver.execute_script("arguments[0].click();", target)
    time.sleep(1)
    print(f"✅ Đã chọn: {label}")
    return True


def select_thinking_model(driver, max_wait=10):
    del max_wait
    try:
        button, current = open_model_dropdown(driver)
        if not button:
            return False
        if "thinking" in current or "tư duy" in current:
            print("✅ Đã chọn model Thinking")
            return True
        print(f"📌 Model hiện tại: {current}. Đang chuyển sang Thinking...")
        driver.execute_script("arguments[0].click();", button)
        time.sleep(1.5)
        return click_menu_item(driver, ["Thinking", "Tư duy"], "Thinking")
    except Exception as error:
        print(f"⚠️ Lỗi khi chọn model: {error}")
        return False


def select_pro_model(driver, max_wait=10):
    del max_wait
    try:
        button, current = open_model_dropdown(driver)
        if not button:
            return False
        if "pro" in current and "thinking" not in current and "tư duy" not in current:
            print("✅ Đã chọn model Pro")
            return True
        print(f"📌 Model hiện tại: {current}. Đang chuyển sang Pro...")
        driver.execute_script("arguments[0].click();", button)
        time.sleep(1.5)
        return click_menu_item(driver, ["Pro"], "Pro")
    except Exception as error:
        print(f"⚠️ Lỗi khi chọn model: {error}")
        return False


def select_flash_model(driver, max_wait=10):
    del max_wait
    try:
        button, current = open_model_dropdown(driver)
        if not button:
            return False
        if any(label in current for label in ("fast", "nhanh", "flash")):
            print("✅ Đã chọn model Flash/Fast")
            return True
        print(f"📌 Model hiện tại: {current}. Đang chuyển sang Flash/Fast...")
        driver.execute_script("arguments[0].click();", button)
        time.sleep(1.5)
        return click_menu_item(
            driver,
            ["Fast", "Nhanh", "Flash"],
            "Flash/Fast",
        )
    except Exception as error:
        print(f"⚠️ Lỗi khi chọn model: {error}")
        return False


def select_thinking_level(driver, level="extended", max_wait=10):
    """
    Chọn cấp độ tư duy. Chỉ có 2 level: "Tiêu chuẩn" và "Mở rộng".

    Giao diện mới (2025-07):
      - "Mở rộng" nằm ngay trong menu chính, sau mat-divider
      - Không còn submenu con value="thinking_level"
      - Là gem-menu-item thường, không có data-mode-id
    """
    level_keywords = {
        "off": ["Tiêu chuẩn", "Standard"],
        "standard": ["Tiêu chuẩn", "Standard"],
        "low": ["Tiêu chuẩn", "Standard"],
        "medium": ["Tiêu chuẩn", "Standard"],
        "high": ["Mở rộng", "Extended"],
        "extended": ["Mở rộng", "Extended"],
    }
    keywords = level_keywords.get(level, ["Mở rộng", "Extended"])
    level_label = level.upper()
    want_extended = level in ("high", "extended")

    try:
        print(f"🧠 Đang chọn cấp độ tư duy: {level_label}...")

        # Mở dropdown model
        model_button, _ = open_model_dropdown(driver)
        if model_button:
            driver.execute_script("arguments[0].click();", model_button)
            time.sleep(1.5)

        # --- Giao diện mới: "Mở rộng" là item phẳng sau divider ---
        # Tìm tất cả gem-menu-item trong menu chính
        thinking_item = None
        item_selectors = [
            '[data-test-id="gem-mode-menu"] gem-menu-item[role="menuitem"]',
            '.cdk-overlay-pane gem-menu-item[role="menuitem"]',
            'gem-menu[role="menu"] gem-menu-item[role="menuitem"]',
        ]

        for selector in item_selectors:
            try:
                elements = driver.find_elements(By.CSS_SELECTOR, selector)
                for el in elements:
                    if not el.is_displayed():
                        continue
                    # Bỏ qua các model item (có data-mode-id)
                    if el.get_attribute("data-mode-id"):
                        continue
                    # Đọc label
                    try:
                        lbl = el.find_element(By.CSS_SELECTOR, "span.label")
                        text = lbl.text.strip().lower()
                    except:
                        text = el.text.strip().lower()
                    # Match với keywords
                    for kw in keywords:
                        if kw.strip().lower() in text:
                            thinking_item = el
                            break
                    if thinking_item:
                        break
                if thinking_item:
                    break
            except:
                continue

        # --- Fallback: giao diện cũ với value="thinking_level" ---
        if not thinking_item:
            try:
                elements = driver.find_elements(
                    By.CSS_SELECTOR, 'gem-menu-item[value="thinking_level"]'
                )
                for el in elements:
                    if el.is_displayed():
                        thinking_item = el
                        # Giao diện cũ: cần check sublabel và mở submenu
                        try:
                            sublabel = el.find_element(By.CSS_SELECTOR, ".sublabel")
                            current = sublabel.text.strip().lower()
                            target_kw = keywords[0].strip().lower()
                            if target_kw in current:
                                print(f"✅ Đã ở cấp độ: {sublabel.text.strip()}")
                                driver.execute_script("document.body.click();")
                                return True
                        except:
                            pass
                        # Click mở submenu cũ
                        driver.execute_script("arguments[0].click();", el)
                        time.sleep(1)
                        # Tìm option trong submenu cũ
                        sub_items = driver.find_elements(
                            By.CSS_SELECTOR,
                            '.cdk-overlay-pane gem-menu-item[role="menuitem"]',
                        )
                        for sub_el in sub_items:
                            if sub_el.is_displayed():
                                val = sub_el.get_attribute("value") or ""
                                if val == "thinking_level":
                                    continue
                                try:
                                    sub_lbl = sub_el.find_element(
                                        By.CSS_SELECTOR, "span.label"
                                    )
                                    sub_text = sub_lbl.text.strip().lower()
                                except:
                                    sub_text = sub_el.text.strip().lower()
                                for kw in keywords:
                                    if kw.strip().lower() in sub_text:
                                        driver.execute_script(
                                            "arguments[0].click();", sub_el
                                        )
                                        time.sleep(1)
                                        print(
                                            f"✅ Đã chọn cấp độ tư duy: {level_label} (submenu cũ)"
                                        )
                                        return True
                        print(f"⚠️ Không tìm thấy '{level_label}' trong submenu cũ")
                        driver.execute_script("document.body.click();")
                        return False
            except:
                pass

        if not thinking_item:
            print("⚠️ Không tìm thấy option cấp độ tư duy trong menu")
            driver.execute_script("document.body.click();")
            return False

        # Check nếu đã chọn (class "selected" trên item hoặc gem-menu-item-content)
        is_selected = "selected" in (thinking_item.get_attribute("class") or "")
        if not is_selected:
            try:
                content_el = thinking_item.find_element(
                    By.CSS_SELECTOR, "gem-menu-item-content"
                )
                is_selected = "selected" in (content_el.get_attribute("class") or "")
            except:
                pass

        if want_extended and is_selected:
            print(f"✅ Đã ở cấp độ: Mở rộng")
            driver.execute_script("document.body.click();")
            return True
        elif not want_extended and not is_selected:
            # Muốn Tiêu chuẩn và Mở rộng chưa được chọn → đã ở Tiêu chuẩn
            print(f"✅ Đã ở cấp độ: Tiêu chuẩn")
            driver.execute_script("document.body.click();")
            return True

        # Click toggle
        driver.execute_script("arguments[0].click();", thinking_item)
        time.sleep(1)
        print(f"✅ Đã chọn cấp độ tư duy: {level_label}")
        return True

    except Exception as e:
        print(f"⚠️ Lỗi khi chọn thinking level: {e}")
        return False
