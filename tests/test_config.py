"""Tests for claude_teletype.config module.

Covers TeletypeConfig dataclass defaults, TOML loading, env var overrides,
CLI flag merging, and default config file generation.
"""

import tomllib

from claude_teletype.config import (
    CONFIG_FILE,
    TeletypeConfig,
    apply_env_overrides,
    load_config,
    merge_cli_flags,
    resolve_sources,
    write_default_config,
)

# --- Test 1: TeletypeConfig defaults ---


class TestTeletypeConfigDefaults:
    def test_delay_default(self):
        assert TeletypeConfig().delay == 75.0

    def test_no_audio_default(self):
        assert TeletypeConfig().no_audio is False

    def test_no_tui_default(self):
        assert TeletypeConfig().no_tui is False

    def test_transcript_dir_default(self):
        assert TeletypeConfig().transcript_dir == "transcripts"

    def test_device_default(self):
        assert TeletypeConfig().device is None

    def test_juki_default(self):
        assert TeletypeConfig().juki is False


# --- Test 2: load_config returns defaults when file does not exist ---


class TestLoadConfigMissingFile:
    def test_returns_defaults_for_nonexistent_path(self, tmp_path):
        result = load_config(tmp_path / "nonexistent" / "config.toml")
        assert result == TeletypeConfig()


# --- Test 3: load_config reads TOML sections and populates dataclass ---


class TestLoadConfigFromToml:
    def test_reads_general_and_printer_sections(self, tmp_path):
        config_file = tmp_path / "config.toml"
        config_file.write_text(
            "[general]\ndelay = 50.0\n\n[printer]\njuki = true\n",
            encoding="utf-8",
        )
        result = load_config(config_file)
        assert result.delay == 50.0
        assert result.juki is True
        # Other fields remain defaults
        assert result.no_audio is False
        assert result.device is None


# --- Test 4: load_config ignores unknown TOML keys ---


class TestLoadConfigUnknownKeys:
    def test_ignores_unknown_keys_gracefully(self, tmp_path):
        config_file = tmp_path / "config.toml"
        config_file.write_text(
            '[general]\nfuture_key = "value"\n',
            encoding="utf-8",
        )
        result = load_config(config_file)
        assert result == TeletypeConfig()


# --- Test 5: apply_env_overrides reads CLAUDE_TELETYPE_DELAY ---


class TestEnvOverrideDelay:
    def test_float_env_override(self, monkeypatch):
        monkeypatch.setenv("CLAUDE_TELETYPE_DELAY", "50")
        result = apply_env_overrides(TeletypeConfig())
        assert result.delay == 50.0


# --- Test 6: apply_env_overrides handles boolean env vars ---


class TestEnvOverrideBooleans:
    def test_true_string(self, monkeypatch):
        monkeypatch.setenv("CLAUDE_TELETYPE_NO_AUDIO", "true")
        result = apply_env_overrides(TeletypeConfig())
        assert result.no_audio is True

    def test_zero_string(self, monkeypatch):
        monkeypatch.setenv("CLAUDE_TELETYPE_NO_AUDIO", "0")
        result = apply_env_overrides(TeletypeConfig())
        assert result.no_audio is False

    def test_one_string(self, monkeypatch):
        monkeypatch.setenv("CLAUDE_TELETYPE_NO_AUDIO", "1")
        result = apply_env_overrides(TeletypeConfig())
        assert result.no_audio is True

    def test_yes_string(self, monkeypatch):
        monkeypatch.setenv("CLAUDE_TELETYPE_NO_AUDIO", "yes")
        result = apply_env_overrides(TeletypeConfig())
        assert result.no_audio is True


# --- Test 7: apply_env_overrides handles string env vars (device) ---


class TestEnvOverrideDevice:
    def test_device_string_override(self, monkeypatch):
        monkeypatch.setenv("CLAUDE_TELETYPE_DEVICE", "/dev/usb/lp0")
        result = apply_env_overrides(TeletypeConfig())
        assert result.device == "/dev/usb/lp0"


# --- Test 8: merge_cli_flags overrides only non-None values ---


class TestMergeCliFlags:
    def test_overrides_non_none(self):
        result = merge_cli_flags(TeletypeConfig(), delay=50.0, no_audio=None)
        assert result.delay == 50.0

    def test_preserves_none_values(self):
        result = merge_cli_flags(TeletypeConfig(), delay=50.0, no_audio=None)
        assert result.no_audio is False  # unchanged from default

    def test_overrides_multiple_flags(self):
        result = merge_cli_flags(TeletypeConfig(), delay=30.0, juki=True)
        assert result.delay == 30.0
        assert result.juki is True


# --- Test 9: write_default_config creates file with commented TOML template ---


