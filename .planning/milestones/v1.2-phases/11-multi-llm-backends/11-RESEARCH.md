# Phase 11: Multi-LLM Backends - Research

**Researched:** 2026-02-17
**Domain:** LLM API integration, async streaming, backend abstraction
**Confidence:** HIGH

## Summary

Phase 11 adds OpenAI and OpenRouter as alternative LLM backends alongside the existing Claude Code CLI subprocess. Both OpenAI and OpenRouter use the same `openai` Python SDK (v2.21.0) -- OpenRouter is just the OpenAI SDK pointed at a different `base_url`. The core challenge is producing an async character stream from each backend that feeds into the existing teletype pipeline (pacer, output multiplexer, word wrap, printer, audio, transcript) identically, so the typewriter experience is backend-agnostic.

The existing `bridge.py` module currently owns the entire streaming lifecycle: spawning a subprocess, parsing NDJSON, yielding `str | StreamResult`. The new architecture needs a backend abstraction that replaces `stream_claude_response()` calls in `cli.py` and `tui.py` with a backend-polymorphic equivalent. The `openai` SDK provides `AsyncOpenAI` with `chat.completions.create(stream=True)` returning an async iterator of `ChatCompletionChunk` objects, which must be adapted to yield plain `str` text chunks and a final `StreamResult`.

**Primary recommendation:** Create an `AsyncIterator[str | StreamResult]` protocol/ABC for all backends. The Claude Code CLI backend wraps existing `stream_claude_response()`. The OpenAI/OpenRouter backend uses `AsyncOpenAI.chat.completions.create(stream=True)` with conversation history managed in-memory. Config and CLI flags (`--backend`, `--model`) select the backend at startup, locked for the session.

<user_constraints>
## User Constraints (from CONTEXT.md)

### Locked Decisions
- Default backend is config-driven (TOML config sets the default, Claude Code CLI is factory default)
- Backend is locked at startup -- no mid-session switching
- `--backend` flag overrides config for a single run
- Model selection: `--model` flag overrides config, config sets default model per backend, each backend has a hardcoded fallback default
- OpenRouter is a single backend -- user specifies model names like `anthropic/claude-3.5-sonnet` directly
- All backends produce the same stream format feeding into the existing character pipeline
- Output should feel consistent regardless of backend -- the typewriter effect is the product's identity
- Users can set a system prompt via TOML config for OpenAI/OpenRouter backends
- Claude Code CLI manages its own system prompt (not configurable through teletype)
- Full message history sent with every request for OpenAI/OpenRouter backends
- No turn limit -- send everything (may hit context limits on very long conversations, but keep it simple for v1)
- Claude Code CLI continues to manage its own conversation state via subprocess
- OpenAI and OpenRouter both use the `openai` Python SDK -- OpenRouter is just a different base URL
- Claude Code CLI streams via subprocess (existing behavior), the other backends use SDK streaming
- All backends must converge into the same async character stream that the teletype pipeline already consumes

### Claude's Discretion
- Streaming pacing strategy (whether to buffer and normalize speed across backends or let natural speed through)
- Internal architecture for backend abstraction
- Error handling approach (startup validation, runtime error display)
- Default model choices per backend
- Context window overflow handling (if/when full history exceeds limits)

### Deferred Ideas (OUT OF SCOPE)
None -- discussion stayed within phase scope
</user_constraints>

<phase_requirements>
## Phase Requirements

