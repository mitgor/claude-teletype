# Architecture Research

**Domain:** Python CLI tool — hardware I/O (USB-LPT printer), subprocess wrapping (Claude Code), audio playback, terminal UI (split-screen)
**Researched:** 2026-02-14
**Confidence:** HIGH (well-understood domains; Python subprocess, curses, USB I/O, and audio all have mature ecosystem patterns)

## Standard Architecture

### System Overview

```
┌─────────────────────────────────────────────────────────────────────┐
│                         Application Layer                           │
│  ┌──────────────┐  ┌──────────────┐  ┌──────────────┐              │
│  │  CLI Entry   │  │  Session      │  │  Config      │              │
│  │  (argparse)  │  │  Manager      │  │  Manager     │              │
│  └──────┬───────┘  └──────┬───────┘  └──────┬───────┘              │
│         │                 │                  │                      │
├─────────┴─────────────────┴──────────────────┴──────────────────────┤
│                         Orchestrator Layer                           │
│  ┌──────────────────────────────────────────────────────────────┐   │
│  │                      Main Event Loop                         │   │
│  │               (asyncio — coordinates all I/O)                │   │
│  └──────┬───────────────┬───────────────┬──────────────┬───────┘   │
│         │               │               │              │           │
├─────────┴───────────────┴───────────────┴──────────────┴───────────┤
│                         Service Layer                               │
│  ┌────────────┐ ┌────────────┐ ┌────────────┐ ┌────────────────┐   │
│  │ Claude     │ │ Printer    │ │ Audio      │ │ Terminal UI    │   │
│  │ Bridge     │ │ Driver     │ │ Engine     │ │ Renderer       │   │
│  └─────┬──────┘ └─────┬──────┘ └─────┬──────┘ └──────┬─────────┘  │
│        │              │              │               │             │
├────────┴──────────────┴──────────────┴───────────────┴─────────────┤
│                         Adapter Layer                               │
│  ┌────────────┐ ┌────────────┐ ┌────────────┐ ┌────────────────┐   │
│  │ subprocess │ │ pyusb /    │ │ sounddevice│ │ curses         │   │
│  │ (asyncio)  │ │ file I/O   │ │ / AppKit   │ │                │   │
│  └────────────┘ └────────────┘ └────────────┘ └────────────────┘   │
│                                                                     │
│  ┌────────────────────────────────────────────────────────────────┐ │
│  │                     Transcript Store                           │ │
│  │                (plain text file on disk)                       │ │
│  └────────────────────────────────────────────────────────────────┘ │
└─────────────────────────────────────────────────────────────────────┘
```

### Component Responsibilities

| Component | Responsibility | Typical Implementation |
|-----------|----------------|------------------------|
| **CLI Entry** | Parse args, detect hardware, select mode, launch event loop | `argparse` or `click`; `main()` entrypoint |
| **Config Manager** | Manage device paths, timing params, sound toggle, transcript path | Dataclass or dict; CLI flags override defaults |
| **Session Manager** | Track conversation state, handle start/continue/quit lifecycle | Manages Claude Code session IDs for `--resume` |
| **Main Event Loop** | Coordinate concurrent tasks: subprocess I/O, printer writes, audio, UI refresh | `asyncio.run()` with `create_task()` per concern |
| **Claude Bridge** | Spawn Claude Code subprocess, parse NDJSON stream, extract text tokens | `asyncio.create_subprocess_exec()` with `stdout=PIPE` |
| **Printer Driver** | Discover USB-LPT device, write bytes character-by-character with throttling | `pyusb` bulk transfer or raw file I/O to device node |
| **Audio Engine** | Play typewriter key-click and carriage-return sounds on each character/newline | Pre-loaded WAV buffers, fire-and-forget playback |
| **Terminal UI Renderer** | Split-screen display: input pane (top) + output pane (bottom), scrolling | `curses` windows with `newpad()` for scrollable regions |
| **Transcript Store** | Append each character to a plain text file as it flows through | Simple `open(path, 'a')` writes, flushed per line |

## Recommended Project Structure

