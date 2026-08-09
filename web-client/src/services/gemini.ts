export interface GenerateOptions {
  apiKey: string;
  model: string;
  maxOutputTokens?: number | null;
  thinkingLevel?: "LOW" | "MEDIUM" | "HIGH";
  systemInstruction: string;
  prompt: string;
  signal?: AbortSignal;
}

export interface StreamOptions extends GenerateOptions {
  onText: (text: string) => void;
}

interface GeminiResponse {
  candidates?: Array<{ content?: { parts?: Array<{ text?: string }> } }>;
  promptFeedback?: { blockReason?: string };
  error?: { message?: string };
}

export class GeminiRequestError extends Error {
  constructor(message: string, public readonly status: number) {
    super(message);
    this.name = "GeminiRequestError";
  }
}

const SAFETY_OFF = [
  "HARM_CATEGORY_HARASSMENT",
  "HARM_CATEGORY_HATE_SPEECH",
  "HARM_CATEGORY_SEXUALLY_EXPLICIT",
  "HARM_CATEGORY_DANGEROUS_CONTENT",
].map((category) => ({ category, threshold: "OFF" }));

export async function generateContent(options: GenerateOptions): Promise<string> {
  const endpoint = `https://generativelanguage.googleapis.com/v1beta/models/${encodeURIComponent(options.model)}:generateContent`;
  const response = await fetch(endpoint, {
    method: "POST",
    headers: {
      "Content-Type": "application/json",
      "x-goog-api-key": options.apiKey,
    },
    body: JSON.stringify({
      systemInstruction: { parts: [{ text: options.systemInstruction }] },
      contents: [{ role: "user", parts: [{ text: options.prompt }] }],
      generationConfig: {
        ...(options.maxOutputTokens ? { maxOutputTokens: options.maxOutputTokens } : {}),
        thinkingConfig: { thinkingLevel: options.thinkingLevel || "HIGH" },
      },
      safetySettings: SAFETY_OFF,
    }),
    signal: options.signal,
  });

  const data = (await response.json()) as GeminiResponse;
  if (!response.ok) throw new GeminiRequestError(data.error?.message || `Gemini trả về HTTP ${response.status}.`, response.status);
  const text = data.candidates?.[0]?.content?.parts?.map((part) => part.text || "").join("").trim();
  if (!text) {
    const reason = data.promptFeedback?.blockReason;
    throw new Error(reason ? `Gemini đã chặn yêu cầu: ${reason}.` : "Gemini không trả về nội dung.");
  }
  return text;
}

export async function streamInteraction(options: StreamOptions): Promise<string> {
  const response = await fetch("https://generativelanguage.googleapis.com/v1beta/interactions?alt=sse", {
    method: "POST",
    headers: {
      "Content-Type": "application/json",
      "Accept": "text/event-stream",
      "x-goog-api-key": options.apiKey,
    },
    body: JSON.stringify({
      model: options.model,
      input: options.prompt,
      stream: true,
      store: false,
      ...(options.systemInstruction ? { system_instruction: options.systemInstruction } : {}),
      generation_config: {
        ...(options.maxOutputTokens ? { max_output_tokens: options.maxOutputTokens } : {}),
        thinking_level: (options.thinkingLevel || "HIGH").toLowerCase(),
      },
    }),
    signal: options.signal,
  });
  if (!response.ok) {
    const detail = await response.text();
    let message = detail;
    try { message = (JSON.parse(detail) as { error?: { message?: string } }).error?.message || detail; } catch { /* keep response text */ }
    throw new GeminiRequestError(message || `Gemini trả về HTTP ${response.status}.`, response.status);
  }
  if (!response.body) throw new Error("Trình duyệt không nhận được luồng dữ liệu từ Gemini.");

  const reader = response.body.getReader();
  const decoder = new TextDecoder();
  let buffer = "";
  let output = "";
  let completed = false;
  const consume = (line: string) => {
    if (!line.startsWith("data:")) return;
    const raw = line.slice(5).trim();
    if (!raw || raw === "[DONE]") return;
    const event = JSON.parse(raw) as { event_type?: string; delta?: { type?: string; text?: string }; interaction?: { status?: string }; error?: { message?: string } };
    if (event.event_type === "step.delta" && event.delta?.type === "text" && event.delta.text) {
      output += event.delta.text;
      options.onText(event.delta.text);
    } else if (event.event_type === "interaction.completed") {
      if (event.interaction?.status && event.interaction.status !== "completed") throw new Error(`Gemini Interactions kết thúc với trạng thái ${event.interaction.status}.`);
      completed = true;
    } else if (event.event_type === "error") throw new Error(event.error?.message || "Gemini Interactions stream gặp lỗi.");
  };

  while (true) {
    const { done, value } = await reader.read();
    buffer += decoder.decode(value, { stream: !done });
    const lines = buffer.split(/\r?\n/);
    buffer = done ? "" : lines.pop() || "";
    for (const line of lines) consume(line);
    if (done) {
      if (buffer) consume(buffer);
      break;
    }
  }
  if (!completed) throw new Error("Gemini Interactions stream kết thúc trước khi hoàn tất.");
  if (!output.trim()) throw new Error("Gemini không trả về nội dung.");
  return output.trim();
}

