"""Tests for `claude-teletype print` subcommand (CLI-01..CLI-04).

The print subcommand renders a markdown file in one shot through
MarkdownRenderer + WordWrapper + ProfilePrinterDriver. Phase 25-01 owns the
explicit-path entrypoint; Phase 25-02 adds the no-path picker-mode launcher
that pushes Phase 24's FilePickerScreen and routes the result through
``_render_markdown_to_driver``.

These tests use Typer's CliRunner (same pattern as tests/test_cli.py).

Patch-target convention: ``_render_markdown_to_driver`` imports its narrow
deps (``MarkdownRenderer``, ``WordWrapper``, ``discover_printer``) LOCALLY
inside the function body. Patches must therefore target the SOURCE modules
(e.g., ``claude_teletype.printer.discover_printer``), NOT
``claude_teletype.cli.discover_printer``. The picker factory
``_make_markdown_picker_app`` is patched at ``claude_teletype.cli.``
because the dispatch in ``print_md`` resolves it through the cli module
namespace.
"""

from unittest.mock import MagicMock, patch

from typer.testing import CliRunner

from claude_teletype.cli import app

runner = CliRunner()


def _write_md(tmp_path, name="doc.md", content="# Hello\n\nworld\n"):
    """Helper: write a markdown file under tmp_path and return the Path."""
    p = tmp_path / name
    p.write_text(content)
    return p


def _make_mock_driver(*, with_end_response: bool = True):
    """Mock driver with the methods _render_markdown_to_driver actually calls.

    spec= keeps ``getattr(driver, 'end_response', None)`` honest: when
    with_end_response=False, the helper must skip the end_response call.
    """
    methods = ["write", "write_bytes", "close", "is_connected"]
    if with_end_response:
        methods.append("end_response")
    return MagicMock(spec=methods)


# ---------------------------------------------------------------------------
# CLI-01: explicit path
# ---------------------------------------------------------------------------


class TestPrintCli01ExplicitPath:
    """`claude-teletype print <path>` reads + renders + exits 0 (CLI-01)."""

    def test_print_with_valid_path_exits_zero(self, tmp_path):
        md = _write_md(tmp_path)
        with patch("claude_teletype.printer.discover_printer") as mock_disc:
            mock_disc.return_value = _make_mock_driver()
            result = runner.invoke(app, ["print", str(md)])
        assert result.exit_code == 0, result.output

    def test_print_calls_markdown_renderer_with_file_text(self, tmp_path):
        md = _write_md(tmp_path, content="# Test\n\nbody\n")
        with patch("claude_teletype.printer.discover_printer") as mock_disc, \
                patch(
                    "claude_teletype.markdown.MarkdownRenderer",
                ) as mock_renderer_cls:
            mock_disc.return_value = _make_mock_driver()
            mock_renderer = MagicMock()
            mock_renderer_cls.return_value = mock_renderer
            result = runner.invoke(app, ["print", str(md)])

        assert result.exit_code == 0, result.output
        mock_renderer_cls.assert_called_once()
        mock_renderer.render.assert_called_once_with("# Test\n\nbody\n")

    def test_print_calls_wrapper_flush_after_render(self, tmp_path):
        md = _write_md(tmp_path)
        parent = MagicMock()
        with patch("claude_teletype.printer.discover_printer") as mock_disc, \
                patch(
                    "claude_teletype.wordwrap.WordWrapper",
                ) as mock_wrap_cls, \
                patch(
                    "claude_teletype.markdown.MarkdownRenderer",
                ) as mock_renderer_cls:
            mock_disc.return_value = _make_mock_driver()
            mock_wrap = MagicMock()
            mock_wrap_cls.return_value = mock_wrap
            mock_renderer = MagicMock()
            mock_renderer_cls.return_value = mock_renderer
            parent.attach_mock(mock_renderer, "renderer")
            parent.attach_mock(mock_wrap, "wrapper")
            result = runner.invoke(app, ["print", str(md)])

        assert result.exit_code == 0, result.output
        mock_wrap.flush.assert_called_once()
        # Order: render must happen before flush
        names = [str(c) for c in parent.mock_calls]
        render_idx = next(i for i, n in enumerate(names) if "renderer.render" in n)
        flush_idx = next(i for i, n in enumerate(names) if "wrapper.flush" in n)
        assert render_idx < flush_idx, (
            f"flush must follow render; got: {names}"
        )

    def test_print_closes_driver_in_finally_on_render_error(self, tmp_path):
        md = _write_md(tmp_path)
        with patch("claude_teletype.printer.discover_printer") as mock_disc, \
                patch(
                    "claude_teletype.markdown.MarkdownRenderer",
                ) as mock_renderer_cls:
            driver = _make_mock_driver()
            mock_disc.return_value = driver
            mock_renderer = MagicMock()
            mock_renderer.render.side_effect = RuntimeError("boom")
            mock_renderer_cls.return_value = mock_renderer
            result = runner.invoke(app, ["print", str(md)])

        # The exception propagates (CliRunner sees nonzero exit), but close()
        # MUST still have been called via finally.
        assert result.exit_code != 0
        driver.close.assert_called_once()