| ID | Description | Research Support |
|----|-------------|-----------------|
| LLM-01 | User can switch between LLM backends (Claude Code CLI, OpenAI, OpenRouter) via config or CLI flag | Config `[llm]` section with `backend` field + `--backend` CLI flag; backend factory pattern selects implementation at startup |
| LLM-02 | User can chat with OpenAI or OpenRouter models via direct API using the `openai` library | `openai` SDK v2.21.0 with `AsyncOpenAI` client; `chat.completions.create(stream=True)` for streaming; OpenRouter uses same SDK with `base_url="https://openrouter.ai/api/v1"` |
| LLM-03 | User can select a specific model within a backend via `--model` flag or config default | Config `[llm]` section with per-backend `model` field + `--model` CLI flag override; hardcoded fallback defaults per backend |
| LLM-04 | User gets a clear error message on startup if the selected backend is unreachable or misconfigured | Startup validation: check API key env var exists, optionally test connection with a lightweight API call; map `openai.AuthenticationError`, `APIConnectionError` to user-friendly messages |
</phase_requirements>

## Standard Stack

### Core
| Library | Version | Purpose | Why Standard |
|---------|---------|---------|--------------|
| `openai` | >=2.21.0 | OpenAI and OpenRouter API client | Official SDK; used by both OpenAI and OpenRouter; `AsyncOpenAI` with streaming; Pydantic-typed responses |

### Supporting
| Library | Version | Purpose | When to Use |
|---------|---------|---------|-------------|
| `httpx` | (transitive) | HTTP client underneath `openai` | Pulled in by `openai`; no direct import needed |

### Alternatives Considered
| Instead of | Could Use | Tradeoff |
|------------|-----------|----------|
| `openai` SDK | `litellm` | Explicitly out of scope per REQUIREMENTS.md -- 67MB+ dependency for what `openai` handles in ~2MB |
| `openai` SDK | Raw `httpx` SSE | More control but must manually parse SSE, handle reconnection, type responses -- `openai` SDK does all this |
| Per-backend module | Plugin system | Explicitly out of scope per REQUIREMENTS.md -- over-engineering for 3 backends |

**Installation:**
```bash
uv add "openai>=2.21.0"
```

## Architecture Patterns

### Recommended Project Structure
```
src/claude_teletype/
    backends/
        __init__.py          # Backend ABC/Protocol, factory function, registry
        claude_cli.py        # Claude Code CLI subprocess backend (wraps existing bridge.py)
        openai_backend.py    # OpenAI direct API backend
        openrouter.py        # OpenRouter backend (thin wrapper over openai_backend)
    bridge.py                # Unchanged -- StreamResult stays here, used by claude_cli backend
    config.py                # Extended with [llm] section
    cli.py                   # Extended with --backend and --model flags
    tui.py                   # Refactored to use backend abstraction instead of bridge directly
```

### Pattern 1: Backend Protocol with AsyncIterator
**What:** An abstract base class or Protocol defining the streaming interface that all backends implement.
**When to use:** Always -- this is the core abstraction.
**Recommendation:** Use ABC over Protocol here. The backends share enough structure (startup validation, streaming, cleanup) that an ABC with abstract methods is clearer than a structural Protocol. The existing `PrinterDriver` uses Protocol because implementations are structurally diverse; here, backends are structurally similar.

```python
from abc import ABC, abstractmethod
from collections.abc import AsyncIterator
from claude_teletype.bridge import StreamResult

class LLMBackend(ABC):
    """Abstract base for all LLM streaming backends."""

    @abstractmethod
    async def stream(
        self, prompt: str
    ) -> AsyncIterator[str | StreamResult]:
        """Stream a response, yielding text chunks and a final StreamResult."""
        ...

    @abstractmethod
    def validate(self) -> None:
        """Check configuration at startup. Raise BackendError if misconfigured."""
        ...

    @abstractmethod
    def add_to_history(self, role: str, content: str) -> None:
        """Record a message in conversation history (no-op for Claude CLI)."""
        ...
```

### Pattern 2: Backend Factory
**What:** A factory function that creates the correct backend based on config + CLI flags.
**When to use:** At startup, once, before entering the event loop.

