# Phase 23: Streaming Markdown Renderer - Context

**Gathered:** 2026-04-28
**Status:** Ready for planning
**Mode:** Auto-generated (autonomous run, skip_discuss=true)

<domain>
## Phase Boundary

A streaming renderer turns markdown text into a sequence of `(plain_char, optional_style_bytes)` events that compose with the existing `WordWrapper` and `ProfilePrinterDriver` newline pattern — so wrapped lines preserve list indentation, blockquote prefixes, and the atomic CR+LF + reinit transfer.

Covers requirements MD-01 through MD-08 (see REQUIREMENTS.md).

</domain>

<decisions>
## Implementation Decisions

### Architecture: separate channels for text and style bytes

The renderer must NOT try to send ESC byte sequences through `WordWrapper` or `pacer.py` — those operate on user-visible characters, while ESC sequences are control codes that must be transmitted atomically and bypass per-character pacing.

The recommended approach:

1. **New module** `src/claude_teletype/markdown.py` (suggested name) — implements a `MarkdownRenderer` class with a `render(text: str) -> None` method.

2. **Two output callbacks** passed to the renderer at construction:
   - `text_output_fn: Callable[[str], None]` — for plain characters; consumed by the existing pacer + WordWrapper pipeline
   - `style_output_fn: Callable[[bytes], None]` — for ESC style sequences; sent directly to the printer driver

3. **Profile-aware style resolution.** The renderer is given a `PrinterProfile` (or equivalent capabilities source) and uses `resolve_style(profile, style)` from Phase 21 to pick the correct on/off bytes for bold/italic/underline at each markdown emphasis token. When `resolve_style` returns `(b"", b"")`, the renderer skips the style emit and the text falls back to plain.

4. **No new public method on ProfilePrinterDriver.** A new `write_bytes(data: bytes)` public method on `ProfilePrinterDriver` is the cleanest way for `style_output_fn` to send raw ESC sequences atomically (it would internally call `_send_raw`). Adding this is in scope for this phase. Update the `PrinterDriver` Protocol accordingly so all driver classes satisfy it (Null, File, Cups, Usb, Profile).

### Markdown features supported (MD-01 .. MD-08)

