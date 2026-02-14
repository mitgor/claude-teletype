# Project Research Summary

**Project:** Claude Teletype
**Domain:** Python CLI tool — hardware printer interface, AI conversation wrapper, terminal UI
**Researched:** 2026-02-14
**Confidence:** MEDIUM-HIGH

## Executive Summary

Claude Teletype is a Python CLI tool that transforms Claude Code conversations into a physical typewriter/teletype experience, printing AI responses character-by-character to a dot-matrix printer via USB-LPT adapter while providing an authentic terminal simulation mode for users without hardware. This is a nostalgia/art project in a niche domain where USB-to-parallel printer communication on macOS is the highest-risk technical area, character-by-character streaming from Claude Code is the foundational requirement, and the typewriter pacing effect is the entire value proposition.

The recommended approach uses Python 3.12+ with asyncio-native architecture, Textual for the split-screen terminal UI, sounddevice for low-latency typewriter sound effects, and a tiered printer communication strategy (CUPS raw queue preferred, direct device file I/O fallback, virtual simulation for development). The Claude Code CLI wrapper uses `--output-format stream-json --include-partial-messages` to achieve token-level streaming via NDJSON parsing. The architecture centers on a character flow fan-out pattern where one async generator distributes characters from Claude to multiple consumers (printer, UI, audio, transcript) concurrently with configurable typewriter pacing.

Critical risks include subprocess buffering destroying the character-by-character effect, macOS USB device access requiring root or special permissions, subprocess pipe deadlock on bidirectional communication, and audio playback latency breaking the typewriter feel. Mitigation requires asyncio-based subprocess streaming from day one, tiered printer backend design with graceful permission failure, avoiding stdin/stdout bidirectional piping, and pre-loaded WAV buffers with low-latency playback. The USB-LPT printer path on macOS is inherently unreliable (USB-to-Parallel adapters are explicitly warned against in python-escpos) — the product must be designed simulation-first with hardware as a bonus feature, not hardware-dependent.

## Key Findings

### Recommended Stack

The stack research identified Python 3.12+ as the runtime with uv 0.10.x for package management (10-100x faster than pip/poetry, the 2025-2026 standard). Textual 7.5.0 provides the terminal UI framework with CSS-like layout and async-native architecture, sounddevice 0.5.5 handles low-latency audio playback via PortAudio, and asyncio (stdlib) coordinates all concurrent I/O.

**Core technologies:**
- **Python 3.12+**: Stable async runtime with significant perf improvements; 3.13 acceptable but 3.12 safer for library compatibility
- **Textual 7.5.0**: Dominant Python TUI framework with split-screen support, async-native, MIT licensed — modern alternative to raw curses
- **sounddevice 0.5.5**: PortAudio-based audio with async-compatible non-blocking playback; Jan 2026 release, actively maintained
- **asyncio (stdlib)**: Required to simultaneously read subprocess output, write to printer, play sounds, and update TUI — all character streaming is inherently async
- **CUPS raw queue**: Most reliable macOS printer path via `lp -o raw` — no Python library needed, just subprocess calls

**Printer communication strategy (tiered):**
1. **Tier 1 (preferred):** CUPS raw queue via `subprocess.run(["lp", "-o", "raw", "-d", printer])` — works on macOS and Linux with proper printer setup (MEDIUM confidence)
2. **Tier 2 (fallback):** Direct device file I/O to `/dev/usb/lp0` (Linux) or via libusb — rare on macOS (LOW confidence on macOS)
3. **Tier 3 (fallback):** PyUSB raw USB via pyusb 1.3.1 for native USB printers (not USB-LPT adapters) — requires libusb backend (MEDIUM confidence)
4. **Tier 4 (simulation):** Virtual printer in Textual widget with typewriter-style character rendering — development/demo mode (HIGH confidence)

**Critical finding:** USB-to-Parallel adapters are unreliable for programmatic control. The python-escpos project explicitly warns: "Stay away from USB-to-Parallel-Adapter since they are unreliable and produce arbitrary errors." The most reliable macOS path is configuring the printer as a CUPS raw queue, then using `lp -o raw` to send text.

### Expected Features

Feature research identified 8 table-stakes features (users expect these to exist), 11 differentiators (competitive advantage), and 6 anti-features (commonly requested but problematic).

