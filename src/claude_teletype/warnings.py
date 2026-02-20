"""Warning logic for configuration conflicts and backend limitations.

Detects situations where user configuration will be silently ignored or
where actions would cause data loss, and provides friendly explanations
with remediation suggestions.
"""

from __future__ import annotations

# Track which (backend, system_prompt) combos have already been warned about
# this process lifetime. Per-process suppression is sufficient since config
# changes restart the relevant code paths.
_warned_combos: set[tuple[str, str]] = set()


def check_system_prompt_warning(backend: str, system_prompt: str) -> str | None:
    """Check if system_prompt is configured but will be ignored by the backend.

    Returns a warning message if backend is claude-cli and system_prompt is
    non-empty, since Claude Code manages its own context via CLAUDE.md and
    ignores the system_prompt setting.

    Args:
        backend: The configured backend name (e.g., "claude-cli", "openai").
        system_prompt: The configured system prompt string.

    Returns:
        A friendly warning message string, or None if no warning needed.
    """
    if backend != "claude-cli" or not (system_prompt and system_prompt.strip()):
        return None

    return (
        "system_prompt is configured but will be ignored by the claude-cli backend. "
        "Claude Code manages its own context via CLAUDE.md, so custom system prompts "
        "have no effect. To use your system_prompt, switch to the openai or openrouter "
        "backend in Settings (Ctrl+,) or in your config file."
    )


def should_warn_startup(backend: str, system_prompt: str) -> bool:
    """Check if a startup warning should be shown for this config combination.

    Returns True the first time a given (backend, system_prompt) combination
    is seen, then False for subsequent calls with the same combination.
    This prevents repeated warnings when config hasn't changed.

    Args:
        backend: The configured backend name.
        system_prompt: The configured system prompt string.

    Returns:
        True if this is the first time seeing this combination, False otherwise.
    """
    key = (backend, system_prompt)
    if key in _warned_combos:
        return False
    _warned_combos.add(key)
    return True


def _reset_warned() -> None:
    """Reset the warned combos set. For testing only."""
    _warned_combos.clear()
