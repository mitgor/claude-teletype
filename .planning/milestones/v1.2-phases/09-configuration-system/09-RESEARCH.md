# Phase 9: Configuration System - Research

**Researched:** 2026-02-17
**Domain:** TOML config file, environment variable overrides, CLI flag merge, Typer subcommands
**Confidence:** HIGH

## Summary

Phase 9 adds a persistent configuration system to claude-teletype so users do not have to pass `--delay`, `--no-audio`, `--device`, etc. on every run. The system follows a standard three-layer precedence model: defaults < TOML config file < environment variables < CLI flags. The config file lives at the platform-standard location (`~/.config/claude-teletype/config.toml` on Linux, `~/Library/Application Support/claude-teletype/config.toml` on macOS) determined by `platformdirs`. Reading uses Python 3.11+ stdlib `tomllib`; writing the initial template uses `tomli-w`. A new `config` subcommand group provides `claude-teletype config show` and `claude-teletype config init`.

The main architectural challenge is restructuring the Typer CLI from a single-command app to one that supports both the existing default `chat` behavior AND a `config` subcommand group, without breaking backward compatibility. Typer's `@app.callback(invoke_without_command=True)` pattern solves this cleanly. The config module itself is straightforward: a dataclass defines the schema, `tomllib.load()` reads the file, environment variables with `CLAUDE_TELETYPE_` prefix override individual keys, and CLI flags (already handled by Typer) take final precedence.

The project currently has 8 CLI options that become configurable. The TOML schema is flat with two sections (`[general]` and `[printer]`), keeping it simple for users while being extensible for Phase 10 (Printer Profiles) and Phase 11 (Multi-LLM) which will add their own sections.

**Primary recommendation:** Use `tomllib` (stdlib) for reading, `tomli-w` + `platformdirs` as new dependencies, a `TeletypeConfig` dataclass for the schema, and Typer's callback pattern to restructure the CLI for subcommand support.

<phase_requirements>
## Phase Requirements

| ID | Description | Research Support |
|----|-------------|-----------------|
| CFG-01 | User can persist settings in a TOML config file at the platform-standard location | `platformdirs.user_config_path("claude-teletype")` gives correct OS-specific path. `tomllib` (stdlib) reads TOML. Config file location: `~/.config/claude-teletype/config.toml` (Linux), `~/Library/Application Support/claude-teletype/config.toml` (macOS), `%APPDATA%\claude-teletype\config.toml` (Windows). |
| CFG-02 | User gets a config file with documented defaults on first run or via `--init-config` | `tomli-w.dumps()` writes a Python dict as valid TOML. Template includes all keys with defaults and TOML comments explaining each. `--init-config` flag or `config init` subcommand generates the file. |
| CFG-03 | User can override any config value with a CLI flag for one session | Already works via Typer `typer.Option()` defaults. The change is: CLI flags default to `None` (sentinel), config provides the "real" defaults, and merge logic picks the first non-None from [CLI flag, env var, config file, hardcoded default]. |
| CFG-04 | User can run `claude-teletype config show` to see effective merged configuration | New `config` subcommand group via `app.add_typer()`. The `show` subcommand loads config, applies env overrides, and prints the merged result as formatted TOML or table. |
| CFG-05 | User can override config values via `CLAUDE_TELETYPE_*` environment variables | Simple `os.environ.get("CLAUDE_TELETYPE_DELAY")` pattern. Env vars use uppercase with underscores. Mapping is explicit in the config module: each config key has a known env var name. |
</phase_requirements>

## Standard Stack

### Core
| Library | Version | Purpose | Why Standard |
|---------|---------|---------|--------------|
| tomllib | stdlib (3.11+) | Read TOML config files | In Python stdlib since 3.11; project requires 3.12+. Zero dependencies. |
| tomli-w | >=1.2.0 | Write TOML config files (for `--init-config` / `config init`) | Official counterpart to tomli/tomllib. Only 2 functions, MIT licensed, tiny. |
| platformdirs | >=4.0.0 | Determine platform-standard config directory | De facto standard for cross-platform config paths. Used by pip, black, virtualenv, tox. |