```python
def create_backend(config: TeletypeConfig) -> LLMBackend:
    """Create LLM backend from resolved config. Raises BackendError on failure."""
    backend_name = config.backend  # "claude-cli" | "openai" | "openrouter"
    if backend_name == "claude-cli":
        return ClaudeCliBackend(session_id=config.resume_session_id)
    elif backend_name == "openai":
        return OpenAIBackend(
            api_key=os.environ.get("OPENAI_API_KEY"),
            model=config.model or "gpt-4o",
            system_prompt=config.system_prompt,
        )
    elif backend_name == "openrouter":
        return OpenRouterBackend(
            api_key=os.environ.get("OPENROUTER_API_KEY"),
            model=config.model or "openai/gpt-4o",
            system_prompt=config.system_prompt,
        )
    else:
        raise BackendError(f"Unknown backend: {backend_name!r}")
```

### Pattern 3: OpenAI/OpenRouter Streaming Adapter
**What:** Adapts `AsyncOpenAI.chat.completions.create(stream=True)` chunks to `str | StreamResult`.
**When to use:** For OpenAI and OpenRouter backends.

```python
from openai import AsyncOpenAI

class OpenAIBackend(LLMBackend):
    def __init__(self, api_key: str | None, model: str, system_prompt: str | None = None,
                 base_url: str | None = None):
        self._client = AsyncOpenAI(api_key=api_key, base_url=base_url)
        self._model = model
        self._system_prompt = system_prompt
        self._history: list[dict[str, str]] = []

    def validate(self) -> None:
        if not self._client.api_key:
            raise BackendError("OPENAI_API_KEY environment variable not set")

    def add_to_history(self, role: str, content: str) -> None:
        self._history.append({"role": role, "content": content})

    async def stream(self, prompt: str) -> AsyncIterator[str | StreamResult]:
        self.add_to_history("user", prompt)
        messages = self._build_messages()
        assistant_content = []

        try:
            response = await self._client.chat.completions.create(
                model=self._model,
                messages=messages,
                stream=True,
            )
            async for chunk in response:
                delta = chunk.choices[0].delta if chunk.choices else None
                if delta and delta.content:
                    assistant_content.append(delta.content)
                    yield delta.content

            # Record assistant response in history
            full_response = "".join(assistant_content)
            self.add_to_history("assistant", full_response)

            yield StreamResult(
                model=self._model,
                is_error=False,
            )

        except openai.AuthenticationError as e:
            yield StreamResult(is_error=True, error_message=f"Authentication failed: {e}")
        except openai.RateLimitError as e:
            yield StreamResult(is_error=True, error_message=f"Rate limit: {e}")
        except openai.APIConnectionError as e:
            yield StreamResult(is_error=True, error_message=f"Connection error: {e}")
        except openai.APIError as e:
            yield StreamResult(is_error=True, error_message=str(e))

    def _build_messages(self) -> list[dict[str, str]]:
        messages = []
        if self._system_prompt:
            messages.append({"role": "system", "content": self._system_prompt})
        messages.extend(self._history)
        return messages
```

### Pattern 4: OpenRouter as Thin Wrapper
**What:** OpenRouter backend is an `OpenAIBackend` with different `base_url` and API key env var.
**When to use:** For the OpenRouter backend -- avoids code duplication.

```python
class OpenRouterBackend(OpenAIBackend):
    def __init__(self, api_key: str | None, model: str, system_prompt: str | None = None):
        super().__init__(
            api_key=api_key,
            model=model,
            system_prompt=system_prompt,
            base_url="https://openrouter.ai/api/v1",
        )

    def validate(self) -> None:
        if not self._client.api_key:
            raise BackendError("OPENROUTER_API_KEY environment variable not set")
```

### Pattern 5: Conversation History Management
**What:** In-memory message list for OpenAI/OpenRouter backends, replayed on each request.
**When to use:** For multi-turn conversations with API backends.

The history is a simple `list[dict[str, str]]` with `{"role": "user"|"assistant"|"system", "content": "..."}` entries. Each request sends the full history. The Claude CLI backend does not use this -- it manages its own state via `--resume` session ID.

