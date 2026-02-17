# Claude Teletype

## What This Is

A Python CLI tool that wraps Claude Code and streams all input/output character-by-character to a physical dot-matrix printer connected via USB-LPT adapter. It recreates the experience of using a mechanical typewriter that thinks — you type a question, hear the keys clatter, and watch Claude's answer appear on paper one character at a time. When no printer hardware is available, it runs a split-screen terminal simulator. Supports multi-turn conversations with session persistence, error recovery, and word-wrapped output.

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

### Active

**v1.2 — Configuration, Printer Profiles, Multi-LLM, Settings UI**

- Configuration system with persistent settings file (delays, sound, default printer, API keys)
- Printer profiles with per-printer control codes and paper handling (Juki 9100, Epson/IBM dot matrix, HP/Epson inkjet)
- Multi-LLM backends: keep Claude Code CLI as default, add OpenAI and OpenRouter via direct API
- TUI settings page accessible via keyboard shortcut (printer, LLM, paper options)
- Simple typewriter mode: no LLM, keystrokes go straight to printer/screen with pacing and sound
- Fix `--no-tui` mode crash (StreamResult guard) and add test coverage

### Out of Scope

- GUI interface — this is a terminal-only tool
- Network/remote printer support — local USB-LPT only (network printers buffer pages, destroying character streaming)
- Formatting/rich text — plain text only, as a typewriter would produce
- Markdown rendering in TUI — typewriter aesthetic is plain text
- Client-side context truncation — Claude Code's auto-compact handles this (for Claude backend)

## Context

**Current state:** v1.1 shipped (2026-02-17). 1,839 LOC source + 3,139 LOC tests (Python).

**Tech stack:** Python 3.12+, Textual 7.x (TUI), Rich (CLI spinners), Typer (argument parsing), sounddevice/numpy (audio).

**Modules:** bridge.py (Claude Code subprocess wrapper), tui.py (Textual TUI), cli.py (Typer entry point), pacer.py (character pacing), output.py (multiplexer), printer.py (CUPS/File/Null drivers), audio.py (bell sounds), transcript.py (file writer), errors.py (error classification), wordwrap.py (streaming word wrapper).

**Known tech debt:**
- `_chat_async` in cli.py crashes with TypeError in `--no-tui` mode (StreamResult not guarded)
- No test coverage for `--no-tui` code path

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

---
*Last updated: 2026-02-17 after v1.2 milestone started*