### Supporting
| Library | Version | Purpose | When to Use |
|---------|---------|---------|-------------|
| dataclasses | stdlib | Define config schema as typed dataclass | Always -- provides type hints, defaults, and `asdict()` for serialization |

### Alternatives Considered
| Instead of | Could Use | Tradeoff |
|------------|-----------|----------|
| tomli-w | String templates for TOML output | String templates are fragile, can produce invalid TOML. tomli-w guarantees valid output. |
| platformdirs | Hardcoded `~/.config/` | Breaks on macOS (`~/Library/Application Support/`), Windows (`%APPDATA%`), and custom `$XDG_CONFIG_HOME`. |
| Hand-rolled config | pydantic-settings | pydantic-settings adds pydantic as a transitive dependency (~2MB). Overkill for 8 config keys with flat structure. |
| Hand-rolled config | dynaconf | Full-featured but heavy dependency for a simple CLI tool. |
| dataclass schema | TypedDict | Dataclass provides defaults, `asdict()`, and is more idiomatic for config objects. |

**Installation:**
```bash
uv add tomli-w platformdirs
```

## Architecture Patterns

### Recommended Project Structure

```
src/claude_teletype/
├── config.py          # NEW: TeletypeConfig dataclass, load/save/merge logic
├── cli.py             # MODIFIED: Typer restructure, config loading, flag merge
├── ... (existing)
```

### Pattern 1: Three-Layer Config Merge

**What:** Configuration values are resolved by checking layers in priority order: CLI flag > env var > config file > hardcoded default.

**When to use:** Every configurable value in the application.

**Example:**
```python
import os
import tomllib
from dataclasses import dataclass, asdict, field, fields
from pathlib import Path

from platformdirs import user_config_path

APP_NAME = "claude-teletype"
CONFIG_DIR = user_config_path(APP_NAME)
CONFIG_FILE = CONFIG_DIR / "config.toml"

# Env var prefix: CLAUDE_TELETYPE_
ENV_PREFIX = "CLAUDE_TELETYPE_"


@dataclass
class TeletypeConfig:
    """Application configuration with typed defaults.

    Each field maps to a TOML key, an env var, and a CLI flag.
    """
    # [general]
    delay: float = 75.0
    no_audio: bool = False
    no_tui: bool = False
    transcript_dir: str = "transcripts"

    # [printer]
    device: str | None = None
    juki: bool = False

    # Future: [llm], [profiles] sections added by Phase 10, 11


def load_config(config_path: Path | None = None) -> TeletypeConfig:
    """Load config from TOML file, returning defaults if file missing."""
    path = config_path or CONFIG_FILE
    if not path.exists():
        return TeletypeConfig()

    with open(path, "rb") as f:
        raw = tomllib.load(f)

    # Flatten nested TOML sections into flat dataclass fields
    flat = {}
    for section in raw.values():
        if isinstance(section, dict):
            flat.update(section)
        else:
            # Top-level keys (unlikely but handle gracefully)
            pass

    # Only set fields that exist in the dataclass
    valid_fields = {f.name for f in fields(TeletypeConfig)}
    filtered = {k: v for k, v in flat.items() if k in valid_fields}
    return TeletypeConfig(**filtered)


def apply_env_overrides(config: TeletypeConfig) -> TeletypeConfig:
    """Override config values from CLAUDE_TELETYPE_* environment variables."""
    type_map = {f.name: f.type for f in fields(TeletypeConfig)}

    for f in fields(TeletypeConfig):
        env_key = f"{ENV_PREFIX}{f.name.upper()}"
        env_val = os.environ.get(env_key)
        if env_val is not None:
            # Type coercion based on field type
            if f.type is bool or f.type == "bool":
                setattr(config, f.name, env_val.lower() in ("1", "true", "yes"))
            elif f.type is float or f.type == "float":
                setattr(config, f.name, float(env_val))
            else:
                setattr(config, f.name, env_val)
    return config


def merge_cli_flags(config: TeletypeConfig, **cli_flags) -> TeletypeConfig:
    """Override config values with CLI flags (non-None values only)."""
    for key, value in cli_flags.items():
        if value is not None and hasattr(config, key):
            setattr(config, key, value)
    return config
```