### Anti-Patterns to Avoid
- **Mid-session backend switching:** The user decided backend is locked at startup. Do not build infrastructure for changing backends after the event loop starts.
- **Shared conversation history across backends:** Each backend manages its own history format. Claude CLI uses session IDs; API backends use message lists. Never try to convert between them.
- **Custom SSE parsing:** The `openai` SDK handles SSE parsing internally. Never parse raw HTTP responses or SSE events manually.
- **Blocking API calls in the event loop:** Always use `AsyncOpenAI`, never synchronous `OpenAI` client. The entire app is async.
- **LiteLLM or plugin systems:** Explicitly out of scope per REQUIREMENTS.md.

## Don't Hand-Roll

| Problem | Don't Build | Use Instead | Why |
|---------|-------------|-------------|-----|
| SSE streaming | Custom SSE parser | `openai` SDK `stream=True` | SSE parsing has edge cases (reconnection, comments, multi-line data); SDK handles all of it |
| HTTP client | Raw `httpx` or `aiohttp` | `openai` SDK wraps `httpx` | Handles auth headers, retries (2x default), timeouts (10min default), error mapping |
| Error classification | Custom HTTP status parsing | `openai` exception hierarchy | SDK raises typed exceptions: `AuthenticationError`, `RateLimitError`, `APIConnectionError`, `InternalServerError` |
| Retry logic for API calls | Custom exponential backoff | `openai` SDK built-in retries | SDK retries connection errors, 408, 409, 429, >=500 automatically (2x default) |
| OpenRouter client | Separate HTTP client | `openai` SDK with `base_url` | OpenRouter is API-compatible with OpenAI; just change `base_url` |

**Key insight:** The `openai` SDK does the heavy lifting. The implementation work is mostly in the abstraction layer between `openai` SDK output and the existing teletype pipeline, plus config/CLI wiring.

## Common Pitfalls

### Pitfall 1: Streaming Chunk with None Content
**What goes wrong:** `chunk.choices[0].delta.content` can be `None` on the first chunk (which only has `role`) or on the final chunk (which only has `finish_reason`). Accessing `.content` without a None check crashes the stream.
**Why it happens:** OpenAI streaming sends a role-only delta first, then content deltas, then a finish_reason-only delta.
**How to avoid:** Always check `if delta and delta.content:` before yielding.
**Warning signs:** `AttributeError` or empty string yields during streaming.

### Pitfall 2: Empty Choices Array
**What goes wrong:** Some streaming chunks have an empty `choices` list (e.g., usage-only final chunks when `stream_options={"include_usage": True}`).
**Why it happens:** The final usage chunk has no choices.
**How to avoid:** Check `if chunk.choices:` before accessing `chunk.choices[0]`.
**Warning signs:** `IndexError: list index out of range` during streaming.

### Pitfall 3: OpenRouter SSE Comments
**What goes wrong:** OpenRouter sends `": OPENROUTER PROCESSING"` comment lines during long processing to prevent timeout. If parsed as data, they corrupt the stream.
**Why it happens:** SSE spec allows comment lines (starting with `:`) as keepalives.
**How to avoid:** The `openai` SDK handles this transparently. Do not parse raw SSE yourself.
**Warning signs:** Only a problem if you bypass the SDK.

### Pitfall 4: API Key Not Set vs. Invalid Key
**What goes wrong:** Confusing "no API key" (should error at startup) with "invalid API key" (errors at first API call). Users get confusing errors.
**Why it happens:** The `openai` SDK accepts construction without a key and only fails on the first request.
**How to avoid:** Validate API key presence in the `validate()` method at startup, before any streaming begins. Check `os.environ.get("OPENAI_API_KEY")` is truthy.
**Warning signs:** User sees "AuthenticationError" mid-conversation instead of a clear startup error.

