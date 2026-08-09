// @vitest-environment jsdom
import JSZip from "jszip";
import { describe, expect, it } from "vitest";
import { parse } from "yaml";
import type { Chapter, Project, ProjectAsset } from "../types";
import { exportLocalProject, importLocalProject, projectContextYaml } from "./localProjectArchive";

describe("local project archive", () => {
  it("builds one complete context YAML without appending duplicate fields", () => {
    const project = { id: "p", name: "Truyện", sourceLanguage: "Hàn", targetLanguage: "Việt", characters: "", contextV1: "index: 1\nstyle_notes: cũ\nglossary: cũ = old\n", styleNotes: "quy tắc mới", glossary: [{ id: "g", source: "원문", target: "nguyên văn" }], createdAt: "", updatedAt: "" } satisfies Project;
    const yaml = projectContextYaml(project);
    expect(parse(yaml)).toMatchObject({ index: 1, style_notes: "quy tắc mới", glossary: "원문 = nguyên văn" });
    expect(yaml.match(/^style_notes:/gm)).toHaveLength(1);
    expect(yaml.match(/^glossary:/gm)).toHaveLength(1);
  });

  it("exports the exact local raw, translated, image and YAML layout", async () => {
    const stamp = "2026-08-10T00:00:00.000Z";
    const project: Project = { id: "project", name: "Truyện thử", sourceLanguage: "Hàn", targetLanguage: "Việt", characters: "# Nhân vật", characterIndex: 12, contextV1: "index: 3\n", promptRole: "Vai trò dịch", promptTask: "Nhiệm vụ dịch", polishPromptRole: "Vai trò hiệu đính", polishPromptTask: "Nhiệm vụ hiệu đính", glossaryIndex: 3, styleNotes: "Giữ tên riêng", glossary: [{ id: "g1", source: "마탑", target: "Ma Tháp" }], pronouns: "A---B:\n  locked: false\n", createdAt: stamp, updatedAt: stamp };
    const chapter: Chapter = { id: "chapter", projectId: project.id, title: "Chương thử", source: "# Chương thử\n\n![Bìa](asset://image-id)", translation: "# Chương dịch\n\nBản dịch", review: "Ổn", localFileName: "v2_c7_s3.md", order: 1, updatedAt: stamp };
    const asset: ProjectAsset = { id: "image-id", projectId: project.id, name: "cover.png", mimeType: "image/png", blob: new Blob([new Uint8Array([137, 80, 78, 71])]) };

    const data = await exportLocalProject(project, [chapter], [asset]);
    const zip = await JSZip.loadAsync(data);

    expect(await zip.file("Truyện thử/raw/v2_c7_s3.md")?.async("string")).toContain("../image/cover.png");
    expect(await zip.file("Truyện thử/translated/v2_c7_s3.md")?.async("string")).toContain("Bản dịch");
    expect(zip.file("Truyện thử/image/cover.png")).toBeTruthy();
    expect(await zip.file("Truyện thử/characters.md")?.async("string")).toBe("# Nhân vật");
    const context = parse(await zip.file("Truyện thử/context.yaml")!.async("string"));
    expect(context.glossary).toBe("마탑 = Ma Tháp");
    expect(context.prompt_role).toBe("Vai trò dịch");
    expect(context.polish_prompt_task).toBe("Nhiệm vụ hiệu đính");
    expect(parse(await zip.file("Truyện thử/review.yaml")!.async("string")).v2_c7_s3.summary).toBe("Ổn");
    expect(zip.file("Truyện thử/project.json")).toBeNull();
  });

  it("restores local filenames and converts image paths for web preview", async () => {
    const zip = new JSZip();
    zip.file("Truyện local/raw/v1_c0_s1.md", "# 원문\n\n![Ảnh](../image/a.png)");
    zip.file("Truyện local/translated/v1_c0_s1.md", "# Bản dịch\n\nNội dung");
    zip.file("Truyện local/image/a.png", new Uint8Array([137, 80, 78, 71]));
    zip.file("Truyện local/context.yaml", "index: 1\nstyle_notes: tự nhiên\nprompt_role: Vai trò dịch\nprompt_task: Nhiệm vụ dịch\npolish_prompt_role: Vai trò hiệu đính\npolish_prompt_task: Nhiệm vụ hiệu đính\nglossary: |\n  원문 = nguyên văn\n");
    zip.file("Truyện local/characters.md", "# Hồ sơ");
    zip.file("Truyện local/char_index.yaml", "char_index: 9\n");
    zip.file("Truyện local/pronouns.yaml", "A---B:\n  locked: false\n");
    zip.file("Truyện local/review.yaml", "v1_c0_s1:\n  chapter_number: 1\n  score: 10\n  issue_count: 0\n  issues: []\n  summary: Tốt\n");

    const archive = await importLocalProject(await zip.generateAsync({ type: "arraybuffer" }));

    expect(archive.project.name).toBe("Truyện local");
    expect(archive.project.characterIndex).toBe(9);
    expect(archive.project.glossary?.[0]).toMatchObject({ source: "원문", target: "nguyên văn" });
    expect(archive.project.promptRole).toBe("Vai trò dịch");
    expect(archive.project.polishPromptTask).toBe("Nhiệm vụ hiệu đính");
    expect(archive.chapters[0].localFileName).toBe("v1_c0_s1.md");
    expect(archive.chapters[0].translatedTitle).toBe("Bản dịch");
    expect(archive.chapters[0].translation).toContain("Nội dung");
    expect(archive.chapters[0].review).toBe("Tốt");
    expect(archive.chapters[0].source).toContain(`asset://${archive.assets[0].id}`);
  });
});
