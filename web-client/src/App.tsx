import { useCallback, useEffect, useRef, useState } from "react";
import {
  AddressBook,
  BookOpenText,
  CaretDown,
  ChatCenteredText,
  ClipboardText,
  DownloadSimple,
  FilePlus,
  GearSix,
  Key,
  MagnifyingGlass,
  Eye,
  PencilSimple,
  Plus,
  Sparkle,
  Stop,
  Trash,
  Translate,
  UploadSimple,
} from "@phosphor-icons/react";
import { db, deleteProject } from "./db/database";
import { MarkdownEditor } from "./components/MarkdownEditor";
import type { MarkdownEditorHandle } from "./components/MarkdownEditor";
import { MarkdownPreview, markdownToClipboardHtml, markdownToPlainText } from "./components/MarkdownPreview";
import {
  charactersPrompt,
  containsCjkOrHangul,
  contextPrompt,
  DEFAULT_POLISH_ROLE,
  DEFAULT_POLISH_TASK,
  DEFAULT_TRANSLATION_ROLE,
  DEFAULT_TRANSLATION_TASK,
  generateContent,
  GeminiRequestError,
  polishPrompt,
  parseTranslationStream,
  parseTranslationResponse,
  parseReviewResponse,
  pronounsPrompt,
  reviewPrompt,
  reviewResultText,
  translationPrompt,
  streamInteraction,
} from "./services/gemini";
import { createChapterImportPreview, parseNovelFile } from "./services/importNovel";
import { resumeChapterId } from "./services/chapterSelection";
import type { ChapterImportPreview, ImportedNovel } from "./services/importNovel";
import { exportLocalProject, importLocalProject, projectContextYaml } from "./services/localProjectArchive";
import type { AiTaskKind, AiTaskSettings, AppSettings, Chapter, Project, ProjectAsset, WorkspaceView } from "./types";
import { parse, stringify } from "yaml";

const BASE_TASK_SETTINGS: Omit<AiTaskSettings, "systemInstruction"> = {
  model: "gemini-3.5-flash",
  maxOutputTokens: null,
};

const DEFAULT_TASKS: Record<AiTaskKind, AiTaskSettings> = {
  translate: { ...BASE_TASK_SETTINGS, systemInstruction: "" },
  polish: { ...BASE_TASK_SETTINGS, model: "gemini-3-flash-preview", systemInstruction: "" },
  pronouns: { ...BASE_TASK_SETTINGS, model: "gemini-3.1-flash-lite-preview", systemInstruction: "" },
  review: { ...BASE_TASK_SETTINGS, model: "gemini-3.1-flash-lite-preview", systemInstruction: "" },
};

const DEFAULT_SETTINGS: AppSettings = {
  id: "app",
  model: "gemini-2.5-flash",
  temperature: 0.5,
  topP: 0.95,
  topK: 40,
  maxOutputTokens: 65536,
  tasks: DEFAULT_TASKS,
  rememberApiKey: false,
};

const navItems: Array<{ id: WorkspaceView; label: string; icon: typeof Translate }> = [
  { id: "translate", label: "Biên dịch", icon: Translate },
  { id: "characters", label: "Hồ sơ nhân vật", icon: AddressBook },
  { id: "context", label: "Thuật ngữ", icon: BookOpenText },
  { id: "pronouns", label: "Xưng hô", icon: ChatCenteredText },
  { id: "settings", label: "Thiết lập", icon: GearSix },
];

function now() {
  return new Date().toISOString();
}

function downloadBlob(name: string, blob: Blob) {
  const url = URL.createObjectURL(blob);
  const link = document.createElement("a");
  link.href = url;
  link.download = name;
  link.click();
  URL.revokeObjectURL(url);
}

function parseApiKeys(value: string) {
  return [...new Set(value.split(/\r?\n/).map((key) => key.trim()).filter(Boolean))];
}

