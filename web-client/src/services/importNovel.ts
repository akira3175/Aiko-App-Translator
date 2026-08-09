import JSZip from "jszip";

export interface ImportedChapter {
  title: string;
  source: string;
}

export interface ImportedNovel {
  name: string;
  chapters: ImportedChapter[];
  assets: ImportedAsset[];
}

export interface ImportedAsset {
  id: string;
  name: string;
  mimeType: string;
  blob: Blob;
}

export interface ChapterImportPreviewItem extends ImportedChapter {
  sourceIndex: number;
  matchIndex: number | null;
  matchScore: number;
  selected: boolean;
}

export interface ChapterImportPreview {
  chapters: ChapterImportPreviewItem[];
  sourceFrom: number;
  sourceTo: number;
  targetStart: number;
  anchors: number;
  confidence: "high" | "medium" | "manual";
  noNew: boolean;
}

const CHAPTER_HEADING = /^(?:#{1,3}\s*)?(?:(?:chương|chapter|chap)\s+[\p{L}\p{N}]+|第\s*[\p{L}\p{N}]+\s*章|제\s*[\p{L}\p{N}]+\s*화)(?:\s*[:：.\-–—]\s*|\s+|$).*/iu;

function baseName(filename: string) {
  return filename.replace(/\.[^.]+$/, "").trim() || "Truyện mới";
}

function cleanText(value: string) {
  return value
    .replace(/^\uFEFF/, "")
    .replace(/\r\n?/g, "\n")
    .replace(/[ \t]+\n/g, "\n")
    .replace(/\n{3,}/g, "\n\n")
    .trim();
}

function normalizedAnchorText(value: string, title = false) {
  let result = value.normalize("NFKC").toLocaleLowerCase();
  if (title) result = result.replace(/^(?:chapter|chap|chương|第|제)\s*\d+\s*(?:章|話|话|幕|화|장)?/iu, "");
  return result
    .replace(/!\[[^\]]*\]\([^)]*\)/g, "")
    .replace(/[^\p{L}\p{N}_\u3040-\u30ff\u3400-\u9fff\uac00-\ud7af]+/gu, "")
    .slice(0, 1600);
}

function similarityRatio(left: string, right: string) {
  if (!left || !right) return 0;
  if (left === right) return 1;
  if (left.length === 1 || right.length === 1) return left === right ? 1 : 0;
  const pairs = new Map<string, number>();
  for (let index = 0; index < left.length - 1; index += 1) {
    const pair = left.slice(index, index + 2);
    pairs.set(pair, (pairs.get(pair) || 0) + 1);
  }
  let overlap = 0;
  for (let index = 0; index < right.length - 1; index += 1) {
    const pair = right.slice(index, index + 2);
    const count = pairs.get(pair) || 0;
    if (!count) continue;
    overlap += 1;
    pairs.set(pair, count - 1);
  }
  return (2 * overlap) / (left.length + right.length - 2);
}

function anchorFeatures(chapter: ImportedChapter) {
  const lines = chapter.source.split(/\r?\n/);
  return {
    title: normalizedAnchorText(`# ${chapter.title || lines[0] || ""}`, true),
    body: normalizedAnchorText(lines.slice(1).join("\n") || chapter.source),
  };
}