**Must have (table stakes):**
- **Claude Code CLI wrapping** — the entire product is "Claude on paper," this is the foundation
- **Character-by-character output pacing** — the typewriter feel IS the core value, dumping text instantly defeats the purpose
- **USB-LPT printer auto-discovery** — users plug in hardware and expect it to work
- **Split-screen terminal simulator** — enables development and no-hardware usage for 90% of users
- **Screen mirroring** — when hardware is connected, users still need to see what's printing
- **Conversation transcript saving** — paper is ephemeral, digital backup is expected
- **Graceful hardware disconnect handling** — USB devices get unplugged, tool must not crash
- **Clean exit and paper positioning** — send form feed on exit to leave paper at tear-off point

**Should have (competitive advantage):**
- **Typewriter sound effects** — transforms experience from "text appearing" to "machine thinking on paper" (HIGH user value, MEDIUM complexity)
- **Variable character pacing by context** — punctuation gets longer pause (thinking), code gets faster (machine output) — creates organic human-like feel
- **Carriage return sound + line pause** — reproduce mechanical carriage return ding followed by brief pause for authenticity
- **ESC/P printer formatting** — bold for user prompts, normal for Claude responses, underline for code blocks on paper
- **Paper-aware line wrapping** — wrap at word boundaries for 80 or 132 column printers
- **Interactive speed control** — keyboard shortcuts to adjust character pacing mid-session
- **Session resume** — pass through `--resume` to Claude Code for multi-session conversations
- **Input echo to printer** — user's input prints character-by-character like real teletype

**Defer (v2+):**
- **Printer ribbon style in terminal** — render text with dot-matrix aesthetic (faded, uneven weight) in simulator mode
- **Printer status detection** — check if printer is online, has paper, not in error state (complex and adapter-dependent)
- **Sound preset profiles** — multiple sound themes like daktilo's approach

**Key anti-features (do NOT build):**
- **Direct Anthropic API integration** — reimplementing Claude Code's auth, tool use, context windows, MCP is months of work for worse experience
- **Network/remote printer support** — network printers buffer entire pages, cannot stream character-by-character
- **Rich text / Markdown rendering on paper** — dot-matrix printers are plain text devices, the constraint IS the aesthetic
- **GUI interface** — this is a terminal tool for terminal people, GUI adds massive dependency surface and fights core identity

### Architecture Approach

Architecture research identified a fan-out pattern where a central CharacterFlow async generator distributes characters from Claude Code to multiple consumers (printer, UI, audio, transcript) concurrently. The asyncio event loop coordinates all I/O without blocking. Printer backend uses strategy pattern with multiple implementations (USB, file, null) selected at startup based on hardware discovery.

**Major components:**
1. **Claude Bridge** — spawns Claude Code subprocess with `--output-format stream-json`, parses NDJSON stream, extracts text_delta tokens character-by-character
2. **CharacterFlow** — central fan-out point that receives characters from Claude Bridge and distributes to all consumers with configurable typewriter pacing (75ms default)
3. **Printer Driver (strategy pattern)** — USBPrinterDriver, FilePrinterDriver, or NullPrinterDriver selected at startup; writes raw bytes to hardware or no-ops for simulator mode
4. **Terminal UI Renderer** — Textual split-screen (input pane + output pane) with scrolling, receives characters from CharacterFlow queue
5. **Audio Engine** — pre-loads WAV buffers at startup, plays keystroke.wav per character and carriage_return.wav per newline via non-blocking fire-and-forget
6. **Transcript Store** — simple file I/O, appends each character as it flows through the system

**Key patterns:**
- **Async Fan-Out via Character Channel**: One asyncio.Queue receives characters from Claude Bridge and distributes to all consumers concurrently at different speeds
- **Strategy Pattern for Printer Backend**: Common PrinterDriver protocol with USB/file/null implementations selected at runtime
- **Textual Split-Screen with Async Input Loop**: Two windows (input + output) managed by asyncio event loop, non-blocking keyboard input

**Data flow:**
```
[Claude Bridge] → parse NDJSON stream → extract text_delta
    ↓
[CharacterFlow] → throttle at ~75ms per char
    ├→ [Printer Driver] → USB write
    ├→ [Terminal UI] → addstr + refresh
    ├→ [Audio Engine] → play keystroke.wav
    └→ [Transcript Store] → append to file
```

### Critical Pitfalls

Research identified 6 critical pitfalls that will break the product if not addressed in the correct phases.

