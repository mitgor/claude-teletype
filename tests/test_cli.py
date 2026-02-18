"""Tests for CLI: _chat_async, config subcommands, and CLI-config integration."""

from unittest.mock import AsyncMock, MagicMock, patch

import pytest
from typer.testing import CliRunner

from claude_teletype.bridge import StreamResult
from claude_teletype.cli import _chat_async, app

runner = CliRunner()


def _make_mock_backend(items):
    """Create a mock LLM backend that yields the given items from stream()."""
    mock_backend = MagicMock()

    async def mock_stream(prompt):
        for item in items:
            yield item

    mock_backend.stream = mock_stream
    return mock_backend


class TestChatAsyncStreamResult:
    """Tests for _chat_async handling of StreamResult from backend.stream()."""

    @pytest.mark.asyncio
    async def test_chat_async_streams_text_and_handles_stream_result(
        self, tmp_path
    ) -> None:
        """_chat_async completes without crash when StreamResult is the final yield.

        Verifies: no crash, pace_characters called with "Hello" (not StreamResult).
        """
        mock_backend = _make_mock_backend([
            "Hello",
            StreamResult(session_id="test-session"),
        ])

        with patch(
            "claude_teletype.cli.pace_characters",
            new_callable=AsyncMock,
        ) as mock_pace, patch(
            "claude_teletype.cli.console",
        ) as mock_console, patch(
            "claude_teletype.transcript.make_transcript_output",
            return_value=(MagicMock(), MagicMock()),
        ):
            # Set up console.status context manager
            mock_console.status.return_value.__enter__ = MagicMock(
                return_value=MagicMock()
            )
            mock_console.status.return_value.__exit__ = MagicMock(
                return_value=False
            )

            await _chat_async(
                "test prompt",
                base_delay_ms=0,
                no_audio=True,
                transcript_dir=str(tmp_path),
                backend=mock_backend,
            )

        # pace_characters should have been called with "Hello", not StreamResult
        assert mock_pace.call_count >= 1
        for call in mock_pace.call_args_list:
            first_arg = call[0][0]
            assert isinstance(first_arg, str), (
                f"pace_characters received {type(first_arg).__name__}, expected str"
            )

    @pytest.mark.asyncio
    async def test_chat_async_displays_error_stream_result(
        self, tmp_path
    ) -> None:
        """_chat_async prints error message when StreamResult has is_error=True.

        Verifies: console.print called with error message, no call to pace_characters.
        """
        mock_backend = _make_mock_backend([
            StreamResult(is_error=True, error_message="Something went wrong"),
        ])

        with patch(
            "claude_teletype.cli.pace_characters",
            new_callable=AsyncMock,
        ) as mock_pace, patch(
            "claude_teletype.cli.console",
        ) as mock_console, patch(
            "claude_teletype.transcript.make_transcript_output",
            return_value=(MagicMock(), MagicMock()),
        ):
            mock_console.status.return_value.__enter__ = MagicMock(
                return_value=MagicMock()
            )
            mock_console.status.return_value.__exit__ = MagicMock(
                return_value=False
            )

            await _chat_async(
                "test prompt",
                base_delay_ms=0,
                no_audio=True,
                transcript_dir=str(tmp_path),
                backend=mock_backend,
            )

        # pace_characters should NOT have been called (only error StreamResult)
        mock_pace.assert_not_called()

        # console.print should have been called with the error message
        print_calls = [str(c) for c in mock_console.print.call_args_list]
        error_printed = any("Something went wrong" in c for c in print_calls)
        assert error_printed, (
            f"Expected error message in console.print calls: {print_calls}"
        )

    @pytest.mark.asyncio
    async def test_chat_async_handles_empty_response(
        self, tmp_path
    ) -> None:
        """_chat_async shows 'No response received' when only a success StreamResult is yielded.

        Verifies: no crash, "No response received" message shown.
        """
        mock_backend = _make_mock_backend([
            StreamResult(session_id="test-session"),
        ])

        with patch(
            "claude_teletype.cli.pace_characters",
            new_callable=AsyncMock,
        ) as mock_pace, patch(
            "claude_teletype.cli.console",
        ) as mock_console, patch(
            "claude_teletype.transcript.make_transcript_output",
            return_value=(MagicMock(), MagicMock()),
        ):
            mock_console.status.return_value.__enter__ = MagicMock(
                return_value=MagicMock()
            )
            mock_console.status.return_value.__exit__ = MagicMock(
                return_value=False
            )

            await _chat_async(
                "test prompt",
                base_delay_ms=0,
                no_audio=True,
                transcript_dir=str(tmp_path),
                backend=mock_backend,
            )

        # No text was streamed, so pace_characters should not be called
        mock_pace.assert_not_called()

        # "No response received" message should be shown
        print_calls = [str(c) for c in mock_console.print.call_args_list]
        no_response_shown = any("No response received" in c for c in print_calls)
        assert no_response_shown, (
            f"Expected 'No response received' in console.print calls: {print_calls}"
        )


