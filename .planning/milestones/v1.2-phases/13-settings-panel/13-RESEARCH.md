# Phase 13: Settings Panel - Research

**Researched:** 2026-02-17
**Domain:** Textual ModalScreen, form widgets (Select, Switch, Input), runtime configuration mutation, TUI settings UX
**Confidence:** HIGH

## Summary

Phase 13 adds a settings modal to the TUI so users can adjust runtime settings (printer profile, LLM backend/model, character delay, and audio toggle) without leaving the application or editing config files. The scope is narrow: one requirement (SET-01), one screen (ModalScreen), four settings, and immediate effect on the running session. SET-02 (live preview) and SET-03 (persist to disk) are explicitly deferred to v1.3+.

The codebase already has all the infrastructure needed. `TeletypeApp` stores all configurable values as instance attributes (`base_delay_ms`, `no_audio`, `printer`, `_backend`). The `TypewriterScreen` push/pop pattern (Phase 12) provides a proven template for adding new screens. Textual 7.5.0 ships `ModalScreen`, `Select`, `Switch`, `Input`, `Label`, and container widgets that map directly to the four settings. The modal blocks interaction with the underlying chat while keeping it visible, which is the expected UX for an in-app settings panel.

The main architectural challenge is making settings changes "take effect immediately" (Success Criterion 3). Character delay (`base_delay_ms`) and audio toggle (`no_audio`) are simple attribute mutations on `TeletypeApp` that the next `stream_response` call picks up. Switching LLM backend/model is more complex: it requires creating a new backend instance via `create_backend()`, validating it, and replacing `_backend` on the app -- but only between turns, not mid-stream. Printer profile changes similarly require profile lookup and potentially re-wrapping the printer driver. None of these require restart because all are read fresh each turn.

**Primary recommendation:** Create a `SettingsScreen(ModalScreen)` in a new `settings_screen.py` file. Use `Select` for printer profile and backend, `Input(type="number")` for delay, and `Switch` for audio toggle. On dismiss, write changed values back to `TeletypeApp` attributes. Wire a `ctrl+s` keybinding in `TeletypeApp` to push the settings modal. Follow the same lazy-import and push_screen pattern established by `TypewriterScreen` in Phase 12.

<phase_requirements>
## Phase Requirements

| ID | Description | Research Support |
|----|-------------|-----------------|
| SET-01 | User can open a settings modal in the TUI via keyboard shortcut to change printer, LLM, delay, and audio | Textual `ModalScreen` provides a blocking overlay that prevents interaction with the chat screen. `Select` widget handles printer profile and LLM backend/model dropdowns. `Input(type="number")` handles delay input with built-in validation. `Switch` handles the audio boolean toggle. A keyboard shortcut (`ctrl+s`) pushes the modal via the same `push_screen` pattern used by TypewriterScreen. On "Save", the modal writes changed values directly to `TeletypeApp` attributes so they take effect on the next turn. |
</phase_requirements>

## Standard Stack

### Core
| Library | Version | Purpose | Why Standard |
|---------|---------|---------|--------------|
| textual | 7.5.0 (installed) | ModalScreen, Select, Switch, Input, Label, Container widgets | Already the TUI framework. ModalScreen blocks parent screen input and renders semi-transparent overlay. All form widgets are built-in. |

### Supporting
| Library | Version | Purpose | When to Use |
|---------|---------|---------|-------------|
| dataclasses | stdlib | None (existing TeletypeConfig used read-only) | Settings modal reads current app state; no new data structures needed |