### Pitfall 5: Forgetting to Record History
**What goes wrong:** Assistant response is not added to conversation history, so the next turn lacks context.
**Why it happens:** The response is streamed in chunks. Developer forgets to accumulate chunks and record the final response.
**How to avoid:** Accumulate `delta.content` chunks into a list during streaming, then join and add to history after stream completes.
**Warning signs:** Second turn of conversation has no context from the first turn.

### Pitfall 6: Context Window Overflow
**What goes wrong:** After many turns, full conversation history exceeds the model's context window limit.
**Why it happens:** User decided "no turn limit -- send everything."
**How to avoid:** For v1, let the API return an error and surface it to the user. The error classification system (errors.py) already has `CONTEXT_EXHAUSTED` category. A simple approach: catch the API error, classify it, display "Context window exhausted. Start a new conversation."
**Warning signs:** 400 error from API mentioning "context length" or "max tokens".

### Pitfall 7: Inconsistent StreamResult Between Backends
**What goes wrong:** Claude CLI backend produces rich StreamResult (session_id, cost, usage, model_usage), while API backends produce minimal ones. Status bar or downstream code crashes on missing fields.
**Why it happens:** Different backends have different metadata available.
**How to avoid:** StreamResult already uses `None` defaults for optional fields. Ensure all consumers handle `None` gracefully (they already do -- `calc_context_pct(None)` returns "--", `extract_model_name(None)` returns `None`).
**Warning signs:** None -- existing code already handles this correctly.

## Code Examples

Verified patterns from official sources:

### AsyncOpenAI Streaming Chat Completion
```python
# Source: https://github.com/openai/openai-python README
import asyncio
from openai import AsyncOpenAI

client = AsyncOpenAI()  # Uses OPENAI_API_KEY env var

async def stream_chat():
    response = await client.chat.completions.create(
        model="gpt-4o",
        messages=[{"role": "user", "content": "Hello!"}],
        stream=True,
    )
    async for chunk in response:
        if chunk.choices and chunk.choices[0].delta.content:
            print(chunk.choices[0].delta.content, end="")

asyncio.run(stream_chat())
```

### OpenRouter with OpenAI SDK
```python
# Source: https://openrouter.ai/docs/guides/community/openai-sdk
from openai import AsyncOpenAI

client = AsyncOpenAI(
    base_url="https://openrouter.ai/api/v1",
    api_key=os.environ.get("OPENROUTER_API_KEY"),
)

# Usage is identical to OpenAI:
response = await client.chat.completions.create(
    model="anthropic/claude-3.5-sonnet",
    messages=[{"role": "user", "content": "Hello!"}],
    stream=True,
)
```

### OpenAI Error Handling
```python
# Source: https://mmacy.github.io/openai-python/1.14.3/error-handling/
import openai

try:
    response = await client.chat.completions.create(...)
except openai.AuthenticationError as e:
    # 401 -- invalid/expired API key
    ...
except openai.RateLimitError as e:
    # 429 -- rate limit exceeded (auto-retried 2x by SDK)
    ...
except openai.APIConnectionError as e:
    # Network unreachable
    ...
except openai.InternalServerError as e:
    # 500+ -- server error (auto-retried 2x by SDK)
    ...
except openai.APIError as e:
    # Catch-all for other API errors
    ...
```

### Multi-Turn Conversation History
```python
# Source: https://deepwiki.com/openai/openai-python/4.1-chat-completions-api
messages = [
    {"role": "system", "content": "You are a helpful assistant."},
    {"role": "user", "content": "What is Python?"},
    {"role": "assistant", "content": "Python is a programming language..."},
    {"role": "user", "content": "What are its main features?"},
]

response = await client.chat.completions.create(
    model="gpt-4o",
    messages=messages,
    stream=True,
)
```

### Config Extension for LLM Settings
```toml
# New [llm] section in config.toml
[llm]
# Backend: "claude-cli", "openai", "openrouter"
backend = "claude-cli"

# Default model per backend (overridden by --model flag)
# claude-cli: not configurable (managed by Claude Code)
# openai: "gpt-4o" (fallback default)
# openrouter: "openai/gpt-4o" (fallback default)
model = ""

# System prompt for OpenAI/OpenRouter backends
# Claude Code CLI manages its own system prompt
system_prompt = ""
```

