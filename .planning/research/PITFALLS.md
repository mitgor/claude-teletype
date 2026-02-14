# Pitfalls Research

**Domain:** USB-LPT printer interface, CLI subprocess wrapping, real-time character streaming, terminal UI, audio synchronization
**Researched:** 2026-02-14
**Confidence:** HIGH (verified with official docs, multiple corroborating sources)

## Critical Pitfalls

### Pitfall 1: Claude Code Subprocess Buffering Destroys Character-by-Character Streaming

**What goes wrong:**
The entire product premise depends on receiving Claude's output character-by-character in real time. Developers use `subprocess.Popen` with `stdout=PIPE` and expect characters to arrive incrementally. Instead, the OS pipe buffer (typically 64KB on macOS) fills up and delivers output in large chunks, destroying the typewriter effect. The output arrives in bursts of thousands of characters rather than one-by-one.

**Why it happens:**
POSIX pipes are **fully buffered** by default (not line-buffered) when the child process detects its stdout is a pipe rather than a TTY. Claude Code's streaming output mode (`--output-format stream-json`) writes JSON lines, but the pipe buffer batches these before the parent process sees them. Even `bufsize=0` on the Python side only controls the parent's read buffer -- it cannot force the child process to flush.

**How to avoid:**
1. Use `--output-format stream-json --verbose --include-partial-messages` which emits `content_block_delta` events with `text_delta` payloads as tokens arrive. Each event is a full JSON line terminated by newline, which makes line-by-line reading viable.
2. Use `asyncio.create_subprocess_exec()` with `asyncio.StreamReader` to read lines as they appear, or use a dedicated reading thread with `readline()` in a loop.
3. Do NOT use `communicate()` -- it waits for the process to finish, which defeats streaming entirely.
4. Test early by measuring inter-character arrival times. If you see >500ms gaps followed by bursts of many characters, buffering is the problem.

**Warning signs:**
- Characters arrive in bursts rather than individually during testing
- `time.time()` between successive characters shows near-zero gaps within bursts and long gaps between bursts
- Output works perfectly with short responses but degrades with longer ones (buffer fills up)

**Phase to address:**
Phase 1 (Core subprocess integration). This is the foundational data pipeline. If character-by-character streaming does not work, nothing downstream works.

---

### Pitfall 2: macOS USB Device Access Requires Root or Entitlements, Breaking Normal User Experience

**What goes wrong:**
The tool is built, tested with `sudo`, and ships. Users run it without `sudo` and get `USBError: [Errno 13] Access denied (insufficient permissions)`. The tool appears completely broken on first use.

