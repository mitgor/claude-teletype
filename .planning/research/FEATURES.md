# Feature Research

**Domain:** Teletype-style CLI printer interface for AI conversation
**Researched:** 2026-02-14
**Confidence:** MEDIUM-HIGH

## Feature Landscape

### Table Stakes (Users Expect These)

Features users assume exist. Missing these = product feels incomplete.

| Feature | Why Expected | Complexity | Notes |
|---------|--------------|------------|-------|
| Claude Code CLI wrapping | The entire product is "Claude on paper." Without the Claude integration, there is no product. | MEDIUM | Use `claude -p --output-format stream-json --include-partial-messages` for streaming. Subprocess via `asyncio.create_subprocess_exec` with stdout PIPE. Character-by-character read via `stream.read(1)` or parse JSON deltas from stream-json format. |
| Character-by-character output pacing | The typewriter feel IS the core value. Dumping text instantly defeats the purpose. | LOW | Simple `asyncio.sleep(0.05-0.1)` between characters. Must be configurable -- 50-100ms default range per PROJECT.md. |
| USB-LPT printer auto-discovery | Users plug in hardware and expect it to work. Manual config as first step kills the magic. | MEDIUM | Use `pyusb` with `usb.core.find()` to scan for known USB-to-parallel adapter vendor/product IDs. Common adapters use USB printer class (0x07). On Linux also check `/dev/usb/lp*` device files. macOS requires libusb backend (no native `/dev/lp` equivalent). |
| Manual device selection fallback | Auto-discovery will fail for unusual adapters or configurations. Users need an escape hatch. | LOW | Simple CLI flag `--device /dev/usb/lp0` or interactive picker listing available USB devices. |
| Split-screen terminal simulator (no-hardware mode) | Most development and demo use happens without physical hardware. Without this, the tool is unusable for 90% of potential users. | MEDIUM-HIGH | Two approaches: (a) Textual/Rich TUI with split panes, or (b) raw curses. Textual is the stronger choice -- modern API, layout system, Rich integration. Top pane = conversation, bottom pane = input. Simulate character-by-character rendering in terminal with same pacing as printer. |
| Screen mirroring (printer + terminal) | When hardware is connected, users still need to see what's being printed on screen. Paper scrolls away; screen persists. | LOW | Write each character to both printer device and terminal stdout. Trivial once the output pipeline exists. |
| Conversation transcript saving | Paper is ephemeral (ink fades, paper tears). Digital backup of conversations is expected for any chat tool. | LOW | Append each message to a timestamped text file. Plain text format matching what the printer produces. |
| Graceful hardware disconnect handling | USB devices get unplugged. The tool must not crash -- it should fall back to terminal-only mode. | MEDIUM | Catch `USBError` / write exceptions on printer output. Switch to terminal-only mode with a warning. Consider `aio-usb-hotplug` for async hotplug events, but a simpler try/except on each write is sufficient for MVP. |
| Clean exit and paper positioning | On a dot-matrix printer, abrupt exit leaves paper mid-line. Users expect the tool to advance paper to a tear-off point on exit. | LOW | Send form feed (`\x0c`) or line feeds on exit signal handler. Register `atexit` and SIGINT/SIGTERM handlers. |

### Differentiators (Competitive Advantage)

Features that set the product apart. Not required, but valuable.

