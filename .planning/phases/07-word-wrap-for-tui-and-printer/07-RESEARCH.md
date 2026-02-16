# Phase 7: Word Wrap for TUI and Printer - Research

**Researched:** 2026-02-17
**Domain:** Streaming character-level word wrapping, Textual widget resize handling, printer output formatting
**Confidence:** HIGH

## Summary

Phase 7 adds word-boundary wrapping to both TUI output and printer output. The core challenge is wrapping text that arrives **one character at a time** through a streaming pipeline -- standard Python `textwrap` operates on complete strings and cannot be used directly.

The solution is a custom `WordWrapper` class that buffers the current word, tracks column position, and inserts newline characters at word boundaries when a word would overflow the line width. This wrapper sits between the pacer and each destination (`log.write` for TUI, `driver.write` for printer) as a pipeline filter. The existing `make_printer_output` hard-break logic at column 80 is replaced with word-aware wrapping using the same `WordWrapper` class.

For TUI resize support (WRAP-03), the `WordWrapper` exposes a mutable `width` property. The TUI app handles `on_resize` events and updates the wrapper's width. Already-rendered text remains unchanged (consistent with terminal behavior); only new text uses the updated width. The effective TUI width is `log.size.width - log.scrollbar_size_vertical` (typically 78 on an 80-column terminal due to the 2-column vertical scrollbar).

**Primary recommendation:** Create a single `WordWrapper` class in a new `wordwrap.py` module, used by both TUI (with dynamic width) and printer (with fixed A4_COLUMNS=80 width). Wire it as a per-destination filter wrapping `log.write` and `driver.write` respectively, leaving transcript and audio destinations unwrapped.

<phase_requirements>
## Phase Requirements

| ID | Description | Research Support |
|----|-------------|-----------------|
| WRAP-01 | Long lines in TUI output wrap at word boundaries instead of extending off-screen | WordWrapper wraps `log.write` before it enters `make_output_fn`. Log widget uses `no_wrap=True` internally (verified), so wrapping MUST happen before write. Wrapper buffers current word and inserts `\n` at word boundaries. |
| WRAP-02 | Long lines on printer wrap at word boundaries instead of breaking mid-word | Replace existing hard-break logic in `make_printer_output` (column >= A4_COLUMNS -> newline) with WordWrapper that inserts newlines at word boundaries. Same WordWrapper class, different width. |
| WRAP-03 | TUI wrap width updates when the terminal is resized | WordWrapper has mutable `width` property. TUI `on_resize` handler reads `log.size.width - log.scrollbar_size_vertical` and updates wrapper. Already-rendered text is not re-wrapped (matches standard terminal behavior). |
</phase_requirements>

## Standard Stack

### Core
| Library | Version | Purpose | Why Standard |
|---------|---------|---------|--------------|
| Python stdlib | 3.12+ | No external libraries needed | Word wrapping at character level is simple enough to implement directly; textwrap cannot handle streaming |
| Textual | >=7.0.0 | Already installed; provides `events.Resize`, `Widget.size`, `Widget.scrollbar_size_vertical` | Existing dependency, provides resize events |

### Supporting
| Library | Version | Purpose | When to Use |
|---------|---------|---------|-------------|
| textwrap (stdlib) | 3.12+ | Reference implementation for word-wrap semantics | NOT used directly -- only as semantic reference for expected behavior |

### Alternatives Considered
| Instead of | Could Use | Tradeoff |
|------------|-----------|----------|
| Custom WordWrapper | textwrap.TextWrapper | textwrap needs complete strings, incompatible with character streaming; would require buffering full lines before wrapping, which breaks the real-time typewriter effect |
| Custom WordWrapper | Textual CSS `overflow-x: hidden` | Log widget forces `no_wrap=True` on all rendered lines (verified in source); CSS cannot override this behavior |
| Custom WordWrapper | Subclass Log with custom render_line | Fragile coupling to Textual internals; would break on Textual updates; wrapping before write is cleaner |

**Installation:**
```bash
# No new dependencies needed
```

## Architecture Patterns

### Recommended Project Structure
```
src/claude_teletype/
    wordwrap.py          # NEW: WordWrapper class
    tui.py               # MODIFIED: wrap log.write, handle on_resize
    printer.py           # MODIFIED: replace hard-break with WordWrapper
    output.py            # UNCHANGED
    pacer.py             # UNCHANGED
```

