import { useEffect, useState } from "react";
import type { ReactNode } from "react";
import type { ProjectAsset } from "../types";

function inlineMarkdown(value: string): ReactNode[] {
  const output: ReactNode[] = [];
  const pattern = /\*\*\*([^*]+)\*\*\*|\*\*([^*]+)\*\*|\*([^*]+)\*/g;
  let cursor = 0;
  for (const match of value.matchAll(pattern)) {
    const index = match.index || 0;
    if (index > cursor) output.push(value.slice(cursor, index));
    if (match[1] !== undefined) output.push(<strong key={`${index}-bold-italic`}><em>{match[1]}</em></strong>);
    else if (match[2] !== undefined) output.push(<strong key={`${index}-bold`}>{match[2]}</strong>);
    else output.push(<em key={`${index}-italic`}>{match[3]}</em>);
    cursor = index + match[0].length;
  }
  if (cursor < value.length) output.push(value.slice(cursor));
  return output;
}

function isListLine(value: string) {
  return /^\s*[-*+]\s+/.test(value) && !/^\s*(\*{1,3})\s*[^*]+?\s*\1\s*$/.test(value);
}

function plainInlineMarkdown(value: string) {
  return value.replace(/!\[([^\]]*)\]\([^)]+\)/g, "$1").replace(/\*\*\*([^*]+)\*\*\*/g, "$1").replace(/\*\*([^*]+)\*\*/g, "$1").replace(/\*([^*]+)\*/g, "$1");
}

function escapeHtml(value: string) {
  return value.replace(/&/g, "&amp;").replace(/</g, "&lt;").replace(/>/g, "&gt;").replace(/"/g, "&quot;");
}

function inlineMarkdownHtml(value: string) {
  return escapeHtml(value).replace(/\*\*\*([^*]+)\*\*\*/g, "<strong><em>$1</em></strong>").replace(/\*\*([^*]+)\*\*/g, "<strong>$1</strong>").replace(/\*([^*]+)\*/g, "<em>$1</em>");
}

type PreviewBlock = { kind: "paragraph" | "heading" | "list" | "rule"; text: string; line: number; level?: number; items?: string[] };

function previewBlocks(value: string): PreviewBlock[] {
  const lines = value.replace(/\r\n?/g, "\n").split("\n");
  const blocks: PreviewBlock[] = [];
  let start = -1;
  let content: string[] = [];
  const flush = () => {
    if (start >= 0 && content.some((line) => line.trim())) blocks.push({ kind: "paragraph", text: content.join("\n").trim(), line: start + 1 });
    start = -1;
    content = [];
  };
  for (let index = 0; index < lines.length; index += 1) {
    const line = lines[index];
    if (!line.trim()) { flush(); continue; }
    const heading = line.match(/^(#{1,4})\s+(.+)$/);
    if (heading) {
      flush();
      blocks.push({ kind: "heading", text: heading[2], level: heading[1].length, line: index + 1 });
      continue;
    }
    if (/^\s*(?:---+|\*\*\*+)\s*$/.test(line)) {
      flush();
      blocks.push({ kind: "rule", text: "", line: index + 1 });
      continue;
    }
    if (isListLine(line)) {
      flush();
      const firstLine = index + 1;
      const items: string[] = [];
      while (index < lines.length && isListLine(lines[index])) {
        items.push(lines[index].replace(/^\s*[-*+]\s+/, ""));
        index += 1;
      }
      index -= 1;
      blocks.push({ kind: "list", text: "", items, line: firstLine });
      continue;
    }
    if (start < 0) start = index;
    content.push(line);
  }
  flush();
  return blocks;
}

export function markdownToPlainText(value: string) {
  return previewBlocks(value).map((block) => {
    if (block.kind === "rule") return "";
    if (block.kind === "list") return (block.items || []).map((item) => `• ${plainInlineMarkdown(item)}`).join("\n");
    return plainInlineMarkdown(block.text);
  }).filter(Boolean).join("\n\n");
}

export function markdownToClipboardHtml(value: string) {
  return previewBlocks(value).map((block) => {
    if (block.kind === "rule") return "<hr>";
    if (block.kind === "list") return `<ul>${(block.items || []).map((item) => `<li>${inlineMarkdownHtml(item)}</li>`).join("")}</ul>`;
    if (block.kind === "heading") return `<h${block.level}>${inlineMarkdownHtml(block.text)}</h${block.level}>`;
    return `<p>${inlineMarkdownHtml(block.text).replace(/\n/g, "<br>")}</p>`;
  }).join("");
}

export function MarkdownPreview({ value, assets, label, onEditLine }: { value: string; assets: ProjectAsset[]; label: string; onEditLine?: (line: number) => void; editorStyle?: boolean }) {
  const [urls, setUrls] = useState<Record<string, string>>({});

  useEffect(() => {
    const next = Object.fromEntries(assets.map((asset) => [asset.id, URL.createObjectURL(asset.blob)]));
    setUrls(next);
    return () => Object.values(next).forEach((url) => URL.revokeObjectURL(url));
  }, [assets]);

  const blocks = previewBlocks(value);
  const edit = (line: number) => onEditLine ? { onDoubleClick: () => onEditLine(line), title: "Nhấp đúp để chỉnh dòng này" } : {};
  return <div className={onEditLine ? "markdown-preview editable-preview" : "markdown-preview"} aria-label={label}>
    {blocks.map((block, index) => {
      const text = block.text;
      if (block.kind === "rule") return <hr key={index} {...edit(block.line)} />;
      if (block.kind === "list") return <ul key={index} {...edit(block.line)}>{block.items?.map((item, itemIndex) => <li key={itemIndex}>{inlineMarkdown(item)}</li>)}</ul>;
      if (block.kind === "heading") {
        const Heading = `h${block.level}` as "h1" | "h2" | "h3" | "h4";
        return <Heading key={index} {...edit(block.line)}>{inlineMarkdown(text)}</Heading>;
      }
      const image = text.match(/^!\[([^\]]*)\]\(asset:\/\/([^)]+)\)$/);
      if (image) return urls[image[2]]
        ? <figure key={`${image[2]}-${index}`} {...edit(block.line)}><img src={urls[image[2]]} alt={image[1] || "Ảnh trong truyện"} /><figcaption>{image[1]}</figcaption></figure>
        : <p className="missing-asset" key={index}>Không tìm thấy ảnh: {image[1] || image[2]}</p>;
      return <p key={index} {...edit(block.line)}>{inlineMarkdown(text)}</p>;
    })}
    {!blocks.length && <p className="preview-empty">Chưa có nội dung để xem trước.</p>}
  </div>;
}