**Why it happens:**
On macOS, `libusb` (which `pyusb` wraps) requires write access to USB device nodes. Unlike Linux where udev rules can grant per-device permissions, macOS controls USB access through kernel extension ownership and entitlements. If a kernel driver (KEXT) already claims the USB-LPT adapter, `libusb` cannot access it without detaching the kernel driver first, which requires either root privileges or the `com.apple.vm.device-access` entitlement (which is only available to signed apps with Apple's approval).

As of libusb 1.0.25+, `libusb_detach_kernel_driver()` is available on macOS, but it still requires root for most device classes.

**How to avoid:**
1. Design the USB access layer with **two backends**: (a) raw device file I/O via `/dev/usb/lp*` or `/dev/cu.*` where the OS exposes the device as a file descriptor (preferred, no `pyusb` needed); (b) `pyusb`/`libusb` as fallback.
2. On macOS, USB-to-parallel adapters often present as USB printer class devices. Check if macOS already exposes them through CUPS or as a character device. If so, simple `open('/dev/usblp0', 'wb')` works without elevated permissions.
3. Detect permission errors gracefully and print a clear message: "Run with sudo, or see troubleshooting guide" -- do not crash with a raw traceback.
4. Document the permission requirements in the README before users discover them the hard way.

**Warning signs:**
- Tool works in development (where developer uses `sudo` or has special permissions) but fails on fresh installs
- Only tested on one machine with one adapter model
- No permission error handling code exists

**Phase to address:**
Phase 2 (USB-LPT hardware interface). Design the device access abstraction from day one to handle the permission problem.

---

### Pitfall 3: Subprocess Pipe Deadlock on Bidirectional Communication

**What goes wrong:**
The tool sends prompts to Claude Code's stdin and reads responses from stdout. If Claude produces enough output to fill the OS pipe buffer (~64KB on macOS) while the parent process is blocked writing to stdin, both processes deadlock permanently. The tool hangs indefinitely with no error message.

**Why it happens:**
OS pipes have finite buffers. If the child's stdout pipe buffer fills while the parent is blocked on a synchronous `stdin.write()`, neither process can make progress. The child blocks trying to write more to stdout; the parent blocks trying to write to stdin. This is the classic subprocess deadlock documented in Python's own `subprocess` module warnings.

**How to avoid:**
1. Use `asyncio` for all subprocess I/O. `asyncio.create_subprocess_exec()` with `asyncio.StreamReader/Writer` handles concurrent reads and writes without deadlock.
2. If using threads instead, put stdin writes and stdout reads in separate threads -- never do both in the same thread.
3. Never use `process.stdin.write()` followed by `process.stdout.read()` synchronously in the same execution path.
4. Consider whether you even need stdin communication. If you invoke Claude Code with `-p "prompt"` for each interaction, you avoid bidirectional piping entirely -- each invocation is a one-shot read-only stream.

**Warning signs:**
- Tool freezes on long Claude responses
- Works for short answers, hangs on detailed ones
- No timeout mechanism in subprocess communication

**Phase to address:**
Phase 1 (Core subprocess integration). The architecture decision between `-p` one-shot mode vs. interactive stdin/stdout must be made upfront.

---

### Pitfall 4: Audio Playback Latency Makes Typewriter Effect Feel Wrong

**What goes wrong:**
Each character should trigger a typewriter key-click sound. With pygame's default mixer buffer (4096 samples), there is 50-100ms latency between triggering a sound and hearing it. At the target character pacing of 50-100ms, the sound for character N plays when character N+1 or N+2 is already visible. The experience feels disconnected and cheap rather than mechanical.

**Why it happens:**
Audio libraries use buffers to prevent glitches. Larger buffers mean higher latency but fewer dropouts. pygame's default buffer is tuned for games with background music, not for per-event sound effects at 10-20Hz frequency. Additionally, loading a sound file from disk on each keypress (rather than pre-loading) adds disk I/O latency.

**How to avoid:**
1. Use `simpleaudio` instead of `pygame.mixer` -- it is designed for low-latency event-driven playback of short WAV files and does not require initializing a full game framework.
2. Pre-load all sound effects into memory at startup (key click, carriage return ding, line feed). Never load from disk per character.
3. If using pygame, initialize the mixer with a small buffer: `pygame.mixer.pre_init(44100, -16, 1, 512)` -- buffer size 512 gives ~11ms latency at 44100Hz.
4. Play sounds in a dedicated thread or use the library's async playback. Do not block the character output loop waiting for audio to finish.
5. Use uncompressed `.wav` files, not `.mp3` or `.ogg` -- decoding compressed audio adds latency per play event.

**Warning signs:**
- Sound plays noticeably after the character appears on screen
- Sound timing drifts over long responses (accumulating latency)
- Audio glitches or pops between rapid character sounds
- CPU usage spikes during rapid character output

**Phase to address:**
Phase 3 (Audio/sound effects). Must be tested with the character pacing loop active, not in isolation.

---

### Pitfall 5: USB-LPT Adapters Are Not Real Parallel Ports -- pyparallel Will Not Work

**What goes wrong:**
Developer finds `pyparallel` (parallel port library) and builds the printer interface on top of it. Nothing works. The USB-LPT adapter is not a parallel port -- it is a USB device that speaks a USB printer protocol internally and has a parallel connector on the other end. `pyparallel` expects a hardware parallel port at I/O address `0x378`, which does not exist on any modern Mac.

**Why it happens:**
The name "USB-to-LPT adapter" is misleading. These devices are USB printer class devices, not parallel port pass-through devices. They accept data over USB bulk endpoints and translate it to parallel printer signals internally. The operating system sees a USB device, not a parallel port.

**How to avoid:**
1. Treat the USB-LPT adapter as a **USB printer class device**, not a parallel port.
2. Use one of: (a) raw device file I/O if the OS exposes it (`/dev/usb/lp*` on Linux, or through the CUPS subsystem on macOS); (b) `pyusb` to send raw bytes to the printer's USB bulk OUT endpoint; (c) `python-escpos` if the printer supports ESC/POS commands.
3. For plain dot-matrix printers, sending raw ASCII bytes to the device's output endpoint is sufficient -- no printer language needed. The printer interprets raw bytes as characters.
4. Test with `lsusb` (Linux) or `system_profiler SPUSBDataType` (macOS) to identify the adapter's vendor ID and product ID before writing any code.

**Warning signs:**
- Code references port addresses like `0x378`
- Dependencies include `pyparallel`
- Device detection code looks for `/dev/lp*` on macOS (these do not exist for USB adapters)

**Phase to address:**
Phase 2 (USB-LPT hardware interface). The correct device communication protocol must be determined before any hardware code is written.

---

### Pitfall 6: Terminal UI and Subprocess Output Compete for the Same TTY

**What goes wrong:**
The split-screen terminal UI (simulated printer view) uses curses or a TUI library that takes over the terminal. Meanwhile, Claude Code subprocess tries to detect terminal capabilities, or the tool tries to print debug output to stdout. The result is garbled display, cursor jumping, or the TUI framework crashing because someone else wrote to the terminal behind its back.

**Why it happens:**
Curses/TUI frameworks assume exclusive control of the terminal. They manage cursor position, screen regions, and escape sequences. If any other code writes directly to stdout (including debug print statements, logging to stderr that the terminal catches, or the subprocess itself trying to interact with the terminal), the display corrupts.

**How to avoid:**
1. Ensure the Claude Code subprocess has NO direct terminal access. Use `subprocess.PIPE` for both stdout and stderr, never inherit the parent's TTY.
2. Route ALL logging through the TUI framework's own display mechanism (a log pane or status bar), never to raw stdout/stderr.
3. If using `Textual` (recommended over raw curses), it provides a proper logging facility and prevents accidental stdout writes from corrupting the display.
4. Wrap the subprocess with `env` variables to prevent it from detecting a TTY: set `TERM=dumb` or similar in the subprocess environment to prevent ANSI escape sequences in the output.
5. Test the TUI with the subprocess actively generating output -- display corruption only manifests under concurrent I/O.

**Warning signs:**
- Screen flickers or garbles when Claude responses arrive
- Cursor jumps to wrong position intermittently
- Works perfectly when tested without the TUI (just printing to stdout)
- `print()` statements in the codebase that go to raw stdout

**Phase to address:**
Phase 4 (Terminal simulator UI). Must be designed in coordination with Phase 1 subprocess output, as they share the terminal resource.

---

## Technical Debt Patterns

| Shortcut | Immediate Benefit | Long-term Cost | When Acceptable |
|----------|-------------------|----------------|-----------------|
| Synchronous subprocess I/O with threads | Faster to implement than asyncio | Thread safety bugs, harder to debug deadlocks, GIL contention with audio threads | Never -- asyncio is the right foundation for concurrent I/O + audio + UI |
| Hardcoded USB device vendor/product IDs | Works with one specific adapter | Breaks with any other adapter model, no auto-discovery | Only for initial hardware bring-up proof-of-concept, replace within same phase |
| Using `os.system()` or `subprocess.run()` for Claude Code | Quick prototype works | Cannot stream output, blocks until completion, no character-by-character capability | Never -- the core product requirement is streaming |
| Storing sound files as bundled MP3s | Smaller package size | Decode latency per play event, codec dependency, licensing concerns | Never -- WAV files are small enough for a few sound effects |
| Global mutable state for printer/audio handles | No need for dependency injection | Impossible to test, hard to swap implementations, simulator mode requires duplication | Only in earliest prototype, refactor before Phase 2 |

## Integration Gotchas

| Integration | Common Mistake | Correct Approach |
|-------------|----------------|------------------|
| Claude Code CLI | Using interactive mode and trying to parse TTY output with ANSI escape codes | Use `-p` flag with `--output-format stream-json --verbose --include-partial-messages` for clean, parseable JSON lines |
| Claude Code CLI | Assuming response is a single text block | Parse `stream_event` objects, filter for `content_block_delta` with `text_delta` type. Handle `tool_use` events, `result` events, and errors as distinct event types |
| pyusb/libusb on macOS | Calling `usb.core.find()` without installing libusb backend first | Install libusb via Homebrew (`brew install libusb`) before using pyusb. pyusb does not bundle libusb. |
| pyusb/libusb on macOS | Not detaching kernel driver before claiming interface | Call `dev.detach_kernel_driver(interface)` in a try/except before `dev.set_configuration()`. Requires root on macOS. |
| python-escpos with USB-to-Serial adapters | Using the USB driver class for USB-to-Serial devices | python-escpos USB driver is only for native USB devices. USB-to-Serial adapters need the Serial driver class instead. |
| simpleaudio | Assuming it works on all macOS versions out of the box | simpleaudio requires working CoreAudio. Test on target macOS version. Consider `sounddevice` as fallback. |

## Performance Traps

| Trap | Symptoms | Prevention | When It Breaks |
|------|----------|------------|----------------|
| Creating new sound objects per character | Memory grows over long conversations, audio latency increases | Pre-load a pool of `simpleaudio.WaveObject` instances at startup, reuse them | After ~1000 characters (a few paragraphs of output) |
| Unbounded conversation transcript in memory | Memory usage grows linearly with conversation length | Write transcript to disk incrementally, keep only recent context in memory | After ~100 exchanges or very long code outputs |
| Synchronous USB writes blocking the event loop | Character pacing becomes irregular, UI freezes during printer writes | Use async I/O or a dedicated printer writer thread with a queue | When printer is slow or USB bus is congested |
| Regex parsing of stream-json output | CPU spikes on long JSON lines with tool results | Use `json.loads()` per line, not regex. JSON lines format guarantees one object per line | When Claude returns large code blocks or file contents |
| Opening/closing USB device per print operation | Multi-second pauses between characters while device re-enumerates | Open device once at startup, keep handle alive, reconnect only on error | Immediately -- every character would trigger USB enumeration |

## Security Mistakes

| Mistake | Risk | Prevention |
|---------|------|------------|
| Running the entire tool with `sudo` because USB needs it | All of Claude Code's subprocess commands execute as root, including Bash tool calls that can modify system files | Elevate privileges ONLY for the USB device open, then drop back to user privileges. Or use device file permissions to avoid sudo entirely. |
| Logging Claude Code API keys or session tokens in transcripts | Transcript files could contain sensitive auth tokens visible in Claude Code's `stream-json` verbose output | Filter `stream_event` objects before logging -- only persist `text_delta` content, never raw event metadata or system messages |
| Storing conversation transcripts in world-readable locations | Other users on shared machines can read conversation history | Create transcript directory with `0o700` permissions, warn if directory permissions are too open |

## UX Pitfalls

| Pitfall | User Impact | Better Approach |
|---------|-------------|-----------------|
| No feedback during Claude's "thinking" time before first token | User thinks tool is frozen -- no output for 2-10 seconds while Claude processes | Show a visual indicator (blinking cursor, spinner, or "thinking..." text on the printer/terminal) until the first `text_delta` event arrives |
| Typewriter sound plays during code blocks at same speed as prose | Code output sounds identical to text, loses the "reading" feel; long code blocks take forever | Detect code blocks (markdown fences in `text_delta`) and optionally speed up character pacing or use a different sound for code |
| No way to interrupt/stop a long print | User must wait for entire response to print character-by-character, even if they see the answer early | Support Ctrl+C to stop printing but keep the full response available in the transcript |
| Carriage return / line feed timing identical to regular characters | Line breaks feel identical to character output -- no mechanical "carriage return" feel | Add a longer pause and distinct "ding" sound on newlines, shorter pause on regular characters, mimicking physical carriage return mechanics |
| Printer simulation mode looks nothing like a real printer | Users without hardware feel like they are using a worse terminal | Make the simulator visually reference dot-matrix output: fixed-width font, greenbar paper aesthetic, visible character-by-character rendering |

## "Looks Done But Isn't" Checklist

- [ ] **USB auto-discovery:** Often missing fallback for adapters that report non-standard USB class codes -- verify with 2-3 different adapter brands
- [ ] **Character encoding:** Often only tested with ASCII -- verify with Unicode characters in Claude's responses (curly quotes, em-dashes, code symbols). Dot-matrix printers may only support specific code pages.
- [ ] **Subprocess cleanup:** Often missing graceful shutdown of Claude Code process on Ctrl+C -- verify the child process is terminated, not orphaned
- [ ] **Long conversation handling:** Often only tested with single Q&A -- verify with 10+ exchanges that session continuation (`--continue` / `--resume`) works correctly through the wrapper
- [ ] **Printer offline handling:** Often crashes if printer is disconnected mid-print -- verify graceful degradation to simulator mode on USB disconnect
- [ ] **Line width handling:** Often ignores physical printer column width (typically 80 columns) -- verify word wrap at correct column, not at terminal width
- [ ] **Sound file licensing:** Often uses sound effects downloaded from the internet without checking license -- verify all audio assets are CC0/public domain or self-recorded
- [ ] **macOS Gatekeeper:** Often forgets that downloaded Python tools may trigger security warnings -- verify the install process works without Gatekeeper/quarantine issues

## Recovery Strategies

| Pitfall | Recovery Cost | Recovery Steps |
|---------|---------------|----------------|
| Wrong subprocess architecture (synchronous instead of async) | HIGH | Rewrite the core event loop from sync to async. Affects every component that touches subprocess output. Must be caught in Phase 1. |
| Wrong USB library choice (pyparallel instead of pyusb) | MEDIUM | Swap library, rewrite device communication layer. Contained to one module if device abstraction exists. |
| Audio latency from wrong library | LOW | Swap audio library (e.g., pygame to simpleaudio). Sound playback is a leaf dependency, not deeply integrated. |
| TTY corruption from mixed stdout | MEDIUM | Audit and redirect all output paths through TUI framework. Requires finding every print/logging call. |
| Hardcoded device IDs | LOW | Add auto-discovery scan. Small change if device access is properly abstracted. |
| No permission error handling | LOW | Add try/except around device open with clear error messages. Quick fix but embarrassing if shipped without. |

## Pitfall-to-Phase Mapping

| Pitfall | Prevention Phase | Verification |
|---------|------------------|--------------|
| Subprocess buffering kills streaming | Phase 1: Core subprocess integration | Measure inter-character arrival time; must be consistent, not bursty |
| macOS USB permission errors | Phase 2: USB-LPT hardware interface | Test on clean macOS install without sudo |
| Subprocess pipe deadlock | Phase 1: Core subprocess integration | Stress test with 5000+ word Claude responses while sending new prompts |
| Audio playback latency | Phase 3: Sound effects | Time delta between character display and sound playback start; must be <20ms |
| USB-LPT is not a parallel port | Phase 2: USB-LPT hardware interface | Code review: no references to pyparallel, port addresses, or /dev/lp* |
| Terminal UI vs subprocess TTY conflict | Phase 4: Terminal simulator | Run full integration test: subprocess + TUI + audio simultaneously for 5 minutes |
| Subprocess architecture choice (sync vs async) | Phase 1: Core subprocess integration | Architecture review before implementation: must be asyncio-based |
| Character encoding on printer | Phase 2: USB-LPT hardware interface | Send Unicode test string to printer, verify output or graceful fallback to ASCII |
| No thinking/loading feedback | Phase 1: Core subprocess integration | Observe tool with 5-second response delay; must show activity indicator |
| Printer disconnect mid-session | Phase 2: USB-LPT hardware interface | Unplug USB during active print; tool must switch to simulator without crash |

## Sources

- [Python subprocess documentation](https://docs.python.org/3/library/subprocess.html) -- deadlock warnings, buffering behavior
- [Python asyncio subprocess documentation](https://docs.python.org/3/library/asyncio-subprocess.html) -- async subprocess streaming
- [Claude Code headless/programmatic docs](https://code.claude.com/docs/en/headless) -- stream-json format, partial messages
- [Capture Python subprocess output in real-time](https://lucadrf.dev/blog/python-subprocess-buffers/) -- buffering analysis
- [libusb macOS kernel driver detach PR #911](https://github.com/libusb/libusb/pull/911) -- macOS device access limitations
- [libusb FAQ](https://github.com/libusb/libusb/wiki/FAQ) -- kernel driver conflicts
- [pyusb permission issues on macOS (#208)](https://github.com/pyusb/pyusb/issues/208) -- Access denied errors
- [pyusb device not found on macOS M1 (#482)](https://github.com/pyusb/pyusb/discussions/482) -- hardware compatibility
- [python-escpos documentation](https://python-escpos.readthedocs.io/en/latest/user/printers.html) -- USB vs Serial driver distinction
- [Python curses programming HOWTO](https://docs.python.org/3/howto/curses.html) -- terminal UI pitfalls
- [Textual TUI framework](https://github.com/Textualize/textual) -- modern terminal UI alternative
- [pygame mixer lag discussion](https://groups.google.com/g/pygame-mirror-on-google-groups/c/mP2P3QfSoV4) -- audio buffer sizing
- [python-sounddevice threading issues (#187)](https://github.com/spatialaudio/python-sounddevice/issues/187) -- GIL and audio threading
- [PTY pseudo-terminal pitfalls](https://runebook.dev/en/docs/python/library/pty) -- macOS pty safety concerns

---
*Pitfalls research for: USB-LPT printer CLI wrapper with real-time character streaming*
*Researched: 2026-02-14*
