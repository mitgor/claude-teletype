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


class TestMatchSavedPrinterProfileName:
    """match_saved_printer owns the profile hand-off (ARCH-04)."""

    def test_usb_variant_stamps_profile_name(self):
        discovery = DiscoveryResult(
            usb_devices=[UsbDeviceInfo(vendor_id=0x04B8, product_id=0x0005)]
        )
        result = match_saved_printer(
            "usb", "04b8:0005", discovery, profile_name="juki-6100"
        )
        assert result is not None
        assert result.profile_name == "juki-6100"

    def test_usb_variant_defaults_to_generic(self):
        discovery = DiscoveryResult(
            usb_devices=[UsbDeviceInfo(vendor_id=0x04B8, product_id=0x0005)]
        )
        result = match_saved_printer("usb", "04b8:0005", discovery)
        assert result is not None
        assert result.profile_name == "generic"

    def test_cups_variant_stamps_profile_name(self):
        discovery = DiscoveryResult(
            cups_printers=[CupsPrinterInfo(name="HP_LaserJet", uri="usb://HP/LaserJet")]
        )
        result = match_saved_printer(
            "cups", "HP_LaserJet", discovery, profile_name="epson-fx"
        )
        assert result is not None
        assert result.profile_name == "epson-fx"


class TestPrinterSelectionFrozen:
    """PrinterSelection is immutable — the ARCH-04 mutation class cannot recur."""

    def test_assignment_raises_frozen_instance_error(self):
        import dataclasses

        import pytest

        from claude_teletype.printing.discovery import PrinterSelection

        selection = PrinterSelection(connection_type="usb")
        with pytest.raises(dataclasses.FrozenInstanceError):
            selection.profile_name = "juki-6100"


class TestCupsNoNameFallback:
    """create_driver_for_selection: cups with no name picks first enabled queue (CR-03)."""

    def test_no_name_picks_first_enabled_queue(self, capsys):
        from claude_teletype.printing.drivers import CupsPrinterDriver
        from claude_teletype.printing.discovery import PrinterSelection
        from claude_teletype.printing.selection import create_driver_for_selection

        discovery = DiscoveryResult(
            cups_printers=[
                CupsPrinterInfo(name="Disabled_Q", uri="usb://a", enabled=False),
                CupsPrinterInfo(name="Enabled_Q", uri="usb://b", enabled=True),
                CupsPrinterInfo(name="Another_Q", uri="usb://c", enabled=True),
            ]
        )
        selection = PrinterSelection(connection_type="cups", cups_printer_name=None)
        driver = create_driver_for_selection(selection, discovery)
        assert isinstance(driver, CupsPrinterDriver)
        assert driver._name == "Enabled_Q"
        assert "Enabled_Q" in capsys.readouterr().err

    def test_no_name_no_enabled_queues_returns_null(self):
        from claude_teletype.printing.drivers import NullPrinterDriver
        from claude_teletype.printing.discovery import PrinterSelection
        from claude_teletype.printing.selection import create_driver_for_selection

        discovery = DiscoveryResult(
            cups_printers=[
                CupsPrinterInfo(name="Disabled_Q", uri="usb://a", enabled=False),
            ]
        )
        selection = PrinterSelection(connection_type="cups", cups_printer_name=None)
        driver = create_driver_for_selection(selection, discovery)
        assert isinstance(driver, NullPrinterDriver)


