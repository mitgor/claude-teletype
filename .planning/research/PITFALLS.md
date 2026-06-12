# Pitfalls Research

**Domain:** USB dot-matrix printer fleet detection + per-family profiles + package refactoring + PyInstaller standalone packaging (Python/Textual/pyusb/sounddevice on macOS)
**Researched:** 2026-06-12
**Confidence:** HIGH (USB/macOS kernel-driver behavior, PyInstaller dylib bundling, mock patch-target semantics all verified against official issues/docs; profile encoding pitfalls grounded in this project's own hard-won notes)

This file targets pitfalls of **adding v1.6 features to the existing v1.5 system** — not greenfield mistakes. It respects existing hard-won knowledge (CH341 atomic CR+LF, verbatim-from-manual encoding, ESC/POS binary 1/0, per-profile buffer_bytes) and focuses on the new failure surfaces those features introduce.

## Critical Pitfalls

### Pitfall 1: VID:PID matrix matches bridge chips, not printers (massive false-positive surface)

**What goes wrong:**
The detection matrix lists CH340 (`1a86:7523`), CH341 (`1a86:5512`/`1a86:7584`), Prolific PL2303 (`067b:2303`), and FTDI (`0403:6001`) as "dot-matrix printers." But these VID:PIDs identify the *bridge/serial chip*, not the printer behind it. The same `1a86:7523` is on millions of Arduino clones, ESP dev boards, GPS dongles, CNC controllers, and RS-232 cables. Auto-selecting any matched device as a printer means the tool offers (or silently drives) a random Arduino as if it were a Juki, and a user with a dev board plugged in gets garbage writes to their microcontroller.

**Why it happens:**
Bridge chips have no product-level identity. CH340 is "mostly Arduino clones" in the wild — printer usage is the minority case. Developers building a VID:PID table conflate "this chip can carry parallel printer signals" with "this device is a printer."

**How to avoid:**
- Two-tier classification. Tier A = **native-USB printers** (Epson TM/LQ, OKI, Star, Citizen with real printer VID:PIDs) → match by VID:PID AND require USB class 7 (printer) at interface level. Tier B = **bridge chips** → never auto-select; surface as "possible USB-LPT adapter (could be a serial device)" and require explicit user confirmation + manual profile assignment. The existing setup screen already gates selection — keep bridge chips behind that gate, never behind smart-skip.
- Reuse the existing "USB printer class 7 filter before VID:PID matching" decision (logged as Good) for Tier A. Do NOT extend class-7 filtering to bridge chips — CH341 in printer-class mode (alt 0/1) does present class 7, but so do other configs; class alone won't disambiguate Arduino-vs-printer for vendor-serial chips.
- For bridge chips, prefer interface/altsetting fingerprinting over VID:PID alone where possible (CH341: alt 0 unidirectional printer-class, alt 1 bidirectional, alt 2 vendor raw — documented in project hardware notes).
- Never let a bridge-chip match satisfy the v1.4 "smart startup skip" (saved printer still connected). A matched CH340 ≠ "my Juki is back."

**Warning signs:**
Diagnose output lists a device as a printer when no printer is attached. Users report "it found a printer but printing does nothing" (it's their Arduino). The matrix has more bridge-chip rows than printer-family rows.

**Phase to address:**
USB detection matrix phase. Verification = run `diagnose` with a CH340 dev board (no printer) attached; it must NOT auto-suggest/auto-skip, only offer as unconfirmed adapter.

---

### Pitfall 2: macOS USBLP/kernel driver claims the printer before pyusb can

**What goes wrong:**
On macOS, when a native-USB printer (class 7) enumerates, the system can bind a kernel-side driver / CUPS backend to it. `libusb_claim_interface` then fails (`LIBUSB_ERROR_ACCESS` / `LIBUSB_ERROR_BUSY`), or `darwin_claim_interface` fails outright on macOS 12.4+. The new "direct-drive the broad universe of native-USB printers" feature works on the test Juki (CH341 bridge, which CUPS ignores) but breaks on a real Epson TM whose class-7 interface macOS already owns. Worse: detaching/claiming it can leave CUPS unable to print afterward (documented libusb/cups interaction).

**Why it happens:**
The existing system was validated against a CH341 USB-LPT bridge — a thin pass-through that macOS/CUPS does not claim as a managed printer. v1.6 newly adds *native-USB printer families*, which are exactly the devices the OS wants to manage. The test hardware does not exercise this path, so it's invisible until a real native-USB printer is plugged in.

**How to avoid:**
- Distinguish "bridge-backed parallel printer" (claimable, the current happy path) from "native-USB class-7 printer" (likely OS-claimed) in the driver layer. For the latter, detect the claim failure and fall back to the **CUPS queue path** (already supported since v1.4) rather than forcing a raw claim.
- Do NOT auto-detach the kernel driver on macOS as a default — it can break CUPS for that device until replug. If detach is ever offered, make it explicit, reversible, and documented.
- Catch `USBError`/`LIBUSB_ERROR_ACCESS`/`BUSY` at claim time and present a clear message ("macOS is managing this printer; using CUPS queue instead") instead of an opaque pyusb traceback.
- Treat macOS 12.4+ claim regressions as a known constraint; test on the actual minimum-supported macOS.

**Warning signs:**
`USBError: [Errno 13] Access denied (insufficient permissions)` or `Resource busy` on a printer that enumerates fine in `diagnose`. Raw direct mode works for Juki but every native-USB printer errors. Printing via the tool kills the device for CUPS afterward.

**Phase to address:**
Direct-mode / driver-architecture phase. Verification = on a native-USB class-7 printer (or simulated claim failure), the driver falls back to CUPS without crashing; CUPS still prints to that device afterward.

---

### Pitfall 3: PyInstaller bundle can't find libusb / PortAudio dylib at runtime

**What goes wrong:**
The app runs fine from source but the PyInstaller bundle crashes on launch or on first USB/audio use. `libusb-1.0.dylib` isn't auto-collected (pyusb dlopens it by name at runtime — PyInstaller's static analysis can't see the dependency), so `usb.core.find()` raises `NoBackendError`. Separately, sounddevice's bundled `libportaudio.dylib` may be collected by the hook but resolved to the *local dev install* path at runtime (documented issue #7816), so audio fails on other machines. On Apple Silicon, a wrong-arch `libusb-1.0.dylib` gives `mach-o, but wrong architecture` / `dlopen` OSError. Since macOS Big Sur, system dylibs aren't on disk (dyld cache), so naive "does file exist" library probing also misfires.

**Why it happens:**
pyusb has **no PyInstaller hook for libusb** — it finds the backend by `ctypes.util.find_library('usb-1.0')` / dlopen, which is invisible to PyInstaller's import graph. sounddevice *does* have a hook (PyInstaller ≥5.13) but the path-resolution bug bites. These are the two new heavy native deps v1.6 adds to packaging; the existing app never packaged them.

**How to avoid:**
- Explicitly bundle libusb: add `libusb-1.0.dylib` via `--add-binary` (or a custom hook with `binaries=[...]`) AND set `LIBUSB_PATH` / configure pyusb's backend to load the bundled copy at runtime (`usb.backend.libusb1.get_backend(find_library=lambda x: bundled_path)`). Don't rely on auto-collection.
- Build on each target arch (or build universal2); verify `lipo -archs` on bundled dylibs. Don't ship an x86_64 libusb to Apple Silicon users.
- For sounddevice, verify the bundled `libportaudio.dylib` is actually loaded from the bundle (not the dev machine) — test on a machine without Homebrew/portaudio installed, or at least move/rename the local install before smoke-testing.
- Smoke-test the bundle on a **clean machine** (no Python, no Homebrew, no dev libs), not just the build host. "Works on my machine" is the canonical PyInstaller lie here.

**Warning signs:**
`usb.core.NoBackendError: No backend available` only in the bundle. `OSError: ... mach-o, but wrong architecture`. Audio silent in bundle but fine from source. Bundle works on dev Mac, fails on a colleague's.

**Phase to address:**
PyInstaller packaging phase. Verification = clean-machine smoke test: USB detection + audio + a print both work from the bundled `.app`/binary with no dev tooling installed.

---

### Pitfall 4: Big-bang refactor breaks 700 tests via stale patch targets

**What goes wrong:**
Refactoring the flat 23-module package into sub-packages changes import paths. Tests that `patch("ct.printer.usb.core.find")` (patch-at-source-module style, which this project uses per PROJECT.md) silently break or — worse — silently no-op when the symbol moves to `ct.drivers.usb.discovery`. Mocks stop intercepting, real USB/subprocess/network calls leak into tests, and either tests fail in bulk or pass while testing nothing. A big-bang reorg turns a green 700-test suite red all at once with hundreds of failures whose root cause (moved patch target) is indistinguishable from real regressions.

**Why it happens:**
`unittest.mock.patch` requires patching **where the name is looked up**, not where it's defined. The cardinal mock rule. When modules move, every `patch()` string referencing the old path is now wrong: it either errors (`AttributeError`/`ModuleNotFoundError`) or, if the old module still re-exports the name, patches a copy nobody uses (silent no-op — the dangerous case). The existing tech-debt list (cli.py duplication, USB re-discovery, discovery=None sentinel) tempts a sweeping rewrite that touches many import boundaries at once.

**How to avoid:**
- **Incremental, not big-bang.** Move one sub-package at a time, keep the suite green between moves. Each move = (a) relocate module, (b) update its callers' import sites, (c) update patch-target strings in tests that reference it, (d) run full suite.
- Where feasible, keep thin re-export shims in old module paths during transition so imports don't break in lockstep — but treat shims as temporary and grep them out before milestone close (otherwise they mask stale patch targets).
- Prefer `patch.object(module, "name")` or patching the *consuming* module's reference over fragile dotted-string source-module patches where you're free to choose — reduces churn surface. (Respect existing convention where it's already correct; just don't multiply fragile targets.)
- Add a CI guard: run `pytest` with `-W error` and ensure no real network/USB access during tests (the suite already mocks these — verify the mocks still bite after each move).
- Land the refactor and the new-profile/detection features in **separate phases**. Mixing reorg with behavior change makes every failure ambiguous.

**Warning signs:**
Hundreds of failures after one commit. A test passes but coverage shows the real function executed. `AttributeError: <module> does not have attribute X` in test collection. Tests suddenly hit the network/USB. Patch decorators referencing modules that no longer exist.

**Phase to address:**
Refactor phase (kept separate from feature phases). Verification = suite green after each incremental move; a grep for old module paths in test files returns nothing; `pytest --collect-only` clean.

---

### Pitfall 5: Fabricated control sequences across many printer families print garbage

**What goes wrong:**
Adding profiles for ~9 new families (Epson FX/LQ/LX, OKI Microline, Star, Citizen, Panasonic KX-P, Tally, IBM/Lexmark Proprinter, Seiko) means encoding dozens of init/reset/status/codepage/paper byte sequences. The temptation is to extrapolate ("Epson FX init is probably like LQ", "OKI reset is like Epson"). But firmware revisions, emulation modes (a printer in IBM-emulation mode vs ESC/P mode answers to *different* command sets), and codepage variance mean a plausible-but-wrong sequence prints literal garbage characters on paper — exactly the failure already documented for this project (fabricated codes print garbage; CR+LF reinit dropped by CH341). The existing tech debt already flags "Juki 9100 codes extrapolated from 6100 — need hardware verification" and "style ESC sequences spec-verified only." v1.6 multiplies this risk 9×.

**Why it happens:**
Manuals are scattered, paywalled, or scanned PDFs; copying verbatim is tedious; families look similar on paper. Emulation modes are easy to forget — the same physical printer is a *different command target* depending on a DIP switch. Codepage commands especially vary (the recent untracked `codepage_command`/`text_fallback` work shows this is live).

**How to avoid:**
- Enforce the existing "encoding-table-as-contract" / "leave empty when unsure" rule (logged Good decision) across ALL new families, no exceptions. An empty `b""` that falls back to plain/CR+LF beats a guessed sequence that prints `[2J` on paper.
- For each byte sequence, record provenance in the profile/source: manual name + page/revision + emulation mode it assumes. No provenance → leave empty.
- Make **emulation mode explicit** in each profile (e.g., "Epson FX profile assumes ESC/P mode, not IBM-emulation"). Don't assume default mode.
- ESC/POS / status sequences: remember binary 1/0 not ASCII (existing knowledge) — applies to the new status/paper-handling fields too.
- Flag every unverified family for `human_needed` hardware confirmation, exactly as Phase 22 did. Spec-verified ≠ hardware-verified; ship them as "best-effort, unconfirmed" not "supported."

**Warning signs:**
Printer emits literal `ESC @` glyphs or escape-sequence text on paper. A reset command on family X does nothing or jams paper. Codepage command produces wrong glyphs for non-ASCII (CP866/CP1125 examples are the canary). A profile has byte sequences but no manual citation.

**Phase to address:**
Profile-authoring phase. Verification = every non-empty byte field has a cited manual source + assumed emulation mode; unverified families tagged `human_needed`; CP866/CP1125 example docs still render correctly.

---

## Technical Debt Patterns

| Shortcut | Immediate Benefit | Long-term Cost | When Acceptable |
|----------|-------------------|----------------|-----------------|
| Auto-select any VID:PID match (incl. bridge chips) as printer | Zero-click setup | Drives Arduinos/serial devices as printers; data corruption to user's microcontroller | Never for bridge chips; OK for Tier-A class-7 native printers behind confirmation |
| Extrapolate control codes from a similar family | Fast profile coverage | Garbage on paper, jams, support burden; violates project's verbatim rule | Never — leave `b""` instead |
| Big-bang package reorg in one PR | "Clean" history | 700 tests red at once, ambiguous failures, stale patch targets | Never at this scale — go incremental |
| Re-export shims left in old module paths | Imports don't break during refactor | Mask stale patch targets that silently no-op (test nothing) | Only as temporary scaffolding; grep-removed before milestone close |
| Auto-detach macOS kernel driver to force raw claim | Direct mode "just works" on native-USB printers | Breaks CUPS for that device until replug; fragile on macOS 12.4+ | Never as default; explicit/reversible only |
| Rely on PyInstaller auto-collection for libusb | Less spec-file work | NoBackendError in bundle; ships broken | Never — explicitly add-binary + set backend path |
| Build PyInstaller bundle only on dev host arch | Faster CI | Wrong-arch dylib crashes Apple Silicon/Intel users | Never — build per-arch or universal2, verify with lipo |

## Integration Gotchas

| Integration | Common Mistake | Correct Approach |
|-------------|----------------|------------------|
| pyusb + libusb in PyInstaller | Assume PyInstaller finds the dlopen'd backend | `--add-binary libusb-1.0.dylib` + point pyusb backend at bundled copy via `find_library` lambda |
| sounddevice + PortAudio in bundle | Trust the hook fully | Hook collects it but may resolve to dev-install path; clean-machine test required |
| macOS native-USB printer (class 7) | Force `claim_interface` | Expect OS claim; catch ACCESS/BUSY, fall back to existing CUPS path |
| CH341 bridge (existing test device) | Use printer-class control queries (GET_PORT_STATUS/SOFT_RESET) | They STALL/EPIPE on CH341; it's a thin pass-through — don't depend on status feedback |
| CUPS coexistence | Detach kernel driver and forget | Detaching can break CUPS for that device; avoid or restore explicitly |
| Codepage on impact printers | Encode codepage command as ASCII | Many are binary; copy verbatim from manual, validate against CP866/CP1125 examples |

## Performance Traps

| Trap | Symptoms | Prevention | When It Breaks |
|------|----------|------------|----------------|
| Per-character bulk USB writes to native-USB printer without buffering | Dropped chars / overrun on fast native printers | Reuse per-profile `buffer_bytes` chunking (existing) tuned per new family | Faster native-USB printers (LQ/TM) than the slow Juki daisywheel |
| Fragmented CR+LF+reinit across multiple USB transfers | CH341 drops LF; stair-stepping | Keep CR+LF+reinit as ONE atomic transfer (existing locked decision) | Any CH341-bridged word-wrap newline |
| Scanning/probing every USB device at startup for the big matrix | Slow setup screen; hammering serial dev boards with probes | Match by descriptor (VID:PID + class) only; never write probe bytes to unconfirmed devices | Many USB devices attached; bridge-chip dev boards present |

## Security / Safety Mistakes

(Domain here is "physical hardware + local packaging," so "security" is mostly safety/integrity.)

| Mistake | Risk | Prevention |
|---------|------|------------|
| Writing printer bytes to an unconfirmed bridge-chip device | Corrupts/bricks a user's Arduino/CNC/GPS that shares the VID:PID | Never write to bridge-chip matches without explicit user confirmation |
| Shipping unsigned PyInstaller bundle | Gatekeeper "app is damaged / cannot be opened"; users disable Gatekeeper (unsafe) or can't run it | Code-sign + notarize with hardened runtime; document `xattr -dr com.apple.quarantine` only as last resort |
| Bundling secrets/config in the app | OpenAI/OpenRouter keys baked into distributable | Keep keys in user TOML/env (existing three-layer config); never embed in bundle |

## UX Pitfalls

| Pitfall | User Impact | Better Approach |
|---------|-------------|-----------------|
| Setup screen lists a bridge-chip as a confirmed printer | User picks it, prints, nothing happens (or their dev board gets garbage) | Label bridge matches "unconfirmed USB-LPT adapter — verify this is your printer" |
| Opaque pyusb traceback on macOS claim failure | User thinks app is broken | Friendly message + automatic CUPS fallback (reuse existing CUPS path) |
| Gatekeeper blocks first launch with no guidance | User abandons the app | Ship signing/notarization; if unsigned, provide explicit right-click-Open / quarantine instructions |
| New family profiles silently fall back to plain text | User expects bold/codepage, gets nothing, no explanation | Surface "this profile is unconfirmed/best-effort" in diagnose; keep fallback chain visible |

## "Looks Done But Isn't" Checklist

- [ ] **USB matrix:** Often missing bridge-vs-native distinction — verify a CH340 dev board with NO printer is NOT auto-selected/skip-matched
- [ ] **Native-USB printer driver:** Often missing macOS claim-failure handling — verify ACCESS/BUSY falls back to CUPS without traceback
- [ ] **New family profiles:** Often missing manual provenance + emulation mode — verify every non-empty byte field cites a source and assumed mode
- [ ] **Refactor:** Often missing patch-target updates — verify `grep` for old module paths in tests is empty and suite is green after each move
- [ ] **PyInstaller libusb:** Often missing explicit bundling — verify `usb.core.find()` works in the bundle on a clean machine
- [ ] **PyInstaller sounddevice:** Often resolves to dev-install dylib — verify audio works on a machine without Homebrew portaudio
- [ ] **Apple Silicon:** Often ships wrong-arch dylib — verify `lipo -archs` on bundled libusb/portaudio matches target
- [ ] **Gatekeeper:** Often unsigned — verify `spctl --assess --type execute -vvv` passes, or quarantine instructions are documented
- [ ] **Codepage:** Often regressed by refactor — verify CP866/CP1125 example docs still print correctly

## Recovery Strategies

| Pitfall | Recovery Cost | Recovery Steps |
|---------|---------------|----------------|
| Bridge-chip false positive shipped | LOW | Add confirmation gate; demote bridge matches to "unconfirmed"; ship patch |
| macOS claim failure crashes app | LOW-MEDIUM | Wrap claim in try/except; route to existing CUPS path; user-facing message |
| Big-bang refactor red suite | HIGH | Revert to last green; redo incrementally one sub-package at a time; fix patch targets per move |
| Fabricated control codes print garbage | MEDIUM | Blank the offending byte field to `b""`; re-source from manual; tag `human_needed` |
| libusb missing in bundle | MEDIUM | Add `--add-binary` + backend path; rebuild; clean-machine re-test |
| Gatekeeper blocks app | MEDIUM | Set up signing+notarization with hardened runtime; or document quarantine removal |

## Pitfall-to-Phase Mapping

| Pitfall | Prevention Phase | Verification |
|---------|------------------|--------------|
| Bridge-chip false positives | USB detection matrix phase | CH340 dev board (no printer) is not auto-selected/skip-matched |
| macOS kernel driver claims printer | Driver-architecture / direct-mode phase | Claim failure falls back to CUPS; CUPS still prints after |
| Fabricated control sequences | Profile-authoring phase | Every non-empty byte field cites manual + emulation mode; unverified tagged `human_needed` |
| Refactor breaks patch targets | Refactor phase (separate from features) | Suite green after each incremental move; no old module paths in tests |
| PyInstaller dylib/arch/signing | Packaging phase | Clean-machine smoke test passes USB+audio+print; `lipo`/`spctl` checks pass |

## Sources

- [PyInstaller #2633 — Can't package pyusb, "Unable to find libusb-1.0.so.0"](https://github.com/pyinstaller/pyinstaller/issues/2633) (HIGH)
- [pyusb #360 — Mac: how to package libusb so pyusb can find it](https://github.com/pyusb/pyusb/issues/360) and [#355 — Mac M1 support](https://github.com/pyusb/pyusb/issues/355) (HIGH)
- [PyInstaller #5107 — can't find dynamically linked libs on macOS Big Sur (dyld cache)](https://github.com/pyinstaller/pyinstaller/issues/5107) (HIGH)
- [PyInstaller #7816 — PortAudio bundled but resolves to local install](https://github.com/pyinstaller/pyinstaller/issues/7816) and [PR #4498 — sounddevice hook](https://github.com/pyinstaller/pyinstaller/pull/4498/files) (HIGH)
- [libusb #1153 — macOS 12.4+ failure to claim interface](https://github.com/libusb/libusb/issues/1153), [#575 — claim fails under Mojave](https://github.com/libusb/libusb/issues/575), [#364 / apple/cups #5176 — libusb breaks CUPS printing](https://github.com/libusb/libusb/issues/364) (HIGH)
- [Textualize/textual Discussion #4512 — packaging a TUI with PyInstaller (hidden imports)](https://github.com/Textualize/textual/discussions/4512) and [PyInstaller #6244 — console/GUI bundle terminal detection](https://github.com/pyinstaller/pyinstaller/issues/6244) (MEDIUM)
- [PyInstaller #5112 / #7937 — code signing & notarization on macOS .app bundles](https://github.com/pyinstaller/pyinstaller/issues/5112); [spctl/quarantine guidance, Apple Developer Forums #132908](https://developer.apple.com/forums/thread/132908) (HIGH)
- [Python docs — unittest.mock "where to patch"](https://docs.python.org/3/library/unittest.mock.html#where-to-patch) (HIGH)
- [Arduino IDE VID/PID list for CH340/CH341/PL2303/FTDI serial chips (per1234/zzInoVIDPID)](https://github.com/per1234/zzInoVIDPID) — evidence that these VID:PIDs are serial-chip-level, not device-level (MEDIUM)
- Project hardware notes: Juki 2200 / CH341 USB-LPT quirks (`project_juki_2200_hardware.md`) and PROJECT.md Key Decisions (atomic CR+LF, verbatim encoding, class-7 filter, buffer_bytes) (HIGH — primary, project-internal)

---
*Pitfalls research for: USB dot-matrix printer fleet + per-family profiles + package refactor + PyInstaller packaging*
*Researched: 2026-06-12*