### Pattern 2: Typer CLI Restructure with Callback + Subcommands

**What:** Convert current single-command Typer app to support both default `chat` behavior and a `config` subcommand group.

**When to use:** When adding `config show` and `config init` without breaking `claude-teletype "hello"`.

**Example:**
```python
import typer

app = typer.Typer()
config_app = typer.Typer(help="Manage configuration")
app.add_typer(config_app, name="config")


@config_app.command()
def show():
    """Show effective merged configuration (file + env + flags)."""
    from claude_teletype.config import load_config, apply_env_overrides
    config = load_config()
    config = apply_env_overrides(config)
    # Print as formatted table or TOML
    ...


@config_app.command("init")
def init_config():
    """Create config file with documented defaults."""
    from claude_teletype.config import write_default_config
    write_default_config()


@app.callback(invoke_without_command=True)
def main(
    ctx: typer.Context,
    prompt: str = typer.Argument(None, help="Prompt (omit for interactive TUI)"),
    delay: float = typer.Option(None, "--delay", "-d", help="Base delay (ms)"),
    # ... other options with None defaults ...
):
    """Send a prompt to Claude and watch the response appear character by character."""
    if ctx.invoked_subcommand is not None:
        return  # Let subcommand handle it

    # Load config, apply env overrides, merge CLI flags
    from claude_teletype.config import load_config, apply_env_overrides, merge_cli_flags
    config = load_config()
    config = apply_env_overrides(config)
    config = merge_cli_flags(config, delay=delay, ...)

    # Proceed with chat logic using config
    check_claude_installed()
    ...
```

**CRITICAL BACKWARD COMPATIBILITY NOTE:** The current CLI uses `@app.command()` for `chat()` with `prompt` as a `typer.Argument`. When restructuring to `@app.callback(invoke_without_command=True)`, the behavior must remain identical:
- `claude-teletype "hello"` still works (prompt as positional arg)
- `claude-teletype --delay 50 "hello"` still works
- `claude-teletype` with no args still launches TUI
- `claude-teletype config show` is the NEW behavior

### Pattern 3: Config File Template with Comments

**What:** Generate a well-documented default config file that teaches users the available options.

**When to use:** `--init-config` flag or `claude-teletype config init`.

**Example template:**
```toml
# Claude Teletype Configuration
# Location: ~/.config/claude-teletype/config.toml (Linux)
#           ~/Library/Application Support/claude-teletype/config.toml (macOS)
#
# Values here are overridden by:
#   1. CLAUDE_TELETYPE_* environment variables
#   2. CLI flags (e.g., --delay 50)

[general]
# Base delay between characters in milliseconds (50-100 recommended)
delay = 75.0

# Disable bell sound on line breaks
no_audio = false

# Disable TUI, use plain stdout
no_tui = false

# Directory for transcript files (relative to cwd, or absolute path)
transcript_dir = "transcripts"

[printer]
# Printer device path (e.g., /dev/usb/lp0). Leave empty for auto-discovery.
# device = "/dev/usb/lp0"

# Enable Juki 6100 impact printer mode
juki = false
```

**Note on comments:** `tomli-w` does not write comments (TOML comments are not part of the data model). The template must be written as a raw string, NOT via `tomli-w.dumps()`. Use `tomli-w` only for `config show` output (programmatic round-trip). For the initial template, use a pre-formatted string constant.

### Pattern 4: `--init-config` as a Flag on the Main Command

**What:** In addition to `config init` subcommand, support `--init-config` as a top-level flag for discoverability.

**When to use:** Users running `claude-teletype --help` see the option without knowing about subcommands.