## Discretion Recommendations

### Streaming Pacing Strategy
**Recommendation:** Let natural speed through, do not buffer or normalize.
**Rationale:** The pacer already controls character-by-character output speed via `pace_characters()`. The backend stream speed only affects how fast chunks arrive to the pacer. If chunks arrive faster than the pacer can consume them, they queue naturally in the async generator. If chunks arrive slower, the pacer simply waits. The typewriter effect is already governed by `base_delay_ms`, which is backend-agnostic. No additional buffering layer is needed.

### Internal Architecture for Backend Abstraction
**Recommendation:** ABC-based `LLMBackend` in a `backends/` subpackage, with a factory function.
**Rationale:** The three backends share enough interface (validate, stream, history management) to benefit from an ABC. A `backends/` subpackage keeps the code organized without over-engineering. The factory function is called once at startup and returns the backend used for the entire session. No plugin registry, no dynamic loading.

### Error Handling Approach
**Recommendation:** Two-stage validation. (1) Startup: validate API key presence and backend name. Fail fast with clear error before entering the event loop. (2) Runtime: map `openai` SDK exceptions to the existing `ErrorCategory` enum in `errors.py`, then let the existing retry/display logic handle them.
**Rationale:** The existing error classification and retry system (`errors.py`, `tui.py` retry loop) already handles rate limits, auth errors, overloaded, network errors, and context exhaustion. The `openai` SDK exceptions map cleanly to these categories. Adding new patterns for the SDK exceptions to `ERROR_PATTERNS` in `errors.py` or catching them directly in the backend and yielding classified `StreamResult` errors both work. Recommendation: catch SDK exceptions in the backend, yield `StreamResult(is_error=True, error_message=...)` with messages that match existing `ERROR_PATTERNS` substrings so the TUI retry logic works unchanged.

### Default Model Choices Per Backend
**Recommendation:**
- Claude CLI: Not applicable (Claude Code manages model selection)
- OpenAI: `gpt-4o` as hardcoded fallback. Despite deprecation from ChatGPT, `gpt-4o` remains available in the API and is widely known. Users who want newer models can set `--model gpt-4o-mini` or `--model gpt-5.2`.
- OpenRouter: `openai/gpt-4o` as hardcoded fallback. Follows the `provider/model` naming convention.

**Confidence:** MEDIUM -- Model availability changes frequently. The fallback default should be a well-known, stable model name. `gpt-4o` is a safe choice for now since it is still available in the API even though it was retired from ChatGPT. If the model is deprecated from the API before implementation, switch to `gpt-4o-mini` or the then-current recommended model.

### Context Window Overflow Handling
**Recommendation:** Do nothing special. When the API returns a context length error, the existing error classification will catch it (patterns `"context window"`, `"context length"`, and `"max" + "token"` are already in `ERROR_PATTERNS`). The TUI will display "Context window exhausted. Start a new conversation." This is consistent with the user's decision to keep it simple for v1.

## State of the Art

| Old Approach | Current Approach | When Changed | Impact |
|--------------|------------------|--------------|--------|
| `openai.ChatCompletion.create()` (v0.x) | `client.chat.completions.create()` (v1.x+) | Nov 2023 (v1.0) | Must use new client-based API; old functional API removed |
| No built-in async | `AsyncOpenAI()` built-in | Nov 2023 (v1.0) | Native async support; no need for `asyncio.to_thread` wrappers |
| Manual retry logic | SDK auto-retries 2x (429, 500+) | v1.0+ | Less custom retry code needed; configurable via `max_retries` |
| GPT-4o as default ChatGPT model | GPT-5.2 in ChatGPT; GPT-4o still in API | Feb 2026 | GPT-4o still works for API users but may be deprecated later |
| `chat.completions.create(stream=True)` | Also: `chat.completions.stream()` helper | Recent (v1.40+) | Helper provides typed events, auto-accumulation; but `stream=True` is simpler and sufficient |

