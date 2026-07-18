# Claude Teletype

## What This Is

A Python CLI tool that streams AI conversation to a physical dot-matrix printer character-by-character via USB-LPT adapter. Supports multiple LLM backends (Claude Code CLI, OpenAI, OpenRouter), configurable printer profiles (Juki, Epson, IBM, HP, custom), and a pure typewriter mode for direct keystroke-to-paper output. Features an interactive printer setup screen on startup for device discovery, connection selection, and profile assignment — with in-app pyusb installation and config persistence. When no printer hardware is available, it runs a split-screen terminal simulator. Prints local Markdown files via a TUI file picker (`ctrl+o`) or the `claude-teletype print` subcommand, rendering bold/italic/headings/lists/code/tables through capability-aware printer profiles with a per-print speed dialog. Includes a diagnostic CLI command, persistent TOML configuration, a TUI settings modal, multi-turn conversations with session persistence, error recovery, and word-wrapped output.

## Core Value

The physical typewriter experience — characters appearing on paper one at a time with authentic pacing and sound, making AI conversation feel tangible and mechanical.

## Requirements

### Validated

- ✓ Wrap Claude Code CLI and capture its streaming output — v1.0
- ✓ Auto-discover USB-LPT adapters on the system — v1.0
- ✓ Fall back to manual device selection if auto-discovery fails — v1.0
- ✓ Simulate printer in split-screen terminal mode when no hardware is found — v1.0
- ✓ Stream Claude's responses to printer character by character — v1.0
- ✓ Throttle character output with intentional delay (~50-100ms) for typewriter feel — v1.0
- ✓ Mirror all printer output to the terminal screen simultaneously — v1.0
- ✓ Play typewriter sound effects (carriage return dings) — v1.0
- ✓ Save conversation transcripts to text files — v1.0
- ✓ Multi-turn conversation in TUI with session persistence — v1.1
- ✓ Session resume via `--resume <session_id>` CLI flag — v1.1
- ✓ Visual turn separators and "You:"/"Claude:" labels — v1.1
- ✓ Status bar with turn count, context%, and model name — v1.1
- ✓ Input blocking during streaming to prevent race conditions — v1.1
- ✓ Error classification with 7 categories and user-friendly messages — v1.1
- ✓ Pre-flight CLI check with install URL when Claude Code missing — v1.1
- ✓ Subprocess readline timeout (300s/30s) preventing hangs — v1.1
- ✓ Automatic retry with exponential backoff for rate limit/overloaded — v1.1
- ✓ Session recovery on corrupted `--resume` — v1.1
- ✓ Word-boundary wrapping in TUI and printer output — v1.1
- ✓ Dynamic TUI resize updates wrap width — v1.1

- ✓ Persistent TOML configuration with three-layer merge (file < env < CLI flags) — v1.2
- ✓ Config file creation via `--init-config` and `config show`/`config init` subcommands — v1.2
- ✓ Data-driven printer profiles (Juki, Epson ESC/P, IBM PPDS, HP PCL, generic) with custom TOML profiles — v1.2
- ✓ USB auto-detection matching printer profiles by VID:PID — v1.2
- ✓ Multi-LLM backends: Claude Code CLI, OpenAI, OpenRouter via `--backend`/`--model` flags — v1.2
- ✓ Clear startup error messages for misconfigured backends — v1.2
- ✓ TUI settings modal via ctrl+comma for runtime config changes — v1.2
- ✓ Typewriter mode via ctrl+t: keystrokes to screen and printer with pacing and sound — v1.2
- ✓ Fixed `--no-tui` mode StreamResult crash with test coverage — v1.2
- ✓ system_prompt preserved during backend hot-swap in settings modal — v1.2

- ✓ "ibm" alias for PPDS printer profile with case-insensitive lookup — v1.3
- ✓ `config show` annotates every setting with source (default/file/env) — v1.3
- ✓ Startup warning when system_prompt configured with claude-cli backend (ignored in favor of CLAUDE.md) — v1.3
- ✓ Backend hot-swap confirmation dialog when switching away from claude-cli (context loss prevention) — v1.3

