# Domain Pitfalls: v1.2 Configuration, Printer Profiles, Multi-LLM, Settings UI, Typewriter Mode

**Domain:** Adding configuration system, printer profiles with per-printer control codes, multi-LLM backends (OpenAI + OpenRouter), TUI settings page, and typewriter mode to an existing Python terminal application
**Researched:** 2026-02-17
**Confidence:** HIGH (verified with official API docs for OpenAI/Anthropic/OpenRouter, Textual docs, Python stdlib docs, printer protocol references)

---

## Critical Pitfalls

Mistakes that cause rewrites, security vulnerabilities, or major breakage.

### Pitfall 1: Storing API Keys in the Config File Alongside Non-Secret Settings

**What goes wrong:**
The developer creates a single `config.toml` file that stores everything -- delays, printer preferences, AND API keys for OpenAI/OpenRouter. The file gets committed to git. Or the user shares their config with someone for debugging. Or a crash dump includes the config contents. The API keys are now leaked. Even if the file is excluded from git, it sits on disk in plaintext, readable by any process running as the same user.

**Why it happens:**
It is the simplest implementation. One file, one load function, one save function. The developer intends to add `.gitignore` entries and "handle it later." But the config file is a natural thing to share ("here's my setup") and plaintext files are trivially exfiltrated by malware or shoulder-surfing.

**Consequences:**
- API keys leaked to git history (even if removed later, they are in reflog forever)
- API keys exposed when user shares config for support/debugging
- Third-party processes on same machine can read the keys
- OpenAI/OpenRouter keys have billing implications -- a leaked key generates charges

**Prevention:**
1. **Separate secrets from config entirely.** Non-secret settings go in `config.toml`. API keys go in one of:
   - **Environment variables** (simplest, `OPENAI_API_KEY`, `OPENROUTER_API_KEY`) -- the existing convention both OpenAI and OpenRouter recommend
   - **A dedicated `.env` file** loaded via `python-dotenv` -- still plaintext but at least separate from shareable config and conventionally gitignored
   - **macOS Keychain via `keyring` library** -- encrypted at rest, requires user authentication
2. **The config file should only store a boolean** like `llm_provider = "openai"`, never the key itself.
3. **At load time, resolve keys from environment variables first**, then `.env` file, then keyring. Never write keys to `config.toml`.
4. **Mask keys in any logging or error output**: show only last 4 characters (`sk-...abcd`).

**Detection:**
- `grep -r "sk-" .` or `grep -r "api_key" config.toml` in the repo
- Check if `config.toml` contains any string starting with `sk-` or `or-`

**Confidence:** HIGH -- standard security practice, verified with [GitGuardian secrets management guide](https://blog.gitguardian.com/how-to-handle-secrets-in-python/) and [OpenAI API key documentation](https://platform.openai.com/docs/api-reference/authentication).

**Phase to address:** Config system phase (first). The secret/non-secret boundary must be established before any code reads API keys.

---

### Pitfall 2: Treating OpenAI SSE and Anthropic NDJSON (via Claude Code CLI) as the Same Stream Format

**What goes wrong:**
The developer creates a "unified streaming interface" that assumes all LLM backends produce the same stream format. The current bridge.py parses NDJSON lines from Claude Code CLI's `--output-format stream-json`. The developer assumes OpenAI's streaming is also NDJSON. It is not. OpenAI uses Server-Sent Events (SSE) with `data: {json}` prefixes and terminates with `data: [DONE]`. Anthropic's direct API also uses SSE but with different event types (`content_block_delta` vs OpenAI's `choices[0].delta.content`). The parser silently produces no output or crashes on `json.loads("data: {...}")`.

**Why it happens:**
Three different stream formats are in play and they look superficially similar:

| Backend | Format | Text Location | Stream End | Usage Location |
|---------|--------|---------------|------------|----------------|
| Claude Code CLI | NDJSON (one JSON per line) | `event.delta.text` in `content_block_delta` | EOF + `result` message | `result` message at end |
| OpenAI API | SSE (`data: {json}\n\n`) | `choices[0].delta.content` | `data: [DONE]` | Final chunk before `[DONE]` (if `stream_options.include_usage: true`) |
| Anthropic API | SSE (`event: type\ndata: {json}\n\n`) | `delta.text` in `content_block_delta` | `event: message_stop` | `message_delta` event with cumulative usage |
| OpenRouter API | SSE (OpenAI-compatible + comments) | `choices[0].delta.content` | `data: [DONE]` | Same as OpenAI but may include SSE comments like `: OPENROUTER PROCESSING` |

**Consequences:**
- Silent failure: parser finds no matching events, yields nothing, user sees empty response
- Crash on `json.loads()` when input includes `data: ` prefix or `event: ` lines
- `data: [DONE]` causes JSONDecodeError if not handled
- OpenRouter SSE comment lines (`: OPENROUTER PROCESSING`) cause parsing errors
- Usage/cost tracking breaks because token counts are reported differently

**Prevention:**
1. **Each backend gets its own stream parser module.** Do NOT try to normalize at the byte level. Instead:
   - `bridge.py` (existing) -- parses Claude Code CLI NDJSON, unchanged
   - `openai_bridge.py` (new) -- parses OpenAI SSE format
   - `openrouter_bridge.py` (new, or reuse openai_bridge) -- parses OpenAI-compatible SSE with comment filtering