### Alternatives Considered
| Instead of | Could Use | Tradeoff |
|------------|-----------|----------|
| ModalScreen | push_screen with regular Screen | ModalScreen blocks parent bindings and shows semi-transparent overlay. Regular Screen would fully replace the view. Modal is the correct UX for a transient settings panel. |
| Select widget for backend/profile | RadioSet/RadioButton | RadioSet shows all options at once, consuming vertical space. Select is compact (dropdown) and better for 3-5 options. |
| Input(type="number") for delay | Third-party textual-slider | Extra dependency for one numeric field. Input with built-in Number validator is sufficient. Slider cannot express precise float values like 75.0. |
| Switch for audio toggle | Checkbox | Switch and Checkbox are functionally equivalent for booleans. Switch has better visual affordance for on/off state. |
| Writing changed values directly to TeletypeApp attributes | Reactive properties / message bus | Over-engineering for 4 settings. Direct attribute mutation is what the codebase already does (e.g., `self.base_delay_ms` is a plain float). |

**Installation:**
No new dependencies. All required widgets ship with textual 7.5.0.

## Architecture Patterns

### Recommended Project Structure
```
src/claude_teletype/
    settings_screen.py   # NEW: SettingsScreen(ModalScreen) with form widgets
    tui.py               # MODIFIED: Add ctrl+s binding, action_open_settings method
    config.py            # EXISTING: TeletypeConfig, profiles list (read-only)
    profiles.py          # EXISTING: BUILTIN_PROFILES dict (read for dropdown options)
    backends/__init__.py # EXISTING: create_backend factory (called on backend change)
```

### Pattern 1: ModalScreen for Settings Panel

**What:** A `SettingsScreen` extending `ModalScreen` that composes form widgets (Select, Switch, Input) inside a styled container. The modal blocks chat interaction and is dismissed with Save or Cancel.

**When to use:** For any transient settings/configuration UI that should overlay the main screen.

