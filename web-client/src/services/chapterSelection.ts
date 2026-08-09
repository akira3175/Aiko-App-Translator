import type { Chapter } from "../types";

export function resumeChapterId(chapters: Chapter[]) {
  if (!chapters.length) return "";
  let lastTranslated = -1;
  chapters.forEach((chapter, index) => {
    if (chapter.translation.trim()) lastTranslated = index;
  });
  return chapters[lastTranslated + 1]?.id || chapters[chapters.length - 1].id;
}
