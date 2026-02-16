# Claude Teletype

## What This Is

A Python CLI tool that wraps Claude Code and streams all input/output character-by-character to a physical dot-matrix printer connected via USB-LPT adapter. It recreates the experience of using a mechanical typewriter that thinks — you type a question, hear the keys clatter, and watch Claude's answer appear on paper one character at a time. When no printer hardware is available, it runs a split-screen terminal simulator.

## Core Value

The physical typewriter experience — characters appearing on paper one at a time with authentic pacing and sound, making AI conversation feel tangible and mechanical.

## Current Milestone: v1.1 Conversation Mode

**Goal:** Turn the one-shot prompt/response tool into a real multi-turn conversation experience with proper error handling and text wrapping.

**Target features:**
- Multi-turn conversation in both TUI and CLI modes
- Full conversation context with auto-truncation for long sessions
- Word wrap in TUI output
- Better error handling for common failure modes

## Requirements

### Validated

<!-- Shipped and confirmed valuable in v1.0. -->

- ✓ Wrap Claude Code CLI and capture its streaming output — v1.0 Phase 1
- ✓ Auto-discover USB-LPT adapters on the system — v1.0 Phase 3
- ✓ Fall back to manual device selection if auto-discovery fails — v1.0 Phase 3
- ✓ Simulate printer in split-screen terminal mode when no hardware is found — v1.0 Phase 2
- ✓ Echo user keyboard input to printer character by character — v1.0 Phase 3
- ✓ Stream Claude's responses to printer character by character — v1.0 Phase 1
- ✓ Throttle character output with intentional delay (~50-100ms) for typewriter feel — v1.0 Phase 1
- ✓ Mirror all printer output to the terminal screen simultaneously — v1.0 Phase 2
- ✓ Play typewriter sound effects (key clicks, carriage return dings) — v1.0 Phase 4
- ✓ Save conversation transcripts to text files — v1.0 Phase 4

### Active

- [ ] Multi-turn conversation in TUI (prompt → response → prompt loop)
- [ ] Multi-turn conversation in CLI mode (interactive stdin loop)
- [ ] Full conversation context passed to Claude on each turn
- [ ] Auto-truncate oldest messages when context exceeds limits
- [ ] Word wrap for long lines in TUI output
- [ ] Clear error messages when Claude Code is not installed
- [ ] Graceful handling of network failures during streaming

### Out of Scope

- Direct Anthropic API integration — wraps Claude Code CLI, not the API
- GUI interface — this is a terminal-only tool
- Network/remote printer support — local USB-LPT only
- Formatting/rich text — plain text only, as a typewriter would produce
- TUI settings screen — deferred to v1.2
- Model selection (OpenAI/ChatGPT) — deferred to v1.2
- Paper format selection (A4, A3) — deferred to v1.2
- Printer profiles system — deferred to v1.2

## Context

- Platform: macOS (Darwin), may work on Linux
- USB-LPT adapters typically appear as /dev/usb/lp* on Linux or via libusb on macOS
- Dot-matrix printers accept raw text bytes, making them ideal for character-by-character streaming
- Claude Code CLI supports streaming output which can be captured and throttled
- Claude Code CLI uses `-p` flag for one-shot mode and `--resume` for session continuity
- Python has pyserial and pyusb libraries for hardware communication
- Sound effects played via sounddevice/numpy (880 Hz bell tone)
- Textual 7.x for TUI, Rich for CLI spinners, Typer for argument parsing

## Constraints

- **Language**: Python — user's choice
- **Hardware**: Must handle missing printer gracefully (simulation mode)
- **Dependency**: Claude Code CLI must be installed and configured
- **Platform**: macOS primary, Linux compatibility is a bonus

## Key Decisions

| Decision | Rationale | Outcome |
|----------|-----------|---------|
| Wrap Claude Code CLI rather than use API directly | Preserves Claude Code's existing auth, context, and tool use capabilities | ✓ Good |
| Split-screen simulator as fallback | Lets development and testing happen without physical hardware | ✓ Good |
| Throttled character pacing over raw speed | The deliberate delay IS the experience — mechanical feel matters more than speed | ✓ Good |
| output_fn injection pattern | Enables testing without real stdout, flexible destination fan-out | ✓ Good |
| Textual Log widget for TUI output | Handles character streaming with proper newline semantics | ✓ Good |

---
*Last updated: 2026-02-16 after v1.1 milestone start*
