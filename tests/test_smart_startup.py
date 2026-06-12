"""Tests for smart startup: skip setup when saved printer is connected."""

from __future__ import annotations

from claude_teletype.printing.discovery import (
    CupsPrinterInfo,
    DiscoveryResult,
    UsbDeviceInfo,
)
from claude_teletype.printing.selection import match_saved_printer


class TestMatchSavedPrinterUsb:
    """match_saved_printer matches USB devices by VID:PID hex string."""

    def test_usb_match_returns_selection_when_vid_pid_matches(self):
        discovery = DiscoveryResult(
            usb_devices=[
                UsbDeviceInfo(vendor_id=0x04B8, product_id=0x0005, product_name="Epson"),
            ]
        )
        result = match_saved_printer("usb", "04b8:0005", discovery)
        assert result is not None
        assert result.connection_type == "usb"
        assert result.device_index == 0

    def test_usb_no_match_returns_none(self):
        discovery = DiscoveryResult(
            usb_devices=[
                UsbDeviceInfo(vendor_id=0x04B8, product_id=0x0005),
            ]
        )
        result = match_saved_printer("usb", "1234:5678", discovery)
        assert result is None

    def test_usb_match_second_device(self):
        discovery = DiscoveryResult(
            usb_devices=[
                UsbDeviceInfo(vendor_id=0x1111, product_id=0x2222),
                UsbDeviceInfo(vendor_id=0x04B8, product_id=0x0005),
            ]
        )
        result = match_saved_printer("usb", "04b8:0005", discovery)
        assert result is not None
        assert result.device_index == 1

    def test_usb_empty_devices_returns_none(self):
        discovery = DiscoveryResult(usb_devices=[])
        result = match_saved_printer("usb", "04b8:0005", discovery)
        assert result is None

    def test_usb_invalid_vid_pid_format_returns_none(self):
        discovery = DiscoveryResult(
            usb_devices=[UsbDeviceInfo(vendor_id=0x04B8, product_id=0x0005)]
        )
        result = match_saved_printer("usb", "not-hex", discovery)
        assert result is None


class TestMatchSavedPrinterCups:
    """match_saved_printer matches CUPS printers by queue name."""

    def test_cups_match_returns_selection(self):
        discovery = DiscoveryResult(
            cups_printers=[
                CupsPrinterInfo(name="HP_LaserJet", uri="usb://HP/LaserJet"),
            ]
        )
        result = match_saved_printer("cups", "HP_LaserJet", discovery)
        assert result is not None
        assert result.connection_type == "cups"
        assert result.cups_printer_name == "HP_LaserJet"

    def test_cups_no_match_returns_none(self):
        discovery = DiscoveryResult(
            cups_printers=[
                CupsPrinterInfo(name="HP_LaserJet", uri="usb://HP/LaserJet"),
            ]
        )
        result = match_saved_printer("cups", "Epson_Dot_Matrix", discovery)
        assert result is None

    def test_cups_disabled_queue_not_matched(self):
        """Disabled CUPS queues are skipped so smart-startup falls through to setup.

        Regression: a stale CUPS queue ("Unable to send data to printer") was
        smart-matched by name only, silently routing characters into a dead
        queue while a working USB Direct device was ignored.
        """
        discovery = DiscoveryResult(
            cups_printers=[
                CupsPrinterInfo(
                    name="USB2.0-Print",
                    uri="usb:///USB2.0-Print",
                    enabled=False,
                ),
            ]
        )
        result = match_saved_printer("cups", "USB2.0-Print", discovery)
        assert result is None

    def test_cups_enabled_queue_still_matched(self):
        discovery = DiscoveryResult(
            cups_printers=[
                CupsPrinterInfo(
                    name="HP_LaserJet",
                    uri="usb://HP/LaserJet",
                    enabled=True,
                ),
            ]
        )
        result = match_saved_printer("cups", "HP_LaserJet", discovery)
        assert result is not None
        assert result.cups_printer_name == "HP_LaserJet"


