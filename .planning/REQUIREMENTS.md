# Requirements: Claude Teletype

**Defined:** 2026-04-28
**Core Value:** The physical typewriter experience — characters appearing on paper one at a time with authentic pacing and sound, making AI conversation feel tangible and mechanical.

## v1.5 Requirements

Requirements for the **Markdown File Printing** milestone. Each maps to roadmap phases.

### File Picker (TUI)

- [ ] **PICK-01**: User can open a markdown file picker from the main TUI session via a keybinding
- [ ] **PICK-02**: Picker is rooted at the directory `claude-teletype` was launched from (cwd) and supports navigating into subdirectories and back to parents
- [ ] **PICK-03**: Picker filters visible files to `.md` and `.markdown` extensions; directories are always shown
- [ ] **PICK-04**: User can cancel the picker and return to the chat session without printing anything
- [ ] **PICK-05**: Picker displays the resolved absolute path of the highlighted file so the user knows what they're about to print

### CLI Subcommand

- [ ] **CLI-01**: User can run `claude-teletype print <path>` to print a markdown file in one shot without entering the chat TUI
- [ ] **CLI-02**: User can run `claude-teletype print` with no path to launch the file picker, then exit after printing
- [ ] **CLI-03**: `claude-teletype print` honors all existing config layers (TOML, env, CLI flags) for printer profile, delay, audio, and saved-printer matching
- [ ] **CLI-04**: `claude-teletype print` exits with a non-zero status and a clear error when the path doesn't exist or isn't a regular file

### Markdown Rendering