**Example:**
```python
@app.callback(invoke_without_command=True)
def main(
    ctx: typer.Context,
    init_config: bool = typer.Option(False, "--init-config", help="Create config file with defaults"),
    ...
):
    if init_config:
        from claude_teletype.config import write_default_config
        write_default_config()
        raise typer.Exit()
    ...
```

### Anti-Patterns to Avoid

- **API keys in TOML config:** NEVER store API keys or secrets in the config file. The config stores env var NAMES (e.g., `api_key_env = "OPENAI_API_KEY"`), not the actual key values. This is a prior project decision.
- **Auto-creating config on first run without user consent:** Do NOT silently create `~/.config/claude-teletype/config.toml` on first launch. The app should work with zero config (hardcoded defaults). Config file creation is an explicit user action via `--init-config` or `config init`.
- **Reading config on every keystroke:** Load config once at startup. Do NOT re-read the file during a session. (Prior decision: "No real-time config file watching".)
- **Breaking the existing CLI interface:** The restructure MUST preserve `claude-teletype "hello"` and `claude-teletype` (no args = TUI). The `config` subcommand is additive.
- **Deep nesting in TOML:** Keep the schema shallow. Two levels max (`[section]` + keys). Deeply nested config is hard to map to env vars and CLI flags.
- **Using `None` as TOML value:** TOML has no null/None type. Optional config values use TOML comments showing the key but commented out (like the `device` example above). In the dataclass, these are `str | None = None`.

## Don't Hand-Roll

| Problem | Don't Build | Use Instead | Why |
|---------|-------------|-------------|-----|
| Platform config paths | Hardcoded `~/.config/` or `$HOME/.claude-teletype` | `platformdirs.user_config_path()` | macOS uses `~/Library/Application Support/`, Windows uses `%APPDATA%`, Linux uses `$XDG_CONFIG_HOME` or `~/.config/` |
| TOML parsing | regex or string splitting | `tomllib` (stdlib) | TOML spec has edge cases (multiline strings, arrays of tables, datetime literals). stdlib handles all of them. |
| TOML writing | f-strings or `str.format()` | `tomli-w` for programmatic output | Guarantees valid TOML 1.0 output, handles quoting/escaping correctly |
| Boolean env var parsing | Custom truthiness checks | Explicit mapping (`"1"`, `"true"`, `"yes"` -> True) | Consistent with POSIX conventions and other Python tools |
| Config schema validation | Manual key checking | `dataclasses.fields()` introspection | Type-safe, auto-generates field list, provides defaults |

**Key insight:** The config system is simple enough (8 keys, 2 sections, flat structure) that a framework like pydantic-settings is overkill. A dataclass + `tomllib` + `platformdirs` gives full functionality in ~100 lines with zero learning curve.

## Common Pitfalls

### Pitfall 1: CLI Flag Defaults Masking Config Values
**What goes wrong:** Typer option defaults (e.g., `delay: float = typer.Option(75.0, ...)`) always have a value, so the merge logic cannot distinguish "user passed `--delay 75`" from "user did not pass `--delay` at all."
**Why it happens:** Typer fills in the default when the flag is not provided, making it indistinguishable from an explicit user value.
**How to avoid:** Change all configurable CLI option defaults to `None`. The merge function checks: if CLI value is not None, use it; else check env var; else use config file value; else use hardcoded default from the dataclass.
**Warning signs:** Config file values are always ignored because CLI defaults win.

### Pitfall 2: Boolean CLI Flags and None Sentinel
**What goes wrong:** `typer.Option(None, "--no-audio")` for a boolean flag does not work as expected -- Typer treats boolean options specially (`--flag` / `--no-flag`).
**Why it happens:** Typer auto-generates `--no-audio` / `--audio` pairs for `bool` options. Setting default to `None` may confuse this mechanism.
**How to avoid:** For boolean flags that need a None sentinel, use `Optional[bool] = typer.Option(None, ...)` or keep the boolean default and accept that the CLI default wins over config for booleans. Alternatively, use `--audio/--no-audio` explicitly. Test this behavior carefully.
**Warning signs:** `--no-audio` flag stops working or produces type errors.