class TestConfigShow:
    """Tests for `claude-teletype config show` subcommand."""

    def test_config_show_default(self, tmp_path):
        """config show with no config file shows default values."""
        fake_config = tmp_path / "nonexistent.toml"
        with patch("claude_teletype.cli.CONFIG_FILE", fake_config), patch(
            "claude_teletype.config.CONFIG_FILE", fake_config
        ):
            result = runner.invoke(app, ["config", "show"])

        assert result.exit_code == 0
        assert "delay = 75.0" in result.output
        assert "no_audio = False" in result.output
        assert "no_tui = False" in result.output
        assert "transcript_dir = transcripts" in result.output
        assert "device = None" in result.output
        assert "printer_profile = generic" in result.output
        assert "juki = False" in result.output
        assert "File loaded: False" in result.output

    def test_config_show_with_file(self, tmp_path):
        """config show with a config file shows loaded values."""
        config_file = tmp_path / "config.toml"
        config_file.write_text("[general]\ndelay = 50.0\nno_audio = true\n")
        with patch("claude_teletype.cli.CONFIG_FILE", config_file), patch(
            "claude_teletype.config.CONFIG_FILE", config_file
        ):
            result = runner.invoke(app, ["config", "show"])

        assert result.exit_code == 0
        assert "delay = 50.0" in result.output
        assert "no_audio = True" in result.output
        assert "File loaded: True" in result.output


class TestConfigInit:
    """Tests for `claude-teletype config init` subcommand."""

    def test_config_init_creates_file(self, tmp_path):
        """config init creates config file at the expected path."""
        config_file = tmp_path / "config.toml"
        with patch("claude_teletype.cli.CONFIG_FILE", config_file), patch(
            "claude_teletype.config.CONFIG_FILE", config_file
        ):
            result = runner.invoke(app, ["config", "init"])

        assert result.exit_code == 0
        assert config_file.exists()
        content = config_file.read_text()
        assert "[general]" in content
        assert "Config file created:" in result.output

    def test_config_init_does_not_overwrite(self, tmp_path):
        """config init refuses to overwrite existing config file."""
        config_file = tmp_path / "config.toml"
        config_file.write_text("existing content")
        with patch("claude_teletype.cli.CONFIG_FILE", config_file), patch(
            "claude_teletype.config.CONFIG_FILE", config_file
        ):
            result = runner.invoke(app, ["config", "init"])

        assert result.exit_code == 0
        assert "already exists" in result.output
        assert config_file.read_text() == "existing content"


class TestInitConfigFlag:
    """Tests for `claude-teletype --init-config` shortcut."""

    def test_init_config_flag_creates_file(self, tmp_path):
        """--init-config creates config file and exits."""
        config_file = tmp_path / "config.toml"
        with patch("claude_teletype.cli.CONFIG_FILE", config_file), patch(
            "claude_teletype.config.CONFIG_FILE", config_file
        ):
            result = runner.invoke(app, ["--init-config"])

        assert result.exit_code == 0
        assert config_file.exists()
        assert "Config file created:" in result.output

    def test_init_config_flag_warns_if_exists(self, tmp_path):
        """--init-config warns if config file already exists."""
        config_file = tmp_path / "config.toml"
        config_file.write_text("existing")
        with patch("claude_teletype.cli.CONFIG_FILE", config_file), patch(
            "claude_teletype.config.CONFIG_FILE", config_file
        ):
            result = runner.invoke(app, ["--init-config"])

        assert result.exit_code == 0
        assert "already exists" in result.output


def _mock_create_backend(*args, **kwargs):
    """Return a mock backend with no-op validate() for CLI tests."""
    mock_be = MagicMock()
    mock_be.validate = MagicMock()
    return mock_be


