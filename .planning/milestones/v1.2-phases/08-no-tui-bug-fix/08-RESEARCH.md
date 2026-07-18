# Phase 8: No-TUI Bug Fix - Research

**Researched:** 2026-02-17
**Domain:** Bug fix -- `_chat_async` crash when StreamResult is yielded in headless mode
**Confidence:** HIGH

## Summary

The `--no-tui` code path in `cli.py` crashes with `TypeError: 'StreamResult' object is not iterable` because `_chat_async` passes every yielded item from `stream_claude_response()` directly to `pace_characters()` without checking its type. The async generator `stream_claude_response()` yields `str | StreamResult`, where `StreamResult` is always the final item containing session metadata. The TUI code path in `tui.py` correctly handles this with an `isinstance(item, StreamResult)` check (line 278), but `_chat_async` was never updated when `StreamResult` was introduced in Phase 5.

This is a focused, single-function bug fix with well-understood root cause, clear fix pattern (the TUI provides the template), and a gap in test coverage that should be addressed simultaneously.

**Primary recommendation:** Add `isinstance(item, StreamResult)` type dispatch to `_chat_async`'s stream loop, mirroring the TUI's pattern, and write tests for the `_chat_async` function covering normal flow, StreamResult handling, error StreamResult, and empty response.

<phase_requirements>
## Phase Requirements

| ID | Description | Research Support |
|----|-------------|-----------------|
| FIX-01 | `--no-tui` mode handles StreamResult without crashing and has test coverage | Root cause identified: `_chat_async` in `cli.py` (line 97) passes `StreamResult` objects to `pace_characters()` which expects `str`. Fix pattern exists in `tui.py` (line 278). Zero existing tests for `_chat_async` -- all test infrastructure (pytest-asyncio, mock subprocess patterns) is already in place from `test_bridge.py`. |
</phase_requirements>

## Standard Stack

### Core

No new libraries needed. This is a bug fix on existing code using existing dependencies.

| Library | Version | Purpose | Already Used |
|---------|---------|---------|--------------|
| pytest | >=9.0.2 | Test framework | Yes, in dev dependencies |
| pytest-asyncio | >=1.3.0 | Async test support | Yes, `asyncio_mode = "auto"` in pyproject.toml |
| unittest.mock | stdlib | AsyncMock, MagicMock, patch | Yes, used extensively in test_bridge.py |

**Installation:** No new packages required.

## Architecture Patterns

### The Bug: Missing Type Dispatch in `_chat_async`

**File:** `src/claude_teletype/cli.py`, function `_chat_async`, lines 97-106

**Current (broken) code:**
```python
async for text_chunk in stream_claude_response(prompt):
    if first_token:
        status.stop()
        first_token = False
    await pace_characters(
        text_chunk,              # <-- BUG: text_chunk can be StreamResult
        base_delay_ms=base_delay_ms,
        output_fn=output_fn,
    )
```

**What happens:**
1. `stream_claude_response()` yields `str | StreamResult` (type annotation on line 170 of bridge.py)
2. `StreamResult` is always the final yield (line 262 of bridge.py)
3. `pace_characters()` expects `text: str` and does `for char in text:` (line 51 of pacer.py)
4. `StreamResult` is a dataclass, not iterable -- `TypeError: 'StreamResult' object is not iterable`

**Crash confirmed empirically:** Running `StreamResult(session_id='test')` through iteration raises `TypeError`.

### The Fix Pattern: TUI's Type Dispatch

**File:** `src/claude_teletype/tui.py`, method `stream_response`, lines 273-317

```python
async for item in stream_claude_response(
    prompt,
    session_id=self._session_id,
    proc_holder=self._proc_holder,
):
    if isinstance(item, StreamResult):
        # Handle metadata: session_id, error status, model info, context pct
        if item.is_error:
            # Error handling with retry logic
            ...
        else:
            self._session_id = item.session_id
        self._model_name = extract_model_name(item.model_usage) or "--"
        self._context_pct = calc_context_pct(item.model_usage)
        self._update_status()
    else:
        has_text = True
        await pace_characters(
            item,
            base_delay_ms=self.base_delay_ms,
            output_fn=output_fn,
        )
```

**Key decisions for the no-TUI fix:**
1. `isinstance(item, StreamResult)` check before pace_characters
2. No retry logic needed in `_chat_async` (single-shot mode, not multi-turn)
3. StreamResult error should be reported to stderr/console (not swallowed)
4. StreamResult success metadata can be silently consumed (or optionally logged)

### Recommended Fix Structure

The fix should:
1. Import `StreamResult` in `_chat_async` (already imported from bridge at top of cli.py via `stream_claude_response`, but `StreamResult` itself needs explicit import)
2. Use `isinstance(item, StreamResult)` dispatch inside the `async for` loop
3. For error StreamResult: print error message to console via `console.print()`
4. For success StreamResult: silently consume (no status bar in headless mode)
5. Only pass `str` items to `pace_characters()`