### Pattern 1: Streaming Word Wrapper (Pipeline Filter)

**What:** A stateful object that accepts characters one at a time, buffers the current word, and calls an output function with wrapped characters. Inserts `\n` at word boundaries when a word would exceed the line width.

**When to use:** Whenever text streams character-by-character and must be word-wrapped before reaching a destination that does not support native wrapping.

**Algorithm:**
```
State: column (int), word_buffer (list[str]), pending_space (bool), width (int)

On feed(char):
  if char == '\n':
    flush_word()
    pending_space = False
    output('\n')
    column = 0
  elif char == ' ':
    flush_word()
    if column > 0:
      pending_space = True   # defer space until next word
  else:
    word_buffer.append(char)

On flush_word():
  if word_buffer empty: return
  space_needed = (1 if pending_space else 0) + len(word_buffer)
  if column + space_needed > width and column > 0:
    output('\n')             # wrap
    column = 0
    pending_space = False
  if pending_space and column > 0:
    output(' ')              # emit deferred space
    column += 1
  pending_space = False
  for ch in word_buffer:
    if column >= width:      # word longer than width, hard-break
      output('\n')
      column = 0
    output(ch)
    column += 1
  word_buffer.clear()
```

**Key design decisions:**
- Space is deferred (not emitted immediately) so that when wrapping occurs, the space is dropped rather than appearing as a trailing space on the previous line
- Words longer than `width` are hard-broken (forced newline mid-word) -- this is the same behavior as `textwrap.wrap(break_long_words=True)`
- Multiple consecutive spaces collapse to a single space at word boundaries (standard word-wrap behavior)

**Example (verified via prototype):**
```python
# Input: "The quick brown fox jumps over the lazy dog" at width=20
# Output: "The quick brown fox\njumps over the lazy\ndog"

wrapper = WordWrapper(width=20, output_fn=log.write)
for char in text:
    wrapper.feed(char)
wrapper.flush()
```

### Pattern 2: Per-Destination Wrapping

**What:** Each output destination that needs wrapping gets its own `WordWrapper` instance with appropriate width. Non-wrapping destinations (transcript, audio) receive characters directly.

**When to use:** When different destinations need different wrapping widths (TUI: terminal width, printer: A4 paper width).

**Example:**
```python
# In TUI stream_response:
log = self.query_one("#output", Log)
effective_width = log.size.width - log.scrollbar_size_vertical
tui_wrapper = WordWrapper(effective_width, log.write)

destinations = [tui_wrapper.feed]  # wrapped
if printer_write:
    destinations.append(printer_write)  # printer has its own wrapping
if bell_write:
    destinations.append(bell_write)    # no wrapping needed
if transcript_write:
    destinations.append(transcript_write)  # no wrapping needed

output_fn = make_output_fn(*destinations)
```

### Pattern 3: Resize Handling

**What:** On terminal resize, update the wrapper's width so future characters wrap at the new boundary.

**When to use:** For TUI word wrap (WRAP-03).

**Example:**
```python
class TeletypeApp(App):
    def __init__(self, ...):
        self._tui_wrapper = None  # set during stream setup

    def on_resize(self, event: events.Resize) -> None:
        if self._tui_wrapper is not None:
            log = self.query_one("#output", Log)
            new_width = log.size.width - log.scrollbar_size_vertical
            self._tui_wrapper.width = new_width
```

**Confirmed:** Textual fires `on_resize` event on the App when terminal size changes. The event provides `event.size` (new terminal Size). Tested in Textual 7.5.0 headless mode.

### Anti-Patterns to Avoid
- **CSS-based wrapping on Log widget:** Log widget hard-codes `no_wrap=True` in its render method (`Text(_line, no_wrap=True)` -- verified in Textual 7.5.0 source). CSS properties like `overflow-x: hidden` or `text-wrap` have no effect on Log content rendering.
- **Wrapping inside `make_output_fn`:** The output multiplexer is destination-agnostic. Wrapping belongs in per-destination filters, not in the shared multiplexer.
- **Re-wrapping on resize:** Already-written Log content cannot be efficiently re-wrapped. The Log widget provides `clear()` but re-rendering all content would lose scroll position and break the streaming feel. Standard terminal behavior is to not re-flow old output on resize.
- **Global wrapper for all destinations:** Transcript should store original unwrapped text. Audio bell should trigger on original newlines (not wrap-inserted newlines). Each destination's wrapping needs are different.

