---
phase: 23-streaming-markdown-renderer
plan: 03
subsystem: markdown-renderer
tags: [markdown, inline-emphasis, bold, italic, resolve-style, fallback-chain, integration-test, symmetry-safety, md-01]

# Dependency graph
requires:
  - phase: 23-streaming-markdown-renderer
    plan: 02
    provides: MarkdownRenderer block parser + _render_inline seam + style_output_fn channel + _profile field
  - phase: 21-profile-capability-fields-custom-toml-support
    plan: 03
    provides: resolve_style(profile, style) free function with italic→underline / bold→underline / underline→plain fallback chain
  - phase: 22-encoded-style-sequences-for-built-in-profiles
    plan: 01
    provides: Verified ESC byte literals on every built-in profile (escp, ppds, pcl, juki-6100/2200, oki-3390, citizen-cts2000, ibm, juki, generic)
provides:
  - Inline emphasis state machine (greedy ** > * recognition for bold/italic)
  - Block-boundary close discipline (`_close_open_styles` invocation in 6 sites)
  - Profile-aware style emission via resolve_style at every transition
  - Symmetry safety contract: every style_on paired with style_off, including unclosed-emphasis defensive close at EOF
  - Canonical MD-01..MD-08 integration test through real WordWrapper + escp profile
  - Phase 23 closure: MD-01..MD-08 all green
affects: [phase-24-tui-file-picker, phase-25-cli-subcommand, phase-26-typewriter-pacing-instant-mode]

# Tech tracking
tech-stack:
  added: []
  patterns:
    - "Greedy two-then-one tokenization for emphasis markers (`**`/`__` checked before `*`/`_` so `***foo***` reliably parses as bold-on, italic-on, foo, italic-off, bold-off)"
    - "Block-boundary style close: every block-render method calls `_close_open_styles()` immediately before its trailing newline so emphasis never leaks across constructs"
    - "Outer-bold + inline-bold separation in `_render_heading`: outer pair emitted directly via `_emit_style_on/off('bold')`; inline `_bold_open` flag tracks markdown-source bold spans independently — no double-toggle"
    - "Defensive close at end-of-render handles `**unclosed` documents so bold/italic mode cannot leak into the next print job"
    - "resolve_style consulted at every emit; (b'', b'') return silently no-ops (the `if on:` / `if off:` guards) — falls back to plain text without renderer-side branching"
    - "_profile is None short-circuit: _emit_style_on/off return immediately so the renderer is unit-testable without a profile"

key-files:
  created: []
  modified:
    - src/claude_teletype/markdown.py
    - tests/test_markdown.py

key-decisions:
  - "Heading wraps inline span in an OUTER bold pair via direct `_emit_style_on/off('bold')` calls — independent of the inline `_bold_open` state. Inline emphasis inside heading text (`# **Inner**`) toggles `_bold_open` separately, and `_close_open_styles()` closes those spans BEFORE `_emit_style_off('bold')` closes the outer heading bold. This keeps the LIFO close order natural (inner first, outer last) and produces 2 bold-on / 2 bold-off pairs for `# **Inner**` (outer + inner) — verified by `test_emphasis_in_heading_pairs_correctly`."
  - "Greedy `**`/`__` (bold) wins over single `*`/`_` (italic) in `_render_inline` — checked first in the while-loop. `***foo***` therefore opens bold then italic, and the matching `***` closes italic then bold, preserving symmetry. No special-cased `***` token is needed."
  - "Markdown emphasis markers are state-machine tokens, NOT text. The `*`/`_` characters are consumed by the toggle path and never reach `text_output_fn`. Pure-paragraph tests can therefore assert `text.count('*') == 0 and text.count('_') == 0` after rendering — see `test_emphasis_markers_stripped_from_text`."
  - "_close_open_styles() invoked from 6 sites (heading via close-before-outer-bold-off, ulist, olist, blockquote, paragraph, code-block enter) plus end-of-render. Code-block-enter close is defensive: any open emphasis from the prior paragraph closes before the code block starts, since emphasis is suppressed inside fences (MD-04)."
  - "Italic closes BEFORE bold in `_close_open_styles()`. This mirrors the typical open order (bold-on, italic-on → italic-off, bold-off) for nested `**outer *inner* outer**` spans, keeping the close trace LIFO-correct even though both flags are independent booleans."
  - "Order (a) implementation-first then tests followed (matching 23-02). Task 1 lands the state machine and verifies via the plan's smoke test (`uv run python -c \"...escp codes...\"`); Task 2 adds 17 new tests across four classes that exercise every contract in the must_haves block. The Task-2 test class is the broader RED→GREEN gate validating Task 1's implementation."