class TestWriteDefaultConfig:
    def test_creates_file(self, tmp_path):
        path = tmp_path / "config.toml"
        write_default_config(path)
        assert path.exists()

    def test_contains_general_section(self, tmp_path):
        path = tmp_path / "config.toml"
        write_default_config(path)
        content = path.read_text(encoding="utf-8")
        assert "[general]" in content

    def test_contains_printer_section(self, tmp_path):
        path = tmp_path / "config.toml"
        write_default_config(path)
        content = path.read_text(encoding="utf-8")
        assert "[printer]" in content

    def test_contains_delay_default(self, tmp_path):
        path = tmp_path / "config.toml"
        write_default_config(path)
        content = path.read_text(encoding="utf-8")
        assert "delay = 75.0" in content

    def test_is_valid_toml(self, tmp_path):
        path = tmp_path / "config.toml"
        write_default_config(path)
        with open(path, "rb") as f:
            data = tomllib.load(f)
        # Should parse without error and contain expected keys
        assert "general" in data or "delay" in data.get("general", {})

    def test_creates_parent_directories(self, tmp_path):
        path = tmp_path / "nested" / "dir" / "config.toml"
        write_default_config(path)
        assert path.exists()


# --- Test 10: CONFIG_FILE uses platformdirs ---


# --- Test 10: CONFIG_FILE uses platformdirs ---


class TestPrinterProfileConfig:
    """Tests for printer_profile field in TeletypeConfig."""

    def test_printer_profile_default_is_generic(self):
        """TeletypeConfig.printer_profile defaults to 'generic'."""
        assert TeletypeConfig().printer_profile == "generic"

    def test_load_config_reads_printer_profile(self, tmp_path):
        """load_config reads printer_profile from TOML [printer] section."""
        config_file = tmp_path / "config.toml"
        config_file.write_text(
            '[printer]\nprofile = "juki"\n', encoding="utf-8"
        )
        result = load_config(config_file)
        assert result.printer_profile == "juki"

    def test_load_config_extracts_custom_profiles(self, tmp_path):
        """load_config extracts custom_profiles from [printer.profiles.*] tables."""
        config_file = tmp_path / "config.toml"
        config_file.write_text(
            '[printer]\nprofile = "my-printer"\n\n'
            '[printer.profiles.my-printer]\n'
            'description = "My custom printer"\n'
            'init = "1b40"\n'
            'crlf = true\n',
            encoding="utf-8",
        )
        result = load_config(config_file)
        assert "my-printer" in result.custom_profiles
        assert result.custom_profiles["my-printer"]["init"] == "1b40"
        assert result.custom_profiles["my-printer"]["crlf"] is True

    def test_env_override_printer_profile(self, monkeypatch):
        """CLAUDE_TELETYPE_PRINTER_PROFILE env var overrides config."""
        monkeypatch.setenv("CLAUDE_TELETYPE_PRINTER_PROFILE", "escp")
        result = apply_env_overrides(TeletypeConfig())
        assert result.printer_profile == "escp"

    def test_custom_profiles_default_empty(self):
        """TeletypeConfig.custom_profiles defaults to empty dict."""
        assert TeletypeConfig().custom_profiles == {}

    def test_load_config_no_profiles_section(self, tmp_path):
        """load_config without [printer.profiles] section returns empty custom_profiles."""
        config_file = tmp_path / "config.toml"
        config_file.write_text(
            '[printer]\nprofile = "juki"\n', encoding="utf-8"
        )
        result = load_config(config_file)
        assert result.custom_profiles == {}


class TestResolveSources:
    """Tests for resolve_sources() — determines origin of each config value."""

    def test_all_defaults_when_no_file(self, tmp_path):
        """With no config file, all sources should be 'default'."""
        sources = resolve_sources(tmp_path / "nonexistent" / "config.toml")
        for field_name, source in sources.items():
            assert source == "default", f"{field_name} should be default, got {source}"

    def test_file_source_when_toml_overrides(self, tmp_path):
        """File overrides are tagged with 'file (path)'."""
        config_file = tmp_path / "config.toml"
        config_file.write_text(
            "[general]\ndelay = 50.0\n", encoding="utf-8"
        )
        sources = resolve_sources(config_file)
        assert sources["delay"] == f"file ({config_file})"
        assert sources["no_audio"] == "default"

    def test_env_source_overrides_file(self, tmp_path, monkeypatch):
        """Env var wins over file config in source detection."""
        config_file = tmp_path / "config.toml"
        config_file.write_text(
            "[general]\ndelay = 50.0\n", encoding="utf-8"
        )
        monkeypatch.setenv("CLAUDE_TELETYPE_DELAY", "60")
        sources = resolve_sources(config_file)
        assert sources["delay"] == "env (CLAUDE_TELETYPE_DELAY)"

    def test_env_source_without_file(self, tmp_path, monkeypatch):
        """Env var detected even without a config file."""
        monkeypatch.setenv("CLAUDE_TELETYPE_NO_AUDIO", "true")
        sources = resolve_sources(tmp_path / "nonexistent.toml")
        assert sources["no_audio"] == "env (CLAUDE_TELETYPE_NO_AUDIO)"

    def test_custom_profiles_excluded(self, tmp_path):
        """'custom_profiles' key does not appear in resolve_sources output."""
        sources = resolve_sources(tmp_path / "nonexistent.toml")
        assert "custom_profiles" not in sources


class TestConfigFilePath:
    def test_path_contains_app_name(self):
        assert "claude-teletype" in str(CONFIG_FILE)
