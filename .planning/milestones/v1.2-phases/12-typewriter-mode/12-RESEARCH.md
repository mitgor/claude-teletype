# Phase 12: Typewriter Mode - Research

**Researched:** 2026-02-17
**Domain:** TUI keyboard capture, typewriter pacing/audio, simultaneous printer output, Textual screen modes
**Confidence:** HIGH

## Summary

Phase 12 transforms the existing `--teletype` raw printer mode into a full TUI typewriter experience. Currently, `--teletype` mode (in `teletype.py`) uses `termios`/`tty` cbreak mode to read stdin char-by-char and send directly to a USB printer -- no TUI, no pacing, no sound, no screen display. Phase 12 needs to deliver a mode where keystrokes appear on screen with typewriter pacing and sound while simultaneously being sent to the printer with correct profile control codes.

The two requirements (TYPE-01 and TYPE-03) split cleanly: TYPE-01 is the TUI side (keystrokes to screen with pacing and sound, no LLM), and TYPE-03 is the printer side (keystrokes sent to printer simultaneously). The existing codebase already has all the building blocks: `pacer.py` for character-by-character delay, `audio.py` for sound generation via sounddevice, `output.py` for multiplexed `make_output_fn()`, `printer.py` for `ProfilePrinterDriver` with profile-driven ESC codes, and `tui.py` for the Textual app framework. The work is integration, not invention.

The key architectural decision is how to implement typewriter mode within the TUI. Textual's **screen modes** (`MODES` class variable) provide a clean mechanism: a "chat" mode for the current LLM conversation screen and a "typewriter" mode for direct keyboard-to-paper typing. The typewriter screen captures keystrokes via `on_key`, applies pacing delay before displaying each character, plays a keystroke sound, and simultaneously sends the character to the printer.

**Primary recommendation:** Add a `TypewriterScreen` to `TeletypeApp` using Textual screen modes. The screen captures `on_key` events, routes printable characters through `pace_characters()` and `make_output_fn()` to Log widget + audio + printer destinations. Switch between modes via a keybinding (e.g., `ctrl+t`). Keep the existing `--teletype` raw mode as a fallback for users without a TUI.

<phase_requirements>
## Phase Requirements

| ID | Description | Research Support |
|----|-------------|-----------------|
| TYPE-01 | User can enter typewriter mode where keystrokes go directly to screen with pacing and sound, no LLM | New `TypewriterScreen` in the Textual TUI. Captures `on_key` events for printable characters. Uses existing `pace_characters()` for delay, existing `make_bell_output()` pattern adapted for keystroke sounds, and `Log.write()` for screen display. No LLM backend is invoked. Mode entered via keybinding or `--typewriter-mode` flag. |
| TYPE-03 | User's typewriter keystrokes are sent to the connected printer simultaneously | Existing `make_printer_output()` creates a `Callable[[str], None]` wrapping `ProfilePrinterDriver` with word-wrap. Wire this as a destination in `make_output_fn()` alongside the Log widget and audio destinations. Printer receives characters as they are typed, with profile-driven ESC codes from Phase 10. |
</phase_requirements>

## Standard Stack

### Core
| Library | Version | Purpose | Why Standard |
|---------|---------|---------|--------------|
| textual | >=7.0.0 (installed: 7.5.0) | TUI framework, screen modes, key event capture | Already the app framework. Screen modes (`MODES`) provide named screen stacks for chat vs typewriter. `on_key` event gives `character` and `is_printable` attributes for keystroke capture. |
| sounddevice | >=0.5.0 (installed: 0.5.5) | Typewriter keystroke sound playback | Already used for bell sound on newlines. For keystroke sounds, a very short (~20-30ms) click tone generated in-memory works with `sd.play()` since sound finishes before next keystroke at normal typing speed. |
| numpy | >=1.26.0 | In-memory keystroke sound synthesis | Already used for bell tone generation. Same pattern for generating a short typewriter click. |

### Supporting
| Library | Version | Purpose | When to Use |
|---------|---------|---------|-------------|
| asyncio | stdlib | Async pacing delays in keystroke output | Already used by `pace_characters()`. Typewriter mode uses same async delay pattern. |