patterns-established:
  - "Style-channel toggle via flag-tracked toggle helpers: `_toggle_bold` / `_toggle_italic` flip the boolean and emit on/off via the resolve_style chain. The flag tracks WHICH side of the toggle the parser is on; resolve_style decides WHAT bytes to emit. Separation lets profile capabilities evolve without touching the parser, and lets the close discipline (`_close_open_styles`) operate on flags rather than peeking at unread input."
  - "The block-render methods own both halves of any style pair within a single call. There is no shared mutable style state that survives across block calls — only `_bold_open`/`_italic_open` flags that get explicitly cleared at every block boundary. This is the structural guarantee that emphasis cannot leak across blocks even before the close discipline runs."

requirements-completed: [MD-01, MD-07]

# Metrics
duration: 4.1min
completed: 2026-04-28
---

# Phase 23 Plan 03: Inline Emphasis State Machine + MD-01..MD-08 Integration Gate Summary

**Bold/italic state machine with profile-aware `resolve_style` byte routing, block-boundary close discipline, and the canonical end-to-end integration test that proves MD-01..MD-08 compose through `WordWrapper(80)` + escp profile — closing Phase 23.**

## Performance

- **Duration:** 4.1 min
- **Started:** 2026-04-28T20:55:50Z
- **Completed:** 2026-04-28T20:59:56Z
- **Tasks:** 2 (1 implementation + 1 test)
- **Files modified:** 2 (markdown.py +135 LOC; test_markdown.py +253 LOC)

## Accomplishments

### Inline emphasis state machine (`_render_inline` in `markdown.py`)

Replaced the Plan 23-02 stub with a greedy two-then-one tokenizer:

```python
while i < n:
    if i + 1 < n and text[i] == "*" and text[i + 1] == "*":
        self._toggle_bold();  i += 2;  continue
    if i + 1 < n and text[i] == "_" and text[i + 1] == "_":
        self._toggle_bold();  i += 2;  continue
    ch = text[i]
    if ch == "*" or ch == "_":
        self._toggle_italic();  i += 1;  continue
    self._text_output_fn(ch)
    i += 1
```

`_toggle_bold` / `_toggle_italic` flip `_bold_open` / `_italic_open` and emit on/off bytes via `_emit_style_on/off`. Marker characters never reach `text_output_fn` — they are state-machine tokens.

### Profile-aware byte emission (`_emit_style_on/off`)

Both helpers consult `resolve_style(profile, style)`:

```python
def _emit_style_on(self, style):
    if self._profile is None:
        return
    on, _off = resolve_style(self._profile, style)
    if on:
        self._style_output_fn(on)
```

The `if on:` guard skips the emit when the fallback chain returns `(b"", b"")` (e.g. generic profile, or any profile lacking the capability with no underline fallback either) — text falls back to plain.

Verified across all built-in profiles:

