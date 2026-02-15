"""Tests for the audio bell output module."""

import sys
from unittest.mock import patch

from claude_teletype.audio import make_bell_output


def test_make_bell_output_returns_callable():
    """make_bell_output() returns a callable."""
    result = make_bell_output()
    assert callable(result)


def test_bell_output_accepts_non_newline_chars():
    """Bell output callable accepts non-newline characters without raising."""
    bell = make_bell_output()
    for char in ["a", "b", " ", "Z", "1", "\t"]:
        bell(char)  # should not raise


def test_bell_output_accepts_newline():
    """Bell output callable accepts newline without raising."""
    bell = make_bell_output()
    bell("\n")  # should not raise (may or may not play in test env)


def test_bell_output_graceful_degradation():
    """When sounddevice is unavailable, make_bell_output returns a no-op callable."""
    # Simulate missing sounddevice by removing it from sys.modules temporarily
    saved_sd = sys.modules.pop("sounddevice", None)
    saved_np = sys.modules.pop("numpy", None)
    try:
        with patch.dict(sys.modules, {"sounddevice": None, "numpy": None}):
            result = make_bell_output()
            assert callable(result)
            # No-op callable should accept any character without raising
            result("a")
            result("\n")
    finally:
        # Restore modules
        if saved_sd is not None:
            sys.modules["sounddevice"] = saved_sd
        if saved_np is not None:
            sys.modules["numpy"] = saved_np