class TestRegistryBackedProfileLookup:
    """create_driver_for_selection resolves profiles via ProfileRegistry (WR-01/WR-04)."""

    @staticmethod
    def _cups_discovery():
        return DiscoveryResult(
            cups_printers=[
                CupsPrinterInfo(name="Q", uri="usb://q", enabled=True),
            ]
        )

    def test_wrong_case_profile_name_still_wraps(self):
        """'Juki' resolves case-insensitively to builtin 'juki' (WR-01)."""
        from claude_teletype.printing.discovery import PrinterSelection
        from claude_teletype.printing.drivers import ProfilePrinterDriver
        from claude_teletype.printing.profiles import BUILTIN_PROFILES
        from claude_teletype.printing.registry import ProfileRegistry
        from claude_teletype.printing.selection import create_driver_for_selection

        selection = PrinterSelection(
            connection_type="cups", cups_printer_name="Q", profile_name="Juki"
        )
        driver = create_driver_for_selection(
            selection,
            self._cups_discovery(),
            registry=ProfileRegistry(BUILTIN_PROFILES),
        )
        assert isinstance(driver, ProfilePrinterDriver)

    def test_unknown_profile_appends_diagnostic_and_unwraps(self):
        """Unknown name: unwrapped driver + one diagnostic in the passed list."""
        from claude_teletype.printing.discovery import PrinterSelection
        from claude_teletype.printing.drivers import (
            CupsPrinterDriver,
            ProfilePrinterDriver,
        )
        from claude_teletype.printing.selection import create_driver_for_selection

        diagnostics: list[str] = []
        selection = PrinterSelection(
            connection_type="cups", cups_printer_name="Q", profile_name="nonexistent"
        )
        driver = create_driver_for_selection(
            selection, self._cups_discovery(), diagnostics=diagnostics
        )
        assert isinstance(driver, CupsPrinterDriver)
        assert not isinstance(driver, ProfilePrinterDriver)
        assert len(diagnostics) == 1
        assert "nonexistent" in diagnostics[0]

    def test_unknown_profile_prints_to_stderr_without_list(self, capsys):
        """diagnostics=None keeps the CLI path loud via stderr."""
        from claude_teletype.printing.discovery import PrinterSelection
        from claude_teletype.printing.drivers import ProfilePrinterDriver
        from claude_teletype.printing.selection import create_driver_for_selection

        selection = PrinterSelection(
            connection_type="cups", cups_printer_name="Q", profile_name="nonexistent"
        )
        driver = create_driver_for_selection(selection, self._cups_discovery())
        assert not isinstance(driver, ProfilePrinterDriver)
        assert "nonexistent" in capsys.readouterr().err

    def test_usb_cups_fallback_message_routed_through_diagnostics(self, capsys, monkeypatch):
        """CR-03 USB->CUPS fallback goes to the list when passed, stderr when not."""
        from claude_teletype.printing import discovery as _discovery
        from claude_teletype.printing.discovery import PrinterSelection
        from claude_teletype.printing.drivers import CupsPrinterDriver
        from claude_teletype.printing.selection import create_driver_for_selection

        monkeypatch.setattr(_discovery, "_find_usb_printer", lambda identity=None: None)
        discovery = DiscoveryResult(
            usb_devices=[UsbDeviceInfo(vendor_id=0x04B8, product_id=0x0005)],
            cups_printers=[CupsPrinterInfo(name="Q", uri="usb://q", enabled=True)],
        )
        selection = PrinterSelection(connection_type="usb", device_index=0)

        # list passed: appended, not printed
        diagnostics: list[str] = []
        driver = create_driver_for_selection(selection, discovery, diagnostics=diagnostics)
        assert isinstance(driver, CupsPrinterDriver)
        assert any("falling back to CUPS queue Q" in d for d in diagnostics)
        assert "falling back" not in capsys.readouterr().err

        # no list: printed to stderr (existing behavior preserved)
        driver = create_driver_for_selection(selection, discovery)
        assert isinstance(driver, CupsPrinterDriver)
        assert "falling back to CUPS queue Q" in capsys.readouterr().err

    def test_bare_call_resolves_builtin_names(self):
        """No registry/all_profiles args: builtin names still resolve."""
        from claude_teletype.printing.discovery import PrinterSelection
        from claude_teletype.printing.drivers import ProfilePrinterDriver
        from claude_teletype.printing.selection import create_driver_for_selection

        selection = PrinterSelection(
            connection_type="cups", cups_printer_name="Q", profile_name="juki"
        )
        driver = create_driver_for_selection(selection, self._cups_discovery())
        assert isinstance(driver, ProfilePrinterDriver)


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
    def _run_cli(argv, config, discovery=None):
        """Invoke the CLI with the standard mock harness; return TeletypeApp kwargs.

        ``discovery`` overrides what the patched discover_all() returns;
        defaults to a single enabled CUPS queue.
        """
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
            mock_discover.return_value = discovery if discovery is not None else DiscoveryResult(
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


class TestR011ClassificationNeverAutoSkips:
    """R011 regression: classification informs, it never auto-skips setup.

    The one allowed auto path is an exact saved VID:PID match
    (SKIP_SAVED_MATCH); a recognized bridge chip with no saved config must
    still land on SHOW_SETUP.
    """

    @staticmethod
    def _bridge_only_discovery():
        """Exactly one CH341 bridge (the VID:PID the juki profile pins)."""
        return DiscoveryResult(
            pyusb_available=True,
            usb_devices=[
                UsbDeviceInfo(
                    vendor_id=0x1A86,
                    product_id=0x7584,
                    product_name="USB2.0-Print",
                    printer_class=False,
                )
            ],
        )

    def test_bridge_only_discovery_without_saved_config_shows_setup(self):
        """No saved printer config + one bridge device → SHOW_SETUP.

        Classification alone never auto-skips, even though the bridge's
        VID:PID matches the juki profile's pin."""
        from claude_teletype.config import TeletypeConfig
        from claude_teletype.setup_decision import SetupDecision

        cfg = TeletypeConfig()
        discovery = self._bridge_only_discovery()

        kwargs = TestCliSetsDistinctSetupDecisions._run_cli(
            [], cfg, discovery=discovery
        )
        assert kwargs["setup_decision"] is SetupDecision.SHOW_SETUP
        assert kwargs["discovery"] is discovery

    def test_saved_vidpid_match_on_bridge_still_skips(self):
        """The saved-match path (R011's one allowed auto path) still skips
        when the saved VID:PID matches the connected bridge."""
        from claude_teletype.config import TeletypeConfig
        from claude_teletype.setup_decision import SetupDecision

        cfg = TeletypeConfig()
        cfg.saved_printer_type = "usb"
        cfg.saved_printer_id = "1a86:7584"
        cfg.saved_printer_profile = "juki"

        kwargs = TestCliSetsDistinctSetupDecisions._run_cli(
            [], cfg, discovery=self._bridge_only_discovery()
        )
        assert kwargs["setup_decision"] is SetupDecision.SKIP_SAVED_MATCH
        assert kwargs["discovery"] is None


class TestSavedMatchDiagnosticsReachTui:
    """WR-03: the cli saved-match path threads a diagnostics list from
    create_driver_for_selection through to TeletypeApp(startup_diagnostics=)."""

    def test_diagnostics_list_is_shared_between_factory_and_app(self):
        from typer.testing import CliRunner
        from unittest.mock import MagicMock, patch

        from claude_teletype.cli import app
        from claude_teletype.config import TeletypeConfig

        cfg = TeletypeConfig()
        cfg.saved_printer_type = "cups"
        cfg.saved_printer_id = "USB2.0-Print"
        cfg.saved_printer_profile = "juki"

        def _fake_create_driver(selection, discovery, *, registry=None, diagnostics=None):
            assert diagnostics is not None, "cli must pass a diagnostics list (WR-03)"
            diagnostics.append("fallback diag from factory")
            return MagicMock()

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
            "claude_teletype.printing.selection.create_driver_for_selection",
            side_effect=_fake_create_driver,
        ), patch(
            "claude_teletype.tui.TeletypeApp"
        ) as mock_tui_cls, patch(
            "claude_teletype.cli.sys"
        ) as mock_sys:
            mock_env.return_value = cfg
            mock_merge.return_value = cfg
            mock_discover.return_value = DiscoveryResult(
                cups_printers=[
                    CupsPrinterInfo(
                        name="USB2.0-Print", uri="usb:///USB2.0-Print", enabled=True
                    )
                ]
            )
            mock_tui = MagicMock()
            mock_tui.session_id = None
            mock_tui_cls.return_value = mock_tui
            mock_sys.stdin.isatty.return_value = True

            result = CliRunner().invoke(app, [])

        assert result.exit_code == 0, result.output
        kwargs = mock_tui_cls.call_args[1]
        assert kwargs["startup_diagnostics"] == ["fallback diag from factory"]