## Don't Hand-Roll

| Problem | Don't Build | Use Instead | Why |
|---------|-------------|-------------|-----|
| Word-wrap semantics for complete strings | Custom line-breaking algorithm | `textwrap.wrap()` as reference | Python's textwrap has 20+ years of edge case handling; use its semantics as spec |
| Terminal size detection | Custom ioctl/stty parsing | `shutil.get_terminal_size()` or `Widget.size` | Standard library handles all platforms; Textual provides widget-level sizes |

**Key insight:** The only custom code needed is the streaming adapter (WordWrapper) that bridges character-at-a-time input with word-boundary wrapping output. The wrapping semantics themselves are well-understood and simple (break at spaces, hard-break long words). No complex algorithm is needed.

## Common Pitfalls

### Pitfall 1: Trailing Spaces on Wrapped Lines
**What goes wrong:** If a space is emitted before checking whether the next word fits, wrapped lines end with a trailing space (e.g., `"hello "`).
**Why it happens:** Eager space emission -- the wrapper outputs the space as soon as it sees it, then discovers the next word doesn't fit and emits a newline.
**How to avoid:** Defer space emission. Buffer the space as `pending_space = True` and only emit it when the next word is confirmed to fit on the current line. If wrapping occurs, the pending space is dropped.
**Warning signs:** Test assertions showing trailing whitespace on wrapped lines.

### Pitfall 2: Label Text Not Counted in Column Position
**What goes wrong:** Word wrapping only accounts for Claude's response text, but "Claude: " prefix (8 chars) was already written to the same line, causing the first wrapped line to exceed the width.
**Why it happens:** The wrapper is initialized with column=0 but `log.write("Claude: ")` was called directly, bypassing the wrapper.
**How to avoid:** ALL text going to a wrapped destination MUST flow through the wrapper, including labels ("You: ", "Claude: "), turn separators, error messages. Alternatively, route label writes through `wrapper.feed()` instead of calling `log.write()` directly.
**Warning signs:** First line of Claude's response extends past terminal width by exactly 8 characters.

### Pitfall 3: Wrap-Inserted Newlines Triggering Audio Bell
**What goes wrong:** The audio bell (AUDI-01) plays on every newline. If the wrapper inserts newlines for wrapping, the bell plays on every wrapped line, not just actual paragraph breaks.
**Why it happens:** The wrapper is placed before the output multiplexer, so its inserted newlines flow to all destinations including audio.
**How to avoid:** The wrapper wraps ONLY the TUI destination (`log.write`), not the shared `output_fn`. Audio receives original characters without wrap-inserted newlines. The architecture is: `output_fn = make_output_fn(tui_wrapper.feed, printer_write, bell_write, transcript_write)` where only `tui_wrapper.feed` inserts TUI-specific newlines.
**Warning signs:** Bell sound plays mid-sentence when long lines wrap.

### Pitfall 4: Printer Graceful Degradation Lost During Refactor
**What goes wrong:** Replacing the hard-break logic in `make_printer_output` with WordWrapper removes the `try/except OSError` handling and the `disconnected` flag.
**Why it happens:** The word-wrap refactor focuses on wrapping logic and forgets the error-handling wrapper around driver.write.
**How to avoid:** Keep the `disconnected` flag and `try/except OSError` in `make_printer_output`. The WordWrapper's output_fn should be the error-handling wrapper, not `driver.write` directly.
**Warning signs:** Tests `test_make_printer_output_degrades_on_error` failing after refactor.

### Pitfall 5: Scrollbar Width Not Accounted For
**What goes wrong:** TUI wraps at `log.size.width` (e.g., 80) but the vertical scrollbar takes 2 columns, so actual visible width is 78. Lines appear to overflow or scrollbar overlaps text.
**Why it happens:** Using `log.size.width` without subtracting `log.scrollbar_size_vertical`.
**How to avoid:** Calculate effective width as `log.size.width - log.scrollbar_size_vertical`. Verified: in Textual 7.5.0 headless mode with 80-column terminal, `log.size.width=80` and `log.scrollbar_size_vertical=2`, giving effective width of 78.
**Warning signs:** Text wraps 2 characters too late; horizontal scrollbar appears.

