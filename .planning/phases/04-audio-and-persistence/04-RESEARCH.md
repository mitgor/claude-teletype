# Phase 4: Audio and Persistence - Research

**Researched:** 2026-02-15
**Domain:** Audio playback (sounddevice/PortAudio), file persistence (plain text transcripts)
**Confidence:** HIGH

## Summary

Phase 4 adds two independent consumers to the existing character fan-out pipeline: (1) a bell/ding sound triggered on newline characters, and (2) a transcript writer that saves conversations to timestamped plain text files. Both features are architecturally simple -- they plug into the existing `make_output_fn(*destinations)` pattern as additional destination callables, or as observer wrappers around the output function.

The audio component uses `sounddevice` (already identified in stack research) with `numpy` to generate a short bell tone in-memory at startup. The `sd.play()` convenience function provides non-blocking fire-and-forget playback suitable for this use case -- it stops any previous playback before starting the new sound, which is acceptable since the bell only fires on newlines and rapid consecutive newlines should simply re-trigger cleanly.

The transcript component is the simplest possible consumer: accumulate characters into a buffer, flush to a timestamped file. No external dependencies beyond Python stdlib.

**Primary recommendation:** Implement audio and transcript as two thin modules (`audio.py` and `transcript.py`) that each expose a single callable matching the `Callable[[str], None]` output destination signature. Wire them into the existing `make_output_fn()` fan-out in both TUI and CLI paths.

## Standard Stack

### Core

| Library | Version | Purpose | Why Standard |
|---------|---------|---------|--------------|
| sounddevice | 0.5.5 | Audio playback via PortAudio | Actively maintained (Jan 2026 release). Cross-platform (macOS/Linux/Windows). Non-blocking `sd.play()` returns immediately. Pre-loads NumPy arrays for low-latency fire-and-forget playback. |
| numpy | latest stable | Generate bell tone waveform in-memory | Required by sounddevice's convenience API (`sd.play()` takes NumPy arrays). Also used to synthesize the bell tone programmatically -- no external WAV files needed. |

### Supporting

| Library | Version | Purpose | When to Use |
|---------|---------|---------|-------------|
| pathlib | stdlib | Transcript file path management | Always. Use `Path` for cross-platform path construction, `mkdir(parents=True, exist_ok=True)` for directory creation. |
| datetime | stdlib | Timestamp generation for transcript filenames | Always. `datetime.now().strftime()` for human-readable filenames. |

### Alternatives Considered

| Instead of | Could Use | Tradeoff |
|------------|-----------|----------|
| sounddevice + numpy | soundfile + bundled WAV | Adds a WAV file asset to manage and ship. soundfile is a heavier dependency than numpy for this use case. Generating the tone in-memory with numpy is zero external assets, ~10 lines of code. |
| sounddevice | pygame.mixer | 30+ MB dependency for a 200ms bell sound. Massive overkill. |
| sounddevice | simpleaudio | Abandoned since 2019 (v1.0.4). No Python 3.12+ testing. Will break. |
| In-memory tone generation | Bundled WAV files in sounds/ directory | WAV files add package_data complexity, asset management, licensing concerns. In-memory generation is deterministic, self-contained, and trivially customizable. |
| sd.play() convenience API | OutputStream with callback | Only needed for overlapping playback. Since the bell fires only on newlines (not every character), sd.play() is sufficient. It auto-stops previous playback before starting new, which is correct behavior for our case. |

**Installation:**
```bash
uv add sounddevice numpy
```

**System Dependencies (macOS):**
```bash
brew install portaudio
```

**System Dependencies (Linux):**
```bash
sudo apt install libportaudio2 portaudio19-dev
```

## Architecture Patterns

### Recommended Module Structure

```
src/claude_teletype/
    audio.py          # Bell sound generation + playback callable
    transcript.py     # Timestamped transcript writer callable
    output.py         # (existing) make_output_fn(*destinations)
    pacer.py          # (existing) pace_characters with output_fn
    tui.py            # (existing) wire audio + transcript into destinations
    cli.py            # (existing) wire audio + transcript into destinations
```

