"""Small display-formatting helpers shared across UI surfaces.

Presentation-only: these never touch the math or the stored values,
just how a number reads on screen / in an export.
"""

from __future__ import annotations

from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from gwdrawdown.analysis import AnalysisInputs


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


def format_source_aquifer(inputs: AnalysisInputs) -> str:
    """One-line description of the run's source aquifer.

    Shared by the results-page run summary and the PDF input-parameters
    table so the two can't drift apart.

    Aquifer number leads, material in brackets, name and subtype
    trailing as context — officers refer to aquifers by number
    (client feedback, 2026-07). Examples::

        Aquifer 199 (Sand and Gravel) — Cowichan Valley, subtype 1a
        Other — aquifer not delineated (Unconsolidated); nearest mapped:
            Aquifer 199 (Sand and Gravel), 120 m away

    In manual mode the ``nearest mapped`` clause is what shows the run
    was declared undelineated *despite* mapped polygons being nearby;
    it is omitted when nothing was found within the search radius.
    """
    if inputs.is_manual_mode:
        text = f"{inputs.source_aquifer_name} ({inputs.manual_material or '—'})"
        if inputs.nearest_mapped_aquifer:
            text += f"; nearest mapped: {inputs.nearest_mapped_aquifer}"
        else:
            text += "; no mapped aquifer nearby"
        return text

    material = inputs.source_aquifer_material or "material not recorded"
    text = f"Aquifer {inputs.source_aquifer_id} ({material})"
    if inputs.source_aquifer_name:
        text += f" — {inputs.source_aquifer_name}"
    return f"{text}, subtype {inputs.source_subtype_code or '—'}"