### Pitfall 3: TOML Type Mismatches
**What goes wrong:** User writes `delay = "75"` (string) in TOML instead of `delay = 75.0` (float). `tomllib` preserves TOML types, so the dataclass gets a string where it expects a float.
**Why it happens:** TOML is typed, but users make mistakes. Unlike `.env` files, TOML values have actual types.
**How to avoid:** Validate types after loading. Either catch `TypeError` during dataclass construction, or add a validation step that coerces/rejects mismatched types with a helpful error message.
**Warning signs:** `TypeError: __init__() got an unexpected type` or silent string-to-float failures.

### Pitfall 4: Config File Permissions on macOS
**What goes wrong:** `platformdirs` returns `~/Library/Application Support/claude-teletype/` but the directory does not exist and `tomllib.load()` raises `FileNotFoundError`.
**Why it happens:** The config directory is not created until the user runs `config init` or `--init-config`.
**How to avoid:** `load_config()` must handle `FileNotFoundError` gracefully and return defaults. Only `config init` / `--init-config` creates the directory (using `Path.mkdir(parents=True, exist_ok=True)`).
**Warning signs:** Crash on first run before config file exists.

### Pitfall 5: Typer Callback Breaking Positional Argument
**What goes wrong:** Moving `prompt` from `@app.command()` to `@app.callback()` may change how Typer parses the positional argument, especially when subcommands exist.
**Why it happens:** Typer/Click callback arguments are processed before subcommand dispatch. A positional argument in a callback can interfere with subcommand name matching.
**How to avoid:** Test extensively that `claude-teletype "hello"`, `claude-teletype config show`, and `claude-teletype` (no args) all work correctly. May need to use `ctx.invoked_subcommand` check to prevent the callback from consuming args meant for subcommands. Consider making `prompt` a keyword option (`--prompt` / `-p`) instead of positional if conflicts arise.
**Warning signs:** `claude-teletype config show` fails because "config" is parsed as the prompt argument.

### Pitfall 6: Environment Variable Type Coercion for Floats
**What goes wrong:** `CLAUDE_TELETYPE_DELAY=50` is parsed as string "50", needs coercion to `float(50.0)`.
**Why it happens:** All environment variables are strings.
**How to avoid:** The `apply_env_overrides()` function must inspect the dataclass field type and coerce accordingly: `float()` for floats, `str.lower() in ("1", "true", "yes")` for bools, `str` for strings.
**Warning signs:** `TypeError` when setting a float field from env var string.

## Code Examples

### Example 1: Minimal Config Module (config.py)

```python
"""Configuration system for Claude Teletype.

Loads settings from TOML file, environment variables, and CLI flags
with three-layer precedence: defaults < config file < env vars < CLI flags.
"""

import os
import tomllib
from dataclasses import dataclass, fields, asdict
from pathlib import Path

from platformdirs import user_config_path

APP_NAME = "claude-teletype"
CONFIG_DIR: Path = user_config_path(APP_NAME)
CONFIG_FILE: Path = CONFIG_DIR / "config.toml"
ENV_PREFIX = "CLAUDE_TELETYPE_"

# Pre-formatted template with comments (tomli-w cannot write comments)
DEFAULT_CONFIG_TEMPLATE = """\
# Claude Teletype Configuration
# Override with CLAUDE_TELETYPE_* env vars or CLI flags.

[general]
# Base delay between characters in milliseconds (50-100 recommended)
delay = 75.0

# Disable bell sound on line breaks
no_audio = false

# Disable TUI, use plain stdout
no_tui = false

# Directory for transcript files (relative to cwd, or absolute)
transcript_dir = "transcripts"

[printer]
# Printer device path (e.g., /dev/usb/lp0)
# Uncomment to use a specific device instead of auto-discovery:
# device = "/dev/usb/lp0"

# Enable Juki 6100 impact printer mode
juki = false
"""


@dataclass
class TeletypeConfig:
    delay: float = 75.0
    no_audio: bool = False
    no_tui: bool = False
    transcript_dir: str = "transcripts"
    device: str | None = None
    juki: bool = False


def load_config(config_path: Path | None = None) -> TeletypeConfig:
    path = config_path or CONFIG_FILE
    if not path.exists():
        return TeletypeConfig()

    with open(path, "rb") as f:
        raw = tomllib.load(f)

    flat: dict = {}
    for key, value in raw.items():
        if isinstance(value, dict):
            flat.update(value)
        # top-level scalars could also be supported
    valid = {f.name for f in fields(TeletypeConfig)}
    return TeletypeConfig(**{k: v for k, v in flat.items() if k in valid})


def apply_env_overrides(config: TeletypeConfig) -> TeletypeConfig:
    for f in fields(TeletypeConfig):
        env_val = os.environ.get(f"{ENV_PREFIX}{f.name.upper()}")
        if env_val is None:
            continue
        if f.type is bool:
            setattr(config, f.name, env_val.lower() in ("1", "true", "yes"))
        elif f.type is float:
            setattr(config, f.name, float(env_val))
        else:
            setattr(config, f.name, env_val)
    return config


def merge_cli_flags(config: TeletypeConfig, **flags) -> TeletypeConfig:
    for key, val in flags.items():
        if val is not None and hasattr(config, key):
            setattr(config, key, val)
    return config


def write_default_config(config_path: Path | None = None) -> Path:
    path = config_path or CONFIG_FILE
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(DEFAULT_CONFIG_TEMPLATE, encoding="utf-8")
    return path
```