- [ ] **MD-01**: Renderer supports bold (`**text**`, `__text__`) and italic (`*text*`, `_text_`) inline emphasis
- [ ] **MD-02**: Renderer supports ATX headings (`#` through `######`) styled as bold with an extra blank line above
- [ ] **MD-03**: Renderer supports unordered lists (`-`, `*`, `+`) and ordered lists with stable bullet/number glyphs and indentation for nested levels
- [ ] **MD-04**: Renderer supports fenced code blocks (```` ``` ````) printed as indented monospace with no inline-emphasis processing inside the block
- [ ] **MD-05**: Renderer supports blockquotes (`>`) with a visible quote marker prefix on each wrapped line
- [ ] **MD-06**: Renderer supports GitHub-flavored tables, formatted as ASCII grids that fit within `profile.columns`
- [ ] **MD-07**: Renderer composes with the existing `WordWrapper` so wrapped lines preserve list indentation and blockquote prefixes
- [ ] **MD-08**: Renderer emits the existing CR+LF + reinit pattern on newlines so daisywheel/CH341 printers don't drop bytes

### Profile Capabilities

- [x] **CAP-01**: `PrinterProfile` exposes `bold_on`, `bold_off`, `italic_on`, `italic_off`, `underline_on`, `underline_off` byte fields (empty bytes = capability not supported)
- [x] **CAP-02**: `PrinterProfile` exposes a `buffer_bytes` integer field (default chosen per profile family) used to chunk writes in instant mode
- [ ] **CAP-03**: Renderer applies a documented fallback chain: italic → underline → plain when italic codes are absent; bold → underline → plain when bold codes are absent
- [ ] **CAP-04**: Built-in Epson ESC/P, IBM PPDS, and HP PCL profiles ship with verified bold and italic sequences encoded
- [ ] **CAP-05**: Built-in Juki, OKI, and Citizen profiles ship with whatever bold sequences are documented for the family; absent capabilities are left as empty bytes (no incorrect codes)
- [x] **CAP-06**: Custom TOML profiles can declare bold/italic/underline byte sequences and `buffer_bytes` using the same field names

### Print Speed & Buffer Flow

- [ ] **FLOW-01**: Before each markdown print job, user sees a dialog choosing between **typewriter pacing** and **instant** print modes
- [ ] **FLOW-02**: Dialog default selection follows `profile.instant_output` for the active printer profile
- [ ] **FLOW-03**: Typewriter mode reuses the existing character pacer and audio pipeline so pacing matches conversation streaming
- [ ] **FLOW-04**: Instant mode chunks writes at `profile.buffer_bytes` boundaries to prevent buffer overruns on impact printers
- [ ] **FLOW-05**: User can cancel an in-progress print job from the TUI without crashing the app or leaving the printer in a bad style state (style codes always closed on cancel)

### Transcript Integration

- [ ] **TXN-01**: Each printed markdown file appears in the active session transcript as a "Printed file: `<path>`" entry followed by the plain-text rendered body
- [ ] **TXN-02**: Transcript entries for printed files do not contain raw printer ESC sequences (text only)
- [ ] **TXN-03**: Printing a file with no active conversation session creates no transcript file (transcript stays optional, matching existing behavior)

## Future Requirements

Deferred to v1.6+. Tracked but not in current roadmap.

### Print Preview & Formatting

- **PREV-01**: User can preview the rendered output in the TUI before sending to the printer
- **FMT-01**: Renderer supports page numbers, headers, and footers for multi-page documents

### Picker Enhancements

- **PICK-06**: Picker remembers recently-printed files and surfaces them at the top
- **PICK-07**: Picker supports a configurable `notes_dir` setting that overrides cwd as the default root

### Capability Expansion

- **CAP-07**: Renderer supports inline links (footnote-numbered references at end of document)
- **CAP-08**: Renderer supports task lists (`- [ ]` / `- [x]`) with check-glyph rendering

## Out of Scope

| Feature | Reason |
|---------|--------|
| Markdown editing inside the TUI | Read-only view + print only — editing belongs in the user's editor of choice |
| Network/cloud markdown sources (URLs, gists, Notion, etc.) | Local files only — keeps the offline, hardware-first character of the tool |
| Print preview screen | Deferred to a later milestone (PREV-01 above) so v1.5 ships the core feature first |
| Page numbering / headers / footers | Deferred (FMT-01 above) — v1.5 prints documents as continuous output |
| HTML or RTF source files | Markdown only; other formats can convert to markdown externally |
| Font-size or proportional-font selection | Most supported impact printers are fixed-size; decision matches existing project constraint |

## Traceability

Which phases cover which requirements. Filled in by `gsd-roadmapper` during roadmap creation.

| Requirement | Phase | Status |
|-------------|-------|--------|
| PICK-01 | Phase 24 | Pending |
| PICK-02 | Phase 24 | Pending |
| PICK-03 | Phase 24 | Pending |
| PICK-04 | Phase 24 | Pending |
| PICK-05 | Phase 24 | Pending |
| CLI-01 | Phase 25 | Pending |
| CLI-02 | Phase 25 | Pending |
| CLI-03 | Phase 25 | Pending |
| CLI-04 | Phase 25 | Pending |
| MD-01 | Phase 23 | Pending |
| MD-02 | Phase 23 | Pending |
| MD-03 | Phase 23 | Pending |
| MD-04 | Phase 23 | Pending |
| MD-05 | Phase 23 | Pending |
| MD-06 | Phase 23 | Pending |
| MD-07 | Phase 23 | Pending |
| MD-08 | Phase 23 | Pending |
| CAP-01 | Phase 21 | Complete |
| CAP-02 | Phase 21 | Complete |
| CAP-03 | Phase 21 | Pending |
| CAP-04 | Phase 22 | Pending |
| CAP-05 | Phase 22 | Pending |
| CAP-06 | Phase 21 | Complete |
| FLOW-01 | Phase 26 | Pending |
| FLOW-02 | Phase 26 | Pending |
| FLOW-03 | Phase 26 | Pending |
| FLOW-04 | Phase 26 | Pending |
| FLOW-05 | Phase 26 | Pending |
| TXN-01 | Phase 26 | Pending |
| TXN-02 | Phase 26 | Pending |
| TXN-03 | Phase 26 | Pending |

**Coverage:** 31/31 requirements mapped ✓

---
*Requirements defined: 2026-04-28*