**Example:**
```python
# settings_screen.py
from textual.containers import Vertical, Horizontal
from textual.screen import ModalScreen
from textual.widgets import Button, Input, Label, Select, Static, Switch

class SettingsScreen(ModalScreen):
    """Modal settings panel for runtime configuration."""

    CSS = """
    SettingsScreen {
        align: center middle;
    }
    #settings-dialog {
        width: 60;
        height: auto;
        max-height: 80%;
        border: thick $background 80%;
        background: $surface;
        padding: 1 2;
    }
    """

    BINDINGS = [
        Binding("escape", "cancel", "Cancel"),
    ]

    def __init__(
        self,
        current_delay: float,
        current_no_audio: bool,
        current_backend: str,
        current_model: str,
        current_profile: str,
        available_profiles: list[str],
        **kwargs,
    ) -> None:
        super().__init__(**kwargs)
        self._current_delay = current_delay
        self._current_no_audio = current_no_audio
        self._current_backend = current_backend
        self._current_model = current_model
        self._current_profile = current_profile
        self._available_profiles = available_profiles

    def compose(self) -> ComposeResult:
        with Vertical(id="settings-dialog"):
            yield Static("Settings", id="settings-title")

            yield Label("Character Delay (ms)")
            yield Input(
                value=str(self._current_delay),
                type="number",
                id="delay-input",
            )

            yield Label("Audio")
            yield Switch(value=not self._current_no_audio, id="audio-switch")

            yield Label("Printer Profile")
            yield Select(
                [(p, p) for p in self._available_profiles],
                value=self._current_profile,
                id="profile-select",
            )

            yield Label("LLM Backend")
            yield Select(
                [("claude-cli", "claude-cli"), ("openai", "openai"), ("openrouter", "openrouter")],
                value=self._current_backend,
                id="backend-select",
            )

            yield Label("Model")
            yield Input(
                value=self._current_model,
                id="model-input",
                placeholder="e.g., gpt-4o (empty = default)",
            )

            with Horizontal():
                yield Button("Save", variant="primary", id="save-btn")
                yield Button("Cancel", id="cancel-btn")
```
**Source:** [Textual ModalScreen](https://textual.textualize.io/guide/screens/), [Textual Select](https://textual.textualize.io/widgets/select/), [Textual Switch](https://textual.textualize.io/widgets/switch/), [Textual Input](https://textual.textualize.io/widgets/input/)

### Pattern 2: Dismiss with Result Data

**What:** The ModalScreen dismisses with a dict of changed settings. The parent app's callback applies the changes.

**When to use:** When the modal produces data that the parent screen needs to act on.

**Example:**
```python
# In settings_screen.py
class SettingsScreen(ModalScreen[dict | None]):
    """Dismisses with a dict of settings or None for cancel."""

    def on_button_pressed(self, event: Button.Pressed) -> None:
        if event.button.id == "save-btn":
            self.dismiss({
                "delay": float(self.query_one("#delay-input", Input).value),
                "no_audio": not self.query_one("#audio-switch", Switch).value,
                "backend": self.query_one("#backend-select", Select).value,
                "model": self.query_one("#model-input", Input).value,
                "profile": self.query_one("#profile-select", Select).value,
            })
        else:
            self.dismiss(None)

    def action_cancel(self) -> None:
        self.dismiss(None)


# In tui.py
class TeletypeApp(App):
    def action_open_settings(self) -> None:
        from claude_teletype.settings_screen import SettingsScreen

        self.push_screen(
            SettingsScreen(
                current_delay=self.base_delay_ms,
                current_no_audio=self.no_audio,
                current_backend=self._backend_name,
                current_model=self._model_config,
                current_profile=self._profile_name,
                available_profiles=list(self._all_profiles.keys()),
            ),
            callback=self._apply_settings,
        )

    def _apply_settings(self, result: dict | None) -> None:
        if result is None:
            return  # Cancelled
        self.base_delay_ms = result["delay"]
        self.no_audio = result["no_audio"]
        # Backend/model change requires new backend instance
        if result["backend"] != self._backend_name or result["model"] != self._model_config:
            self._switch_backend(result["backend"], result["model"])
        # Profile change
        if result["profile"] != self._profile_name:
            self._switch_profile(result["profile"])
```
**Source:** [Textual ModalScreen dismiss](https://textual.textualize.io/guide/screens/)

### Pattern 3: Applying Settings at Runtime

**What:** Changed settings are written to `TeletypeApp` attributes. Simple values (delay, audio) are immediate. Backend changes require creating a new backend instance. Profile changes require looking up the profile.

**When to use:** When settings must take effect immediately without restart.

**How each setting applies:**

1. **Character delay** (`base_delay_ms`): Direct attribute assignment. Next call to `pace_characters()` uses the new value.

2. **Audio toggle** (`no_audio`): Direct attribute assignment. The `stream_response` method checks `self.no_audio` each turn when building destinations. The TypewriterScreen also checks it on push.

3. **LLM backend/model**: Requires creating a new backend instance via `create_backend(backend, model)` and calling `validate()`. On success, replace `self._backend`. On validation failure (e.g., missing API key), show an error notification and keep the old backend. Conversation history is lost on backend switch (this is expected -- you're switching providers).

4. **Printer profile**: Look up the profile name in the merged profiles dict (`BUILTIN_PROFILES` + custom profiles). The printer driver itself doesn't change (it's the USB/file device), but the profile that controls ESC sequences changes. This maps to updating the `ProfilePrinterDriver`'s profile reference if the printer supports it, or noting the change for future printer operations.

### Pattern 4: Tracking Current Settings in TeletypeApp

**What:** `TeletypeApp` needs to know the *names* of the current backend and profile (not just the objects) so the settings modal can display them and detect changes.

**When to use:** When the settings modal needs to show current values.

**Example:**
```python
# In tui.py TeletypeApp.__init__, add tracking attributes:
def __init__(
    self,
    base_delay_ms: float = 75.0,
    printer=None,
    no_audio: bool = False,
    # ... existing params ...
    backend=None,
    backend_name: str = "claude-cli",
    model_config: str = "",
    profile_name: str = "generic",
    all_profiles: dict | None = None,
    **kwargs,
) -> None:
    # ... existing init ...
    self._backend_name = backend_name
    self._model_config = model_config
    self._profile_name = profile_name
    self._all_profiles = all_profiles or {}
```

### Anti-Patterns to Avoid

- **Storing settings in a global/singleton config object that the modal mutates:** The TUI already has all settings as instance attributes. A global mutable config adds indirection and makes testing harder. Mutate the app's own attributes directly.
- **Rebuilding the entire TUI on settings change:** The settings changes should be surgical. Don't unmount and remount the app or recreate widgets. Just update the attribute and let the next operation pick it up.
- **Blocking on backend validation in the modal:** Backend validation (API key check, network reachability) should happen in the `_apply_settings` callback, not in the modal's Save handler. If validation fails, show a Textual notification and revert.
- **Persisting settings to disk in v1.2:** SET-03 (config file write-back) is explicitly deferred to v1.3+. The settings panel only changes the runtime session.
- **Using reactive properties for settings:** The codebase uses plain attributes (e.g., `self.base_delay_ms = 75.0`). Converting to Textual reactive properties would require refactoring existing code for no benefit. The settings are read per-turn, not per-frame.

## Don't Hand-Roll

| Problem | Don't Build | Use Instead | Why |
|---------|-------------|-------------|-----|
| Modal overlay with input blocking | Custom screen with manual focus management | `ModalScreen` (Textual built-in) | ModalScreen handles input blocking, semi-transparent overlay, and dismissal automatically |
| Dropdown selection for profile/backend | Custom OptionList with manual toggle | `Select` widget (Textual built-in) | Select handles overlay rendering, keyboard navigation, type-to-search, and value binding |
| Boolean toggle for audio | Checkbox or custom toggle | `Switch` widget (Textual built-in) | Switch has better on/off visual affordance and built-in keyboard handling |
| Numeric input with validation | Custom text field with manual parsing | `Input(type="number")` with `Number` validator | Built-in type restriction prevents non-numeric input; validator checks range |
| Form layout with labels | Manual coordinate positioning | `Vertical` + `Label` containers | CSS-driven layout with standard Textual containers |

**Key insight:** Textual ships every widget needed for this settings panel. The entire implementation is wiring existing widgets to existing app attributes. No custom widget development is required.

## Common Pitfalls

### Pitfall 1: Backend Switch Fails Silently

**What goes wrong:** User selects a new LLM backend (e.g., openai) but has no API key. The app creates the backend, it fails validation, and either crashes or silently uses an invalid backend.

**Why it happens:** `create_backend()` returns a backend object, but `validate()` is a separate call that can raise `BackendError`. If the settings callback doesn't handle this, the invalid backend replaces the working one.

**How to avoid:** In `_apply_settings`, wrap backend creation + validation in try/except. On `BackendError`, show a Textual `self.notify("API key not configured", severity="error")` notification and keep the previous backend. Only replace `self._backend` on successful validation.

**Warning signs:** App shows API key error on next prompt after changing backend in settings.

### Pitfall 2: Settings Modal Opens Mid-Stream

**What goes wrong:** User opens the settings modal while Claude is streaming a response. They change delay or toggle audio, affecting the in-progress stream inconsistently.

**Why it happens:** `stream_response` reads `self.base_delay_ms` and `self.no_audio` at the start of each turn. If these change mid-stream, the current response may use a mix of old and new values.

**How to avoid:** Two approaches: (a) Disable the settings shortcut while streaming (check `input_widget.disabled` state, which is True during streaming), or (b) accept that mid-stream changes affect the current response immediately -- this is arguably the expected behavior for "take effect immediately." Approach (a) is simpler and safer.

**Warning signs:** Inconsistent pacing within a single response.

### Pitfall 3: Select Widget Value Mismatch

**What goes wrong:** The `Select` widget for printer profile is populated with profile names, but the currently selected profile doesn't match any option (e.g., a custom profile was auto-detected but isn't in the dropdown).

**Why it happens:** The settings modal builds the options list from `BUILTIN_PROFILES` + custom profiles, but the current profile was resolved through the auto-detect chain which might not have a name in the list.

**How to avoid:** Always include the current profile name in the options list even if it's not in the standard set. If auto-detection selected a profile, its name is in `BUILTIN_PROFILES` (auto-detect only matches known profiles). For the "generic" default case, "generic" is always in `BUILTIN_PROFILES`.

**Warning signs:** Select widget shows blank or "Select" prompt instead of current profile name.

### Pitfall 4: Keyboard Shortcut Conflicts

**What goes wrong:** `ctrl+s` (common for "save/settings") might be intercepted by the terminal emulator or conflict with other bindings.

**Why it happens:** Some terminal emulators use `ctrl+s` for XOFF (flow control stop). This would freeze the terminal.

**How to avoid:** Use `ctrl+s` but document that users with XOFF enabled should use `stty -ixon` to disable flow control. Alternatively, use `ctrl+,` (settings in many apps) or `F2` as the binding. The existing bindings use `ctrl+d` (quit) and `ctrl+t` (typewriter) without issues.

**Warning signs:** Terminal freezes when pressing ctrl+s. No response until ctrl+q (XON).

**Recommendation:** Use `ctrl+comma` as the settings keybinding. It is the standard "settings" shortcut in many applications (VS Code, Sublime Text, Discord) and does not conflict with terminal flow control. If `ctrl+comma` is not supported by Textual's key parser, fall back to `f2`.

### Pitfall 5: Model Input Freeform vs Validated

**What goes wrong:** User types an invalid model name in the model input field. The backend accepts it but the API returns an error on the next prompt.

**Why it happens:** Model names are backend-specific strings (e.g., "gpt-4o", "anthropic/claude-3.5-sonnet"). There's no authoritative list to validate against at settings-change time.

**How to avoid:** Accept freeform model input without validation at settings time. The error will surface naturally on the next prompt via the existing error handling/retry pipeline. This is the same behavior as `--model invalid-name` on the command line.

**Warning signs:** Error on first prompt after model change. This is expected and handled by existing error classification.

## Code Examples

Verified patterns from official sources and existing codebase:

### Complete SettingsScreen Skeleton
```python
# Source: Textual ModalScreen docs + existing TypewriterScreen pattern
from textual.app import ComposeResult
from textual.binding import Binding
from textual.containers import Horizontal, Vertical
from textual.screen import ModalScreen
from textual.widgets import Button, Input, Label, Select, Static, Switch


class SettingsScreen(ModalScreen[dict | None]):
    """Modal settings panel for runtime configuration.

    Displays current settings and allows changes. Dismisses with a dict
    of new values on Save, or None on Cancel/Escape.
    """

    BINDINGS = [
        Binding("escape", "cancel", "Cancel"),
    ]

    CSS = """
    SettingsScreen {
        align: center middle;
    }
    #settings-dialog {
        width: 60;
        height: auto;
        max-height: 80%;
        border: thick $background 80%;
        background: $surface;
        padding: 1 2;
    }
    #settings-title {
        text-style: bold;
        width: 100%;
        content-align: center middle;
        margin-bottom: 1;
    }
    .setting-label {
        margin-top: 1;
    }
    #button-row {
        margin-top: 1;
        align: center middle;
    }
    #button-row Button {
        margin: 0 1;
    }
    """

    def __init__(
        self,
        current_delay: float,
        current_no_audio: bool,
        current_backend: str,
        current_model: str,
        current_profile: str,
        available_profiles: list[str],
        **kwargs,
    ) -> None:
        super().__init__(**kwargs)
        self._delay = current_delay
        self._no_audio = current_no_audio
        self._backend = current_backend
        self._model = current_model
        self._profile = current_profile
        self._profiles = available_profiles

    def compose(self) -> ComposeResult:
        with Vertical(id="settings-dialog"):
            yield Static("Settings", id="settings-title")

            yield Label("Character Delay (ms)", classes="setting-label")
            yield Input(
                value=str(self._delay),
                type="number",
                id="delay-input",
                placeholder="50-200 recommended",
            )

            yield Label("Audio Enabled", classes="setting-label")
            yield Switch(value=not self._no_audio, id="audio-switch")

            yield Label("Printer Profile", classes="setting-label")
            yield Select[str](
                [(name, name) for name in self._profiles],
                value=self._profile,
                allow_blank=False,
                id="profile-select",
            )

            yield Label("LLM Backend", classes="setting-label")
            yield Select[str](
                [
                    ("Claude CLI", "claude-cli"),
                    ("OpenAI", "openai"),
                    ("OpenRouter", "openrouter"),
                ],
                value=self._backend,
                allow_blank=False,
                id="backend-select",
            )

            yield Label("Model", classes="setting-label")
            yield Input(
                value=self._model,
                id="model-input",
                placeholder="Leave empty for backend default",
            )

            with Horizontal(id="button-row"):
                yield Button("Save", variant="primary", id="save-btn")
                yield Button("Cancel", id="cancel-btn")

    def on_button_pressed(self, event: Button.Pressed) -> None:
        if event.button.id == "save-btn":
            delay_str = self.query_one("#delay-input", Input).value
            try:
                delay_val = float(delay_str) if delay_str else self._delay
            except ValueError:
                delay_val = self._delay

            self.dismiss({
                "delay": delay_val,
                "no_audio": not self.query_one("#audio-switch", Switch).value,
                "backend": self.query_one("#backend-select", Select).value,
                "model": self.query_one("#model-input", Input).value,
                "profile": self.query_one("#profile-select", Select).value,
            })
        elif event.button.id == "cancel-btn":
            self.dismiss(None)

    def action_cancel(self) -> None:
        self.dismiss(None)
```

### TeletypeApp Integration
```python
# Source: Existing tui.py push_screen pattern (TypewriterScreen)
# In tui.py, add to BINDINGS:
BINDINGS = [
    Binding("ctrl+d", "quit", "Quit"),
    Binding("ctrl+t", "enter_typewriter", "Typewriter"),
    Binding("ctrl+s", "open_settings", "Settings"),  # or ctrl+comma / f2
    Binding("escape", "cancel_stream", "Cancel", show=False),
]

# Add to TeletypeApp:
def action_open_settings(self) -> None:
    """Open the settings modal."""
    from claude_teletype.settings_screen import SettingsScreen

    self.push_screen(
        SettingsScreen(
            current_delay=self.base_delay_ms,
            current_no_audio=self.no_audio,
            current_backend=self._backend_name,
            current_model=self._model_config,
            current_profile=self._profile_name,
            available_profiles=list(self._all_profiles.keys()),
        ),
        callback=self._apply_settings,
    )

def _apply_settings(self, result: dict | None) -> None:
    """Apply settings from the modal to the running app."""
    if result is None:
        return

    self.base_delay_ms = result["delay"]
    self.no_audio = result["no_audio"]

    # Backend/model change
    if (result["backend"] != self._backend_name
            or result["model"] != self._model_config):
        from claude_teletype.backends import BackendError, create_backend
        try:
            new_backend = create_backend(
                backend=result["backend"],
                model=result["model"] or None,
            )
            new_backend.validate()
            self._backend = new_backend
            self._backend_name = result["backend"]
            self._model_config = result["model"]
        except BackendError as e:
            self.notify(str(e), severity="error")

    # Profile change
    if result["profile"] != self._profile_name:
        self._profile_name = result["profile"]
        # Update printer profile if printer is connected
        # (profile lookup from self._all_profiles)
```

### Testing SettingsScreen
```python
# Source: Existing test patterns (test_tui.py, test_typewriter_screen.py)
import pytest
from textual.app import App
from textual.widgets import Input, Select, Switch

from claude_teletype.settings_screen import SettingsScreen


class SettingsTestApp(App):
    """Minimal test app that pushes SettingsScreen on mount."""

    def __init__(self, **settings_kwargs):
        super().__init__()
        self._settings_kwargs = settings_kwargs
        self.applied_result = None

    def on_mount(self) -> None:
        self.push_screen(
            SettingsScreen(**self._settings_kwargs),
            callback=self._on_settings_result,
        )

    def _on_settings_result(self, result):
        self.applied_result = result


@pytest.mark.asyncio
async def test_settings_screen_composes():
    """SettingsScreen renders with all expected form widgets."""
    app = SettingsTestApp(
        current_delay=75.0,
        current_no_audio=False,
        current_backend="claude-cli",
        current_model="",
        current_profile="generic",
        available_profiles=["generic", "juki", "escp"],
    )
    async with app.run_test() as pilot:
        assert app.screen.query_one("#delay-input", Input) is not None
        assert app.screen.query_one("#audio-switch", Switch) is not None
        assert app.screen.query_one("#profile-select", Select) is not None
        assert app.screen.query_one("#backend-select", Select) is not None


@pytest.mark.asyncio
async def test_settings_cancel_dismisses_none():
    """Pressing Cancel dismisses the modal with None."""
    app = SettingsTestApp(
        current_delay=75.0,
        current_no_audio=False,
        current_backend="claude-cli",
        current_model="",
        current_profile="generic",
        available_profiles=["generic"],
    )
    async with app.run_test() as pilot:
        await pilot.click("#cancel-btn")
        await pilot.pause()
        assert app.applied_result is None


@pytest.mark.asyncio
async def test_settings_save_returns_values():
    """Pressing Save dismisses with current widget values."""
    app = SettingsTestApp(
        current_delay=75.0,
        current_no_audio=False,
        current_backend="claude-cli",
        current_model="",
        current_profile="generic",
        available_profiles=["generic"],
    )
    async with app.run_test() as pilot:
        await pilot.click("#save-btn")
        await pilot.pause()
        assert app.applied_result is not None
        assert app.applied_result["delay"] == 75.0
```

## State of the Art

| Old Approach | Current Approach | When Changed | Impact |
|--------------|------------------|--------------|--------|
| Edit config file + restart app | Settings modal changes runtime values immediately | Phase 13 | Users can experiment with settings without leaving the TUI |
| CLI flags only for per-session overrides | Settings modal + CLI flags | Phase 13 | Two complementary ways to override defaults |
| No feedback on settings change | Notification on backend switch failure | Phase 13 | Users know when a backend change fails validation |

**Deprecated/outdated:**
- None. This is a new feature. Config file and CLI flags continue to work as before for startup values.

**Deferred to v1.3+ (from REQUIREMENTS.md):**
- SET-02: Live settings preview showing pacing speed in real-time
- SET-03: Settings persist to config file via `tomli-w` write-back

## Open Questions

1. **Keyboard shortcut for settings**
   - What we know: `ctrl+s` is intuitive but may trigger XOFF in terminals. `ctrl+comma` is the standard settings shortcut in many apps. `f2` is universally safe.
   - What's unclear: Whether Textual's key parser supports `ctrl+comma` as a binding key.
   - Recommendation: Try `ctrl+comma` first. If Textual doesn't support it, use `f2`. Avoid `ctrl+s` unless XOFF concerns are documented.

2. **Profile change effect on active printer**
   - What we know: The printer driver (`ProfilePrinterDriver`) is initialized with a profile. Changing the profile at runtime would require either (a) re-initializing the driver with the new profile, or (b) updating the profile reference on the existing driver.
   - What's unclear: Whether `ProfilePrinterDriver` supports profile swapping after initialization. The printer hardware connection should persist; only the ESC sequences change.
   - Recommendation: Store the profile name and look up the profile object for the next printer operation. If the driver is already initialized, check if it has a mutable profile attribute. If not, the simplest approach is to note the preference and apply it when the next printer output is created (each `stream_response` call creates new output destinations).

3. **Conversation history on backend switch**
   - What we know: Each backend (`OpenAIBackend`, `ClaudeCliBackend`) maintains its own conversation history. Switching backends loses the conversation context.
   - What's unclear: Whether users expect conversation continuity across backend switches.
   - Recommendation: Accept the history loss. Show a notification: "Switched to {backend}. Conversation history reset." This is honest and matches the technical reality -- different APIs can't share conversation state.

4. **Settings shortcut availability during streaming**
   - What we know: During streaming, the input widget is disabled and the app is processing a response.
   - What's unclear: Whether the settings shortcut should be disabled during streaming or allowed.
   - Recommendation: Allow opening settings during streaming. The modal will block the chat screen, and the stream continues in the background worker. Changed delay takes effect on the next `pace_characters` call within the current stream. Changed backend/model only takes effect on the next turn.

## Sources

### Primary (HIGH confidence)
- [Textual ModalScreen Guide](https://textual.textualize.io/guide/screens/) - Modal screen creation, dismiss patterns, callback handling
- [Textual Select Widget](https://textual.textualize.io/widgets/select/) - Dropdown selection, options format, value binding
- [Textual Switch Widget](https://textual.textualize.io/widgets/switch/) - Boolean toggle, Changed event, value access
- [Textual Input Widget](https://textual.textualize.io/widgets/input/) - Numeric type restriction, Number validator, placeholder
- [Textual Widget Gallery](https://textual.textualize.io/widget_gallery/) - All available form widgets
- [Textual Testing Guide](https://textual.textualize.io/guide/testing/) - Pilot-based async testing with run_test
- Existing codebase: `src/claude_teletype/tui.py` - TeletypeApp class, push_screen pattern, attribute storage
- Existing codebase: `src/claude_teletype/typewriter_screen.py` - Screen push/pop pattern, lazy import
- Existing codebase: `src/claude_teletype/config.py` - TeletypeConfig dataclass, all configurable fields
- Existing codebase: `src/claude_teletype/backends/__init__.py` - create_backend factory, BackendError, validate pattern
- Existing codebase: `src/claude_teletype/profiles.py` - BUILTIN_PROFILES dict, PrinterProfile dataclass
- Existing codebase: `tests/test_tui.py` - Test patterns for TeletypeApp
- Existing codebase: `tests/test_typewriter_screen.py` - Test patterns for pushed screens

### Secondary (MEDIUM confidence)
- [Creating a Modal Dialog in Textual](https://www.blog.pythonlibrary.org/2024/02/06/creating-a-modal-dialog-for-your-tuis-in-textual/) - Practical ModalScreen examples
- [How to use modal screens in Textual](https://mathspp.com/blog/how-to-use-modal-screens-in-textual) - Additional modal patterns
- [Textual RadioSet](https://textual.textualize.io/widgets/radioset/) - Alternative to Select for exclusive options

### Tertiary (LOW confidence)
- ctrl+comma keybinding support in Textual - Not verified whether Textual's key parser supports this binding string. Needs testing.
- textual-slider third-party widget - Exists on GitHub but not needed; Input(type="number") is sufficient.

## Metadata

**Confidence breakdown:**
- Standard stack: HIGH - All widgets are built into Textual 7.5.0 which is already installed. No new dependencies.
- Architecture: HIGH - ModalScreen pattern is well-documented. Push/dismiss/callback flow is proven. Settings application is straightforward attribute mutation.
- Pitfalls: HIGH - Key pitfalls (backend validation, XOFF, mid-stream changes) identified from codebase analysis and terminal knowledge.
- Code examples: HIGH - Based on Textual official docs and existing codebase patterns (TypewriterScreen provides direct template).
- Testing: HIGH - Same `run_test()` + Pilot pattern used throughout the test suite.

**Research date:** 2026-02-17
**Valid until:** 2026-03-17 (stable domain, Textual API mature, no new dependencies)