class TestMatchSavedPrinterEdgeCases:
    """match_saved_printer handles empty/skip/missing saved config."""

    def test_empty_type_returns_none(self):
        discovery = DiscoveryResult(
            usb_devices=[UsbDeviceInfo(vendor_id=0x04B8, product_id=0x0005)]
        )
        result = match_saved_printer("", "04b8:0005", discovery)
        assert result is None

    def test_skip_type_returns_none(self):
        discovery = DiscoveryResult(
            usb_devices=[UsbDeviceInfo(vendor_id=0x04B8, product_id=0x0005)]
        )
        result = match_saved_printer("skip", "04b8:0005", discovery)
        assert result is None

    def test_usb_empty_id_returns_none(self):
        discovery = DiscoveryResult(
            usb_devices=[UsbDeviceInfo(vendor_id=0x04B8, product_id=0x0005)]
        )
        result = match_saved_printer("usb", "", discovery)
        assert result is None

    def test_cups_empty_id_returns_none(self):
        discovery = DiscoveryResult(
            cups_printers=[CupsPrinterInfo(name="HP", uri="usb://HP")]
        )
        result = match_saved_printer("cups", "", discovery)
        assert result is None


class _FakeBackend:
    def validate(self): pass


class TestNeedsPrinterSetupWithSavedConfig:
    """_needs_printer_setup branches on the explicit SetupDecision (REF-04)."""

    def test_skips_setup_on_saved_match_decision(self):
        """SKIP_SAVED_MATCH (saved printer matched), setup is skipped."""
        from claude_teletype.setup_decision import SetupDecision
        from claude_teletype.tui import TeletypeApp

        app = TeletypeApp(
            backend=_FakeBackend(),
            discovery=None,
            setup_decision=SetupDecision.SKIP_SAVED_MATCH,
            printer=None,
        )
        assert app._needs_printer_setup() is False

    def test_skips_setup_on_device_override_decision(self):
        """SKIP_DEVICE_OVERRIDE (--device), setup is skipped."""
        from claude_teletype.setup_decision import SetupDecision
        from claude_teletype.tui import TeletypeApp

        app = TeletypeApp(
            backend=_FakeBackend(),
            discovery=None,
            setup_decision=SetupDecision.SKIP_DEVICE_OVERRIDE,
            printer=None,
        )
        assert app._needs_printer_setup() is False

    def test_skips_setup_on_no_tui_decision(self):
        from claude_teletype.setup_decision import SetupDecision
        from claude_teletype.tui import TeletypeApp

        app = TeletypeApp(
            backend=_FakeBackend(),
            discovery=None,
            setup_decision=SetupDecision.SKIP_NO_TUI,
            printer=None,
        )
        assert app._needs_printer_setup() is False

    def test_shows_setup_on_show_setup_decision_and_no_printer(self):
        """SHOW_SETUP (saved printer NOT found), setup shows."""
        from claude_teletype.setup_decision import SetupDecision
        from claude_teletype.tui import TeletypeApp

        app = TeletypeApp(
            backend=_FakeBackend(),
            discovery=DiscoveryResult(),
            setup_decision=SetupDecision.SHOW_SETUP,
            printer=None,
        )
        assert app._needs_printer_setup() is True

    def test_legacy_discovery_kwarg_still_means_show_setup(self):
        """Back-compat: a DiscoveryResult without an explicit decision shows setup."""
        from claude_teletype.tui import TeletypeApp

        app = TeletypeApp(
            backend=_FakeBackend(),
            discovery=DiscoveryResult(),
            printer=None,
        )
        assert app._needs_printer_setup() is True

    def test_skip_reasons_are_distinct_values(self):
        """The three old discovery=None meanings are distinguishable now."""
        from claude_teletype.setup_decision import SetupDecision

        skips = {
            SetupDecision.SKIP_NO_TUI,
            SetupDecision.SKIP_DEVICE_OVERRIDE,
            SetupDecision.SKIP_SAVED_MATCH,
        }
        assert len(skips) == 3
        assert SetupDecision.SHOW_SETUP not in skips