**Deprecated/outdated:**
- `openai.ChatCompletion.create()`: Removed in v1.0. Must use `client.chat.completions.create()`.
- `openai.error.RateLimitError`: Now `openai.RateLimitError` (top-level import).

## Open Questions

1. **SDK auto-retry vs. our retry loop**
   - What we know: The `openai` SDK retries 429 and 500+ errors 2 times automatically with exponential backoff. The TUI already has its own retry loop (3 retries with backoff) for Claude CLI errors.
   - What's unclear: Whether having both retry layers (SDK + TUI) causes too many total retries.
   - Recommendation: Set `max_retries=0` on the `AsyncOpenAI` client to disable SDK-level retries, letting the TUI retry loop handle everything consistently across all backends. This gives consistent retry behavior and messaging.

2. **Usage/cost data from OpenAI streaming**
   - What we know: OpenAI streaming can include usage stats in the final chunk via `stream_options={"include_usage": True}`. OpenRouter includes usage in the final chunk by default.
   - What's unclear: Whether `stream_options` is supported by OpenRouter, and the exact structure of usage data in streaming mode.
   - Recommendation: Include `stream_options={"include_usage": True}` for OpenAI, and extract usage from the final chunk to populate `StreamResult.usage`. For OpenRouter, test whether it respects this parameter or provides usage differently. The status bar already handles `None` usage gracefully.

3. **`check_claude_installed()` gating**
   - What we know: `cli.py` calls `check_claude_installed()` which exits if `claude` CLI is not on PATH. This must be skipped for non-Claude backends.
   - What's unclear: Nothing -- this is a straightforward fix.
   - Recommendation: Move the check inside the Claude CLI backend's `validate()` method, or guard it with `if config.backend == "claude-cli"`.

## Sources

### Primary (HIGH confidence)
- OpenAI Python SDK README: https://github.com/openai/openai-python -- async streaming examples, client configuration, base_url support
- OpenAI Python SDK helpers.md: https://github.com/openai/openai-python/blob/main/helpers.md -- stream helper API, event types
- OpenRouter OpenAI SDK guide: https://openrouter.ai/docs/guides/community/openai-sdk -- base_url, API key, model format
- OpenRouter streaming docs: https://openrouter.ai/docs/api/reference/streaming -- SSE format, usage in final chunk, error handling

### Secondary (MEDIUM confidence)
- OpenAI error handling reference: https://mmacy.github.io/openai-python/1.14.3/error-handling/ -- exception hierarchy, auto-retry behavior, status codes
- DeepWiki chat completions: https://deepwiki.com/openai/openai-python/4.1-chat-completions-api -- async streaming pattern, message format, delta structure
- OpenAI PyPI: https://pypi.org/project/openai/ -- v2.21.0 current, Python >=3.9
- OpenAI model deprecations: https://platform.openai.com/docs/deprecations -- GPT-4o still in API despite ChatGPT retirement

### Tertiary (LOW confidence)
- OpenRouter rankings: https://openrouter.ai/rankings -- popular model names (changes frequently)

## Metadata

**Confidence breakdown:**
- Standard stack: HIGH -- `openai` SDK is the only library needed; well-documented, verified via multiple sources
- Architecture: HIGH -- Backend abstraction pattern is straightforward; existing codebase integration points clearly identified in `bridge.py`, `cli.py`, `tui.py`
- Pitfalls: HIGH -- Streaming chunk structure, None checks, history management all verified with official SDK examples
- Default models: MEDIUM -- Model names change; `gpt-4o` is available now but may be deprecated from API later

**Research date:** 2026-02-17
**Valid until:** 2026-03-17 (30 days -- `openai` SDK is stable; model names may change sooner)
