"""Per-family printer profile catalog (S03).

Each module in this package covers one printer family and exports
``PROFILES: dict[str, PrinterProfile]``. ``profiles._load_catalog()``
merges every module's PROFILES into ``BUILTIN_PROFILES``.

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