### Alternatives Considered
| Instead of | Could Use | Tradeoff |
|------------|-----------|----------|
| Textual screen modes (`MODES`) | `push_screen`/`pop_screen` | Modes give independent screen stacks with named switching. Push/pop is a stack-based model that's more complex to manage. Modes are cleaner for two distinct app states. |
| Textual screen modes (`MODES`) | Hiding/showing widgets in single screen | Fragile, clutters the main screen CSS, no clean separation of concerns. |
| `sd.play()` for keystroke sound | Custom `OutputStream` mixer for overlapping | `sd.play()` auto-stops previous playback. But for a ~20ms click sound at typical typing speed (100-200ms between keystrokes), the sound finishes before the next `sd.play()` call. A mixer is over-engineering unless the user types faster than the sound duration. |
| `sd.play()` for keystroke sound | pygame.mixer channels | 30MB dependency for click sounds. Massive overkill. |
| New TypewriterScreen class | Modify existing TeletypeApp.compose() | Separation of concerns. The typewriter screen has completely different UI (no input widget, no status bar with LLM info). A separate screen class is cleaner. |

**Installation:**
No new dependencies. All required libraries are already in `pyproject.toml`.

## Architecture Patterns

### Recommended Project Structure
```
src/claude_teletype/
    tui.py               # MODIFIED: Add MODES dict, keybinding to switch modes
    typewriter_screen.py  # NEW: TypewriterScreen with on_key capture, pacing, audio
    audio.py             # MODIFIED: Add make_keystroke_output() alongside make_bell_output()
    teletype.py          # EXISTING: Raw --teletype mode (keep as fallback, no changes)
    pacer.py             # EXISTING: pace_characters() reused for keystroke pacing
    output.py            # EXISTING: make_output_fn() for multiplexed destinations
    printer.py           # EXISTING: make_printer_output() for printer destination
    cli.py               # MODIFIED: Wire typewriter mode flag/entry point
```

### Pattern 1: Textual Screen Modes for Chat vs Typewriter

**What:** Use Textual's `MODES` class variable to define two independent screen stacks -- one for LLM chat, one for typewriter mode.

**When to use:** When the app has distinct operational modes with different UI layouts and key handling.

**Example:**
```python
# In tui.py
from claude_teletype.typewriter_screen import TypewriterScreen

class TeletypeApp(App):
    MODES = {
        "chat": "ChatScreen",       # Current screen content, extracted to a Screen class
        "typewriter": "TypewriterScreen",  # New typewriter mode
    }
    DEFAULT_MODE = "chat"

    BINDINGS = [
        Binding("ctrl+d", "quit", "Quit"),
        Binding("ctrl+t", "switch_mode('typewriter')", "Typewriter"),
    ]
```

