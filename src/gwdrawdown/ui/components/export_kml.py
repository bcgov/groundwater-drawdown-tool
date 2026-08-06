"""KML export of an analysis run.

Produces a Google-Earth-ready ``.kml`` document: one Placemark for the
proposed pumping well plus one per observation well, each colour-coded
by its `WellStatus` and carrying the full per-well result row as
``<ExtendedData>``. Clients are more familiar with Google Earth than
with GeoJSON, so KML is the spatial-export format — it replaced the
originally-planned GeoJSON for that reason.

Each well marker is also *scaled by predicted impact* (an inline
``<IconStyle><scale>``), echoing the proportional marker sizing on the
results-page map. Wells with no computable impact render at the
minimum scale.

The module is pure: it takes an (override-applied) `AnalysisResult` and
returns a KML string. No Dash, no I/O — unit-testable directly.

Coordinates: well points are stored in BC Albers on `WellResult`; they
are converted back to WGS84 lon/lat here (KML is WGS84-only). The
pumping well already carries WGS84 lon/lat on `AnalysisInputs`.
"""

from __future__ import annotations

from xml.sax.saxutils import escape

from gwdrawdown.analysis import AnalysisResult, WellResult
from gwdrawdown.core.crs_utils import to_wgs84
from gwdrawdown.ui import disclaimers
from gwdrawdown.ui.components.palette import PUMPING_COLOR, STATUS_COLOR
from gwdrawdown.ui.format_utils import format_aquifer_id, format_licence_status

# A neutral white circle icon hosted by Google; the per-marker
# ``<color>`` element tints it, so one icon serves every status.
_ICON_HREF = "http://maps.google.com/mapfiles/kml/shapes/placemark_circle.png"

# Marker-scale bounds for the impact-proportional sizing. Wells with
# no computable impact_fraction sit at the minimum.
_MIN_SCALE = 0.9
_MAX_SCALE = 2.1

# Human-readable labels for the four override-able fields, mirrored
# from `results_table._EDITABLE_FIELD_LABELS` so the "Edited" value in
# the KML matches what the officer sees in the results table.
_EDITABLE_FIELD_LABELS: dict[str, str] = {
    "static_water_level_m": "NPL",
    "finished_well_depth_m": "Finished Depth",
    "stickup_m": "Stickup",
    "top_of_fracture_or_aquifer_or_screen_m": "Top of Frac/Screen",
}


def _kml_colour(hex_rgb: str) -> str:
    """Convert ``#rrggbb`` to KML's opaque ``aabbggrr`` byte order."""
    h = hex_rgb.lstrip("#")
    r, g, b = h[0:2], h[2:4], h[4:6]
    return f"ff{b}{g}{r}".lower()


def _fmt(value: object, digits: int) -> str:
    """Format a numeric value to ``digits`` decimals, '' for None."""
    if value is None:
        return ""
    try:
        return f"{float(value):.{digits}f}"
    except (TypeError, ValueError):
        return str(value)


def _impact_scale(w: WellResult, max_impact: float) -> float:
    """Marker scale proportional to predicted impact, clamped to bounds.

    Mirrors `results_map._radius_for_well`: linear in
    ``impact_fraction`` relative to the run's largest impact, with
    no-impact wells (SAD uncomputable) pinned at the minimum.
    """
    if w.impact_fraction is None or max_impact <= 0:
        return _MIN_SCALE
    fraction = max(0.0, min(1.0, w.impact_fraction / max_impact))
    return _MIN_SCALE + fraction * (_MAX_SCALE - _MIN_SCALE)


def _well_data(w: WellResult, edited: str) -> list[tuple[str, str]]:
    """Flatten a `WellResult` to ordered (name, value) pairs for KML.

    Order matches the per-well details table in the results page and
    the PDF export so the three artifacts read consistently.
    """
    impact_pct = (
        w.impact_fraction * 100 if w.impact_fraction is not None else None
    )
    return [
        ("WTN", str(w.well_tag_number)),
        (
            "Aquifer ID",
            format_aquifer_id(w.aquifer_id, not_delineated=w.aquifer_not_delineated),
        ),
        ("Intended Use", w.intended_water_use or ""),
        ("Licence Status", format_licence_status(w.licence_status)),
        ("Distance (m)", _fmt(w.distance_m, 1)),
        ("Finished Depth (m)", _fmt(w.finished_well_depth_m, 2)),
        ("Total Depth (m)", _fmt(w.total_depth_drilled_m, 2)),
        ("Bedrock Depth (m)", _fmt(w.bedrock_depth_m, 2)),
        ("Yield (m3/day)", _fmt(w.yield_m3_per_day, 2)),
        ("NPL (m)", _fmt(w.static_water_level_m, 2)),
        ("Stickup (m)", _fmt(w.stickup_m, 2)),
        ("GWELLS Material", w.aquifer_material_gwells or ""),
        ("Reassigned Material", w.reassigned_material),
        ("Drawdown (m)", _fmt(w.drawdown_m, 4)),
        ("Top of Frac/Screen (m)", _fmt(w.top_of_fracture_or_aquifer_or_screen_m, 2)),
        ("SAD (m)", _fmt(w.sad_m, 3)),
        ("Impact %", _fmt(impact_pct, 1)),
        ("Status", w.well_status.value),
        ("Edited", edited),
        ("GWELLS record", w.well_details_url or ""),
    ]


