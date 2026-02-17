# Phase 15: Fix system_prompt Backend Hot-Swap - Research

**Researched:** 2026-02-17
**Domain:** TUI state management / backend factory wiring
**Confidence:** HIGH

## Summary

This phase fixes a minor integration gap identified in the v1.2 milestone audit: when a user switches LLM backends via the settings modal (ctrl+comma), the `system_prompt` configured in their TOML config file is silently dropped. The root cause is two-fold: (1) `TeletypeApp` never receives or stores the `system_prompt` value from config at startup, and (2) `_apply_settings` calls `create_backend()` without a `system_prompt` argument.

The fix is small and surgical: add a `_system_prompt` tracking attribute to `TeletypeApp.__init__`, pass it from `cli.py` at construction time (the same pattern used for `backend_name`, `model_config`, `profile_name`), and thread it through the `create_backend()` call in `_apply_settings`. No new libraries, no architectural changes, and no changes to the settings modal UI are required.

**Primary recommendation:** Add `self._system_prompt` tracking attribute to `TeletypeApp`, pass `config.system_prompt` from `cli.py`, and include it in the `create_backend()` call within `_apply_settings`. Test with a unit test that asserts `_system_prompt` survives a backend hot-swap.

<phase_requirements>
## Phase Requirements

| ID | Description | Research Support |
|----|-------------|-----------------|
| SET-01 | User can open a settings modal in the TUI via keyboard shortcut to change printer, LLM, delay, and audio | Settings modal already works (Phase 13). This phase ensures backend switching within that modal does not silently drop system_prompt, maintaining full settings integrity. |
| LLM-02 | User can chat with OpenAI or OpenRouter models via direct API using the openai library | OpenAI/OpenRouter backends accept `system_prompt` in their constructors and use it to prepend a system message. Without this fix, switching backends via settings loses that prompt, degrading the API chat experience. |
</phase_requirements>

## Standard Stack

### Core

No new libraries. This phase modifies only existing application code.

| Library | Version | Purpose | Why Standard |
|---------|---------|---------|--------------|
| textual | existing | TUI framework (TeletypeApp) | Already in use; no changes to Textual APIs needed |
| openai | existing | OpenAI/OpenRouter SDK | Already in use; system_prompt flows through constructor |
| pytest | existing | Testing | Existing test patterns for _apply_settings |

### Supporting

None needed.

### Alternatives Considered

| Instead of | Could Use | Tradeoff |
|------------|-----------|----------|
| Tracking attribute on TeletypeApp | Read system_prompt from backend._system_prompt before swap | Violates encapsulation; not all backends have _system_prompt (ClaudeCliBackend does not) |
| Adding system_prompt to settings modal UI | N/A | Out of scope for v1.2; would require new Input widget and UI testing; system_prompt is a developer-level setting, not a casual toggle |

**Installation:**
```bash
# No new packages needed
```

## Architecture Patterns

### Recommended Project Structure
```
# Files to modify (only 3):
src/claude_teletype/tui.py          # Add _system_prompt tracking attr + pass to create_backend
src/claude_teletype/cli.py          # Pass system_prompt= to TeletypeApp constructor
tests/test_tui.py                   # Add test_system_prompt_preserved_on_backend_swap
```

### Pattern 1: Tracking Attribute Injection (Established Pattern)

**What:** CLI startup reads config, passes values as constructor kwargs to `TeletypeApp`, which stores them as `self._attr` tracking attributes. These attributes are read in `_apply_settings` when rebuilding subsystems.

**When to use:** When the TUI needs to preserve a config value across runtime operations (like backend hot-swap) that reconstruct objects.

**Example (existing pattern from Phase 13):**
```python
# cli.py — passes config values to TUI constructor
tui_app = TeletypeApp(
    # ...existing kwargs...
    backend_name=config.backend,         # Phase 13 added these
    model_config=config.model,           # Phase 13 added these
    profile_name=resolved_profile.name,  # Phase 13 added these
    all_profiles=all_profiles,           # Phase 13 added these
)

# tui.py — __init__ stores as tracking attributes
def __init__(self, ..., backend_name="claude-cli", model_config="", ...):
    self._backend_name = backend_name
    self._model_config = model_config
```

**This is the exact same pattern for system_prompt. Add one more kwarg, one more tracking attr.**

### Pattern 2: Backend Factory system_prompt Passthrough (Already Exists)

**What:** `create_backend()` already accepts `system_prompt=` and passes it to OpenAI/OpenRouter constructors. ClaudeCliBackend ignores it (Claude CLI manages its own system prompt).