```
claude-teletype/
├── pyproject.toml          # Project metadata, dependencies, entry point
├── src/
│   └── claude_teletype/
│       ├── __init__.py
│       ├── __main__.py     # Entry: `python -m claude_teletype`
│       ├── cli.py          # Argument parsing, mode selection, startup
│       ├── config.py       # Configuration dataclass, defaults
│       ├── loop.py         # Main asyncio orchestrator
│       ├── bridge.py       # Claude Code subprocess management
│       ├── printer/
│       │   ├── __init__.py
│       │   ├── discovery.py    # USB-LPT device auto-detection
│       │   ├── usb_driver.py   # pyusb bulk transfer writer
│       │   ├── file_driver.py  # /dev/usb/lp* file-based writer
│       │   └── null_driver.py  # No-op driver (simulator mode)
│       ├── audio.py        # Sound effect loading and playback
│       ├── ui/
│       │   ├── __init__.py
│       │   ├── terminal.py     # curses split-screen renderer
│       │   └── simulator.py    # Printer simulation pane (replaces hardware)
│       ├── transcript.py   # Conversation file writer
│       └── charflow.py     # Character-by-character throttle + fan-out
├── sounds/
│   ├── keystroke.wav       # Typewriter key click
│   └── carriage_return.wav # Line-end ding/return sound
└── tests/
    ├── test_bridge.py
    ├── test_charflow.py
    ├── test_printer_discovery.py
    └── test_transcript.py
```

### Structure Rationale

- **`src/claude_teletype/`:** Single-package layout. The `src/` prefix prevents accidental imports of uninstalled code during development.
- **`printer/`:** Separate sub-package because USB discovery, USB driver, file driver, and null driver are distinct concerns with a shared interface (write bytes). Strategy pattern via a common protocol.
- **`ui/`:** Separate sub-package because the terminal renderer and simulator pane have distinct rendering logic but share the same data feed (the character stream).
- **`charflow.py`:** Central "character flow" module that sits between the Claude Bridge (source) and all consumers (printer, UI, audio, transcript). This is the fan-out point and the single place where throttling/pacing lives.
- **`sounds/`:** Bundled WAV assets. Small files (~10-50KB each). Ship with the package via `package_data` in pyproject.toml.

## Architectural Patterns

### Pattern 1: Async Fan-Out via Character Channel

**What:** A single async generator or `asyncio.Queue` receives characters from Claude Bridge and distributes them to all consumers (printer, UI, audio, transcript) concurrently.
**When to use:** When one producer feeds multiple consumers that each process at different speeds.
**Trade-offs:** Clean separation of concerns and easy to add/remove consumers. Slightly more complex than synchronous sequential writes, but necessary because printer I/O and audio playback are blocking operations that must not stall the UI.

**Example:**
```python
import asyncio

class CharacterFlow:
    """Fan-out: one character from Claude → multiple consumers."""

    def __init__(self, delay_ms: float = 75.0):
        self._delay = delay_ms / 1000.0
        self._consumers: list[asyncio.Queue] = []

    def subscribe(self) -> asyncio.Queue:
        q: asyncio.Queue[str | None] = asyncio.Queue()
        self._consumers.append(q)
        return q

    async def feed(self, char: str) -> None:
        for q in self._consumers:
            await q.put(char)
        await asyncio.sleep(self._delay)  # Typewriter pacing

    async def close(self) -> None:
        for q in self._consumers:
            await q.put(None)  # Sentinel
```

### Pattern 2: Strategy Pattern for Printer Backend

**What:** A common `PrinterDriver` protocol with multiple implementations (USB, file, null). The CLI selects the implementation at startup based on hardware discovery.
**When to use:** When the same operation (write bytes to printer) has fundamentally different transports depending on runtime conditions.
**Trade-offs:** Clean abstraction boundary, easy testing (null driver), straightforward fallback chain. Minimal overhead since selection happens once at startup.