- **MD-01 Bold + Italic emphasis** (`**bold**`, `__bold__`, `*italic*`, `_italic_`). Implementation: regex/state-machine recognition; emit `style_on` bytes before the run, plain chars during, `style_off` bytes after. Nested emphasis is allowed.
- **MD-02 ATX headings** (`#` … `######`). Render as bold text + extra blank line before AND after the heading. NOT changing font size (impact printers are fixed-size). Strip trailing `#` chars.
- **MD-03 Lists.** Unordered (`-`, `*`, `+`) → `* ` glyph prefix. Ordered (`1.`, `2.`) → `1. ` style numeric prefix preserved as-is. Nested list indent levels = two spaces per level. Nesting tracked via leading whitespace in the source.
- **MD-04 Fenced code blocks** (```` ``` ````). Indent each line by 4 spaces; do NOT process inline emphasis inside the block; do NOT word-wrap (passing through `WordWrapper.feed("\n")` is fine — long code lines are allowed to exceed `profile.columns`). Optional language tag after the opening fence is ignored.
- **MD-05 Blockquotes** (`>` prefix per line). Emit `> ` as a literal prefix at the start of each wrapped output line within the block. Multi-line blockquotes share the prefix.
- **MD-06 GitHub-flavored tables.** Detect by `|` separators with a delimiter row (`|---|---|`). Compute column widths so the table fits within `profile.columns`. Render as ASCII grid using `+`, `-`, `|` characters. Cells wider than allocated column width are truncated (single-line cells only, no in-cell wrapping).
- **MD-07 Composes with WordWrapper.** When wrapping happens mid-line, the prefix (list marker, blockquote `>`, code-block 4-space indent) must be emitted at the start of the next line. Preserve trailing-space-on-wrap behavior (no trailing whitespace on wrapped lines, matching existing WordWrapper deferred-space pattern).
- **MD-08 CR+LF + reinit pattern preserved.** All newline emissions go through `text_output_fn("\n")` → eventually reaches `ProfilePrinterDriver.write("\n")` which already does the atomic CR+LF + reinit transfer. The renderer must NEVER bypass that path for newlines (no direct `style_output_fn(b"\n")`).

### Design constraints

- **Streaming, not batched** — the renderer must be able to start emitting output before the full markdown text is parsed. For a single file this matters less, but the streaming shape composes naturally with the existing pipeline (pacer is a streaming consumer).
- **Style symmetry safety** — the renderer must emit a matching style_off for every style_on it emits. If parsing detects unclosed emphasis at end of document (e.g. `**hello`), close the open style anyway (defensive — prevents leaking bold mode into the next print job).
- **No external dependency** — implement the markdown parser inline rather than pulling in `markdown-it`, `mistune`, etc. The supported feature set is small and deterministic; a hand-written state machine is roughly 200-400 LOC and avoids dependency churn.
- **Pure Python, no I/O** — the renderer doesn't open files; the caller (Phase 24 picker / Phase 25 CLI subcommand) reads the file and passes the text. Keeps the renderer testable without filesystem fixtures.

### Test strategy

Add `tests/test_markdown.py`:
- Per-feature tests for each MD-01..MD-08 requirement
- Capability-fallback tests: when profile.italic_on is empty, italic markdown still renders (as underline if available, else plain)
- Integration test: render a complex markdown document with mixed features (heading + list + bold + table) through real `WordWrapper` and capture output
- Edge cases: unclosed emphasis, empty fenced code block, table with too few columns, nested lists, blockquote inside list

### Plan layout

Three plans is reasonable:
- **23-01 (Wave 1):** Add `write_bytes` to PrinterDriver protocol and all driver implementations. Foundation for the renderer's style channel.
- **23-02 (Wave 2, depends on 23-01):** Implement `MarkdownRenderer` core — block-level parsing (headings, lists, code, blockquote, table), line-level streaming through `text_output_fn`, with a stub style channel.
- **23-03 (Wave 3, depends on 23-02):** Add inline emphasis parsing (bold + italic) with profile-aware style resolution via `resolve_style`. Tests for each fallback chain scenario.

### Claude's Discretion

- Internal API of `MarkdownRenderer` (one `render(text)` method vs streaming `feed(line)` per line)
- Exact regex / state-machine details
- Whether tables share rendering code with regular block parsing or have a dedicated path
- Whether to expose `write_bytes` as a method on `PrinterDriver` Protocol or keep it private and have the renderer access via a separate adapter

</decisions>

<canonical_refs>
## Canonical References

**Downstream agents MUST read these before planning or implementing.**

### Project files
- `src/claude_teletype/wordwrap.py` — WordWrapper class; the renderer's text channel feeds into this
- `src/claude_teletype/printer.py` — `PrinterDriver` Protocol (line 17), `ProfilePrinterDriver` (line 194), `_send_raw` (line 211); renderer adds `write_bytes` public method
- `src/claude_teletype/profiles.py` — `resolve_style` helper (Phase 21); profile capability fields
- `src/claude_teletype/output.py` — output multiplexer (existing pattern for fan-out)
- `src/claude_teletype/pacer.py` — character pacer; renderer must compose with this for typewriter mode (Phase 26 ties them together)
- `tests/test_wordwrap.py` — test patterns to mirror for streaming-style assertions
- `tests/test_printer.py` — tests for ProfilePrinterDriver to extend with `write_bytes` coverage
- `.planning/REQUIREMENTS.md` — MD-01 through MD-08 definitions
- `.planning/PROJECT.md` — frozen-dataclass decision, CR+LF atomic transfer decision (must not violate)
- `.planning/phases/21-profile-capability-fields-custom-toml-support/21-03-SUMMARY.md` — `resolve_style` import contract: `from claude_teletype.profiles import resolve_style`
- `.planning/phases/22-encoded-style-sequences-for-built-in-profiles/22-01-SUMMARY.md` — what bytes are encoded per profile (renderer's expected input)

</canonical_refs>

<specifics>
## Specific Ideas

- The renderer's tests should cover one full integration: a sample markdown document with heading + paragraph + bold + italic + list + code + blockquote + table, rendered through real `WordWrapper` (column width 80) into a list-collector output_fn, then asserted against a hand-written expected output. This is the user-acceptance test for MD-01..MD-08 working together.
- The `style_output_fn` parameter should be optional (default no-op) so the renderer can be tested without a profile. When present, it's wired to `ProfilePrinterDriver.write_bytes` in production.
- For tables, prefer `tabulate`-style ASCII grids (each row separated by horizontal rule) — same shape regardless of cell content.

</specifics>

<deferred>
## Deferred Ideas

- **Inline links** (footnote references at end of document) — CAP-07, Future Requirements section in REQUIREMENTS.md.
- **Task lists** (`- [ ]` / `- [x]`) — CAP-08, Future Requirements.
- **Multi-page formatting** (page numbers, headers, footers) — FMT-01, Future Requirements.
- **Print preview screen** — PREV-01, deferred to a later milestone.
- **In-cell wrapping for tables** — too complex for v1.5; truncation is acceptable.
- **CommonMark / GFM full compliance** — only the subset listed in MD-01..MD-08 is supported.

</deferred>

---

*Phase: 23-streaming-markdown-renderer*
*Context auto-generated 2026-04-28 (autonomous run, skip_discuss=true)*
