"""Re-export shim — moved to claude_teletype.rendering.pacer."""

from claude_teletype.rendering.pacer import *  # noqa: F401,F403
from claude_teletype.rendering.pacer import (  # noqa: F401
    CHAR_DELAYS,
    PUNCTUATION,
    classify_char,
    pace_characters,
)