def _extended_data(pairs: list[tuple[str, str]]) -> str:
    rows = "\n".join(
        f'        <Data name="{escape(name)}">'
        f"<value>{escape(value)}</value></Data>"
        for name, value in pairs
    )
    return f"      <ExtendedData>\n{rows}\n      </ExtendedData>"


def _icon_style(colour_hex: str, scale: float, *, label_scale: float = 0.8) -> str:
    """An inline ``<Style>`` block: tinted circle icon at ``scale``."""
    return (
        "      <Style>\n"
        "        <IconStyle>\n"
        f"          <color>{_kml_colour(colour_hex)}</color>\n"
        f"          <scale>{scale:.2f}</scale>\n"
        f"          <Icon><href>{_ICON_HREF}</href></Icon>\n"
        "        </IconStyle>\n"
        f"        <LabelStyle><scale>{label_scale:.1f}</scale></LabelStyle>\n"
        "      </Style>"
    )


def _placemark(
    name: str,
    style_block: str,
    lon: float,
    lat: float,
    pairs: list[tuple[str, str]],
    description: str = "",
) -> str:
    desc = (
        f"      <description>{escape(description)}</description>\n"
        if description
        else ""
    )
    return (
        f"    <Placemark>\n"
        f"      <name>{escape(name)}</name>\n"
        f"{style_block}\n"
        f"{desc}"
        f"{_extended_data(pairs)}\n"
        f"      <Point><coordinates>{lon:.6f},{lat:.6f},0</coordinates></Point>\n"
        f"    </Placemark>"
    )


def build_kml(
    result: AnalysisResult,
    *,
    overrides_by_wtn: dict[int, dict[str, float | None]] | None = None,
) -> str:
    """Serialise an `AnalysisResult` to a KML document string.

    Args:
        result: The analysis result, with any per-well overrides
            already applied (the callers pass the override-applied
            result from `analysis.apply_overrides`).
        overrides_by_wtn: The raw per-WTN override map, used only to
            populate each well's "Edited" field. ``None`` means no
            overrides.

    Returns:
        A complete KML document as a UTF-8 string.
    """
    overrides_by_wtn = overrides_by_wtn or {}
    inputs = result.inputs

    pumping_pairs = [
        ("Run ID", result.run_id),
        ("Run timestamp", result.run_timestamp.strftime("%Y-%m-%d %H:%M:%S")),
        ("Source aquifer", inputs.source_aquifer_name),
        ("T (m2/day)", _fmt(inputs.transmissivity_m2_per_day, 4)),
        ("S", _fmt(inputs.storativity, 6)),
        ("Q (m3/day)", _fmt(inputs.Q_m3_per_day, 3)),
        ("Duration (days)", _fmt(inputs.duration_days, 1)),
        ("Buffer radius (m)", _fmt(inputs.buffer_radius_m, 0)),
    ]
    pumping = _placemark(
        "Proposed pumping well",
        _icon_style(PUMPING_COLOR, 1.4, label_scale=1.0),
        inputs.pumping_lon,
        inputs.pumping_lat,
        pumping_pairs,
        description="Proposed groundwater withdrawal location.",
    )

    impacts = [
        w.impact_fraction for w in result.wells if w.impact_fraction is not None
    ]
    max_impact = max(impacts) if impacts else 1.0

    well_placemarks: list[str] = []
    for w in sorted(result.wells, key=lambda x: x.distance_m):
        lon, lat = to_wgs84(w.x_albers, w.y_albers)
        cell_overrides = overrides_by_wtn.get(w.well_tag_number, {})
        edited = ", ".join(
            label
            for field_name, label in _EDITABLE_FIELD_LABELS.items()
            if field_name in cell_overrides
        )
        colour = STATUS_COLOR.get(w.well_status, "#666666")
        scale = _impact_scale(w, max_impact)
        well_placemarks.append(
            _placemark(
                f"WTN {w.well_tag_number}",
                _icon_style(colour, scale),
                lon,
                lat,
                _well_data(w, edited),
            )
        )

    doc_name = f"Groundwater Drawdown Analysis — {result.run_id}"
    doc_desc = (
        "Screening-level drawdown analysis. Marker colour shows well "
        "status; marker size is proportional to predicted impact. "
        + disclaimers.INTERPRETATION_FULL
    )
    wells_folder = (
        "    <Folder>\n"
        "      <name>Observation wells</name>\n"
        + "\n".join(well_placemarks)
        + "\n    </Folder>"
        if well_placemarks
        else "    <Folder><name>Observation wells</name></Folder>"
    )

    return (
        '<?xml version="1.0" encoding="UTF-8"?>\n'
        '<kml xmlns="http://www.opengis.net/kml/2.2">\n'
        "  <Document>\n"
        f"    <name>{escape(doc_name)}</name>\n"
        f"    <description>{escape(doc_desc)}</description>\n"
        f"{pumping}\n"
        f"{wells_folder}\n"
        "  </Document>\n"
        "</kml>\n"
    )
