# Claude Teletype

## What This Is

A Python CLI tool that wraps Claude Code and streams all input/output character-by-character to a physical dot-matrix printer connected via USB-LPT adapter. It recreates the experience of using a mechanical typewriter that thinks — you type a question, hear the keys clatter, and watch Claude's answer appear on paper one character at a time. When no printer hardware is available, it runs a split-screen terminal simulator.

## Core Value

The physical typewriter experience — characters appearing on paper one at a time with authentic pacing and sound, making AI conversation feel tangible and mechanical.

## Requirements

### Validated

(None yet — ship to validate)

### Active

- [ ] Wrap Claude Code CLI and capture its streaming output
- [ ] Auto-discover USB-LPT adapters on the system
- [ ] Fall back to manual device selection if auto-discovery fails
- [ ] Simulate printer in split-screen terminal mode when no hardware is found
- [ ] Echo user keyboard input to printer character by character
- [ ] Stream Claude's responses to printer character by character
- [ ] Throttle character output with intentional delay (~50-100ms) for typewriter feel
- [ ] Mirror all printer output to the terminal screen simultaneously
- [ ] Play typewriter sound effects (key clicks, carriage return dings)
- [ ] Save conversation transcripts to text files

### Out of Scope

- Direct Anthropic API integration — wraps Claude Code CLI, not the API
- Custom printer drivers — uses standard device I/O
- GUI interface — this is a terminal-only tool
- Network/remote printer support — local USB-LPT only
- Formatting/rich text — plain text only, as a typewriter would produce

## Context

- Platform: macOS (Darwin), may work on Linux
- USB-LPT adapters typically appear as /dev/usb/lp* on Linux or via libusb on macOS
- Dot-matrix printers accept raw text bytes, making them ideal for character-by-character streaming
- Claude Code CLI supports streaming output which can be captured and throttled
- Python has pyserial and pyusb libraries for hardware communication
- Sound effects can be played with pygame, simpleaudio, or similar

## Constraints

- **Language**: Python — user's choice
- **Hardware**: Must handle missing printer gracefully (simulation mode)
- **Dependency**: Claude Code CLI must be installed and configured
- **Platform**: macOS primary, Linux compatibility is a bonus

## Key Decisions

| Decision | Rationale | Outcome |
|----------|-----------|---------|
| Wrap Claude Code CLI rather than use API directly | Preserves Claude Code's existing auth, context, and tool use capabilities | — Pending |
| Split-screen simulator as fallback | Lets development and testing happen without physical hardware | — Pending |
| Throttled character pacing over raw speed | The deliberate delay IS the experience — mechanical feel matters more than speed | — Pending |

---
*Last updated: 2026-02-14 after initialization*