| Feature | Value Proposition | Complexity | Notes |
|---------|-------------------|------------|-------|
| Typewriter sound effects | Transforms the experience from "text appearing on screen" to "machine thinking on paper." The sensory dimension is what makes this memorable. Daktilo (Rust tool) proves the appeal of keyboard sounds -- this extends it to AI output. | MEDIUM | Use `simpleaudio` for low-latency WAV playback (lighter than pygame, no SDL dependency). Need separate sounds: keyclick (user typing), printhead strike (Claude output), carriage return ding (newline), paper feed whir (form feed). Sounds must be non-blocking -- fire and forget via `simpleaudio.play_buffer()`. Bundle a small WAV library (~100KB total). |
| ASCII art session headers | Each conversation session starts with a decorative banner on paper. Makes physical printouts feel like artifacts, not raw logs. | LOW | Use `pyfiglet` (Python figlet port) to generate banners. Print date, session ID, model name in large ASCII text. Looks great on dot-matrix paper. |
| Variable character pacing by context | Not all characters should arrive at the same speed. Punctuation gets a longer pause (thinking). Code gets faster (machine output). This creates a more organic, human-like feel. | LOW | Map character classes to delay multipliers: punctuation = 1.5x, newline = 3x, spaces = 0.5x, alphanumeric = 1.0x. Small lookup table, large experiential impact. |
| Carriage return sound + line pause | On real teletypes, the carriage return was a distinct mechanical event -- a ding followed by a brief pause. Reproducing this adds authenticity. | LOW | Detect newline in output stream, play ding WAV, insert ~300ms pause. Tiny implementation, outsized immersion effect. |
| ESC/P printer formatting | Dot-matrix printers understand ESC/P escape codes for bold, italic, underline, and font changes. Using these to distinguish user input from Claude output on paper. | MEDIUM | Send ESC/P codes before/after text segments. Bold for user prompts (`ESC E` / `ESC F`), normal for Claude responses, underline for code blocks (`ESC - 1` / `ESC - 0`). Must be optional -- not all printers support ESC/P. |
| Paper-aware line wrapping | Dot-matrix printers have a fixed column width (typically 80 or 132 columns). Text must wrap at word boundaries, not mid-word. | LOW | Track column position, wrap at last space before column limit. Configurable column width via `--columns` flag. Standard text-wrapping logic. |
| Printer status detection | Before sending data, check if the printer is online, has paper, and is not in error state. Prevents silent data loss. | MEDIUM | USB status queries vary by adapter. Some USB-LPT adapters expose IEEE 1284 status nibble (paper out, select, error). Check via `pyusb` control transfer. Not universally supported -- degrade gracefully. |
| Interactive speed control | Let users adjust character pacing mid-session with keyboard shortcuts (faster/slower). Finding the right speed is subjective. | LOW | Global speed multiplier variable. Bind `+`/`-` keys (or Ctrl-Up/Down) to adjust. Display current speed in status bar. |
| Session resume / continue | Resume a previous Claude Code conversation with `--continue` or `--resume`. Seamless multi-session conversations on paper. | LOW | Pass `-c` or `-r <session-id>` through to the underlying Claude Code CLI call. Transcript file continues appending. |
| Configurable printer ribbon style | In terminal simulator mode, render text in dot-matrix aesthetic: slightly faded, uneven character weight, mono font. Makes the terminal experience echo the physical one. | MEDIUM | ANSI color codes for faded ink effect (dim attribute). Could use Rich markup for styled output. In Textual, custom CSS for the output widget. Nice visual touch but not essential. |
| Input echo to printer | When the user types, their input also prints on paper character-by-character, just like a real teletype where everything appears on paper. | LOW | Mirror stdin characters to printer output stream with same pacing. Add visual distinction (bold or prefixed with `> `). |

### Anti-Features (Commonly Requested, Often Problematic)

Features that seem good but create problems.

