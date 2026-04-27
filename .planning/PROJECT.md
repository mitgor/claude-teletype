# Claude Teletype

## What This Is

A Python CLI tool that streams AI conversation to a physical dot-matrix printer character-by-character via USB-LPT adapter. Supports multiple LLM backends (Claude Code CLI, OpenAI, OpenRouter), configurable printer profiles (Juki, Epson, IBM, HP, custom), and a pure typewriter mode for direct keystroke-to-paper output. Features an interactive printer setup screen on startup for device discovery, connection selection, and profile assignment — with in-app pyusb installation and config persistence. When no printer hardware is available, it runs a split-screen terminal simulator. Includes a diagnostic CLI command, persistent TOML configuration, a TUI settings modal, multi-turn conversations with session persistence, error recovery, and word-wrapped output.

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

### Active

(None — planning next milestone)

### Out of Scope

- GUI interface — this is a terminal-only tool
- Network/remote printer support — local USB-LPT only (network printers buffer pages, destroying character streaming)
- Formatting/rich text — plain text only, as a typewriter would produce
- Markdown rendering in TUI — typewriter aesthetic is plain text
- Client-side context truncation — Claude Code's auto-compact handles this (for Claude backend)

## Context

**Current state:** v1.4 shipped (2026-04-03). 4,646 LOC source + 6,510 LOC tests (Python). 479 tests passing.

**Tech stack:** Python 3.12+, Textual 7.x (TUI), Rich (CLI spinners/tables), Typer (argument parsing), sounddevice/numpy (audio), openai SDK (OpenAI/OpenRouter backends), tomllib/platformdirs (configuration), pyusb (optional, USB auto-detection).

**Modules:** bridge.py (Claude Code subprocess wrapper), tui.py (Textual TUI), cli.py (Typer entry point), pacer.py (character pacing), output.py (multiplexer), printer.py (CUPS/File/Null/Profile/USB drivers + discovery dataclasses + driver factory), audio.py (bell + keystroke sounds), transcript.py (file writer), errors.py (error classification), wordwrap.py (streaming word wrapper), config.py (TOML config + env + CLI merge + atomic save), profiles.py (printer profile registry + USB auto-detect), backends/ (LLMBackend ABC + Claude CLI + OpenAI + OpenRouter), typewriter_screen.py (keystroke-to-paper mode), printer_setup_screen.py (interactive printer setup), settings_screen.py (TUI settings modal), diagnose.py (CLI diagnostic command), warnings.py (config conflict detection + startup warnings).

**Known tech debt:**
- `config show` cannot detect CLI flag sources (Typer architectural constraint — separate subcommand)
- Pre-existing test_cli_teletype_passes_no_profile failure (USB auto-detection test)
- Juki 9100 control codes extrapolated from 6100 (need hardware verification)
- create_driver_for_selection() for USB re-discovers by class, not by index (single printer assumed)
- discovery=None sentinel carries two meanings (saved-match and device-override skip)

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
*Last updated: 2026-04-03 after v1.4 milestone*