class TestCliSetsDistinctSetupDecisions:
    """cli.main passes a distinct SetupDecision per startup path (REF-04)."""

    @staticmethod
    def _run_cli(argv, config):
        """Invoke the CLI with the standard mock harness; return TeletypeApp kwargs."""
        from typer.testing import CliRunner
        from unittest.mock import MagicMock, patch

        from claude_teletype.cli import app
        from claude_teletype.printing.discovery import CupsPrinterInfo

        def _mock_create_backend(*args, **kwargs):
            mock_be = MagicMock()
            mock_be.validate = MagicMock()
            return mock_be

        with patch(
            "claude_teletype.cli.create_backend", side_effect=_mock_create_backend
        ), patch(
            "claude_teletype.cli.load_config"
        ), patch(
            "claude_teletype.cli.apply_env_overrides"
        ) as mock_env, patch(
            "claude_teletype.cli.merge_cli_flags"
        ) as mock_merge, patch(
            "claude_teletype.printing.discovery.discover_all"
        ) as mock_discover, patch(
            "claude_teletype.printing.selection.discover_printer",
            return_value=MagicMock(),
        ), patch(
            "claude_teletype.printing.selection.create_driver_for_selection",
            return_value=MagicMock(),
        ), patch(
            "claude_teletype.tui.TeletypeApp"
        ) as mock_tui_cls, patch(
            "claude_teletype.cli.sys"
        ) as mock_sys:
            mock_env.return_value = config
            mock_merge.return_value = config
            mock_discover.return_value = DiscoveryResult(
                cups_printers=[
                    CupsPrinterInfo(
                        name="USB2.0-Print",
                        uri="usb:///USB2.0-Print",
                        enabled=True,
                    )
                ]
            )
            mock_tui = MagicMock()
            mock_tui.session_id = None
            mock_tui_cls.return_value = mock_tui
            mock_sys.stdin.isatty.return_value = True

            result = CliRunner().invoke(app, argv)

        assert result.exit_code == 0, result.output
        return mock_tui_cls.call_args[1]

    def test_saved_match_passes_skip_saved_match(self):
        from claude_teletype.config import TeletypeConfig
        from claude_teletype.setup_decision import SetupDecision

        cfg = TeletypeConfig()
        cfg.saved_printer_type = "cups"
        cfg.saved_printer_id = "USB2.0-Print"
        cfg.saved_printer_profile = "juki"

        kwargs = self._run_cli([], cfg)
        assert kwargs["setup_decision"] is SetupDecision.SKIP_SAVED_MATCH
        assert kwargs["discovery"] is None

    def test_device_override_passes_skip_device_override(self):
        from claude_teletype.config import TeletypeConfig
        from claude_teletype.setup_decision import SetupDecision

        cfg = TeletypeConfig()
        cfg.device = "/dev/usb/lp0"

        kwargs = self._run_cli([], cfg)
        assert kwargs["setup_decision"] is SetupDecision.SKIP_DEVICE_OVERRIDE
        assert kwargs["discovery"] is None

    def test_no_saved_printer_passes_show_setup_with_discovery(self):
        from claude_teletype.config import TeletypeConfig
        from claude_teletype.setup_decision import SetupDecision

        cfg = TeletypeConfig()

        kwargs = self._run_cli([], cfg)
        assert kwargs["setup_decision"] is SetupDecision.SHOW_SETUP
        assert kwargs["discovery"] is not None

    def test_saved_match_skip_differs_from_device_override_skip(self):
        """The two skip paths that used to be the same None are distinct."""
        from claude_teletype.config import TeletypeConfig

        saved_cfg = TeletypeConfig()
        saved_cfg.saved_printer_type = "cups"
        saved_cfg.saved_printer_id = "USB2.0-Print"
        saved_cfg.saved_printer_profile = "juki"
        saved_kwargs = self._run_cli([], saved_cfg)

        device_cfg = TeletypeConfig()
        device_cfg.device = "/dev/usb/lp0"
        device_kwargs = self._run_cli([], device_cfg)

        assert saved_kwargs["discovery"] is None
        assert device_kwargs["discovery"] is None  # old contract: identical
        assert (
            saved_kwargs["setup_decision"] is not device_kwargs["setup_decision"]
        )  # new contract: distinguishable