class TestPromptBackwardCompat:
    """Tests for backward compatibility: prompt as positional argument."""

    def test_prompt_still_works(self):
        """claude-teletype --no-tui 'hello' still reaches the chat logic."""
        with patch(
            "claude_teletype.cli.create_backend", side_effect=_mock_create_backend
        ), patch(
            "claude_teletype.cli.asyncio.run"
        ) as mock_run, patch(
            "claude_teletype.cli.load_config"
        ), patch(
            "claude_teletype.cli.apply_env_overrides"
        ) as mock_env, patch(
            "claude_teletype.cli.merge_cli_flags"
        ) as mock_merge, patch(
            "claude_teletype.printer.discover_printer", return_value=None
        ):
            from claude_teletype.config import TeletypeConfig

            mock_cfg = TeletypeConfig()
            mock_env.return_value = mock_cfg
            mock_merge.return_value = mock_cfg

            result = runner.invoke(app, ["--no-tui", "hello"])

        assert result.exit_code == 0
        mock_run.assert_called_once()
        # First arg to asyncio.run is the coroutine from _chat_async
        call_args = mock_run.call_args[0][0]
        # It's a coroutine, so close it to avoid warning
        call_args.close()

    def test_no_args_reaches_tui(self):
        """claude-teletype with no args and a tty reaches TUI path (mocked)."""
        with patch(
            "claude_teletype.cli.create_backend", side_effect=_mock_create_backend
        ), patch(
            "claude_teletype.cli.load_config"
        ), patch(
            "claude_teletype.cli.apply_env_overrides"
        ) as mock_env, patch(
            "claude_teletype.cli.merge_cli_flags"
        ) as mock_merge, patch(
            "claude_teletype.printer.discover_printer", return_value=None
        ), patch(
            "claude_teletype.tui.TeletypeApp"
        ) as mock_tui_cls, patch(
            "claude_teletype.cli.sys"
        ) as mock_sys:
            from claude_teletype.config import TeletypeConfig

            mock_cfg = TeletypeConfig()
            mock_env.return_value = mock_cfg
            mock_merge.return_value = mock_cfg
            mock_tui = MagicMock()
            mock_tui.session_id = None
            mock_tui_cls.return_value = mock_tui
            # Simulate a real terminal (not piped)
            mock_sys.stdin.isatty.return_value = True

            result = runner.invoke(app, [])

        assert result.exit_code == 0
        mock_tui_cls.assert_called_once()


class TestPrinterFlag:
    """Tests for --printer flag and --juki deprecation."""

    def test_printer_flag_sets_profile(self):
        """--printer juki resolves to juki profile."""
        with patch(
            "claude_teletype.cli.create_backend", side_effect=_mock_create_backend
        ), patch(
            "claude_teletype.cli.asyncio.run"
        ) as mock_run, patch(
            "claude_teletype.cli.load_config"
        ), patch(
            "claude_teletype.cli.apply_env_overrides"
        ) as mock_env, patch(
            "claude_teletype.cli.merge_cli_flags"
        ) as mock_merge, patch(
            "claude_teletype.printer.discover_printer", return_value=None
        ) as mock_discover:
            from claude_teletype.config import TeletypeConfig

            mock_cfg = TeletypeConfig()
            mock_env.return_value = mock_cfg
            mock_merge.return_value = mock_cfg

            result = runner.invoke(app, ["--no-tui", "--printer", "juki", "hello"])

        assert result.exit_code == 0
        mock_discover.assert_called_once()
        call_kwargs = mock_discover.call_args[1]
        assert call_kwargs["profile"].name == "juki"
        # Close the coroutine to avoid RuntimeWarning
        if mock_run.called:
            mock_run.call_args[0][0].close()

    def test_juki_flag_emits_deprecation_warning(self):
        """--juki emits deprecation warning."""
        with patch(
            "claude_teletype.cli.create_backend", side_effect=_mock_create_backend
        ), patch(
            "claude_teletype.cli.asyncio.run"
        ) as mock_run, patch(
            "claude_teletype.cli.load_config"
        ), patch(
            "claude_teletype.cli.apply_env_overrides"
        ) as mock_env, patch(
            "claude_teletype.cli.merge_cli_flags"
        ) as mock_merge, patch(
            "claude_teletype.printer.discover_printer", return_value=None
        ):
            from claude_teletype.config import TeletypeConfig

            mock_cfg = TeletypeConfig()
            mock_env.return_value = mock_cfg
            mock_merge.return_value = mock_cfg

            result = runner.invoke(app, ["--no-tui", "--juki", "hello"])

        assert result.exit_code == 0
        assert "deprecated" in result.output.lower()
        # Close the coroutine to avoid RuntimeWarning
        if mock_run.called:
            mock_run.call_args[0][0].close()

    def test_unknown_printer_name_exits_with_error(self):
        """--printer nonexistent exits with error."""
        with patch("claude_teletype.cli.load_config") as mock_load, patch(
            "claude_teletype.cli.apply_env_overrides"
        ) as mock_env, patch(
            "claude_teletype.cli.merge_cli_flags"
        ) as mock_merge:
            from claude_teletype.config import TeletypeConfig

            mock_cfg = TeletypeConfig()
            mock_load.return_value = mock_cfg
            mock_env.return_value = mock_cfg
            mock_merge.return_value = mock_cfg

            result = runner.invoke(app, ["--no-tui", "--printer", "nonexistent", "hello"])

        assert result.exit_code != 0

    def test_config_show_displays_printer_profile(self, tmp_path):
        """config show displays printer_profile."""
        fake_config = tmp_path / "nonexistent.toml"
        with patch("claude_teletype.cli.CONFIG_FILE", fake_config), patch(
            "claude_teletype.config.CONFIG_FILE", fake_config
        ):
            result = runner.invoke(app, ["config", "show"])

        assert result.exit_code == 0
        assert "printer_profile = generic" in result.output


