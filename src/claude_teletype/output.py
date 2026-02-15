"""Multiplexed output function factory for character-by-character streaming.

Creates a single output function that fans each character to one or more
destinations (e.g., TUI log widget, printer device).
"""

from collections.abc import Callable


def _noop(_char: str) -> None:
    """No-op output function used when no destinations are provided."""


def make_output_fn(*destinations: Callable[[str], None]) -> Callable[[str], None]:
    """Create a multiplexed output function that writes to all destinations.

    Args:
        *destinations: One or more callables that accept a single character string.
            Each destination is called in order for every character.

    Returns:
        A single callable that writes to all destinations. If zero destinations
        are provided, returns a no-op function. If one destination is provided,
        returns it directly (no wrapper overhead).
    """
    if not destinations:
        return _noop

    if len(destinations) == 1:
        return destinations[0]

    def output(char: str) -> None:
        for dest in destinations:
            dest(char)

    return output
