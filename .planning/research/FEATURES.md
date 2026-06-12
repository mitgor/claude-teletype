# Feature Research

**Domain:** USB dot-matrix printer fleet detection + per-family direct-mode profiles + standalone packaging (Claude Teletype v1.6)
**Researched:** 2026-06-12
**Confidence:** MEDIUM (command-language facts HIGH from vendor manuals; specific per-model USB PIDs LOW — vendor IDs verified, but vintage parallel units have NO native USB PID, so model-level PID matching is largely inapplicable)

---

## Critical framing fact (drives everything below)

There are **two physically distinct connection paths**, and they detect completely differently:

1. **Vintage parallel printers via a USB-LPT bridge cable.** The printer (Epson FX/LX, OKI ML320, IBM Proprinter, Panasonic KX-P, old Star/Citizen) has **no USB at all**. The host only ever sees the **bridge chip's** VID:PID (CH340/CH341, Prolific, FTDI, MosChip). The printer model is **invisible to USB enumeration** — it must be chosen by the user, not auto-detected. This is the dominant case for the "vintage" half of the milestone.

2. **Modern native-USB impact/POS printers** (Epson LQ-590/690 USB, OKI ML390 USB, Star/Citizen POS, modern TM-series). These enumerate as USB printer-class (class 7) with the **manufacturer's** VID and a model PID — auto-detectable, matching the existing v1.4/v1.2 VID:PID path.

**Implication for the roadmap:** detection is a two-tier system. Tier 1 (bridge chips) identifies *a printer is probably attached* but cannot name it → fall back to user profile selection. Tier 2 (native USB) names the family → auto-suggest profile. The existing `usb_vendor_id`/`usb_product_id` profile fields serve Tier 2; a new **bridge-chip registry** (separate from printer profiles) serves Tier 1.

