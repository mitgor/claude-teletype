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
    # Skip non-env-overridable fields
    _skip_fields = {"custom_profiles"}

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


def write_default_config(config_path: Path | None = None) -> Path:
    """Create a config file with commented TOML template.

    Creates parent directories if they don't exist.
    Returns the path to the created file.
    """
    path = config_path or CONFIG_FILE
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(DEFAULT_CONFIG_TEMPLATE, encoding="utf-8")
    return path
