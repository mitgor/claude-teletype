"""Configuration system for Claude Teletype.

Loads settings from TOML file, environment variables, and CLI flags
with three-layer precedence: defaults < config file < env vars < CLI flags.
"""

from __future__ import annotations

import os
import tomllib
from dataclasses import dataclass, field, fields
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
# Printer profile name (generic, juki, escp, ppds, pcl)
profile = "generic"

# Printer device path (e.g., /dev/usb/lp0)
# Uncomment to use a specific device instead of auto-discovery:
# device = "/dev/usb/lp0"

# Custom profile example (uncomment and modify):
# [printer.profiles.my-printer]
# description = "My custom printer"
# init = "1b40"          # hex-encoded init bytes
# reset = "1b40"         # hex-encoded reset bytes
# line_spacing = ""      # hex-encoded line spacing command
# char_pitch = ""        # hex-encoded pitch command
# crlf = false           # true for CR+LF newlines
# formfeed_on_close = true

[llm]
# LLM backend: "claude-cli", "openai", "openrouter"
backend = "claude-cli"

# Model name (empty = backend default: gpt-4o for openai, openai/gpt-4o for openrouter)
# Claude Code CLI manages its own model selection.
model = ""

# System prompt for OpenAI/OpenRouter backends
# Claude Code CLI manages its own system prompt.
system_prompt = ""

[keys]
# API keys for LLM backends (config file keys override env vars).
# Env var fallback: OPENAI_API_KEY, OPENROUTER_API_KEY
# openai_api_key = "sk-..."
# openrouter_api_key = "sk-or-..."
"""


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
    juki: bool = False  # Deprecated: use printer_profile instead
    printer_profile: str = "generic"

    # [llm]
    backend: str = "claude-cli"  # "claude-cli", "openai", "openrouter"
    model: str = ""  # Empty = use backend's default
    system_prompt: str = ""  # For OpenAI/OpenRouter only

    # [keys]
    openai_api_key: str = ""
    openrouter_api_key: str = ""

    # Non-TOML field: stores raw custom profile dicts from [printer.profiles.*]
    custom_profiles: dict = field(default_factory=dict, repr=False)


def load_config(config_path: Path | None = None) -> TeletypeConfig:
    """Load config from TOML file, returning defaults if file missing."""
    path = config_path or CONFIG_FILE
    if not path.exists():
        return TeletypeConfig()

    with open(path, "rb") as f:
        raw = tomllib.load(f)

    # Extract custom profiles before flattening (they would break flat field mapping)
    printer_section = raw.get("printer", {})
    custom_profiles_raw = printer_section.get("profiles", {})

    # Flatten nested TOML sections into flat dataclass fields
    flat: dict = {}
    for value in raw.values():
        if isinstance(value, dict):
            # Skip nested dicts (like profiles sub-tables) during flattening
            for k, v in value.items():
                if not isinstance(v, dict):
                    flat[k] = v

    # Map 'profile' TOML key to 'printer_profile' field
    if "profile" in flat:
        flat["printer_profile"] = flat.pop("profile")

    # Only set fields that exist in the dataclass
    valid = {f.name for f in fields(TeletypeConfig)}
    filtered = {k: v for k, v in flat.items() if k in valid}
    config = TeletypeConfig(**filtered)
    config.custom_profiles = custom_profiles_raw
    return config


def apply_env_overrides(config: TeletypeConfig) -> TeletypeConfig:
    """Override config values from CLAUDE_TELETYPE_* environment variables."""
    # Skip non-env-overridable fields (API keys use their own env vars)
    _skip_fields = {"custom_profiles", "openai_api_key", "openrouter_api_key"}

    for f in fields(TeletypeConfig):
        if f.name in _skip_fields:
            continue
        env_key = f"{ENV_PREFIX}{f.name.upper()}"
        env_val = os.environ.get(env_key)
        if env_val is None:
            continue
        # Use default value type for dispatch (avoids __future__ annotations issue)
        default_val = getattr(config, f.name)
        if isinstance(default_val, bool) or f.name in ("juki", "no_audio", "no_tui"):
            setattr(config, f.name, env_val.lower() in ("1", "true", "yes"))
        elif isinstance(default_val, float):
            setattr(config, f.name, float(env_val))
        else:
            setattr(config, f.name, env_val)
    return config


def merge_cli_flags(config: TeletypeConfig, **flags) -> TeletypeConfig:
    """Override config values with CLI flags (non-None values only)."""
    for key, val in flags.items():
        if val is not None and hasattr(config, key):
            setattr(config, key, val)
    return config


def save_config(config: TeletypeConfig, config_path: Path | None = None) -> Path:
    """Save current configuration to TOML file.

    Preserves custom profiles from the loaded config. Creates parent
    directories if they don't exist. Returns the path to the saved file.
    """
    path = config_path or CONFIG_FILE
    path.parent.mkdir(parents=True, exist_ok=True)

    def _esc(value: str) -> str:
        return value.replace("\\", "\\\\").replace('"', '\\"').replace("\n", "\\n")

    lines = [
        "# Claude Teletype Configuration",
        "",
        "[general]",
        f"delay = {config.delay}",
        f"no_audio = {'true' if config.no_audio else 'false'}",
        f"no_tui = {'true' if config.no_tui else 'false'}",
        f'transcript_dir = "{_esc(config.transcript_dir)}"',
        "",
        "[printer]",
        f'profile = "{_esc(config.printer_profile)}"',
    ]

    if config.device:
        lines.append(f'device = "{_esc(config.device)}"')

    # Preserve custom profiles
    for name, data in config.custom_profiles.items():
        lines.append("")
        lines.append(f"[printer.profiles.{name}]")
        for key, val in data.items():
            if isinstance(val, bool):
                lines.append(f"{key} = {'true' if val else 'false'}")
            elif isinstance(val, (int, float)):
                lines.append(f"{key} = {val}")
            else:
                lines.append(f'{key} = "{_esc(str(val))}"')

    lines.extend([
        "",
        "[llm]",
        f'backend = "{_esc(config.backend)}"',
        f'model = "{_esc(config.model)}"',
        f'system_prompt = "{_esc(config.system_prompt)}"',
        "",
        "[keys]",
        f'openai_api_key = "{_esc(config.openai_api_key)}"',
        f'openrouter_api_key = "{_esc(config.openrouter_api_key)}"',
        "",
    ])

    path.write_text("\n".join(lines) + "\n", encoding="utf-8")
    return path


def write_default_config(config_path: Path | None = None) -> Path:
    """Create a config file with commented TOML template.

    Creates parent directories if they don't exist.
    Returns the path to the created file.
    """
    path = config_path or CONFIG_FILE
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(DEFAULT_CONFIG_TEMPLATE, encoding="utf-8")
    return path
