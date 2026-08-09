import Dexie, { type EntityTable } from "dexie";
import type { AppSettings, Chapter, Project, ProjectAsset } from "../types";

class TranslatorDatabase extends Dexie {
  projects!: EntityTable<Project, "id">;
  chapters!: EntityTable<Chapter, "id">;
  settings!: EntityTable<AppSettings, "id">;
  assets!: EntityTable<ProjectAsset, "id">;

  constructor() {
    super("novel-translator-web");
    this.version(1).stores({
      projects: "id, updatedAt, name",
      chapters: "id, projectId, [projectId+order], updatedAt",
      settings: "id",
    });
    this.version(2).stores({
      projects: "id, updatedAt, name",
      chapters: "id, projectId, [projectId+order], updatedAt",
      settings: "id",
      assets: "id, projectId, chapterId",
    });
  }
}

export const db = new TranslatorDatabase();

export async function deleteProject(projectId: string): Promise<void> {
  await db.transaction("rw", db.projects, db.chapters, db.assets, async () => {
    await db.chapters.where("projectId").equals(projectId).delete();
    await db.assets.where("projectId").equals(projectId).delete();
    await db.projects.delete(projectId);
  });
}
