"""Tests for CLI: _chat_async, config subcommands, and CLI-config integration."""

from unittest.mock import AsyncMock, MagicMock, patch

import pytest
from typer.testing import CliRunner

from claude_teletype.cli import _chat_async, app

# Reuse NDJSON fixture constants from test_bridge.py
from tests.test_bridge import (
    RESULT_MESSAGE_ERROR,
    RESULT_MESSAGE_FULL,
    SYSTEM_INIT,
    TEXT_DELTA_HELLO,
)

runner = CliRunner()


def _make_mock_stream(ndjson_lines: list[bytes]):
    """Build a mock subprocess that yields the given NDJSON lines.

    Returns a mock_proc suitable for patching create_subprocess_exec.
    """
    mock_stdout = MagicMock()
    line_iter = iter(ndjson_lines)
    mock_stdout.readline = AsyncMock(side_effect=lambda: next(line_iter))

    mock_proc = MagicMock()
    mock_proc.stdout = mock_stdout
    mock_proc.wait = AsyncMock(return_value=0)
    mock_proc.terminate = MagicMock()
    return mock_proc


class TestChatAsyncStreamResult:
    """Tests for _chat_async handling of StreamResult from stream_claude_response."""

    @pytest.mark.asyncio
    async def test_chat_async_streams_text_and_handles_stream_result(
        self, tmp_path
    ) -> None:
        """_chat_async completes without crash when StreamResult is the final yield.

        Verifies: no crash, pace_characters called with "Hello" (not StreamResult).
        """
        mock_proc = _make_mock_stream([
            SYSTEM_INIT + b"\n",
            TEXT_DELTA_HELLO + b"\n",
            RESULT_MESSAGE_FULL + b"\n",
            b"",  # EOF
        ])

        with patch(
            "claude_teletype.bridge.asyncio.create_subprocess_exec",
            new_callable=AsyncMock,
            return_value=mock_proc,
        ), patch(
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
        mock_proc = _make_mock_stream([
            RESULT_MESSAGE_ERROR + b"\n",
            b"",  # EOF
        ])

        with patch(
            "claude_teletype.bridge.asyncio.create_subprocess_exec",
            new_callable=AsyncMock,
            return_value=mock_proc,
        ), patch(
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
        # Only a success StreamResult, no text chunks
        mock_proc = _make_mock_stream([
            SYSTEM_INIT + b"\n",
            RESULT_MESSAGE_FULL + b"\n",
            b"",  # EOF
        ])

        with patch(
            "claude_teletype.bridge.asyncio.create_subprocess_exec",
            new_callable=AsyncMock,
            return_value=mock_proc,
        ), patch(
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


class TestPromptBackwardCompat:
    """Tests for backward compatibility: prompt as positional argument."""

    def test_prompt_still_works(self):
        """claude-teletype --no-tui 'hello' still reaches the chat logic."""
        with patch("claude_teletype.cli.check_claude_installed"), patch(
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
        with patch("claude_teletype.cli.check_claude_installed"), patch(
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


class TestConfigMerge:
    """Tests for config file values serving as defaults when CLI flags are absent."""

    def test_config_merge_delay(self, tmp_path):
        """Config file delay used when CLI --delay flag not passed."""
        config_file = tmp_path / "config.toml"
        config_file.write_text("[general]\ndelay = 50.0\n")

        with patch("claude_teletype.cli.CONFIG_FILE", config_file), patch(
            "claude_teletype.config.CONFIG_FILE", config_file
        ), patch("claude_teletype.cli.check_claude_installed"), patch(
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
        ), patch("claude_teletype.cli.check_claude_installed"), patch(
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
        ), patch("claude_teletype.cli.check_claude_installed"), patch(
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