1. **Claude Code subprocess buffering destroys character-by-character streaming** — OS pipe buffers (64KB on macOS) batch output in chunks of thousands of characters instead of one-by-one, destroying the typewriter effect. **Prevention:** Use `--output-format stream-json --include-partial-messages` with `asyncio.create_subprocess_exec()` and `StreamReader.readline()` to get NDJSON events as they arrive. Never use `communicate()` which waits for completion. Test early by measuring inter-character arrival times.

2. **macOS USB device access requires root or entitlements** — Users run tool without sudo and get "Access denied" errors, tool appears broken. **Prevention:** Design USB access layer with two backends: raw device file I/O via `/dev/usb/lp*` (preferred, no pyusb needed) and pyusb/libusb as fallback. Detect permission errors gracefully with clear error messages, not raw tracebacks.

3. **Subprocess pipe deadlock on bidirectional communication** — If Claude produces enough output to fill pipe buffer while parent is blocked writing to stdin, both processes deadlock permanently. **Prevention:** Use asyncio for all subprocess I/O with concurrent reads and writes, or avoid bidirectional piping entirely by using `-p "prompt"` one-shot mode instead of stdin/stdout interaction.

4. **Audio playback latency makes typewriter effect feel wrong** — Default pygame mixer buffer (4096 samples) causes 50-100ms latency; sound for character N plays when character N+2 is already visible. **Prevention:** Use sounddevice instead of pygame (designed for low-latency event playback), pre-load all WAV files into memory at startup, use non-blocking playback, never load from disk per character.

5. **USB-LPT adapters are not real parallel ports** — Developer uses pyparallel library expecting hardware parallel port at I/O address 0x378, nothing works because USB-LPT adapters are USB printer class devices. **Prevention:** Treat adapters as USB devices, use raw device file I/O or pyusb bulk transfers, never reference port addresses or use pyparallel.

6. **Terminal UI and subprocess output compete for same TTY** — Textual/curses takes over terminal, Claude Code subprocess tries to detect terminal capabilities or debug prints go to stdout, display garbles or framework crashes. **Prevention:** Subprocess gets NO direct terminal access (stdout=PIPE, stderr=PIPE), route ALL logging through TUI framework's display mechanism, set `TERM=dumb` in subprocess environment.

## Implications for Roadmap

Based on research, suggested 7-phase structure organized around the CharacterFlow architectural spine with clear dependency chain:

### Phase 1: Core Subprocess Integration
**Rationale:** Foundation layer — cannot test anything without Claude Code streaming working. Character-by-character streaming is the entire product. If this doesn't work, nothing downstream works.
**Delivers:** Claude Code CLI wrapper with streaming JSON parsing, character extraction, basic terminal output
**Addresses:** Claude Code CLI wrapping (table stakes), character-by-character pacing (table stakes)
**Avoids:** Subprocess buffering pitfall (#1), subprocess pipe deadlock pitfall (#3), subprocess architecture choice must be asyncio from day one
**Research flag:** Standard patterns (skip deep research) — well-documented subprocess + asyncio patterns

### Phase 2: CharacterFlow Fan-Out Architecture
**Rationale:** Architectural spine — every subsequent component plugs into this. Cannot build multiple consumers (printer, UI, audio, transcript) without the fan-out pattern.
**Delivers:** Async generator/queue that receives characters from Bridge and distributes to N consumers with configurable pacing
**Uses:** asyncio queues, async generators
**Implements:** CharacterFlow component from architecture
**Avoids:** Tightly coupling printer and UI logic (architecture anti-pattern)
**Research flag:** Standard patterns (skip deep research) — pub/sub and fan-out are well-established async patterns

### Phase 3: Terminal UI Simulator
**Rationale:** Most development and demo use happens without hardware. Without this, tool is unusable for 90% of users. Can develop with CharacterFlow as data source before printer hardware exists.
**Delivers:** Textual split-screen (input pane + output pane) with scrolling, character-by-character rendering with typewriter pacing
**Addresses:** Split-screen terminal simulator (table stakes), screen mirroring (table stakes)
**Uses:** Textual 7.5.0, asyncio
**Implements:** Terminal UI Renderer and Input Loop components
**Avoids:** Terminal UI vs subprocess TTY conflict pitfall (#6)
**Research flag:** Needs research — Textual layout system and async integration patterns are complex, consult official docs during implementation

### Phase 4: USB-LPT Hardware Interface
**Rationale:** Hardware is the differentiator but must not block development. Comes after simulator so product works without hardware. Strategy pattern allows swapping backends.
**Delivers:** USB-LPT auto-discovery, CUPS raw queue driver, device file driver, graceful permission handling, disconnect detection
**Addresses:** USB-LPT printer auto-discovery (table stakes), manual device selection fallback (table stakes), graceful hardware disconnect handling (table stakes), clean exit and paper positioning (table stakes)
**Uses:** pyusb 1.3.1, libusb, subprocess for CUPS lp command
**Implements:** Printer Driver strategy pattern components
**Avoids:** macOS USB permission errors pitfall (#2), USB-LPT is not parallel port pitfall (#5), printer offline handling gaps
**Research flag:** Needs research — USB-LPT adapter communication on macOS is highest-risk area with LOW confidence; will need hardware-specific research for adapter models during implementation

### Phase 5: Audio Engine
**Rationale:** Independent consumer that can be built after CharacterFlow exists. High user value but not blocking other features. Sound effects transform experience from visual to sensory.
**Delivers:** Pre-loaded WAV buffers, non-blocking keystroke and carriage return sound playback, sound toggle
**Addresses:** Typewriter sound effects (differentiator), carriage return sound + line pause (differentiator)
**Uses:** sounddevice 0.5.5, numpy for audio buffers
**Implements:** Audio Engine component
**Avoids:** Audio playback latency pitfall (#4), performance trap of creating new sound objects per character
**Research flag:** Standard patterns (skip deep research) — sounddevice is well-documented, pre-loading WAV files is straightforward

### Phase 6: Transcript and Session Management
**Rationale:** Simplest consumer — just file I/O. Can be built any time after CharacterFlow. Essential for conversation persistence but low complexity.
**Delivers:** Plain text file per session with timestamped conversations, session resume passthrough to Claude Code
**Addresses:** Conversation transcript saving (table stakes), session resume (differentiator)
**Uses:** Python file I/O, Claude Code `--resume` flag
**Implements:** Transcript Store component
**Avoids:** Unbounded transcript in memory performance trap, logging Claude API keys in transcripts
**Research flag:** Standard patterns (skip deep research) — simple file I/O and CLI flag passthrough

### Phase 7: Polish and Enhancement
**Rationale:** After core pipeline works, add features that improve experience. Variable pacing, ESC/P formatting, paper wrapping are polish, not foundation.
**Delivers:** Variable character pacing by context (punctuation/code/prose), ESC/P formatting for bold user input, paper-aware line wrapping, interactive speed control, ASCII art session headers, input echo to printer
**Addresses:** Variable character pacing (differentiator), ESC/P formatting (differentiator), paper-aware line wrapping (differentiator), interactive speed control (differentiator), ASCII art headers (differentiator), input echo (differentiator)
**Uses:** ESC/P escape codes, pyfiglet, character class detection
**Avoids:** UX pitfalls (no thinking indicator, code blocks sound identical to prose, no interrupt mechanism)
**Research flag:** Needs research for ESC/P — printer-specific escape codes require reference manual lookup during implementation

### Phase Ordering Rationale

- **Phases 1-2 are the foundation**: Claude Bridge + CharacterFlow must work before anything else. Character-by-character streaming is the entire product.
- **Phase 3 (UI) before Phase 4 (printer)**: Simulator mode is the development environment and fallback. Build what 90% of users will use first, hardware second.
- **Phases 3-6 are independent consumers**: Once CharacterFlow exists, UI, printer, audio, and transcript can be built in parallel or any order. Suggested order prioritizes most visible/complex first.
- **Phase 7 is polish**: Enhancement features that improve experience but aren't blocking the core pipeline.
- **This order avoids critical pitfalls**: Asyncio architecture locked in Phase 1, prevents later refactor. Simulator built before printer prevents hardware dependency. Permission handling designed into Phase 4 from start.

### Research Flags

**Phases likely needing deeper research during planning:**
- **Phase 3 (Terminal UI):** Textual layout system and async integration patterns are complex; consult official Textual docs and examples for split-screen setup
- **Phase 4 (USB-LPT Hardware):** USB-LPT adapter communication on macOS is highest-risk area with LOW confidence; will need hardware-specific research for different adapter models, CUPS raw queue setup instructions, and macOS libusb permission handling
- **Phase 7 (ESC/P Formatting):** Printer-specific escape codes require ESC/P reference manual lookup; codes vary between Epson, Star, and other manufacturers

**Phases with standard patterns (skip research-phase):**
- **Phase 1 (Subprocess):** asyncio subprocess streaming is well-documented in Python docs, NDJSON parsing is straightforward
- **Phase 2 (CharacterFlow):** pub/sub and fan-out are established async patterns with abundant examples
- **Phase 5 (Audio):** sounddevice is well-documented, pre-loading WAV files is a standard audio programming pattern
- **Phase 6 (Transcript):** simple file I/O and CLI flag passthrough, no deep research needed

## Confidence Assessment

| Area | Confidence | Notes |
|------|------------|-------|
| Stack | MEDIUM-HIGH | Core libraries verified via PyPI (HIGH confidence); printer I/O path has LOW confidence due to macOS USB-LPT adapter limitations and lack of hardware testing |
| Features | HIGH | Table stakes and differentiators are well-scoped based on competitor analysis and Drew DeVault's line printer implementation; anti-features prevent scope creep |
| Architecture | HIGH | Well-understood domains — Python subprocess, asyncio, TUI frameworks, USB I/O, and audio all have mature ecosystem patterns; fan-out pattern is proven |
| Pitfalls | HIGH | Critical pitfalls verified with official docs (subprocess deadlock, buffering) and corroborating sources (USB-LPT adapter warnings from python-escpos, libusb macOS issues) |

**Overall confidence:** MEDIUM-HIGH

Confidence is high for software architecture (subprocess, asyncio, TUI, audio) and medium for hardware integration (USB-LPT adapter reliability on macOS is inherently uncertain without testing multiple adapter models). The product must be designed simulation-first with hardware as a bonus feature.

### Gaps to Address

**USB-LPT adapter hardware compatibility** — Research is based on library documentation and community warnings, not testing with actual hardware. During Phase 4 implementation, will need to test with multiple USB-to-parallel adapter models to verify CUPS raw queue approach works reliably. If not, may need to pivot to simulation-only product or support only specific verified adapter models.

**NDJSON message format from Claude Code** — Research is based on community-documented spec and CLI reference, not live testing of `--output-format stream-json`. During Phase 1 implementation, actual message structure may differ from spec. Will need to inspect live output and adjust parsing logic.

**Textual layout performance with high-frequency updates** — Research assumes Textual can handle character-by-character updates at 75ms intervals without lag. During Phase 3 implementation, may need to batch multiple characters per UI refresh if per-character rendering is too slow.

**macOS permission model for USB devices** — Research identified that libusb requires root or entitlements but actual behavior varies by macOS version and adapter. During Phase 4 implementation, will need to test on multiple macOS versions (12/13/14) to determine if CUPS raw queue approach bypasses permission issues or if sudo is mandatory.

**ESC/P code compatibility across printers** — Research assumes ESC/P codes for bold/underline are standard across dot-matrix printers. During Phase 7 implementation, may discover that different printer models support different ESC/P command sets. Will need to test with target printers or make formatting optional with auto-detection fallback.

## Sources

### Primary (HIGH confidence)
- Textual PyPI and docs — version 7.5.0 verified, layout system and widgets documented
- sounddevice PyPI — version 0.5.5 released Jan 2026, PortAudio-based, actively maintained
- Python asyncio subprocess docs — official docs for async subprocess streaming patterns
- Claude Code CLI Reference — official docs for `--output-format stream-json`, `--include-partial-messages`
- pyusb PyPI and docs — version 1.3.1 released Jan 2025, USB device discovery and bulk transfers
- Python subprocess docs — deadlock warnings, buffering behavior officially documented

### Secondary (MEDIUM confidence)
- Drew DeVault line printer hack — Epson LX-350 via `/dev/usb/lp9`, paper feed management, real-world implementation
- python-escpos USB-LPT warning — "Stay away from USB-to-Parallel-Adapter since they are unreliable" from GitHub issue #214
- macOS CUPS raw printing setup — `lp -o raw` approach for raw byte sending
- Daktilo GitHub — typewriter sound presets, TOML configuration, cross-platform keyboard monitoring (inspected for sound effect patterns)
- Claude Agent SDK Spec NDJSON format — community-documented spec of stream-json message types
- libusb macOS kernel driver detach PR — macOS device access limitations and permission requirements

### Tertiary (LOW confidence, needs validation)
- USB-LPT adapter behavior on macOS — no first-hand testing, extrapolated from Linux behavior and library warnings
- NDJSON message structure details — based on community spec, not official Anthropic documentation
- Textual performance with high-frequency updates — assumed based on framework design, not stress-tested for this use case

---
*Research completed: 2026-02-14*
*Ready for roadmap: yes*
