#!/usr/bin/env bash
# Frozen-build smoke gate for the PyInstaller onedir bundle (R027/R029).
#
# Run from the repo root, after a build (see packaging/README.md):
#
#   bash packaging/smoke_frozen.sh
#
# Headless approximation of the clean-machine run (the real clean-machine
# pass is human_needed — R028). Guards the two silent failure modes:
#   - pyusb absent from the build venv (bundle "works" but USB is dead)
#   - bundled dylibs still referencing Homebrew paths (works on the dev
#     machine, breaks on a machine without /opt/homebrew)
#
# Each check prints PASS/FAIL; the script exits non-zero on any failure.
set -euo pipefail

DIST="dist/claude-teletype"
BIN="$DIST/claude-teletype"

FAILURES=0
pass() { printf 'PASS  %s\n' "$1"; }
fail() { printf 'FAIL  %s\n' "$1"; FAILURES=$((FAILURES + 1)); }

if [ ! -x "$BIN" ]; then
    fail "$BIN missing or not executable — build the onedir bundle first (packaging/README.md)"
    echo "FROZEN SMOKE: FAILED"
    exit 1
fi

# (1) --help exits 0 -------------------------------------------------------
if "$BIN" --help > /dev/null 2>&1; then
    pass "--help exits 0"
else
    fail "--help exited non-zero"
fi

# (2) diagnose exits 0 and renders the no-USB degradation surface ----------
# 'Profile Capabilities' + a star-line row + the 'Built-in profiles only'
# footnote is the S03 no-USB surface (D008): proves R029's diagnose path
# renders fully without hardware.
DIAG_OUT=""
DIAG_RC=0
DIAG_OUT="$("$BIN" diagnose 2>&1)" || DIAG_RC=$?

if [ "$DIAG_RC" -eq 0 ]; then
    pass "diagnose exits 0"
else
    fail "diagnose exited $DIAG_RC"
fi

if grep -q 'Profile Capabilities' <<< "$DIAG_OUT"; then
    pass "diagnose renders 'Profile Capabilities' table"
else
    fail "diagnose output missing 'Profile Capabilities' table title"
fi

if grep -q 'star-line' <<< "$DIAG_OUT"; then
    pass "diagnose capability table includes the star-line row"
else
    fail "diagnose output missing the star-line profile row"
fi

if grep -q 'Built-in profiles only' <<< "$DIAG_OUT"; then
    pass "diagnose renders the 'Built-in profiles only' footnote"
else
    fail "diagnose output missing the 'Built-in profiles only' footnote"
fi

# (3) pyusb is actually in the bundle (R027 quiet-failure guard) -----------
# Exit-0 alone is NOT sufficient: a bundle built without --extra usb still
# runs and diagnoses fine, it just permanently reports pyusb missing.
if grep -E -q 'pyusb[^A-Za-z]+Installed' <<< "$DIAG_OUT"; then
    pass "diagnose reports pyusb as Installed"
else
    fail "diagnose does not report pyusb as Installed — was the bundle built without 'uv sync --extra usb'?"
fi

if grep -q 'Not installed' <<< "$DIAG_OUT"; then
    fail "diagnose output contains 'Not installed' — a dependency is missing from the bundle"
else
    pass "diagnose output contains no 'Not installed' rows"
fi

# (4) No bundled binary references Homebrew or /usr/local ------------------
# otool -L echoes the queried file path as a header line ("path:"), so only
# load-command lines (tab-indented) are matched — otherwise auditing a file
# under /opt/homebrew would false-positive on its own header.
LEAKS=0
SCANNED=0
while IFS= read -r -d '' lib; do
    SCANNED=$((SCANNED + 1))
    LEAK_LINES="$(otool -L "$lib" | grep -E $'^\t' | grep -E '/opt/homebrew|/usr/local' || true)"
    if [ -n "$LEAK_LINES" ]; then
        printf 'FAIL  Homebrew/local path leaked from %s:\n%s\n' "$lib" "$LEAK_LINES"
        LEAKS=$((LEAKS + 1))
    fi
done < <(find "$DIST" \( -name '*.dylib' -o -name '*.so' \) -print0)

if [ "$SCANNED" -eq 0 ]; then
    fail "no .dylib/.so files found under $DIST — is the build complete?"
elif [ "$LEAKS" -eq 0 ]; then
    pass "no /opt/homebrew or /usr/local references in $SCANNED bundled binaries"
else
    FAILURES=$((FAILURES + LEAKS))
fi

# (5) Clean-machine approximation: stripped environment --------------------
# env -i with a bare PATH ≈ no Homebrew PATH, no dev shell, fresh HOME.
CLEAN_OUT=""
CLEAN_RC=0
CLEAN_OUT="$(env -i HOME="$(mktemp -d)" PATH=/usr/bin:/bin "$BIN" diagnose 2>&1)" || CLEAN_RC=$?

if [ "$CLEAN_RC" -eq 0 ]; then
    pass "diagnose exits 0 under stripped env (env -i, no Homebrew PATH)"
else
    fail "diagnose exited $CLEAN_RC under stripped env"
fi

if grep -q 'Profile Capabilities' <<< "$CLEAN_OUT"; then
    pass "capability table still renders under stripped env"
else
    fail "capability table missing under stripped env"
fi

# ---------------------------------------------------------------------------
if [ "$FAILURES" -gt 0 ]; then
    echo "FROZEN SMOKE: $FAILURES FAILURE(S)"
    exit 1
fi
echo "FROZEN SMOKE: ALL PASS"
