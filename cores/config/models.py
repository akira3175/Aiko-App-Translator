"""Model and reasoning defaults loaded from the active task settings."""

from cores.config.runtime import int_option, option


FIX_MAX_RETRY = int_option("fix_max_retry", 3, minimum=1)
POLISH_MODEL = str(option("polish_model", "gemini-flash-latest"))
REVIEW_BG_MODEL = str(option("review_bg_model", "gemini-flash-lite-latest"))
PRONOUN_MODEL = str(option("pronoun_model", "gemini-flash-lite-latest"))

DEFAULT_REVIEW_BG_CRITERIA = """1. Thiếu nội dung: chỉ báo khi một ý, hành động, hội thoại hoặc sự kiện trong bản gốc thực sự biến mất khỏi bản dịch; không báo lỗi khi bản dịch diễn đạt cô đọng nhưng vẫn đủ nghĩa.
2. Dịch sai nội dung: báo khi ý nghĩa thay đổi rõ rệt, nhầm nhân vật, sự kiện hoặc quan hệ nguyên nhân-kết quả.
3. Xưng hô: kiểm tra giới tính, vai vế, quan hệ và ngữ cảnh giao tiếp của nhân vật.
4. Phong cách và thuật ngữ: kiểm tra độ tự nhiên của tiếng Việt và tính nhất quán với glossary tham chiếu.
5. Ngoại ngữ: chỉ báo khi ký tự hoặc câu ngoại ngữ thực sự còn xuất hiện trong bản dịch; không dùng văn bản nguồn làm bằng chứng cho lỗi này.
6. Chỉ nêu lỗi khi có dẫn chứng cụ thể trong cả bản gốc và bản dịch; không suy đoán hoặc bắt lỗi khác biệt diễn đạt thuần túy."""
REVIEW_BG_CRITERIA = str(option("review_bg_criteria", DEFAULT_REVIEW_BG_CRITERIA))
