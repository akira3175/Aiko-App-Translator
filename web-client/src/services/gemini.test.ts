import { describe, expect, it, vi } from "vitest";
import { charactersPrompt, contextPrompt, geminiRetryAction, generateContent, parseReviewResponse, parseTranslationResponse, parseTranslationStream, polishPrompt, pronounsPrompt, reviewPrompt, streamInteraction, translationPrompt } from "./gemini";

describe("Gemini prompts", () => {
  it("matches the local default prompt and keeps dynamic translation context", () => {
    const value = translationPrompt({ title: "제목", source: "원문", context: "glossary: []", pronouns: "Ta / ngươi", previousChapters: "Chương trước", from: "Tiếng Hàn", to: "Tiếng Việt" });
    expect(value.systemInstruction).toBe("");
    expect(value.prompt).toContain("원문");
    expect(value.prompt).toContain("glossary: []");
    expect(value.prompt).toContain("Ta / ngươi");
    expect(value.prompt).toContain("###END###");
    expect(value.prompt).toContain("# 🌸 Vai trò");
    expect(value.prompt).toContain("# 🎯 Nhiệm vụ");
  });

  it("uses the translation and polish prompts edited for the project", () => {
    const translation = translationPrompt({ title: "제목", source: "원문", context: "", pronouns: "", previousChapters: "", from: "Hàn", to: "Việt", role: "Vai trò riêng", task: "Nhiệm vụ riêng" });
    const polish = polishPrompt("원문", "Bản dịch", "", "Vai trò hiệu đính", "Nhiệm vụ hiệu đính");
    expect(translation.prompt).toContain("Vai trò riêng");
    expect(translation.prompt).toContain("Nhiệm vụ riêng");
    expect(polish.systemInstruction).toBe("Vai trò hiệu đính");
    expect(polish.prompt).toContain("Nhiệm vụ hiệu đính");
  });

  it("asks the character task to preserve confirmed information", () => {
    const value = charactersPrompt("Chương mới");
    expect(value.prompt).toContain("không bịa");
    expect(value.prompt).toContain("characters.md");
  });

  it("asks Context V1 for compatible YAML keys", () => {
    const value = contextPrompt("Chương mới", "");
    expect(value.systemInstruction).toContain("YAML hợp lệ");
    expect(value.prompt).toContain("index, style_notes, glossary");
  });

  it("sends editable generation settings to Gemini", async () => {
    const request = vi.spyOn(globalThis, "fetch").mockResolvedValue(new Response(JSON.stringify({
      candidates: [{ content: { parts: [{ text: "Bản dịch" }] } }],
    }), { status: 200, headers: { "Content-Type": "application/json" } }));
    await generateContent({
      apiKey: "test-key",
      model: "gemini-test",
      maxOutputTokens: 24000,
      systemInstruction: "Dịch",
      prompt: "Nguyên văn",
    });
    const body = JSON.parse(String(request.mock.calls[0][1]?.body));
    expect(body.generationConfig).toEqual({ maxOutputTokens: 24000, thinkingConfig: { thinkingLevel: "HIGH" } });
    request.mockRestore();
  });

  it("sends characters.md as a separate inline document", async () => {
    const request = vi.spyOn(globalThis, "fetch").mockResolvedValue(new Response(JSON.stringify({
      candidates: [{ content: { parts: [{ text: "Đã xử lý" }] } }],
    }), { status: 200, headers: { "Content-Type": "application/json" } }));
    await generateContent({ apiKey: "key", model: "model", systemInstruction: "", prompt: "Dịch chương", document: { name: "characters.md", mimeType: "text/markdown", content: "## Hwangju\nGiới tính: Nam" } });
    const body = JSON.parse(String(request.mock.calls[0][1]?.body));
    expect(body.contents[0].parts[0].text).toContain("characters.md");
    expect(body.contents[0].parts[1]).toEqual({ inlineData: { mimeType: "text/markdown", data: btoa(unescape(encodeURIComponent("## Hwangju\nGiới tính: Nam"))) } });
    request.mockRestore();
  });

  it("classifies retryable Gemini HTTP errors", () => {
    expect(geminiRetryAction(429)).toBe("rotate-key");
    expect(geminiRetryAction(401)).toBe("rotate-key");
    expect(geminiRetryAction(503)).toBe("retry-same-key");
    expect(geminiRetryAction(400)).toBe("fail");
  });

  it("validates the structured translation response", () => {
    expect(parseTranslationResponse("###TITLE###\nChương Một\n###CONTENT###\nNội dung\n###END###")).toEqual({ title: "Chương Một", content: "Nội dung" });
    expect(() => parseTranslationResponse("Bản dịch bị cắt")).toThrow(/sai định dạng/);
  });

  it("parses an unfinished translation without requiring the end marker", () => {
    expect(parseTranslationStream("###TITLE###\nChương Một\n###CONTENT###\nDòng 1\nDòng")).toEqual({ title: "Chương Một", content: "Dòng 1\nDòng", complete: false });
  });

  it("streams Interactions text deltas in order", async () => {
    const chunks = [
      'data: {"event_type":"step.delta","delta":{"type":"text","text":"Dòng 1\\n"}}\n',
      'data: {"event_type":"step.delta","delta":{"type":"text","text":"Dòng 2"}}\n',
      'data: {"event_type":"interaction.completed","interaction":{"status":"completed"}}\n',
    ];
    const encoder = new TextEncoder();
    const request = vi.spyOn(globalThis, "fetch").mockResolvedValueOnce(new Response(new ReadableStream({ start(controller) { chunks.forEach((chunk) => controller.enqueue(encoder.encode(chunk))); controller.close(); } }), { status: 200 }));
    const deltas: string[] = [];
    const result = await streamInteraction({ apiKey: "key", model: "model", systemInstruction: "", prompt: "prompt", document: { name: "characters.md", mimeType: "text/markdown", content: "## Nhân vật" }, onText: (text) => deltas.push(text) });
    expect(result).toBe("Dòng 1\nDòng 2");
    expect(deltas).toEqual(["Dòng 1\n", "Dòng 2"]);
    expect(request.mock.calls[0][1]?.headers).toMatchObject({ Accept: "text/event-stream" });
    const body = JSON.parse(String(request.mock.calls[0][1]?.body));
    expect(body.input[0].text).toContain("characters.md");
    expect(body.input[1]).toEqual({ type: "text", text: "## Reference file: characters.md\n\n## Nhân vật" });
    vi.restoreAllMocks();
  });

  it("keeps supported Interactions CSV references as documents", async () => {
    const encoder = new TextEncoder();
    const request = vi.spyOn(globalThis, "fetch").mockResolvedValueOnce(new Response(new ReadableStream({ start(controller) {
      controller.enqueue(encoder.encode('data: {"event_type":"step.delta","delta":{"type":"text","text":"OK"}}\n'));
      controller.enqueue(encoder.encode('data: {"event_type":"interaction.completed","interaction":{"status":"completed"}}\n'));
      controller.close();
    } }), { status: 200 }));
    await streamInteraction({ apiKey: "key", model: "model", systemInstruction: "", prompt: "prompt", document: { name: "terms.csv", mimeType: "text/csv", content: "a,b" }, onText: () => {} });
    const body = JSON.parse(String(request.mock.calls[0][1]?.body));
    expect(body.input[1]).toMatchObject({ type: "document", mime_type: "text/csv" });
    vi.restoreAllMocks();
  });

  it("keeps raw and translation in post-translation tasks", () => {
    expect(polishPrompt("원문", "Bản dịch", "context").prompt).toContain("원문");
    expect(pronounsPrompt("원문", "Bản dịch", "xưng hô cũ").prompt).toContain("xưng hô cũ");
    const review = reviewPrompt({ chapterId: "v1_c1_s1", chapterNumber: 1, rawTitle: "제목", source: "원문", translatedTitle: "Chương 1", translation: "Bản dịch", context: "context" });
    expect(review.prompt).toContain("Bản dịch");
    expect(review.prompt).toContain("LỖI GIỚI TÍNH");
    expect(review.prompt).toContain('"gender_ok": true');
  });

  it("parses the structured local review result", () => {
    const result = parseReviewResponse('```json\n{"chapter_id":"v1_c1_s1","overall_score":8,"issues":[{"type":"xưng hô","severity":"nặng","original_kr":"나","original_vi":"tôi","suggestion":"ta"}],"gender_ok":true,"address_ok":false,"summary":"Cần sửa."}\n```');
    expect(result.overall_score).toBe(8);
    expect(result.address_ok).toBe(false);
    expect(result.issues[0].suggestion).toBe("ta");
  });
});