export function createChapterImportPreview(incoming: ImportedChapter[], existing: ImportedChapter[]): ChapterImportPreview {
  if (!incoming.length) throw new Error("Không có chương nào để phân tích.");
  const existingFeatures = existing.map(anchorFeatures);
  const anchors: Array<{ sourceIndex: number; matchIndex: number }> = [];
  const chapters = incoming.map((chapter, sourceIndex): ChapterImportPreviewItem => {
    const source = anchorFeatures(chapter);
    let candidates = existingFeatures.map((candidate, matchIndex) => ({ candidate, matchIndex })).filter(({ candidate }) =>
      (source.title && candidate.title === source.title) || (source.body && candidate.body.slice(0, 240) === source.body.slice(0, 240)),
    );
    if (!candidates.length) candidates = existingFeatures.map((candidate, matchIndex) => ({ candidate, matchIndex })).filter(({ candidate }) =>
      (source.title && similarityRatio(source.title, candidate.title) >= 0.55) || (source.body && similarityRatio(source.body.slice(0, 240), candidate.body.slice(0, 240)) >= 0.55),
    );
    const ranked = candidates.map(({ candidate, matchIndex }) => {
      const titleScore = similarityRatio(source.title, candidate.title);
      const bodyScore = similarityRatio(source.body, candidate.body);
      const score = titleScore * 0.4 + bodyScore * 0.6;
      const valid = bodyScore >= 0.72 || (titleScore >= 0.9 && bodyScore >= 0.35);
      return { matchIndex, score: valid ? score : 0 };
    }).sort((left, right) => right.score - left.score);
    const best = ranked[0] || { matchIndex: -1, score: 0 };
    const secondScore = ranked[1]?.score || 0;
    const matchIndex = best.score >= 0.62 && best.score - secondScore >= 0.08 ? best.matchIndex : null;
    if (matchIndex !== null) anchors.push({ sourceIndex, matchIndex });
    return { ...chapter, sourceIndex, matchIndex, matchScore: matchIndex === null ? 0 : Math.round(best.score * 100) / 100, selected: false };
  });
  const mappings = new Map<string, number[]>();
  for (const anchor of anchors) {
    const offset = anchor.matchIndex - anchor.sourceIndex;
    const key = String(offset);
    mappings.set(key, [...(mappings.get(key) || []), anchor.sourceIndex]);
  }
  const bestMapping = [...mappings.entries()].sort((left, right) => right[1].length - left[1].length)[0];
  let sourceFrom: number;
  let targetStart: number;
  let confidence: ChapterImportPreview["confidence"];
  let noNew = false;
  if (bestMapping) {
    const offset = Number(bestMapping[0]);
    sourceFrom = Math.max(...bestMapping[1]) + 1;
    noNew = sourceFrom >= chapters.length;
    if (noNew) sourceFrom = chapters.length - 1;
    targetStart = sourceFrom + offset;
    confidence = bestMapping[1].length >= 2 ? "high" : "medium";
  } else {
    sourceFrom = 0;
    targetStart = existing.length;
    confidence = "manual";
  }
  const sourceTo = chapters.length - 1;
  chapters.forEach((chapter) => { chapter.selected = !noNew && chapter.sourceIndex >= sourceFrom; });
  return { chapters, sourceFrom, sourceTo, targetStart, anchors: bestMapping?.[1].length || 0, confidence, noNew };
}