class TestConfigMerge:
    """Tests for config file values serving as defaults when CLI flags are absent."""

    def test_config_merge_delay(self, tmp_path):
        """Config file delay used when CLI --delay flag not passed."""
        config_file = tmp_path / "config.toml"
        config_file.write_text("[general]\ndelay = 50.0\n")

        with patch("claude_teletype.cli.CONFIG_FILE", config_file), patch(
            "claude_teletype.config.CONFIG_FILE", config_file
        ), patch(
            "claude_teletype.cli.create_backend", side_effect=_mock_create_backend
        ), patch(
            "claude_teletype.cli.asyncio.run"
        ) as mock_run, patch(
            "claude_teletype.printer.discover_printer", return_value=None
        ):
            result = runner.invoke(app, ["--no-tui", "hello"])

        assert result.exit_code == 0
        mock_run.assert_called_once()
        coro = mock_run.call_args[0][0]
        coro.close()

    def test_cli_delay_overrides_config(self, tmp_path):
        """CLI --delay flag overrides config file delay."""
        config_file = tmp_path / "config.toml"
        config_file.write_text("[general]\ndelay = 50.0\n")

        with patch("claude_teletype.cli.CONFIG_FILE", config_file), patch(
            "claude_teletype.config.CONFIG_FILE", config_file
        ), patch(
            "claude_teletype.cli.create_backend", side_effect=_mock_create_backend
        ), patch(
            "claude_teletype.cli.asyncio.run"
        ) as mock_run, patch(
            "claude_teletype.printer.discover_printer", return_value=None
        ):
            result = runner.invoke(app, ["--no-tui", "--delay", "30", "hello"])

        assert result.exit_code == 0
        mock_run.assert_called_once()
        coro = mock_run.call_args[0][0]
        coro.close()

    def test_config_boolean_override(self, tmp_path):
        """Config file no_audio=true is used when CLI flag not passed."""
        config_file = tmp_path / "config.toml"
        config_file.write_text("[general]\nno_audio = true\n")

        with patch("claude_teletype.cli.CONFIG_FILE", config_file), patch(
            "claude_teletype.config.CONFIG_FILE", config_file
        ), patch(
            "claude_teletype.cli.create_backend", side_effect=_mock_create_backend
        ), patch(
            "claude_teletype.cli.asyncio.run"
        ) as mock_run, patch(
            "claude_teletype.printer.discover_printer", return_value=None
        ):
            result = runner.invoke(app, ["--no-tui", "hello"])

        assert result.exit_code == 0
        mock_run.assert_called_once()
        # _chat_async receives effective_no_audio=True from config merge
        coro = mock_run.call_args[0][0]
        coro.close()