export function chapterDisplayTitle(chapter: Chapter) {
  const stored = chapter.translatedTitle?.trim();
  if (stored && stored !== chapter.title.trim()) return stored;
  if (chapter.translation.trim()) {
    const firstContentLine = chapter.translation.split(/\r?\n/).map((line) => line.replace(/^\s*#{1,6}\s*/, "").trim()).find(Boolean);
    if (firstContentLine) return firstContentLine;
  }
  return stored || chapter.title;
}

export function translationContextYaml(project: Project, rawText: string) {
  let context: Record<string, unknown> = {};
  try { context = parse(projectContextYaml(project)) as Record<string, unknown> || {}; } catch { /* projectContextYaml always emits valid YAML */ }
  for (const key of ["index", "prompt_preset", "prompt_role", "prompt_task", "polish_prompt_preset", "polish_prompt_role", "polish_prompt_task"]) delete context[key];
  const source = rawText.toLocaleLowerCase();
  const glossary = (project.glossary || []).filter((entry) => entry.source.trim() && source.includes(entry.source.trim().toLocaleLowerCase()));
  if (glossary.length) context.glossary = glossary.map((entry) => `${entry.source} = ${entry.target}`).join("\n");
  else delete context.glossary;
  return stringify(context, { lineWidth: 0 });
}

function characterPrompt(batch: Chapter[], existing: string, glossary: Project["glossary"]) {
  const raw = batch.map((item) => `### ${item.title}\n${item.source}`).join("\n\n");
  const glossaryText = glossary?.map((item) => `${item.source} = ${item.target}`).join("\n") || "(Chua co glossary)";
  return `# Vai tro
Ban la tro ly bien tap chuyen phan tich nhan vat trong tieu thuyet fantasy Han Quoc.

---

# Nhiem vu
Doc doan van ban goc ben duoi, sau do **trich xuat / cap nhat** thong tin nhan vat.

---

# Van ban goc (raw):
${raw}

---

# Glossary ten nhan vat / thuat ngu (bat buoc dung lam ten header):
${glossaryText}

---

# Du lieu nhan vat hien co (de tham khao, tranh mau thuan, chi bo sung them):
${existing || "(Chua co du lieu nhan vat)"}

---

# Yeu cau chi tiet

1. **Trich xuat** tat ca nhan vat QUAN TRONG (co thoai, hanh dong, tac dong den plot).
2. **Bo qua** NPC phu khong dang ke, chi xuat hien 1 lan.
3. Voi moi nhan vat, dien day du thong tin theo template ben duoi.
4. Neu nhan vat da co trong "Du lieu hien co", hay **hop nhat va bo sung** (khong xoa du lieu cu, chi cap nhat).
5. Thong tin bang tieng Viet. Ten nhan vat va thuat ngu theo glossary (neu biet).

**QUY TAC DAT TEN HEADER (BAT BUOC):**
- Header \`## Ten nhan vat\` PHAI la **ten day du, chinh thuc theo Glossary**.
- Neu nhan vat da co trong "Du lieu hien co", **giu nguyen ten header do**.
- Khong dung biet danh, danh hieu, hoac ten tat lam header.
- Neu ten khong co trong Glossary, dung ten rieng day du nhat co the tu van ban.

---

# Template cho moi nhan vat (bat buoc):

\`\`\`
## [Ten nhan vat]

### Thong tin co ban
- **Ten goc**: (ten trong nguyen tac Han/Han/Anh)
- **Biet danh / Danh hieu**: (neu co)
- **Gioi tinh**: Nam / Nu / Khong xac dinh
- **Tuoi / Do tuoi uoc luong**:
- **Chung toc / Xuat than**:
- **Dia vi / Chuc vu**:
- **Phe / To chuc**:

### Ghi chu dich thuat
- (Ten goc, cach dich dac biet, luu y khi dich thoai...)
\`\`\`

---

# Dinh dang dau ra
> Bat dau bang dong \`###CHAR_START###\`
> Ket thuc bang dong \`###CHAR_END###\`
> O giua: **toan bo** noi dung Markdown theo template tren cho tung nhan vat.
> KHONG them bat ky giai thich hay text nao ngoai phan giua hai marker.`;
}

export function extractCharacterBlock(response: string) {
  const cleaned = response.trim().replace(/^```(?:markdown|md)?\s*/i, "").replace(/\s*```$/, "").replace(/^\\(?=#+\s*(?:CHAR_START|CHAR_END))/gm, "");
  const start = cleaned.match(/^\s*###\s*CHAR_START\s*###\s*$/im);
  const end = cleaned.match(/^\s*###\s*CHAR_END\s*###\s*$/im);
  if (start?.index !== undefined && end?.index !== undefined && end.index > start.index + start[0].length) return cleaned.slice(start.index + start[0].length, end.index).trim();
  return /^##\s+\S/m.test(cleaned) ? cleaned : "";
}

function characterBlocks(value: string) {
  return Object.fromEntries(value.split(/\n(?=## )/).map((block) => block.trim()).filter((block) => block.startsWith("## ")).map((block) => [block.split("\n")[0].slice(3).trim(), block]));
}

export function mergeCharacterMarkdown(existing: string, incoming: string) {
  const merged = characterBlocks(existing);
  for (const [name, nextBlockValue] of Object.entries(characterBlocks(incoming))) {
    let nextBlock = nextBlockValue;
    const oldBlock = merged[name];
    if (oldBlock) {
      const newFields = new Set([...nextBlock.matchAll(/^- \*\*(.+?)\*\*\s*:/gm)].map((match) => match[1].trim().toLocaleLowerCase("vi")));
      const preserved = oldBlock.split("\n").filter((line) => { const field = line.match(/^- \*\*(.+?)\*\*\s*:/); return field && !newFields.has(field[1].trim().toLocaleLowerCase("vi")); });
      if (preserved.length) nextBlock = `${nextBlock.trim()}\n\n### Thông tin được bảo toàn\n${preserved.join("\n")}`;
    }
    merged[name] = nextBlock;
  }
  return Object.keys(merged).sort((a, b) => a.localeCompare(b, "vi")).map((name) => merged[name]).join("\n\n---\n\n");
}

function glossaryPrompt(batch: Chapter[], existing: Project["glossary"]) {
  const raw = batch.map((item) => `${item.title}\n${item.source}`).join("\n\n");
  const old = existing?.map((item) => `${item.source} = ${item.target}`).join("\n") || "";
  return `Bạn là công cụ xây dựng glossary cho bản dịch tiểu thuyết.

Từ nội dung raw dưới đây, trích xuất thuật ngữ, danh hiệu, xưng hô, tên riêng
và địa danh cần giữ nhất quán. Bỏ qua từ phổ thông và vật dụng đời thường.
Tên riêng ngoại lai phải chuyển về dạng La-tinh gốc nếu nhận diện được.
Thuật ngữ và danh hiệu dịch sang tiếng Việt hiện đại, đúng ngữ cảnh.

Glossary hiện có:
${old}

Nội dung raw:
${raw}

Chỉ xuất mỗi dòng theo dạng:
Nguyên văn = Bản dịch

Bắt đầu bằng ###START### và kết thúc bằng ###END###.
Không thêm Markdown hoặc lời giải thích.`;
}

export function parseGlossaryResponse(response: string) {
  const start = response.indexOf("###START###");
  const end = response.indexOf("###END###", start + 11);
  if (start < 0 || end < 0) throw new Error("Gemini trả glossary thiếu marker START/END.");
  return response.slice(start + 11, end).split(/\r?\n/).map((line) => line.trim()).filter(Boolean).map((line) => {
    const separator = line.indexOf("=");
    if (separator <= 0) return null;
    const source = line.slice(0, separator).trim();
    const target = line.slice(separator + 1).trim();
    return source && target ? { source, target } : null;
  }).filter((item): item is { source: string; target: string } => Boolean(item));
}

const CHARACTER_HEADER = "# Hồ Sơ Nhân Vật\n\n> File được tạo tự động. Bạn có thể chỉnh sửa trực tiếp; lần phân tích sau sẽ đọc và bổ sung dữ liệu hiện có.\n\n---\n\n";

interface PendingChapterImport {
  fileName: string;
  imported: ImportedNovel;
  preview: ChapterImportPreview;
  conflict: "skip" | "overwrite";
}

interface ManualTranslationDraft {
  prompt: string;
  result: string;
}

export function App() {
  const [projects, setProjects] = useState<Project[]>([]);
  const [projectId, setProjectId] = useState("");
  const [chapters, setChapters] = useState<Chapter[]>([]);
  const [chapterId, setChapterId] = useState("");
  const [assets, setAssets] = useState<ProjectAsset[]>([]);
  const [view, setView] = useState<WorkspaceView>("translate");
  const [settings, setSettings] = useState<AppSettings>(DEFAULT_SETTINGS);
  const [apiKey, setApiKey] = useState("");
  const [busy, setBusy] = useState<AiTaskKind | "translate-all" | "characters" | "context" | null>(null);
  const [streamStatus, setStreamStatus] = useState<{ chapterId: string; stage: "translate" | "polish"; line: number | null } | null>(null);
  const [importingNovel, setImportingNovel] = useState(false);
  const [notice, setNotice] = useState("");
  const [error, setError] = useState("");
  const [ready, setReady] = useState(false);
  const [deleteModalOpen, setDeleteModalOpen] = useState(false);
  const [chapterImport, setChapterImport] = useState<PendingChapterImport | null>(null);
  const [manualTranslation, setManualTranslation] = useState<ManualTranslationDraft | null>(null);
  const abortRef = useRef<AbortController | null>(null);
  const backupImportRef = useRef<HTMLInputElement>(null);
  const novelImportRef = useRef<HTMLInputElement>(null);
  const chapterImportRef = useRef<HTMLInputElement>(null);

  const project = projects.find((item) => item.id === projectId);
  const chapter = chapters.find((item) => item.id === chapterId);

  const refreshProjects = useCallback(async (preferredId?: string) => {
    const items = await db.projects.orderBy("updatedAt").reverse().toArray();
    setProjects(items);
    setProjectId((current) => preferredId || (items.some((item) => item.id === current) ? current : items[0]?.id || ""));
  }, []);

  useEffect(() => {
    void (async () => {
      const saved = await db.settings.get("app");
      const legacyTask = saved ? {
        model: saved.model,
        maxOutputTokens: saved.maxOutputTokens,
        systemInstruction: "",
      } : DEFAULT_TASKS.translate;
      const tasks = Object.fromEntries((Object.keys(DEFAULT_TASKS) as AiTaskKind[]).map((kind) => [
        kind,
        { ...DEFAULT_TASKS[kind], ...(kind === "translate" ? legacyTask : {}), ...saved?.tasks?.[kind] },
      ])) as Record<AiTaskKind, AiTaskSettings>;
      const next = { ...DEFAULT_SETTINGS, ...saved, tasks };
      setSettings(next);
      setApiKey(next.rememberApiKey ? next.apiKey || "" : sessionStorage.getItem("gemini-api-key") || "");
      await refreshProjects();
      setReady(true);
    })().catch((reason) => setError(reason instanceof Error ? reason.message : "Không thể mở dữ liệu cục bộ."));
  }, [refreshProjects]);

  useEffect(() => {
    if (!projectId) {
      setChapters([]);
      setAssets([]);
      setChapterId("");
      return;
    }
    void Promise.all([
      db.chapters.where("projectId").equals(projectId).sortBy("order"),
      db.assets.where("projectId").equals(projectId).toArray(),
    ]).then(([items, storedAssets]) => {
      setChapters(items);
      setAssets(storedAssets);
      setChapterId((current) => items.some((item) => item.id === current) ? current : resumeChapterId(items));
    });
  }, [projectId]);

  useEffect(() => {
    if (!deleteModalOpen) return;
    const closeOnEscape = (event: KeyboardEvent) => {
      if (event.key === "Escape") setDeleteModalOpen(false);
    };
    window.addEventListener("keydown", closeOnEscape);
    return () => window.removeEventListener("keydown", closeOnEscape);
  }, [deleteModalOpen]);

  async function createProject() {
    const stamp = now();
    const item: Project = {
      id: crypto.randomUUID(),
      name: `Dự án ${projects.length + 1}`,
      sourceLanguage: "Tiếng Hàn",
      targetLanguage: "Tiếng Việt",
      characters: "",
      contextV1: "index: []\nstyle_notes: []\nglossary: []",
      createdAt: stamp,
      updatedAt: stamp,
    };
    await db.projects.add(item);
    await refreshProjects(item.id);
    setView("translate");
    setNotice("Đã tạo dự án. Dữ liệu đang được lưu trong trình duyệt này.");
  }

  async function updateProject(fields: Partial<Project>) {
    if (!project) return;
    const updated = { ...project, ...fields, updatedAt: now() };
    setProjects((items) => items.map((item) => item.id === updated.id ? updated : item));
    await db.projects.put(updated);
  }

  async function confirmDeleteProject() {
    if (!project) return;
    const deletedName = project.name;
    await deleteProject(project.id);
    setDeleteModalOpen(false);
    setChapters([]);
    setAssets([]);
    setChapterId("");
    await refreshProjects();
    setView("translate");
    setNotice(`Đã xóa truyện “${deletedName}” cùng toàn bộ chương và ảnh.`);
  }

  async function createChapter() {
    if (!project) return;
    const item: Chapter = {
      id: crypto.randomUUID(),
      projectId: project.id,
      title: `Chương ${chapters.length + 1}`,
      source: "",
      translation: "",
      order: chapters.length + 1,
      updatedAt: now(),
    };
    await db.chapters.add(item);
    setChapters((items) => [...items, item]);
    setChapterId(item.id);
  }

  async function updateChapter(fields: Partial<Chapter>) {
    if (!chapter) return;
    const updated = { ...chapter, ...fields, updatedAt: now() };
    setChapters((items) => items.map((item) => item.id === updated.id ? updated : item));
    await db.chapters.put(updated);
  }

  async function runTask(kind: AiTaskKind | "characters" | "context") {
    if (!project || !chapter?.source.trim()) {
      setError("Hãy chọn dự án và nhập nội dung chương nguồn trước.");
      return;
    }
    const apiKeys = parseApiKeys(apiKey);
    if (!apiKeys.length) {
      setView("settings");
      setError("Hãy nhập Gemini API key trong Thiết lập.");
      return;
    }
    if ((kind === "polish" || kind === "review") && !chapter.translation.trim()) {
      setError("Chương cần có bản dịch trước khi hiệu đính hoặc review.");
      return;
    }
    if (kind === "translate") {
      await translateSelectedChapter(apiKeys);
      return;
    }
    setBusy(kind);
    setError("");
    setNotice("");
    const controller = new AbortController();
    abortRef.current = controller;
    try {
      const projectContext = translationContextYaml(project, `${chapter.title}\n${chapter.source}\n${chapters[chapters.findIndex((item) => item.id === chapter.id) + 1]?.source || ""}`);
      const prompt = kind === "polish"
          ? polishPrompt(chapter.source, chapter.translation, projectContext, project.characters, project.polishPromptRole, project.polishPromptTask)
          : kind === "pronouns"
            ? pronounsPrompt(chapter.source, chapter.translation, project.pronouns || "")
            : kind === "review"
              ? reviewPrompt({ chapterId: chapter.localFileName?.replace(/\.md$/i, "") || chapter.id, chapterNumber: chapter.order, rawTitle: chapter.title, source: chapter.source, translatedTitle: chapter.translatedTitle || chapter.title, translation: chapter.translation, context: projectContext })
              : kind === "characters"
                ? charactersPrompt(chapter.source, project.characters)
                : contextPrompt(chapter.source, projectContext, project.characters);
      const taskKind: AiTaskKind = kind === "characters" || kind === "context" ? "translate" : kind;
      const taskSettings = settings.tasks?.[taskKind] || DEFAULT_TASKS[taskKind];
      let result: string;
      if (kind === "polish") {
        const original = chapter.translation;
        let streamed = "";
        let renderedLines = 0;
        result = await streamWithApiKeys(apiKeys, 0, {
          model: taskSettings.model,
          maxOutputTokens: taskSettings.maxOutputTokens,
          ...prompt,
          systemInstruction: taskSettings.systemInstruction.trim() || prompt.systemInstruction,
          signal: controller.signal,
          onText: (delta) => {
            streamed += delta;
            const incoming = streamed.split("\n");
            const ready = Math.max(0, incoming.length - 1);
            if (ready <= renderedLines) return;
            renderedLines = ready;
            const next = original.split("\n");
            for (let line = 0; line < ready; line += 1) next[line] = incoming[line];
            showStreamedChapter(chapter.id, { translation: next.join("\n") }, "polish", ready - 1);
          },
        }, () => {
          streamed = "";
          renderedLines = 0;
          showStreamedChapter(chapter.id, { translation: original }, "polish", null);
        });
        showStreamedChapter(chapter.id, { translation: result }, "polish", Math.max(0, result.split("\n").length - 1));
      } else result = await generateWithApiKeys(apiKeys, 0, {
          model: taskSettings.model,
          maxOutputTokens: taskSettings.maxOutputTokens,
          ...prompt,
          systemInstruction: taskSettings.systemInstruction.trim() || prompt.systemInstruction,
          signal: controller.signal,
        });
      if (kind === "polish") await updateChapter({ translation: result });
      if (kind === "pronouns") await updateProject({ pronouns: result });
      if (kind === "review") {
        const parsed = parseReviewResponse(result);
        const review = reviewResultText(parsed);
        await updateChapter({ review, localReviewText: review, localReviewData: { chapter_number: chapter.order, score: parsed.overall_score, issue_count: parsed.issues.length, gender_ok: parsed.gender_ok, address_ok: parsed.address_ok, issues: parsed.issues, summary: parsed.summary } });
      }
      if (kind === "characters") await updateProject({ characters: result });
      if (kind === "context") await updateProject({ contextV1: result.replace(/^```(?:yaml)?\s*|\s*```$/g, "") });
      const messages: Record<typeof kind, string> = {
        polish: "Đã hiệu đính và cập nhật bản dịch.",
        pronouns: "Đã cập nhật xưng hô dự án.", review: "Đã lưu review của chương.",
        characters: "Đã cập nhật hồ sơ nhân vật.", context: "Đã cập nhật Context V1.",
      };
      setNotice(messages[kind]);
    } catch (reason) {
      if (kind === "polish") setChapters((items) => items.map((item) => item.id === chapter.id ? chapter : item));
      if (reason instanceof DOMException && reason.name === "AbortError") setNotice("Đã dừng tác vụ.");
      else setError(reason instanceof Error ? reason.message : "Tác vụ thất bại.");
    } finally {
      abortRef.current = null;
      setStreamStatus(null);
      setBusy(null);
    }
  }

  async function generateWithApiKeys(keys: string[], startIndex: number, options: Omit<Parameters<typeof generateContent>[0], "apiKey">) {
    let lastError: unknown;
    const attempts = Math.max(3, keys.length);
    for (let offset = 0; offset < attempts; offset += 1) {
      try {
        return await generateContent({ ...options, apiKey: keys[(startIndex + offset) % keys.length] });
      } catch (reason) {
        if (reason instanceof DOMException && reason.name === "AbortError") throw reason;
        if (!(reason instanceof GeminiRequestError)) throw reason;
        lastError = reason;
      }
    }
    throw lastError || new Error("Không có Gemini API key khả dụng.");
  }

  async function streamWithApiKeys(keys: string[], startIndex: number, options: Omit<Parameters<typeof streamInteraction>[0], "apiKey">, onAttempt: () => void) {
    let lastError: unknown;
    const attempts = Math.max(3, keys.length);
    for (let offset = 0; offset < attempts; offset += 1) {
      try {
        onAttempt();
        return await streamInteraction({ ...options, apiKey: keys[(startIndex + offset) % keys.length] });
      } catch (reason) {
        if (reason instanceof DOMException && reason.name === "AbortError") throw reason;
        if (!(reason instanceof GeminiRequestError)) throw reason;
        lastError = reason;
      }
    }
    throw lastError || new Error("Không có Gemini API key khả dụng.");
  }

  function showStreamedChapter(chapterId: string, fields: Partial<Chapter>, stage: "translate" | "polish", line: number | null) {
    setChapters((items) => items.map((item) => item.id === chapterId ? { ...item, ...fields } : item));
    setStreamStatus({ chapterId, stage, line });
  }

  function taskEnabled(kind: AiTaskKind) {
    const model = (settings.tasks?.[kind] || DEFAULT_TASKS[kind]).model.trim().toLowerCase();
    return model !== "" && model !== "none";
  }

  function contextForChapter(item: Chapter, itemIndex: number) {
    return project ? translationContextYaml(project, `${item.title}\n${item.source}\n${chapters[itemIndex + 1]?.source || ""}`) : "";
  }

  function previousChapterContext(itemIndex: number, chapterState: Chapter[]) {
    return chapterState.slice(Math.max(0, itemIndex - 3), itemIndex).filter((item) => item.translation.trim()).map((item) => `${item.translatedTitle || item.title}\n${item.translation}`).join("\n\n\n\n\n");
  }

  function openManualTranslation() {
    if (!project || !chapter?.source.trim()) return;
    const itemIndex = chapters.findIndex((item) => item.id === chapter.id);
    const request = translationPrompt({
      title: chapter.title,
      source: chapter.source,
      context: contextForChapter(chapter, itemIndex),
      characters: project.characters,
      pronouns: project.pronouns || "",
      previousChapters: previousChapterContext(itemIndex, chapters),
      from: project.sourceLanguage,
      to: project.targetLanguage,
      role: project.promptRole,
      task: project.promptTask,
    });
    const customSystem = (settings.tasks?.translate || DEFAULT_TASKS.translate).systemInstruction.trim();
    setManualTranslation({ prompt: [customSystem, request.prompt].filter(Boolean).join("\n\n"), result: "" });
  }

  async function applyManualTranslation() {
    if (!manualTranslation) return;
    try {
      const translated = parseTranslationResponse(manualTranslation.result);
      await updateChapter({ translatedTitle: translated.title, translation: translated.content });
      setManualTranslation(null);
      setNotice("Đã lưu kết quả dịch thủ công.");
    } catch (reason) {
      setError(reason instanceof Error ? reason.message : "Không thể đọc kết quả dịch thủ công.");
    }
  }

  async function translateChapterPipeline(item: Chapter, itemIndex: number, chapterState: Chapter[], keys: string[], keyOffset: number, signal: AbortSignal, pronounMemory: string) {
    if (!project) throw new Error("Không tìm thấy dự án.");
    const translateSettings = settings.tasks?.translate || DEFAULT_TASKS.translate;
    const context = contextForChapter(item, itemIndex);
    const prompt = translationPrompt({
      title: item.title,
      source: item.source,
      context,
      characters: project.characters,
      pronouns: pronounMemory,
      previousChapters: previousChapterContext(itemIndex, chapterState),
      from: project.sourceLanguage,
      to: project.targetLanguage,
      role: project.promptRole,
      task: project.promptTask,
    });
    let translated: { title: string; content: string } | undefined;
    let lastError: unknown;
    for (let attempt = 0; attempt < 3; attempt += 1) {
      try {
        let streamed = "";
        let streamFrame: number | null = null;
        let pending: ReturnType<typeof parseTranslationStream> = null;
        const renderPending = () => {
          streamFrame = null;
          if (!pending) return;
          const partial = pending;
          pending = null;
          const line = partial.content ? partial.content.split("\n").length - 1 : null;
          showStreamedChapter(item.id, { translatedTitle: partial.title || item.title, translation: partial.content }, "translate", line);
        };
        const response = await streamWithApiKeys(keys, keyOffset + attempt, {
          model: translateSettings.model,
          maxOutputTokens: translateSettings.maxOutputTokens,
          ...prompt,
          systemInstruction: translateSettings.systemInstruction.trim() || prompt.systemInstruction,
          signal,
          onText: (delta) => {
            streamed += delta;
            const partial = parseTranslationStream(streamed);
            if (!partial) return;
            pending = partial;
            if (streamFrame === null) streamFrame = window.requestAnimationFrame(renderPending);
          },
        }, () => {
          if (streamFrame !== null) window.cancelAnimationFrame(streamFrame);
          streamed = "";
          streamFrame = null;
          pending = null;
          showStreamedChapter(item.id, { translatedTitle: item.title, translation: "" }, "translate", null);
        });
        if (streamFrame !== null) window.cancelAnimationFrame(streamFrame);
        translated = parseTranslationResponse(response);
        showStreamedChapter(item.id, { translatedTitle: translated.title, translation: translated.content }, "translate", Math.max(0, translated.content.split("\n").length - 1));
        break;
      } catch (reason) {
        lastError = reason;
        if (reason instanceof DOMException && reason.name === "AbortError") throw reason;
      }
    }
    if (!translated) throw lastError || new Error("Không thể dịch chương sau 3 lần thử.");

    let content = translated.content;
    if (taskEnabled("polish")) {
      const polishSettings = settings.tasks?.polish || DEFAULT_TASKS.polish;
      const polish = polishPrompt(item.source, content, context, project.characters, project.polishPromptRole, project.polishPromptTask);
      const original = content;
      let streamed = "";
      let renderedLines = 0;
      content = await streamWithApiKeys(keys, keyOffset + 1, { model: polishSettings.model, maxOutputTokens: polishSettings.maxOutputTokens, ...polish, systemInstruction: polishSettings.systemInstruction.trim() || polish.systemInstruction, signal, onText: (delta) => {
        streamed += delta;
        const incoming = streamed.split("\n");
        const ready = Math.max(0, incoming.length - 1);
        if (ready <= renderedLines) return;
        renderedLines = ready;
        const next = original.split("\n");
        for (let line = 0; line < ready; line += 1) next[line] = incoming[line];
        showStreamedChapter(item.id, { translation: next.join("\n") }, "polish", ready - 1);
      } }, () => {
        streamed = "";
        renderedLines = 0;
        showStreamedChapter(item.id, { translation: original }, "polish", null);
      });
      showStreamedChapter(item.id, { translation: content }, "polish", Math.max(0, content.split("\n").length - 1));
      for (let attempt = 0; attempt < 3 && containsCjkOrHangul(content); attempt += 1) {
        content = await generateWithApiKeys(keys, keyOffset + attempt + 2, { model: polishSettings.model, maxOutputTokens: polishSettings.maxOutputTokens, systemInstruction: "Bạn sửa bản dịch còn sót chữ Hán, Nhật hoặc Hàn. Dịch hết phần còn sót sang tiếng Việt, giữ nguyên đầy đủ nội dung, Markdown ảnh và dấu hội thoại. Chỉ trả về bản dịch hoàn chỉnh.", prompt: `# Nguyên tác\n${item.source}\n\n# Bản dịch còn sót chữ ngoại ngữ\n${content}`, signal });
      }
      if (containsCjkOrHangul(content)) throw new Error(`${item.title} vẫn còn ký tự Hán, Nhật hoặc Hàn sau 3 lần sửa.`);
    }

    let nextPronouns = pronounMemory;
    if (taskEnabled("pronouns")) {
      const pronounSettings = settings.tasks?.pronouns || DEFAULT_TASKS.pronouns;
      const pronoun = pronounsPrompt(item.source, content, pronounMemory);
      nextPronouns = await generateWithApiKeys(keys, keyOffset + 2, { model: pronounSettings.model, maxOutputTokens: pronounSettings.maxOutputTokens, ...pronoun, systemInstruction: pronounSettings.systemInstruction.trim() || pronoun.systemInstruction, signal });
    }

    let review = item.review || "";
    let localReviewData = item.localReviewData;
    let localReviewText = item.localReviewText;
    if (taskEnabled("review")) {
      const reviewSettings = settings.tasks?.review || DEFAULT_TASKS.review;
      const reviewRequest = reviewPrompt({ chapterId: item.localFileName?.replace(/\.md$/i, "") || item.id, chapterNumber: item.order, rawTitle: item.title, source: item.source, translatedTitle: translated.title, translation: content, context });
      const response = await generateWithApiKeys(keys, keyOffset + 3, { model: reviewSettings.model, maxOutputTokens: reviewSettings.maxOutputTokens, ...reviewRequest, systemInstruction: reviewSettings.systemInstruction.trim() || reviewRequest.systemInstruction, signal });
      const parsed = parseReviewResponse(response);
      review = reviewResultText(parsed);
      localReviewText = review;
      localReviewData = { chapter_number: item.order, score: parsed.overall_score, issue_count: parsed.issues.length, gender_ok: parsed.gender_ok, address_ok: parsed.address_ok, issues: parsed.issues, summary: parsed.summary };
    }
    return { chapter: { ...item, translatedTitle: translated.title, translation: content, review, localReviewData, localReviewText, updatedAt: now() }, pronouns: nextPronouns };
  }

  async function persistPipelineResult(result: Awaited<ReturnType<typeof translateChapterPipeline>>) {
    if (!project) return;
    await db.transaction("rw", db.chapters, db.projects, async () => {
      await db.chapters.put(result.chapter);
      await db.projects.update(project.id, { pronouns: result.pronouns, updatedAt: now() });
    });
    setChapters((items) => items.map((item) => item.id === result.chapter.id ? result.chapter : item));
    setProjects((items) => items.map((item) => item.id === project.id ? { ...item, pronouns: result.pronouns, updatedAt: now() } : item));
  }

  async function translateSelectedChapter(apiKeys: string[]) {
    if (!chapter) return;
    const controller = new AbortController();
    abortRef.current = controller;
    setBusy("translate");
    setError("");
    setNotice(`Đang chạy pipeline: ${chapter.title}`);
    try {
      const index = chapters.findIndex((item) => item.id === chapter.id);
      const result = await translateChapterPipeline(chapter, index, chapters, apiKeys, 0, controller.signal, project?.pronouns || "");
      await persistPipelineResult(result);
      setNotice("Đã dịch, hiệu đính, cập nhật xưng hô và review chương.");
    } catch (reason) {
      setChapters((items) => items.map((item) => item.id === chapter.id ? chapter : item));
      if (reason instanceof DOMException && reason.name === "AbortError") setNotice("Đã dừng tác vụ.");
      else setError(reason instanceof Error ? reason.message : "Pipeline dịch thất bại.");
    } finally {
      abortRef.current = null;
      setStreamStatus(null);
      setBusy(null);
    }
  }

  async function analyzeCharacters() {
    if (!project || !chapters.length) return;
    const keys = parseApiKeys(apiKey);
    if (!keys.length) {
      setView("settings");
      setError("Hãy thêm ít nhất một Gemini API key trong Thiết lập.");
      return;
    }
    const savedIndex = Math.min(project.characterIndex || 0, chapters.length);
    const startIndex = savedIndex >= chapters.length ? 0 : savedIndex;
    const batchSize = Math.min(100, Math.max(1, Math.trunc(project.characterBatchSize || 10)));
    const controller = new AbortController();
    abortRef.current = controller;
    setBusy("characters");
    setError("");
    let body = Object.values(characterBlocks(project.characters)).join("\n\n---\n\n");
    try {
      for (let offset = startIndex; offset < chapters.length; offset += batchSize) {
        const segment = chapters.slice(offset, offset + batchSize);
        const batch = segment.filter((item) => item.source.trim());
        if (!batch.length) continue;
        setNotice(`Hồ sơ nhân vật: chương ${offset + 1}-${offset + batch.length}/${chapters.length}`);
        const prompt = characterPrompt(batch, body, project.glossary);
        let block = "";
        let lastError: unknown;
        for (let attempt = 0; attempt < 3 && !block; attempt += 1) {
          try {
            const response = await generateWithApiKeys(keys, attempt, { model: DEFAULT_TASKS.translate.model, maxOutputTokens: null, systemInstruction: "", prompt: attempt ? `${prompt}\n\nLƯU Ý SỬA OUTPUT: Trả ít nhất một header \`## Tên nhân vật\` giữa \`###CHAR_START###\` và \`###CHAR_END###\`.` : prompt, signal: controller.signal });
            block = extractCharacterBlock(response);
            if (!Object.keys(characterBlocks(block)).length) block = "";
          } catch (reason) { lastError = reason; if (reason instanceof DOMException && reason.name === "AbortError") throw reason; }
        }
        if (!block) throw lastError || new Error("Gemini trả hồ sơ nhân vật sai marker sau 3 lần; tiến độ chưa được tăng.");
        body = mergeCharacterMarkdown(body, block);
        const characterIndex = Math.min(offset + segment.length, chapters.length);
        const characters = CHARACTER_HEADER + body;
        await db.projects.update(project.id, { characters, characterIndex, updatedAt: now() });
        setProjects((items) => items.map((item) => item.id === project.id ? { ...item, characters, characterIndex, updatedAt: now() } : item));
      }
      setNotice(`Đã cập nhật hồ sơ nhân vật từ ${chapters.length - startIndex} chương.`);
    } catch (reason) {
      if (reason instanceof DOMException && reason.name === "AbortError") setNotice("Đã dừng phân tích nhân vật; tiến độ các batch hoàn tất đã được lưu.");
      else setError(reason instanceof Error ? reason.message : "Phân tích nhân vật thất bại.");
    } finally { abortRef.current = null; setBusy(null); }
  }

  async function analyzeGlossary() {
    if (!project || !chapters.length) return;
    const keys = parseApiKeys(apiKey);
    if (!keys.length) {
      setView("settings");
      setError("Hãy thêm ít nhất một Gemini API key trong Thiết lập.");
      return;
    }
    const savedIndex = Math.min(project.glossaryIndex || 0, chapters.length);
    const startIndex = savedIndex >= chapters.length ? 0 : savedIndex;
    const batchSize = Math.min(100, Math.max(1, Math.trunc(project.glossaryBatchSize || 30)));
    const controller = new AbortController();
    abortRef.current = controller;
    setBusy("context");
    setError("");
    let glossary = [...(project.glossary || [])];
    try {
      for (let offset = startIndex; offset < chapters.length; offset += batchSize) {
        const segment = chapters.slice(offset, offset + batchSize);
        const batch = segment.filter((item) => item.source.trim());
        if (!batch.length) continue;
        setNotice(`Glossary: chương ${offset + 1}-${offset + batch.length}/${chapters.length}`);
        const prompt = glossaryPrompt(batch, glossary);
        let incoming: Array<{ source: string; target: string }> = [];
        let lastError: unknown;
        for (let attempt = 0; attempt < 3 && !incoming.length; attempt += 1) {
          try {
            const response = await generateWithApiKeys(keys, attempt, { model: DEFAULT_TASKS.translate.model, maxOutputTokens: 16000, systemInstruction: "", prompt, signal: controller.signal });
            incoming = parseGlossaryResponse(response);
          } catch (reason) { lastError = reason; if (reason instanceof DOMException && reason.name === "AbortError") throw reason; }
        }
        if (!incoming.length) throw lastError || new Error("Gemini không trả về glossary hợp lệ sau 3 lần; tiến độ chưa được tăng.");
        const merged = new Map(glossary.map((item) => [item.source, item]));
        incoming.forEach((item) => merged.set(item.source, { id: merged.get(item.source)?.id || crypto.randomUUID(), ...item }));
        glossary = [...merged.values()];
        const glossaryIndex = Math.min(offset + segment.length, chapters.length);
        await db.projects.update(project.id, { glossary, glossaryIndex, updatedAt: now() });
        setProjects((items) => items.map((item) => item.id === project.id ? { ...item, glossary, glossaryIndex, updatedAt: now() } : item));
      }
      setNotice(`Đã cập nhật glossary từ ${chapters.length - startIndex} chương.`);
    } catch (reason) {
      if (reason instanceof DOMException && reason.name === "AbortError") setNotice("Đã dừng tạo glossary; tiến độ các batch hoàn tất đã được lưu.");
      else setError(reason instanceof Error ? reason.message : "Tạo glossary thất bại.");
    } finally { abortRef.current = null; setBusy(null); }
  }

  async function translateToEnd() {
    if (!project || !chapter) return;
    const apiKeys = parseApiKeys(apiKey);
    if (!apiKeys.length) {
      setView("settings");
      setError("Hãy thêm ít nhất một Gemini API key trong Thiết lập.");
      return;
    }
    const startIndex = chapters.findIndex((item) => item.id === chapter.id);
    const queue = chapters.slice(Math.max(0, startIndex)).filter((item) => item.source.trim() && !item.translation.trim());
    if (!queue.length) {
      setNotice("Không còn chương chưa dịch từ vị trí hiện tại.");
      return;
    }
    const controller = new AbortController();
    abortRef.current = controller;
    setBusy("translate-all");
    setError("");
    let activeItem: Chapter | null = null;
    try {
      let workingChapters = [...chapters];
      let pronounMemory = project.pronouns || "";
      for (let index = 0; index < queue.length; index += 1) {
        const item = queue[index];
        activeItem = item;
        setChapterId(item.id);
        setNotice(`Pipeline ${index + 1}/${queue.length}: ${item.title}`);
        const itemIndex = workingChapters.findIndex((current) => current.id === item.id);
        const result = await translateChapterPipeline(item, itemIndex, workingChapters, apiKeys, index, controller.signal, pronounMemory);
        await persistPipelineResult(result);
        pronounMemory = result.pronouns;
        workingChapters = workingChapters.map((current) => current.id === result.chapter.id ? result.chapter : current);
      }
      setNotice(`Đã hoàn tất pipeline cho ${queue.length} chương.`);
    } catch (reason) {
      if (activeItem) setChapters((items) => items.map((item) => item.id === activeItem?.id ? activeItem : item));
      if (reason instanceof DOMException && reason.name === "AbortError") setNotice("Đã dừng dịch đến hết sau chương vừa hoàn thành.");
      else setError(reason instanceof Error ? reason.message : "Dịch đến hết thất bại.");
    } finally {
      abortRef.current = null;
      setStreamStatus(null);
      setBusy(null);
    }
  }

  async function saveSettings() {
    const stored: AppSettings = {
      ...settings,
      apiKey: settings.rememberApiKey ? apiKey.trim() : undefined,
    };
    await db.settings.put(stored);
    if (settings.rememberApiKey) sessionStorage.removeItem("gemini-api-key");
    else sessionStorage.setItem("gemini-api-key", apiKey.trim());
    setNotice(settings.rememberApiKey ? "Đã lưu thiết lập và API key trên thiết bị này." : "Đã lưu thiết lập. API key chỉ giữ đến khi đóng tab.");
  }

  async function handleExport() {
    if (!project) return;
    const data = await exportLocalProject(project, chapters, assets);
    const blob = new Blob([data.buffer as ArrayBuffer], { type: "application/zip" });
    downloadBlob(`${project.name.replace(/[^\p{L}\p{N}._-]+/gu, "-")}.zip`, blob);
    setNotice("Đã xuất ZIP tương thích cấu trúc app local.");
  }

  async function handleImport(file?: File) {
    if (!file) return;
    try {
      if (!file.name.toLocaleLowerCase().endsWith(".zip")) throw new Error("Chỉ hỗ trợ bản sao ZIP của app local.");
      const archive = await importLocalProject(await file.arrayBuffer());
      const duplicate = projects.some((item) => item.name.toLocaleLowerCase("vi") === archive.project.name.toLocaleLowerCase("vi"));
      if (duplicate) archive.project.name = `${archive.project.name} (khôi phục)`;
      await db.transaction("rw", db.projects, db.chapters, db.assets, async () => {
        await db.projects.add(archive.project);
        if (archive.chapters.length) await db.chapters.bulkAdd(archive.chapters);
        if (archive.assets.length) await db.assets.bulkAdd(archive.assets);
      });
      const id = archive.project.id;
      await refreshProjects(id);
      setNotice("Đã khôi phục truyện cùng raw, translated, ảnh và bộ nhớ dự án.");
    } catch (reason) {
      setError(reason instanceof Error ? reason.message : "Tệp sao lưu không hợp lệ.");
    }
  }

  async function handleNovelImport(file?: File) {
    if (!file) return;
    setImportingNovel(true);
    setError("");
    setNotice("");
    try {
      const imported = await parseNovelFile(file);
      const stamp = now();
      const importedProject: Project = {
        id: crypto.randomUUID(),
        name: imported.name,
        sourceLanguage: "Tự động nhận diện",
        targetLanguage: "Tiếng Việt",
        characters: "",
        contextV1: "index: []\nstyle_notes: []\nglossary: []",
        createdAt: stamp,
        updatedAt: stamp,
      };
      const importedChapters: Chapter[] = imported.chapters.map((item, index) => ({
        id: crypto.randomUUID(),
        projectId: importedProject.id,
        title: item.title,
        source: item.source,
        translation: "",
        order: index + 1,
        updatedAt: stamp,
      }));
      const importedAssets: ProjectAsset[] = imported.assets.map((asset) => ({ ...asset, projectId: importedProject.id }));
      await db.transaction("rw", db.projects, db.chapters, db.assets, async () => {
        await db.projects.add(importedProject);
        await db.chapters.bulkAdd(importedChapters);
        if (importedAssets.length) await db.assets.bulkAdd(importedAssets);
      });
      await refreshProjects(importedProject.id);
      setView("translate");
      setNotice(`Đã nhập ${importedChapters.length} chương và ${importedAssets.length} ảnh từ ${file.name}.`);
    } catch (reason) {
      setError(reason instanceof Error ? reason.message : "Không thể nhập tệp truyện.");
    } finally {
      setImportingNovel(false);
      if (novelImportRef.current) novelImportRef.current.value = "";
    }
  }

  async function handleChapterImport(file?: File) {
    if (!file || !project) return;
    setImportingNovel(true);
    setError("");
    setNotice("");
    try {
      const imported = await parseNovelFile(file);
      const preview = createChapterImportPreview(
        imported.chapters,
        chapters.map((item) => ({ title: item.title, source: item.source })),
      );
      setChapterImport({ fileName: file.name, imported, preview, conflict: "skip" });
    } catch (reason) {
      setError(reason instanceof Error ? reason.message : "Không thể phân tích tệp chương mới.");
    } finally {
      setImportingNovel(false);
      if (chapterImportRef.current) chapterImportRef.current.value = "";
    }
  }

  async function confirmChapterImport() {
    if (!project || !chapterImport) return;
    const { imported, preview, conflict } = chapterImport;
    const selected = preview.chapters.filter((item) => item.selected && item.sourceIndex >= preview.sourceFrom && item.sourceIndex <= preview.sourceTo);
    if (!selected.length) {
      setError("Hãy chọn ít nhất một chương để nhập.");
      return;
    }
    const stamp = now();
    const next = [...chapters];
    const changed: Chapter[] = [];
    let importedCount = 0;
    let skipped = 0;
    let overwritten = 0;
    for (const source of selected) {
      const targetIndex = preview.targetStart + source.sourceIndex - preview.sourceFrom;
      const existing = next[targetIndex];
      if (existing && conflict === "skip") {
        skipped += 1;
        continue;
      }
      if (existing) {
        const updated = { ...existing, title: source.title, source: source.source, updatedAt: stamp };
        next[targetIndex] = updated;
        changed.push(updated);
        overwritten += 1;
      } else {
        const item: Chapter = { id: crypto.randomUUID(), projectId: project.id, title: source.title, source: source.source, translation: "", order: targetIndex + 1, updatedAt: stamp };
        next.push(item);
        changed.push(item);
        importedCount += 1;
      }
    }
    next.sort((left, right) => left.order - right.order).forEach((item, index) => { item.order = index + 1; });
    const referencedAssets = new Set(selected.flatMap((item) => [...item.source.matchAll(/asset:\/\/([\w-]+)/g)].map((match) => match[1])));
    const importedAssets: ProjectAsset[] = imported.assets.filter((asset) => referencedAssets.has(asset.id)).map((asset) => ({ ...asset, projectId: project.id }));
    await db.transaction("rw", db.projects, db.chapters, db.assets, async () => {
      if (changed.length) await db.chapters.bulkPut(changed);
      await Promise.all(next.map((item) => db.chapters.update(item.id, { order: item.order })));
      if (importedAssets.length) await db.assets.bulkPut(importedAssets);
      await db.projects.update(project.id, { updatedAt: stamp });
    });
    setChapters(next);
    setAssets((items) => [...items.filter((item) => !referencedAssets.has(item.id)), ...importedAssets]);
    if (changed[0]) setChapterId(changed[0].id);
    setChapterImport(null);
    setNotice(`Đã thêm ${importedCount} chương${overwritten ? `, cập nhật ${overwritten} chương` : ""}${skipped ? `, bỏ qua ${skipped} chương trùng` : ""}.`);
  }

  if (!ready) return <div className="boot-state">Đang mở studio cục bộ...</div>;

  return (
    <main className="app-shell">
      <aside className="sidebar">
        <div className="brand"><img src="/aiko-logo-256.png" alt="Aiko Novel Translator" /><div><strong>Novel Translator</strong><small>Web Client</small></div></div>
        <label className="field-label" htmlFor="project-select">Dự án</label>
        <div className="select-wrap">
          <select id="project-select" value={projectId} onChange={(event) => setProjectId(event.target.value)}>
            {!projects.length && <option value="">Chưa có dự án</option>}
            {projects.map((item) => <option value={item.id} key={item.id}>{item.name}</option>)}
          </select>
          <CaretDown size={15} weight="bold" />
        </div>
        <button className="button secondary full" onClick={() => void createProject()}><Plus size={17} />Dự án mới</button>
        <button className="button secondary full" disabled={importingNovel} onClick={() => novelImportRef.current?.click()}><FilePlus size={17} />{importingNovel ? "Đang nhập..." : "Nhập EPUB / TXT"}</button>
        <input ref={novelImportRef} hidden type="file" accept=".epub,.txt,application/epub+zip,text/plain" onChange={(event) => void handleNovelImport(event.target.files?.[0])} />
        <input ref={chapterImportRef} hidden type="file" accept=".epub,.txt,application/epub+zip,text/plain" onChange={(event) => void handleChapterImport(event.target.files?.[0])} />

        <nav aria-label="Khu vực làm việc">
          {navItems.map((item) => {
            const Icon = item.icon;
            return <button className={view === item.id ? "nav-item active" : "nav-item"} key={item.id} onClick={() => setView(item.id)}><Icon size={19} />{item.label}</button>;
          })}
        </nav>

        <div className="sidebar-tools">
          <a className="desktop-app-link" href="https://github.com/akira3175/Aiko-App-Translator/releases" target="_blank" rel="noreferrer"><span><strong>Aiko App Translator</strong><small>Bản desktop có đầy đủ chức năng hơn</small></span><DownloadSimple size={18} /></a>
          <button className="tool-button" disabled={!project} onClick={() => void handleExport()}><DownloadSimple size={18} />Sao lưu</button>
          <button className="tool-button" onClick={() => backupImportRef.current?.click()}><UploadSimple size={18} />Khôi phục</button>
          <button className="tool-button delete-project" disabled={!project || !!busy} onClick={() => setDeleteModalOpen(true)}><Trash size={18} />Xóa truyện</button>
          <input ref={backupImportRef} hidden type="file" accept=".zip,application/zip" onChange={(event) => void handleImport(event.target.files?.[0])} />
        </div>
      </aside>

      <section className="workspace">
        <header className="topbar">
          <div className="topbar-project">
            {project ? <input className="project-title" aria-label="Tên dự án" value={project.name} onChange={(event) => void updateProject({ name: event.target.value })} /> : <h1>Studio dịch</h1>}
            <p>{project ? "Tự động lưu trên thiết bị này" : "Tạo dự án để bắt đầu"}</p>
            <select className="mobile-project-select" aria-label="Chọn dự án" value={projectId} onChange={(event) => setProjectId(event.target.value)}>{projects.map((item) => <option value={item.id} key={item.id}>{item.name}</option>)}</select>
          </div>
          {busy ? <button className="button danger" onClick={() => abortRef.current?.abort()}><Stop size={17} weight="fill" />Dừng tác vụ</button> : <div className="top-actions"><button className="mobile-delete-project" aria-label="Xóa truyện" disabled={!project} onClick={() => setDeleteModalOpen(true)}><Trash size={19} /></button><button className="button primary top-import" disabled={importingNovel} onClick={() => novelImportRef.current?.click()}><FilePlus size={17} />Nhập truyện</button></div>}
        </header>

        {(notice || error) && <div role="status" className={error ? "message error" : "message success"}>{error || notice}<button aria-label="Đóng thông báo" onClick={() => { setError(""); setNotice(""); }}>×</button></div>}

        {!project ? <EmptyProject onCreate={() => void createProject()} /> : view === "translate" ? (
          <TranslateView
            chapters={chapters}
            chapter={chapter}
            chapterId={chapterId}
            assets={assets}
            busy={busy}
            streamStatus={streamStatus}
            onSelect={setChapterId}
            onCreate={() => void createChapter()}
            onImport={() => chapterImportRef.current?.click()}
            onUpdate={(fields) => void updateChapter(fields)}
            onRun={(kind) => void runTask(kind)}
            onRunAll={() => void translateToEnd()}
            onManual={openManualTranslation}
          />
        ) : view === "characters" ? (
          <CharacterView value={project.characters} assets={assets} busy={busy === "characters"} analyzed={project.characterIndex || 0} total={chapters.length} batchSize={project.characterBatchSize || 10} onBatchSize={(characterBatchSize) => void updateProject({ characterBatchSize })} onChange={(characters) => void updateProject({ characters })} onRun={() => void analyzeCharacters()} />
        ) : view === "context" ? (
          <TerminologyView project={project} busy={busy === "context"} total={chapters.length} onProject={updateProject} onRun={() => void analyzeGlossary()} />
        ) : view === "pronouns" ? (
          <PronounView value={project.pronouns || ""} onChange={(pronouns) => void updateProject({ pronouns })} />
        ) : (
          <SettingsView project={project} settings={settings} apiKey={apiKey} onProject={updateProject} onSettings={setSettings} onApiKey={setApiKey} onSave={() => void saveSettings()} />
        )}
      </section>
      {deleteModalOpen && project && <div className="modal-backdrop" role="presentation" onMouseDown={(event) => { if (event.target === event.currentTarget) setDeleteModalOpen(false); }}><section className="confirm-modal" role="dialog" aria-modal="true" aria-labelledby="delete-project-title"><div className="confirm-icon"><Trash size={24} /></div><div><p className="eyebrow">XÓA TRUYỆN</p><h2 id="delete-project-title">Xóa “{project.name}”?</h2><p>Thao tác này sẽ xóa vĩnh viễn <strong>{chapters.length} chương</strong>, bản dịch, review, thuật ngữ, hồ sơ nhân vật, xưng hô và <strong>{assets.length} ảnh</strong> khỏi thiết bị này.</p></div><div className="confirm-warning">Không thể hoàn tác. Hãy sao lưu trước nếu bạn còn cần dữ liệu.</div><div className="confirm-actions"><button className="button outline" autoFocus onClick={() => setDeleteModalOpen(false)}>Hủy</button><button className="button destructive" onClick={() => void confirmDeleteProject()}><Trash size={17} />Xóa vĩnh viễn</button></div></section></div>}
      {chapterImport && <ChapterImportModal value={chapterImport} onChange={setChapterImport} onCancel={() => setChapterImport(null)} onConfirm={() => void confirmChapterImport()} />}
      {manualTranslation && <ManualTranslationModal value={manualTranslation} onChange={setManualTranslation} onCancel={() => setManualTranslation(null)} onConfirm={() => void applyManualTranslation()} />}
    </main>
  );
}

function ManualTranslationModal({ value, onChange, onCancel, onConfirm }: { value: ManualTranslationDraft; onChange: (value: ManualTranslationDraft) => void; onCancel: () => void; onConfirm: () => void }) {
  const [copied, setCopied] = useState(false);
  const copyPrompt = async () => {
    await navigator.clipboard.writeText(value.prompt);
    setCopied(true);
    window.setTimeout(() => setCopied(false), 1500);
  };
  return <div className="modal-backdrop" role="presentation" onMouseDown={(event) => { if (event.target === event.currentTarget) onCancel(); }}><section className="manual-translation-modal" role="dialog" aria-modal="true" aria-labelledby="manual-translation-title"><div className="chapter-import-heading"><div><p className="eyebrow">DỊCH THỦ CÔNG</p><h2 id="manual-translation-title">Đưa prompt sang AI bên ngoài</h2><p>Sao chép prompt đầy đủ, sau đó dán nguyên kết quả có các marker TITLE và CONTENT.</p></div><button className="modal-close" aria-label="Đóng" onClick={onCancel}>×</button></div><div className="manual-translation-steps"><label><span>Bước 1 · Prompt đầy đủ</span><textarea readOnly spellCheck={false} value={value.prompt} /></label><button className="button outline manual-copy-prompt" onClick={() => void copyPrompt()}><ClipboardText size={17} />{copied ? "Đã sao chép" : "Sao chép prompt"}</button><label><span>Bước 2 · Dán toàn bộ kết quả AI</span><textarea autoFocus spellCheck={false} placeholder={"###TITLE###\nTiêu đề đã dịch\n\n###CONTENT###\nNội dung đã dịch\n\n###END###"} value={value.result} onChange={(event) => onChange({ ...value, result: event.target.value })} /></label></div><div className="modal-actions"><button className="button outline" onClick={onCancel}>Hủy</button><button className="button primary" disabled={!value.result.trim()} onClick={onConfirm}>Lưu bản dịch</button></div></section></div>;
}

function EmptyProject({ onCreate }: { onCreate: () => void }) {
  return <div className="empty-state"><div className="empty-icon"><BookOpenText size={30} /></div><h2>Chưa có dự án</h2><p>Tạo một dự án để lưu chương, hồ sơ nhân vật và Context V1 ngay trong trình duyệt.</p><button className="button primary" onClick={onCreate}><Plus size={18} />Tạo dự án đầu tiên</button></div>;
}

function ChapterImportModal({ value, onChange, onCancel, onConfirm }: { value: PendingChapterImport; onChange: (value: PendingChapterImport) => void; onCancel: () => void; onConfirm: () => void }) {
  const { preview } = value;
  const updatePreview = (fields: Partial<ChapterImportPreview>) => onChange({ ...value, preview: { ...preview, ...fields } });
  const updateRange = (field: "sourceFrom" | "sourceTo" | "targetStart", displayValue: number) => {
    const nextValue = Math.max(0, Math.trunc(displayValue) - 1);
    if (field === "targetStart") return updatePreview({ targetStart: nextValue });
    const nextPreview = { ...preview, [field]: nextValue };
    nextPreview.chapters = preview.chapters.map((chapter) => ({
      ...chapter,
      selected: chapter.sourceIndex >= nextPreview.sourceFrom && chapter.sourceIndex <= nextPreview.sourceTo,
    }));
    onChange({ ...value, preview: nextPreview });
  };
  const selectedCount = preview.chapters.filter((chapter) => chapter.selected && chapter.sourceIndex >= preview.sourceFrom && chapter.sourceIndex <= preview.sourceTo).length;
  return <div className="modal-backdrop" role="presentation" onMouseDown={(event) => { if (event.target === event.currentTarget) onCancel(); }}><section className="chapter-import-modal" role="dialog" aria-modal="true" aria-labelledby="chapter-import-title"><div className="chapter-import-heading"><div><p className="eyebrow">THÊM VÀO TRUYỆN ĐANG MỞ</p><h2 id="chapter-import-title">Thêm chương từ EPUB/TXT</h2><p>{value.fileName} · App dùng chương trùng làm điểm neo để đề xuất phần mới.</p></div><button className="modal-close" aria-label="Đóng" onClick={onCancel}>×</button></div><div className={preview.noNew ? "import-suggestion empty" : "import-suggestion"}>{preview.noNew ? <><strong>Chưa thấy chương mới rõ ràng</strong><span>Đã tìm thấy {preview.anchors} điểm neo. Bạn có thể sửa range và chọn chương thủ công.</span></> : <><strong>Đề xuất · độ tin cậy {preview.confidence === "high" ? "cao" : preview.confidence === "medium" ? "trung bình" : "thủ công"}</strong><span>{preview.anchors} chương trùng dùng làm điểm neo · nhập từ chương nguồn {preview.sourceFrom + 1} vào vị trí {preview.targetStart + 1}.</span></>}</div><div className="import-mapping-fields"><label><span>Chương nguồn từ</span><input type="number" min={1} max={preview.chapters.length} value={preview.sourceFrom + 1} onChange={(event) => updateRange("sourceFrom", Number(event.target.value))} /></label><label><span>Đến</span><input type="number" min={1} max={preview.chapters.length} value={preview.sourceTo + 1} onChange={(event) => updateRange("sourceTo", Number(event.target.value))} /></label><label><span>Lưu bắt đầu ở vị trí</span><input type="number" min={1} value={preview.targetStart + 1} onChange={(event) => updateRange("targetStart", Number(event.target.value))} /></label><label><span>Chương trùng</span><select value={value.conflict} onChange={(event) => onChange({ ...value, conflict: event.target.value as PendingChapterImport["conflict"] })}><option value="skip">Bỏ qua (an toàn)</option><option value="overwrite">Cập nhật raw</option></select></label></div><div className="chapter-import-table-wrap"><table className="chapter-import-table"><thead><tr><th>Thêm</th><th>Chương nguồn</th><th>Vị trí đích</th><th>Điểm neo</th></tr></thead><tbody>{preview.chapters.map((item) => <tr key={item.sourceIndex}><td><input type="checkbox" checked={item.selected} onChange={(event) => updatePreview({ chapters: preview.chapters.map((chapter) => chapter.sourceIndex === item.sourceIndex ? { ...chapter, selected: event.target.checked } : chapter) })} /></td><td><strong>{item.sourceIndex + 1}. {item.title}</strong></td><td>{preview.targetStart + item.sourceIndex - preview.sourceFrom + 1}</td><td>{item.matchIndex === null ? "—" : `Chương ${item.matchIndex + 1} · ${Math.round(item.matchScore * 100)}%`}</td></tr>)}</tbody></table></div><div className="modal-actions"><span>{selectedCount} chương được chọn</span><button className="button outline" onClick={onCancel}>Hủy</button><button className="button primary" disabled={!selectedCount} onClick={onConfirm}>Nhập các chương đã chọn</button></div></section></div>;
}

function TranslateView({ chapters, chapter, chapterId, assets, busy, streamStatus, onSelect, onCreate, onImport, onUpdate, onRun, onRunAll, onManual }: {
  chapters: Chapter[]; chapter?: Chapter; chapterId: string; assets: ProjectAsset[]; busy: AiTaskKind | "translate-all" | "characters" | "context" | null;
  streamStatus: { chapterId: string; stage: "translate" | "polish"; line: number | null } | null;
  onSelect: (id: string) => void; onCreate: () => void; onImport: () => void; onUpdate: (fields: Partial<Chapter>) => void; onRun: (kind: AiTaskKind) => void; onRunAll: () => void; onManual: () => void;
}) {
  const [sourcePreview, setSourcePreview] = useState(false);
  const [targetPreview, setTargetPreview] = useState(false);
  const [mobilePane, setMobilePane] = useState<"source" | "target" | "review">("target");
  const [reviewModalOpen, setReviewModalOpen] = useState(false);
  const [previewCopied, setPreviewCopied] = useState(false);
  const sourceEditorRef = useRef<MarkdownEditorHandle>(null);
  const targetEditorRef = useRef<MarkdownEditorHandle>(null);
  const chapterIndex = chapters.findIndex((item) => item.id === chapterId);
  const editorStreaming = streamStatus?.chapterId === chapterId;
  useEffect(() => {
    if (!editorStreaming) return;
    setTargetPreview(false);
    setMobilePane("target");
  }, [editorStreaming]);
  const editPreviewLine = (kind: "source" | "target", line: number) => {
    if (kind === "source") setSourcePreview(false);
    else setTargetPreview(false);
    setMobilePane(kind);
    requestAnimationFrame(() => requestAnimationFrame(() => (kind === "source" ? sourceEditorRef : targetEditorRef).current?.focusLine(line)));
  };
  const openEditorFind = (kind: "source" | "target") => {
    if (kind === "source") setSourcePreview(false);
    else setTargetPreview(false);
    setMobilePane(kind);
    requestAnimationFrame(() => requestAnimationFrame(() => (kind === "source" ? sourceEditorRef : targetEditorRef).current?.openFind()));
  };
  const formatTarget = (marker: "*" | "**") => {
    targetEditorRef.current?.wrapSelection(marker);
  };
  const copyTargetPreview = async () => {
    if (!chapter) return;
    const plain = markdownToPlainText(chapter.translation);
    const html = markdownToClipboardHtml(chapter.translation);
    if (typeof ClipboardItem !== "undefined" && navigator.clipboard.write) {
      await navigator.clipboard.write([new ClipboardItem({ "text/plain": new Blob([plain], { type: "text/plain" }), "text/html": new Blob([html], { type: "text/html" }) })]);
    } else await navigator.clipboard.writeText(plain);
    setPreviewCopied(true);
    window.setTimeout(() => setPreviewCopied(false), 1500);
  };
  return <div className="translate-layout">
    <div className="editor-workspace">
      {chapter ? <>
        <div className="workspace-toolbar">
          <button className="button outline chapter-nav" disabled={!!busy || chapterIndex <= 0} onClick={() => onSelect(chapters[chapterIndex - 1]?.id)}>← <span>Chương trước</span></button>
          <label className="chapter-picker"><small>ĐANG CHỈNH SỬA</small><select disabled={!!busy} value={chapterId} onChange={(event) => onSelect(event.target.value)}>{chapters.map((item) => <option value={item.id} key={item.id}>{chapterDisplayTitle(item)}</option>)}</select><CaretDown size={15} weight="bold" /></label>
          <button className="button outline chapter-nav" disabled={!!busy || chapterIndex < 0 || chapterIndex >= chapters.length - 1} onClick={() => onSelect(chapters[chapterIndex + 1]?.id)}><span>Chương tiếp</span> →</button>
          <button className="icon-add" disabled={!!busy} aria-label="Thêm chương" title="Thêm chương trống" onClick={onCreate}><FilePlus size={18} /></button>
          <button className="icon-add" disabled={!!busy} aria-label="Thêm chương từ EPUB hoặc TXT" title="Thêm chương từ EPUB / TXT bằng điểm neo" onClick={onImport}><UploadSimple size={18} /></button>
          <div className="chapter-actions">
            <button className="button primary" disabled={!!busy || !chapter.source.trim()} onClick={() => onRun("translate")}><Sparkle size={17} weight="fill" />{busy === "translate" ? "Đang dịch..." : "Dịch"}</button>
            <button className="button outline run-all" disabled={!!busy || !chapter.source.trim()} onClick={onRunAll}>{busy === "translate-all" ? "Đang chạy..." : "Dịch đến hết"}</button>
            <button className="button outline manual-translate-button" disabled={!!busy || !chapter.source.trim()} onClick={onManual}>Dịch thủ công</button>
            <button className="button outline" disabled={!!busy || !chapter.translation.trim()} onClick={() => onRun("polish")}>{busy === "polish" ? "Đang hiệu đính..." : "Hiệu đính"}</button>
            <button className="button outline toolbar-review-button" disabled={!!busy || !chapter.translation.trim()} onClick={() => onRun("review")}>{busy === "review" ? "Đang review..." : "Review"}</button>
          </div>
        </div>
        <div className="chapter-title-row"><input className="chapter-title-input" disabled={!!busy} aria-label="Tiêu đề dịch" value={chapterDisplayTitle(chapter)} onChange={(event) => onUpdate({ translatedTitle: event.target.value })} /><button className="desktop-review-trigger" disabled={!!busy} onClick={() => setReviewModalOpen(true)}><ClipboardText size={16} />Xem review</button></div>
        <div className="mobile-editor-switch segmented" role="group" aria-label="Nội dung đang hiển thị"><button className={mobilePane === "source" ? "active" : ""} onClick={() => setMobilePane("source")}>Bản gốc</button><button className={mobilePane === "target" ? "active" : ""} onClick={() => setMobilePane("target")}>Bản dịch</button><button className={mobilePane === "review" ? "active" : ""} onClick={() => setMobilePane("review")}>Review</button></div>
        <div className="editor-grid">
          <section className={mobilePane === "source" ? "mobile-pane-active" : ""}><div className="pane-label"><strong>BẢN GỐC</strong><div><span>{chapter.source.length.toLocaleString("vi-VN")} ký tự</span><button type="button" onClick={() => openEditorFind("source")}><MagnifyingGlass size={14} />Tìm</button><button className={sourcePreview ? "active" : ""} type="button" onClick={() => setSourcePreview((value) => !value)}>{sourcePreview ? <Eye size={15} /> : <PencilSimple size={15} />}{sourcePreview ? "Bản đọc" : "Markdown"}</button></div></div>{sourcePreview ? <MarkdownPreview editorStyle label="Xem trước chương nguồn" value={chapter.source} assets={assets} onEditLine={(line) => editPreviewLine("source", line)} /> : <MarkdownEditor ref={sourceEditorRef} readOnly label="Nội dung chương nguồn" value={chapter.source} onChange={() => undefined} />}</section>
          <section className={mobilePane === "target" ? "mobile-pane-active" : ""}><div className="pane-label"><strong className="editable-pane-title">BẢN DỊCH TIẾNG VIỆT<small>{editorStreaming ? streamStatus.stage === "translate" ? "AI ĐANG DỊCH · CHỈ ĐỌC" : "AI ĐANG HIỆU ĐÍNH · CHỈ ĐỌC" : "SOẠN THẢO · TỰ ĐỘNG LƯU"}</small></strong><div><span>{chapter.translation.length.toLocaleString("vi-VN")} ký tự</span><button disabled={!!busy} className="format-button" type="button" title="In đậm (Ctrl+B)" onClick={() => formatTarget("**")}><strong>B</strong></button><button disabled={!!busy} className="format-button italic" type="button" title="In nghiêng (Ctrl+I)" onClick={() => formatTarget("*")}>I</button><button disabled={!!busy} type="button" onClick={() => openEditorFind("target")}><MagnifyingGlass size={14} />Tìm</button><button disabled={!!busy || !chapter.translation.trim()} type="button" title="Sao chép nội dung đã render" onClick={() => void copyTargetPreview()}><ClipboardText size={14} />{previewCopied ? "Đã chép" : "Sao chép"}</button><button disabled={!!busy} className={targetPreview ? "active" : ""} type="button" onClick={() => setTargetPreview((value) => !value)}>{targetPreview ? <Eye size={15} /> : <PencilSimple size={15} />}{targetPreview ? "Xem trước" : "Soạn thảo"}</button></div></div>{targetPreview ? <MarkdownPreview editorStyle label="Xem trước bản dịch" value={chapter.translation} assets={assets} onEditLine={(line) => editPreviewLine("target", line)} /> : <MarkdownEditor ref={targetEditorRef} streaming={editorStreaming} activeLine={streamStatus?.line} label="Nội dung bản dịch có thể chỉnh sửa" value={chapter.translation} onChange={(translation) => onUpdate({ translation })} />}</section>
          <section className={`review-pane ${mobilePane === "review" ? "mobile-pane-active" : ""}`}><div className="pane-label"><strong>REVIEW CHƯƠNG</strong><span>{chapter.review?.trim() ? "Đã có nhận xét" : "Chưa review"}</span></div><ReviewDetail chapter={chapter} /></section>
        </div>
        {reviewModalOpen && <div className="modal-backdrop review-modal-backdrop" role="presentation" onMouseDown={(event) => { if (event.target === event.currentTarget) setReviewModalOpen(false); }}><section className="review-modal" role="dialog" aria-modal="true" aria-labelledby="review-modal-title"><div className="review-modal-heading"><div><p className="eyebrow">REVIEW CHƯƠNG HIỆN TẠI</p><h2 id="review-modal-title">{chapterDisplayTitle(chapter)}</h2><p>Đối chiếu bản gốc và bản dịch theo review của app local.</p></div><div><button className="button primary" disabled={!!busy || !chapter.translation.trim()} onClick={() => onRun("review")}><Sparkle size={16} />{busy === "review" ? "Đang review..." : chapter.review?.trim() ? "Review lại" : "Chạy review"}</button><button className="modal-close" aria-label="Đóng review" onClick={() => setReviewModalOpen(false)}>×</button></div></div><div className="review-modal-editor"><ReviewDetail chapter={chapter} /></div></section></div>}
      </> : <div className="empty-state compact"><FilePlus size={30} /><h2>Thêm chương đầu tiên</h2><button className="button primary" onClick={onCreate}><Plus size={18} />Thêm chương</button></div>}
    </div>
  </div>;
}

function ReviewDetail({ chapter }: { chapter: Chapter }) {
  const data = chapter.localReviewData || {};
  const issues = Array.isArray(data.issues) ? data.issues.filter((item): item is Record<string, unknown> => !!item && typeof item === "object") : [];
  const score = data.score ?? "—";
  const summary = String(data.summary || chapter.review || "");
  if (!summary && !issues.length) return <div className="empty-review"><strong>Chưa có review</strong><span>Bấm Chạy review để đối chiếu chương hiện tại.</span></div>;
  return <div className="review-detail"><div className="review-detail-head"><div className="review-metrics"><span className="metric">Điểm <strong>{String(score)}/10</strong></span><span className="metric"><strong>{issues.length}</strong> lỗi</span><span className="metric">Giới tính <strong>{data.gender_ok === false ? "Cần kiểm tra" : "Đạt"}</strong></span><span className="metric">Xưng hô <strong>{data.address_ok === false ? "Cần kiểm tra" : "Đạt"}</strong></span></div></div><p className="review-copy">{summary || "Không có tóm tắt."}</p><div className="issues">{issues.length ? issues.map((issue, index) => <section className="issue" key={index}><div className="issue-top"><span className="issue-type">Lỗi {index + 1} · {String(issue.type || "khác")}</span><span>{String(issue.severity || "")}</span></div><dl><div><dt>NGUYÊN VĂN</dt><dd>{String(issue.original_kr || "—")}</dd></div><div><dt>BẢN DỊCH</dt><dd>{String(issue.original_vi || "—")}</dd></div><div><dt>ĐỀ XUẤT</dt><dd className="suggestion">{String(issue.suggestion || "—")}</dd></div></dl></section>) : <div className="empty-review compact"><strong>Không phát hiện lỗi</strong><span>Chương này đã đạt yêu cầu.</span></div>}</div></div>;
}

function CharacterView({ value, assets, busy, analyzed, total, batchSize, onBatchSize, onChange, onRun }: { value: string; assets: ProjectAsset[]; busy: boolean; analyzed: number; total: number; batchSize: number; onBatchSize: (value: number) => void; onChange: (value: string) => void; onRun: () => void }) {
  const [preview, setPreview] = useState(false);
  const [draft, setDraft] = useState(value);
  const saveTimer = useRef<number | null>(null);
  useEffect(() => setDraft(value), [value]);
  useEffect(() => () => { if (saveTimer.current !== null) window.clearTimeout(saveTimer.current); }, []);
  const saveDraft = (next: string) => {
    setDraft(next);
    if (saveTimer.current !== null) window.clearTimeout(saveTimer.current);
    saveTimer.current = window.setTimeout(() => { onChange(next); saveTimer.current = null; }, 300);
  };
  const flushDraft = () => {
    if (saveTimer.current !== null) window.clearTimeout(saveTimer.current);
    saveTimer.current = null;
    if (draft !== value) onChange(draft);
  };
  return <div className="memory-view"><div className="section-intro"><div><p className="eyebrow">BỘ NHỚ NHÂN VẬT</p><h2>Hồ sơ nhân vật</h2><p>{Math.min(analyzed, total)}/{total} chương đã phân tích. Batch hiện tại: {batchSize} chương.</p></div><div className="head-actions"><BatchSizeField value={batchSize} busy={busy} onChange={onBatchSize} /><button className="button outline" disabled={busy || !total} onClick={onRun}><Sparkle size={17} />{busy ? "Đang phân tích..." : analyzed >= total && total ? "Phân tích lại toàn bộ" : "Phân tích tiếp"}</button></div></div><div className="memory-toolbar"><div className="segmented"><button className={!preview ? "active" : ""} onClick={() => setPreview(false)}>Soạn thảo</button><button className={preview ? "active" : ""} onClick={() => { flushDraft(); setPreview(true); }}>Preview Markdown</button></div><span>Tự động lưu</span></div><div className="memory-editor-shell">{preview ? <MarkdownPreview label="Preview hồ sơ nhân vật" value={draft} assets={assets} /> : <textarea className="character-plain-editor" aria-label="Hồ sơ nhân vật" value={draft} onChange={(event) => saveDraft(event.target.value)} onBlur={flushDraft} spellCheck={false} />}</div></div>;
}

function BatchSizeField({ value, busy, onChange }: { value: number; busy: boolean; onChange: (value: number) => void }) {
  return <label className="batch-size-field"><span>Số chương mỗi batch</span><input type="number" min={1} max={100} step={1} value={value} disabled={busy} onChange={(event) => { const next = Number(event.target.value); if (Number.isInteger(next) && next >= 1 && next <= 100) onChange(next); }} /></label>;
}

function TerminologyView({ project, busy, total, onProject, onRun }: { project: Project; busy: boolean; total: number; onProject: (fields: Partial<Project>) => void; onRun: () => void }) {
  const [query, setQuery] = useState("");
  const glossary = project.glossary || [];
  const visible = glossary.filter((item) => `${item.source} ${item.target}`.toLocaleLowerCase("vi").includes(query.toLocaleLowerCase("vi")));
  const updateEntry = (id: string, fields: Partial<(typeof glossary)[number]>) => onProject({ glossary: glossary.map((item) => item.id === id ? { ...item, ...fields } : item) });
  return <div className="memory-view terminology-view"><div className="section-intro"><div><p className="eyebrow">BỘ NHỚ DỰ ÁN</p><h2>Thuật ngữ & phong cách</h2><p>{glossary.length} thuật ngữ · {Math.min(project.glossaryIndex || 0, total)}/{total} chương đã quét · Batch {project.glossaryBatchSize || 30} chương.</p></div><div className="head-actions"><label className="search-box"><MagnifyingGlass size={17} /><input value={query} onChange={(event) => setQuery(event.target.value)} placeholder="Tìm nguyên văn hoặc bản dịch" /></label><BatchSizeField value={project.glossaryBatchSize || 30} busy={busy} onChange={(glossaryBatchSize) => onProject({ glossaryBatchSize })} /><button className="button outline" onClick={() => onProject({ glossary: [...glossary, { id: crypto.randomUUID(), source: "", target: "" }] })}><Plus size={17} />Thêm</button><button className="button primary" disabled={busy || !total} onClick={onRun}><Sparkle size={17} />{busy ? "Đang cập nhật..." : (project.glossaryIndex || 0) >= total && total ? "Quét lại toàn bộ" : "Tạo glossary"}</button></div></div><div className="terminology-grid"><section className="memory-card"><div className="memory-card-head"><div><small>GLOSSARY</small><strong>{visible.length} thuật ngữ</strong></div><span>Đã đồng bộ</span></div><div className="glossary-list">{visible.length ? visible.map((item) => <div className="glossary-row" key={item.id}><textarea rows={1} aria-label="Nguyên văn" value={item.source} onChange={(event) => updateEntry(item.id, { source: event.target.value })} placeholder="Nguyên văn" spellCheck={false} /><i>→</i><textarea rows={1} aria-label="Bản dịch" value={item.target} onChange={(event) => updateEntry(item.id, { target: event.target.value })} placeholder="Bản dịch" spellCheck={false} /><button aria-label="Xóa thuật ngữ" onClick={() => onProject({ glossary: glossary.filter((entry) => entry.id !== item.id) })}><Trash size={16} /></button></div>) : <div className="memory-empty">Chưa có thuật ngữ phù hợp.</div>}</div></section><section className="memory-card context-card"><div className="memory-card-head"><div><small>STYLE NOTE</small><strong>Quy tắc biên tập</strong></div><span>Tự động lưu</span></div><textarea value={project.styleNotes || ""} onChange={(event) => onProject({ styleNotes: event.target.value })} placeholder="Ví dụ: Giữ giọng kể tự nhiên; dùng dấu ngoặc kép cho hội thoại; không Việt hóa tên riêng..." spellCheck={false} /></section></div></div>;
}

type PronounEntry = { speaker?: string; listener?: string; speaker_self?: string; speaker_to_listener?: string; relationship_status?: string; emotional_tone?: string; chapter_number?: number; [key: string]: unknown };
type PronounPair = { characters?: string[]; timeline?: PronounEntry[]; locked?: boolean; [key: string]: unknown };
type PronounDraft = { speaker: string; listener: string; speakerSelf: string; speakerToListener: string; relationship: string; tone: string; locked: boolean };

function parsePronounMemory(value: string) {
  try {
    const data = parse(value);
    return data && typeof data === "object" && !Array.isArray(data) ? data as Record<string, PronounPair> : {};
  } catch { return {}; }
}

function latestPronounEntry(pair?: PronounPair) {
  const timeline = Array.isArray(pair?.timeline) ? pair.timeline : [];
  return timeline.reduce<{ entry: PronounEntry; index: number } | null>((latest, entry, index) => !latest || Number(entry.chapter_number || 0) >= Number(latest.entry.chapter_number || 0) ? { entry, index } : latest, null);
}

function PronounView({ value, onChange }: { value: string; onChange: (value: string) => void }) {
  const [query, setQuery] = useState("");
  useEffect(() => {
    const textarea = document.querySelector<HTMLTextAreaElement>(".raw-memory textarea");
    if (textarea) textarea.readOnly = true;
  });
  const data = parsePronounMemory(value);
  const pairs = Object.entries(data).flatMap(([key, pair]) => {
    const latest = latestPronounEntry(pair);
    return latest ? [{ key, pair, latest }] : [];
  });
  const [selected, setSelected] = useState(pairs[0]?.key || "");
  const current = pairs.find((item) => item.key === selected) || pairs[0];
  const [draft, setDraft] = useState<PronounDraft>({ speaker: "", listener: "", speakerSelf: "", speakerToListener: "", relationship: "", tone: "", locked: false });
  useEffect(() => {
    if (!current) return;
    const entry = current.latest.entry;
    setDraft({ speaker: String(entry.speaker || current.pair.characters?.[0] || ""), listener: String(entry.listener || current.pair.characters?.[1] || ""), speakerSelf: String(entry.speaker_self || ""), speakerToListener: String(entry.speaker_to_listener || ""), relationship: String(entry.relationship_status || ""), tone: String(entry.emotional_tone || ""), locked: Boolean(current.pair.locked) });
  }, [current?.key, value]);
  const visible = pairs.filter((item) => `${item.key} ${item.latest.entry.speaker || ""} ${item.latest.entry.listener || ""} ${item.latest.entry.speaker_self || ""} ${item.latest.entry.speaker_to_listener || ""}`.toLocaleLowerCase("vi").includes(query.toLocaleLowerCase("vi")));
  const save = () => {
    if (!current || !draft.speakerSelf.trim() || !draft.speakerToListener.trim()) return;
    const next = structuredClone(data);
    const pair = next[current.key];
    const timeline = Array.isArray(pair.timeline) ? pair.timeline : [];
    timeline[current.latest.index] = { ...timeline[current.latest.index], speaker_self: draft.speakerSelf.trim(), speaker_to_listener: draft.speakerToListener.trim(), relationship_status: draft.relationship.trim(), emotional_tone: draft.tone.trim(), source: "manual" };
    pair.timeline = timeline;
    pair.locked = draft.locked;
    onChange(stringify(next, { lineWidth: 0 }));
  };
  const remove = () => {
    if (!current || !window.confirm(`Xóa cặp xưng hô ${draft.speaker} → ${draft.listener}?`)) return;
    const next = structuredClone(data);
    delete next[current.key];
    onChange(stringify(next, { lineWidth: 0 }));
    setSelected("");
  };
  return <div className="memory-view"><div className="section-intro"><div><p className="eyebrow">BỘ NHỚ XƯNG HÔ</p><h2>Xưng hô nhân vật</h2><p>{pairs.length} cặp xưng hô · {pairs.filter((item) => item.pair.locked).length} đã khóa.</p></div><div className="head-actions"><label className="search-box"><MagnifyingGlass size={17} /><input value={query} onChange={(event) => setQuery(event.target.value)} placeholder="Tìm nhân vật hoặc cách gọi" /></label></div></div><div className="pronoun-layout"><section className="pronoun-list-panel"><div className="pronoun-list-head"><strong>Danh sách xưng hô</strong><span>{visible.length}/{pairs.length}</span></div><div className="pronoun-list">{visible.length ? visible.map((item) => { const entry = item.latest.entry; const label = entry.speaker && entry.listener ? `${entry.speaker} → ${entry.listener}` : item.pair.characters?.join(" ↔ ") || item.key; return <button className={item.key === current?.key ? "pronoun-row active" : "pronoun-row"} key={item.key} onClick={() => setSelected(item.key)}><strong>{label}</strong><small>{entry.speaker_self || "?"} / {entry.speaker_to_listener || "?"} · Chương {entry.chapter_number || "—"}{item.pair.locked ? " · Đã khóa" : ""}</small></button>; }) : <div className="memory-empty">Chưa có cặp xưng hô phù hợp.</div>}</div></section><section className="pronoun-detail">{current ? <><div className="pronoun-detail-head pronoun-edit-head"><div><p className="eyebrow">QUY TẮC XƯNG HÔ</p><h3>{draft.speaker} → {draft.listener}</h3><p>Chỉnh bản ghi gần nhất và khóa nếu đã được bạn xác nhận.</p></div><button className="button outline pronoun-delete" onClick={remove}><Trash size={16} />Xóa cặp</button></div><div className="pronoun-form"><label><span>Người nói</span><input value={draft.speaker} readOnly /></label><label><span>Người nghe</span><input value={draft.listener} readOnly /></label><label><span>Tự xưng</span><input value={draft.speakerSelf} onChange={(event) => setDraft({ ...draft, speakerSelf: event.target.value })} placeholder="tôi, anh, em..." /></label><label><span>Gọi đối phương</span><input value={draft.speakerToListener} onChange={(event) => setDraft({ ...draft, speakerToListener: event.target.value })} placeholder="cậu, cô, ngài..." /></label><label className="pronoun-form-wide"><span>Trạng thái quan hệ</span><input value={draft.relationship} onChange={(event) => setDraft({ ...draft, relationship: event.target.value })} placeholder="Bạn bè, xa cách, thân thiết..." /></label><label className="pronoun-form-wide"><span>Giọng điệu</span><input value={draft.tone} onChange={(event) => setDraft({ ...draft, tone: event.target.value })} placeholder="Ấm áp, lạnh lùng, kính trọng..." /></label><label className="pronoun-lock-field"><input type="checkbox" checked={draft.locked} onChange={(event) => setDraft({ ...draft, locked: event.target.checked })} /><span><strong>Khóa quy tắc</strong><small>Pipeline dịch phải ưu tiên quy tắc bạn đã xác nhận.</small></span></label><div className="pronoun-form-actions"><button className="button primary" disabled={!draft.speakerSelf.trim() || !draft.speakerToListener.trim()} onClick={save}>Lưu quy tắc</button></div></div></> : <div className="pronoun-empty"><strong>Chưa có dữ liệu xưng hô</strong><span>Dữ liệu sẽ được tạo tự động trong pipeline dịch.</span></div>}</section></div><details className="raw-memory"><summary>Chỉnh dữ liệu YAML thô</summary><textarea value={value} onChange={(event) => onChange(event.target.value)} spellCheck={false} /></details></div>;
}

function SettingsView({ project, settings, apiKey, onProject, onSettings, onApiKey, onSave }: { project: Project; settings: AppSettings; apiKey: string; onProject: (fields: Partial<Project>) => void; onSettings: (value: AppSettings) => void; onApiKey: (value: string) => void; onSave: () => void }) {
  const tasks = settings.tasks || DEFAULT_TASKS;
  const taskDefinitions: Array<{ id: AiTaskKind; label: string; description: string }> = [
    { id: "translate", label: "Dịch", description: "Tạo bản dịch mới từ chương nguồn." },
    { id: "polish", label: "Hiệu đính", description: "Chỉnh câu chữ trên bản dịch hiện tại." },
    { id: "pronouns", label: "Xuất xưng hô", description: "Phân tích và cập nhật bảng xưng hô dự án." },
    { id: "review", label: "Review", description: "Đánh giá bản dịch mà không sửa nội dung." },
  ];
  const updateTask = (id: AiTaskKind, fields: Partial<AiTaskSettings>) => {
    const nextTasks = { ...tasks, [id]: { ...tasks[id], ...fields } };
    onSettings({ ...settings, tasks: nextTasks });
  };
  return <div className="settings-view"><div className="settings-heading"><h2>Thiết lập</h2><p>Khóa API của bạn không được đưa vào bản sao dự án.</p></div><div className="settings-sections">
    <section className="settings-api"><h3><Key size={20} />Gemini API</h3><div className="form-grid"><label className="wide"><span>Danh sách API key</span><textarea className="api-key-editor" rows={5} autoComplete="off" value={apiKey} onChange={(event) => onApiKey(event.target.value)} placeholder={"AIza...\nAIza...\nMỗi key một dòng"} /><small>{parseApiKeys(apiKey).length} key hợp lệ. App tự luân phiên và chuyển key khi gặp lỗi quota hoặc rate-limit.</small></label><label className="check wide"><input type="checkbox" checked={settings.rememberApiKey} onChange={(event) => onSettings({ ...settings, rememberApiKey: event.target.checked })} /><span>Ghi nhớ danh sách API key trong IndexedDB trên thiết bị này</span></label></div></section>
    <section className="prompt-settings"><div className="prompt-settings-heading"><div><h3><Sparkle size={20} />Prompt dịch</h3><p>Vai trò và nhiệm vụ mặc định của app local. Dữ liệu chương được chèn tự động.</p></div><button className="button outline" onClick={() => onProject({ promptRole: DEFAULT_TRANSLATION_ROLE, promptTask: DEFAULT_TRANSLATION_TASK })}>Khôi phục mặc định</button></div><div className="form-grid prompt-editor-grid"><label><span>Vai trò</span><textarea rows={10} value={project.promptRole ?? DEFAULT_TRANSLATION_ROLE} onChange={(event) => onProject({ promptRole: event.target.value })} spellCheck={false} /></label><label><span>Nhiệm vụ</span><textarea rows={10} value={project.promptTask ?? DEFAULT_TRANSLATION_TASK} onChange={(event) => onProject({ promptTask: event.target.value })} spellCheck={false} /></label></div></section>
    <section className="prompt-settings"><div className="prompt-settings-heading"><div><h3><Sparkle size={20} />Prompt hiệu đính</h3><p>Chỉnh riêng cho pipeline hiệu đính của truyện hiện tại.</p></div><button className="button outline" onClick={() => onProject({ polishPromptRole: DEFAULT_POLISH_ROLE, polishPromptTask: DEFAULT_POLISH_TASK })}>Khôi phục mặc định</button></div><div className="form-grid prompt-editor-grid"><label><span>Vai trò</span><textarea rows={10} value={project.polishPromptRole ?? DEFAULT_POLISH_ROLE} onChange={(event) => onProject({ polishPromptRole: event.target.value })} spellCheck={false} /></label><label><span>Nhiệm vụ</span><textarea rows={10} value={project.polishPromptTask ?? DEFAULT_POLISH_TASK} onChange={(event) => onProject({ polishPromptTask: event.target.value })} spellCheck={false} /></label></div></section>
    {taskDefinitions.map((task) => { const value = tasks[task.id]; return <section className="task-settings" key={task.id}><div className="task-settings-heading"><div><h3><Sparkle size={20} />{task.label}</h3><p>{task.description}</p></div></div><div className="form-grid"><label><span>Model</span><input value={value.model} onChange={(event) => updateTask(task.id, { model: event.target.value })} /></label><label><span>Token đầu ra tối đa</span><input type="number" min="1000" step="1000" value={value.maxOutputTokens ?? ""} onChange={(event) => updateTask(task.id, { maxOutputTokens: event.target.value ? Number(event.target.value) : null })} placeholder="Mặc định của model" /><small>Để trống để Gemini tự chọn giới hạn.</small></label><label className="wide"><span>System prompt tùy chỉnh</span><textarea rows={5} value={value.systemInstruction} onChange={(event) => updateTask(task.id, { systemInstruction: event.target.value })} placeholder="Để trống để dùng system prompt mặc định của tác vụ." /><small>Khi có nội dung, prompt này sẽ thay thế system prompt mặc định.</small></label></div></section>; })}
    <section className="settings-language"><h3><Translate size={20} />Ngôn ngữ dự án</h3><div className="form-grid"><label><span>Ngôn ngữ nguồn</span><input value={project.sourceLanguage} onChange={(event) => onProject({ sourceLanguage: event.target.value })} /></label><label><span>Ngôn ngữ đích</span><input value={project.targetLanguage} onChange={(event) => onProject({ targetLanguage: event.target.value })} /></label></div></section>
  </div><button className="button primary save-settings" onClick={onSave}>Lưu thiết lập</button></div>;
}
