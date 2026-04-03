"""Tests for config persistence: saved printer fields and atomic writes."""

from __future__ import annotations

import os
import tomllib
from pathlib import Path
from unittest.mock import patch

import pytest

from claude_teletype.config import (
    DEFAULT_CONFIG_TEMPLATE,
    TeletypeConfig,
    load_config,
    save_config,
)


class TestSavedPrinterFields:
    """TeletypeConfig has saved_printer_type/id/profile with empty defaults."""

    def test_saved_printer_type_default(self):
        cfg = TeletypeConfig()
        assert cfg.saved_printer_type == ""

    def test_saved_printer_id_default(self):
        cfg = TeletypeConfig()
        assert cfg.saved_printer_id == ""

    def test_saved_printer_profile_default(self):
        cfg = TeletypeConfig()
        assert cfg.saved_printer_profile == ""


class TestSavedPrinterToml:
    """save_config writes [printer.saved] and load_config round-trips it."""

    def test_save_writes_printer_saved_section(self, tmp_path: Path):
        cfg = TeletypeConfig(
            saved_printer_type="usb",
            saved_printer_id="04b8:0005",
            saved_printer_profile="escp",
        )
        path = tmp_path / "config.toml"
        save_config(cfg, path)

        raw = tomllib.loads(path.read_text())
        saved = raw["printer"]["saved"]
        assert saved["type"] == "usb"
        assert saved["id"] == "04b8:0005"
        assert saved["profile"] == "escp"

    def test_round_trip_saved_fields(self, tmp_path: Path):
        cfg = TeletypeConfig(
            saved_printer_type="cups",
            saved_printer_id="HP_LaserJet",
            saved_printer_profile="pcl",
        )
        path = tmp_path / "config.toml"
        save_config(cfg, path)

        loaded = load_config(path)
        assert loaded.saved_printer_type == "cups"
        assert loaded.saved_printer_id == "HP_LaserJet"
        assert loaded.saved_printer_profile == "pcl"

    def test_no_saved_section_when_empty(self, tmp_path: Path):
        cfg = TeletypeConfig()
        path = tmp_path / "config.toml"
        save_config(cfg, path)

        raw = tomllib.loads(path.read_text())
        printer = raw.get("printer", {})
        assert "saved" not in printer


class TestAtomicSave:
    """save_config uses atomic temp file + os.replace."""

    def test_uses_os_replace(self, tmp_path: Path):
        """save_config calls os.replace (not write_text) for atomicity."""
        cfg = TeletypeConfig()
        path = tmp_path / "config.toml"

        with patch("claude_teletype.config.os.replace", wraps=os.replace) as mock_replace:
            save_config(cfg, path)
            mock_replace.assert_called_once()

    def test_original_unchanged_on_write_failure(self, tmp_path: Path):
        """If temp file write fails, the original config is untouched."""
        cfg = TeletypeConfig(delay=99.0)
        path = tmp_path / "config.toml"
        save_config(cfg, path)
        original_content = path.read_text()

        # Force os.write to fail after fd is opened
        cfg2 = TeletypeConfig(delay=42.0)
        with patch("claude_teletype.config.os.write", side_effect=OSError("disk full")):
            with pytest.raises(OSError, match="disk full"):
                save_config(cfg2, path)

        assert path.read_text() == original_content


class TestDefaultTemplate:
    """DEFAULT_CONFIG_TEMPLATE includes commented [printer.saved] section."""

    def test_template_has_printer_saved_comment(self):
        assert "# [printer.saved]" in DEFAULT_CONFIG_TEMPLATE


class TestEnvSkip:
    """Saved printer fields are not env-overridable."""

    def test_saved_fields_not_env_overridable(self, tmp_path: Path):
        from claude_teletype.config import apply_env_overrides

        cfg = TeletypeConfig()
        env = {
            "CLAUDE_TELETYPE_SAVED_PRINTER_TYPE": "usb",
            "CLAUDE_TELETYPE_SAVED_PRINTER_ID": "1234:5678",
            "CLAUDE_TELETYPE_SAVED_PRINTER_PROFILE": "juki",
        }
        with patch.dict(os.environ, env):
            result = apply_env_overrides(cfg)

        assert result.saved_printer_type == ""
        assert result.saved_printer_id == ""
        assert result.saved_printer_profile == ""