2. **All parsers yield the same output type**: `AsyncIterator[str | StreamResult]`. The normalization happens at the output, not the input.
3. **OpenAI SSE parsing must:**
   - Skip blank lines (SSE delimiter)
   - Skip lines starting with `:` (SSE comments, used by OpenRouter for keepalive)
   - Strip `data: ` prefix before JSON parsing
   - Handle `data: [DONE]` as stream termination (not JSON)
   - Extract text from `choices[0].delta.content` (may be None on non-content chunks)
4. **Anthropic direct API SSE parsing must:**
   - Parse `event:` lines to determine event type
   - Handle `ping` events (skip them)
   - Handle `error` events mid-stream
   - Extract text from `content_block_delta` events with `text_delta` type
   - Detect `message_stop` for stream end
5. **Test with real API responses**, not mocked data. SSE edge cases (empty delta, `content: null`, tool_use blocks) are easy to miss.

**Detection:**
- Run all three backends and compare output for the same prompt
- Specifically test: empty response, very long response, response with code blocks, rate limit mid-stream

**Confidence:** HIGH -- verified from [Anthropic streaming docs](https://platform.claude.com/docs/en/api/messages-streaming), [OpenAI streaming reference](https://platform.openai.com/docs/api-reference/chat-streaming), [OpenRouter streaming docs](https://openrouter.ai/docs/api/reference/streaming), and [Simon Willison's SSE comparison](https://til.simonwillison.net/llms/streaming-llm-apis).

**Phase to address:** Multi-LLM phase. This is the core architectural decision for the provider abstraction.

---

### Pitfall 3: Switching LLM Provider Mid-Session Corrupts Conversation Context

**What goes wrong:**
The user opens settings mid-conversation, switches from Claude Code to OpenAI, and sends the next prompt. The app tries to continue the conversation but the context is gone -- Claude Code's session state (stored in `~/.claude/sessions/`) is meaningless to OpenAI, and the conversation history was never tracked in-process (because v1.1 deliberately delegated context management to Claude Code). The user gets a response with no context of the previous 10 turns.

**Why it happens:**
The v1.1 architecture made a deliberate and correct decision (see v1.1 PITFALLS.md, Pitfall 4): let Claude Code own session state via `--resume <session_id>`. This means the app stores NO conversation history in-process. When switching to a provider that does not have access to Claude Code's session storage, there is no history to send.

**Consequences:**
- Complete context loss on provider switch
- User confusion: "I just asked about X, why does it not remember?"
- If the app tries to reconstruct history from the transcript, it gets only the text (no system prompts, no tool results, no token counts)
- Switching back to Claude Code works (session_id is still valid), creating asymmetric behavior

**Prevention:**
1. **Do NOT allow provider switching mid-session.** When the user changes LLM provider in settings, start a new session. Display a clear message: "Switching provider starts a new conversation."
2. **Alternative (more complex, defer to later milestone):** Maintain a shadow conversation history in-process alongside Claude Code's session management. On provider switch, replay the history to the new provider. This is complex and was explicitly avoided in v1.1 for good reason.
3. **For v1.2, the simple approach is correct:** Provider is set at session start. Changing it requires a new session. The settings UI should make this clear with a warning before applying the change.
4. **Store the provider choice in StreamResult** so the status bar shows which provider is active. This prevents confusion about which backend is handling the current session.

**Detection:**
- Test: start session with Claude Code (5 turns), switch to OpenAI in settings, send prompt. Does the response have context?
- Test: switch from OpenAI to Claude Code. Does `--resume` work with a session_id from OpenAI? (It should not -- they are separate systems.)

**Confidence:** HIGH -- direct analysis of the v1.1 architecture decision in bridge.py and tui.py.

**Phase to address:** Settings UI phase, but the constraint must be documented in the multi-LLM phase architecture.

---

### Pitfall 4: Printer Control Code Bytes Interpreted as Text Characters

**What goes wrong:**
The developer stores printer control codes as strings in TOML config: `init_sequence = "\x1b\x1aI"`. When loaded by Python's `tomllib`, the string contains Unicode characters U+001B, U+001A, U+0049. The code calls `driver.write(init_sequence)` which encodes each character with `char.encode("ascii", errors="replace")`. This works for ASCII-range control characters. But the developer then tries to store multi-byte ESC/P2 parameters like `\x1b\x2a\x00\x80\x02` (graphics mode with a 640-byte parameter). The `\x80` is outside ASCII range. `errors="replace"` converts it to `?` (0x3F). The printer receives `ESC * NUL ? STX` instead of `ESC * NUL 0x80 STX`, enters an undefined state, and may print garbage, jam, or hang.

**Why it happens:**
The existing `PrinterDriver.write(char: str)` interface was designed for printable text characters. It encodes with `ascii, errors="replace"`. Printer control codes often include bytes outside the ASCII printable range (0x80-0xFF are used for parameter values, graphic data, and extended character sets). The `str -> bytes` encoding path silently corrupts these values.

**Consequences:**
- Control codes silently corrupted -- no error raised
- Printer enters undefined state (wrong graphics mode, wrong pitch, wrong paper feed distance)
- On dot matrix printers, corrupted ESC sequences can cause the printhead to slam into the side of the carriage (line spacing set to 0) or feed paper continuously
- On daisywheel/impact printers like the Juki, corrupted init codes produce wrong pitch or line spacing with no visible error

**Prevention:**
1. **Printer profiles should store control codes as byte arrays, not strings.** Use hex notation in TOML:
   ```toml
   [printer.juki_6100]
   init_codes = "1b 1a 49 1b 1e 09 1b 51"  # hex string
   newline = "0d 0a"
   ```
   Parse at load time: `bytes.fromhex(value.replace(" ", ""))`
2. **Add a `write_raw(data: bytes)` method to PrinterDriver** that bypasses the `str.encode("ascii")` path. The existing `JukiPrinterDriver._send_raw()` already does this character-by-character, but it should be a first-class method on the protocol.
3. **Validate control code sequences at profile load time.** Check that sequences start with valid ESC (0x1B) or control characters. Reject sequences that contain obviously invalid byte patterns.
4. **Never pass raw control code bytes through the WordWrapper or output_fn pipeline.** Control codes must be sent directly to the driver, bypassing the character-by-character pacing/wrapping system.

**Detection:**
- Print a test pattern with init codes that include bytes > 0x7F
- Compare hex dump of sent bytes vs expected bytes: `driver.write()` output vs profile definition

**Confidence:** HIGH -- direct code analysis of `FilePrinterDriver.write()` and `UsbPrinterDriver.write()` which both use `char.encode("ascii", errors="replace")`, confirmed by [ESC/P reference](https://files.support.epson.com/pdf/general/escp2ref.pdf) which documents parameters in the 0x80-0xFF range.

**Phase to address:** Printer profiles phase. The `write_raw()` method must exist before profiles send init codes.

---

### Pitfall 5: Config File Schema Changes Break Existing Installations on Upgrade

**What goes wrong:**
v1.2.0 ships with `config.toml` having fields `[llm]`, `[printer]`, `[audio]`. v1.2.1 adds `[printer.paper]` with a required `size` field. Users who upgrade have an old config file without `[printer.paper]`. The app crashes on startup with `KeyError: 'paper'` or a Pydantic `ValidationError`. The user sees a stack trace, has no idea what changed, and files a bug report.

**Why it happens:**
Config schema evolution is one of the most common sources of bugs in desktop applications. Every new field must have a default value. Every renamed field must be migrated. Every removed field must be silently ignored. Most developers test with fresh configs and never test the upgrade path.

**Consequences:**
- App crashes on startup after upgrade -- worst possible user experience
- Users manually edit config files incorrectly trying to fix it
- If the app writes a "fixed" config that drops unknown fields, user customizations from newer versions are lost on downgrade

**Prevention:**
1. **Every config field MUST have a default value.** Use Pydantic `BaseModel` with defaults for all fields:
   ```python
   class PrinterConfig(BaseModel):
       default_device: str | None = None
       columns: int = 80
       paper_size: str = "a4"  # Always has a default
   ```
2. **Include a `schema_version` integer in the config file.** Check it at load time. If missing, assume version 1 and migrate:
   ```toml
   schema_version = 1
   ```
3. **Use `model_config = ConfigDict(extra="ignore")` in Pydantic** to silently drop unknown fields rather than crashing. This handles downgrade gracefully.
4. **Write a `migrate_config(data: dict, from_version: int) -> dict` function** that applies sequential transformations:
   ```python
   def migrate_config(data, from_version):
       if from_version < 2:
           data.setdefault("printer", {}).setdefault("paper_size", "a4")
       if from_version < 3:
           # Rename old key
           if "delay_ms" in data:
               data["pacing"] = {"base_delay_ms": data.pop("delay_ms")}
       data["schema_version"] = CURRENT_VERSION
       return data
   ```
5. **Test the upgrade path explicitly:** Load a v1 config with v2 code. Load a v2 config with v1 code (downgrade). Load a corrupt/empty config.
6. **Never crash on config load failure.** Fall back to defaults and warn the user:
   ```
   [Warning: config.toml has errors. Using defaults. Run 'claude-teletype config reset' to fix.]
   ```

**Detection:**
- Delete the config file and launch the app -- should work with defaults
- Load a config from an older version -- should work without errors
- Add unknown fields to config -- should be silently ignored

**Confidence:** HIGH -- standard configuration management pattern, verified with [Pydantic BaseSettings docs](https://docs.pydantic.dev/latest/concepts/pydantic_settings/) and the TOML 1.1.0 specification.

**Phase to address:** Config system phase (first). Schema versioning and migration must be built into the first implementation, not retrofitted.

---

## Moderate Pitfalls

Mistakes that cause significant bugs or rework but are contained to specific modules.

### Pitfall 6: OpenRouter SSE Comment Lines Cause Silent Stream Parsing Failure

**What goes wrong:**
The developer implements OpenAI-compatible SSE parsing that strips the `data: ` prefix and parses JSON. This works for direct OpenAI API calls. When the same parser is used for OpenRouter, it encounters lines like `: OPENROUTER PROCESSING` (SSE comments used as keepalive). The parser tries `json.loads("OPENROUTER PROCESSING")`, gets a `JSONDecodeError`, and either crashes or (if caught) silently drops the comment -- which is correct. But the parser may also encounter empty `data:` lines or `data: ` with trailing whitespace, leading to `json.loads("")` errors.

**Why it happens:**
OpenRouter's SSE stream is mostly OpenAI-compatible but includes extra comment payloads that the official OpenAI SDK never produces. Per the SSE specification, lines starting with `:` are comments and should be ignored. But many ad-hoc SSE parsers do not handle this.

**Prevention:**
1. **The SSE parser must explicitly handle the SSE spec's four line types:**
   ```python
   for line in stream:
       line = line.strip()
       if not line:
           continue  # Empty line (event boundary)
       if line.startswith(":"):
           continue  # SSE comment (OpenRouter keepalive)
       if line.startswith("data: "):
           payload = line[6:]
           if payload == "[DONE]":
               break  # Stream complete
           chunk = json.loads(payload)
           # Process chunk...
       if line.startswith("event: "):
           event_type = line[7:]
           # Only relevant for Anthropic direct API
   ```
2. **Use the `httpx-sse` library** or similar for SSE parsing rather than hand-rolling. It handles comments, multi-line data fields, and event types correctly.
3. **Test with OpenRouter specifically** -- the comment payloads only appear under load when OpenRouter is routing to a slow backend.

**Detection:**
- Send a request to OpenRouter during high traffic. Check if keepalive comments cause errors.
- Log all raw SSE lines before parsing to see what the stream actually contains.

**Confidence:** MEDIUM -- verified from [OpenRouter streaming docs](https://openrouter.ai/docs/api/reference/streaming) which document comment payloads, but the specific failure mode depends on parser implementation.

**Phase to address:** Multi-LLM phase, specifically the OpenAI/OpenRouter bridge implementation.

---

### Pitfall 7: Textual ModalScreen Dismissal While Background Worker Is Streaming

**What goes wrong:**
The user opens the settings screen (ModalScreen push) while a Claude response is streaming in the background. They change a setting and dismiss the screen. The background worker was started on the main screen, and it is still running. But the worker holds references to widgets on the main screen (`self.query_one("#output", Log)`). If the modal screen's compose/dismiss cycle causes any recomposition of the main screen, the widget references become stale. The worker crashes with `NoMatches` or writes to a detached widget.

**Why it happens:**
Textual's worker lifecycle is tied to the DOM node where the worker was created. Pushing a modal screen does NOT pop the underlying screen -- it overlays it. The underlying screen's widgets remain mounted. However, if the settings screen modifies the app state in a way that triggers recomposition of the underlying screen (e.g., changing CSS classes, calling `recompose()`), widgets are destroyed and recreated with new IDs. The running worker's cached widget references (`log = self.query_one("#output", Log)`) now point to dead objects.

**Consequences:**
- `NoMatches` exception crashes the streaming worker
- Partial response lost -- user sees interrupted output
- App may enter inconsistent state (input remains disabled, status bar not updated)

**Prevention:**
1. **Do NOT trigger recomposition of the main screen from the settings screen.** Settings changes should update app-level state (instance variables), not CSS or widget structure.
2. **The settings screen should only modify config values, not apply them immediately.** Use a "changes take effect on next message" or "changes take effect on next session" pattern for settings that affect the streaming pipeline.
3. **Re-query widgets inside the worker loop, not once at the start.** Instead of:
   ```python
   log = self.query_one("#output", Log)  # Cached reference
   for chunk in stream:
       log.write(chunk)  # Breaks if recomposed
   ```
   Use:
   ```python
   for chunk in stream:
       self.query_one("#output", Log).write(chunk)  # Fresh query
   ```
   This is slightly less efficient but survives recomposition.
4. **Settings that affect the current stream (delay, audio) can use reactive attributes** that the worker reads on each iteration, rather than cached values.
5. **Disable the settings shortcut while streaming** (simplest prevention). Re-enable when the response completes.

**Detection:**
- Open settings screen while response is streaming. Change a setting. Dismiss. Does the stream continue?
- Open settings screen, trigger a recompose (resize the terminal while settings is open), dismiss. Does the worker crash?

**Confidence:** MEDIUM -- based on [Textual Screens docs](https://textual.textualize.io/guide/screens/) and [Textual Workers docs](https://textual.textualize.io/guide/workers/) which describe widget lifecycle, but the specific interaction between modal screens and workers is not explicitly documented.

**Phase to address:** TUI settings phase. Must be tested with concurrent streaming.

---

### Pitfall 8: Printer Profile CR/LF Newline Handling Differs Between Printer Types

**What goes wrong:**
The developer creates printer profiles that all use `\n` for newlines (matching Python convention). The Epson dot matrix works because it has "auto CR" enabled by default. The Juki daisywheel does not -- it needs explicit `\r\n`. The HP inkjet expects `\n` only. The developer tests on one printer, ships, and users with other printers get staircase printing (each line indented further right) or double-spaced output.

**Why it happens:**
Printer newline behavior varies fundamentally:

| Printer Type | Default Newline | Auto-CR | Notes |
|-------------|----------------|---------|-------|
| Epson ESC/P dot matrix | LF only (auto-CR on by default) | Configurable via DIP switch | `ESC 5` turns auto LF on/off |
| IBM PPDS emulation | LF includes CR automatically | Always on in PPDS mode | Different from ESC/P mode on same printer |
| Juki daisywheel | Needs explicit CR+LF | Off | Impact printers generally need CR+LF |
| HP inkjet (PCL) | LF only | Driver handles it | PCL `ESC &k2G` sets CR+LF mode |
| Thermal receipt (ESC/POS) | LF only | Always on | `\n` always moves to start of next line |

The existing `JukiPrinterDriver` already handles this correctly (converts `\n` to `\r\n`), but generalizing to profiles requires each profile to declare its newline behavior.

**Consequences:**
- Staircase printing: each line starts further right because CR was not sent
- Double spacing: printer interprets LF as LF+CR+LF because auto-CR and explicit CR both fire
- Garbled output on printer that interprets CR as form feed or other control character

**Prevention:**
1. **Each printer profile must declare its newline mode explicitly:**
   ```toml
   [printer.juki_6100]
   newline = "crlf"  # Send CR+LF

   [printer.epson_lq590]
   newline = "lf"    # Send LF only (auto-CR is on)

   [printer.hp_deskjet]
   newline = "lf"    # PCL handles it
   ```
2. **The profile driver must intercept `\n` and replace it with the profile's newline bytes** before writing to the hardware driver. This is the same pattern `JukiPrinterDriver` uses, but generalized.
3. **Include auto-CR initialization in the profile's init_codes** where supported. For Epson, send `ESC 5 1` to explicitly enable auto-CR so the profile does not depend on DIP switch settings.
4. **Test each profile on actual hardware** -- newline behavior cannot be accurately simulated.

**Detection:**
- Print a multi-line test pattern. If lines staircase right, CR is missing. If double-spaced, CR is being doubled.

**Confidence:** HIGH -- verified from [Epson LQ-590 manual](https://files.support.epson.com/htmldocs/lq590_/lq590_rf/cp_3.htm) (auto-CR DIP switch), [IBM PPDS reference](https://www.ibm.com/support/pages/list-ibm-ppds-and-epson-escp-control-codes-and-escape-sequences) (LF includes CR in PPDS mode), and existing Juki code in `printer.py`.

**Phase to address:** Printer profiles phase. Newline mode is the most fundamental profile setting.

---

### Pitfall 9: `keyring` Library Fails Silently in Headless/SSH Environments

**What goes wrong:**
The developer uses `keyring` for API key storage (good security practice). It works perfectly in development (macOS with GUI). In production or CI, the app runs via SSH or in a Docker container. `keyring` silently falls back to the `null` backend, which stores nothing and returns `None` for all keys. The app starts, cannot find any API key, and shows "Authentication error" with no indication that keyring is the problem.

**Why it happens:**
On macOS, `keyring` uses the system Keychain, which requires a GUI login session. Over SSH without a forwarded Keychain, the Keychain is locked. `keyring` does not raise an error -- it silently returns `None`. On Linux without GNOME Keyring or KDE Wallet, the same thing happens. The developer never tests outside their GUI terminal.

**Consequences:**
- API keys "disappear" when running over SSH
- No error message indicates keyring is the problem
- User sets keys, restarts app, keys are gone (null backend stored nothing)
- CI/CD pipelines fail mysteriously

**Prevention:**
1. **Do NOT use keyring as the primary or only key storage.** Use it as an optional enhancement.
2. **Key resolution order should be:**
   ```
   1. Environment variable (OPENAI_API_KEY, OPENROUTER_API_KEY)
   2. .env file in project root
   3. keyring (if available and functional)
   4. Prompt user interactively
   ```
3. **Test keyring availability before using it:**
   ```python
   try:
       import keyring
       # Write and read a test value to verify backend works
       keyring.set_password("claude-teletype-test", "test", "test")
       if keyring.get_password("claude-teletype-test", "test") == "test":
           keyring.delete_password("claude-teletype-test", "test")
           keyring_available = True
       else:
           keyring_available = False
   except Exception:
       keyring_available = False
   ```
4. **When keyring fails, log a clear message:** "Keychain not available (running headless?). Using environment variables for API keys."
5. **For v1.2, skip keyring entirely.** Environment variables are sufficient and universally supported. Add keyring support in a later milestone if users request it.

**Detection:**
- SSH into the machine and try to access a keyring-stored key
- Run in a Docker container and check if keys persist

**Confidence:** HIGH -- verified from [keyring docs](https://keyring.readthedocs.io/) and [macOS Keychain headless issues](https://github.com/jaraco/keyring/issues/457).

**Phase to address:** Config system phase. Decide on key storage strategy before implementing it.

---

### Pitfall 10: Typewriter Mode and Conversation Mode Share Input Handling Code That Conflicts

**What goes wrong:**
The developer implements typewriter mode (keyboard direct to printer) by reusing the TUI's input handling. In the TUI, `Input` widget captures keystrokes, buffers them, and submits on Enter. In typewriter mode, each keystroke should go immediately to the printer with no buffering. The developer adds a "typewriter mode" flag to `TeletypeApp` that changes behavior. But the `Input` widget still captures keystrokes, still buffers, still has placeholder text, still responds to Ctrl+D for quit. The typewriter experience feels like typing into a text field, not like a typewriter.

**Why it happens:**
The TUI's `Input` widget is designed for editing (backspace, cursor movement, selection). Typewriter mode needs raw character passthrough with NO editing capability -- what you type is what prints, immediately, irrevocably (like a real typewriter). These are fundamentally different input models, and trying to share code between them creates a Frankenstein that satisfies neither use case.

**Consequences:**
- Backspace "works" in the input widget but the character is already printed (cannot un-print)
- Cursor movement keys produce escape sequences that the printer interprets as control codes
- Delete key produces printer-visible characters
- The typewriter "feel" is destroyed by input buffering

**Prevention:**
1. **Typewriter mode should NOT use the TUI at all.** The existing `teletype.py` module already does this correctly: it uses `tty.setcbreak()` for raw character input and writes directly to the printer driver. This is the right approach.
2. **For v1.2, keep typewriter mode as a separate code path from the TUI.** The `--teletype` flag already bypasses `TeletypeApp` entirely. Enhance this path rather than trying to add typewriter mode inside the TUI.
3. **If a TUI typewriter mode is desired later**, use a custom widget that overrides `on_key()` to forward raw keystrokes, NOT the `Input` widget. But this is unnecessary complexity for v1.2.
4. **Mode switching between conversation and typewriter should restart the app**, not switch within the TUI. They are different applications that happen to share printer hardware.

**Detection:**
- In typewriter mode, press backspace. Does the printer receive a backspace character? Or does the Input widget consume it?
- Type rapidly in typewriter mode. Is there any buffering delay?

**Confidence:** HIGH -- direct analysis of existing `teletype.py` (raw mode) vs `tui.py` (Input widget), and the architectural differences between immediate vs. buffered input.

**Phase to address:** Typewriter mode phase. Keep it as a separate code path. Do NOT merge into TUI.

---

### Pitfall 11: OpenAI/OpenRouter Error Responses Use Different Error Structures Than Claude Code

**What goes wrong:**
The existing `errors.py` classifies errors by searching for substrings like "rate_limit", "overloaded", "429" in error messages. This works for Claude Code CLI error strings. OpenAI returns errors as structured JSON with a different schema: `{"error": {"message": "...", "type": "invalid_request_error", "code": "model_not_found"}}`. OpenRouter wraps errors differently again, and mid-stream errors arrive as SSE chunks with `finish_reason: "error"`. The error classifier never matches, and all OpenAI/OpenRouter errors show as "UNKNOWN".

**Why it happens:**
Each provider has its own error taxonomy:

| Provider | Error Format | Rate Limit | Auth Error | Context Exceeded |
|----------|-------------|------------|------------|-----------------|
| Claude Code CLI | Text in NDJSON `result` | "rate_limit" / "429" | "not authenticated" | "context window" |
| OpenAI API | JSON `{"error": {"type": "...", "code": "..."}}` | HTTP 429 + `"rate_limit_exceeded"` | HTTP 401 + `"invalid_api_key"` | `"context_length_exceeded"` or `finish_reason: "length"` |
| OpenRouter API | JSON (OpenAI-compatible) + mid-stream errors | HTTP 429 + `"rate_limit_exceeded"` | HTTP 401/403 | `finish_reason: "error"` with error field |
| Anthropic API | JSON `{"type": "error", "error": {"type": "...", "message": "..."}}` | `"rate_limit_error"` | `"authentication_error"` | `"invalid_request_error"` + message |

**Prevention:**
1. **Extend the error classification to accept structured error objects, not just strings:**
   ```python
   def classify_error(
       error_message: str | None = None,
       error_type: str | None = None,
       error_code: str | None = None,
       http_status: int | None = None,
   ) -> ErrorCategory:
   ```
2. **Each bridge module should extract error fields into this common signature** before calling the classifier.
3. **Add HTTP status code classification** as a first-pass filter:
   - 401/403 -> AUTH
   - 429 -> RATE_LIMIT
   - 500/502/503 -> OVERLOADED
   - 529 -> OVERLOADED (Anthropic-specific)
4. **Handle OpenRouter mid-stream errors** (arrive as SSE chunks after HTTP 200): check every chunk for `finish_reason: "error"` and extract the error message from the chunk's `error` field.

**Detection:**
- Force each error type on each backend (invalid key, rate limit, huge prompt) and verify the classifier produces the correct category.

**Confidence:** HIGH -- verified from [OpenAI error codes](https://platform.openai.com/docs/api-reference/errors), [OpenRouter error handling docs](https://openrouter.ai/docs/api/reference/streaming), and [Anthropic error docs](https://platform.claude.com/docs/en/api/errors).

**Phase to address:** Multi-LLM phase, as part of each bridge implementation. The error classifier extension should be done before the bridges are built.

---

## Minor Pitfalls

Mistakes that cause user-facing bugs but are quick to fix.

### Pitfall 12: TOML Config File Location Platform Differences

**What goes wrong:**
The developer hardcodes the config path as `~/.config/claude-teletype/config.toml`. This follows XDG convention on Linux. On macOS, the convention is `~/Library/Application Support/claude-teletype/config.toml`. The app works on the developer's Linux machine but users on macOS cannot find their config file and `~/Library/Application Support/` already has a different structure expectation.

**Prevention:**
Use `platformdirs` library (pure Python, no native deps):
```python
from platformdirs import user_config_dir
config_dir = Path(user_config_dir("claude-teletype"))
```
This returns `~/Library/Application Support/claude-teletype` on macOS and `~/.config/claude-teletype` on Linux. Alternatively, for simplicity, use `~/.claude-teletype/config.toml` which works on both platforms and is easy to find.

**Confidence:** HIGH -- standard cross-platform pattern.

**Phase to address:** Config system phase.

---

### Pitfall 13: Config File Written During Streaming Causes Partial Write / Corruption

**What goes wrong:**
The user changes a setting in the TUI while a response is streaming. The settings screen saves the config to disk. A crash or power loss during the write leaves a truncated TOML file. Next startup, the config cannot be parsed and the app crashes (see Pitfall 5).

**Prevention:**
1. **Atomic writes:** Write to a temporary file, then `os.replace()` to the target path. This is atomic on POSIX:
   ```python
   import tempfile, os
   with tempfile.NamedTemporaryFile(
       mode="w", dir=config_dir, delete=False, suffix=".tmp"
   ) as f:
       toml.dump(config_data, f)
       tmp_path = f.name
   os.replace(tmp_path, config_path)
   ```
2. **Never crash on corrupt config** -- fall back to defaults (see Pitfall 5).

**Confidence:** HIGH -- standard file I/O pattern.

**Phase to address:** Config system phase.

---

### Pitfall 14: TOML Cannot Represent Raw Byte Sequences Directly

**What goes wrong:**
The developer tries to store printer control codes as TOML string values with `\x` escapes: `init = "\x1b\x1a\x49"`. TOML 1.0 does NOT support `\x` escapes in strings. Only `\uXXXX` and `\UXXXXXXXX` are supported. The `\x` is treated as literal backslash-x, producing the string `\x1b\x1a\x49` (12 printable characters) instead of 3 bytes. TOML 1.1 adds `\xHH` support, but Python's `tomllib` (stdlib since 3.11) implements TOML 1.0 only.

**Prevention:**
1. **Store control codes as hex strings, not escape sequences:**
   ```toml
   init_codes = "1B 1A 49 1B 1E 09 1B 51"
   ```
   Parse with `bytes.fromhex(value.replace(" ", ""))`.
2. **Or store as arrays of integers:**
   ```toml
   init_codes = [0x1B, 0x1A, 0x49, 0x1B, 0x1E, 0x09, 0x1B, 0x51]
   ```
   Parse with `bytes(value)`.
3. **Do NOT rely on TOML 1.1 `\x` escapes** -- Python's stdlib `tomllib` does not support them as of Python 3.13.

**Confidence:** HIGH -- verified from [TOML 1.0 spec](https://toml.io/en/v1.0.0) (no `\xHH` support) and [Python tomllib docs](https://docs.python.org/3/library/tomllib.html) which implement TOML 1.0.

**Phase to address:** Printer profiles phase. The byte representation format must be decided before defining any profiles.

---

### Pitfall 15: OpenAI Token Usage Only Available if Explicitly Requested in Streaming Mode

**What goes wrong:**
The developer implements cost/token tracking by reading usage from the final streaming chunk. With OpenAI, `usage` is `null` in all streaming chunks by default. The developer assumes the API changed or their parsing is broken. They never see token counts.

**Prevention:**
OpenAI requires `stream_options: {"include_usage": true}` in the request body to get usage data in streaming mode. Without this flag, `usage` is null in all chunks and the final chunk with usage data is not sent. Add this to every OpenAI streaming request.

**Confidence:** HIGH -- verified from [OpenAI streaming docs](https://platform.openai.com/docs/api-reference/chat-streaming) which state the `usage` field requires `stream_options`.

**Phase to address:** Multi-LLM phase, in the OpenAI bridge.

---

### Pitfall 16: Textual Settings Screen Keybinding Conflicts with Main Screen

**What goes wrong:**
The developer binds `Ctrl+S` to open settings. But `Ctrl+S` might also be used in a future text editing context. More critically, the settings screen defines its own bindings (e.g., `Escape` to dismiss) that conflict with the main screen's `Escape` to cancel streaming. If the settings screen does not properly capture input focus, keystrokes leak through to the main screen.

**Prevention:**
1. **Use `ModalScreen` (not regular `Screen`) for settings.** Modal screens dim the background and capture all input -- keystrokes do not leak to the underlying screen.
2. **Choose a non-conflicting keybinding for settings.** `F2` (common convention for settings in TUI apps), `Ctrl+,` (macOS convention), or a command palette approach.
3. **Disable the settings keybinding while streaming** to avoid the worker interaction problem (Pitfall 7).

**Confidence:** HIGH -- verified from [Textual Screens guide](https://textual.textualize.io/guide/screens/) which describes modal screen input capture.

**Phase to address:** TUI settings phase.

---

## Phase-Specific Warnings

| Phase Topic | Likely Pitfall | Mitigation |
|-------------|---------------|------------|
| Config system | API keys in config file (Pitfall 1) | Separate secrets from config; use env vars |
| Config system | Schema changes break upgrades (Pitfall 5) | All fields have defaults, schema_version, migration function |
| Config system | Config path platform differences (Pitfall 12) | Use `platformdirs` or `~/.claude-teletype/` |
| Config system | Partial write corruption (Pitfall 13) | Atomic writes with `os.replace()` |
| Printer profiles | Control codes corrupted by ASCII encoding (Pitfall 4) | Add `write_raw(bytes)` method, store codes as hex strings |
| Printer profiles | TOML cannot represent raw bytes (Pitfall 14) | Use hex string format, parse with `bytes.fromhex()` |
| Printer profiles | CR/LF differences between printers (Pitfall 8) | Each profile declares newline mode explicitly |
| Multi-LLM | Different stream formats (Pitfall 2) | Separate parser per backend, normalize output type |
| Multi-LLM | Provider switch loses context (Pitfall 3) | Provider change starts new session with warning |
| Multi-LLM | OpenRouter SSE comments (Pitfall 6) | Handle SSE comment lines in parser |
| Multi-LLM | Error structure differences (Pitfall 11) | Extend error classifier with structured input |
| Multi-LLM | OpenAI usage requires opt-in (Pitfall 15) | Set `stream_options.include_usage: true` |
| TUI settings | Modal screen + worker conflict (Pitfall 7) | Disable settings during streaming, or re-query widgets |
| TUI settings | Keybinding conflicts (Pitfall 16) | Use ModalScreen, choose non-conflicting key (F2) |
| Typewriter mode | Shared input handling (Pitfall 10) | Keep typewriter as separate code path from TUI |
| keyring | Silent failure in headless environments (Pitfall 9) | Use env vars as primary, keyring as optional |

## Integration Gotchas Specific to v1.2

| Integration Point | Common Mistake | Correct Approach |
|-------------------|----------------|------------------|
| Config + API keys | Storing keys in config.toml | Env vars or .env file; config stores provider choice only |
| Config + printer profiles | Same TOML file for config and profiles | Profiles can be in same file but control codes use hex string format |
| Multi-LLM + existing bridge | Modifying bridge.py to support all formats | Keep bridge.py for Claude Code CLI; add new modules for OpenAI/OpenRouter |
| Multi-LLM + error handling | Extending substring matching for new providers | Add structured error classification (type, code, HTTP status) |
| Multi-LLM + session management | Allowing provider switch mid-conversation | New provider = new session, with user warning |
| TUI settings + streaming worker | Recomposing main screen from settings | Settings modify app state only; changes apply on next message |
| TUI settings + config file | Writing config synchronously during streaming | Atomic writes; never block the event loop |
| Typewriter mode + TUI | Running typewriter mode inside TeletypeApp | Typewriter mode bypasses TUI entirely (existing --teletype flag) |
| Printer profiles + existing drivers | Passing hex init codes through write(str) | Use write_raw(bytes) for control codes; write(str) for text only |

## "Changed Assumptions" Checklist

Things that were true in v1.0/v1.1 but are no longer true in v1.2:

- [ ] **Single LLM backend:** v1.0-v1.1 only used Claude Code CLI. v1.2 has three backends with different stream formats, error structures, and auth mechanisms.
- [ ] **No persistent configuration:** v1.0-v1.1 used CLI flags for all settings. v1.2 has a config file that must be loaded, validated, migrated, and saved.
- [ ] **One printer type:** v1.0-v1.1 assumed generic ASCII output or Juki-specific codes. v1.2 has profiles for multiple printer types with different control code languages.
- [ ] **Hardcoded init codes:** v1.0-v1.1 Juki codes were constants in JukiPrinterDriver. v1.2 control codes come from config files and must be validated.
- [ ] **No settings UI:** v1.0-v1.1 had no modal screens. v1.2 adds a settings screen that interacts with the running app state.
- [ ] **Text-only writes to printer:** v1.0-v1.1 only sent printable ASCII via `write(str)`. v1.2 sends raw byte sequences for control codes.
- [ ] **Session == Claude Code session:** v1.0-v1.1's session was always a Claude Code `--resume` session. v1.2 sessions may use OpenAI or OpenRouter, which have no persistent session concept.

## Sources

- [OpenAI Chat Streaming API](https://platform.openai.com/docs/api-reference/chat-streaming) -- SSE format, delta structure, `stream_options`, `data: [DONE]` termination
- [Anthropic Messages Streaming](https://platform.claude.com/docs/en/api/messages-streaming) -- SSE event types, `content_block_delta`, `message_stop`, error events, ping events
- [OpenRouter Streaming Docs](https://openrouter.ai/docs/api/reference/streaming) -- SSE comment payloads, OpenAI compatibility, mid-stream errors, cancellation limits
- [Simon Willison - How Streaming LLM APIs Work](https://til.simonwillison.net/llms/streaming-llm-apis) -- SSE format comparison across providers
- [GitGuardian - Python Secrets Management](https://blog.gitguardian.com/how-to-handle-secrets-in-python/) -- API key storage best practices, .env files, environment variables
- [Python keyring docs](https://keyring.readthedocs.io/) -- backend architecture, macOS Keychain requirements
- [keyring macOS headless issue #457](https://github.com/jaraco/keyring/issues/457) -- silent failure without GUI session
- [Pydantic Settings docs](https://docs.pydantic.dev/latest/concepts/pydantic_settings/) -- BaseSettings, config file loading, validation
- [TOML 1.0 Specification](https://toml.io/en/v1.0.0) -- no `\xHH` escape support
- [Python tomllib docs](https://docs.python.org/3/library/tomllib.html) -- TOML 1.0 implementation in stdlib
- [Textual Screens Guide](https://textual.textualize.io/guide/screens/) -- ModalScreen, push_screen, dismiss, callback pattern
- [Textual Workers Guide](https://textual.textualize.io/guide/workers/) -- worker lifecycle, DOM node binding, cleanup on screen pop
- [Textual Reactivity Guide](https://textual.textualize.io/guide/reactivity/) -- reactive attributes for live settings
- [Epson LQ-590 Printer Settings](https://files.support.epson.com/htmldocs/lq590_/lq590_rf/cp_3.htm) -- auto-CR DIP switch, ESC/P mode behavior
- [IBM PPDS vs ESC/P Control Codes](https://www.ibm.com/support/pages/list-ibm-ppds-and-epson-escp-control-codes-and-escape-sequences) -- command differences between emulation modes
- [ESC/P Reference Manual](https://files.support.epson.com/pdf/general/escp2ref.pdf) -- byte parameter ranges including 0x80-0xFF
- [ESC/P Wikipedia](https://en.wikipedia.org/wiki/ESC/P) -- protocol overview, printer compatibility

---
*Pitfalls research for: v1.2 configuration system, printer profiles, multi-LLM backends, TUI settings, typewriter mode*
*Researched: 2026-02-17*
