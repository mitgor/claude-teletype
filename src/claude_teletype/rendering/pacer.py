"""Character pacing module for typewriter-style output.

Classifies characters into categories and applies variable delays
to create an authentic typewriter feel.
"""

import asyncio
import sys
from collections.abc import Callable

# Delay multipliers relative to base delay
CHAR_DELAYS: dict[str, float] = {
    "punctuation": 1.5,  # . , ! ? ; : -- feels like "thinking"
    "newline": 3.0,  # \n -- carriage return pause
    "space": 0.5,  # spaces are visually light, go faster
    "default": 1.0,  # alphanumeric and everything else
}

PUNCTUATION: set[str] = set(".,!?;:")


def classify_char(char: str) -> str:
    """Classify a character for pacing purposes.

    Returns one of: "newline", "space", "punctuation", "default".
    """
    if char == "\n":
        return "newline"
    if char == " ":
        return "space"
    if char in PUNCTUATION:
        return "punctuation"
    return "default"


async def pace_characters(
    text: str,
    base_delay_ms: float = 75.0,
    output_fn: Callable[[str], None] | None = None,
) -> None:
    """Output text character by character with typewriter pacing.

    Args:
        text: The text to output character by character.
        base_delay_ms: Base delay in milliseconds between characters.
        output_fn: Optional function to call with each character.
                   If None, writes to sys.stdout with flush.
    """
    base_delay = base_delay_ms / 1000.0

    for char in text:
        if output_fn is not None:
            output_fn(char)
        else:
            sys.stdout.write(char)
            sys.stdout.flush()

        multiplier = CHAR_DELAYS[classify_char(char)]
        await asyncio.sleep(base_delay * multiplier)
