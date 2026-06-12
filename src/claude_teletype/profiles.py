"""Re-export shim — profiles.py code moved to claude_teletype.printing.profiles.

Kept so existing absolute imports (`from claude_teletype.profiles import X`)
keep resolving while internal imports and tests migrate (Phase 27 Plans 02/03).
"""

from claude_teletype.printing.profiles import *  # noqa: F401,F403

# Explicit re-exports for names tests reference by attribute.
from claude_teletype.printing.profiles import (  # noqa: F401
    BUILTIN_PROFILES,
    PrinterProfile,
    auto_detect_profile,
    get_profile,
    load_custom_profiles,
    resolve_style,
)
