import { describe, expect, it } from "vitest";
import type { Chapter } from "../types";
import { resumeChapterId } from "./chapterSelection";

function chapter(id: string, translation = ""): Chapter {
  return { id, projectId: "p", title: id, source: "raw", translation, order: 1, updatedAt: "" };
}

describe("resumeChapterId", () => {
  it("opens the first chapter when the story has not been translated", () => {
    expect(resumeChapterId([chapter("c1"), chapter("c2")])).toBe("c1");
  });

  it("opens the chapter immediately after the last translated chapter", () => {
    expect(resumeChapterId([chapter("c1", "dịch"), chapter("c2", "dịch"), chapter("c3")])).toBe("c3");
  });

  it("opens the last chapter when every chapter is translated", () => {
    expect(resumeChapterId([chapter("c1", "dịch"), chapter("c2", "dịch")])).toBe("c2");
  });
});