**Source:** [Textual Screens Guide - Modes](https://textual.textualize.io/guide/screens/)

**Caveat:** Using MODES requires extracting the current TUI content into a `Screen` subclass. This is a moderate refactor. A simpler alternative is using `push_screen`/`pop_screen` which doesn't require extracting to Screen classes -- the default screen remains the chat mode and TypewriterScreen is pushed on top.

### Pattern 2: Push/Pop Screen (Simpler Alternative to Modes)

**What:** Keep the existing `TeletypeApp` as-is, add `TypewriterScreen` as a separate `Screen` subclass, and push it when entering typewriter mode.

**When to use:** When you want minimal refactoring of existing code.

**Example:**
```python
# In tui.py (minimal change to existing code)
class TeletypeApp(App):
    BINDINGS = [
        Binding("ctrl+d", "quit", "Quit"),
        Binding("ctrl+t", "enter_typewriter", "Typewriter Mode"),
        Binding("escape", "cancel_stream", "Cancel", show=False),
    ]

    def action_enter_typewriter(self) -> None:
        from claude_teletype.typewriter_screen import TypewriterScreen
        self.push_screen(TypewriterScreen(
            base_delay_ms=self.base_delay_ms,
            printer=self.printer,
            no_audio=self.no_audio,
        ))
```

```python
# In typewriter_screen.py
from textual.screen import Screen

class TypewriterScreen(Screen):
    BINDINGS = [
        Binding("escape", "app.pop_screen", "Back to Chat"),
    ]

    def on_key(self, event: events.Key) -> None:
        if event.is_printable and event.character:
            event.prevent_default()
            self._type_character(event.character)
        elif event.key == "enter":
            event.prevent_default()
            self._type_character("\n")
```

**Recommendation:** Use push_screen/pop_screen (Pattern 2) instead of MODES. It avoids refactoring the existing TeletypeApp compose/mount/stream_response code into a separate Screen class. TypewriterScreen is added on top and popped when done.

### Pattern 3: Keystroke Capture via on_key

**What:** Intercept keyboard events at the Screen level using `on_key`, filter to printable characters, and route them through the pacing/audio/printer pipeline.

**When to use:** When building a typewriter mode that needs raw character-by-character input without a text Input widget.

**Example:**
```python
# In typewriter_screen.py
class TypewriterScreen(Screen):
    def on_key(self, event: events.Key) -> None:
        if event.is_printable and event.character:
            event.prevent_default()
            event.stop()
            self._handle_keystroke(event.character)
        elif event.key == "enter":
            event.prevent_default()
            event.stop()
            self._handle_keystroke("\n")
        elif event.key == "backspace":
            # Typewriters don't have backspace in the traditional sense.
            # Could optionally implement as backspace-space-backspace on printer.
            event.prevent_default()
        elif event.key == "tab":
            event.prevent_default()
            event.stop()
            self._handle_keystroke("\t")
```

**Source:** [Textual Key Event](https://textual.textualize.io/events/key/)

Key attributes:
- `event.is_printable` -- True if the key produces a visible character
- `event.character` -- The Unicode character string, or None for non-printable keys
- `event.prevent_default()` -- Prevents base class handlers (like Input widget) from processing
- `event.stop()` -- Prevents event from bubbling to parent widgets

### Pattern 4: Async Pacing for Typed Characters

**What:** Apply typewriter pacing delay to each keystroke before displaying it. The character appears on screen with a slight delay, creating a "printing" feel.

**When to use:** TYPE-01 requires keystrokes to appear with typewriter pacing.

**Example:**
```python
from textual import work

class TypewriterScreen(Screen):
    @work(exclusive=True, group="typing")
    async def _handle_keystroke(self, char: str) -> None:
        """Process a single keystroke through the typewriter pipeline."""
        await pace_characters(
            char,
            base_delay_ms=self._base_delay_ms,
            output_fn=self._output_fn,
        )
```

**Important consideration:** Using `@work(exclusive=True)` means each keystroke cancels the previous worker. For typewriter mode where characters come one at a time, this is fine -- each character is a single-character "chunk" that processes almost instantly (the delay is just the pacing delay for that one character). However, if the user types faster than the pacing delay, characters will queue up. An alternative is to buffer keystrokes in an `asyncio.Queue` and process them sequentially with a single long-running worker.

### Pattern 5: Keystroke Queue for Consistent Pacing

**What:** Buffer keystrokes in an async queue and process them sequentially to ensure consistent pacing even during fast typing.

**When to use:** When the user might type faster than the pacing delay.

**Example:**
```python
import asyncio

class TypewriterScreen(Screen):
    def __init__(self, **kwargs):
        super().__init__(**kwargs)
        self._key_queue: asyncio.Queue[str] = asyncio.Queue()

    def on_mount(self) -> None:
        self._process_keys()  # Start background worker

    def on_key(self, event: events.Key) -> None:
        if event.is_printable and event.character:
            event.prevent_default()
            event.stop()
            self._key_queue.put_nowait(event.character)
        elif event.key == "enter":
            event.prevent_default()
            event.stop()
            self._key_queue.put_nowait("\n")

    @work(exclusive=True)
    async def _process_keys(self) -> None:
        """Continuously drain the keystroke queue with pacing."""
        while True:
            char = await self._key_queue.get()
            await pace_characters(
                char,
                base_delay_ms=self._base_delay_ms,
                output_fn=self._output_fn,
            )
```

**Recommendation:** Use the queue pattern. It handles fast typing gracefully -- characters buffer and appear at a steady typewriter pace, creating the authentic feel of a mechanical typewriter where the type mechanism has its own speed regardless of how fast the typist presses keys.

### Pattern 6: Keystroke Sound (Adapted from make_bell_output)

**What:** Generate a short typewriter click sound in-memory and play it per keystroke, following the same pattern as `make_bell_output()` in `audio.py`.

**When to use:** TYPE-01 requires sound with keystrokes.

**Example:**
```python
# In audio.py
def make_keystroke_output() -> Callable[[str], None]:
    """Create an output function that plays a keystroke click on each character.

    Generates a short (~20ms) click tone with white noise burst.
    Returns a no-op if sounddevice/numpy unavailable.
    """
    try:
        import numpy as np
        import sounddevice as sd

        sr = 44100
        duration = 0.020  # 20ms -- very short click
        t = np.linspace(0, duration, int(sr * duration), endpoint=False)

        # Mix a sharp attack with rapid decay: brief noise burst + low thump
        noise = np.random.default_rng(42).normal(0, 0.3, len(t)).astype(np.float32)
        thump = np.sin(2 * np.pi * 200 * t) * np.exp(-t * 150)
        click = ((noise + thump) * np.exp(-t * 200)).astype(np.float32)
        # Normalize
        click = click / np.max(np.abs(click)) * 0.5

        def _click_write(char: str) -> None:
            if char != "\n":  # Newline gets the bell sound, not a click
                sd.play(click, samplerate=sr)

        return _click_write

    except (ImportError, OSError):
        def _noop(char: str) -> None:
            pass
        return _noop
```

**Critical detail about sd.play() and overlapping:** `sd.play()` internally calls `sd.stop()` before starting new playback, which means rapid keystrokes will cut off the previous sound. At 20ms click duration, this is acceptable because:
1. A skilled typist types ~8-12 chars/second = 80-125ms between keystrokes
2. The 20ms click finishes well before the next keystroke
3. Even for burst typing (multiple keys nearly simultaneous), the last key's click plays to completion

For a carriage return / Enter key, the existing bell sound (880 Hz, 150ms) fires instead. The bell is longer but only fires on newlines, so no overlap concern.

### Anti-Patterns to Avoid

- **Blocking the Textual event loop with pacing:** Never call `time.sleep()` in `on_key`. Use `asyncio.sleep()` inside a `@work` worker or `set_timer` for async delays.
- **Using termios/tty inside Textual:** Textual already handles raw terminal input via its own driver (XTermParser). Setting cbreak mode manually would conflict with Textual's input handling.
- **Sending printer output synchronously in on_key:** Printer I/O (especially USB bulk writes) can block. If the printer is slow, it could freeze the TUI. Keep printer writes in the async worker chain, or ensure `driver.write()` is non-blocking (USB bulk writes are typically fast for single characters).
- **Creating a new audio object per keystroke:** Pre-generate the click sound array once in `make_keystroke_output()`, not on every keypress.
- **Refactoring TeletypeApp into Screen classes unnecessarily:** Use push_screen/pop_screen rather than MODES to minimize disruption to the existing working codebase.

## Don't Hand-Roll

| Problem | Don't Build | Use Instead | Why |
|---------|-------------|-------------|-----|
| Keyboard capture in TUI | Raw termios/tty manipulation | Textual `on_key` event + `event.character` | Textual already handles terminal input. Manual terminal mode changes will conflict. |
| Character pacing delay | Custom sleep loop | Existing `pace_characters()` from `pacer.py` | Already tested, handles all character classification. |
| Multiplexed output | Custom dispatch loop | Existing `make_output_fn()` from `output.py` | Already handles 0-N destinations with single/multi optimization. |
| Printer word wrap | Manual column tracking | Existing `make_printer_output()` from `printer.py` | Already wraps `WordWrapper` + `ProfilePrinterDriver`. |
| Keystroke sound generation | Loading WAV files from disk | In-memory numpy array (same as bell in `audio.py`) | No external assets. ~10 lines. Pre-generated once. |
| Audio mixing for overlapping sounds | Custom OutputStream mixer | Short click duration (~20ms) that completes before next `sd.play()` | Over-engineering. At normal typing speed, sounds don't overlap. |

**Key insight:** Every component needed for typewriter mode already exists in the codebase. The pacer, audio, output multiplexer, printer driver, and word wrapper are all designed as composable `Callable[[str], None]` destinations. Typewriter mode is wiring these existing pieces to a new input source (keyboard) instead of the current input source (LLM stream).

## Common Pitfalls

### Pitfall 1: Textual Event Loop Blocking

**What goes wrong:** Calling `time.sleep()` or synchronous I/O in `on_key` freezes the entire TUI. No screen updates, no further key events processed.

**Why it happens:** Textual runs on a single asyncio event loop. Synchronous blocking in an event handler blocks everything.

**How to avoid:** All pacing delays must use `asyncio.sleep()` inside a `@work` decorated method or `self.call_later`/`self.set_timer`. Printer writes should be fast enough to be synchronous (single character USB writes are sub-millisecond), but if latency is a concern, wrap in `run_in_thread`.

**Warning signs:** TUI freezes when typing. Characters appear in bursts rather than one at a time.

### Pitfall 2: Key Event Consumed by Input Widget

**What goes wrong:** If an Input widget has focus, it captures all printable key events. The typewriter screen's `on_key` never sees them.

**Why it happens:** Textual routes key events to the focused widget. The Input widget consumes printable characters.

**How to avoid:** The TypewriterScreen should NOT contain an Input widget. It should have a Log widget (for display) and capture keys at the Screen level via `on_key`. No focusable input widget means keys bubble to the Screen handler.

**Warning signs:** Typing does nothing in typewriter mode. Characters appear in an unexpected widget.

### Pitfall 3: sd.play() Cuts Off Previous Sound During Fast Typing

**What goes wrong:** Rapid typing causes `sd.play()` to call `sd.stop()` internally, cutting off the previous keystroke sound before it finishes.

**Why it happens:** `sd.play()` is a convenience function that manages a single global output stream. Each call stops the previous.

**How to avoid:** Keep the click sound very short (~20ms). At typical typing speed of 8-12 chars/second (80-125ms gap), a 20ms sound completes well before the next keystroke. For the carriage return bell (150ms), it only fires on Enter so no overlap with click sounds. If users report sound artifacts from very fast typing, consider: (a) reducing click duration to 10ms, or (b) using a custom `OutputStream` mixer as a future enhancement.

**Warning signs:** Sound clicks abruptly during fast typing. Intermittent silence between sounds.

### Pitfall 4: Printer Not Available in Typewriter Mode

**What goes wrong:** User enters typewriter mode but no printer is connected. Characters appear on screen but nothing prints.

**Why it happens:** `discover_printer()` returns `NullPrinterDriver` when no printer is found. `make_printer_output()` wraps it, but writes go nowhere.

**How to avoid:** This is actually correct graceful degradation. Typewriter mode should work without a printer (screen-only mode is still valuable for the typewriter feel). Show a status indicator: "Printer: [connected/not connected]" in the typewriter screen's status bar so the user knows.

**Warning signs:** User expects printing but nothing happens. No error message tells them why.

### Pitfall 5: asyncio.Queue Not Created in Correct Event Loop

**What goes wrong:** `asyncio.Queue()` created in `__init__` may not be in the same event loop as the Textual app.

**Why it happens:** Textual creates its own event loop. If the Queue is created before the loop starts, it may be bound to a different loop (Python 3.10+ removed the implicit loop parameter but the Queue must be used from the same event loop context).

**How to avoid:** Create the `asyncio.Queue()` in `on_mount()` (which runs inside the Textual event loop), not in `__init__()`.

**Warning signs:** `RuntimeError: got Future attached to a different loop`. Queue operations hang or raise.

### Pitfall 6: Enter Key Handling Ambiguity

**What goes wrong:** Enter key should produce a newline in typewriter mode (carriage return on printer, newline on screen) but Textual may interpret it as form submission or action.

**Why it happens:** Some Textual widgets have built-in Enter key handling.

**How to avoid:** In `on_key`, explicitly handle `event.key == "enter"` and call `event.prevent_default()` and `event.stop()` to prevent any default handling. Map Enter to `"\n"` in the keystroke queue.

**Warning signs:** Enter does nothing. Enter triggers unexpected behavior.

## Code Examples

Verified patterns from official sources and existing codebase:

### TypewriterScreen Structure
```python
# Source: Textual Screens guide + existing codebase patterns
from textual import events, work
from textual.binding import Binding
from textual.screen import Screen
from textual.widgets import Footer, Header, Log, Static

class TypewriterScreen(Screen):
    """Typewriter mode: keystrokes to screen with pacing and sound."""

    BINDINGS = [
        Binding("escape", "app.pop_screen", "Back to Chat"),
    ]

    CSS = """
    #typewriter-output {
        height: 1fr;
    }
    #typewriter-status {
        dock: bottom;
        height: 1;
        background: $surface;
        color: $text-muted;
        padding: 0 1;
    }
    """

    def __init__(
        self,
        base_delay_ms: float = 75.0,
        printer=None,
        no_audio: bool = False,
        **kwargs,
    ) -> None:
        super().__init__(**kwargs)
        self._base_delay_ms = base_delay_ms
        self._printer = printer
        self._no_audio = no_audio
        self._key_queue = None  # Created in on_mount
        self._output_fn = None

    def compose(self):
        yield Header()
        yield Log(id="typewriter-output", auto_scroll=True)
        printer_status = "connected" if (self._printer and self._printer.is_connected) else "none"
        yield Static(f"TYPEWRITER MODE | Printer: {printer_status}", id="typewriter-status")
        yield Footer()

    def on_mount(self) -> None:
        import asyncio
        from claude_teletype.audio import make_bell_output, make_keystroke_output
        from claude_teletype.output import make_output_fn
        from claude_teletype.printer import make_printer_output

        self._key_queue = asyncio.Queue()

        log = self.query_one("#typewriter-output", Log)
        destinations = [log.write]

        if self._printer is not None and self._printer.is_connected:
            destinations.append(make_printer_output(self._printer))

        if not self._no_audio:
            destinations.append(make_keystroke_output())
            destinations.append(make_bell_output())  # Bell on newlines

        self._output_fn = make_output_fn(*destinations)
        self._process_keys()

    def on_key(self, event: events.Key) -> None:
        if event.is_printable and event.character:
            event.prevent_default()
            event.stop()
            self._key_queue.put_nowait(event.character)
        elif event.key == "enter":
            event.prevent_default()
            event.stop()
            self._key_queue.put_nowait("\n")
        elif event.key == "tab":
            event.prevent_default()
            event.stop()
            self._key_queue.put_nowait("\t")

    @work(exclusive=True)
    async def _process_keys(self) -> None:
        from claude_teletype.pacer import pace_characters
        while True:
            char = await self._key_queue.get()
            await pace_characters(
                char,
                base_delay_ms=self._base_delay_ms,
                output_fn=self._output_fn,
            )
```

### Keystroke Sound Generator
```python
# Source: Adapted from existing audio.py make_bell_output() pattern
def make_keystroke_output() -> Callable[[str], None]:
    try:
        import numpy as np
        import sounddevice as sd

        sr = 44100
        duration = 0.020  # 20ms click
        t = np.linspace(0, duration, int(sr * duration), endpoint=False)
        rng = np.random.default_rng(42)  # Fixed seed for deterministic sound
        noise = rng.normal(0, 0.3, len(t)).astype(np.float32)
        thump = np.sin(2 * np.pi * 200 * t) * np.exp(-t * 150)
        click = ((noise + thump) * np.exp(-t * 200)).astype(np.float32)
        click = click / np.max(np.abs(click)) * 0.5

        def _click_write(char: str) -> None:
            if char not in ("\n", "\r"):  # Newlines get bell, not click
                sd.play(click, samplerate=sr)

        return _click_write
    except (ImportError, OSError):
        def _noop(char: str) -> None:
            pass
        return _noop
```

### Wiring push_screen in TeletypeApp
```python
# Source: Textual Screens guide (push_screen pattern)
# In tui.py, add to TeletypeApp:

BINDINGS = [
    Binding("ctrl+d", "quit", "Quit"),
    Binding("ctrl+t", "enter_typewriter", "Typewriter"),
    Binding("escape", "cancel_stream", "Cancel", show=False),
]

def action_enter_typewriter(self) -> None:
    """Switch to typewriter mode (no LLM, direct keyboard to screen+printer)."""
    from claude_teletype.typewriter_screen import TypewriterScreen
    self.push_screen(TypewriterScreen(
        base_delay_ms=self.base_delay_ms,
        printer=self.printer,
        no_audio=self.no_audio,
    ))
```

### Integration with Existing --teletype Flag
```python
# In cli.py, modify the teletype branch to offer TUI typewriter mode as well:
# Keep --teletype for raw USB mode (no TUI, backward compat)
# Add typewriter mode entry to the TUI flow (activated via ctrl+t binding)
# Optionally: --typewriter flag to start directly in typewriter mode TUI
```

## State of the Art

| Old Approach | Current Approach | When Changed | Impact |
|--------------|------------------|--------------|--------|
| `--teletype` raw termios mode | TUI TypewriterScreen with pacing + sound | Phase 12 | Users get the typewriter experience in the TUI with audio feedback |
| Bell only on newlines | Click on keystrokes + bell on newlines | Phase 12 | Per-character audio feedback creates authentic typewriter feel |
| No screen display in teletype | Log widget shows typed text | Phase 12 | Users see what they're typing even without a printer |

**Deprecated/outdated:**
- The existing `--teletype` raw mode (`teletype.py`) remains as a fallback for users who want direct USB printing without a TUI. It is NOT removed.

## Open Questions

1. **Keyboard shortcut for entering typewriter mode**
   - What we know: `ctrl+t` is a common binding. Must not conflict with existing bindings.
   - What's unclear: Whether `ctrl+t` is already used by terminal emulators (it opens a new tab in some terminals).
   - Recommendation: Use `ctrl+t` as the binding. It's intuitive ("t" for typewriter). If it conflicts in some terminals, document alternative or make it configurable in Phase 13 (Settings Panel).

2. **Should pacing apply to typed characters or only displayed characters?**
   - What we know: TYPE-01 says "keystrokes appear on screen with typewriter pacing." This means the display is paced, not the keyboard input.
   - What's unclear: Should the user feel resistance (key input buffered) or should characters appear smoothly with delay? Both create the typewriter feel but differently.
   - Recommendation: Buffer keystrokes in a queue and process at pacing speed. This creates the authentic typewriter effect where the mechanism has its own speed. The user types freely and characters appear at the typewriter's pace.

3. **Backspace behavior**
   - What we know: Real typewriters don't delete. The carriage moves back but the character remains.
   - What's unclear: Should backspace be disabled, or should it move the cursor back (like a real typewriter's backspace key)?
   - Recommendation: Ignore backspace in v1 for simplicity. The Log widget is append-only anyway. Document this as intentional (typewriter authenticity). A future enhancement could implement overstrike.

4. **Word wrap in typewriter mode**
   - What we know: The printer gets word-wrapped output via `make_printer_output()`. The TUI Log widget also needs wrapping.
   - What's unclear: Should the screen show word wrap at the terminal width, or at the printer's column width?
   - Recommendation: Wrap at terminal width for screen, at printer column width for printer (same per-destination wrapping pattern used in chat mode). The screen wrapper uses `WordWrapper(log.size.width, log.write)`.

5. **Should typewriter mode be available without a TUI?**
   - What we know: The existing `--teletype` flag provides raw keyboard-to-printer mode without TUI.
   - What's unclear: Should Phase 12 enhance `--teletype` or only add TUI typewriter mode?
   - Recommendation: Phase 12 focuses on TUI typewriter mode (new TypewriterScreen). The existing `--teletype` raw mode is unchanged and serves as a minimal fallback. They serve different use cases: `--teletype` for raw USB hacking, TUI typewriter mode for the full experience.

6. **Interaction between keystroke clicks and bell sounds**
   - What we know: `sd.play()` stops previous playback. If a click is playing when Enter is pressed, the bell will cut off the click.
   - What's unclear: Whether this produces audible artifacts.
   - Recommendation: Since the click is ~20ms and the bell is triggered by Enter (a deliberate pause in typing), the click will have finished by the time Enter triggers the bell. No issue in practice. Both click and bell callables are wired as separate destinations in `make_output_fn()`, so both fire for `"\n"` -- but `make_keystroke_output()` should skip `"\n"` and `make_bell_output()` should only fire on `"\n"`, so they don't overlap.

## Sources

### Primary (HIGH confidence)
- [Textual Key Event](https://textual.textualize.io/events/key/) - `is_printable`, `character`, `prevent_default()` attributes
- [Textual Screens Guide](https://textual.textualize.io/guide/screens/) - `push_screen`, `pop_screen`, `MODES`, modal screens
- [Textual Input Guide](https://textual.textualize.io/guide/input/) - key routing, focus system, `on_key` handler
- [Textual Events Guide](https://textual.textualize.io/guide/events/) - `prevent_default()`, `stop()`, event bubbling
- [Textual Log Widget](https://textual.textualize.io/widgets/log/) - `write()`, `auto_scroll`, `write_line()`
- [python-sounddevice API](https://python-sounddevice.readthedocs.io/en/latest/api/convenience-functions.html) - `sd.play()` stops previous, non-blocking, OutputStream for overlapping
- Existing codebase: `src/claude_teletype/audio.py` - `make_bell_output()` pattern
- Existing codebase: `src/claude_teletype/pacer.py` - `pace_characters()` async pacing
- Existing codebase: `src/claude_teletype/output.py` - `make_output_fn()` multiplexer
- Existing codebase: `src/claude_teletype/printer.py` - `make_printer_output()`, `ProfilePrinterDriver`
- Existing codebase: `src/claude_teletype/tui.py` - `TeletypeApp` class, stream_response pattern
- Existing codebase: `src/claude_teletype/teletype.py` - existing raw `--teletype` mode
- Existing codebase: `src/claude_teletype/cli.py` - `--teletype` flag wiring, printer discovery flow

### Secondary (MEDIUM confidence)
- [Textual Switching Screens Tutorial](https://www.blog.pythonlibrary.org/2025/01/14/textual-switching-screens-in-your-terminal/) - practical examples of screen switching
- Phase 4 Research: `04-RESEARCH.md` - audio architecture, `sd.play()` behavior, sound generation patterns
- Phase 10 Research: `10-RESEARCH.md` - printer profile architecture, ProfilePrinterDriver

### Tertiary (LOW confidence)
- Typewriter click sound synthesis parameters (frequency, duration, decay) - based on audio engineering principles, not verified against real typewriter recordings. May need user-testing to tune.

## Metadata

**Confidence breakdown:**
- Standard stack: HIGH - all libraries already installed and used in the codebase
- Architecture: HIGH - push_screen pattern is well-documented in Textual. Keystroke queue is standard asyncio. All output destinations are existing code.
- Pitfalls: HIGH - key pitfalls (event loop blocking, key routing, sd.play() overlap) identified from official docs and existing codebase experience
- Code examples: HIGH - based on verified Textual API docs and existing codebase patterns. TypewriterScreen example is a composition of proven patterns.
- Audio synthesis: MEDIUM - keystroke sound parameters (20ms, noise+thump) are reasonable estimates but not verified against real typewriter recordings

**Research date:** 2026-02-17
**Valid until:** 2026-03-17 (stable domain, all libraries mature)
