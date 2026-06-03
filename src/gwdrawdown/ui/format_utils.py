"""Small display-formatting helpers shared across UI surfaces.

Presentation-only: these never touch the math or the stored values,
just how a number reads on screen / in an export.
"""

from __future__ import annotations


def format_float(value: float | None) -> str:
    """Render a float in fixed-point with trailing zeros stripped.

    Python's default ``str(0.00003)`` — and ``f"{0.00003:g}"`` — yield
    ``"3e-05"``, which is hard to read in a Water Officer-facing UI for
    storativity values like ``0.00003`` (subtype 5a) or ``0.00064``
    (6a/6b). Force fixed-point so the on-screen value matches what a
    hydrogeologist expects to see and type.

    Returns an empty string for ``None`` so callers can drop it straight
    into an f-string. Whole numbers lose their trailing ``.0``
    (``250.0`` -> ``"250"``).
    """
    if value is None:
        return ""
    formatted = f"{value:.10f}".rstrip("0").rstrip(".")
    return formatted if formatted else "0"