### Example 2: Restructured CLI with Config + Subcommands

```python
import typer

from claude_teletype.config import (
    CONFIG_FILE,
    TeletypeConfig,
    apply_env_overrides,
    load_config,
    merge_cli_flags,
    write_default_config,
)

app = typer.Typer()
config_app = typer.Typer(help="Manage configuration")
app.add_typer(config_app, name="config")


@config_app.command()
def show():
    """Show effective merged configuration (file + env)."""
    config = apply_env_overrides(load_config())
    # Display as table or TOML
    from dataclasses import asdict
    for key, val in asdict(config).items():
        typer.echo(f"{key} = {val!r}")


@config_app.command("init")
def init_config():
    """Create config file with documented defaults."""
    path = write_default_config()
    typer.echo(f"Config written to: {path}")


@app.callback(invoke_without_command=True)
def main(
    ctx: typer.Context,
    prompt: str = typer.Argument(None),
    delay: float = typer.Option(None, "--delay", "-d"),
    no_tui: bool = typer.Option(False, "--no-tui"),
    # ... more options ...
    init_config_flag: bool = typer.Option(False, "--init-config"),
):
    if ctx.invoked_subcommand is not None:
        return

    if init_config_flag:
        path = write_default_config()
        typer.echo(f"Config written to: {path}")
        raise typer.Exit()

    config = load_config()
    config = apply_env_overrides(config)
    config = merge_cli_flags(config, delay=delay, no_tui=no_tui, ...)
    # Proceed with chat using config values
    ...
```

### Example 3: Config Show Output

```
$ claude-teletype config show
# Effective configuration (file + env + defaults)
# Config file: ~/.config/claude-teletype/config.toml (loaded)

delay = 75.0
no_audio = false
no_tui = false
transcript_dir = "transcripts"
device = <not set>
juki = false

# Overrides active:
#   CLAUDE_TELETYPE_DELAY = "50" -> delay = 50.0
```

## State of the Art

| Old Approach | Current Approach | When Changed | Impact |
|--------------|------------------|--------------|--------|
| Custom `~/.apprc` files | `platformdirs` + XDG spec | ~2020+ | Cross-platform correctness |
| `configparser` (INI) | `tomllib` (TOML) | Python 3.11 (2022) | Type-safe config, stdlib support |
| `toml` package (unmaintained) | `tomllib` (stdlib) + `tomli-w` | PEP 680 (2022) | No third-party parser needed |
| `pydantic-settings` for everything | Dataclass + tomllib for simple apps | 2024+ | Lighter dependency footprint |

