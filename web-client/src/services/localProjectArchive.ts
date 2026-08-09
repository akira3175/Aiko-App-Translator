import JSZip from "jszip";
import { parse, stringify } from "yaml";
import type { Chapter, Project, ProjectAsset } from "../types";

export interface LocalProjectArchive {
  project: Project;
  chapters: Chapter[];
  assets: ProjectAsset[];
}

const CHAPTER_FILE = /^v\d+_c\d+_s\d+\.md$/i;

function safeFolderName(value: string) {
  return value.replace(/[<>:"/\\|?*\u0000-\u001f]/g, "_").replace(/[ .]+$/g, "").trim() || "Truyện";
}

function chapterFileName(chapter: Chapter) {
  return chapter.localFileName && CHAPTER_FILE.test(chapter.localFileName)
    ? chapter.localFileName
    : `v1_c${Math.max(0, chapter.order - 1)}_s1.md`;
}

function chapterOrder(name: string) {
  const numbers = name.match(/\d+/g)?.map(Number) || [];
  return numbers.length ? numbers : [Number.MAX_SAFE_INTEGER];
}

function compareChapterNames(left: string, right: string) {
  const a = chapterOrder(left);
  const b = chapterOrder(right);
  for (let index = 0; index < Math.max(a.length, b.length); index += 1) {
    const difference = (a[index] ?? 0) - (b[index] ?? 0);
    if (difference) return difference;
  }
  return left.localeCompare(right, "vi");
}

function chapterTitle(text: string, fallback: string) {
  for (const line of text.split(/\r?\n/)) {
    const title = line.replace(/^\s*#{1,6}\s*/, "").trim();
    if (title) return title;
  }
  return fallback.replace(/\.md$/i, "");
}

function parseGlossary(value: unknown) {
  const lines = Array.isArray(value) ? value.map(String) : String(value || "").split(/\r?\n/);
  return lines.flatMap((line) => {
    const separator = line.indexOf("=");
    if (separator < 1) return [];
    const source = line.slice(0, separator).trim();
    const target = line.slice(separator + 1).trim();
    return source && target ? [{ id: crypto.randomUUID(), source, target }] : [];
  });
}

export function projectContextYaml(project: Project) {
  let context: Record<string, unknown> = {};
  try {
    const parsed = parse(project.contextV1);
    if (parsed && typeof parsed === "object" && !Array.isArray(parsed)) context = parsed as Record<string, unknown>;
  } catch { /* Rebuild invalid legacy context from structured fields. */ }
  context.index = project.glossaryIndex ?? context.index ?? 0;
  context.prompt_role = project.promptRole ?? context.prompt_role ?? "";
  context.prompt_task = project.promptTask ?? context.prompt_task ?? "";
  context.polish_prompt_role = project.polishPromptRole ?? context.polish_prompt_role ?? "";
  context.polish_prompt_task = project.polishPromptTask ?? context.polish_prompt_task ?? "";
  if (project.styleNotes?.trim()) context.style_notes = project.styleNotes.trim();
  if (project.glossary?.length) context.glossary = project.glossary.map((item) => `${item.source} = ${item.target}`).join("\n");
  return stringify(context, { lineWidth: 0 });
}

function localImageText(value: string, assets: ProjectAsset[]) {
  const names = new Map(assets.map((asset) => [asset.id, asset.name]));
  return value.replace(/asset:\/\/([\w-]+)/g, (_match, id: string) => `../image/${names.get(id) || id}`);
}

function webImageText(value: string, imageIds: Map<string, string>) {
  return value.replace(/(?:\.\.\/)?image\/([\w.-]+)/g, (match, name: string) => imageIds.has(name) ? `asset://${imageIds.get(name)}` : match);
}

function reviewRecord(chapter: Chapter) {
  if (chapter.localReviewData && chapter.review === chapter.localReviewText) return chapter.localReviewData;
  if (!chapter.review?.trim()) return null;
  return {
    chapter_number: chapter.order,
    score: null,
    issue_count: 0,
    issues: [],
    summary: chapter.review.trim(),
  };
}

function reviewText(value: Record<string, unknown>) {
  const summary = typeof value.summary === "string" ? value.summary : "";
  const issues = Array.isArray(value.issues) ? value.issues : [];
  const issueText = issues.map((issue, index) => {
    if (!issue || typeof issue !== "object") return `- Lỗi ${index + 1}`;
    const item = issue as Record<string, unknown>;
    return `- ${String(item.type || `Lỗi ${index + 1}`)}: ${String(item.suggestion || item.original_vi || "")}`.trim();
  }).join("\n");
  return [summary, issueText].filter(Boolean).join("\n\n") || stringify(value, { lineWidth: 0 }).trim();
}

export async function exportLocalProject(project: Project, chapters: Chapter[], assets: ProjectAsset[]) {
  const zip = new JSZip();
  const root = zip.folder(safeFolderName(project.name))!;
  root.folder("raw");
  root.folder("translated");
  root.folder("image");
  const imageAssets = assets.filter((asset) => !asset.localPath || asset.localPath.startsWith("image/"));
  for (const chapter of chapters) {
    const name = chapterFileName(chapter);
    if (chapter.source) root.file(`raw/${name}`, localImageText(chapter.source, imageAssets));
    if (chapter.translation) root.file(`translated/${name}`, localImageText(chapter.translation, imageAssets));
  }
  for (const asset of imageAssets) root.file(`image/${asset.name}`, asset.blob);
  if (project.characters.trim()) root.file("characters.md", project.characters);
  root.file("char_index.yaml", stringify({ char_index: project.characterIndex || 0 }));
  root.file("context.yaml", projectContextYaml(project));
  if (project.pronouns?.trim()) root.file("pronouns.yaml", project.pronouns);
  const reviews: Record<string, unknown> = {};
  for (const chapter of chapters) {
    const record = reviewRecord(chapter);
    if (record) reviews[chapterFileName(chapter).replace(/\.md$/i, "")] = record;
  }
  if (Object.keys(reviews).length) root.file("review.yaml", stringify(reviews, { lineWidth: 0 }));
  return zip.generateAsync({ type: "uint8array", compression: "DEFLATE", compressionOptions: { level: 6 } });
}

function archiveRoot(paths: string[]) {
  const raw = paths.find((path) => /(?:^|\/)raw\/[^/]+\.md$/i.test(path));
  const translated = paths.find((path) => /(?:^|\/)translated\/[^/]+\.md$/i.test(path));
  const sample = raw || translated;
  if (!sample) throw new Error("ZIP không có thư mục raw hoặc translated của app local.");
  return sample.slice(0, sample.search(/(?:^|\/)(?:raw|translated)\//i)).replace(/\/$/, "");
}

export async function importLocalProject(buffer: ArrayBuffer): Promise<LocalProjectArchive> {
  const zip = await JSZip.loadAsync(buffer);
  const files = Object.values(zip.files).filter((entry) => !entry.dir);
  const root = archiveRoot(files.map((entry) => entry.name));
  const prefix = root ? `${root}/` : "";
  const relative = (path: string) => path.startsWith(prefix) ? path.slice(prefix.length) : path;
  const byRelative = new Map(files.map((entry) => [relative(entry.name), entry]));
  const imageEntries = files.filter((entry) => relative(entry.name).startsWith("image/"));
  const projectId = crypto.randomUUID();
  const assets: ProjectAsset[] = [];
  const imageIds = new Map<string, string>();
  for (const entry of imageEntries) {
    const name = relative(entry.name).slice("image/".length);
    if (!name || name.includes("/")) continue;
    const id = crypto.randomUUID();
    imageIds.set(name, id);
    assets.push({ id, projectId, name, mimeType: entry.name.endsWith(".png") ? "image/png" : entry.name.endsWith(".webp") ? "image/webp" : entry.name.endsWith(".gif") ? "image/gif" : "image/jpeg", blob: await entry.async("blob"), localPath: `image/${name}` });
  }
  const rawNames = files.map((entry) => relative(entry.name)).filter((path) => path.startsWith("raw/")).map((path) => path.slice(4)).filter((name) => CHAPTER_FILE.test(name));
  const translatedNames = files.map((entry) => relative(entry.name)).filter((path) => path.startsWith("translated/")).map((path) => path.slice(11)).filter((name) => CHAPTER_FILE.test(name));
  const names = [...new Set([...rawNames, ...translatedNames])].sort(compareChapterNames);
  let reviews: Record<string, Record<string, unknown>> = {};
  const reviewEntry = byRelative.get("review.yaml");
  if (reviewEntry) {
    try { reviews = parse(await reviewEntry.async("string")) || {}; } catch { reviews = {}; }
  }
  const stamp = new Date().toISOString();
  const chapters: Chapter[] = [];
  for (const [index, name] of names.entries()) {
    const rawEntry = byRelative.get(`raw/${name}`);
    const translatedEntry = byRelative.get(`translated/${name}`);
    const source = rawEntry ? webImageText(await rawEntry.async("string"), imageIds) : "";
    const translation = translatedEntry ? webImageText(await translatedEntry.async("string"), imageIds) : "";
    const data = reviews[name.replace(/\.md$/i, "")];
    const review = data && typeof data === "object" ? reviewText(data) : "";
    chapters.push({ id: crypto.randomUUID(), projectId, title: chapterTitle(source || translation, name), translatedTitle: translation.trim() ? chapterTitle(translation, name) : undefined, source, translation, review, localFileName: name, localReviewData: data, localReviewText: review, order: index + 1, updatedAt: stamp });
  }
  const read = async (name: string) => byRelative.get(name)?.async("string") || "";
  const contextV1 = await read("context.yaml");
  let context: Record<string, unknown> = {};
  try { context = parse(contextV1) || {}; } catch { context = {}; }
  const glossary = parseGlossary(context.glossary);
  const styleNotes = Array.isArray(context.style_notes) ? context.style_notes.map(String).join("\n") : String(context.style_notes || "");
  let characterIndex = 0;
  try { characterIndex = Number((parse(await read("char_index.yaml")) || {}).char_index) || 0; } catch { characterIndex = 0; }
  const project: Project = { id: projectId, name: root.split("/").pop() || "Truyện khôi phục", sourceLanguage: "Tự động nhận diện", targetLanguage: "Tiếng Việt", characters: await read("characters.md"), characterIndex, contextV1: contextV1 || "index: 0\nstyle_notes: []\nglossary: ''\n", promptRole: String(context.prompt_role || ""), promptTask: String(context.prompt_task || ""), polishPromptRole: String(context.polish_prompt_role || ""), polishPromptTask: String(context.polish_prompt_task || ""), glossaryIndex: Number(context.index) || 0, styleNotes, pronouns: await read("pronouns.yaml"), glossary, createdAt: stamp, updatedAt: stamp };
  return { project, chapters, assets };
}
