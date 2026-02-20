# Claude Teletype

## What This Is

A Python CLI tool that streams AI conversation to a physical dot-matrix printer character-by-character via USB-LPT adapter. Supports multiple LLM backends (Claude Code CLI, OpenAI, OpenRouter), configurable printer profiles (Juki, Epson, IBM, HP, custom), and a pure typewriter mode for direct keystroke-to-paper output. When no printer hardware is available, it runs a split-screen terminal simulator. Includes persistent TOML configuration, a TUI settings modal, multi-turn conversations with session persistence, error recovery, and word-wrapped output.

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

### Active

## Current Milestone: v1.3 Tech Debt Cleanup

**Goal:** Resolve all known tech debt from v1.2 — improve discoverability, config transparency, and user warnings for edge cases.

**Target features:**
- Add "ibm" alias for PPDS printer profile
- Show effective merged config with source annotations in `config show`
- Warn at startup when system_prompt is set but backend is claude-cli
- Warn user when hot-swapping away from claude-cli that session context will be lost

### Out of Scope

- GUI interface — this is a terminal-only tool
- Network/remote printer support — local USB-LPT only (network printers buffer pages, destroying character streaming)
- Formatting/rich text — plain text only, as a typewriter would produce
- Markdown rendering in TUI — typewriter aesthetic is plain text
- Client-side context truncation — Claude Code's auto-compact handles this (for Claude backend)

## Context

**Current state:** v1.2 shipped (2026-02-17). 3,191 LOC source + 5,349 LOC tests (Python). 401 tests passing.

**Tech stack:** Python 3.12+, Textual 7.x (TUI), Rich (CLI spinners), Typer (argument parsing), sounddevice/numpy (audio), openai SDK (OpenAI/OpenRouter backends), tomllib/platformdirs (configuration), pyusb (optional, USB auto-detection).

**Modules:** bridge.py (Claude Code subprocess wrapper), tui.py (Textual TUI), cli.py (Typer entry point), pacer.py (character pacing), output.py (multiplexer), printer.py (CUPS/File/Null/Profile drivers), audio.py (bell + keystroke sounds), transcript.py (file writer), errors.py (error classification), wordwrap.py (streaming word wrapper), config.py (TOML config + env + CLI merge), profiles.py (printer profile registry + USB auto-detect), backends/ (LLMBackend ABC + Claude CLI + OpenAI + OpenRouter), typewriter_screen.py (keystroke-to-paper mode), settings_screen.py (TUI settings modal).

**Known tech debt:**
- ~~IBM PPDS profile keyed as "ppds" not "ibm" (discoverability)~~ — resolved v1.3 Phase 16
- ~~`config show` reflects file+env but not CLI flags~~ — resolved v1.3 Phase 16 (CLI flags excluded by design: separate Typer subcommand)
- system_prompt silently ignored for claude-cli backend (uses CLAUDE.md instead)
- Backend hot-swap loses session_id for claude-cli (starts fresh session)

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

---
*Last updated: 2026-02-20 after Phase 17*