**Example:**
```python
from typing import Protocol

class PrinterDriver(Protocol):
    async def write_char(self, char: str) -> None: ...
    async def flush_line(self) -> None: ...
    def close(self) -> None: ...

class USBPrinterDriver:
    """Writes to USB-LPT device via pyusb bulk transfer."""
    def __init__(self, device):
        self._dev = device
        self._endpoint = self._find_bulk_out_endpoint()

    async def write_char(self, char: str) -> None:
        await asyncio.to_thread(
            self._dev.write, self._endpoint.bEndpointAddress, char.encode('ascii')
        )

class NullPrinterDriver:
    """No-op driver when no hardware attached."""
    async def write_char(self, char: str) -> None:
        pass  # Simulator mode — UI handles display

    async def flush_line(self) -> None:
        pass

    def close(self) -> None:
        pass
```

### Pattern 3: Curses Split-Screen with Async Input Loop

**What:** Two curses windows (input pane + output pane) managed by the asyncio event loop. Keyboard input is polled non-blocking via `window.nodelay(True)` inside an async task. Output pane receives characters from the fan-out queue.
**When to use:** When you need simultaneous keyboard input capture and streaming output display in the same terminal.
**Trade-offs:** Curses is universally available (stdlib) and fast, but has a steep learning curve and raw API. Alternative: Textual is more ergonomic but adds a heavy dependency. For this project, curses is the right call — the UI is simple (two panes), and Textual would be overkill.

**Example:**
```python
import curses
import asyncio

class TerminalUI:
    def __init__(self, stdscr):
        height, width = stdscr.getmaxyx()
        mid = height // 2
        self._input_win = curses.newwin(mid, width, 0, 0)
        self._output_win = curses.newwin(height - mid, width, mid, 0)
        self._input_win.nodelay(True)   # Non-blocking key reads
        self._input_win.scrollok(True)
        self._output_win.scrollok(True)

    async def read_input(self) -> str | None:
        """Non-blocking key read, yields to event loop."""
        ch = self._input_win.getch()
        if ch == -1:
            await asyncio.sleep(0.01)  # Yield
            return None
        return chr(ch)

    def write_output_char(self, char: str) -> None:
        self._output_win.addstr(char)
        self._output_win.refresh()
```

## Data Flow

### Primary Data Flow: User Question → Claude → Printer/Screen

```
[Keyboard]
    │ (raw keypress)
    ▼
[Terminal UI: Input Pane]  ←─── display echo
    │
    ▼ (accumulated line on Enter)
[CharacterFlow: User Input Fan-Out]
    ├──→ [Printer Driver] ──→ write char + CR/LF to hardware
    ├──→ [Audio Engine] ──→ play keystroke.wav per char
    └──→ [Transcript Store] ──→ append to file
    │
    ▼ (complete user prompt)
[Claude Bridge]
    │ spawn: claude -p --output-format stream-json --include-partial-messages "prompt"
    │ parse NDJSON lines from stdout
    │ extract text from content_block_delta events
    │
    ▼ (character stream from Claude)
[CharacterFlow: Assistant Output Fan-Out]
    ├──→ [Printer Driver] ──→ write char to hardware (throttled ~75ms)
    ├──→ [Terminal UI: Output Pane] ──→ addstr + refresh
    ├──→ [Audio Engine] ──→ play keystroke.wav per char, carriage_return.wav on \n
    └──→ [Transcript Store] ──→ append to file
```

### Secondary Flow: Hardware Discovery (Startup)

```
[CLI Entry]
    │
    ▼
[Printer Discovery]
    │ 1. pyusb.core.find() — scan for USB devices with printer class (0x07)
    │ 2. Check /dev/usb/lp* (Linux) or libusb enumeration (macOS)
    │ 3. If found → USBPrinterDriver or FilePrinterDriver
    │ 4. If not found → prompt user for manual path OR NullPrinterDriver
    │
    ▼
[Config Manager] → stores selected driver
    │
    ▼
[Main Event Loop] → uses selected driver for all output
```

### Claude Code Subprocess Communication