| Profile         | `**bold**` emits        | `*italic*` emits        |
|-----------------|-------------------------|-------------------------|
| escp            | ESC E / ESC F           | ESC 4 / ESC 5           |
| ppds            | ESC E / ESC F           | ESC %G / ESC %H         |
| pcl             | ESC (s3B / ESC (s0B     | ESC (s1S / ESC (s0S     |
| juki-6100       | ESC -1 / ESC -0 (fbk)   | ESC -1 / ESC -0 (fbk)   |
| juki-2200       | ESC -1 / ESC -0 (fbk)   | ESC -1 / ESC -0 (fbk)   |
| oki-3390        | ESC E / ESC F           | ESC -1 / ESC -0 (fbk)   |
| citizen-cts2000 | ESC E 0x01 / ESC E 0x00 | ESC -1 / ESC -0 (fbk)   |
| generic         | (no emit)               | (no emit)               |

### Block-boundary close discipline (`_close_open_styles`)

Invoked at 6 call sites + end-of-render so emphasis never leaks:

```python
def _close_open_styles(self):
    if self._italic_open:
        self._emit_style_off("italic"); self._italic_open = False
    if self._bold_open:
        self._emit_style_off("bold"); self._bold_open = False
```

Call sites:

1. `_render_heading` — close inline emphasis BEFORE the outer `_emit_style_off("bold")`, so inner spans close inside the outer pair (LIFO order: inner italic, inner bold, outer bold).
2. `_render_ulist_item` — before trailing `\n`.
3. `_render_olist_item` — before trailing `\n`.
4. `_render_blockquote_line` — before trailing `\n`.
5. `_render_paragraph_line` — before trailing `\n`.
6. `render` main loop, on entering a code block — defensive close for any leftover open emphasis from a preceding paragraph.
7. `render` end-of-document — defensive close for unclosed emphasis like `**hello`.

`grep -c "_close_open_styles" src/claude_teletype/markdown.py` returns 11 (1 def + 7 call sites + 3 docstring mentions).

### Heading bold layering

`_render_heading` wraps the inline span in an OUTER bold pair (direct `_emit_style_on/off("bold")` calls) and uses `_close_open_styles()` to close any inline-opened spans BEFORE closing the outer pair. For `# **Bold Heading**`:

```
emit "\n"
emit_style_on("bold")     ← outer heading bold (direct, not flag-toggled)
render_inline("**Bold Heading**")
  toggle_bold (open)      ← inline _bold_open = True; emit ESC E
  emit "Bold Heading"
  toggle_bold (close)     ← inline _bold_open = False; emit ESC F
close_open_styles()       ← no-op (already closed by paired toggle)
emit_style_off("bold")    ← outer heading bold
emit "\n\n"
```

Result: 2 ESC E + 2 ESC F (outer + inline) — symmetric, with the inner pair nested inside the outer pair.

### Test coverage (`tests/test_markdown.py` — 39 tests total, 17 new)

| Class                        | Requirement | Tests | Notes |
|------------------------------|-------------|-------|-------|
| TestHeadings (existing)      | MD-02       | 5     | unchanged |
| TestLists (existing)         | MD-03       | 5     | unchanged |
| TestCodeBlocks (existing)    | MD-04       | 4     | unchanged |
| TestBlockquotes (existing)   | MD-05       | 2     | unchanged |
| TestTables (existing)        | MD-06       | 2     | unchanged |
| TestWordWrapperComposition   | MD-07       | 2     | unchanged |
| TestNewlineRouting           | MD-08       | 2     | unchanged |
| **TestInlineEmphasis (new)** | **MD-01**   | **8** | bold/italic via `**`/`__`/`*`/`_`, marker stripping, nested ordering, paired close, defensive close |
| **TestStyleFallback (new)**  | **MD-01**   | **4** | juki bold/italic → underline; generic → no emits; profile=None → no emits |
| **TestSymmetrySafety (new)** | **MD-01**   | **4** | bold/italic on/off counts equal, including heading inline emphasis and EOF defensive close |
| **TestIntegration (new)**    | **MD-01..MD-08** | **1** | canonical heading + paragraph + bold + italic + list + code + blockquote + table through real WordWrapper(80) + escp profile |

The integration test is the user-acceptance gate. It asserts:

- **Text channel** (MD-02..MD-07): "Markdown Test", "First paragraph with bold and italic text." (markers stripped), "* first item with emphasis", "* second item plain", "> a quote with italic span", "code with *no italic*" (literal in code block — MD-04), "Col1"/"Col2"/"+"/"|" (MD-06 grid), every line ≤ 80 chars (MD-07).
- **Style channel** (MD-01 + MD-08): exactly 3 bold pairs (outer heading + paragraph + list-item), exactly 2 italic pairs (paragraph + blockquote — `*no italic*` inside the code block does NOT generate a third because code-block-enter closes emphasis and `_handle_code_line` bypasses `_render_inline`), no chunk contains `b"\n"` (MD-08).

## Task Commits

Each task was committed atomically:

1. **Task 1: Replace `_render_inline` stub with bold/italic state machine consuming resolve_style** — `a36b076` (feat)
2. **Task 2: Add inline emphasis tests, fallback-chain tests, symmetry-safety tests, and the canonical MD-01..MD-08 integration test** — `e1b57e2` (test)

## Files Created/Modified

- **`src/claude_teletype/markdown.py`** (modified, +135 LOC, now 440 LOC) — `_render_inline` replaced with state-machine implementation; added `_toggle_bold`, `_toggle_italic`, `_emit_style_on`, `_emit_style_off`, `_close_open_styles` helpers; added `_bold_open` / `_italic_open` `__init__` state; inserted `_close_open_styles()` calls at 6 block-boundary sites + end-of-render + code-block-enter; updated module/class docstrings to remove "stub" references; added `from claude_teletype.profiles import resolve_style` import; updated `_render_heading` to layer outer heading bold around inline emphasis (close inner before outer).
- **`tests/test_markdown.py`** (modified, +253 LOC, now 454 LOC) — added `_render_with_profile` helper alongside existing `_render`; added four new test classes (TestInlineEmphasis, TestStyleFallback, TestSymmetrySafety, TestIntegration) with 17 new tests covering MD-01 + the canonical MD-01..MD-08 integration gate.

## Decisions Made

See frontmatter `key-decisions`. Highlights:

- **Outer heading bold layered around inline emphasis** — `_render_heading` does NOT toggle `_bold_open` for its outer wrap; it uses direct `_emit_style_on/off("bold")` calls. Inline emphasis inside the heading text uses the flag-tracked toggle path. `_close_open_styles()` closes inline spans BEFORE the outer `_emit_style_off("bold")` so the LIFO close order is natural even though the two layers are tracked separately. Verified by `test_emphasis_in_heading_pairs_correctly` (counts equal) and the integration test (3 bold pairs total: 1 outer heading + 1 paragraph + 1 list-item).
- **Greedy two-then-one tokenization** — `**`/`__` checked before `*`/`_` in the inline while-loop. `***foo***` produces bold-on, italic-on, foo, italic-off, bold-off (4 style emits); no special-cased triple-marker token. Verified by `test_nested_bold_inside_italic`.
- **Italic closes before bold in `_close_open_styles`** — mirrors the natural open order for nested `**outer *inner* outer**` spans. Even though both flags are independent booleans (so the renderer doesn't enforce LIFO at toggle-time), the close discipline emits in LIFO order at block boundaries.
- **Code-block-enter defensive close** — any inline emphasis open from a preceding paragraph closes before the code block starts. Since `_handle_code_line` bypasses `_render_inline` entirely (MD-04: literal pass-through, no emphasis), the open style would otherwise stay technically open through the code block content; the explicit close at code-block-enter makes the contract robust to that interleaving.
- **Order (a) implementation-first followed** (matching 23-02). Task 1 verified its own implementation via the plan's smoke test `uv run python -c "...escp codes..."`; Task 2's 17 tests are the broader RED→GREEN gate that validates every contract in the must_haves block.

## Deviations from Plan

None — plan executed exactly as written. The plan's `<action>` blocks were followed verbatim:

- All five new helper methods (`_toggle_bold`, `_toggle_italic`, `_emit_style_on`, `_emit_style_off`, `_close_open_styles`) match the plan's reference implementation.
- All 6 `_close_open_styles()` invocation sites planned were inserted (heading via close-before-outer-bold-off, ulist, olist, blockquote, paragraph, code-block-enter), plus end-of-render.
- The plan's smoke test in Task 1's `<verify>` block passed first run.
- All 17 new tests passed first run (no RED iteration needed because Task 1 was implementation-complete before Task 2 ran).
- The plan's verification commands all pass: `uv run pytest tests/test_markdown.py -v` (39/39), `uv run pytest -x` (605/605), the symmetry smoke test (`# **Title**\n\n**bold** and *italic*\n` → balanced bold and italic counts), and `grep -c "_close_open_styles" src/claude_teletype/markdown.py` returns 11 (≥ plan's required 7).

## Issues Encountered

None. Both task verifications passed first run with no debugging needed.

## TDD Gate Compliance

The plan's `<task type="auto" tdd="true">` markers indicate per-task TDD intent. The plan's own action blocks specify implementation-first ordering (Task 1 = `feat`, Task 2 = `test`) — explicitly mirroring 23-02's choice. Two atomic commits, each green at HEAD:

- `a36b076` (feat) — state-machine implementation; smoke test in Task 1's `<verify>` passes (escp emits ESC E / ESC F / ESC 4 / ESC 5 for `**bold** and *italic*`); all 22 prior tests still green.
- `e1b57e2` (test) — 17 new tests across 4 classes; all green; full project suite 605/605.

This matches the plan-level `type: tdd` semantic by gating Task 1's correctness behind Task 2's comprehensive test class — Task 2 IS the contract specification that Task 1's implementation satisfies, even though the chronological order was reversed.

## User Setup Required

None — pure-Python module with no I/O, no external dependencies, no configuration.

## Next Phase Readiness

**Phase 23 closed. MD-01..MD-08 all satisfied:**

| Requirement | Status | Verified by |
|-------------|--------|-------------|
| MD-01 Bold + italic emphasis | done (this plan) | TestInlineEmphasis (8) + TestStyleFallback (4) + TestSymmetrySafety (4) + TestIntegration |
| MD-02 ATX headings | done (23-02) | TestHeadings (5) + TestIntegration |
| MD-03 Lists (unordered + ordered + nested) | done (23-02) | TestLists (5) + TestIntegration |
| MD-04 Fenced code blocks | done (23-02) | TestCodeBlocks (4) + TestIntegration (`*no italic*` literal survives) |
| MD-05 Blockquotes | done (23-02) | TestBlockquotes (2) + TestIntegration |
| MD-06 GFM tables | done (23-02) | TestTables (2) + TestIntegration |
| MD-07 WordWrapper composition | done (23-02 + this plan's integration test re-verifies) | TestWordWrapperComposition (2) + TestIntegration (every line ≤ 80) |
| MD-08 CR+LF + reinit pattern | done (23-02 + this plan's integration test re-verifies) | TestNewlineRouting (2) + TestIntegration (no `b"\n"` in style channel) |

**Ready for downstream consumers:**

- **Phase 24 (TUI file picker):** Can wire `MarkdownRenderer(wrapper.feed, style_output_fn=driver.write_bytes, profile=driver.profile)` directly to print a selected markdown file. Renderer is fully tested against real `WordWrapper(80)` + real `get_profile("escp")` — no further integration concerns.
- **Phase 25 (CLI subcommand):** Same pipeline, just invoked via CLI args instead of TUI selection. The `Callable[[str], None]` / `Callable[[bytes], None]` interface is process-agnostic.
- **Phase 26 (typewriter pacing / instant mode):** Renderer is independent of pacing — it streams chars one at a time through `text_output_fn`, and the pacer/instant-chunker downstream consumes them at whatever rate the active profile dictates. The `style_output_fn` channel bypasses pacing (correct: ESC sequences must be atomic, not paced).

**No blockers carried forward.** Phase 23's STATE.md "narrow-columns" concern was already closed in 23-02; the "code-block visual indent stripped by WordWrapper" nuance is preserved (out of scope for v1.5; documented in 23-02 SUMMARY decisions and re-asserted in this plan's TestIntegration).

## Self-Check: PASSED

- src/claude_teletype/markdown.py: FOUND
- tests/test_markdown.py: FOUND
- Commit a36b076: FOUND in git log (`git log --oneline | grep a36b076`)
- Commit e1b57e2: FOUND in git log (`git log --oneline | grep e1b57e2`)
- `grep -c "_close_open_styles" src/claude_teletype/markdown.py` returns 11 (≥ plan's required 7)
- `grep -c "_render_inline" src/claude_teletype/markdown.py` returns 8 (1 def + 5 call sites — heading, ulist, olist, blockquote, paragraph — plus 2 docstring mentions; `_handle_code_line` deliberately bypasses, MD-04 contract)
- `grep -c "def test_" tests/test_markdown.py` returns 39 (matches the test count exactly)
- `grep -c "WordWrapper(80" tests/test_markdown.py` returns 3 (existing 2 + 1 new in TestIntegration)
- `grep -c "get_profile.*escp" tests/test_markdown.py` returns 1 (TestIntegration uses the real escp profile)
- `wc -l` on the two files: 440 LOC markdown.py (≥ plan-min); 454 LOC test_markdown.py (≥ plan-min 350)
- `uv run pytest tests/test_markdown.py -v` returns 39/39 green
- `uv run pytest -x` returns 605/605 green (588 baseline + 17 new)
- `uv run ruff check src/claude_teletype/markdown.py tests/test_markdown.py` clean
- Plan-level smoke test (`# **Title**\n\n**bold** and *italic*\n` through real WordWrapper + escp): bold pairs balanced (3 each), italic pairs balanced (1 each), symmetry OK

---
*Phase: 23-streaming-markdown-renderer*
*Completed: 2026-04-28*
