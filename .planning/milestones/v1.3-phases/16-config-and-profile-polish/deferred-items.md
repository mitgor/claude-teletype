# Deferred Items - Phase 16

## Pre-existing Test Failure

**test_cli_teletype_passes_no_profile** (`tests/test_teletype.py:390`)
- Test expects `profile=None` when `--teletype` is used without `--printer`, but USB auto-detection resolves to the Juki profile because `usb_vendor_id` and `usb_product_id` were added to the Juki profile in a previous phase.
- The mock for `discover_usb_device_verbose` returns a driver but doesn't mock `auto_detect_profile`, so the real auto-detect runs and finds the Juki VID:PID match.
- This failure exists on `master` before Phase 16 changes.
- **Recommendation:** The test should either mock `auto_detect_profile` to return None or expect the Juki profile to be resolved.