export function parseTranslationStream(value: string) {
  const normalized = value.replace(/\\###/g, "###");
  const titleMarker = normalized.indexOf("###TITLE###");
  const contentMarker = normalized.indexOf("###CONTENT###");
  if (titleMarker < 0 || contentMarker <= titleMarker) return null;
  const endMarker = normalized.indexOf("###END###", contentMarker);
  return {
    title: normalized.slice(titleMarker + "###TITLE###".length, contentMarker).trim(),
    content: normalized.slice(contentMarker + "###CONTENT###".length, endMarker < 0 ? undefined : endMarker).replace(/^\r?\n/, ""),
    complete: endMarker >= 0,
  };
}

export interface TranslationPromptInput {
  title: string;
  source: string;
  context: string;
  characters: string;
  pronouns: string;
  previousChapters: string;
  from: string;
  to: string;
  role?: string;
  task?: string;
}

export const DEFAULT_TRANSLATION_ROLE = `Bạn là một **biên tập viên dịch thuật tài hoa**, với trái tim dành trọn cho từng con chữ.
Hãy gìn giữ nguyên vẹn **tinh hoa của từng dòng thơ, từng câu văn** – như những báu vật thiêng liêng của tác phẩm gốc.
Sau đó, bằng bàn tay khéo léo và hơi thở của nghệ sĩ, **hãy mài giũa ngôn từ cho long lanh hơn**, khơi dậy linh hồn sâu lắng,
để văn bản không chỉ truyền tải mà còn **lay động trái tim người đọc**, như dòng sông quê hương êm đềm mà cuồn cuộn sóng ngầm cảm xúc.`;

export const DEFAULT_TRANSLATION_TASK = `Dịch **cả tiêu đề (title)** lẫn **nội dung (content)** sang **tiếng Việt**,
giữ **văn phong mượt mà, nhất quán**.
Không tự thêm định dạng Markdown. Phải giữ nguyên Markdown ảnh hoặc ký hiệu đã tồn tại trong nội dung nguồn.
**TUYỆT ĐỐI KHÔNG ĐƯỢC** làm mất “ ” hay ‘ ’ để đánh dấu đoạn hội thoại.

**QUAN TRỌNG về xưng hô – linh hồn của bản dịch:**
- PHÂN BIỆT RÕ DẪN TRUYỆN VÀ HỘI THOẠI:
  + Trong phần DẪN TRUYỆN, TUÂN THỦ TUYỆT ĐỐI quy tắc dẫn truyện được giao.
  + Trong phần HỘI THOẠI, nhân vật linh hoạt xưng hô theo cảm xúc và đối tượng giao tiếp.
- Tham khảo bộ nhớ xưng hô bên dưới để giữ nhất quán, nhưng KHÔNG CỨNG NHẮC trong hội thoại.
- Xưng hô phải phản ánh đúng CẢM XÚC & TRẠNG THÁI QUAN HỆ tại thời điểm đó.
- Cảm xúc biến chuyển trong cùng cuộc hội thoại thì xưng hô cũng có thể biến chuyển theo.
- Nếu có xung đột giữa bộ nhớ và ngữ cảnh hiện tại thì tin vào ngữ cảnh hiện tại.

**QUY TẮC TÊN TIÊU ĐỀ: Title Case** viết hoa ký tự đầu mỗi từ. Nếu tên chương đánh số thì đánh số Ả Rập.`;

export function translationPrompt(input: TranslationPromptInput) {
  return {
    systemInstruction: "",
    prompt: `# 🌸 Vai trò
${input.role?.trim() || DEFAULT_TRANSLATION_ROLE}

---

# 🎯 Nhiệm vụ
${input.task?.trim() || DEFAULT_TRANSLATION_TASK}

---

## 📜 Dữ liệu đầu vào

### Các chương trước:
${input.previousChapters}

${input.pronouns ? `## 📌 Bộ nhớ xưng hô nhân vật (tham khảo để dịch có hồn)\n\n💡 Lưu ý: Xưng hô phản ánh CẢM XÚC và MỐI QUAN HỆ. Hãy điều chỉnh linh hoạt theo diễn biến nội tâm nhân vật trong chương này.\n\n${input.pronouns}` : ""}

### Dịch đúng theo bảng thuật ngữ tên riêng bên dưới.
Quy tắc dịch:
${input.context}

### Tiêu đề gốc:
${input.title}

### Nội dung gốc:
${input.source}

# ⚠️ Yêu cầu xuất kết quả
**TUYỆT ĐỐI KHÔNG** ghi thêm dòng hỏi muốn dịch thêm.
Chỉ xuất đúng theo định dạng sau:

###TITLE###
<tiêu đề dịch>

###CONTENT###
<nội dung dịch>

###END###`,
  };
}

export function parseTranslationResponse(value: string) {
  const normalized = value.replace(/\\###/g, "###").trim();
  const titleMarker = normalized.indexOf("###TITLE###");
  const contentMarker = normalized.indexOf("###CONTENT###");
  const endMarker = normalized.lastIndexOf("###END###");
  if (titleMarker < 0 || contentMarker <= titleMarker || endMarker <= contentMarker) throw new Error("Gemini trả về sai định dạng hoặc bị cắt giữa chừng.");
  const title = normalized.slice(titleMarker + "###TITLE###".length, contentMarker).trim();
  const content = normalized.slice(contentMarker + "###CONTENT###".length, endMarker).trim();
  if (!title || !content || /<\s*(?:tiêu đề|nội dung|translated)/i.test(`${title}\n${content}`)) throw new Error("Gemini trả về placeholder hoặc nội dung rỗng.");
  return { title, content };
}

export function containsCjkOrHangul(value: string) {
  return /[\u3040-\u30ff\u3400-\u9fff\uac00-\ud7af]/u.test(value);
}

export function charactersPrompt(source: string, existing: string) {
  return {
    systemInstruction: "Bạn là biên tập viên phân tích nhân vật tiểu thuyết. Viết tiếng Việt, chỉ trả về Markdown.",
    prompt: `Cập nhật hồ sơ nhân vật dựa trên chương mới. Giữ thông tin cũ đúng, không bịa khi văn bản không xác nhận. Mỗi nhân vật dùng tiêu đề \"## Tên\" và các mục: Tên gốc, biệt danh, giới tính, vai trò, đặc điểm, quan hệ, xưng hô.\n\n# Hồ sơ hiện có\n${existing || "(Chưa có)"}\n\n# Chương nguồn\n${source}`,
  };
}

export function contextPrompt(source: string, existing: string, characters: string) {
  return {
    systemInstruction: "Bạn xây dựng Context V1 cho dịch tiểu thuyết. Chỉ trả về YAML hợp lệ, không dùng code fence.",
    prompt: `Cập nhật context dịch từ dữ liệu dưới đây. Giữ các khóa: index, style_notes, glossary. Glossary là danh sách chuỗi theo dạng \"Nguyên văn = Tiếng Việt\". Bảo toàn mục cũ còn đúng, thêm tên riêng và thuật ngữ thực sự xuất hiện, không thêm từ quá chung.\n\n# Context hiện có\n${existing || "index: []\nstyle_notes: []\nglossary: []"}\n\n# Hồ sơ nhân vật\n${characters || "(Chưa có)"}\n\n# Chương nguồn\n${source}`,
  };
}

export const DEFAULT_POLISH_ROLE = "Bạn là biên tập viên dịch thuật chuyên nghiệp tiểu thuyết.";

export const DEFAULT_POLISH_TASK = `Nhiệm vụ là BIÊN TẬP LẠI bản dịch hiện có theo hai mục tiêu SONG SONG:

1. TRAU CHUỐT VĂN PHONG:
   - Sửa các câu còn dịch sót ngôn ngữ gốc.
   - Tránh dịch sai nghĩa gốc; hãy tham khảo bản gốc để đảm bảo độ nguyên bản.
   - Giữ nguyên dấu ngoặc kép “…” ‘…’ đánh dấu hội thoại.
   - KHÔNG thêm Markdown, KHÔNG thêm giải thích.
   - Giữ toàn bộ nội dung, KHÔNG cắt bớt hay thêm ý mới.

2. CHỈNH XƯNG HÔ:
   - Tra characters.md để biết giới tính, tuổi tác và vai trò của từng nhân vật.
   - Tra bộ nhớ xưng hô liên quan hoặc pronouns_snapshot.yaml để giữ cách xưng hô nhất quán với các chương trước.
   - Trong HỘI THOẠI: xưng hô linh hoạt theo cảm xúc, không cứng nhắc.
   - Trong DẪN TRUYỆN: nhất quán theo bộ nhớ xưng hô.
   - Ưu tiên ngữ cảnh hiện tại nếu xung đột với bộ nhớ.
   - Mục có locked: true là quy tắc do người dùng xác nhận, PHẢI ưu tiên và không tự ý thay đổi.

3. BIÊN TẬP TIÊU ĐỀ:
   - Chỉ sửa xưng hô hoặc văn phong nếu cần, KHÔNG đổi nghĩa.
   - Giữ dạng Title Case (viết hoa chữ cái đầu mỗi từ).`;

export function polishPrompt(source: string, translation: string, context: string, characters: string, role?: string, task?: string) {
  return {
    systemInstruction: role?.trim() || DEFAULT_POLISH_ROLE,
    prompt: `${task?.trim() || DEFAULT_POLISH_TASK}\n\n# Context V1\n${context || "(Chưa có)"}\n\n# Hồ sơ nhân vật\n${characters || "(Chưa có)"}\n\n# Nguyên tác\n${source}\n\n# Bản dịch cần hiệu đính\n${translation}`,
  };
}

export function pronounsPrompt(source: string, translation: string, existing: string) {
  return {
    systemInstruction: "Bạn trích xuất quy tắc xưng hô trong tiểu thuyết. Chỉ ghi quan hệ thực sự xuất hiện hoặc được xác nhận; trả về Markdown ngắn gọn.",
    prompt: `Cập nhật danh sách xưng hô theo mẫu: Người nói → Người nghe: cách tự xưng / cách gọi, kèm ghi chú bối cảnh nếu cần. Bảo toàn quy tắc cũ còn đúng.\n\n# Xưng hô hiện có\n${existing || "(Chưa có)"}\n\n# Nguyên tác\n${source}\n\n# Bản dịch\n${translation || "(Chưa dịch)"}`,
  };
}

export interface ReviewResult {
  chapter_id: string;
  overall_score: number | null;
  issues: Array<{ type: string; severity: string; original_kr: string; original_vi: string; suggestion: string }>;
  gender_ok: boolean;
  address_ok: boolean;
  summary: string;
}

export function reviewPrompt(input: { chapterId: string; chapterNumber: number; rawTitle: string; source: string; translatedTitle: string; translation: string; context: string }) {
  return {
    systemInstruction: "Bạn là chuyên gia review dịch thuật tiểu thuyết Hàn-Việt. Chỉ trả về JSON hợp lệ, không dùng Markdown.",
    prompt: `Bạn là chuyên gia review dịch thuật tiểu thuyết Hàn-Việt.
Nhiệm vụ: Đối chiếu sát bản gốc tiếng Hàn với bản dịch tiếng Việt và tìm lỗi. Không được phỏng đoán lỗi nếu bản gốc không chứng minh điều đó.

## ƯU TIÊN CAO NHẤT — Phải kiểm tra kỹ:

### 1. LỖI GIỚI TÍNH (severity: "nặng")
- Dùng sai đại từ giới tính: "anh ấy" cho nữ, "cô ấy" cho nam.
- Dùng sai đại từ ngôi thứ ba trong dẫn thoại: "hắn" cho nữ, "nàng" cho nam.
- Nhầm "cậu" (nam) và "cô" (nữ) trong dẫn truyện ngôi thứ ba.
- Dịch sai giới tính qua cách miêu tả (ví dụ: miêu tả nam như nữ hoặc ngược lại).
- Nhầm vai trò giới trong hội thoại (ai nói câu gì).

### 2. LỖI XƯNG HÔ (severity: "nặng")
- Xưng hô không phù hợp mối quan hệ (ví dụ: bạn bè gọi "ngài", đồng nghiệp gọi "con").
- Thiếu nhất quán trong cùng một chương mà không có lý do.
- Xưng hô sai vai vế (em gái xưng "anh", anh trai xưng "em" khi không có lý do đặc biệt).
- Lẫn lộn ngôi xưng hô giữa các cặp nhân vật khác nhau.

### 3. Lỗi khác (severity: "trung bình" hoặc "nhẹ")
- Thiếu câu, thiếu đoạn hoặc tự thêm nội dung không có trong bản gốc.
- Dịch sai nghĩa, nhầm chủ thể, nhầm quan hệ hoặc sai sự kiện.
- Thuật ngữ dịch sai hoặc không nhất quán.
- Phong cách dịch cứng nhắc, không tự nhiên.
- Logic truyện bị sai.
- Còn sót ký tự ngoại ngữ.

## Thuật ngữ tham chiếu:
${input.context.slice(0, 3000) || "(Chưa có)"}

## Thông tin chương:
- ID: ${input.chapterId}
- Số chương: ${input.chapterNumber}

## Bản gốc tiếng Hàn:
### Tiêu đề gốc:
${input.rawTitle}

### Nội dung gốc:
${input.source}

## Bản dịch tiếng Việt:
### Tiêu đề dịch:
${input.translatedTitle}

### Nội dung dịch:
${input.translation}

## YÊU CẦU OUTPUT:
Trả về JSON (KHÔNG Markdown, KHÔNG giải thích thêm):
{
  "chapter_id": "${input.chapterId}",
  "overall_score": <1-10>,
  "issues": [{
    "type": "thiếu nội dung|thêm nội dung|dịch sai|giới tính|xưng hô|thuật ngữ|phong cách|logic|ngoại ngữ",
    "severity": "nặng|trung bình|nhẹ",
    "original_kr": "đoạn tương ứng trong bản gốc",
    "original_vi": "đoạn lỗi trong bản dịch",
    "suggestion": "gợi ý sửa"
  }],
  "gender_ok": true,
  "address_ok": true,
  "summary": "nhận xét tổng quan 1-2 câu"
}

Nếu có lỗi giới tính hoặc xưng hô, phải đặt cờ tương ứng thành false và liệt kê chi tiết trong issues. Chỉ trả về JSON.`,
  };
}

export function parseReviewResponse(value: string): ReviewResult {
  const clean = value.replace(/```json\s*|\s*```/gi, "").trim();
  const start = clean.indexOf("{");
  const end = clean.lastIndexOf("}");
  if (start < 0 || end <= start) throw new Error("Gemini trả review không có JSON hợp lệ.");
  const raw = JSON.parse(clean.slice(start, end + 1)) as Partial<ReviewResult>;
  const issues = Array.isArray(raw.issues) ? raw.issues.map((issue) => ({
    type: String(issue?.type || "khác"), severity: String(issue?.severity || ""),
    original_kr: String(issue?.original_kr || ""), original_vi: String(issue?.original_vi || ""), suggestion: String(issue?.suggestion || ""),
  })) : [];
  return {
    chapter_id: String(raw.chapter_id || ""),
    overall_score: Number.isFinite(Number(raw.overall_score)) ? Number(raw.overall_score) : null,
    issues,
    gender_ok: raw.gender_ok !== false,
    address_ok: raw.address_ok !== false,
    summary: String(raw.summary || ""),
  };
}

export function reviewResultText(review: ReviewResult) {
  const issueText = review.issues.map((issue, index) => `- ${issue.type || `Lỗi ${index + 1}`}: ${issue.suggestion || issue.original_vi}`).join("\n");
  return [review.summary, issueText].filter(Boolean).join("\n\n");
}