### Pattern 1: Audio Destination as Callable

**What:** A module-level function that generates the bell tone once at import/init time, then returns a `Callable[[str], None]` that plays the bell on newline characters and ignores all other characters.

**When to use:** When adding a new character-stream consumer that reacts to specific characters.

**Why this pattern:** Matches the existing `make_output_fn(*destinations)` signature. The audio destination is just another callable alongside `log.write`, `printer_write`, and `transcript_write`.

**Example:**
```python
# src/claude_teletype/audio.py
import numpy as np

def make_bell_output() -> Callable[[str], None]:
    """Create an output destination that plays a bell on newline characters.

    Generates the bell tone in-memory at creation time.
    Returns a callable matching the output_fn signature.
    """
    import sounddevice as sd

    # Generate bell tone: short sine wave with exponential decay
    sample_rate = 44100
    duration = 0.15  # 150ms -- short, crisp ding
    t = np.linspace(0, duration, int(sample_rate * duration), endpoint=False)
    frequency = 880  # A5 -- bright bell tone
    tone = np.sin(2 * np.pi * frequency * t)
    # Apply exponential decay envelope for bell-like character
    envelope = np.exp(-t * 20)
    bell = (tone * envelope).astype(np.float32)

    def bell_output(char: str) -> None:
        if char == "\n":
            sd.play(bell, samplerate=sample_rate)
            # Non-blocking: returns immediately, plays in background

    return bell_output
```

### Pattern 2: Transcript Destination as Callable

**What:** A callable that accumulates all characters and writes them to a timestamped file. The callable is created once per session, opening a file handle that persists for the session lifetime.

**When to use:** When persisting the character stream to disk.

**Example:**
```python
# src/claude_teletype/transcript.py
from datetime import datetime
from pathlib import Path
from collections.abc import Callable

def make_transcript_output(
    transcript_dir: Path | None = None,
) -> Callable[[str], None]:
    """Create an output destination that writes all characters to a transcript file.

    Creates a timestamped file in transcript_dir (default: ./transcripts/).
    Returns a callable matching the output_fn signature.
    """
    if transcript_dir is None:
        transcript_dir = Path.cwd() / "transcripts"
    transcript_dir.mkdir(parents=True, exist_ok=True)

    timestamp = datetime.now().strftime("%Y%m%d-%H%M%S")
    filepath = transcript_dir / f"transcript-{timestamp}.txt"
    fh = open(filepath, "a", encoding="utf-8")

    def transcript_write(char: str) -> None:
        fh.write(char)
        if char == "\n":
            fh.flush()  # Flush per line for durability

    return transcript_write
```

### Pattern 3: Wiring Into Existing Fan-Out

**What:** Add audio and transcript as additional destinations in the existing `make_output_fn()` calls in `tui.py` and `cli.py`.

**When to use:** At the integration points where destinations are assembled.

**Example (TUI integration):**
```python
# In tui.py stream_response():
from claude_teletype.audio import make_bell_output
from claude_teletype.transcript import make_transcript_output

destinations = [log.write]
if self.printer is not None and self.printer.is_connected:
    destinations.append(make_printer_output(self.printer))
destinations.append(make_bell_output())
destinations.append(make_transcript_output())

output_fn = make_output_fn(*destinations)
```

### Anti-Patterns to Avoid

- **Loading sound from disk on every newline:** Pre-generate the NumPy array once. Disk I/O per newline adds latency and is unnecessary.
- **Opening/closing the transcript file per character:** Open once at session start, close at session end. Flush per line for durability.
- **Blocking audio playback:** Never use `sd.play(bell, blocking=True)` in the output path. It would block the entire character stream for the sound duration.
- **Creating a new sounddevice stream per newline:** Use `sd.play()` which manages a single global stream internally. Creating streams per event leaks handles.
- **Writing sensitive metadata to transcripts:** Only write text content (user prompts and Claude responses). Never write session IDs, API tokens, or raw NDJSON events.

## Don't Hand-Roll