**Deprecated/outdated:**
- `toml` package (PyPI): Unmaintained since 2021, does not support TOML 1.0. Use `tomllib` (stdlib) instead.
- `configparser`: INI format lacks types, arrays, nested tables. TOML is the modern replacement.
- `appdirs`: Predecessor to `platformdirs`, no longer maintained. `platformdirs` is the active fork.

## Open Questions

1. **Positional `prompt` argument vs keyword option in callback**
   - What we know: Currently `prompt` is a positional `typer.Argument`. Moving to callback may conflict with subcommand names (e.g., `claude-teletype config` could be parsed as prompt="config").
   - What's unclear: Whether Typer handles this correctly with `invoke_without_command=True`. Click's argument parsing for callbacks with both positional args and subcommands can be tricky.
   - Recommendation: Test the callback approach first. If positional `prompt` conflicts with the `config` subcommand name, fall back to making `prompt` an option (`--prompt` / `-p`). Alternatively, keep `chat` as an explicit command and make the default behavior (no subcommand) launch TUI, with `claude-teletype chat "hello"` for one-shot prompts. This avoids the conflict entirely.

2. **Boolean flag None sentinel approach**
   - What we know: Typer handles boolean options via `--flag/--no-flag` pairs. Setting default to `None` to detect "not provided" may not work cleanly.
   - What's unclear: Whether `Optional[bool] = typer.Option(None)` produces the expected `--flag/--no-flag` behavior in Typer.
   - Recommendation: Test with a spike. If None sentinel does not work for booleans, accept that boolean CLI flags always win over config file (which is acceptable UX -- if the user passes `--no-audio`, they mean it).

3. **Config path override for testing**
   - What we know: Tests need to use temp directories, not the real user config path.
   - What's unclear: Best pattern for injecting a test config path.
   - Recommendation: `load_config(config_path=...)` already accepts an override path. For integration tests, use `tmp_path` fixtures. For the CLI, add a `--config` option or `CLAUDE_TELETYPE_CONFIG` env var to override the config file path.

## Sources

### Primary (HIGH confidence)
- **Python stdlib docs** - `tomllib` module: https://docs.python.org/3/library/tomllib.html
- **PEP 680** - tomllib addition to stdlib: https://peps.python.org/pep-0680/
- **platformdirs docs** - API and platform-specific paths: https://platformdirs.readthedocs.io/en/latest/api.html
- **platformdirs platform details** - macOS, Linux, Windows paths: https://platformdirs.readthedocs.io/en/latest/platforms.html
- **tomli-w PyPI** - TOML writer API: https://pypi.org/project/tomli-w/
- **Typer docs** - Subcommands: https://typer.tiangolo.com/tutorial/subcommands/
- **Typer docs** - add_typer: https://typer.tiangolo.com/tutorial/subcommands/add-typer/
- **Typer docs** - Callback with context: https://typer.tiangolo.com/tutorial/commands/context/
- **Typer docs** - Callback: https://typer.tiangolo.com/tutorial/commands/callback/
- **Project source code** - all files in `src/claude_teletype/` read directly

### Secondary (MEDIUM confidence)
- **cloudbytes.dev** - Default command pattern in Typer: https://cloudbytes.dev/snippets/set-the-default-command-in-python-typer-cli
- **jacobian.org** - Common arguments with Typer: https://jacobian.org/til/common-arguments-with-typer/
- **Real Python** - Python and TOML guide: https://realpython.com/python-toml/

### Tertiary (LOW confidence)
- None.

## Metadata

**Confidence breakdown:**
- Standard stack: HIGH -- tomllib is stdlib, platformdirs is de facto standard, tomli-w is the official counterpart
- Architecture: HIGH -- three-layer merge is a well-understood pattern used by uv, pip, streamlit, and others. Typer subcommand pattern is documented.
- Pitfalls: HIGH -- boolean sentinel issue and positional arg conflict identified from Typer documentation and Click behavior. Config file missing gracefully handled.

**Research date:** 2026-02-17
**Valid until:** 90 days (stable libraries, no fast-moving APIs)
