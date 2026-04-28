---
phase: 23-streaming-markdown-renderer
plan: 02
subsystem: markdown-renderer
tags: [markdown, renderer, block-parsing, headings, lists, code-blocks, blockquotes, tables, wordwrap-composition, md-08]

# Dependency graph
requires:
  - phase: 23-streaming-markdown-renderer
    plan: 01
    provides: write_bytes on PrinterDriver Protocol + 5 drivers (the style channel sink)
provides:
  - MarkdownRenderer class in src/claude_teletype/markdown.py
  - Block-level parsing for ATX headings, unordered/ordered/nested lists, fenced code blocks, blockquotes, GFM tables
  - text_output_fn / style_output_fn dual-channel API (style stub in this plan)
  - _render_inline seam for Plan 23-03 to replace with bold/italic state machine
  - MD-08 newline-routing contract enforced in code + tests
affects: [23-03-PLAN, markdown-renderer, inline-emphasis]

# Tech tracking
tech-stack:
  added: []
  patterns:
    - "Hand-written state-machine markdown parser (no external library) — split("\\n"), drop trailing empty, look-ahead dispatch loop"
    - "Module-level compiled regexes for block detection (cheap, keeps dispatch readable)"
    - "Two-channel renderer: text via text_output_fn (composes with WordWrapper), style via style_output_fn (Plan 23-03 wires bold/italic ESC bytes)"
    - "Eager table rendering via two-line look-ahead (header line + |---|---| delimiter); keeps the parser stateless across the table boundary"
    - "_render_inline as a single-method seam replaceable in one place (Plan 23-03 swap point)"

key-files:
  created:
    - src/claude_teletype/markdown.py
    - tests/test_markdown.py
  modified: []

key-decisions:
  - "Trailing empty line from split(\"\\n\") is dropped at render() entry. A document ending with \"\\n\" splits to [..., \"\"]; the trailing newline is structural delimitation, not a blank-line paragraph. Without the drop, \"# Hello\\n\" would emit \"\\nHello\\n\\n\\n\" (extra trailing newline) instead of the plan-spec \"\\nHello\\n\\n\". Discovered while writing Task 2's hand-checkable expected strings — caught by the plan's TDD red-then-fix instructions."
  - "Tables render eagerly in render() via 2-line look-ahead (header `|` + delimiter `|---|`). The plan's <action> block listed two options (look-ahead vs. flush-time validation); look-ahead is clearer and keeps `_dispatch_block_line` free of table state. `_flush_table` is kept as a no-op stub for a future streaming-mode renderer that can't peek."
  - "Code-block 4-space leading indent is intentionally NOT preserved through WordWrapper. WordWrapper's canonical leading-space-at-column-0 rule (test_leading_space_dropped) strips them. This is a known nuance in the MD-07 contract — code-block CONTENT survives, but the 4-space visual indent is lost after wrap. List bullets (`* `) and blockquote prefix (`> `) survive because their leading char is non-space."
  - "_render_inline is a separate method that emits each char verbatim through text_output_fn. This is the single seam Plan 23-03 will replace with a bold/italic/underline state machine. Keeping it as a one-line stub now means 23-03 swaps just the method body and inherits all of 23-02's per-block call sites (heading text, list content, paragraph, blockquote)."
  - "Style channel (style_output_fn) defaults to a no-op lambda when None is passed. Lets the renderer be unit-tested without a profile/driver — every test in TestHeadings/TestLists/etc instantiates the renderer with text_output_fn only. The MD-08 negative test exercises the style channel explicitly to assert no newline ever leaks into it."
  - "Table column-width formula: usable = self._columns - (3*col_count + 1); base = usable // col_count; extra = usable % col_count. Distributes the leftover modulo evenly to the first `extra` columns. Cells wider than allocated width are clipped via cell[:w] (no in-cell wrapping in v1, per CONTEXT.md deferred-ideas)."

patterns-established:
  - "Per-character emission via _emit_text(text) → loops chars through text_output_fn. Even though most block renderers have the entire string in hand, per-char streaming preserves the contract WordWrapper expects downstream."
  - "ATX heading regex `r'^(#{1,6})\\s+(.*?)\\s*#*\\s*$'` doubles as the heading-vs-paragraph gate: `####### Seven` matches NO heading regex (7 hashes is too many) and falls through to paragraph; `###no-space` similarly fails on the missing `\\s+` and renders as paragraph."

requirements-completed: [MD-02, MD-03, MD-04, MD-05, MD-06, MD-07, MD-08]

# Metrics
duration: 5.1min
completed: 2026-04-28
---

# Phase 23 Plan 02: MarkdownRenderer Block-Level Parsing Summary