- ✓ Interactive printer setup screen on startup with USB and CUPS device discovery — v1.4
- ✓ User selects connection method (USB Direct / CUPS Queue) and printer profile with VID:PID auto-suggestion — v1.4
- ✓ In-app pyusb installation via async `uv sync --extra usb` with progress indicator — v1.4
- ✓ Graceful pyusb-missing handling — CUPS-only mode, no crashes — v1.4
- ✓ Printer selection saved to TOML config with atomic writes — v1.4
- ✓ Smart startup: setup screen skipped when saved printer still connected (USB by VID:PID, CUPS by queue name) — v1.4
- ✓ `claude-teletype diagnose` CLI command with structured Rich output — v1.4
- ✓ Skip/simulator option always available in setup screen — v1.4

- ✓ TUI markdown file picker (`ctrl+o`) rooted at cwd with `.md`/`.markdown` filtering and cancel-back-to-chat — v1.5
- ✓ `claude-teletype print [path]` CLI subcommand (explicit path or picker mode) honoring all config layers — v1.5
- ✓ Streaming markdown renderer — bold, italic, headings, lists, fenced code, blockquotes, ASCII tables — v1.5
- ✓ `PrinterProfile` style capability fields + `resolve_style` fallback chain (italic/bold→underline→plain) — v1.5
- ✓ Verified style ESC sequences for Epson ESC/P, IBM PPDS, HP PCL, Juki/OKI/Citizen where documented — v1.5
- ✓ Custom TOML profiles can declare style byte sequences and `buffer_bytes` — v1.5
- ✓ Per-print speed dialog (typewriter pace vs instant) defaulting from `profile.instant_output` — v1.5
- ✓ Instant-mode buffer chunking via per-profile `buffer_bytes` field — v1.5
- ✓ Cancel-safe printing — style codes always closed via `renderer.close()` on abort — v1.5
- ✓ Printed files logged in session transcript as plain text (no ESC bytes) — v1.5

- ✓ Package refactor into `printing/`, `rendering/`, `screens/` sub-packages via move-with-shim (shims deleted after migration) — v1.6
- ✓ `ProfileRegistry` + per-family `catalog/` modules replacing flat `BUILTIN_PROFILES` dict — v1.6
- ✓ USB driver selection by device identity; `SetupDecision` enum replacing `discovery=None` dual-meaning sentinel — v1.6
- ✓ Curated `BRIDGE_CHIPS` registry (CH341/Prolific/MosChip/FTDI) kept separate from printer profiles — v1.6
- ✓ Discovery `classify()` yielding NATIVE_PRINTER / BRIDGE / UNKNOWN; bridges route to manual family picker, never auto-guess — v1.6
- ✓ Serial-only chip (CH340) warning; kernel-claimed printer falls back to CUPS with clear message — v1.6
- ✓ Expanded native VID:PID matrix (Epson, OKI, Star, Lexmark, IBM, Citizen) auto-suggesting profiles — v1.6
- ✓ Per-family profiles verified-from-manual: escp2, epson-tm (ESC/POS), enriched ppds, OKI emulation + native, star-line, Panasonic/Tally aliases — v1.6
- ✓ Codepage support formalized: `codepage_command`/`text_codec`/`text_fallback` tracked, tested, custom-TOML settable; per-language codepage defaults — v1.6
- ✓ `diagnose` fleet matrix: per-device classification + per-profile capability summary; GET_PORT_STATUS readback (absent-not-broken on bridges) — v1.6
- ✓ Standalone macOS `.app` via checked-in PyInstaller onedir spec bundling libusb/PortAudio/Textual data, with `make_app.py` + `smoke_frozen.sh` — v1.6

### Active

(None — next milestone not yet defined)

### Out of Scope

- GUI interface — this is a terminal-only tool
- Network/remote printer support — local USB-LPT only (network printers buffer pages, destroying character streaming)
- Formatting/rich text — plain text only, as a typewriter would produce
- Markdown rendering in TUI — typewriter aesthetic is plain text
- Client-side context truncation — Claude Code's auto-compact handles this (for Claude backend)

## Context

**Current state:** v1.6 shipped (2026-06-13, archived 2026-07-18). 7,901 LOC source + 12,925 LOC tests (Python). 905 tests passing. Phases 28-30 were executed reactively outside GSD phase tracking (commits only, no plan/summary artifacts); requirements were code-verified at close — 27/29 complete, REF-06 and PKG-03 deferred.

**Tech stack:** Python 3.12+, Textual 7.x (TUI), Rich (CLI spinners/tables), Typer (argument parsing), sounddevice/numpy (audio), openai SDK (OpenAI/OpenRouter backends), tomllib/platformdirs (configuration), pyusb (optional, USB auto-detection).

