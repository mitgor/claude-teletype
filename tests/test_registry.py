"""Tests for ProfileRegistry (REF-02).

Covers: name lookup (incl. case-insensitivity and the get_profile error
contract), alias resolution (ibm -> ppds, juki -> juki-6100), names(),
all(), exact-over-vid-only match_vidpid priority, custom-over-builtin
merge, and the deterministic VID-only collision policy (last registered
wins + diagnostic warning).
"""

import dataclasses
import logging

import pytest

from claude_teletype.printing.profiles import BUILTIN_PROFILES, PrinterProfile
from claude_teletype.printing.registry import ProfileRegistry


@pytest.fixture
def registry() -> ProfileRegistry:
    """Registry wrapping the unmodified built-in catalog."""
    return ProfileRegistry(BUILTIN_PROFILES)


# ---------------------------------------------------------------------------
# get() — name lookup
# ---------------------------------------------------------------------------


def test_get_returns_builtin_object(registry):
    """get('escp') returns the very same object as BUILTIN_PROFILES['escp']."""
    assert registry.get("escp") is BUILTIN_PROFILES["escp"]


def test_get_is_case_insensitive_and_strips(registry):
    """get matches the get_profile contract: lowercased + stripped."""
    assert registry.get("EscP") is BUILTIN_PROFILES["escp"]
    assert registry.get(" juki ") is BUILTIN_PROFILES["juki"]


def test_get_unknown_raises_valueerror_listing_available(registry):
    """Unknown name raises ValueError naming the available profiles."""
    with pytest.raises(ValueError, match="Available:.*escp"):
        registry.get("no-such-profile")


def test_get_ibm_alias_resolves_to_ppds_sequences(registry):
    """get('ibm') resolves to the ppds alias target (same ESC sequences)."""
    ibm = registry.get("ibm")
    ppds = BUILTIN_PROFILES["ppds"]
    assert ibm.name == "ibm"
    # Identical to ppds modulo name/description (built via dataclasses.replace)
    assert dataclasses.replace(
        ibm, name=ppds.name, description=ppds.description
    ) == ppds


def test_get_juki_alias_resolves_to_juki_6100_sequences(registry):
    """get('juki') resolves to the juki-6100 alias target."""
    juki = registry.get("juki")
    six = BUILTIN_PROFILES["juki-6100"]
    assert juki.name == "juki"
    assert dataclasses.replace(
        juki, name=six.name, description=six.description
    ) == six


# ---------------------------------------------------------------------------
# names() / all()
# ---------------------------------------------------------------------------


def test_names_returns_every_builtin_including_aliases(registry):
    """names() covers the whole catalog, alias entries included."""
    assert set(registry.names()) == set(BUILTIN_PROFILES)
    assert "ibm" in registry.names()
    assert "juki" in registry.names()


def test_all_returns_merged_dict(registry):
    """all() mirrors the wrapped catalog when no custom profiles exist."""
    assert registry.all() == BUILTIN_PROFILES


def test_all_returns_copy_not_internal_state(registry):
    """Mutating the all() result does not corrupt the registry."""
    snapshot = registry.all()
    snapshot.pop("escp")
    assert registry.get("escp") is BUILTIN_PROFILES["escp"]


# ---------------------------------------------------------------------------
# match_vidpid()
# ---------------------------------------------------------------------------


def test_match_vidpid_exact_match(registry):
    """Exact (vid, pid) entry resolves: citizen-cts2000 is 0x2730:0x2002."""
    match = registry.match_vidpid(0x2730, 0x2002)
    assert match is not None
    assert match.name == "citizen-cts2000"


def test_match_vidpid_vid_only_fallback(registry):
    """No exact entry, but a vid-only entry exists: any HP product -> pcl."""
    match = registry.match_vidpid(0x03F0, 0x9999)
    assert match is not None
    assert match.name == "pcl"


def test_match_vidpid_no_match_returns_none(registry):
    """Neither exact nor vid-only entry -> None."""
    assert registry.match_vidpid(0x1234, 0x5678) is None