| Feature | Why Requested | Why Problematic | Alternative |
|---------|---------------|-----------------|-------------|
| Direct Anthropic API integration | "Why depend on Claude Code CLI? Just call the API directly." | Claude Code provides auth management, tool use, context windows, file access, MCP, and agent capabilities. Reimplementing these is months of work and creates a worse, divergent experience. The value of this project is the physical output layer, not another API client. | Use `claude -p --output-format stream-json` for clean subprocess integration. Let Claude Code handle all AI complexity. |
| Network/remote printer support | "What about network printers?" | Network printers (IPP/CUPS) buffer entire pages before printing. They do not support character-by-character streaming. The entire experience depends on immediate character output, which only direct-connect printers (USB/parallel) support. | Stick to USB-LPT direct connection. Document this limitation clearly. |
| Rich text / Markdown rendering on paper | "Render markdown formatting on the printer." | Dot-matrix printers are plain text devices. Attempting to render markdown creates a complex translation layer for minimal benefit. Headers, lists, and emphasis lose meaning on 80-column paper. | Use minimal ESC/P formatting (bold/underline) for structure. Keep content plain text. The constraint IS the aesthetic. |
| GUI interface | "Add a window with settings, preview, etc." | This is a terminal tool for terminal people who want a physical output experience. A GUI adds a massive dependency surface (Tk/Qt/Electron) and fights the core identity. | Keep all configuration via CLI flags and a simple config file (TOML or JSON). |
| Printer driver management | "Support any printer via CUPS/drivers." | CUPS and driver stacks introduce buffering, spooling, and page-based output that destroy character-by-character streaming. Raw device writes are the only way to get the teletype effect. | Write raw bytes directly to the USB device. Document compatible printers (Epson LX-350, similar ESC/P compatible dot-matrix). |
| Multi-printer support | "Print to two printers simultaneously." | Adds synchronization complexity for a feature almost nobody will use. Different printers have different speeds, buffer sizes, and capabilities. | Support one printer at a time. Let users switch via `--device` flag. |
| Syntax highlighting on paper | "Color-code or format code output on paper." | Dot-matrix printers are monochrome. Even with multi-ribbon color printers, switching ribbon colors mid-line is extremely slow and unreliable. | Use indentation and ESC/P underline for code blocks. Keep it simple. The monochrome constraint is authentic. |
| Auto-updating / self-updating | "The tool should update itself." | Adds network requests, version checking, and file system writes for a tool that should be dead-simple. Updates break things. | Use standard `pip install --upgrade` workflow. |

## Feature Dependencies

```
[Claude Code CLI Wrapping]
    └──requires──> [Subprocess streaming infrastructure]
                       └──enables──> [Character-by-character output pacing]
                                         ├──enables──> [Typewriter sound effects]
                                         ├──enables──> [Variable character pacing]
                                         ├──enables──> [Screen mirroring]
                                         └──enables──> [ESC/P printer formatting]

[USB-LPT Printer Auto-Discovery]
    └──enables──> [Manual device selection fallback]
    └──enables──> [Printer status detection]
    └──enables──> [Graceful hardware disconnect handling]

[Split-screen terminal simulator]
    └──requires──> [Character-by-character output pacing]
    └──enhanced-by──> [Configurable printer ribbon style]

[Conversation transcript saving]
    └──independent (no hard dependencies)

[Clean exit and paper positioning]
    └──requires──> [USB-LPT Printer Auto-Discovery] (to know which device to send form feed to)

[Input echo to printer]
    └──requires──> [Character-by-character output pacing]
    └──requires──> [Screen mirroring]

[Session resume / continue]
    └──requires──> [Claude Code CLI Wrapping]
    └──enhanced-by──> [Conversation transcript saving]
```

### Dependency Notes

- **Character pacing requires subprocess streaming:** The pacing layer sits between the Claude CLI output stream and the printer/terminal output. The stream must exist before pacing can be applied.
- **Sound effects require character pacing:** Sounds are triggered per-character during the pacing loop. Without pacing, there's no hook point for audio.
- **Terminal simulator requires character pacing:** The simulator must reproduce the same timing behavior as physical printer output. It reuses the pacing engine with a terminal output backend instead of a device write backend.
- **Printer status detection requires auto-discovery:** You need to have found the USB device before you can query its status registers.
- **ESC/P formatting is optional and additive:** It enhances the output pipeline but the pipeline must work without it (for non-ESC/P printers or terminal-only mode).

## MVP Definition

### Launch With (v1)

Minimum viable product -- what's needed to validate the concept.

