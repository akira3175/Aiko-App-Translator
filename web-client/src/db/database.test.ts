import "fake-indexeddb/auto";
import { afterEach, describe, expect, it } from "vitest";
import { db, deleteProject } from "./database";
import type { ProjectAsset } from "../types";

afterEach(async () => {
  await db.projects.clear();
  await db.chapters.clear();
  await db.assets.clear();
});

describe("project backups", () => {
  it("deletes a project together with chapters and image assets", async () => {
    const stamp = "2026-08-10T00:00:00.000Z";
    await db.projects.add({ id: "delete-me", name: "Xóa", sourceLanguage: "Hàn", targetLanguage: "Việt", characters: "", contextV1: "", createdAt: stamp, updatedAt: stamp });
    await db.chapters.add({ id: "chapter-delete", projectId: "delete-me", title: "Chương 1", source: "raw", translation: "dịch", order: 1, updatedAt: stamp });
    await db.assets.add({ id: "asset-delete", projectId: "delete-me", name: "image.png", mimeType: "image/png", blob: new Blob(["image"]) });

    await deleteProject("delete-me");

    expect(await db.projects.get("delete-me")).toBeUndefined();
    expect(await db.chapters.where("projectId").equals("delete-me").count()).toBe(0);
    expect(await db.assets.where("projectId").equals("delete-me").count()).toBe(0);
  });

  it("stores EPUB image blobs in the workspace", async () => {
    const asset: ProjectAsset = {
      id: "asset-1",
      projectId: "project-1",
      name: "cover.png",
      mimeType: "image/png",
      blob: new Blob([new Uint8Array([137, 80, 78, 71])], { type: "image/png" }),
    };

    await db.assets.add(asset);
    const stored = await db.assets.get(asset.id);

    expect(stored?.mimeType).toBe("image/png");
    expect(stored?.blob).toBeInstanceOf(Blob);
    expect(stored?.blob.size).toBe(4);
  });

});