**Hand-written streaming markdown renderer landing block-level parsing (headings, lists, code, blockquotes, GFM tables) on a dual-channel text/style API, with a `_render_inline` seam ready for Plan 23-03 to replace with bold/italic state machine.**

## Performance

- **Duration:** 5.1 min
- **Started:** 2026-04-28T20:44:51Z
- **Completed:** 2026-04-28T20:50:00Z (approx)
- **Tasks:** 2 (1 implementation + 1 test, with 1 inline Rule-1 fix landed between them)
- **Files created:** 2

## Accomplishments

### Public API (`MarkdownRenderer` in `src/claude_teletype/markdown.py`)

```python
class MarkdownRenderer:
    def __init__(
        self,
        text_output_fn: Callable[[str], None],
        style_output_fn: Callable[[bytes], None] | None = None,
        profile: PrinterProfile | None = None,
        columns: int = 80,
    ) -> None: ...

    def render(self, text: str) -> None: ...
```

- **`text_output_fn`** — required; receives every plain character INCLUDING newlines. Caller wires `WordWrapper.feed` here.
- **`style_output_fn`** — optional; defaults to a no-op. Plan 23-03 will route bold/italic/underline ESC bytes through it. Wired to `ProfilePrinterDriver.write_bytes` in production (the seam Plan 23-01 added).
- **`profile`** — optional `PrinterProfile`. When provided and `profile.columns` is non-zero, it wins over the explicit `columns` argument. Plan 23-03 will additionally pass it to `resolve_style` for inline emphasis lookup.
- **`columns`** — line width used for ASCII table layout; defaults to 80.

### Block-detection state machine

`render()` splits text on `\n`, drops the structural trailing empty element, then iterates with a look-ahead loop:

| Pattern (line `i`) | Routes to | Notes |
|---|---|---|
| Inside `_in_code_block` | `_handle_code_line` | Closing fence resets state; otherwise emits `"    " + line + "\n"` (no inline emphasis) |
| `^```\s*\S*\s*$` | enter code mode | Optional language tag stripped |
| `\|` in line AND `_TABLE_DELIM.match(lines[i+1])` | `_render_table` (eager, multi-row) | Buffers contiguous rows containing `\|`, renders ASCII grid |
| `^(#{1,6})\s+(.*?)\s*#*\s*$` | `_render_heading` | Strips trailing `#`s; emits `\n{text}\n\n` |
| `^>\s?(.*)$` | `_render_blockquote_line` | Emits `> {content}\n` (canonical space normalisation) |
| `^(\s*)(\d+)\.\s+(.*)$` | `_render_olist_item` | Indent = `len(spaces)//2`, preserves source number |
| `^(\s*)([-*+])\s+(.*)$` | `_render_ulist_item` | Indent = `len(spaces)//2`, glyphs to `*` |
| (default) | `_render_paragraph_line` | Blank line passes through as `\n`; non-blank emits `{content}\n` |

### `_render_inline` seam (Plan 23-03 swap point)

```python
def _render_inline(self, text: str) -> None:
    """Stub for Plan 23-03 inline emphasis (bold/italic/underline)."""
    self._emit_text(text)
```

Called from `_render_heading`, `_render_ulist_item`, `_render_olist_item`, `_render_blockquote_line`, and `_render_paragraph_line` (5 call sites). Plan 23-03 replaces the body with a state machine that recognises `**bold**`, `__bold__`, `*italic*`, `_italic_` and emits `resolve_style(profile, ...)` ESC bytes via `self._style_output_fn` while keeping plain chars on `self._text_output_fn`. The stub-replacement seam is intentionally narrow so 23-03 doesn't need to touch any per-block dispatch code.

`_handle_code_line` deliberately does NOT call `_render_inline` (MD-04 contract: literal pass-through inside code fences).

### Test coverage (`tests/test_markdown.py` — 22 tests, all green)

| Class | Requirement | Tests |
|---|---|---|
| `TestHeadings` | MD-02 | 5 (h1, h6, trailing-#, no-space, 7-hashes-degrade) |
| `TestLists` | MD-03 | 5 (dash, asterisk, plus, nested 2-space, ordered) |
| `TestCodeBlocks` | MD-04 | 4 (indent, emphasis pass-through, lang tag, multiline) |
| `TestBlockquotes` | MD-05 | 2 (with-space, canonical normalisation) |
| `TestTables` | MD-06 | 2 (2-col grid, narrow-column truncation) |
| `TestWordWrapperComposition` | MD-07 | 2 (full-document integration through real `WordWrapper(80)`; long-paragraph wrap-at-word-boundary at width 20) |
| `TestNewlineRouting` | MD-08 | 2 (text channel receives `\n`; style channel NEVER receives `b'\n'`) |

The MD-07 integration test instantiates a real `WordWrapper(80, collected.append)` and passes `wrapper.feed` as `text_output_fn`. After rendering a complete sample (heading + paragraph + list + blockquote + code), `wrapper.flush()` runs and the joined output is asserted to contain the structural elements AND no line exceeds 80 chars (WordWrapper enforced). The MD-08 negative test asserts `not any(b'\n' in chunk for chunk in style_calls)` — the style channel never sees a newline byte.

### MD-08 contract preservation

- Every newline emitted by `_render_heading`, `_render_*_item`, `_render_blockquote_line`, `_handle_code_line`, `_render_paragraph_line`, and `_render_table` flows through `_emit_text("\n")` → `self._text_output_fn("\n")`.
- The renderer NEVER passes `b"\n"` to `style_output_fn`. Verified by `test_renderer_never_emits_newline_through_style_channel`.
- This preserves the Plan 23-01 boundary: newlines must reach `ProfilePrinterDriver.write("\n")` for the atomic CR+LF + reinit transfer.

### Style-symmetry safety (deferred to 23-03 with a guarantee)

Even though this plan's `_render_inline` is a stub that emits no style bytes, the block boundaries are designed so 23-03 can safely add `style_on`/`style_off` pairs without leaking state across blocks: each block-level renderer (`_render_heading`, `_render_*_item`, `_render_blockquote_line`, `_render_paragraph_line`) is responsible for emitting both halves of any style pair within its own call. There is no shared mutable style state that survives between calls.

## Task Commits

Each task was committed atomically (with one extra Rule-1 fix commit landed between Task 1 and Task 2):

1. **Task 1: Create MarkdownRenderer skeleton with block parser dispatch and per-block render methods** — `46075c1` (feat)
2. **Inline Rule-1 fix: drop trailing empty line from split("\n")** — `bf4b481` (fix)
3. **Task 2: Per-feature tests for MD-02..MD-08 plus WordWrapper integration test** — `0da9a2a` (test)

## Files Created/Modified

- **`src/claude_teletype/markdown.py`** (created, 305 LOC) — `MarkdownRenderer` class with 11 methods (`render`, `_dispatch_block_line`, `_render_heading`, `_render_ulist_item`, `_render_olist_item`, `_render_blockquote_line`, `_handle_code_line`, `_render_paragraph_line`, `_render_inline`, `_render_table`, `_flush_table`, `_emit_text`) + 6 module-level compiled regexes.
- **`tests/test_markdown.py`** (created, 201 LOC) — 7 test classes, 22 test methods, all green.

## Decisions Made

See frontmatter `key-decisions`. Highlights:

- **Trailing-newline drop** at `render()` entry to align with the plan's hand-checkable expected strings (`# Hello\n` → `\nHello\n\n`, not `\nHello\n\n\n`).
- **Eager table rendering** with 2-line look-ahead — clearer than the alternative flush-time validation.
- **Code-block 4-space indent NOT preserved through WordWrapper** — known nuance, content survives but visual indent is stripped by WordWrapper's leading-space-at-column-0 rule (canonical existing behaviour, not a regression). List bullets and blockquote prefixes survive because their leading char is non-space.
- **`_render_inline` as a single-method seam** — keeps Plan 23-03's surface minimal (one method body to swap, 5 call sites stay untouched).

## Deviations from Plan

### Auto-fixed Issues

**1. [Rule 1 - Bug] Trailing empty line from split("\n") created spurious extra newline**

- **Found during:** Task 2 (writing expected-output strings)
- **Issue:** A document ending with `\n` (e.g. `# Hello\n`) splits to `["# Hello", ""]`. The empty trailing element fell through to `_render_paragraph_line` which emits `\n` for blank lines, producing `\nHello\n\n\n` instead of the plan-spec `\nHello\n\n`. The plan's `<action>` block specified `lines = text.split("\n")` without addressing the trailing empty.
- **Fix:** Drop the trailing empty element at `render()` entry: `if lines and lines[-1] == "": lines.pop()`. Documents ending with `\n` are common (POSIX convention) and that trailing newline is structural delimitation, not a blank paragraph. Multi-newline endings (`...\n\n`) still preserve the inner blank line as a paragraph break.
- **Files modified:** `src/claude_teletype/markdown.py`
- **Commit:** `bf4b481`

### Deviations from planned tests

**2. [Doc-only] MD-07 integration test does NOT assert `"    code line" in out`**

- The plan's `<behavior>` block listed `assert "    code line" in out` as one of the expected substrings.
- Reality: WordWrapper's canonical `test_leading_space_dropped` (in `tests/test_wordwrap.py::TestLeadingSpaceIgnored`) strips leading spaces at column 0. The renderer's `"    code line\n"` emission becomes `code line\n` after wrap.
- The test asserts `assert "code line" in out` instead, with an inline comment explaining the WordWrapper interaction. Code-block content survives (MD-04 contract met); the visual 4-space indent is lost in the wrap stage — a documented MD-07 nuance, not a renderer bug.
- This is NOT a Rule-1 fix because changing WordWrapper to preserve leading spaces would break its canonical contract (`test_leading_space_dropped`). The right place to address visible code-block indent in printed output is downstream (e.g. in a future renderer-aware formatter that emits a non-space leading char or uses tab handling).

**3. [Bonus coverage] Added one extra test (`test_code_block_multiline_indents_each_line`) and one extra MD-07 test (`test_long_paragraph_wraps_at_word_boundary`)**

- The plan's stated minimum was 18-20 tests. The file lands 22 tests. The two extras cover (a) multi-line code-block bodies and (b) WordWrapper's actual word-boundary wrap behaviour at narrow widths — both directly relevant to MD-04 and MD-07 contracts.

## Issues Encountered

None outside of the trailing-newline deviation noted above. The plan's per-task `<verify>` automation commands (`uv run ruff check ...` and `uv run python -c "..."` smoke test) passed first run after each task. Full project suite (588 tests) green.

## TDD Gate Compliance

The two tasks landed implementation-first then tests (Task 1 = `feat`, Task 2 = `test`), with a `fix` between them after the trailing-newline deviation surfaced during test authoring. The plan's own `<action>` block notes:

> "this is a single plan with two tasks (Task 1 implementation, Task 2 tests). Both can be committed together as the renderer and tests co-evolve — the contract IS the test set... The plan executor can either: (a) implement Task 1 first then write Task 2 (then iterate), or (b) write Task 2 tests first as RED, then implement Task 1 to GREEN them. Either order works; per-task atomic commits are the goal."

Order (a) was used. Three atomic commits, each green at HEAD:

- `46075c1` (feat) — initial implementation; smoke test passes
- `bf4b481` (fix) — trailing-newline correction; hand-checked expected strings now match
- `0da9a2a` (test) — 22 tests, all green at landing

## User Setup Required

None — pure-Python module with no I/O, no external dependencies, no configuration.

## Next Phase Readiness

**Ready for Plan 23-03 (Inline emphasis: bold + italic + underline with profile-aware style resolution).**

The seams 23-03 needs are all in place:

- `_render_inline(self, text: str) -> None` — single method to replace with the emphasis state machine. 5 call sites (heading, ulist, olist, blockquote, paragraph) inherit the swap automatically. `_handle_code_line` deliberately bypasses `_render_inline`, satisfying MD-04's "no emphasis processing inside code blocks".
- `self._style_output_fn` — `Callable[[bytes], None]` already wired into `__init__`; defaults to no-op so existing block tests continue to pass without change. 23-03 calls it directly for `style_on` / `style_off` byte pairs.
- `self._profile: PrinterProfile | None` — already stored; 23-03 passes it to `resolve_style(self._profile, "bold")` / `"italic"` / `"underline"`.
- MD-08 enforced: `_render_inline` will need to keep newlines on the text channel even when emphasis spans wrap points. The existing test `test_renderer_never_emits_newline_through_style_channel` will catch any regression.

**No blockers carried forward to 23-03.** The Phase 23 carry-forward concern in STATE.md ("ASCII table layout under narrow `profile.columns`") is satisfied by `test_table_fits_within_columns` — even at columns=30 with 100-char-wide cells, every line fits within columns.

## Self-Check: PASSED

- src/claude_teletype/markdown.py: FOUND
- tests/test_markdown.py: FOUND
- Commit 46075c1: FOUND in git log
- Commit bf4b481: FOUND in git log
- Commit 0da9a2a: FOUND in git log
- `grep -c '_render_inline' src/claude_teletype/markdown.py` returns 8 (1 def + 5 call sites + 2 docstring mentions; >= 5 plan-min)
- `grep -c 'def test_' tests/test_markdown.py` returns 22 (matches the test count exactly)
- `grep -c 'WordWrapper(80' tests/test_markdown.py` returns 2 (integration test instantiates the real wrapper)
- `wc -l` on the two files: 305 LOC markdown.py (>= 250 plan-min); 201 LOC test_markdown.py (>= 200 plan-min)
- `uv run pytest tests/test_markdown.py -v` returns 22/22 green
- `uv run pytest -x` returns 588/588 green (566 baseline + 22 new)
- `uv run ruff check src/claude_teletype/markdown.py tests/test_markdown.py` clean

---
*Phase: 23-streaming-markdown-renderer*
*Completed: 2026-04-28*
