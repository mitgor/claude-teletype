"""Per-family printer profile catalog (S03).

Each module in this package covers one printer family and exports
``PROFILES: dict[str, PrinterProfile]``. ``profiles._load_catalog()``
auto-discovers every module here via pkgutil and merges each PROFILES
into ``BUILTIN_PROFILES`` — adding a printer family is exactly one new
file in this package, no registration edits anywhere (ARCH-03).

Cross-family aliases (dataclasses.replace of another family's profile)
import the sibling catalog module explicitly, e.g. in oki.py::

    from claude_teletype.printing.catalog import epson as _epson
    PROFILES["oki-ml-epson"] = dataclasses.replace(
        _epson.PROFILES["escp"], ...)

Sibling imports are cycle-safe: catalog modules import only profiles.py's
dataclass, and profiles.py imports the catalog function-locally.

Catalog modules import PrinterProfile from
``claude_teletype.printing.profiles`` at module top. That is safe ONLY
because profiles.py imports this package function-locally (inside
``_load_catalog``). NEVER import the catalog at profiles.py module top —
that closes the import cycle.

Catalog rules (R022/R023/R024): every byte sequence is verbatim from a
vendor manual with a citation comment naming manual + section. A
capability that cannot be verified stays empty bytes and gets a
``human_needed`` entry instead — fabrication is forbidden.
"""
