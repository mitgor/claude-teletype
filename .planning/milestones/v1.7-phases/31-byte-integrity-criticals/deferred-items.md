# Deferred Items — Phase 31

- tests/test_usb_backend.py::test_frozen_with_bundled_dylib_builds_explicit_backend and
  ::test_frozen_get_backend_returning_none_propagates fail with
  `ModuleNotFoundError: No module named 'usb'` — pyusb not installed in this
  environment. Pre-existing, unrelated to plan 31-01 (drivers.py byte-integrity fixes).