# ---------------------------------------------------------------------------
# CLI-04: path validation
# ---------------------------------------------------------------------------


class TestPrintCli04PathValidation:
    """Bad path -> non-zero exit + clear error, no driver opened (CLI-04)."""

    def test_print_missing_path_exits_nonzero(self, tmp_path):
        result = runner.invoke(app, ["print", str(tmp_path / "no_such.md")])
        assert result.exit_code != 0

    def test_print_missing_path_emits_clear_error(self, tmp_path):
        result = runner.invoke(app, ["print", str(tmp_path / "no_such.md")])
        # CliRunner mixes stdout+stderr by default; we accept either.
        combined = (result.output + (result.stderr or "")).lower() \
            if hasattr(result, "stderr") else result.output.lower()
        assert "not found" in combined or "does not exist" in combined, (
            f"Expected 'not found' in output: {combined}"
        )

    def test_print_directory_exits_nonzero(self, tmp_path):
        # tmp_path is a directory.
        result = runner.invoke(app, ["print", str(tmp_path)])
        assert result.exit_code != 0

    def test_print_directory_emits_regular_file_error(self, tmp_path):
        result = runner.invoke(app, ["print", str(tmp_path)])
        combined = result.output.lower()
        assert (
            "not a regular file" in combined
            or "is a directory" in combined
        ), f"Expected regular-file error: {combined}"

    def test_print_does_not_open_driver_on_bad_path(self, tmp_path):
        with patch("claude_teletype.printer.discover_printer") as mock_disc:
            result = runner.invoke(
                app, ["print", str(tmp_path / "no.md")],
            )
        assert result.exit_code != 0
        mock_disc.assert_not_called()


# ---------------------------------------------------------------------------
# CLI-03: config layer chain (TOML < env < CLI flag)
# ---------------------------------------------------------------------------


