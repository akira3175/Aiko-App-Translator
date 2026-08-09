// @vitest-environment jsdom
import JSZip from "jszip";
import { describe, expect, it } from "vitest";
import { createChapterImportPreview, parseEpubNovel, parseTxtNovel } from "./importNovel";

describe("novel import", () => {
  it("splits TXT by common Vietnamese chapter headings", () => {
    const novel = parseTxtNovel("Lời mở đầu\n\nChương 1: Gặp gỡ\nNội dung một.\n\nChương 2: Lên đường\nNội dung hai.", "demo.txt");
    expect(novel.name).toBe("demo");
    expect(novel.chapters.map((chapter) => chapter.title)).toEqual(["Mở đầu", "Chương 1: Gặp gỡ", "Chương 2: Lên đường"]);
  });

  it("keeps a heading-free TXT as one chapter", () => {
    const novel = parseTxtNovel("Một văn bản ngắn.", "oneshot.txt");
    expect(novel.chapters).toEqual([{ title: "Chương 1", source: "Một văn bản ngắn." }]);
  });

  it("uses matching chapters as anchors and selects only the new suffix", () => {
    const existing = [
      { title: "Chương 10", source: "# Chương 10\n\nNội dung cũ thứ mười rất dài và rõ ràng." },
      { title: "Chương 11", source: "# Chương 11\n\nNội dung cũ thứ mười một rất dài và rõ ràng." },
    ];
    const incoming = [
      ...existing,
      { title: "Chương 12", source: "# Chương 12\n\nĐây là chương hoàn toàn mới." },
    ];
    const preview = createChapterImportPreview(incoming, existing);
    expect(preview.anchors).toBe(2);
    expect(preview.sourceFrom).toBe(2);
    expect(preview.targetStart).toBe(2);
    expect(preview.chapters.map((chapter) => chapter.selected)).toEqual([false, false, true]);
  });

  it("reports when an anchored file has no newer chapter", () => {
    const chapters = [{ title: "Chương 1", source: "# Chương 1\n\nNội dung trùng hoàn toàn và đủ dài." }];
    const preview = createChapterImportPreview(chapters, chapters);
    expect(preview.noNew).toBe(true);
    expect(preview.chapters[0].selected).toBe(false);
  });

  it("imports EPUB chapters in spine order", async () => {
    const zip = new JSZip();
    zip.file("META-INF/container.xml", '<?xml version="1.0"?><container><rootfiles><rootfile full-path="OPS/book.opf"/></rootfiles></container>');
    zip.file("OPS/book.opf", '<?xml version="1.0"?><package xmlns="http://www.idpf.org/2007/opf" xmlns:dc="http://purl.org/dc/elements/1.1/"><metadata><dc:title>Truyện EPUB</dc:title></metadata><manifest><item id="c1" href="one.xhtml" media-type="application/xhtml+xml"/><item id="c2" href="two.xhtml" media-type="application/xhtml+xml"/><item id="cover" href="images/cover.png" media-type="image/png"/></manifest><spine><itemref idref="c2"/><itemref idref="c1"/></spine></package>');
    zip.file("OPS/one.xhtml", "<html><body><h1>Chương một</h1><p>Nội dung một.</p></body></html>");
    zip.file("OPS/two.xhtml", '<html><body><h1>Chương hai</h1><p>Nội dung hai.</p><img src="images/cover.png" alt="Bìa"/></body></html>');
    zip.file("OPS/images/cover.png", new Uint8Array([137, 80, 78, 71]));
    const data = await zip.generateAsync({ type: "arraybuffer" });
    const novel = await parseEpubNovel(data, "fallback.epub");
    expect(novel.name).toBe("Truyện EPUB");
    expect(novel.chapters.map((chapter) => chapter.title)).toEqual(["Chương hai", "Chương một"]);
    expect(novel.assets).toHaveLength(1);
    expect(novel.chapters[0].source).toContain(`![Bìa](asset://${novel.assets[0].id})`);
  });
});
