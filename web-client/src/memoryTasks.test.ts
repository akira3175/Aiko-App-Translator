import { describe, expect, it } from "vitest";
import { extractCharacterBlock, mergeCharacterMarkdown, parseGlossaryResponse } from "./App";

describe("memory task responses", () => {
  it("only accepts a valid character Markdown block", () => {
    expect(extractCharacterBlock("Giải thích không hợp lệ")).toBe("");
    expect(extractCharacterBlock("###CHAR_START###\n## Gray\n- **Giới tính**: Nữ\n###CHAR_END###")).toContain("## Gray");
  });

  it("merges character profiles and preserves omitted legacy fields", () => {
    const existing = "## Gray\n- **Giới tính**: Nữ\n- **Phe**: Học viện";
    const incoming = "## Gray\n- **Giới tính**: Nữ\n- **Tuổi**: 20";
    const merged = mergeCharacterMarkdown(existing, incoming);
    expect(merged).toContain("**Tuổi**: 20");
    expect(merged).toContain("**Phe**: Học viện");
  });

  it("requires glossary markers and parses source-target lines", () => {
    expect(parseGlossaryResponse("###START###\n김철수 = Kim Cheol-su\n###END###")).toEqual([{ source: "김철수", target: "Kim Cheol-su" }]);
    expect(() => parseGlossaryResponse("김철수 = Kim Cheol-su")).toThrow(/START\/END/);
  });
});