```
[Claude Bridge]
    │
    │  Spawn: asyncio.create_subprocess_exec(
    │      "claude", "-p",
    │      "--output-format", "stream-json",
    │      "--include-partial-messages",
    │      prompt_text,
    │      stdout=asyncio.subprocess.PIPE,
    │      stderr=asyncio.subprocess.PIPE
    │  )
    │
    │  Read stdout line-by-line (NDJSON):
    │  ┌──────────────────────────────────────────────────────────────┐
    │  │ {"type":"system", "session_id":"abc123", ...}               │ → store session ID
    │  │ {"type":"stream_event", "event":"content_block_delta",      │
    │  │  "data":{"delta":{"text":"H"}}}                             │ → emit "H" to CharacterFlow
    │  │ {"type":"stream_event", "event":"content_block_delta",      │
    │  │  "data":{"delta":{"text":"e"}}}                             │ → emit "e" to CharacterFlow
    │  │ ...                                                         │
    │  │ {"type":"assistant", "content":[{"type":"text","text":...}]}│ → complete message (ignore, already streamed)
    │  │ {"type":"result", "status":"success"}                       │ → signal done
    │  └──────────────────────────────────────────────────────────────┘
    │
    ▼
[CharacterFlow] → distributes each character to all consumers
```

### Key Data Flows

1. **User typing flow:** Keypress → echo to input pane + print to hardware + play click + append to transcript. All happen concurrently via fan-out. User sees characters appear immediately in the input pane while the printer and audio catch up.

2. **Claude response flow:** NDJSON stream → parse → extract delta text → character-by-character fan-out (throttled at ~75ms) to output pane, printer, audio, and transcript. The throttle is the deliberate typewriter pacing.

3. **Session continuity flow:** Claude Bridge stores the `session_id` from the `system` message. On subsequent prompts within the same session, it uses `--resume <session_id>` to maintain conversation context.

## Scaling Considerations

This is a single-user CLI tool, not a server. "Scaling" means handling edge cases gracefully.

| Concern | Approach |
|---------|----------|
| Long Claude responses (thousands of chars) | Curses output pane uses `scrollok(True)` and `pad` for scrollback. Printer just keeps printing. Transcript file grows. No memory issue — characters are processed and discarded. |
| Slow printer (hardware latency) | CharacterFlow queue buffers ahead. Printer consumer drains at its own pace. UI and transcript are not blocked. Back-pressure is natural — the queue just grows. For very slow printers, cap queue size and slow down Claude parsing. |
| Claude Code tool use (Bash, Edit, etc.) | Tool invocations appear as `tool_use` and `tool_result` NDJSON messages. Render a summary to the printer (e.g., `[Running: git status...]` and `[Tool output: 3 lines]`) rather than printing raw tool I/O. |
| Terminal resize | Handle `curses.KEY_RESIZE` in input loop. Recalculate window dimensions. Redraw borders. |
| Audio stacking (rapid characters) | Pre-load WAV into memory. Use fire-and-forget playback (non-blocking). If characters arrive faster than audio duration, overlap is fine — typewriter keys overlap in reality too. |

### Scaling Priorities

1. **First bottleneck: Printer throughput.** Dot-matrix printers at 80 columns might max out at ~200 chars/sec. The intentional 75ms throttle means ~13 chars/sec, well within limits. If the user reduces throttle, the printer becomes the bottleneck. Solution: the async queue naturally buffers.

2. **Second bottleneck: Audio overlap management.** Rapid character sequences produce overlapping sound effects. Solution: pre-load sounds into memory, use non-blocking playback, accept natural overlap. If it becomes cacophonous, add a minimum interval between audio triggers.

## Anti-Patterns

### Anti-Pattern 1: Synchronous Blocking I/O in the Event Loop

**What people do:** Call `device.write()` or `sound.play()` directly in the async event loop without `asyncio.to_thread()`.
**Why it's wrong:** USB bulk transfers and audio playback are blocking operations. They stall the entire event loop, freezing the UI and halting Claude stream parsing. Even 5ms of blocking per character compounds to visible lag.
**Do this instead:** Wrap all blocking I/O in `await asyncio.to_thread(blocking_call)`. USB writes, audio playback, and file I/O all go through this pattern.

