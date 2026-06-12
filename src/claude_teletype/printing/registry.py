"""Profile registry: single source of truth for "all profiles" (REF-02).

``ProfileRegistry`` merges built-in profiles with custom (TOML-loaded)
profiles and builds the VID:PID lookup indices ONCE at construction,
replacing the per-call-site map building that previously lived in
``profiles.auto_detect_profile`` and the duplicated
``dict(BUILTIN_PROFILES); .update(custom)`` merges in cli.py.

Index policies (deterministic, asserted in tests/test_registry.py):

- Name merge: ``{**builtins, **custom}`` — a custom profile with the same
  name as a built-in overrides the built-in.
- ``match_vidpid``: an exact ``(vid, pid)`` entry always takes priority
  over a VID-only entry for the same vendor.
- Index collisions follow registration order — the LAST profile registered
  for a given key wins. Custom profiles are registered after built-ins, so
  a custom claim on the same VID:PID overrides a built-in's (mirroring the
  name-merge direction). Built-in alias entries (``ibm``, ``juki``) share
  their target's VID:PID by construction; last-wins keeps that benign.
- An ambiguous VID-only collision (two profiles claiming the same bare VID
  with no PID) is NOT silently shadowed: the later registration still wins,
  but a diagnostic warning is logged naming both profiles, because auto-
  detect cannot distinguish the two devices (ARCHITECTURE §A).
"""

from __future__ import annotations

import logging
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from claude_teletype.printing.profiles import PrinterProfile

logger = logging.getLogger(__name__)


class ProfileRegistry:
    """Merged profile catalog with a one-time VID:PID index.

    Args:
        builtins: The built-in profile dict (``BUILTIN_PROFILES``),
            wrapped unchanged — alias entries included.
        custom: Optional custom profiles (e.g. from
            ``load_custom_profiles``). Custom overrides built-in on
            name collision.
    """

    def __init__(
        self,
        builtins: dict[str, PrinterProfile],
        custom: dict[str, PrinterProfile] | None = None,
    ) -> None:
        self._profiles: dict[str, PrinterProfile] = {
            **builtins,
            **(custom or {}),
        }
        self._exact: dict[tuple[int, int], str] = {}
        self._vid_only: dict[int, str] = {}
        self._build_index()

    def _build_index(self) -> None:
        """Build exact (vid,pid)->name and vid->name indices once.

        Later registrations win on collision (see module docstring).
        VID-only collisions additionally log a diagnostic — two profiles
        claiming the same bare VID is ambiguous for auto-detect.
        """
        for name, profile in self._profiles.items():
            vid = profile.usb_vendor_id
            if vid is None:
                continue
            pid = profile.usb_product_id
            if pid is not None:
                self._exact[(vid, pid)] = name
            else:
                if vid in self._vid_only:
                    logger.warning(
                        "Profile VID collision: %r and %r both claim "
                        "vendor id 0x%04x with no product id; "
                        "auto-detect will resolve to %r (last registered "
                        "wins). Add usb_product_id to disambiguate.",
                        self._vid_only[vid],
                        name,
                        vid,
                        name,
                    )
                self._vid_only[vid] = name

    def get(self, name: str) -> PrinterProfile:
        """Look up a profile by name (case-insensitive).

        Same contract as the legacy ``profiles.get_profile``: aliases
        (``ibm`` -> ppds sequences, ``juki`` -> juki-6100 sequences)
        resolve, and an unknown name raises ValueError listing all
        available profile names.
        """
        key = name.lower().strip()
        if key not in self._profiles:
            available = ", ".join(sorted(self._profiles))
            raise ValueError(
                f"Unknown printer profile: {name!r}. Available: {available}"
            )
        return self._profiles[key]

    def names(self) -> list[str]:
        """Every resolvable profile name, aliases included."""
        return list(self._profiles)

    def match_vidpid(self, vid: int, pid: int) -> PrinterProfile | None:
        """Match a USB device's VID:PID to a profile.

        Exact ``(vid, pid)`` match takes priority over a VID-only match
        (a profile with ``usb_vendor_id`` set but no ``usb_product_id``).
        Returns None when neither index has an entry.
        """
        name = self._exact.get((vid, pid))
        if name is None:
            name = self._vid_only.get(vid)
        if name is None:
            return None
        return self._profiles[name]

    def all(self) -> dict[str, PrinterProfile]:
        """The merged name->profile dict (shallow copy; safe to mutate)."""
        return dict(self._profiles)