- [ ] Claude Code CLI wrapping with `stream-json` output parsing -- this is the foundation
- [ ] Character-by-character output pacing (configurable 50-100ms) -- this IS the experience
- [ ] USB-LPT printer auto-discovery + manual fallback -- hardware must work out of the box
- [ ] Split-screen terminal simulator -- enables development and no-hardware usage
- [ ] Screen mirroring -- see what's printing on screen
- [ ] Basic conversation transcript saving -- plain text file per session
- [ ] Clean exit with paper advance -- don't leave paper in an awkward position
- [ ] Graceful disconnect handling -- don't crash on USB unplug

### Add After Validation (v1.x)

Features to add once core is working.

- [ ] Typewriter sound effects -- add when the silent experience feels incomplete (it will)
- [ ] Variable character pacing by context -- add when uniform speed feels robotic
- [ ] ESC/P printer formatting (bold user input, normal Claude output) -- add when conversations are hard to read on paper
- [ ] ASCII art session headers -- add when printouts lack personality
- [ ] Input echo to printer -- add when users want full teletype authenticity
- [ ] Paper-aware line wrapping -- add when text wraps mid-word on paper
- [ ] Interactive speed control -- add when users complain about fixed speed

### Future Consideration (v2+)

Features to defer until product-market fit is established.