class TestNullFallbackIsLoud:
    """WR-04: a failed usb/cups pick with no fallback queue emits a diagnostic
    instead of silently returning NullPrinterDriver."""

    def test_usb_fail_no_queues_emits_diagnostic(self, monkeypatch):
        from claude_teletype.printing import discovery as _discovery
        from claude_teletype.printing.discovery import PrinterSelection
        from claude_teletype.printing.drivers import NullPrinterDriver
        from claude_teletype.printing.selection import create_driver_for_selection

        monkeypatch.setattr(_discovery, "_find_usb_printer", lambda identity=None: None)
        discovery = DiscoveryResult(
            usb_devices=[UsbDeviceInfo(vendor_id=0x04B8, product_id=0x0005)],
            cups_printers=[],
        )
        selection = PrinterSelection(connection_type="usb", device_index=0)

        diagnostics: list[str] = []
        driver = create_driver_for_selection(selection, discovery, diagnostics=diagnostics)
        assert isinstance(driver, NullPrinterDriver)
        assert any("simulator" in d for d in diagnostics)

    def test_usb_fail_no_queues_prints_to_stderr_without_list(self, monkeypatch, capsys):
        from claude_teletype.printing import discovery as _discovery
        from claude_teletype.printing.discovery import PrinterSelection
        from claude_teletype.printing.selection import create_driver_for_selection

        monkeypatch.setattr(_discovery, "_find_usb_printer", lambda identity=None: None)
        discovery = DiscoveryResult(
            usb_devices=[UsbDeviceInfo(vendor_id=0x04B8, product_id=0x0005)],
        )
        selection = PrinterSelection(connection_type="usb", device_index=0)
        create_driver_for_selection(selection, discovery)
        assert "simulator" in capsys.readouterr().err

    def test_skip_selection_stays_silent(self, capsys):
        from claude_teletype.printing.discovery import PrinterSelection
        from claude_teletype.printing.drivers import NullPrinterDriver
        from claude_teletype.printing.selection import create_driver_for_selection

        selection = PrinterSelection(connection_type="skip")
        driver = create_driver_for_selection(selection, DiscoveryResult())
        assert isinstance(driver, NullPrinterDriver)
        assert capsys.readouterr().err == ""