class TestPrintCli03ConfigChain:
    """`print` honors TOML, env, and CLI flag layers (CLI-03)."""

    def test_print_honors_printer_flag(self, tmp_path):
        md = _write_md(tmp_path)
        with patch("claude_teletype.printer.discover_printer") as mock_disc, \
                patch(
                    "claude_teletype.markdown.MarkdownRenderer",
                ) as mock_renderer_cls:
            mock_disc.return_value = _make_mock_driver()
            mock_renderer_cls.return_value = MagicMock()
            result = runner.invoke(
                app, ["print", "--printer", "escp", str(md)],
            )

        assert result.exit_code == 0, result.output
        # MarkdownRenderer received the escp profile
        call_kwargs = mock_renderer_cls.call_args.kwargs
        assert call_kwargs["profile"] is not None
        assert call_kwargs["profile"].name == "escp"
        # discover_printer also received the same profile
        disc_kwargs = mock_disc.call_args.kwargs
        assert disc_kwargs["profile"].name == "escp"

    def test_print_honors_device_flag(self, tmp_path):
        md = _write_md(tmp_path)
        with patch("claude_teletype.printer.discover_printer") as mock_disc, \
                patch("claude_teletype.markdown.MarkdownRenderer") as mock_render:
            mock_disc.return_value = _make_mock_driver()
            mock_render.return_value = MagicMock()
            result = runner.invoke(
                app, ["print", "--device", "/tmp/fake_lp", str(md)],
            )

        assert result.exit_code == 0, result.output
        disc_kwargs = mock_disc.call_args.kwargs
        assert disc_kwargs["device_override"] == "/tmp/fake_lp"

    def test_print_honors_toml_printer_profile(self, tmp_path):
        md = _write_md(tmp_path)
        config_file = tmp_path / "config.toml"
        config_file.write_text("[printer]\nprinter_profile = \"escp\"\n")
        with patch("claude_teletype.cli.CONFIG_FILE", config_file), \
                patch("claude_teletype.config.CONFIG_FILE", config_file), \
                patch(
                    "claude_teletype.printer.discover_printer",
                ) as mock_disc, \
                patch(
                    "claude_teletype.markdown.MarkdownRenderer",
                ) as mock_renderer_cls:
            mock_disc.return_value = _make_mock_driver()
            mock_renderer_cls.return_value = MagicMock()
            result = runner.invoke(app, ["print", str(md)])

        assert result.exit_code == 0, result.output
        call_kwargs = mock_renderer_cls.call_args.kwargs
        assert call_kwargs["profile"] is not None
        assert call_kwargs["profile"].name == "escp"

    def test_print_unknown_profile_exits_nonzero_and_lists_available(
        self, tmp_path,
    ):
        md = _write_md(tmp_path)
        result = runner.invoke(
            app,
            ["print", "--printer", "definitely_not_a_real_profile", str(md)],
        )
        assert result.exit_code != 0
        assert "Available:" in result.output

    def test_print_env_layer_applied_does_not_crash(
        self, tmp_path, monkeypatch,
    ):
        """CLAUDE_TELETYPE_DELAY env var should be picked up by
        apply_env_overrides during the print path. Phase 25 does NOT pace,
        but the env layer must still load without crashing -- proves the
        config chain runs end-to-end."""
        md = _write_md(tmp_path)
        monkeypatch.setenv("CLAUDE_TELETYPE_DELAY", "10")
        with patch("claude_teletype.printer.discover_printer") as mock_disc, \
                patch("claude_teletype.markdown.MarkdownRenderer") as mock_render:
            mock_disc.return_value = _make_mock_driver()
            mock_render.return_value = MagicMock()
            result = runner.invoke(app, ["print", str(md)])
        assert result.exit_code == 0, result.output


# ---------------------------------------------------------------------------
# Helper-level pipeline tests (direct call to _render_markdown_to_driver)
# ---------------------------------------------------------------------------


class TestPrintRenderingPipeline:
    """Direct unit tests for ``_render_markdown_to_driver`` -- locks the
    contract Plan 25-02 reuses from the picker callback."""

    def test_render_helper_call_order(self, tmp_path):
        from claude_teletype.cli import _render_markdown_to_driver
        from claude_teletype.config import TeletypeConfig

        md = _write_md(tmp_path, content="# Hi\n")
        config = TeletypeConfig()

        parent = MagicMock()
        with patch("claude_teletype.printer.discover_printer") as mock_disc, \
                patch(
                    "claude_teletype.wordwrap.WordWrapper",
                ) as mock_wrap_cls, \
                patch(
                    "claude_teletype.markdown.MarkdownRenderer",
                ) as mock_render_cls:
            mock_driver = _make_mock_driver()
            mock_disc.return_value = mock_driver
            mock_wrap = MagicMock()
            mock_wrap_cls.return_value = mock_wrap
            mock_render = MagicMock()
            mock_render_cls.return_value = mock_render
            parent.attach_mock(mock_render, "renderer")
            parent.attach_mock(mock_wrap, "wrapper")
            parent.attach_mock(mock_driver, "driver")

            rc = _render_markdown_to_driver(md, config, {}, None)

        assert rc == 0
        # Order: renderer.render -> wrapper.flush -> driver.end_response -> driver.close
        names = [str(c) for c in parent.mock_calls]
        render_idx = next(
            i for i, n in enumerate(names) if "renderer.render" in n
        )
        flush_idx = next(
            i for i, n in enumerate(names) if "wrapper.flush" in n
        )
        end_idx = next(
            i for i, n in enumerate(names) if "driver.end_response" in n
        )
        close_idx = next(
            i for i, n in enumerate(names) if "driver.close" in n
        )
        assert render_idx < flush_idx < end_idx < close_idx, (
            f"unexpected order: {names}"
        )

    def test_render_helper_skips_endresponse_when_missing(self, tmp_path):
        """Drivers without end_response (e.g. NullPrinterDriver,
        plain CupsPrinterDriver) must not crash the helper."""
        from claude_teletype.cli import _render_markdown_to_driver
        from claude_teletype.config import TeletypeConfig

        md = _write_md(tmp_path)
        config = TeletypeConfig()
        # Driver WITHOUT end_response (NullPrinterDriver-shaped)
        mock_driver = _make_mock_driver(with_end_response=False)
        with patch(
            "claude_teletype.printer.discover_printer",
            return_value=mock_driver,
        ):
            rc = _render_markdown_to_driver(md, config, {}, None)

        assert rc == 0  # no crash
        mock_driver.close.assert_called_once()
        assert not hasattr(mock_driver, "end_response") or \
            not mock_driver.end_response.called

    def test_render_helper_returns_one_on_read_error(self, tmp_path):
        """Unreadable file produces exit 1, not a crash."""
        from claude_teletype.cli import _render_markdown_to_driver
        from claude_teletype.config import TeletypeConfig

        bad_path = tmp_path / "doesnt_matter.md"
        # Don't create the file -- read_text raises FileNotFoundError
        config = TeletypeConfig()
        with patch(
            "claude_teletype.printer.discover_printer",
        ) as mock_disc:
            rc = _render_markdown_to_driver(bad_path, config, {}, None)
        assert rc == 1
        # Driver must not have been opened on read failure (read happens first)
        mock_disc.assert_not_called()


