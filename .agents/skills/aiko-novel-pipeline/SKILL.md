---
name: aiko-novel-pipeline
description: >-
  Direct Antigravity controller for Aiko App Translator novel projects in `truyen/`.
  Activate whenever the user asks to inspect novel progress, build or update glossary/context,
  analyze character profiles (`characters.json`), translate chapters, polish/edit translations,
  extract or update pronouns (`pronouns.json`), or review translated chapters (`review.json`)
  directly from Antigravity. Reuses 100% of the project's optimized Python `cores/` logic.
---

# Aiko Novel Pipeline — Direct Antigravity Controller

This skill lets you run all AI stages of **Aiko App Translator** directly inside Antigravity (zero external browser/CLI wrapper overhead, full visibility, parallel subagents) while **reusing 100% of the user's optimized Python code in `cores/` and `services/`**.

## Golden Rules (MUST FOLLOW)

1. **NEVER hand-craft prompts or write directly to `truyen/<Project>/` files** (`translated/*.md`, `context.json`, `glossary.txt`, `characters.json`, `pronouns.json`, `review.json`).
2. **ALWAYS go through [aiko_bridge.py](./scripts/aiko_bridge.py)**:
   - Run `*-prepare` to generate the exact R19-masked, image-marker-tagged, glossary-filtered, character-snapshot-filtered prompt bundle into `<ArtifactDir>/scratch/<bundle>/`.
   - Read **100%** of `prompt.md` and every file listed in `"reference_files"` (`characters.md`, `pronouns_snapshot.json`). **If `read_file` truncates a long `prompt.md`, immediately read the remaining line ranges with `StartLine`/`EndLine` until EOF — never generate from a truncated prompt!**
   - Write your raw AI output (`###TITLE###...###END###`, `###START###...###END###`, or JSON) to `<bundle>/result.txt`.
   - Run `*-commit` so Aiko's native validators check formatting, restore R19 placeholders, verify image markers, catch leftover foreign characters, respect locked pronouns/character fields, create `.bak` backups, and log to `Nhật ký AI`.

---

## Bridge CLI Quick Reference

Script path: `.agents/skills/aiko-novel-pipeline/scripts/aiko_bridge.py`

### 1. Inspect Projects & Progress
```powershell
# List all projects in truyen/
python ".agents/skills/aiko-novel-pipeline/scripts/aiko_bridge.py" status

# Detailed status for one project
python ".agents/skills/aiko-novel-pipeline/scripts/aiko_bridge.py" status --project "<Tên truyện>"
```

### 2. Glossary / Context (`context.json` & `glossary.txt`)
Keep `--count` around **10–12 chapters** per batch (~30–40K chars) for fast, zero-truncation reads. For 50+ chapters, read [parallel_workflows.md](./references/parallel_workflows.md) to fan out parallel subagents!
```powershell
python ".agents/skills/aiko-novel-pipeline/scripts/aiko_bridge.py" glossary-prepare --project "<Tên truyện>" --count 10 --out "<scratch>/glossary_b1"
# -> Read prompt.md completely, write ###START### ... ###END### to <scratch>/glossary_b1/result.txt
python ".agents/skills/aiko-novel-pipeline/scripts/aiko_bridge.py" glossary-commit --project "<Tên truyện>" --bundle "<scratch>/glossary_b1" --in "<scratch>/glossary_b1/result.txt"
```

### 3. Character Profiles (`characters.json` & `characters.md`)
Run batches sequentially (`--count 8` or `10`) so canonical character IDs carry forward cleanly:
```powershell
python ".agents/skills/aiko-novel-pipeline/scripts/aiko_bridge.py" characters-prepare --project "<Tên truyện>" --count 10 --out "<scratch>/chars_b1"
# -> Read prompt.md completely, write structured JSON updates to <scratch>/chars_b1/result.json
python ".agents/skills/aiko-novel-pipeline/scripts/aiko_bridge.py" characters-commit --project "<Tên truyện>" --bundle "<scratch>/chars_b1" --in "<scratch>/chars_b1/result.json"
```

### 4. Translate Chapter (`translated/<chapter>.md`)
```powershell
# Omit --chapter to auto-pick the next untranslated chapter
python ".agents/skills/aiko-novel-pipeline/scripts/aiko_bridge.py" translate-prepare --project "<Tên truyện>" --out "<scratch>/trans_1"
# -> Read prompt.md AND all reference_files (characters.md, pronouns_snapshot.json).
# -> Check meta.json: if `untranslated_r19` is non-empty, keep `__20AGE_XXXX__` intact in result.txt and write `<scratch>/trans_1/r19_map.json`.
# -> Write ###TITLE### ... ###CONTENT### ... ###END### to <scratch>/trans_1/result.txt
python ".agents/skills/aiko-novel-pipeline/scripts/aiko_bridge.py" translate-commit --project "<Tên truyện>" --bundle "<scratch>/trans_1" --in "<scratch>/trans_1/result.txt"
```
- **Foreign character check**: If `translate-commit` exits with leftover foreign lines (`L12: ...`), fix those exact lines in `result.txt` and re-run `translate-commit`!

### 5. Polish + Pronoun Extraction (`polish` + `pronouns.json`)
```powershell
# Add --with-pronouns to extract ###PRONOUNS### in the same pass!
python ".agents/skills/aiko-novel-pipeline/scripts/aiko_bridge.py" polish-prepare --project "<Tên truyện>" --chapter "v1_c1_s1.md" --with-pronouns --out "<scratch>/polish_1"
# -> Read prompt.md + characters.md, write ###TITLE### ... ###CONTENT### ... ###PRONOUNS### ... ###END### to result.txt
# -> Add --pending if the user wants to review paragraph diffs in the Web UI before overwriting!
python ".agents/skills/aiko-novel-pipeline/scripts/aiko_bridge.py" polish-commit --project "<Tên truyện>" --bundle "<scratch>/polish_1" --in "<scratch>/polish_1/result.txt"
```

### 6. Standalone Pronouns or Quality Review
```powershell
# Standalone pronoun extraction
python ".agents/skills/aiko-novel-pipeline/scripts/aiko_bridge.py" pronouns-prepare --project "<Tên truyện>" --chapter "v1_c1_s1.md" --out "<scratch>/pron_1"
python ".agents/skills/aiko-novel-pipeline/scripts/aiko_bridge.py" pronouns-commit --project "<Tên truyện>" --bundle "<scratch>/pron_1" --in "<scratch>/pron_1/result.json"

# Quality review (updates review.json & manual_check.json)
python ".agents/skills/aiko-novel-pipeline/scripts/aiko_bridge.py" review-prepare --project "<Tên truyện>" --chapter "v1_c1_s1.md" --out "<scratch>/rev_1"
python ".agents/skills/aiko-novel-pipeline/scripts/aiko_bridge.py" review-commit --project "<Tên truyện>" --bundle "<scratch>/rev_1" --in "<scratch>/rev_1/result.json"
```

---

## Scaling Up to Hundreds of Chapters

Whenever the user asks to process a large batch (e.g. >20 chapters of Glossary, Review, or multi-chapter Translation), read **[parallel_workflows.md](./references/parallel_workflows.md)** first for exact parallel subagent fan-out, harmonization, and R19 handling procedures.