### Test Pattern: Mock Subprocess Stream

The project has an established test pattern in `test_bridge.py` for mocking the Claude subprocess:

```python
# 1. Define NDJSON lines as byte sequences
ndjson_lines = [
    SYSTEM_INIT + b"\n",
    TEXT_DELTA_HELLO + b"\n",
    RESULT_MESSAGE_FULL + b"\n",
    b"",  # EOF
]

# 2. Build mock process with async readline
mock_stdout = MagicMock()
line_iter = iter(ndjson_lines)
mock_stdout.readline = AsyncMock(side_effect=lambda: next(line_iter))

mock_proc = MagicMock()
mock_proc.stdout = mock_stdout
mock_proc.wait = AsyncMock(return_value=0)
mock_proc.terminate = MagicMock()

# 3. Patch create_subprocess_exec
with patch(
    "claude_teletype.bridge.asyncio.create_subprocess_exec",
    new_callable=AsyncMock,
    return_value=mock_proc,
):
    # 4. Call the function under test
    ...
```

For testing `_chat_async`, additional mocking is needed:
- `console.status()` context manager (Rich spinner) -- patch or use `nullcontext`
- `sys.stdout.write` -- capture output
- `asyncio.sleep` in pacer -- mock to zero delay
- `make_transcript_output` -- mock to avoid filesystem side effects

### Anti-Patterns to Avoid
- **String conversion instead of type check:** Do NOT do `str(text_chunk)` as a workaround. `str(StreamResult(...))` would produce a repr string and output it as typewriter text, which is wrong.
- **Try/except TypeError:** Do NOT catch the iteration error. The proper fix is type dispatch, not error suppression.
- **Checking for `str` instead of `StreamResult`:** Prefer `isinstance(item, StreamResult)` over `isinstance(item, str)` because `StreamResult` is the special case. This matches the TUI pattern and is forward-compatible if more types are added.

## Don't Hand-Roll

| Problem | Don't Build | Use Instead | Why |
|---------|-------------|-------------|-----|
| Async test support | Custom event loop setup | pytest-asyncio with `asyncio_mode = "auto"` | Already configured in pyproject.toml |
| Mock subprocess | Real subprocess spawning in tests | AsyncMock + patch pattern from test_bridge.py | Established project pattern, fast, deterministic |
| Console output capture | Custom stdout capture | `unittest.mock.patch("sys.stdout")` or `io.StringIO` | Standard approach, no dependencies |

## Common Pitfalls

### Pitfall 1: Forgetting to Import StreamResult in cli.py
**What goes wrong:** The fix adds `isinstance(item, StreamResult)` but StreamResult is not imported.
**Why it happens:** `cli.py` currently only imports `stream_claude_response` from bridge, not `StreamResult`.
**How to avoid:** Add `StreamResult` to the import statement on line 18 of cli.py.
**Warning signs:** `NameError: name 'StreamResult' is not defined` at runtime.

### Pitfall 2: Not Testing the Error StreamResult Path
**What goes wrong:** Tests only cover happy path (text + success StreamResult), missing the error StreamResult case.
**Why it happens:** Error StreamResult is rare in normal usage but critical for reliability.
**How to avoid:** Write explicit test for `_chat_async` receiving an error StreamResult (with `is_error=True`, `error_message` set).
**Warning signs:** No test covers `sr.is_error` branch in the no-TUI code path.

### Pitfall 3: Transcript and Printer Getting StreamResult String
**What goes wrong:** If the fix converts StreamResult to string for output, transcript and printer get garbage.
**Why it happens:** `output_fn` fans to all destinations (stdout, printer, transcript, audio).
**How to avoid:** StreamResult handling must happen OUTSIDE the pace_characters call, not by converting to string.
**Warning signs:** Transcript files containing `StreamResult(session_id=...` text.

### Pitfall 4: Test Isolation -- Filesystem Side Effects
**What goes wrong:** `_chat_async` creates transcript files via `make_transcript_output`. Tests that call `_chat_async` will write files to disk.
**Why it happens:** `make_transcript_output` creates directories and opens file handles.
**How to avoid:** Either mock `make_transcript_output` or pass a `tmp_path` transcript_dir to avoid polluting the project directory.
**Warning signs:** Spurious transcript files appearing after test runs.

### Pitfall 5: Rich Console Status Spinner in Tests
**What goes wrong:** `console.status()` context manager in `_chat_async` may produce output or require terminal features during tests.
**Why it happens:** Rich Console uses terminal capabilities that may not be available in test environments.
**How to avoid:** Patch `console.status` to return a mock context manager, or set `Console(force_terminal=False)` in test setup.
**Warning signs:** Test output polluted with spinner artifacts, or tests failing in CI.

## Code Examples

### Example 1: The Fix for `_chat_async`

Based on the TUI pattern, the fix for `cli.py` `_chat_async` should look like:

```python
# In _chat_async, change the stream loop from:
async for text_chunk in stream_claude_response(prompt):
    if first_token:
        status.stop()
        first_token = False
    await pace_characters(text_chunk, ...)

# To:
from claude_teletype.bridge import StreamResult

async for item in stream_claude_response(prompt):
    if isinstance(item, StreamResult):
        if item.is_error:
            console.print(f"\n[bold red]Error: {item.error_message}")
        # Success metadata silently consumed in headless mode
        break  # StreamResult is always last, can break
    if first_token:
        status.stop()
        first_token = False
    await pace_characters(item, base_delay_ms=base_delay_ms, output_fn=output_fn)
```

### Example 2: Test for `_chat_async` Normal Flow

```python
@pytest.mark.asyncio
async def test_chat_async_streams_text_with_stream_result():
    """_chat_async completes without crash when StreamResult is yielded."""
    ndjson_lines = [
        SYSTEM_INIT + b"\n",
        TEXT_DELTA_HELLO + b"\n",
        RESULT_MESSAGE_FULL + b"\n",
        b"",
    ]
    mock_stdout = MagicMock()
    line_iter = iter(ndjson_lines)
    mock_stdout.readline = AsyncMock(side_effect=lambda: next(line_iter))

    mock_proc = MagicMock()
    mock_proc.stdout = mock_stdout
    mock_proc.wait = AsyncMock(return_value=0)
    mock_proc.terminate = MagicMock()

    captured = []

    with patch(
        "claude_teletype.bridge.asyncio.create_subprocess_exec",
        new_callable=AsyncMock,
        return_value=mock_proc,
    ), patch(
        "claude_teletype.pacer.asyncio.sleep",
        new_callable=AsyncMock,
    ), patch(
        "claude_teletype.cli.console",
    ) as mock_console:
        mock_console.status.return_value.__enter__ = MagicMock()
        mock_console.status.return_value.__exit__ = MagicMock()

        await _chat_async(
            "test",
            base_delay_ms=0,
            no_audio=True,
            transcript_dir=str(tmp_path),
        )
    # Verify no crash occurred -- test passes if we get here
```

### Example 3: Test for Error StreamResult in No-TUI Mode

```python
@pytest.mark.asyncio
async def test_chat_async_handles_error_stream_result():
    """_chat_async displays error when StreamResult has is_error=True."""
    ndjson_lines = [
        RESULT_MESSAGE_ERROR + b"\n",
        b"",
    ]
    # ... similar mock setup ...
    # Verify console.print was called with error message
```

## State of the Art

| Old Approach | Current Approach | When Changed | Impact |
|--------------|------------------|--------------|--------|
| `stream_claude_response` yielded only `str` | Yields `str \| StreamResult` (union type) | Phase 5 (v1.1) | TUI updated, `_chat_async` was not |

**Root cause of the bug:** Phase 5 (Multi-Turn Conversation Foundation) changed `stream_claude_response` to yield `StreamResult` as its final item for session metadata. The TUI's `stream_response` was updated accordingly, but `_chat_async` (the non-TUI code path) was not updated because it was a secondary/fallback code path.

## Open Questions

1. **Should `_chat_async` display StreamResult metadata to the user?**
   - What we know: TUI shows model name, context percentage, and turn count in status bar.
   - What's unclear: In headless mode, should cost/model/context be printed to stderr?
   - Recommendation: For the bug fix, minimal approach -- only display errors. Metadata display can be added later if users request it. Keep the fix small and focused.

2. **Should `_chat_async` support multi-turn conversation?**
   - What we know: Currently requires `prompt` argument with `--no-tui`, single-shot only.
   - What's unclear: Whether users want interactive headless mode.
   - Recommendation: Out of scope for this bug fix. The current single-shot design is correct for piped/scripted usage. Multi-turn is the TUI's job.

## Sources

### Primary (HIGH confidence)
- **Source code inspection** (all files read directly from the repository):
  - `src/claude_teletype/cli.py` -- the buggy `_chat_async` function (lines 44-117)
  - `src/claude_teletype/bridge.py` -- `StreamResult` dataclass (lines 25-39) and `stream_claude_response` generator (lines 166-283)
  - `src/claude_teletype/tui.py` -- correct `stream_response` pattern (lines 221-349)
  - `src/claude_teletype/pacer.py` -- `pace_characters` function that crashes (lines 36-59)
- **Runtime verification** -- confirmed `StreamResult` is not iterable via Python interpreter
- **Test suite** -- 265 tests pass, zero tests exist for `_chat_async` or `--no-tui` path

### Secondary (MEDIUM confidence)
- None needed -- this is a straightforward code-level bug with full source visibility.

### Tertiary (LOW confidence)
- None.

## Metadata

**Confidence breakdown:**
- Standard stack: HIGH -- no new dependencies, existing test infrastructure
- Architecture: HIGH -- fix pattern directly visible in TUI code, root cause confirmed empirically
- Pitfalls: HIGH -- all pitfalls identified from code inspection, not speculation

**Research date:** 2026-02-17
**Valid until:** Indefinite (bug fix on stable code, no external dependencies to age)