| Problem | Don't Build | Use Instead | Why |
|---------|-------------|-------------|-----|
| Audio playback | Raw PortAudio bindings via ctypes | sounddevice 0.5.5 | PortAudio's C API is complex. sounddevice wraps it cleanly with a Pythonic interface. |
| WAV file loading | Manual wave module parsing + struct unpacking | numpy array generation in-memory | For a simple bell tone, generating it is simpler than loading a file. No asset management needed. |
| Sound mixing for overlaps | Custom audio buffer mixer | sd.play() auto-stop behavior | For single-sound-at-a-time (bell on newline), sd.play()'s stop-then-play is sufficient. Only build a mixer if v2 adds per-character key-click sounds. |
| File locking for transcripts | fcntl/msvcrt file locks | Simple open() with line-buffered flush | Single-process, single-writer scenario. No concurrent access. File locking adds complexity for zero benefit. |

**Key insight:** Both features are trivially simple consumers of the character stream. The existing fan-out architecture (`make_output_fn`) was designed exactly for this extensibility. No new architectural patterns are needed.

## Common Pitfalls

### Pitfall 1: PortAudio Not Installed

**What goes wrong:** `sounddevice` imports successfully (it's a pure Python wrapper) but crashes at runtime with `PortAudioError: Error opening OutputStream` or similar because PortAudio is not installed on the system.

**Why it happens:** sounddevice depends on the PortAudio shared library (`libportaudio`), which must be installed separately on macOS (`brew install portaudio`) and Linux (`apt install libportaudio2`). On macOS, sounddevice ships with a bundled PortAudio dylib, so this may work without `brew install` -- but the bundled version may not match the system's audio configuration.

**How to avoid:** Wrap all sounddevice usage in a try/except at initialization time. If PortAudio is unavailable, log a warning and return a no-op callable instead of the bell. The tool should work without audio -- it's an enhancement, not a requirement.

**Warning signs:** ImportError or OSError on first `sd.play()` call. Works on developer machine but fails on CI or clean installs.

### Pitfall 2: sd.play() Called Before Previous Finishes

**What goes wrong:** Rapid consecutive newlines (e.g., blank lines in Claude's response) trigger `sd.play()` multiple times in quick succession.

**Why it happens:** Claude's output often contains `\n\n` (paragraph breaks) or multiple consecutive blank lines.

**How to avoid:** This is actually fine. `sd.play()` internally calls `sd.stop()` first, which terminates the previous playback and starts the new one. For a 150ms bell, this means consecutive newlines simply re-trigger the bell cleanly. No special handling needed. If the re-triggering is annoying, add a minimum cooldown (e.g., skip if last bell was <100ms ago).

### Pitfall 3: Transcript File Handle Leak

**What goes wrong:** The transcript file handle is never closed, or the file is opened per-character, leading to resource exhaustion or data loss.

**Why it happens:** The callable returned by `make_transcript_output()` captures a file handle in its closure. If the session ends abnormally (crash, Ctrl+C), the file handle may not be flushed/closed.

**How to avoid:** Flush on every newline (not every character -- that's excessive I/O). Register an `atexit` handler or ensure the TUI's `on_unmount` / CLI's finally block calls a cleanup function that closes the file handle. Alternatively, use line-buffered mode: `open(filepath, "a", buffering=1)` which auto-flushes on newlines.

**Warning signs:** Empty transcript files after a session. Truncated transcripts missing the last few lines.

### Pitfall 4: Transcript Directory Permissions

**What goes wrong:** Transcript files are created in the current working directory with default permissions, making them world-readable on shared systems.

**Why it happens:** `open()` inherits the process umask. On some systems, the default creates files with 0o644 permissions.

**How to avoid:** Create the transcripts directory with restricted permissions: `mkdir(mode=0o700)`. This is a minor concern for a single-user CLI tool but good practice.

### Pitfall 5: Audio Blocks the Event Loop

**What goes wrong:** Using `sd.play(bell, blocking=True)` or accidentally calling a blocking audio function in the character output path freezes the TUI for the bell duration.

**Why it happens:** The output destinations are called synchronously in `make_output_fn`'s loop. Any blocking call in a destination blocks all subsequent destinations and the pacer's sleep.

**How to avoid:** Always use `sd.play()` with default `blocking=False`. The function returns immediately. Playback continues in a PortAudio background thread managed by sounddevice.

## Code Examples

Verified patterns from official sources and existing codebase:

### Generating a Bell Tone In-Memory

```python
# Source: numpy sine wave generation + sounddevice docs
import numpy as np

sample_rate = 44100
duration = 0.15  # 150ms
t = np.linspace(0, duration, int(sample_rate * duration), endpoint=False)
frequency = 880  # A5 note - bright bell
tone = np.sin(2 * np.pi * frequency * t)
envelope = np.exp(-t * 20)  # Exponential decay for bell character
bell = (tone * envelope).astype(np.float32)
```

### Non-Blocking Playback

```python
# Source: python-sounddevice docs, convenience functions
import sounddevice as sd

sd.play(bell, samplerate=44100)
# Returns immediately. Plays in background.
# Calling sd.play() again auto-stops previous playback.
```

### Graceful Audio Initialization with Fallback

```python
# Pattern: try sounddevice, fall back to no-op
def make_bell_output() -> Callable[[str], None]:
    try:
        import sounddevice as sd
        import numpy as np

        # Generate bell tone
        sr = 44100
        dur = 0.15
        t = np.linspace(0, dur, int(sr * dur), endpoint=False)
        bell = (np.sin(2 * np.pi * 880 * t) * np.exp(-t * 20)).astype(np.float32)

        def bell_output(char: str) -> None:
            if char == "\n":
                sd.play(bell, samplerate=sr)

        return bell_output
    except (ImportError, OSError):
        # PortAudio not available -- degrade gracefully
        def noop(char: str) -> None:
            pass
        return noop
```

### Transcript Writer with Cleanup

```python
# Pattern: file-handle-in-closure with explicit close
from datetime import datetime
from pathlib import Path

def make_transcript_output(
    transcript_dir: Path | None = None,
) -> tuple[Callable[[str], None], Callable[[], None]]:
    """Returns (write_fn, close_fn) pair."""
    if transcript_dir is None:
        transcript_dir = Path.cwd() / "transcripts"
    transcript_dir.mkdir(parents=True, exist_ok=True)

    ts = datetime.now().strftime("%Y%m%d-%H%M%S")
    fh = open(transcript_dir / f"transcript-{ts}.txt", "a", encoding="utf-8")

    def write(char: str) -> None:
        fh.write(char)
        if char == "\n":
            fh.flush()

    def close() -> None:
        if not fh.closed:
            fh.flush()
            fh.close()

    return write, close
```

### Existing Fan-Out Pattern (for reference)

```python
# Source: src/claude_teletype/output.py (existing code)
def make_output_fn(*destinations: Callable[[str], None]) -> Callable[[str], None]:
    if not destinations:
        return _noop
    if len(destinations) == 1:
        return destinations[0]
    def output(char: str) -> None:
        for dest in destinations:
            dest(char)
    return output
```

### Transcript Format Example

```
> What is the capital of France?

The capital of France is Paris. It is located in the north-central part of
the country along the Seine River.

> Tell me more about Paris.

Paris is the most populous city in France, with a population of over 2
million in the city proper...
```

The format matches what the TUI already renders: user prompts prefixed with `> ` and Claude's responses as plain text. The transcript captures everything the output_fn receives, including the formatting added by `tui.py`'s `on_input_submitted` (`\n> {prompt}\n\n`).

## State of the Art

| Old Approach | Current Approach | When Changed | Impact |
|--------------|------------------|--------------|--------|
| simpleaudio for short sound effects | sounddevice 0.5.5 | simpleaudio abandoned 2019 | simpleaudio has no Python 3.12+ support. sounddevice is actively maintained. |
| Bundled WAV files for sound effects | In-memory NumPy generation | N/A (both valid) | Eliminates asset management. Bell tone is ~10 lines of numpy math. |
| playsound library | sounddevice | playsound abandoned, CVEs | playsound has known security issues and cross-platform bugs. |

**Deprecated/outdated:**
- `simpleaudio`: Last release 2019. Do not use.
- `playsound`: Abandoned, multiple CVEs. Do not use.
- `pygame.mixer` for single sound effects: 30MB dependency. Overkill.

## Open Questions

1. **Bell tone tuning (frequency, duration, decay)**
   - What we know: 880 Hz (A5), 150ms duration, exponential decay sounds like a crisp bell/ding
   - What's unclear: Optimal values are subjective. May need user testing.
   - Recommendation: Start with 880 Hz / 150ms / decay factor 20. These are easily adjustable constants. Could expose a `--no-audio` flag to disable.

2. **Transcript directory location**
   - What we know: Default `./transcripts/` relative to CWD works for a CLI tool.
   - What's unclear: Should it use `~/.claude-teletype/transcripts/` for a persistent location? Or follow XDG conventions?
   - Recommendation: Default to `./transcripts/` for simplicity. This matches the working directory where the user runs the tool. A `--transcript-dir` flag can override.

3. **User input in transcripts**
   - What we know: The TUI writes `\n> {prompt}\n\n` before each response via `log.write()`. If the transcript destination is wired at the same level, it captures this naturally.
   - What's unclear: In `--no-tui` mode, user prompts go through `_chat_async` which doesn't write a prompt header. The transcript would only contain Claude's response.
   - Recommendation: Ensure both TUI and CLI paths write a user prompt header to the output before streaming Claude's response. The transcript captures whatever flows through `output_fn`.

4. **Handling PortAudio unavailability**
   - What we know: sounddevice requires PortAudio system library. It may be missing on some systems.
   - What's unclear: Whether sounddevice ships a bundled PortAudio on macOS (it does for some wheels).
   - Recommendation: Wrap audio initialization in try/except. Return no-op callable on failure. Print a one-time warning. The tool must work without audio.

## Sources

### Primary (HIGH confidence)
- [python-sounddevice convenience functions API](https://python-sounddevice.readthedocs.io/en/latest/api/convenience-functions.html) - `sd.play()` parameters, non-blocking behavior, auto-stop on re-call
- [python-sounddevice PyPI](https://pypi.org/project/sounddevice/) - version 0.5.5, released 2026-01-23, PortAudio wrapper
- [python-sounddevice GitHub issue #170](https://github.com/spatialaudio/python-sounddevice/issues/170) - overlapping playback discussion, callback-based alternatives
- [python-sounddevice GitHub issue #140](https://github.com/spatialaudio/python-sounddevice/issues/140) - thread handle behavior on repeated play() calls
- Existing codebase: `src/claude_teletype/output.py` - `make_output_fn(*destinations)` fan-out pattern
- Existing codebase: `src/claude_teletype/tui.py` - destination wiring in `stream_response()`
- Existing codebase: `src/claude_teletype/cli.py` - destination wiring in `_chat_async()`

### Secondary (MEDIUM confidence)
- [Creating a Sound Effect (Bell) Using Python 3](https://dnmtechs.com/creating-a-sound-effect-bell-using-python-3-programming/) - bell tone generation with numpy sine wave + exponential decay
- [python-rtmixer](https://github.com/spatialaudio/python-rtmixer) - lower-latency alternative for future per-character audio (v2 AUDI-02)
- Stack research: `.planning/research/STACK.md` - sounddevice 0.5.5, soundfile 0.13.1 selections
- Pitfalls research: `.planning/research/PITFALLS.md` - Pitfall 4 (audio latency), Pitfall 6 (TUI conflicts)

### Tertiary (LOW confidence)
- None. All findings verified with primary or secondary sources.

## Metadata

**Confidence breakdown:**
- Standard stack: HIGH - sounddevice is well-documented, actively maintained, and already selected in prior stack research
- Architecture: HIGH - both consumers follow the established `make_output_fn()` fan-out pattern with zero new abstractions
- Pitfalls: HIGH - key pitfalls (PortAudio missing, blocking playback, file handle leaks) are well-understood and have simple mitigations
- Code examples: HIGH - based on official sounddevice docs and existing codebase patterns

**Research date:** 2026-02-15
**Valid until:** 2026-03-15 (stable domain, mature libraries)
