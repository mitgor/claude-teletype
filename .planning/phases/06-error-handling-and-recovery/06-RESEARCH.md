# Phase 6: Error Handling and Recovery - Research

**Researched:** 2026-02-16
**Domain:** Subprocess error detection, error classification, exponential backoff retry, session recovery, CLI availability checking
**Confidence:** HIGH

## Summary

Phase 6 hardens the Claude Teletype application against the six most common failure modes when wrapping Claude Code CLI as a subprocess. The codebase already has partial error handling from Phase 5 (kill-with-timeout subprocess cleanup, resume failure fallback to new session), but it lacks pre-flight CLI detection, error message classification, subprocess timeouts on the read loop, and retry logic for transient API errors.

The implementation requires no new external dependencies. All error handling uses Python stdlib: `shutil.which` for CLI detection, `asyncio.wait_for` for subprocess read timeouts, and a hand-rolled exponential backoff loop (simple enough that a library like `tenacity` would be overkill for a single retry site). The error classification system maps Claude Code's NDJSON `result` messages and subprocess exit codes to human-readable categories: network, authentication, rate limit, context exhausted, and overloaded. The key architectural change is wrapping `stream_claude_response()` with error detection at the bridge level and retry/recovery logic at the TUI level.

Two important discoveries from research: (1) Claude Code CLI v2.1.38+ has a known bug where stream-json mode can hang indefinitely after emitting the result event (issue #25629), making subprocess read timeouts essential rather than optional; (2) Claude Code's own retry logic handles some 429/529 errors internally (up to 10 retries), but the NDJSON result message still arrives as `is_error: true` with `error_during_execution` subtype when all retries are exhausted, so our wrapper needs its own retry layer for resilience.

**Primary recommendation:** Build in three layers: (1) pre-flight validation in CLI entry point, (2) error classification and timeout protection in bridge, (3) retry logic and user notification in TUI. Each layer is independently testable.

<phase_requirements>
## Phase Requirements

| ID | Description | Research Support |
|----|-------------|-----------------|
| ERR-01 | User sees a clear message when Claude Code CLI is not installed, with install URL | `shutil.which("claude")` check at CLI startup, before TUI launch. If None, print clear message with install URL `https://claude.ai/install.sh` and exit. Catches the `FileNotFoundError` that `asyncio.create_subprocess_exec` raises when binary is missing. |
| ERR-02 | User sees categorized error messages (network, auth, rate limit, context exhausted) instead of raw exceptions | Parse `StreamResult.error_message` text against known patterns. Claude Code result messages contain identifiable strings: "overloaded", "rate_limit", "authentication", "context window", "No messages returned". Map to user-friendly categories with actionable guidance. |
| ERR-03 | Subprocess timeouts prevent the app from hanging when Claude Code stops responding | Wrap `proc.stdout.readline()` with `asyncio.wait_for(timeout=...)`. Known issue #25629: Claude Code CLI can hang after emitting result in stream-json mode. A per-line read timeout (e.g., 300s) prevents indefinite blocking. On timeout, kill subprocess and yield error StreamResult. |
| ERR-04 | Zombie/orphaned Claude Code processes are cleaned up with kill-with-timeout pattern | Already implemented in Phase 5 (TUI `_kill_process`: SIGTERM -> wait 5s -> SIGKILL). Phase 6 adds: (a) cleanup on subprocess timeout, (b) cleanup on bridge-level exceptions, (c) `on_unmount` already calls `_kill_process`. Verify coverage is complete for all error paths. |
| ERR-05 | Rate limit and overload errors trigger automatic retry with exponential backoff and user notification | On `StreamResult.is_error` with rate limit/overloaded classification, retry the entire `stream_claude_response()` call with exponential backoff (1s, 2s, 4s, max 3 retries). Show "[Rate limited. Retrying in Ns...]" in TUI log. Give up after max retries with clear message. |
| ERR-06 | Corrupted session recovery -- on `--resume` failure, fall back to new session and inform user | Already partially implemented in Phase 5 TUI (lines 244-249: if `is_error` and `session_id`, reset to None and show warning). Phase 6 enhances: classify the error type, provide specific message (e.g., "Session corrupted after interrupted response"), and ensure the retry does not use the corrupted session_id. |
</phase_requirements>

## Standard Stack

### Core
| Library | Version | Purpose | Why Standard |
|---------|---------|---------|--------------|
| shutil | stdlib | `shutil.which("claude")` for CLI detection | Standard Python utility for checking executable availability in PATH. Cross-platform. |
| asyncio | stdlib | `asyncio.wait_for()` for subprocess read timeouts, subprocess lifecycle | Already used extensively. `wait_for` wraps any awaitable with a timeout. |
| json | stdlib | NDJSON parsing (already used in bridge.py) | Parse error messages from Claude Code result NDJSON lines. |

### Supporting
| Library | Version | Purpose | When to Use |
|---------|---------|---------|-------------|
| dataclasses | stdlib | Extend StreamResult with error category field | Optionally add `error_category: str | None` to StreamResult for typed error classification |
| time | stdlib | `time.monotonic()` for backoff timing | Simple monotonic clock for retry delay measurement |
| random | stdlib | Jitter for exponential backoff | Add randomness to retry delays to avoid thundering herd |

### Alternatives Considered
| Instead of | Could Use | Tradeoff |
|------------|-----------|----------|
| Hand-rolled exponential backoff | `tenacity` library (PyPI) | Tenacity is the standard retry library, but adds a dependency for a single retry site with 3 retries. Hand-rolled loop is ~15 lines. Use stdlib only. |
| String-matching error classification | Structured error codes from Claude Code | Claude Code NDJSON does not expose structured error codes -- only `is_error: bool`, `subtype: str`, and a human-readable `result` string. String matching on known patterns is the only option. |
| Per-line read timeout | Overall subprocess timeout | Per-line timeout is more precise. An overall timeout would kill successful but slow responses. The known hang bug (issue #25629) occurs AFTER the result event, so per-line timeout catches it at the right moment. |

**Installation:** No changes to pyproject.toml. Zero new dependencies.

## Architecture Patterns

### Recommended Changes by File

```
src/claude_teletype/
├── bridge.py           # MODIFY: add readline timeout, error classification helper, CLI check
├── tui.py              # MODIFY: add retry loop, user-facing error messages, retry notifications
├── cli.py              # MODIFY: add pre-flight CLI check before TUI launch
├── output.py           # NO CHANGE
├── pacer.py            # NO CHANGE
├── audio.py            # NO CHANGE
├── printer.py          # NO CHANGE
├── transcript.py       # NO CHANGE
└── teletype.py         # NO CHANGE
```

### Pattern 1: Pre-flight CLI Validation

**What:** Check for `claude` binary in PATH before launching the TUI or running a prompt. If missing, print a clear message with install URL and exit.

**When to use:** At the CLI entry point, before any subprocess is spawned.

**Example:**
```python
# Source: Python stdlib shutil.which docs
import shutil
import sys
import typer

INSTALL_URL = "https://claude.ai/install.sh"

def check_claude_installed() -> None:
    """Verify Claude Code CLI is available in PATH."""
    if shutil.which("claude") is None:
        console.print(
            "[bold red]Claude Code CLI is not installed.[/bold red]\n\n"
            f"Install it with:\n"
            f"  curl -fsSL {INSTALL_URL} | bash\n\n"
            f"Or visit: https://code.claude.com/docs/en/quickstart",
        )
        raise typer.Exit(1)
```

**Why `shutil.which` over try/except on subprocess:** Fail fast with a clear message. Without this check, `asyncio.create_subprocess_exec("claude", ...)` raises `FileNotFoundError` which propagates as an opaque stack trace.

### Pattern 2: Error Classification via String Matching

**What:** Classify Claude Code error messages into actionable categories by matching known substrings in the `StreamResult.error_message` and `StreamResult.is_error` / result `subtype` fields.

**When to use:** After receiving a `StreamResult` with `is_error=True`.

**Example:**
```python
# Source: Codebase analysis + Claude Code GitHub issues research
from enum import Enum

class ErrorCategory(Enum):
    RATE_LIMIT = "rate_limit"
    OVERLOADED = "overloaded"
    AUTH = "auth"
    NETWORK = "network"
    CONTEXT_EXHAUSTED = "context_exhausted"
    SESSION_CORRUPT = "session_corrupt"
    UNKNOWN = "unknown"

# Known error message patterns from Claude Code CLI NDJSON output
ERROR_PATTERNS: list[tuple[str, ErrorCategory]] = [
    ("rate_limit", ErrorCategory.RATE_LIMIT),
    ("rate limit", ErrorCategory.RATE_LIMIT),
    ("429", ErrorCategory.RATE_LIMIT),
    ("overloaded", ErrorCategory.OVERLOADED),
    ("529", ErrorCategory.OVERLOADED),
    ("authentication", ErrorCategory.AUTH),
    ("auth", ErrorCategory.AUTH),
    ("API key", ErrorCategory.AUTH),
    ("not authenticated", ErrorCategory.AUTH),
    ("context window", ErrorCategory.CONTEXT_EXHAUSTED),
    ("context length", ErrorCategory.CONTEXT_EXHAUSTED),
    ("max.*token", ErrorCategory.CONTEXT_EXHAUSTED),
    ("No messages returned", ErrorCategory.SESSION_CORRUPT),
    ("fetch failed", ErrorCategory.NETWORK),
    ("ECONNREFUSED", ErrorCategory.NETWORK),
    ("ETIMEDOUT", ErrorCategory.NETWORK),
    ("network", ErrorCategory.NETWORK),
]

ERROR_MESSAGES: dict[ErrorCategory, str] = {
    ErrorCategory.RATE_LIMIT: "Rate limit reached. Claude Code will retry automatically, or try again in a few minutes.",
    ErrorCategory.OVERLOADED: "Claude API is temporarily overloaded. This usually clears up in 5-15 minutes.",
    ErrorCategory.AUTH: "Authentication error. Run 'claude auth' to re-authenticate.",
    ErrorCategory.NETWORK: "Network error. Check your internet connection.",
    ErrorCategory.CONTEXT_EXHAUSTED: "Context window exhausted. Start a new conversation.",
    ErrorCategory.SESSION_CORRUPT: "Session corrupted (likely from an interrupted response). Starting new session.",
    ErrorCategory.UNKNOWN: "An error occurred. Check Claude Code logs for details.",
}

def classify_error(error_message: str | None) -> ErrorCategory:
    """Classify an error message from Claude Code into a category."""
    if not error_message:
        return ErrorCategory.UNKNOWN
    lower = error_message.lower()
    for pattern, category in ERROR_PATTERNS:
        if pattern.lower() in lower:
            return category
    return ErrorCategory.UNKNOWN
```

**Confidence:** MEDIUM -- the error message patterns are derived from GitHub issues and observed Claude Code behavior, not from a formal API specification. The patterns may need updating as Claude Code evolves. The `classify_error` function should use simple substring matching (not regex) for most patterns to keep it maintainable.

### Pattern 3: Subprocess Read Timeout

**What:** Wrap each `proc.stdout.readline()` call with `asyncio.wait_for()` to prevent indefinite blocking.

**When to use:** In the main read loop of `stream_claude_response()`.

**Example:**
```python
# Source: Python asyncio docs + Claude Code issue #25629 (stream-json hang)
READ_TIMEOUT_SECONDS = 300  # 5 minutes per line -- generous for long tool runs

async def stream_claude_response(prompt, session_id=None, proc_holder=None):
    proc = await asyncio.create_subprocess_exec(...)
    # ... setup ...
    try:
        while True:
            try:
                line = await asyncio.wait_for(
                    proc.stdout.readline(),
                    timeout=READ_TIMEOUT_SECONDS,
                )
            except asyncio.TimeoutError:
                # Subprocess hung -- kill it and yield error
                break
            if not line:
                break  # EOF
            # ... parse and yield ...
        await proc.wait()
    except BaseException:
        proc.terminate()
        await proc.wait()
        raise
```

**Why 300 seconds:** Claude Code can run tool operations (Bash, Edit) that take several minutes. A 5-minute per-line timeout is generous enough to not interrupt legitimate work but catches the known stream-json hang bug where the process emits no output for 5+ minutes after completing.

### Pattern 4: Exponential Backoff Retry at TUI Level

**What:** When `stream_response` receives a retryable error (rate limit or overloaded), retry the entire `stream_claude_response()` call with exponential backoff delays.

**When to use:** In the TUI `stream_response` worker, wrapping the `async for` loop.

**Example:**
```python
# Source: Standard exponential backoff pattern (stdlib only)
import random

MAX_RETRIES = 3
BASE_DELAY = 1.0  # seconds

@work(exclusive=True)
async def stream_response(self, prompt: str) -> None:
    log = self.query_one("#output", Log)
    retries = 0

    while retries <= MAX_RETRIES:
        try:
            async for item in stream_claude_response(
                prompt, session_id=self._session_id, proc_holder=self._proc_holder
            ):
                if isinstance(item, StreamResult):
                    if item.is_error:
                        category = classify_error(item.error_message)
                        if category in (ErrorCategory.RATE_LIMIT, ErrorCategory.OVERLOADED) and retries < MAX_RETRIES:
                            retries += 1
                            delay = BASE_DELAY * (2 ** (retries - 1)) + random.uniform(0, 1)
                            log.write(f"\n[{ERROR_MESSAGES[category]} Retrying in {delay:.0f}s... (attempt {retries}/{MAX_RETRIES})]\n")
                            await asyncio.sleep(delay)
                            break  # Break inner loop to retry
                        else:
                            # Non-retryable error or max retries reached
                            log.write(f"\n[Error: {ERROR_MESSAGES.get(category, ERROR_MESSAGES[ErrorCategory.UNKNOWN])}]\n")
                            return
                    # ... handle success ...
                else:
                    await pace_characters(item, ...)
            else:
                # Inner loop completed without break (success)
                return
        except asyncio.CancelledError:
            raise
        except Exception as exc:
            log.write(f"\n[Error: {exc}]\n")
            return
```

### Pattern 5: Enhanced Session Recovery

**What:** Classify resume failures by error category and provide specific recovery messages.

**When to use:** When `StreamResult.is_error` is True and `self._session_id` is not None (resume was attempted).

**Example:**
```python
# Source: Phase 5 existing pattern (tui.py lines 244-249) + error classification
if isinstance(item, StreamResult):
    if item.is_error and self._session_id is not None:
        category = classify_error(item.error_message)
        self._session_id = None  # Reset to new session
        msg = ERROR_MESSAGES.get(category, ERROR_MESSAGES[ErrorCategory.SESSION_CORRUPT])
        log.write(f"\n[{msg}]\n")
        # Do NOT retry with the corrupted session_id
```

### Anti-Patterns to Avoid

- **Catching FileNotFoundError deep in the bridge:** Check CLI availability at startup, not inside `stream_claude_response`. The bridge should assume `claude` exists. Mixing pre-flight validation with streaming logic creates confusing error surfaces.
- **Using regex for error classification:** Simple substring matching (`"overloaded" in msg.lower()`) is clearer, faster, and more maintainable than regex patterns for known error strings.
- **Retrying with a corrupted session_id:** After a resume failure, the session_id MUST be reset to None before any retry. Retrying with the same broken session will fail again.
- **Setting subprocess read timeout too low:** Claude Code can invoke tools (Bash commands, file operations) that legitimately take minutes. A timeout under 60 seconds will cause false positives. Use 300 seconds (5 minutes) for individual line reads.
- **Adding `tenacity` or `backoff` library:** For a single retry site with 3 retries, a hand-rolled loop is simpler than a new dependency. The retry logic is ~15 lines.
- **Retrying on all errors:** Only retry on transient errors (rate limit, overloaded). Auth errors, context exhausted, and network errors should not be retried automatically -- they require user action.

## Don't Hand-Roll

| Problem | Don't Build | Use Instead | Why |
|---------|-------------|-------------|-----|
| CLI existence check | Manual PATH search or try/except on subprocess spawn | `shutil.which("claude")` | stdlib, cross-platform, handles all PATH resolution edge cases |
| Subprocess timeout | Custom timer thread or signal-based timeout | `asyncio.wait_for(readline(), timeout=N)` | stdlib, integrated with asyncio event loop, clean TimeoutError semantics |
| Process cleanup | Manual SIGTERM/SIGKILL sequences | Existing `_kill_process()` from Phase 5 | Already implemented and tested with the correct SIGTERM -> 5s -> SIGKILL pattern |

**Key insight:** Error handling in a subprocess wrapper is mostly about detection and classification, not complex recovery. The Claude Code CLI handles its own retries, context compaction, and session management. Our wrapper's job is to (1) detect when something went wrong, (2) tell the user what happened in plain language, and (3) retry when the error is transient.

## Common Pitfalls

### Pitfall 1: Stream-JSON Hang After Result Event
**What goes wrong:** Claude Code CLI emits the `{"type":"result","subtype":"success"}` NDJSON line but never closes stdout or exits. The Python `readline()` call blocks forever waiting for the next line that never comes.
**Why it happens:** Known Claude Code CLI bug (issue #25629, reported Feb 2026, still open as of research date). Affects v2.1.38+. The Node.js process fails to trigger its exit routine after the result event.
**How to avoid:** Wrap `readline()` with `asyncio.wait_for(timeout=300)`. After receiving the result message, consider using a shorter timeout (e.g., 30 seconds) since no more content is expected.
**Warning signs:** Process hangs after all text has been streamed, with the result message already captured.

### Pitfall 2: False Positive Error Classification
**What goes wrong:** A legitimate Claude response contains the word "overloaded" or "rate limit" in its text content, and the classifier triggers a false retry.
**Why it happens:** Error classification is applied to `StreamResult.error_message`, but if the code accidentally classifies text delta content or non-error result messages, false positives occur.
**How to avoid:** ONLY classify errors when `StreamResult.is_error is True`. Never apply error classification to regular text chunks or successful result messages.
**Warning signs:** Unexpected retries during normal conversation.

### Pitfall 3: Retry Amplification with Claude Code's Built-in Retries
**What goes wrong:** Claude Code CLI already retries 429/529 errors internally (up to 10 times). If our wrapper also retries, a single rate limit event can cause up to 10 * 3 = 30 API attempts.
**Why it happens:** Both Claude Code and our wrapper implement retry logic independently.
**How to avoid:** Keep our retry count low (MAX_RETRIES=3) and use longer base delays (1-2 seconds). Our retries are a safety net for when Claude Code's internal retries are exhausted. The NDJSON error result is only emitted AFTER Claude Code has already exhausted its own retries.
**Warning signs:** Excessive API calls during overload conditions.

### Pitfall 4: Losing Partial Response on Retry
**What goes wrong:** Claude streams 500 characters of response, then hits a rate limit error. The retry restarts the entire request, and the user sees the first 500 characters duplicated.
**Why it happens:** Each `stream_claude_response()` call is a new subprocess invocation. On retry, Claude regenerates the entire response.
**How to avoid:** On retry, clear the current response from the log (or add a visual separator) and start fresh. Alternatively, only retry if no text chunks were yielded before the error (i.e., the error occurred during the thinking/startup phase).
**Warning signs:** Duplicated text in the TUI output.

### Pitfall 5: Subprocess Timeout Killing Legitimate Long Operations
**What goes wrong:** Claude Code is running a legitimate Bash command that takes 4+ minutes. The 300-second readline timeout fires and kills the process.
**Why it happens:** During tool use, Claude Code may not emit any NDJSON events to stdout while the tool is executing.
**How to avoid:** Use a generous timeout (300 seconds = 5 minutes). Claude Code's own tool timeout is typically 120 seconds for most operations. If needed, the timeout could be made configurable, but 300 seconds is a safe default that catches the hang bug without interrupting normal use.
**Warning signs:** Interrupted responses during long tool operations.

## Code Examples

Verified patterns from official sources:

### Check CLI Availability with shutil.which
```python
# Source: Python stdlib docs (https://docs.python.org/3/library/shutil.html#shutil.which)
import shutil

def check_claude_installed() -> bool:
    """Check if the Claude Code CLI is available in PATH."""
    return shutil.which("claude") is not None
```

### Asyncio Subprocess Read with Timeout
```python
# Source: Python asyncio docs (https://docs.python.org/3/library/asyncio-task.html#asyncio.wait_for)
import asyncio

async def read_line_with_timeout(
    stdout: asyncio.StreamReader,
    timeout: float = 300.0,
) -> bytes | None:
    """Read a line from subprocess stdout with timeout.

    Returns the line bytes, empty bytes on EOF, or None on timeout.
    """
    try:
        line = await asyncio.wait_for(stdout.readline(), timeout=timeout)
        return line
    except asyncio.TimeoutError:
        return None
```

### Exponential Backoff with Jitter (stdlib only)
```python
# Source: Standard exponential backoff pattern
# No external dependencies needed for 3 retries
import asyncio
import random

async def retry_with_backoff(
    coro_factory,
    max_retries: int = 3,
    base_delay: float = 1.0,
):
    """Retry a coroutine with exponential backoff and jitter."""
    for attempt in range(max_retries + 1):
        try:
            return await coro_factory()
        except RetryableError:
            if attempt == max_retries:
                raise
            delay = base_delay * (2 ** attempt) + random.uniform(0, 1)
            await asyncio.sleep(delay)
```

### Claude Code Install URL
```python
# Source: Claude Code official docs (https://code.claude.com/docs/en/troubleshooting)
CLAUDE_INSTALL_URL = "https://claude.ai/install.sh"
CLAUDE_DOCS_URL = "https://code.claude.com/docs/en/quickstart"

INSTALL_MESSAGE = (
    "Claude Code CLI is not installed.\n\n"
    "Install with:\n"
    f"  curl -fsSL {CLAUDE_INSTALL_URL} | bash\n\n"
    f"Or visit: {CLAUDE_DOCS_URL}"
)
```

## State of the Art

| Old Approach (Phase 5) | Current Approach (Phase 6) | When Changed | Impact |
|------------------------|---------------------------|--------------|--------|
| Raw `FileNotFoundError` if claude not installed | Pre-flight `shutil.which` check with install URL | Phase 6 | Users see actionable message, not stack trace |
| Raw `Exception` in TUI catch-all | Classified errors with user-friendly messages | Phase 6 | Each error type gets specific guidance |
| No readline timeout (can hang forever) | `asyncio.wait_for(readline(), timeout=300)` | Phase 6 | Protects against known stream-json hang bug |
| No retry on transient errors | Exponential backoff retry for rate limit/overloaded | Phase 6 | Automatic recovery from transient API issues |
| Generic "Session expired" message on resume failure | Classified error message with specific recovery guidance | Phase 6 | User understands what happened and what to do |
| Kill-with-timeout only on cancel | Kill-with-timeout on all error paths (timeout, error, cancel) | Phase 6 | Complete subprocess cleanup coverage |

**Deprecated/outdated:**
- Generic `except Exception as exc: log.write_line(f"\n[Error: {exc}]")` in TUI: replaced by classified error handling

## Existing Implementation Analysis

### Already Implemented (from Phase 5)
1. **Kill-with-timeout (ERR-04 partial):** `_kill_process()` in tui.py with SIGTERM -> wait 5s -> SIGKILL. Called on cancel, unmount.
2. **Resume failure fallback (ERR-06 partial):** Lines 244-249 in tui.py reset `session_id` to None on `is_error` during resume.
3. **StreamResult error fields:** `is_error`, `error_message` fields on StreamResult dataclass in bridge.py.
4. **Subprocess stderr capture:** `stderr=asyncio.subprocess.PIPE` in bridge.py line 197.

### Not Yet Implemented (Phase 6 scope)
1. **CLI availability check (ERR-01):** No `shutil.which` check anywhere in codebase.
2. **Error classification (ERR-02):** No error categorization. TUI has generic `except Exception` catch-all.
3. **Subprocess read timeout (ERR-03):** No timeout on `readline()` -- can hang indefinitely.
4. **Kill-with-timeout coverage (ERR-04):** Missing on timeout and bridge-level error paths.
5. **Retry with backoff (ERR-05):** No retry logic anywhere in codebase.
6. **Enhanced session recovery messages (ERR-06):** Only generic "Session expired or corrupted" message.

## Open Questions

1. **Should retry logic apply in --no-tui mode?**
   - What we know: The `_chat_async` function in cli.py is the non-TUI code path. It currently has no retry logic.
   - What's unclear: Whether the retry UX (showing retry messages in stdout) is appropriate for piped/scripted use.
   - Recommendation: Implement retry in TUI first. --no-tui mode can be added later if needed. Non-TUI mode is less interactive and users may prefer to handle retries themselves in scripts.

2. **Optimal readline timeout value**
   - What we know: Claude Code's own tool timeouts are ~120s. The stream-json hang bug can last 5+ minutes. Long tool operations (e.g., running a test suite) can exceed 2 minutes.
   - What's unclear: Whether 300 seconds is the right balance. Too low = false positives on legitimate operations. Too high = long wait on hang bug.
   - Recommendation: Start with 300 seconds (5 minutes). Make it a module-level constant for easy tuning. Consider a shorter timeout (30 seconds) AFTER the result message has been received.

3. **Should we read and log stderr from Claude Code subprocess?**
   - What we know: stderr is captured (`stderr=asyncio.subprocess.PIPE`) but never read. Claude Code writes progress info, error details, and retry messages to stderr.
   - What's unclear: Whether reading stderr would provide better error classification. Risk: reading stderr while reading stdout requires careful concurrency handling to avoid deadlocks.
   - Recommendation: For Phase 6, continue to rely on the NDJSON `result` message for error information. Reading stderr can be added in a later phase if error classification proves insufficient. The `proc.stderr.read()` could be called after `proc.wait()` to grab stderr for logging without deadlock risk.

## Sources

### Primary (HIGH confidence)
- Python shutil.which docs: https://docs.python.org/3/library/shutil.html#shutil.which -- cross-platform CLI detection
- Python asyncio subprocess docs: https://docs.python.org/3/library/asyncio-subprocess.html -- create_subprocess_exec, wait, terminate, kill
- Python asyncio.wait_for docs: https://docs.python.org/3/library/asyncio-task.html#asyncio.wait_for -- timeout wrapper for awaitables
- Claude Code CLI Reference: https://code.claude.com/docs/en/cli-reference -- flags including --fallback-model, --resume
- Claude Code Troubleshooting: https://code.claude.com/docs/en/troubleshooting -- installation, auth issues, common errors
- Claude API Errors: https://platform.claude.com/docs/en/api/errors -- HTTP error codes (429 rate_limit, 529 overloaded, 401 auth, 400 invalid_request)
- Claude Code Install Guide: https://code.claude.com/docs/en/troubleshooting -- native installer: `curl -fsSL https://claude.ai/install.sh | bash`

### Secondary (MEDIUM confidence)
- Claude Code stream-json hang bug (issue #25629): https://github.com/anthropics/claude-code/issues/25629 -- CLI hangs after result event, requires process kill. Reported Feb 2026, still open.
- Claude Code resume crash (issue #18880): https://github.com/anthropics/claude-code/issues/18880 -- "No messages returned" error after killed subprocess corrupts session
- Claude Code overloaded errors (issue #3542): https://github.com/anthropics/claude-code/issues/3542 -- 529 overloaded_error with retry pattern "Retrying in N seconds (attempt M/10)"
- Claude Agent SDK spec (gist): https://gist.github.com/POWERFULMOVES/58bcadab9483bf5e633e865f131e6c25 -- NDJSON result message format with is_error, subtype, errors array
- Claude Code 529 errors article: https://medium.com/@joe.njenga/claude-code-529-overloaded-error-is-messing-up-workflows-heres-what-to-do-6934ee8a3e71 -- overloaded error patterns

### Tertiary (LOW confidence)
- None -- all findings verified with primary or secondary sources.

## Metadata

**Confidence breakdown:**
- Standard stack: HIGH -- zero new dependencies, all patterns from Python stdlib docs
- Architecture: HIGH -- surgical additions to existing bridge.py, tui.py, cli.py. No architectural rewrites. Error classification is a pure function, easily testable.
- Pitfalls: HIGH -- stream-json hang bug verified from GitHub issue with multiple reporters. Retry amplification logic verified from Claude Code's documented internal retry behavior. Error classification patterns from GitHub issues.
- Error patterns: MEDIUM -- the specific error message strings from Claude Code are not formally documented. Derived from GitHub issues and observed behavior. May need updating as Claude Code evolves.

**Research date:** 2026-02-16
**Valid until:** 2026-03-16 (30 days -- stable domain, error patterns may shift with Claude Code updates)