def test_match_vidpid_exact_beats_vid_only():
    """Exact-PID priority: a custom exact entry beats escp's vid-only claim."""
    custom = {
        "epson-exact": PrinterProfile(
            name="epson-exact",
            usb_vendor_id=0x04B8,  # same vendor as escp's vid-only entry
            usb_product_id=0x0005,
        )
    }
    registry = ProfileRegistry(BUILTIN_PROFILES, custom)
    exact = registry.match_vidpid(0x04B8, 0x0005)
    assert exact is not None
    assert exact.name == "epson-exact"
    # A different Epson product still falls back to the vid-only escp entry
    fallback = registry.match_vidpid(0x04B8, 0xBEEF)
    assert fallback is not None
    assert fallback.name == "escp"


# ---------------------------------------------------------------------------
# Custom merge — custom overrides built-in
# ---------------------------------------------------------------------------


def test_custom_profile_overrides_builtin_by_name():
    """Custom dict entry shadows a built-in of the same name."""
    custom_escp = PrinterProfile(name="escp", description="my override")
    registry = ProfileRegistry(BUILTIN_PROFILES, {"escp": custom_escp})
    assert registry.get("escp") is custom_escp
    assert registry.all()["escp"] is custom_escp


def test_custom_profile_added_alongside_builtins():
    """A new custom name is resolvable and listed without disturbing built-ins."""
    custom = PrinterProfile(name="my-printer")
    registry = ProfileRegistry(BUILTIN_PROFILES, {"my-printer": custom})
    assert registry.get("my-printer") is custom
    assert "my-printer" in registry.names()
    assert registry.get("escp") is BUILTIN_PROFILES["escp"]


# ---------------------------------------------------------------------------
# Case-preserved keys, case-insensitive get() (WR-03 / FLOW-02)
# ---------------------------------------------------------------------------


def test_uppercase_custom_key_reachable_any_casing():
    """An uppercase custom TOML profile resolves via get() with any casing."""
    custom = PrinterProfile(name="MyPrinter")
    registry = ProfileRegistry(BUILTIN_PROFILES, {"MyPrinter": custom})
    assert registry.get("MyPrinter") is custom
    assert registry.get("myprinter") is custom
    assert registry.get("MYPRINTER") is custom
    assert registry.get("  MyPrinter ") is custom


def test_names_preserves_original_casing():
    """names() lists the case-preserved key, not a lowercased copy."""
    custom = PrinterProfile(name="MyPrinter")
    registry = ProfileRegistry(BUILTIN_PROFILES, {"MyPrinter": custom})
    assert "MyPrinter" in registry.names()
    assert "myprinter" not in registry.names()


def test_get_unknown_still_raises_with_available_names():
    """Unknown name still raises ValueError listing available names."""
    registry = ProfileRegistry(BUILTIN_PROFILES, {"MyPrinter": PrinterProfile(name="MyPrinter")})
    with pytest.raises(ValueError, match="Available:.*MyPrinter"):
        registry.get("nope")


# ---------------------------------------------------------------------------
# VID-only collision policy — last registered wins, diagnostic logged
# ---------------------------------------------------------------------------


def test_vid_only_collision_last_registered_wins_and_warns(caplog):
    """Two vid-only claims on the same VID: deterministic last-wins + warning.

    Custom profiles register after built-ins, so a custom vid-only claim on
    an already-claimed VID wins (consistent with the name-merge direction),
    and the ambiguity is surfaced via a logged diagnostic — never silently.
    """
    colliding = PrinterProfile(
        name="other-hp",
        usb_vendor_id=0x03F0,  # pcl already claims this VID with no PID
    )
    with caplog.at_level(logging.WARNING, logger="claude_teletype.printing.registry"):
        registry = ProfileRegistry(BUILTIN_PROFILES, {"other-hp": colliding})

    match = registry.match_vidpid(0x03F0, 0x1111)
    assert match is not None
    assert match.name == "other-hp"  # last registered wins
    assert any("VID collision" in rec.getMessage() for rec in caplog.records)


def test_builtin_catalog_has_no_vid_only_collisions(caplog):
    """Wrapping BUILTIN_PROFILES alone must not log collision diagnostics."""
    with caplog.at_level(logging.WARNING, logger="claude_teletype.printing.registry"):
        ProfileRegistry(BUILTIN_PROFILES)
    assert not caplog.records