**Example (existing code, backends/__init__.py:43-84):**
```python
def create_backend(
    backend: str,
    model: str | None = None,
    system_prompt: str | None = None,  # Already exists!
    session_id: str | None = None,
) -> LLMBackend:
    if backend == "openai":
        return OpenAIBackend(
            api_key=os.environ.get("OPENAI_API_KEY"),
            model=model or "gpt-4o",
            system_prompt=system_prompt,  # Already wired!
        )
```

**The factory already supports it. The only missing piece is the caller (_apply_settings) not passing it.**

### Anti-Patterns to Avoid

- **Reading backend internals to extract system_prompt:** Do NOT read `self._backend._system_prompt` before swap. The old backend might be a `ClaudeCliBackend` with no `_system_prompt` attribute. The tracking attribute on `TeletypeApp` is the correct source of truth.
- **Adding system_prompt to settings modal:** Out of scope. system_prompt is a config-level setting, not a casual runtime toggle. Adding a UI field would expand scope unnecessarily.
- **Storing system_prompt in `_apply_settings` result dict:** The settings modal does not know about system_prompt and should not need to. The TUI's tracking attribute is the right layer.

## Don't Hand-Roll

| Problem | Don't Build | Use Instead | Why |
|---------|-------------|-------------|-----|
| Backend reconstruction | Custom state transfer between backends | `create_backend()` factory with system_prompt kwarg | Factory already handles all constructor differences between backends |
| Config persistence of system_prompt | Any write-back mechanism | Existing TOML config file + `TeletypeConfig.system_prompt` | system_prompt is read-only at runtime; users edit config file to change it |

**Key insight:** All the infrastructure already exists. This is purely a wiring fix, not a feature implementation.

## Common Pitfalls

### Pitfall 1: Forgetting to pass system_prompt when backend is unchanged but model changes

**What goes wrong:** If only the model changes (same backend), `_apply_settings` still creates a new backend. If `system_prompt` is not passed, it is lost even without a backend change.
**Why it happens:** The condition `result["backend"] != self._backend_name or result["model"] != self._model_config` triggers a full backend rebuild on model-only changes too.
**How to avoid:** Always pass `system_prompt=self._system_prompt` in the `create_backend()` call. It is harmless for ClaudeCliBackend (ignored by factory for that path).
**Warning signs:** Test should cover both backend-change and model-only-change scenarios.

### Pitfall 2: Empty string vs None for system_prompt

**What goes wrong:** `TeletypeConfig.system_prompt` defaults to `""` (empty string). `create_backend()` accepts `str | None`. `OpenAIBackend._build_messages()` checks `if self._system_prompt:` which is falsy for both `None` and `""`. So empty string and None are functionally equivalent.
**Why it happens:** The config layer uses `""` as default, the factory uses `None` as default.
**How to avoid:** CLI already converts with `config.system_prompt or None` at line 350. Follow the same pattern in the TUI: store as-is from constructor, pass `self._system_prompt or None` to `create_backend()`.
**Warning signs:** If tests use `""` for system_prompt, they would not catch a bug where the value is incorrectly converted.

### Pitfall 3: Not testing with a non-empty system_prompt

**What goes wrong:** A test that uses `system_prompt=""` or `system_prompt=None` would pass even if the wiring is broken, because the default behavior (no system prompt) is the same as a dropped system prompt.
**Why it happens:** Default values mask the bug.
**How to avoid:** Test MUST use a non-empty system_prompt string like `"You are a helpful assistant."` and verify it appears in the new backend's `_system_prompt` attribute after swap.
**Warning signs:** All tests pass but the bug is not actually caught.

## Code Examples

Verified patterns from the existing codebase:

### The Exact Bug (tui.py:200-209)
```python
# CURRENT CODE — system_prompt missing from create_backend call
new_backend = create_backend(
    backend=result["backend"],
    model=result["model"] or None,
    # BUG: system_prompt not passed!
)
```

### The Fix: TeletypeApp.__init__ (add system_prompt parameter)
```python
# In TeletypeApp.__init__ — add after model_config parameter
def __init__(
    self,
    # ...existing params...
    model_config: str = "",
    system_prompt: str = "",          # NEW
    profile_name: str = "generic",
    # ...rest...
) -> None:
    # ...existing assignments...
    self._model_config = model_config
    self._system_prompt = system_prompt  # NEW
    self._profile_name = profile_name
```

### The Fix: _apply_settings (pass system_prompt to create_backend)
```python
# In _apply_settings — add system_prompt kwarg
new_backend = create_backend(
    backend=result["backend"],
    model=result["model"] or None,
    system_prompt=self._system_prompt or None,  # FIX
)
```

### The Fix: cli.py (pass system_prompt to TeletypeApp)
```python
# In main() — add to TeletypeApp constructor call
tui_app = TeletypeApp(
    # ...existing kwargs...
    model_config=config.model,
    system_prompt=config.system_prompt,  # NEW
    profile_name=resolved_profile.name if resolved_profile else "generic",
    # ...rest...
)
```

