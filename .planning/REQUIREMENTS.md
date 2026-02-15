# Requirements: Claude Teletype

**Defined:** 2026-02-14
**Core Value:** The physical typewriter experience -- characters appearing on paper one at a time with authentic pacing and sound, making AI conversation feel tangible and mechanical.

## v1 Requirements

Requirements for initial release. Each maps to roadmap phases.

### Claude Integration

- [ ] **CLDE-01**: User can send prompts to Claude Code via CLI wrapper using `--output-format stream-json --verbose --include-partial-messages`
- [ ] **CLDE-02**: Tool parses NDJSON stream and extracts `text_delta` events for character-by-character output
- [ ] **CLDE-03**: Tool shows a thinking indicator while waiting for Claude's first token

### Character Output

- [ ] **CHAR-01**: Characters appear one at a time with configurable delay (50-100ms default range)
- [ ] **CHAR-02**: All output is mirrored to both terminal screen and printer simultaneously
- [ ] **CHAR-03**: Character pacing varies by context (punctuation 1.5x slower, newlines 3x pause, spaces 0.5x faster)

### Printer Hardware

- [ ] **PRNT-01**: Tool auto-discovers USB-LPT adapters on startup via CUPS scan and USB device enumeration
- [ ] **PRNT-02**: User can manually specify a printer device via `--device` CLI flag
- [ ] **PRNT-03**: Tool gracefully falls back to simulator mode if printer disconnects mid-session without crashing

### Terminal Simulator

- [ ] **SIML-01**: Split-screen TUI launches as default mode when no printer hardware is found (Textual-based, top=output, bottom=input)
- [ ] **SIML-02**: Simulator renders characters with same typewriter pacing as physical printer output

### Audio

- [ ] **AUDI-01**: Carriage return / line break triggers a bell/ding sound effect via sounddevice

### Persistence

- [ ] **PERS-01**: Conversations are saved to timestamped plain text transcript files on disk

## v2 Requirements

Deferred to future release. Tracked but not in current roadmap.

### Claude Integration

- **CLDE-04**: User can resume previous conversation sessions via `--resume` flag

### Character Output

- **CHAR-04**: User can adjust character pacing mid-session with keyboard shortcuts (+/-)

### Printer Hardware

- **PRNT-04**: Tool sends form feed on exit for clean paper tearoff
- **PRNT-05**: Tool detects printer status (paper out, error) via USB status query
- **PRNT-06**: Text wraps at word boundaries respecting physical printer column width (80/132)

### Terminal Simulator

- **SIML-03**: Simulator renders with dot-matrix visual aesthetic (faded ink, mono font)

### Audio

- **AUDI-02**: Typewriter key-click sound plays on each character output
- **AUDI-03**: Distinct sounds differentiate user input from Claude output

### Presentation

- **PRES-01**: ASCII art session headers printed at start of each conversation

## Out of Scope

| Feature | Reason |
|---------|--------|
| Direct Anthropic API integration | Wraps Claude Code CLI to preserve auth, tools, context, MCP |
| Network/remote printer support | Network printers buffer pages, destroying character-by-character streaming |
| GUI interface | Terminal tool for terminal people; GUI adds massive dependency |
| Rich text / Markdown rendering on paper | Dot-matrix is plain text; the constraint IS the aesthetic |
| Multi-printer support | Adds sync complexity for near-zero use case |
| Syntax highlighting on paper | Monochrome dot-matrix; color switching unreliable |
| Custom printer drivers | Uses standard device I/O and CUPS |
| pyparallel / parallel port I/O | USB-LPT adapters are USB printer class, not parallel ports |

## Traceability

Which phases cover which requirements. Updated during roadmap creation.

| Requirement | Phase | Status |
|-------------|-------|--------|
| CLDE-01 | Phase 1 | Complete |
| CLDE-02 | Phase 1 | Complete |
| CLDE-03 | Phase 1 | Complete |
| CHAR-01 | Phase 1 | Complete |
| CHAR-02 | Phase 2 | Complete |
| CHAR-03 | Phase 1 | Complete |
| PRNT-01 | Phase 3 | Complete |
| PRNT-02 | Phase 3 | Complete |
| PRNT-03 | Phase 3 | Complete |
| SIML-01 | Phase 2 | Complete |
| SIML-02 | Phase 2 | Complete |
| AUDI-01 | Phase 4 | Pending |
| PERS-01 | Phase 4 | Pending |

**Coverage:**
- v1 requirements: 13 total
- Mapped to phases: 13
- Unmapped: 0

---
*Requirements defined: 2026-02-14*
*Last updated: 2026-02-15 after Phase 1 completion*