Sources: [the-sz USB ID DB — CH341 modes](https://the-sz.com/products/usbid/index.php?v=0x1A86) (0x5584 = parallel/printer mode, 0x5523 = serial, 0x5512 = EPP/I2C); [Linux CH341 driver source](https://github.com/RichStrong/CH341A_linux_driver/blob/master/ch34x_pis.c); [Alibaba electronics Q&A on parallel-to-USB adapters](https://electronics.alibaba.com/question/parallel-to-usb-adapter-does-it-really-work) (CH340/FTDI serial adapters fail on BUSY/ACK handshake; only true IEEE-1284 printer-class bridges work).

---

## Feature Landscape

### Table Stakes (Users Expect These)

| Feature | Why Expected | Complexity | Notes |
|---------|--------------|------------|-------|
| **Bridge-chip detection registry** (CH340/CH341, Prolific PL2303/PL2305, FTDI, MosChip) | The vintage path produces a bridge VID:PID, never a printer PID. Without this, "broad detection" detects nothing for the most common vintage setup | MEDIUM | New data table, separate from `BUILTIN_PROFILES`. Detect chip → message "USB-LPT bridge found; choose your printer family." VIDs: CH=0x1A86, Prolific=0x067B, FTDI=0x0403, MosChip=0x9710. Match only the **printer/parallel** PIDs (CH341 0x5584), not serial-only PIDs (0x5523) which can't drive an impact printer reliably |
| **Per-family built-in profiles by command language** (ESC/P, ESC/P2, IBM PPDS, OKI MICROLINE native, Star line mode, ESC/POS) | Users own a *family*, not a single SKU; one good profile per command language covers dozens of models | MEDIUM | Most impact printers share a command set across many models. Group by language, not by SKU (see family table below) |
| **`ESC @` initialize on connect** | Universal "reset to power-on defaults" across ESC/P, ESC/P2, IBM PPDS. Users expect clearing leftover bold/condensed/codepage state | LOW | `init_sequence=b"\x1b@"`. Already supported by `init_sequence` field. Epson + IBM both use `ESC @`. OKI native + Star use it in their Epson/IBM emulation modes |
| **Form feed / eject page** | Tractor/cut-sheet users expect to eject the current page on demand and at end-of-document | LOW | `FF` (0x0C). Already partially covered by `formfeed_on_close`. Expose as explicit user action (e.g. key binding) for the standalone terminal app |
| **Codepage / international character set switching** | Already shipped untracked (`codepage_command`+`text_codec`+`text_fallback`). Non-ASCII (Cyrillic, accented Latin) is unprintable without it | MEDIUM (done) | v1.6 just *formalizes existing code* into tracked requirements + extends per family. ESC/P/P2: `ESC t n` (char table) + `ESC R n` (intl set). IBM PPDS: code-page select. Keep the conservative leave-empty rule |
| **Graceful "detected bridge but unknown printer" fallback to manual selection** | The vintage path *cannot* name the printer; the setup screen must offer family selection rather than guessing | LOW | Reuses existing v1.4 PrinterSetupScreen profile-picker; new branch: bridge-found-but-no-PID-match → jump straight to profile list |
| **Standalone runnable app with no Python install** | The whole point of "Standalone" milestone — give a non-developer a thing that runs | MEDIUM | PyInstaller. macOS primary. See packaging section |

### Differentiators (Competitive Advantage)

| Feature | Value Proposition | Complexity | Notes |
|---------|-------------------|------------|-------|
| **Verified-from-manual control codes, conservative leave-empty rule** | Most hobby printer tools ship garbage codes that print mojibake. Teletype's existing decision ("byte values copied verbatim from manuals; when unsure leave empty") is a genuine quality differentiator | MEDIUM | Per family: cite the manual page. Epson ESC/P ref (escp2ref.pdf), IBM PPDS list (IBM support page), OKI ML320/390 user guide, Star dot-impact STAR command spec. Empty = safe fallback to plain/underline chain already built |
| **OKI MICROLINE *native* mode support (not just Epson/IBM emulation)** | OKI ML printers default to IBM/Epson emulation but have a native command set; supporting native is rare and signals depth | MEDIUM | Most tools only use the emulation. Native MICROLINE commands documented in ML320 Turbo handbook p.94. LOW priority vs. just using the emulation modes — see anti-feature note |
| **Star line mode (STAR command spec) profile** | Star dot-impact (SP500/SP700-class) have a native "STAR mode" distinct from ESC/POS; supporting it covers POS-style impact units | MEDIUM | Star publishes dot_star_cm_en.pdf (STAR command spec rev 1.91) and a separate ESC/POS spec. Decide per model which mode the unit is jumpered to |
| **End-of-document form-feed/cut as per-profile policy** | Already have `end_of_response_sequence` + `formfeed_on_close`; extending to paper-handling policy per family (tractor vs cut-sheet vs receipt cut) is a clean differentiator | LOW | Receipt/POS = feed+cut; tractor = FF; cut-sheet = eject. Data-driven via existing fields |
| **Universal2 macOS binary (Intel + Apple Silicon)** | One download works on any modern Mac; avoids "wrong architecture" support churn | MEDIUM | PyInstaller `--target-arch universal2`. Requires universal2 Python + deps. Bonus, not table stakes |

### Anti-Features (Commonly Requested, Often Problematic)

| Feature | Why Requested | Why Problematic | Alternative |
|---------|---------------|-----------------|-------------|
| **Auto-naming the printer model behind a bridge cable** | "Just tell me which printer it is" | **Physically impossible** — bridge exposes only its own VID:PID; the parallel printer is invisible to USB. Promising it guarantees wrong guesses | Detect *bridge present*, then ask the user to pick family. Honest and correct |
| **Status / busy / paper-out readback over USB-LPT bridges** | Users want "out of paper" / "ribbon jam" feedback | Most cheap bridges (and all serial-chip CH340/FTDI adapters) are effectively **write-only** for impact printers; bidirectional IEEE-1284 status is unreliable or absent. Building UI around it creates false confidence | Send-and-pray write model (already the architecture). Optionally read status **only** on confirmed bidirectional native-USB printer-class devices; otherwise omit. Document the limitation |
| **Per-SKU profile for every model number** | Completeness instinct | Combinatorial explosion; models within a family share command sets, so 40 profiles add maintenance with no behavioral difference | One profile **per command language/family**, with `columns` + paper-handling as the only per-model knobs |
| **Driving impact printers through a CH340/FTDI *serial* adapter** | They're cheap and plentiful | These are USB-to-RS232, not USB-to-parallel-printer. They drop bytes on BUSY/ACK handshake and corrupt output on most impact printers | Match only true printer-class / parallel-mode bridges (CH341 PID 0x5584, MosChip, IOGEAR/ATEN/Sabrent IEEE-1284). Warn if a serial-only chip is selected |
| **Full graphics / bit-image / barcode printing** | "It's a printer, print images" | Out of scope (PROJECT.md: plain text only, typewriter aesthetic). Bit-image timing also overruns naive USB-bulk writes | Plain-text streaming only; keep the typewriter character-pacing core value |
| **`--onefile` PyInstaller for the primary macOS build** | One file feels cleanest | onefile unpacks to a temp dir on every launch (slow startup, antivirus/gatekeeper friction, harder to sign/notarize). For a TUI app the onedir `.app` is better | Ship a `.app` bundle (onedir) for macOS; reserve `--onefile` for the Linux bonus binary where single-file is idiomatic |

---

## Printer family matrix (command language → models → control codes)

> Grouping principle: **one profile per command language.** The middle column lists representative models so the setup screen can show "e.g." hints. Bracketed codes are HIGH-confidence from cited manuals; leave-empty where a family lacks a documented sequence.

| Family / profile | Command language | Representative models | Init / reset | Codepage / intl | Paper / FF | USB? |
|---|---|---|---|---|---|---|
| **Epson FX / LX** | ESC/P (1st gen, no scalable fonts) | FX-80/85/890/2190, LX-300/350/810/1170 | `ESC @` init | `ESC R n` intl set; `ESC t n` char table | `FF`; `ESC EM n` cut-sheet feeder | LX-350=PID 0x0046 (native USB); older via bridge |
| **Epson LQ / ESC/P2** | ESC/P2 (superset of ESC/P) | LQ-300/350/590/690/2090/2190 | `ESC @` init | `ESC ( t` / `ESC t n`; `ESC R n` | `FF`; `ESC EM n` | LQ-350=PID 0x0047; LQ-590/690 native USB |
| **Epson TM (POS impact)** | ESC/POS | TM-U220/U295/U325 | `ESC @` init | `ESC t n` codepage select | feed+autocut `GS V` | native USB (VID 0x04B8) |
| **IBM / Lexmark Proprinter (PPDS)** | IBM PPDS (Personal Printer Data Stream) | Proprinter II/III/XL/XL24, 4201/4202/4207/4208, Lexmark Forms 2380/2390/2480/2580/4227 | `ESC @` init; `DC1` enable, `DC3` ignored | code-page select `ESC` + page-number bytes (MSB first) | `FF`; cut-sheet handling | Lexmark VID 0x043D (native on Forms-Plus USB); IBM vintage via bridge |
| **OKI MICROLINE** | MICROLINE native **+** IBM Proprinter III / Epson FX emulation (factory = IBM) | ML320/321/390/391 Turbo, ML420/421/490/491 | `ESC @` (in emulation) | via active emulation's codepage cmds | `FF`; tractor + bottom feed | ML390+ native USB (OKI VID 0x06BC); ML320 via bridge |
| **Star dot-impact** | STAR line mode **and/or** ESC/POS (jumper-selected) | SP500/SP512/SP542/SP700/SP742 | `ESC @` | per active mode | feed + autocut | Star VID 0x0519 (native USB on POS units) |
| **Citizen dot-impact** | ESC/POS (existing `citizen-cts2000` already shipped) | CT-S2000 (thermal, already done), CBM-1000, iDP-3550 | `ESC @` | `ESC t n` (CP866 etc. — already wired) | feed + cut | Citizen Systems VID; CT-S2000 already in registry |
| **Panasonic KX-P** | Epson FX / IBM Proprinter emulation (no meaningful native) | KX-P1124/1150/1170/1180/2023/2130 | `ESC @` (emulation) | via emulation codepage | `FF`; tractor/friction | vintage — bridge only |
| **Tally / TallyGenicom** | Epson + IBM Proprinter emulation (MT/T2xxx line printers) | T2030/T2040/T2150, MT645 | `ESC @` (emulation) | via emulation | `FF`; line-printer paper | mostly parallel → bridge |
| **Seiko** | varies (instrument/label) — model-specific | DPU/SLP series | model-specific | model-specific | model-specific | LOW data; defer unless a target unit is in hand |
| **generic / juki-*** (existing) | minimal / daisywheel | already shipped | already shipped | n/a | already shipped | already shipped |

**Confidence notes:**
- Command-language assignments are HIGH (vendor manuals cited).
- Specific native-USB PIDs are HIGH only for Epson LX-350 (0x0046) and LQ-350 (0x0047); all other model-level PIDs are LOW and should be filled at hardware-verification time, not guessed.
- The honest takeaway: **most vintage targets have no PID to match** — they are bridge-only and selected manually. Auto-detection meaningfully applies to the *modern native-USB* subset (Epson LQ-590/690/TM, OKI ML390, Star/Citizen POS, Lexmark Forms-Plus USB).

Sources: [Epson ESC/P Reference Manual (Dec 1997, escp2ref.pdf)](https://files.support.epson.com/pdf/general/escp2ref.pdf); [Epson ESC/P2 & FX command list](https://support2.epson.net/manuals/english/page/epl_5800/ref_g/APCOM_3.HTM); [IBM PPDS & Epson ESC/P control codes list](https://www.ibm.com/support/pages/list-ibm-ppds-and-epson-escp-control-codes-and-escape-sequences); [IBM Proprinter XL24 Programmer's Guide (psi-matrix)](https://psi-matrix.eu/wordpress/wp-content/uploads/2016/08/Programmers-Guide-IBM-Proprinter-XL24.pdf); [Personal Printer Data Stream (Wikipedia)](https://en.wikipedia.org/wiki/Personal_Printer_Data_Stream); [OKI Microline 320/321 Turbo User's Guide](https://www.ricelake.com/media/aytf5gxr/m_ml320-321_turbo_-user_guide.pdf) (emulations + ML commands p.94); [OKI ML390/391 Turbo guide (archive.org)](https://archive.org/details/oki-microline-ml-390-391-turbo-users-guide); [Star dot-impact STAR command spec rev 1.91](https://www.starmicronics.com/support/Mannualfolder/dot_star_cm_en.pdf); [Star ESC/POS command spec](https://www.starmicronics.com/support/Mannualfolder/escpos_cm_en.pdf); [Epson VID 0x04B8 / LX-350 / LQ-350 PIDs](https://the-sz.com/products/usbid/index.php?v=0x04B8); [OKI VID 0x06BC](https://devicehunt.com/view/type/usb/vendor/06BC); [Lexmark VID 0x043D](https://www.the-sz.com/products/usbid/index.php?v=0x043D); [Star VID 0x0519](https://the-sz.com/products/usbid/?v=0x0519).

---

## Direct-mode controls users expect

| Control | Expectation | Existing field support | Gap for v1.6 |
|---|---|---|---|
| **Init / reset** | `ESC @` on connect; reset clears style/codepage state | `init_sequence`, `reset_sequence` ✓ | Populate per family from manuals (conservative) |
| **Status readback** | "Paper out / busy" *if* hardware supports it | none | Add **only** for confirmed bidirectional native-USB printer-class devices; **anti-feature for bridges** (write-only). Document limitation |
| **Form feed / eject** | On-demand + end-of-doc | `formfeed_on_close`, `end_of_response_sequence` ✓ | Expose user-triggered FF action in standalone app; per-family paper policy field |
| **Paper handling** | tractor vs cut-sheet vs receipt-cut behavior | partial via FF + end-of-response | Formalize a paper-handling policy enum/field per family |
| **Codepage switching** | non-ASCII prints correctly | `codepage_command`, `text_codec`, `text_fallback` ✓ (untracked) | Formalize as tracked requirement; extend `ESC t n` / `ESC R n` per family |
| **International char set** | accented Latin / Cyrillic / line-draw | covered by codepage + `text_fallback` transliteration ✓ | Per-family default codepage values |

---

## Standalone packaging expectations

| Aspect | User expectation | Recommendation | Complexity |
|---|---|---|---|
| **macOS deliverable** | Double-clickable thing, no Python/uv install | PyInstaller **`.app` bundle (onedir)**, not `--onefile`. onefile re-extracts to temp each launch → slow start, Gatekeeper/AV friction, harder to sign | MEDIUM |
| **First-run behavior** | App opens, finds the printer (or simulator) automatically | Reuse existing v1.4 smart-startup + setup screen. For bridge-only, jump to family picker. No new UX needed | LOW (reuse) |
| **Architecture** | Works on Intel + Apple Silicon | `--target-arch universal2` (bonus) or two arch-specific builds | MEDIUM |
| **Code signing / notarization** | No "unidentified developer" block | Sign + notarize; updated 2025 PyInstaller workflows exist. Otherwise document the right-click-Open workaround | MEDIUM-HIGH |
| **Build host** | n/a | **Must build on macOS for a Mac `.app`** — no cross-compile. CI = macOS runner | LOW |
| **Linux bonus** | single binary is idiomatic | `--onefile` acceptable here; pyusb/libusb bundling is the main risk | MEDIUM |
| **Bundling traps** | app must actually run | Hidden imports (Textual/Rich lazy imports, backend SDKs), libusb dylib for pyusb, sounddevice/PortAudio native lib, data files. Expect a `.spec` with explicit `hiddenimports`/`binaries` | MEDIUM-HIGH |

Sources: [PyInstaller manual 6.20](https://www.pyinstaller.org/); [PyInstaller macOS .app / universal2 guidance](https://pyinstaller.org/_/downloads/en/stable/pdf/); [PyInstaller onefile vs onedir 2025 guide](https://ahmedsyntax.com/pyinstaller-onefile/); [macOS code signing + notarization gist (Feb 2025)](https://gist.github.com/txoof/0636835d3cc65245c6288b2374799c43); [Real Python PyInstaller guide](https://realpython.com/pyinstaller-python/).

---

## Feature Dependencies

```
Bridge-chip detection registry (new data table)
    └──enables──> Two-tier detection (bridge → manual family pick; native-USB → auto-suggest)
                       └──requires──> Per-family profiles grouped by command language
                                          └──requires──> Verified control codes (manuals, leave-empty rule)
                                                             └──extends──> existing codepage/text_codec/text_fallback fields
                                                                              (formalize untracked work first)

Richer direct-mode profile fields (init/reset/status/paper-policy)
    └──requires──> PrinterProfile dataclass extension (status + paper-handling fields)
    └──depends-on──> code refactor (driver/profile architecture, known tech-debt list)

Standalone PyInstaller app
    └──depends-on──> code refactor (module → package reorg; clean entry point)
    └──requires──> native-lib bundling resolved (libusb, PortAudio, hidden imports)
    └──benefits-from──> first-run reuses existing v1.4 setup screen (no new UX)
```

**Ordering consequences for the roadmap:**
1. Formalize the untracked codepage/`text_codec`/`text_fallback` work into tracked requirements **before** extending it per family (it's the foundation other families build on).
2. The PrinterProfile dataclass extension (status/paper-policy fields) should land with or just after the driver/profile refactor, since both touch the same surface.
3. Bridge-chip registry is independent of the profile work and can be parallelized — but the setup-screen integration depends on both.
4. PyInstaller packaging should come **last** (after refactor stabilizes the entry point); packaging a moving target wastes effort on `.spec` churn.

---

## MVP Recommendation

**Minimum for v1.6 to deliver its promise:**
1. **Bridge-chip detection registry** (CH341 parallel 0x5584, Prolific, FTDI, MosChip) + "bridge found → pick your family" fallback. *This is the single highest-leverage item — it's what makes "broad detection" real for vintage units.*
2. **Per-command-language profiles** for the high-population families: Epson ESC/P (FX/LX), Epson ESC/P2 (LQ), IBM/Lexmark PPDS, OKI MICROLINE (via Epson/IBM emulation), Panasonic KX-P (emulation). Verified `ESC @` + codepage codes; leave-empty elsewhere.
3. **Formalize** the existing codepage/transliteration features as tracked requirements + extend per family.
4. **macOS `.app` via PyInstaller** (onedir), reusing existing first-run setup screen.

**Defer (nice-to-have, not MVP):**
- OKI MICROLINE *native* mode (emulation modes cover the need) — reason: emulation already gives full function; native adds depth, not capability.
- Star native STAR line mode + Tally/Seiko profiles — reason: lower install base, lower data confidence; add when a target unit is available to verify.
- Status/busy readback — reason: unreliable on the bridge path that dominates vintage; risk of false confidence.
- macOS notarization + universal2 + Linux binary — reason: signing/notarization is the long pole; ship a working `.app` first, harden distribution second.

---

## Sources

- [Epson ESC/P Reference Manual (Dec 1997)](https://files.support.epson.com/pdf/general/escp2ref.pdf) — HIGH (vendor)
- [Epson ESC/P2 & FX command list](https://support2.epson.net/manuals/english/page/epl_5800/ref_g/APCOM_3.HTM) — HIGH (vendor)
- [IBM PPDS & Epson ESC/P control codes](https://www.ibm.com/support/pages/list-ibm-ppds-and-epson-escp-control-codes-and-escape-sequences) — HIGH (vendor)
- [IBM Proprinter XL24 Programmer's Guide](https://psi-matrix.eu/wordpress/wp-content/uploads/2016/08/Programmers-Guide-IBM-Proprinter-XL24.pdf) — HIGH (vendor manual)
- [Personal Printer Data Stream (Wikipedia)](https://en.wikipedia.org/wiki/Personal_Printer_Data_Stream) — MEDIUM
- [OKI Microline 320/321 Turbo User's Guide](https://www.ricelake.com/media/aytf5gxr/m_ml320-321_turbo_-user_guide.pdf) — HIGH (emulations, ML commands p.94)
- [OKI ML390/391 Turbo guide](https://archive.org/details/oki-microline-ml-390-391-turbo-users-guide) — HIGH
- [Star dot-impact STAR command spec rev 1.91](https://www.starmicronics.com/support/Mannualfolder/dot_star_cm_en.pdf) — HIGH (vendor)
- [Star ESC/POS command spec](https://www.starmicronics.com/support/Mannualfolder/escpos_cm_en.pdf) — HIGH (vendor)
- [the-sz USB ID DB — CH341 modes (0x1A86)](https://the-sz.com/products/usbid/index.php?v=0x1A86) — HIGH (0x5584 parallel verified)
- [Linux CH341 driver source (modes)](https://github.com/RichStrong/CH341A_linux_driver/blob/master/ch34x_pis.c) — HIGH
- [Epson VID 0x04B8, LX-350/LQ-350 PIDs](https://the-sz.com/products/usbid/index.php?v=0x04B8) — MEDIUM (model PIDs partial)
- [OKI VID 0x06BC](https://devicehunt.com/view/type/usb/vendor/06BC) — MEDIUM
- [Lexmark VID 0x043D](https://www.the-sz.com/products/usbid/index.php?v=0x043D) — MEDIUM
- [Star VID 0x0519](https://the-sz.com/products/usbid/?v=0x0519) — MEDIUM
- [USB-LPT serial-adapter handshake limitation](https://electronics.alibaba.com/question/parallel-to-usb-adapter-does-it-really-work) — MEDIUM (corroborated by multiple sources)
- [PyInstaller manual 6.20](https://www.pyinstaller.org/) — HIGH
- [PyInstaller onefile vs onedir (2025)](https://ahmedsyntax.com/pyinstaller-onefile/) — MEDIUM
- [macOS code signing + notarization (Feb 2025)](https://gist.github.com/txoof/0636835d3cc65245c6288b2374799c43) — MEDIUM

---
*Feature research for: USB dot-matrix printer fleet detection + per-family direct-mode profiles + PyInstaller standalone packaging*
*Researched: 2026-06-12*
