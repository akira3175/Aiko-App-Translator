# Parallel Subagent & Workflow Patterns for Aiko Novel Pipeline

When the user asks to process many chapters (e.g., building a glossary across 100–400+ chapters, reviewing 50 chapters, or translating/polishing a multi-chapter arc), use Antigravity's native subagents (`invoke_subagent` with `TypeName: "self"` or `run_workflow`) to run in parallel while strictly routing all prompt preparation and file persistence through `aiko_bridge.py`.

---

## 1. Fast Parallel Glossary Extraction (e.g., 100–500 Chapters)

Why sequential 30-chapter glossary batches feel slow:
- 30 raw chapters ≈ 100K+ characters (>60K tokens), which exceeds a single `read_file` window and takes several minutes of deep reasoning per batch.

**Optimal Parallel Strategy (10 chapters per slice × N subagents):**

1. Run `status` to check `glossary_processed_index` and `total_raw`.
2. Prepare slice bundles of `--count 10` with `--no-existing` into scratch directories:
   ```powershell
   python ".agents/skills/aiko-novel-pipeline/scripts/aiko_bridge.py" glossary-prepare --project "<Project>" --start 1 --count 10 --no-existing --out "<scratch>/g_001_010"
   python ".agents/skills/aiko-novel-pipeline/scripts/aiko_bridge.py" glossary-prepare --project "<Project>" --start 11 --count 10 --no-existing --out "<scratch>/g_011_020"
   # ... up to 4-6 parallel slices per wave
   ```
3. Spawn parallel subagents (`invoke_subagent`, `TypeName: "self"`), giving each subagent its own bundle path (`<scratch>/g_XXX_YYY/prompt.md`) and instructing it to:
   - Read the entire `prompt.md` (paginating with `StartLine`/`EndLine` if truncated!).
   - Write its extracted `###START### ... ###END###` glossary output to `<scratch>/g_XXX_YYY/result.txt`.
4. Harmonize & Commit:
   - Read the existing `truyen/<Project>/glossary.txt` (if any) plus all `result.txt` files from the wave.
   - Deduplicate conflicting translations for the same source term so one canonical Vietnamese translation wins across all slices, write the harmonized `###START### ... ###END###` file to `<scratch>/wave_harmonized.txt`, and commit atomically:
     ```powershell
     python ".agents/skills/aiko-novel-pipeline/scripts/aiko_bridge.py" glossary-commit --project "<Project>" --in "<scratch>/wave_harmonized.txt" --incremental --new-index <last_chapter_end>
     ```

---

## 2. Multi-Chapter Translation + Polish + Pronouns + Review Pipeline

Why full-pipeline chapter translation has sequential dependencies:
- Each chapter uses `previous_context_chapters` (default: 3 recent translated chapters) for style continuity and updated `pronouns.json`.

**Two modes depending on user preference:**

### Mode A: Maximum Continuity (1 chapter at a time, full pipeline)
For each chapter:
1. `translate-prepare` → read `prompt.md` + `characters.md` + `pronouns_snapshot.json` → write `trans.txt` → `translate-commit`.
2. If polish is requested: `polish-prepare --with-pronouns` → read bundle → write `polish.txt` → `polish-commit` (this updates both `translated/<ch>.md` and `pronouns.json` in one pass!).
3. If review is requested: `review-prepare` → read bundle → write `review.json` → `review-commit`.

### Mode B: Parallel Wave Translation (3–5 chapters per wave)
When `glossary.txt`, `characters.json`, and `pronouns.json` are already established and the user wants high speed:
1. Prepare bundles for chapters `c1..c5` via `translate-prepare --chapter <ch>`.
2. Launch 3–5 subagents in parallel (`TypeName: "self"`), each translating one chapter bundle and running `translate-commit` (fixing any foreign-script remnants flagged by `translate-commit` before finishing).
3. Optionally launch parallel subagents for `polish-prepare --with-pronouns` / `polish-commit` and `review-prepare` / `review-commit` (note: `pronouns.json` uses file locking in `edit_pronouns`, and `review.json` uses atomic `save_json`, though committing sequentially in the coordinator avoids any race on `review.json`).

---

## 3. Character Profile Milestones (`characters-prepare` / `characters-commit`)

Character profile updates (`characters.json` / `characters.md`) track state changes by chapter milestone (`v1_c5_s1`) and depend on previously discovered character IDs (`char_...`).
- **Always run character batches sequentially** (`--count 8` or `--count 10` per batch) so each batch sees canonical character IDs created in earlier batches and avoids duplicate character entries.

---

## 4. Handling R19 Placeholders (`untranslated_r19`)

When `translate-prepare` reports non-empty `"untranslated_r19"` in `meta.json`:
1. Keep all `__20AGE_XXXX__` placeholders untouched inside `###TITLE###` and `###CONTENT###` of `trans.txt` (exact match required by `restore_results`).
2. Create an `r19_map.json` mapping each new token (or source phrase) to its natural Vietnamese translation:
   ```json
   {
     "__20AGE_0001__": "bản dịch tiếng Việt tự nhiên"
   }
   ```
3. Pass `--r19-map "<scratch>/r19_map.json"` to `translate-commit`. The bridge automatically caches those new R19 words into `data/r19_words.txt` and restores capitalization/casing in the chapter!