export function parseTxtNovel(text: string, filename = "truyen.txt"): ImportedNovel {
  const source = cleanText(text);
  if (!source) throw new Error("Tệp TXT không có nội dung.");
  const lines = source.split("\n");
  const headings = lines.flatMap((line, index) => CHAPTER_HEADING.test(line.trim()) ? [index] : []);
  if (!headings.length) {
    return { name: baseName(filename), chapters: [{ title: "Chương 1", source }], assets: [] };
  }

  const chapters: ImportedChapter[] = [];
  if (headings[0] > 0) {
    const opening = cleanText(lines.slice(0, headings[0]).join("\n"));
    if (opening) chapters.push({ title: "Mở đầu", source: opening });
  }
  headings.forEach((start, position) => {
    const end = headings[position + 1] ?? lines.length;
    const title = lines[start].replace(/^#{1,3}\s*/, "").trim() || `Chương ${position + 1}`;
    const chapter = cleanText(lines.slice(start, end).join("\n"));
    if (chapter) chapters.push({ title, source: chapter });
  });
  return { name: baseName(filename), chapters, assets: [] };
}

function parseXml(source: string, label: string) {
  const document = new DOMParser().parseFromString(source, "application/xml");
  if (document.querySelector("parsererror")) throw new Error(`${label} trong EPUB không hợp lệ.`);
  return document;
}

function elementsByName(document: Document, name: string) {
  return [...document.getElementsByTagName("*")].filter((element) => element.localName === name);
}

function resolvePath(base: string, relative: string) {
  const parts = `${base}/${relative}`.split("/");
  const resolved: string[] = [];
  for (const part of parts) {
    if (!part || part === ".") continue;
    if (part === "..") resolved.pop();
    else resolved.push(part);
  }
  return resolved.join("/");
}

function decodePath(value: string) {
  try { return decodeURIComponent(value); } catch { return value; }
}

function htmlChapter(source: string, fallbackTitle: string, chapterPath: string, assetIds: Map<string, string>): ImportedChapter | null {
  const document = new DOMParser().parseFromString(source, "text/html");
  document.querySelectorAll("script,style,nav,svg").forEach((element) => element.remove());
  const title = document.querySelector("h1,h2,h3")?.textContent?.trim()
    || document.querySelector("title")?.textContent?.trim()
    || fallbackTitle;
  const chapterDirectory = chapterPath.includes("/") ? chapterPath.slice(0, chapterPath.lastIndexOf("/")) : "";
  const blocks = [...document.body.querySelectorAll("h1,h2,h3,h4,p,li,blockquote,pre,img")]
    .filter((element) => !element.parentElement?.closest("h1,h2,h3,h4,p,li,blockquote,pre"))
    .map((element) => {
      if (element.tagName === "IMG") {
        const src = element.getAttribute("src") || "";
        const assetId = assetIds.get(resolvePath(chapterDirectory, decodePath(src.split("#")[0])));
        return assetId ? `![${element.getAttribute("alt") || "Ảnh"}](asset://${assetId})` : "";
      }
      const clone = element.cloneNode(true) as Element;
      clone.querySelectorAll("img").forEach((image) => {
        const src = image.getAttribute("src") || "";
        const assetId = assetIds.get(resolvePath(chapterDirectory, decodePath(src.split("#")[0])));
        image.replaceWith(assetId ? `\n![${image.getAttribute("alt") || "Ảnh"}](asset://${assetId})\n` : "");
      });
      clone.querySelectorAll("br").forEach((lineBreak) => lineBreak.replaceWith("\n"));
      const text = clone.textContent?.replace(/[ \t]+/g, " ").trim() || "";
      if (!text) return "";
      if (/^H[1-4]$/.test(element.tagName)) return `${"#".repeat(Number(element.tagName[1]))} ${text}`;
      if (element.tagName === "LI") return `- ${text}`;
      if (element.tagName === "BLOCKQUOTE") return `> ${text}`;
      return text;
    })
    .filter(Boolean);
  const text = cleanText(blocks.length ? blocks.join("\n\n") : document.body.textContent || "");
  return text ? { title, source: text } : null;
}

export async function parseEpubNovel(buffer: ArrayBuffer, filename = "truyen.epub"): Promise<ImportedNovel> {
  const zip = await JSZip.loadAsync(buffer);
  const containerEntry = zip.file("META-INF/container.xml");
  if (!containerEntry) throw new Error("EPUB thiếu META-INF/container.xml.");
  const container = parseXml(await containerEntry.async("string"), "container.xml");
  const packagePath = elementsByName(container, "rootfile")[0]?.getAttribute("full-path");
  if (!packagePath) throw new Error("Không tìm thấy package OPF trong EPUB.");
  const packageEntry = zip.file(packagePath);
  if (!packageEntry) throw new Error("Không đọc được package OPF trong EPUB.");
  const opf = parseXml(await packageEntry.async("string"), "package OPF");
  const packageDirectory = packagePath.includes("/") ? packagePath.slice(0, packagePath.lastIndexOf("/")) : "";
  const manifestElement = elementsByName(opf, "manifest")[0];
  const manifestItems = manifestElement ? [...manifestElement.children].filter((element) => element.localName === "item") : [];
  const manifest = new Map(manifestItems.map((item) => [
    item.getAttribute("id") || "",
    { href: item.getAttribute("href") || "", mediaType: item.getAttribute("media-type") || "" },
  ]));
  const title = elementsByName(opf, "title")[0]?.textContent?.trim() || baseName(filename);
  const assets: ImportedAsset[] = [];
  const assetIds = new Map<string, string>();
  for (const item of manifest.values()) {
    if (!item.mediaType.startsWith("image/")) continue;
    const path = resolvePath(packageDirectory, decodePath(item.href.split("#")[0]));
    const entry = zip.file(path);
    if (!entry) continue;
    const id = crypto.randomUUID();
    assets.push({ id, name: path.split("/").pop() || "image", mimeType: item.mediaType, blob: await entry.async("blob") });
    assetIds.set(path, id);
  }
  const chapters: ImportedChapter[] = [];
  const spineElement = elementsByName(opf, "spine")[0];
  const spineItems = spineElement ? [...spineElement.children].filter((element) => element.localName === "itemref") : [];
  for (const [index, itemref] of spineItems.entries()) {
    const item = manifest.get(itemref.getAttribute("idref") || "");
    if (!item || !/xhtml|html/i.test(item.mediaType)) continue;
    const chapterPath = resolvePath(packageDirectory, decodePath(item.href.split("#")[0]));
    const entry = zip.file(chapterPath);
    if (!entry) continue;
    const chapter = htmlChapter(await entry.async("string"), `Chương ${index + 1}`, chapterPath, assetIds);
    if (chapter) chapters.push(chapter);
  }
  if (!chapters.length) throw new Error("EPUB không có chương văn bản có thể nhập.");
  return { name: title, chapters, assets };
}

export async function parseNovelFile(file: File): Promise<ImportedNovel> {
  const extension = file.name.split(".").pop()?.toLowerCase();
  if (extension === "txt") return parseTxtNovel(await file.text(), file.name);
  if (extension === "epub") return parseEpubNovel(await file.arrayBuffer(), file.name);
  throw new Error("Chỉ hỗ trợ tệp EPUB hoặc TXT.");
}