**Modules:** bridge.py (Claude Code subprocess wrapper), tui.py (Textual TUI), cli.py (Typer entry point), pacer.py (character pacing), output.py (multiplexer), audio.py (bell + keystroke sounds), transcript.py (file writer), errors.py (error classification), wordwrap.py (streaming word wrapper), config.py (TOML config + env + CLI merge + atomic save), warnings.py (config conflict detection), diagnose.py (CLI diagnostic + fleet matrix), setup_decision.py (SetupDecision enum), usb_backend.py (frozen libusb backend seam), backends/ (LLMBackend ABC + Claude CLI + OpenAI + OpenRouter), printing/ (drivers, discovery, selection, detection + BRIDGE_CHIPS, registry/ProfileRegistry, profiles, catalog/{epson,oki,star}), rendering/ (streaming markdown renderer), screens/ (typewriter, printer_setup, settings, file_picker, speed_mode), packaging/ (PyInstaller spec, entry.py, make_app.py, smoke_frozen.sh).

**Known tech debt:**
- `config show` cannot detect CLI flag sources (Typer architectural constraint — separate subcommand)
- Juki 9100 control codes extrapolated from 6100 (need hardware verification)
- Style ESC sequences spec-verified only — real-hardware confirmation pending on all profile families (`human_needed`, incl. new v1.6 families)
- Per-profile `buffer_bytes` defaults unvalidated on real hardware (Juki, Epson) — instant mode trust pending
- WordWrapper strips 4-space code-block indent (content survives, visual indent lost)
- Table cells truncate rather than wrap on narrow profiles (Citizen 42-col thermal)
- REF-06 open: no code-review findings artifact for the v1.6 refactor — run `/gsd:code-review`
- PKG-03 open: frozen `.app` verified via headless smoke script only; true clean-machine run pending (`human_needed`)
- GET_PORT_STATUS readback spec-tested with mocks only; bridge-chip interface-class behavior (CH341 class 7 vs vendor-specific) unverified on real hardware
- Phases 28-30 executed reactively — no per-phase PLAN/SUMMARY artifacts (history lives in git log + MILESTONES.md)

## Constraints

- **Language**: Python — user's choice
- **Hardware**: Must handle missing printer gracefully (simulation mode)
- **Dependency**: At least one LLM backend configured (Claude Code CLI, OpenAI API key, or OpenRouter API key)
- **Platform**: macOS primary, Linux compatibility is a bonus

## Key Decisions