### The Test: Verify system_prompt survives backend swap
```python
# In tests/test_tui.py — new test
def test_system_prompt_preserved_on_backend_swap():
    """system_prompt tracking attribute survives _apply_settings backend swap."""
    from unittest.mock import MagicMock, patch
    from claude_teletype.tui import TeletypeApp

    app = TeletypeApp(
        base_delay_ms=0,
        backend=MagicMock(),
        backend_name="openai",
        model_config="gpt-4o",
        system_prompt="You are a helpful assistant.",
    )

    mock_backend = MagicMock()
    mock_backend.validate = MagicMock()

    with patch(
        "claude_teletype.tui.create_backend", return_value=mock_backend
    ) as mock_create:
        app._apply_settings({
            "delay": 75.0,
            "no_audio": False,
            "backend": "openrouter",
            "model": "openai/gpt-4o",
            "profile": "generic",
        })

    # system_prompt must be passed to create_backend
    mock_create.assert_called_once_with(
        backend="openrouter",
        model="openai/gpt-4o",
        system_prompt="You are a helpful assistant.",
    )
    # Tracking attribute unchanged
    assert app._system_prompt == "You are a helpful assistant."
```

## State of the Art

| Old Approach | Current Approach | When Changed | Impact |
|--------------|------------------|--------------|--------|
| No backend hot-swap | create_backend + validate in _apply_settings | Phase 13 | Enabled runtime backend switching but missed system_prompt |

**Deprecated/outdated:** Nothing. This is a bug fix on current code.

## Open Questions

1. **Should system_prompt be editable in the settings modal?**
   - What we know: system_prompt is a developer-level config setting (defined in TOML `[llm]` section). The settings modal currently shows delay, audio, backend, model, and profile.
   - What's unclear: Whether users would want to change system_prompt at runtime without editing the config file.
   - Recommendation: OUT OF SCOPE for Phase 15. This is tracked as a v1.3+ item (SET-02/SET-03 scope). Phase 15 only preserves the existing value during hot-swap. Adding a UI field would require new widgets, validation, and testing beyond the minimal bug fix.

2. **Should the Claude CLI backend also accept system_prompt?**
   - What we know: `ClaudeCliBackend` ignores system_prompt — Claude Code CLI manages its own system prompt via `--system-prompt` flag. The `create_backend()` factory does not pass system_prompt to `ClaudeCliBackend`.
   - What's unclear: Nothing. This is by design.
   - Recommendation: No change needed. The fix is safe even when switching TO Claude CLI — `system_prompt` is stored on TeletypeApp (not the backend), so it will be available when switching BACK to an API backend.

## Sources

### Primary (HIGH confidence)

- **Codebase direct inspection** - All findings verified by reading the actual source code:
  - `src/claude_teletype/tui.py` - TeletypeApp.__init__ (missing system_prompt param), _apply_settings (missing system_prompt in create_backend call)
  - `src/claude_teletype/cli.py` - main() line 350 shows `system_prompt=config.system_prompt or None` at startup but not passed to TeletypeApp
  - `src/claude_teletype/backends/__init__.py` - create_backend already accepts system_prompt kwarg
  - `src/claude_teletype/backends/openai_backend.py` - OpenAIBackend stores and uses _system_prompt
  - `src/claude_teletype/settings_screen.py` - No system_prompt field in modal (expected, not needed)
  - `tests/test_tui.py` - No test for system_prompt preservation (gap to fill)
  - `tests/test_backends.py` - Has tests for system_prompt in _build_messages (confirms backend supports it)

- **v1.2 Milestone Audit** (`.planning/v1.2-MILESTONE-AUDIT.md`) - Documents the exact integration gap:
  > "system_prompt not preserved during backend hot-swap in _apply_settings... TeletypeApp doesn't store config.system_prompt as tracking attribute"

- **Phase 13 Plan 02** (`.planning/phases/13-settings-panel/13-02-PLAN.md`) - Documents the tracking attribute pattern used for backend_name, model_config, profile_name

### Secondary (MEDIUM confidence)

None needed. All findings are from direct codebase inspection.

### Tertiary (LOW confidence)

None.

## Metadata

**Confidence breakdown:**
- Standard stack: HIGH - No new dependencies; all infrastructure exists
- Architecture: HIGH - Follows exact pattern established in Phase 13 (tracking attributes)
- Pitfalls: HIGH - Three pitfalls identified from direct code analysis; all have clear mitigations

**Research date:** 2026-02-17
**Valid until:** Indefinite (this is a bug fix on stable internal code, not dependent on external library versions)