### Anti-Pattern 2: Polling Claude Output Synchronously

**What people do:** Use `subprocess.Popen` with `stdout.readline()` in a while loop, blocking the main thread.
**Why it's wrong:** Cannot simultaneously handle keyboard input, printer writes, audio, and UI updates. The tool becomes unresponsive during Claude's thinking time.
**Do this instead:** Use `asyncio.create_subprocess_exec()` with `stdout=PIPE` and read from `process.stdout` asynchronously via `readline()` or `read(n)`.

### Anti-Pattern 3: Tightly Coupling Printer and UI Logic

**What people do:** Write printer output code and terminal display code in the same function, with if/else branches for "hardware mode" vs "simulator mode."
**Why it's wrong:** Makes testing impossible without hardware, makes adding new output targets (e.g., network stream, log file) require modifying existing code, and produces tangled state.
**Do this instead:** Use the CharacterFlow fan-out pattern. Each consumer subscribes independently. The printer driver is swapped at startup (strategy pattern). The UI always runs regardless of printer presence.

### Anti-Pattern 4: Re-implementing Claude Code's Auth/Session Logic

**What people do:** Try to call the Anthropic API directly, manage API keys, handle token limits, implement tool use, etc.
**Why it's wrong:** Claude Code already handles all of this. Wrapping the CLI preserves its auth, context window management, tool use, MCP servers, and session persistence for free.
**Do this instead:** Always delegate to `claude -p --output-format stream-json`. Parse the output. Do not attempt to replace Claude Code's internals.

## Integration Points

### External Services

| Service | Integration Pattern | Notes |
|---------|---------------------|-------|
| **Claude Code CLI** | `asyncio.create_subprocess_exec("claude", "-p", "--output-format", "stream-json", "--include-partial-messages", prompt)` | Requires Claude Code installed and authenticated. Parse NDJSON from stdout. Session management via `--resume <id>`. |
| **USB-LPT Printer** | `pyusb`: `usb.core.find(bDeviceClass=0x07)` → `dev.write(endpoint, bytes)`. File I/O fallback: `open("/dev/usb/lp0", "wb")`. | macOS: pyusb + libusb (install via `brew install libusb`). Linux: either pyusb or direct `/dev/usb/lp*` file writes. USB-LPT adapters can be unreliable — always have fallback. |
| **Audio subsystem** | `sounddevice` (preferred, PortAudio-based, Apple Silicon native) or macOS `AppKit.NSSound` via PyObjC. | Pre-load WAV files at startup. Use `sd.play(data, samplerate)` non-blocking. Avoid `simpleaudio` — archived project, unclear Apple Silicon support. |

### Internal Boundaries

| Boundary | Communication | Notes |
|----------|---------------|-------|
| CLI Entry → Main Loop | Function call, passes `Config` dataclass | One-way. CLI parses args, constructs config, hands off. |
| Claude Bridge → CharacterFlow | `asyncio.Queue.put(char)` | Bridge is the sole producer. One char at a time. `None` sentinel signals end of response. |
| CharacterFlow → Printer Driver | `asyncio.Queue.get()` → `driver.write_char()` | Consumer task. Runs `to_thread()` for blocking USB I/O. |
| CharacterFlow → Terminal UI | `asyncio.Queue.get()` → `ui.write_output_char()` | Consumer task. Curses calls must happen on main thread — use `loop.call_soon_threadsafe()` if needed. |
| CharacterFlow → Audio Engine | `asyncio.Queue.get()` → `audio.play_keystroke()` | Consumer task. Fire-and-forget, non-blocking. |
| CharacterFlow → Transcript Store | `asyncio.Queue.get()` → `file.write(char)` | Consumer task. Buffered writes, flush per line. |
| Terminal UI → Claude Bridge | User input line → `bridge.send_prompt(text)` | Triggered on Enter keypress. Bridge spawns new subprocess or resumes session. |

## Build Order (Dependency Chain)

The components have clear dependency relationships that dictate build order:

```
Phase 1: CLI + Config + Claude Bridge
    │     (Can test with terminal output alone — no printer, no UI, no audio)
    │
Phase 2: CharacterFlow (fan-out + throttling)
    │     (Depends on: Bridge as producer. Can test with print() as consumer.)
    │
Phase 3: Terminal UI (curses split-screen)
    │     (Depends on: CharacterFlow as data source. Replaces print() consumer.)
    │
Phase 4: Printer Discovery + Drivers
    │     (Depends on: CharacterFlow as data source. Adds a new consumer.)
    │     (Can develop with NullDriver first, real USB later.)
    │
Phase 5: Audio Engine
    │     (Depends on: CharacterFlow as data source. Adds a new consumer.)
    │     (Independent of printer and UI — can be built in any order after Phase 2.)
    │
Phase 6: Transcript Store
    │     (Depends on: CharacterFlow as data source. Adds a new consumer.)
    │     (Simplest consumer — can be built at any point after Phase 2.)
    │
Phase 7: Polish (session continuity, error handling, graceful shutdown, packaging)
```

**Build order rationale:**
- Phase 1 is the foundation — you cannot test anything without Claude Code integration.
- Phase 2 (CharacterFlow) is the architectural spine — every subsequent component plugs into it.
- Phases 3-6 are independent consumers that can be built in parallel once CharacterFlow exists. The suggested order prioritizes the most visible/complex components first (UI before printer before audio before transcript).
- Phase 7 is integration polish that benefits from all components being in place.

## Sources

- [Claude Code CLI Reference](https://code.claude.com/docs/en/cli-reference) — HIGH confidence. Official docs for `--output-format stream-json`, `--include-partial-messages`, `-p` flag.
- [Claude Agent SDK Spec (NDJSON format)](https://gist.github.com/SamSaffron/603648958a8c18ceae34939a8951d417) — MEDIUM confidence. Community-documented spec of stream-json message types.
- [Claude Flow Stream Chaining Wiki](https://github.com/ruvnet/claude-flow/wiki/Stream-Chaining) — MEDIUM confidence. Documents NDJSON message structure with examples.
- [PyUSB Documentation](https://pyusb.github.io/pyusb/) — HIGH confidence. Official pyusb docs for USB device discovery and bulk transfers.
- [PyUSB Tutorial (GitHub)](https://github.com/pyusb/pyusb/blob/master/docs/tutorial.rst) — HIGH confidence. Official tutorial for device enumeration and data transfer.
- [Python curses HOWTO](https://docs.python.org/3/howto/curses.html) — HIGH confidence. Official Python docs for curses windows, pads, and input handling.
- [Python asyncio subprocess docs](https://docs.python.org/3/library/asyncio-subprocess.html) — HIGH confidence. Official docs for async subprocess management.
- [sounddevice (GitHub)](https://github.com/spatialaudio/python-sounddevice) — HIGH confidence. Active project, PortAudio-based, cross-platform including Apple Silicon.
- [simpleaudio (PyPI)](https://pypi.org/project/simpleaudio/) — MEDIUM confidence. Archived project. Unclear Apple Silicon support. Not recommended.
- [python-escpos docs](https://python-escpos.readthedocs.io/en/latest/user/printers.html) — MEDIUM confidence. Documents USB printer class communication, warns about USB-LPT adapter reliability.
- [Apple CUPS libusb backend (GitHub)](https://github.com/apple/cups/blob/master/backend/usb-libusb.c) — MEDIUM confidence. Reference for how macOS communicates with USB printers via libusb.
- [Streaming subprocess output in Python](https://alexwlchan.net/til/2025/subprocess-line-by-line/) — MEDIUM confidence. Practical pattern for line-by-line subprocess output capture.
- [Textual TUI framework](https://johal.in/textual-tui-widgets-python-rich-terminal-user-interfaces-apps-2025/) — LOW confidence (considered but not recommended for this project). Overkill for two-pane layout.

---
*Architecture research for: Claude Teletype — Python CLI tool wrapping Claude Code with USB-LPT dot-matrix printer output*
*Researched: 2026-02-14*