### Pitfall 6: Word Buffer Not Flushed at End of Stream
**What goes wrong:** The last word of Claude's response is lost because it was still in the word buffer when streaming ended.
**Why it happens:** End of text_delta stream doesn't trigger a space or newline, so the last word stays buffered.
**How to avoid:** Call `wrapper.flush()` explicitly at end of response streaming (in the `stream_response` method's post-loop code, alongside `log.write("\n")`).
**Warning signs:** Last word of response is missing.

## Code Examples

Verified patterns from investigation:

### WordWrapper Core Implementation
```python
# Source: prototype tested during research
class WordWrapper:
    """Streaming character-level word wrapper.

    Buffers the current word and inserts newlines at word boundaries
    when a word would exceed the configured line width.
    """

    def __init__(self, width: int, output_fn: Callable[[str], None]) -> None:
        self._width = width
        self._output_fn = output_fn
        self._column = 0
        self._word_buffer: list[str] = []
        self._pending_space = False

    @property
    def width(self) -> int:
        return self._width

    @width.setter
    def width(self, value: int) -> None:
        self._width = max(1, value)

    def feed(self, char: str) -> None:
        """Feed a single character through the wrapper."""
        if char == "\n":
            self._flush_word()
            self._pending_space = False
            self._output_fn("\n")
            self._column = 0
        elif char == " ":
            self._flush_word()
            if self._column > 0:
                self._pending_space = True
        else:
            self._word_buffer.append(char)

    def _flush_word(self) -> None:
        if not self._word_buffer:
            return
        word_len = len(self._word_buffer)
        space_needed = (1 if self._pending_space else 0) + word_len

        if self._column + space_needed > self._width and self._column > 0:
            self._output_fn("\n")
            self._column = 0
            self._pending_space = False

        if self._pending_space and self._column > 0:
            self._output_fn(" ")
            self._column += 1
        self._pending_space = False

        for ch in self._word_buffer:
            if self._column >= self._width:
                self._output_fn("\n")
                self._column = 0
            self._output_fn(ch)
            self._column += 1
        self._word_buffer.clear()

    def flush(self) -> None:
        """Flush any remaining buffered word."""
        self._flush_word()
```

### Getting Effective TUI Width
```python
# Source: verified in Textual 7.5.0 headless mode
log = self.query_one("#output", Log)
effective_width = log.size.width - log.scrollbar_size_vertical
# Example: 80-col terminal -> log.size.width=80, scrollbar=2, effective=78
```

### Handling Resize Events
```python
# Source: verified in Textual 7.5.0 -- on_resize fires on App
from textual import events

class TeletypeApp(App):
    def on_resize(self, event: events.Resize) -> None:
        if self._tui_wrapper is not None:
            log = self.query_one("#output", Log)
            self._tui_wrapper.width = log.size.width - log.scrollbar_size_vertical
```

### Wiring WordWrapper in TUI stream_response
```python
# In stream_response method:
log = self.query_one("#output", Log)
effective_width = log.size.width - log.scrollbar_size_vertical
self._tui_wrapper = WordWrapper(effective_width, log.write)

destinations = [self._tui_wrapper.feed]  # TUI gets wrapped output
if self._printer_write is not None:
    destinations.append(self._printer_write)  # printer has own wrapping
if not self.no_audio:
    destinations.append(make_bell_output())
if self._transcript_write is not None:
    destinations.append(self._transcript_write)

output_fn = make_output_fn(*destinations)

# ... streaming loop ...

# After streaming loop:
self._tui_wrapper.flush()
self._tui_wrapper = None
log.write("\n")
```

### Upgrading make_printer_output to Word Wrap
```python
def make_printer_output(driver: PrinterDriver) -> Callable[[str], None]:
    """Create output_fn with word-wrap at A4_COLUMNS and graceful degradation."""
    disconnected = False

    def safe_write(char: str) -> None:
        nonlocal disconnected
        if disconnected:
            return
        try:
            driver.write(char)
        except OSError:
            disconnected = True

    wrapper = WordWrapper(A4_COLUMNS, safe_write)

    def printer_write(char: str) -> None:
        if disconnected:
            return
        wrapper.feed(char)

    return printer_write
```

## State of the Art

| Old Approach | Current Approach | When Changed | Impact |
|--------------|------------------|--------------|--------|
| Hard-break at column 80 in printer output | Word-boundary wrapping (this phase) | Phase 7 | Words no longer split mid-word on printer |
| No wrapping in TUI (Log with no_wrap=True) | WordWrapper filter before log.write (this phase) | Phase 7 | Lines no longer extend off-screen in TUI |

**Deprecated/outdated:**
- Textual Log widget does NOT support CSS-based text wrapping. The `no_wrap=True` flag is hardcoded in the render method. This was confirmed by reading the Textual 7.5.0 source: `line_text = Text(_line, no_wrap=True)` in `Log.render_line()`.

## Open Questions

1. **Should `--no-tui` stdout mode also get word wrapping?**
   - What we know: WRAP-01 specifies TUI only, WRAP-02 specifies printer only. The `--no-tui` mode writes to `sys.stdout.write` directly.
   - What's unclear: Whether users of `--no-tui` mode want word-wrapped output. The terminal itself handles wrapping when output reaches the edge.
   - Recommendation: **Do not wrap stdout in `--no-tui` mode.** The terminal handles its own wrapping. Adding wrapping would be redundant and could interfere with pipe/redirect usage. This keeps scope minimal.

2. **Should wrap-inserted newlines be excluded from transcript?**
   - What we know: Transcript receives characters through `make_output_fn` alongside other destinations. Currently all destinations get the same characters.
   - What's unclear: Whether transcript should preserve original (unwrapped) text or wrapped text.
   - Recommendation: **Transcript receives unwrapped text.** The wrapper is per-destination (TUI and printer only). Transcript and audio receive original characters. This preserves clean text in transcripts and avoids false bell triggers.

3. **Should the "Claude: " and "You: " labels go through the wrapper or be written directly?**
   - What we know: Currently labels are written via `log.write("Claude: ")` directly. The wrapper needs to track column position. If labels bypass the wrapper, column is wrong.
   - What's unclear: Whether to route ALL log writes through the wrapper, or to manually set the wrapper's column after direct writes.
   - Recommendation: **Route all text to wrapped destinations through the wrapper.** Replace `log.write("Claude: ")` with individual `tui_wrapper.feed(ch)` calls for each character. This keeps column tracking accurate and simple. Alternative: write labels through a helper that both writes and updates the wrapper's column state.

## Sources

### Primary (HIGH confidence)
- Textual 7.5.0 source code (installed in project venv) -- verified `Log.render_line()` uses `no_wrap=True`, confirmed `Widget.size`, `Widget.scrollbar_size_vertical`, and `events.Resize` API
- Textual 7.5.0 headless mode testing -- confirmed `log.size.width=80`, `log.scrollbar_size_vertical=2` for 80-column terminal
- Python 3.12+ `textwrap.TextWrapper` documentation -- confirmed API and word-wrap semantics
- Codebase inspection: `tui.py`, `printer.py`, `output.py`, `pacer.py`, `bridge.py` -- confirmed data flow and current wrapping logic

### Secondary (MEDIUM confidence)
- Streaming word-wrap prototype tested during research session -- algorithm verified with edge cases (long words, exact boundaries, chunked streaming, multiple spaces, newlines)
- `shutil.get_terminal_size()` confirmed to work in non-tty environments (falls back to 80x24)

### Tertiary (LOW confidence)
- None

## Metadata

**Confidence breakdown:**
- Standard stack: HIGH -- no new dependencies, pure Python implementation using well-understood string processing
- Architecture: HIGH -- data flow verified by reading all relevant source files; wrapper placement confirmed by testing Log widget behavior
- Pitfalls: HIGH -- each pitfall identified from concrete codebase analysis (label column counting, audio newlines, scrollbar width, graceful degradation)

**Research date:** 2026-02-17
**Valid until:** 2026-03-17 (stable domain, no external dependencies to go stale)