| Decision | Rationale | Outcome |
|----------|-----------|---------|
| Wrap Claude Code CLI rather than use API directly | Preserves Claude Code's existing auth, context, and tool use capabilities | ✓ Good |
| Split-screen simulator as fallback | Lets development and testing happen without physical hardware | ✓ Good |
| Throttled character pacing over raw speed | The deliberate delay IS the experience — mechanical feel matters more than speed | ✓ Good |
| output_fn injection pattern | Enables testing without real stdout, flexible destination fan-out | ✓ Good |
| Textual Log widget for TUI output | Handles character streaming with proper newline semantics | ✓ Good |
| StreamResult as final yield from async generator | Clean metadata propagation without side channels | ✓ Good |
| proc_holder mutable list pattern | Subprocess reference propagation from bridge to TUI for cancel support | ✓ Good |
| Substring matching for error classification | Simpler and more maintainable than regex for known error patterns | ✓ Good |
| WordWrapper as pipeline filter (not CSS) | Textual Log widget hardcodes no_wrap=True; wrapping must happen before write() | ✓ Good |
| Deferred space pattern in WordWrapper | Prevents trailing whitespace on wrapped lines | ✓ Good |
| Per-destination wrapping | TUI and printer get wrapped output; transcript and audio get unwrapped | ✓ Good |
| Three-layer config merge: defaults < TOML < env < CLI | Standard precedence chain, each layer overrides previous | ✓ Good |
| Pre-formatted string template for config file | tomli-w cannot write TOML comments; handwritten template preserves docs | ✓ Good |
| Data-driven printer profiles via frozen dataclass | All printer behavior encoded as data, not conditional code | ✓ Good |
| USB printer class 7 filter before VID:PID matching | Prevents false matches against non-printer USB devices | ✓ Good |
| ProfilePrinterDriver as standalone class | Generic profile support; JukiPrinterDriver thin deprecated subclass | ✓ Good |
| Placeholder API key in AsyncOpenAI constructor | Defers validation to validate() method for consistent error path | ✓ Good |
| max_retries=0 on AsyncOpenAI | TUI retry loop handles retries consistently across all backends | ✓ Good |
| Backend hot-swap: create_backend + validate in try/except | Notify on error, keep old backend on failure | ✓ Good |
| ctrl+comma as settings shortcut | Avoids ctrl+s XOFF freeze, matches VS Code/Sublime convention | ✓ Good |
| SettingsScreen uses ModalScreen[dict|None] | Callback-based result passing, clean dismiss semantics | ✓ Good |
| Backspace intentionally ignored in typewriter mode | Append-only for authenticity — typewriters don't have backspace | ✓ Good |
| dataclasses.replace for profile aliasing | Preserves frozen immutability of PrinterProfile | ✓ Good |
| CLI flag source excluded from config show | show() is a separate Typer subcommand without main's CLI params | ✓ Good |
| Per-process suppression for startup warnings | Module-level set sufficient; config changes restart code paths | ✓ Good |
| ConfirmSwapScreen only when leaving claude-cli | API backends have no persistent sessions; only claude-cli has context loss risk | ✓ Good |
| importlib.util.find_spec over import for pyusb detection | Avoids polluting sys.modules cache, enabling same-session reimport after install | ✓ Good |
| PrinterSetupScreen as full Screen, not ModalScreen | Setup is a gate (blocks chat), not an overlay; matches TypewriterScreen pattern | ✓ Good |
| call_after_refresh for deferred screen push | Avoids Textual screen lifecycle races when pushing in on_mount | ✓ Good |
| Atomic config writes via tempfile + os.replace | Prevents config corruption from mid-write crashes | ✓ Good |
| USB matching by VID:PID, CUPS by queue name | Bus/address changes on replug; VID:PID and queue names are stable | ✓ Good |
| discovery=None as skip-setup signal | Reuses existing convention; TUI checks this in _needs_printer_setup | ✓ Good |
| CR+LF+reinit as single atomic USB transfer | Prevents Juki CH341 bridge from dropping LF byte on word-wrap newlines | ✓ Good |
| Empty bytes (b"") sentinel for absent style capability | Fallback chain reads capability state from data; no conditional per-printer code | ✓ Good |
| resolve_style as free function with italic/bold→underline→plain chain | Underline universal on impact printers; never fabricate codes that print garbage | ✓ Good |
| Encoding-table-as-contract for Phase 22 byte literals | Byte values copied verbatim from published manuals; when unsure, leave empty | ✓ Good |
| write_bytes as public Protocol method (style channel) | Dual-channel seam visible at type-checker layer; newlines stay on write('\n') (MD-08) | ✓ Good |
| Hand-written streaming markdown renderer (no library) | Dual text/style channel + WordWrapper composition impossible with off-the-shelf renderers | ✓ Good |
| Emphasis markers as state-machine tokens, not text | `*`/`_` consumed by toggle path; never reach printer output | ✓ Good |
| ctrl+o App-level binding for file picker | Mnemonic, conflict-free, works even while input is disabled mid-stream | ✓ Good |
| _make_*_app() closure factory for one-shot Textual apps | Captures context without overriding Textual constructor signatures | ✓ Good |
| speed_mode defaults to "instant" on _render_markdown_to_driver | Existing Phase 25 callers keep pre-Phase-26 contract without modification | ✓ Good |
| Sync time.sleep pacing in print path (reusing CHAR_DELAYS) | Preserves locked sync callback shape; identical per-char delays to chat path | ✓ Good |
| MarkdownRenderer.close() as thin delegation to _close_open_styles | Single source of truth for LIFO style cleanup; idempotent cancel safety | ✓ Good |
| chunk_writes as free function in printer.py | Driver-agnostic, pure, testable against any PrinterDriver Protocol | ✓ Good |

## Evolution

This document evolves at phase transitions and milestone boundaries.

**After each phase transition** (via `/gsd:transition`):
1. Requirements invalidated? → Move to Out of Scope with reason
2. Requirements validated? → Move to Validated with phase reference
3. New requirements emerged? → Add to Active
4. Decisions to log? → Add to Key Decisions
5. "What This Is" still accurate? → Update if drifted

**After each milestone** (via `/gsd:complete-milestone`):
1. Full review of all sections
2. Core Value check — still the right priority?
3. Audit Out of Scope — reasons still valid?
4. Update Context with current state

---
*Last updated: 2026-07-18 after v1.6 milestone*