- [ ] Configurable printer ribbon style (terminal aesthetic) -- polish, not function
- [ ] Printer status detection -- nice for robustness but complex and adapter-dependent
- [ ] Session resume / continue -- useful but `claude -c` already handles this at the CLI level
- [ ] Multiple sound preset profiles (like daktilo's approach) -- defer until sound system proves valuable

## Feature Prioritization Matrix

| Feature | User Value | Implementation Cost | Priority |
|---------|------------|---------------------|----------|
| Claude Code CLI wrapping | HIGH | MEDIUM | P1 |
| Character-by-character pacing | HIGH | LOW | P1 |
| USB-LPT auto-discovery | HIGH | MEDIUM | P1 |
| Split-screen terminal simulator | HIGH | MEDIUM-HIGH | P1 |
| Screen mirroring | HIGH | LOW | P1 |
| Transcript saving | MEDIUM | LOW | P1 |
| Graceful disconnect handling | MEDIUM | MEDIUM | P1 |
| Clean exit / paper advance | MEDIUM | LOW | P1 |
| Typewriter sound effects | HIGH | MEDIUM | P2 |
| Variable character pacing | MEDIUM | LOW | P2 |
| ESC/P formatting | MEDIUM | MEDIUM | P2 |
| ASCII art headers | LOW | LOW | P2 |
| Input echo to printer | MEDIUM | LOW | P2 |
| Paper-aware line wrapping | MEDIUM | LOW | P2 |
| Interactive speed control | LOW | LOW | P2 |
| Printer ribbon terminal style | LOW | MEDIUM | P3 |
| Printer status detection | LOW | MEDIUM | P3 |
| Session resume passthrough | LOW | LOW | P3 |
| Sound preset profiles | LOW | MEDIUM | P3 |

**Priority key:**
- P1: Must have for launch
- P2: Should have, add when possible
- P3: Nice to have, future consideration

## Competitor Feature Analysis

There are no direct competitors -- this is a niche art/nostalgia project. But adjacent projects inform feature expectations:

| Feature | Drew DeVault Line Printer Hack | 80s Typewriter Linux Terminal (Hackaday) | Daktilo (keyboard sounds) | Cool-Retro-Term | Our Approach |
|---------|-------------------------------|----------------------------------------|--------------------------|----------------|--------------|
| Physical output | Yes (Epson LX-350 via `/dev/usb/lp9`) | Yes (Brother AX-25 via Arduino) | No (audio only) | No (visual only) | Yes (dot-matrix via USB-LPT) |
| Character-by-character | Yes (PTY output to device) | Yes (key-by-key emulation) | N/A | N/A | Yes (throttled streaming) |
| Sound effects | No (physical printer IS the sound) | No (physical mechanism IS the sound) | Yes (6 presets, configurable) | No | Yes (WAV playback for terminal mode, physical sound when printing) |
| Paper management | Yes (Epson escape sequences for feed control) | No (manual) | N/A | N/A | Yes (form feed on exit, line wrapping) |
| No-hardware fallback | No | No | N/A (no hardware needed) | N/A | Yes (split-screen terminal simulator) |
| AI integration | No (generic shell) | No (generic Linux terminal) | No | No | Yes (Claude Code wrapping) |
| Configuration | Hardcoded | Hardcoded | TOML config + CLI flags | JSON profiles | CLI flags + optional config file |
| Cross-platform | Linux only | Raspberry Pi only | Linux, macOS, Windows | Linux, macOS | macOS primary, Linux secondary |

**Our key differentiator:** The only tool combining AI conversation with physical typewriter output AND a no-hardware simulation mode. The others are either generic shell-to-printer hacks or purely visual/audio terminal nostalgia. We bridge AI and physical media.

## Sources

- [Drew DeVault: An old-school shell hack on a line printer](https://drewdevault.com/2019/10/30/Line-printer-shell-hack.html) -- Epson LX-350 line printer shell implementation, paper feed management, `/dev/usb/lp` device path (MEDIUM confidence)
- [Hackaday: Converting An 80s Typewriter Into A Linux Terminal](https://hackaday.com/2022/08/04/converting-an-80s-typewriter-into-a-linux-terminal/) -- Brother AX-25 typewriter terminal, keyboard matrix, escape sequence processing (MEDIUM confidence)
- [Hackaday: Line Printer Does Its Best Teletype Impression](https://hackaday.com/2019/12/03/line-printer-does-its-best-teletype-impression/) -- Teletype emulation on physical printers (MEDIUM confidence)
- [Daktilo GitHub](https://github.com/orhun/daktilo) -- Typewriter sound presets, TOML configuration, cross-platform keyboard monitoring (HIGH confidence, directly inspected)
- [Cool-Retro-Term GitHub](https://github.com/Swordfish90/cool-retro-term) -- CRT visual effects, scanlines, burn-in, terminal model emulation (HIGH confidence)
- [Claude Code CLI Reference](https://code.claude.com/docs/en/cli-reference) -- `--print`, `--output-format stream-json`, `--include-partial-messages` flags for programmatic use (HIGH confidence, official docs)
- [python-escpos documentation](https://python-escpos.readthedocs.io/en/latest/) -- USB printer class, `_raw()` method, device connection patterns (HIGH confidence, official docs)
- [PyUSB documentation](https://pyusb.github.io/pyusb/) -- USB device discovery with `usb.core.find()`, libusb backend (HIGH confidence, official docs)
- [aio-usb-hotplug PyPI](https://pypi.org/project/aio-usb-hotplug/) -- Async USB hotplug event detection (MEDIUM confidence)
- [Python asyncio subprocess documentation](https://docs.python.org/3/library/asyncio-subprocess.html) -- `create_subprocess_exec`, StreamReader, `stream.read(1)` for character-by-character reading (HIGH confidence, official docs)
- [ESC/P Wikipedia](https://en.wikipedia.org/wiki/ESC/P) -- Epson escape code reference for bold, italic, underline, font control (HIGH confidence)
- [Epson ESC/P Reference Manual](https://files.support.epson.com/pdf/general/escp2ref.pdf) -- Complete ESC/P2 command reference (HIGH confidence, official docs)
- [TerminalTextEffects GitHub](https://github.com/ChrisBuilds/terminaltexteffects) -- Terminal visual effects engine, ANSI sequences, no 3rd party deps (MEDIUM confidence)
- [Textual / Rich](https://realpython.com/python-textual/) -- TUI framework for split-screen terminal interface (MEDIUM confidence)
- [Pexpect documentation](https://pexpect.readthedocs.io/en/stable/) -- PTY wrapping, `interact()` method with output_filter for character-level stream processing (HIGH confidence, official docs)

---
*Feature research for: Teletype-style CLI printer interface*
*Researched: 2026-02-14*
