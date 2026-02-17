"""Configuration system for Claude Teletype.

Loads settings from TOML file, environment variables, and CLI flags
with three-layer precedence: defaults < config file < env vars < CLI flags.
"""

import os
import tomllib
from dataclasses import dataclass, fields
from pathlib import Path
from typing import get_args, get_origin

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


def _is_bool_field(field_type: type) -> bool:
    """Check if a dataclass field type is bool (including Union types)."""
    if field_type is bool:
        return True
    return False


def _is_float_field(field_type: type) -> bool:
    """Check if a dataclass field type is float (including Union types)."""
    if field_type is float:
        return True
    return False


def _is_str_field(field_type: type) -> bool:
    """Check if a dataclass field type is str or str | None."""
    if field_type is str:
        return True
    # Handle Union types like str | None
    origin = get_origin(field_type)
    if origin is type(str | None):  # types.UnionType
        args = get_args(field_type)
        return str in args
    return False


def load_config(config_path: Path | None = None) -> TeletypeConfig:
    """Load config from TOML file, returning defaults if file missing."""
    path = config_path or CONFIG_FILE
    if not path.exists():
        return TeletypeConfig()

    with open(path, "rb") as f:
        raw = tomllib.load(f)

    # Flatten nested TOML sections into flat dataclass fields
    flat: dict = {}
    for value in raw.values():
        if isinstance(value, dict):
            flat.update(value)

    # Only set fields that exist in the dataclass
    valid = {f.name for f in fields(TeletypeConfig)}
    filtered = {k: v for k, v in flat.items() if k in valid}
    return TeletypeConfig(**filtered)


def apply_env_overrides(config: TeletypeConfig) -> TeletypeConfig:
    """Override config values from CLAUDE_TELETYPE_* environment variables."""
    for f in fields(TeletypeConfig):
        env_key = f"{ENV_PREFIX}{f.name.upper()}"
        env_val = os.environ.get(env_key)
        if env_val is None:
            continue
        if _is_bool_field(f.type):
            setattr(config, f.name, env_val.lower() in ("1", "true", "yes"))
        elif _is_float_field(f.type):
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
