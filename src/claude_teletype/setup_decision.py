"""Explicit startup setup decision (REF-04).

``discovery=None`` used to carry three different meanings into
``TeletypeApp`` ("--no-tui, no screen", "--device override, skip setup",
and "saved printer matched, skip setup"), collapsed against the one
truthy case ("show the setup screen"). This enum names each case so the
skip reasons are distinguishable and ``discovery`` carries a
DiscoveryResult only when the setup screen will actually consume it.

Lives in its own stdlib-only module (not tui.py) so cli.py's --no-tui
path can import it without pulling in textual.
"""

from __future__ import annotations

import enum


class SetupDecision(enum.Enum):
    """Why the printer setup screen will or will not show at startup."""

    SHOW_SETUP = "show-setup"  # discovery ran; setup screen picks the printer
    SKIP_NO_TUI = "skip-no-tui"  # --no-tui / piped stdin: no screen exists
    SKIP_DEVICE_OVERRIDE = "skip-device-override"  # --device: user chose directly
    SKIP_SAVED_MATCH = "skip-saved-match"  # saved printer reconnected (CFG-02)