# ---------------------------------------------------------------------------
# Regression sentinel: existing main / config / diagnose still work
# ---------------------------------------------------------------------------


class TestNoRegression:
    """Adding the print subcommand must not regress the existing CLI surface."""

    def test_main_help_still_runs(self):
        result = runner.invoke(app, ["--help"])
        assert result.exit_code == 0
        # The new print command should now appear in the help listing.
        assert "print" in result.output.lower()

    def test_config_show_still_runs(self, tmp_path):
        fake_config = tmp_path / "no.toml"
        with patch("claude_teletype.cli.CONFIG_FILE", fake_config), \
                patch("claude_teletype.config.CONFIG_FILE", fake_config):
            result = runner.invoke(app, ["config", "show"])
        assert result.exit_code == 0

    def test_diagnose_command_still_registered(self):
        result = runner.invoke(app, ["diagnose", "--help"])
        assert result.exit_code == 0


# ---------------------------------------------------------------------------
# CLI-02: no-path picker mode
# ---------------------------------------------------------------------------


class TestPrintCli02PickerMode:
    """`claude-teletype print` with no path launches a minimal picker app (CLI-02).

    The dispatch path: print_md sees path=None -> calls
    _print_command_impl_picker -> resolves config + profile via the shared
    _resolve_print_context -> builds a MarkdownPickerApp via the factory ->
    runs it. The factory and its returned app are mocked here to avoid
    spinning a real terminal in CI; the picker callback's runtime behavior
    is unit-tested via direct calls below.
    """

    def test_print_no_path_invokes_picker_app(self):
        """No-path dispatch builds the picker app and calls .run() on it."""
        with patch(
            "claude_teletype.cli._make_markdown_picker_app",
        ) as mock_factory:
            mock_app = MagicMock()
            mock_app._exit_code = 0
            mock_factory.return_value = mock_app
            result = runner.invoke(app, ["print"])
        assert result.exit_code == 0, result.output
        mock_factory.assert_called_once()
        mock_app.run.assert_called_once()

    def test_print_no_path_does_not_call_render_directly(self):
        """The render helper is invoked from inside the picker callback, NOT
        from the dispatch. We mock App.run as a no-op so the callback never
        fires; render must not have been called from the dispatch path."""
        with patch(
            "claude_teletype.cli._make_markdown_picker_app",
        ) as mock_factory, patch(
            "claude_teletype.cli._render_markdown_to_driver",
        ) as mock_render:
            mock_app = MagicMock()
            mock_app._exit_code = 0
            mock_factory.return_value = mock_app
            result = runner.invoke(app, ["print"])
        assert result.exit_code == 0, result.output
        mock_render.assert_not_called()

    def test_picker_app_on_mount_pushes_filepicker(self):
        """Direct unit test: on_mount must push a FilePickerScreen."""
        from claude_teletype.cli import _make_markdown_picker_app
        from claude_teletype.config import TeletypeConfig
        from claude_teletype.file_picker_screen import FilePickerScreen

        app_inst = _make_markdown_picker_app(
            config=TeletypeConfig(),
            all_profiles={},
            resolved_profile=None,
            root=None,
        )
        with patch.object(app_inst, "push_screen") as mock_push:
            app_inst.on_mount()
        mock_push.assert_called_once()
        # First positional arg should be a FilePickerScreen instance
        pushed_screen = mock_push.call_args.args[0]
        assert isinstance(pushed_screen, FilePickerScreen)
        # Callback kwarg should be the app's _on_pick handler
        assert mock_push.call_args.kwargs.get("callback") == app_inst._on_pick

    def test_picker_callback_path_calls_render_helper(self, tmp_path):
        """Path arm: callback calls _render_markdown_to_driver and exits."""
        from claude_teletype.cli import _make_markdown_picker_app
        from claude_teletype.config import TeletypeConfig

        cfg = TeletypeConfig()
        app_inst = _make_markdown_picker_app(
            config=cfg,
            all_profiles={},
            resolved_profile=None,
            root=None,
        )
        md = tmp_path / "doc.md"
        md.write_text("# Hi\n")

        with patch(
            "claude_teletype.cli._render_markdown_to_driver",
            return_value=0,
        ) as mock_render, patch.object(app_inst, "exit") as mock_exit:
            app_inst._on_pick(md)

        mock_render.assert_called_once()
        call_args = mock_render.call_args
        # First positional arg is the path
        assert call_args.args[0] == md
        # Config + all_profiles + resolved_profile passed through (closure
        # capture from the factory).
        assert call_args.args[1] is cfg
        mock_exit.assert_called_once()
        assert app_inst._exit_code == 0

    def test_picker_callback_none_skips_render(self):
        """None arm: cancel = no render, exit 0."""
        from claude_teletype.cli import _make_markdown_picker_app
        from claude_teletype.config import TeletypeConfig

        app_inst = _make_markdown_picker_app(
            config=TeletypeConfig(),
            all_profiles={},
            resolved_profile=None,
            root=None,
        )
        with patch(
            "claude_teletype.cli._render_markdown_to_driver",
        ) as mock_render, patch.object(app_inst, "exit") as mock_exit:
            app_inst._on_pick(None)
        mock_render.assert_not_called()
        mock_exit.assert_called_once()
        assert app_inst._exit_code == 0

    def test_picker_callback_propagates_render_exit_code(self, tmp_path):
        """Render helper non-zero return propagates to _exit_code."""
        from claude_teletype.cli import _make_markdown_picker_app
        from claude_teletype.config import TeletypeConfig

        app_inst = _make_markdown_picker_app(
            config=TeletypeConfig(),
            all_profiles={},
            resolved_profile=None,
            root=None,
        )
        md = tmp_path / "doc.md"
        md.write_text("text")
        with patch(
            "claude_teletype.cli._render_markdown_to_driver",
            return_value=1,
        ), patch.object(app_inst, "exit"):
            app_inst._on_pick(md)
        assert app_inst._exit_code == 1

    def test_print_with_path_does_not_invoke_picker(self, tmp_path):
        """Regression: explicit-path branch never reaches the picker factory."""
        md = _write_md(tmp_path)
        with patch(
            "claude_teletype.cli._make_markdown_picker_app",
        ) as mock_factory, patch(
            "claude_teletype.printer.discover_printer",
        ) as mock_disc, patch(
            "claude_teletype.markdown.MarkdownRenderer",
        ) as mock_renderer_cls:
            mock_disc.return_value = _make_mock_driver()
            mock_renderer_cls.return_value = MagicMock()
            result = runner.invoke(app, ["print", str(md)])
        assert result.exit_code == 0, result.output
        mock_factory.assert_not_called()
