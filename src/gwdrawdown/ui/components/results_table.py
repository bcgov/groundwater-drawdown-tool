"""Results-page tables: at-risk summary + full per-well details.

Two tables share styling so the at-risk summary looks like a focused
extract of the full table. Both use ``dash_table.DataTable``'s
built-in CSV export (the at-risk one is the artifact attached to the
licence-assessment file; matches `InputValues!B30:E32` in the legacy
Excel).

All numeric values are in SI (metres, m³/day, m²/day) per the chosen
display convention. CLIENT_TBD: Q14 — confirm officers prefer SI to
the legacy iMap CSV's mix of feet + US GPM.

In sub-stage 4c.2 the full table gains editable cells for NPL,
finished depth, stickup, and top-of-fracture/screen — all the
override columns are already in `WellResult` (populated as None
today) so 4c.2 only adds the editing UI and the per-row recompute
callback, not new fields.
"""

from __future__ import annotations

import csv
import io

from dash import Input, Output, State, callback, dash_table, dcc, html, no_update

from gwdrawdown.analysis import AnalysisResult, WellResult
from gwdrawdown.core.flagging import WellStatus

_EXPORT_BUTTON_STYLE = {
    "padding": "0.4rem 0.9rem",
    "border": "1px solid #1565c0",
    "backgroundColor": "white",
    "color": "#1565c0",
    "borderRadius": "3px",
    "cursor": "pointer",
    "fontSize": "0.85rem",
}

# Column id -> human label for the full per-well table. Order matches
# PROJECT_PLAN.md §4.1 point 5.
_FULL_COLUMNS: list[tuple[str, str, str]] = [
    # (column id, display name, type)
    ("well_tag_number", "WTN", "numeric"),
    ("intended_water_use", "Intended Use", "text"),
    ("aquifer_id", "Aquifer ID", "numeric"),
    ("finished_well_depth_m", "Finished Depth (m)", "numeric"),
    ("total_depth_drilled_m", "Total Depth (m)", "numeric"),
    ("bedrock_depth_m", "Bedrock Depth (m)", "numeric"),
    ("yield_m3_per_day", "Yield (m³/day)", "numeric"),
    ("static_water_level_m", "NPL (m)", "numeric"),
    ("stickup_m", "Stickup (m)", "numeric"),
    ("aquifer_material_gwells", "GWELLS Material", "text"),
    ("reassigned_material", "Reassigned Material", "text"),
    ("distance_m", "Distance (m)", "numeric"),
    ("drawdown_m", "Drawdown (m)", "numeric"),
    ("top_of_fracture_or_aquifer_or_screen_m", "Top of Frac/Screen (m)", "numeric"),
    ("sad_m", "SAD (m)", "numeric"),
    ("impact_pct", "Impact %", "numeric"),
    ("well_status", "Status", "text"),
]

_AT_RISK_COLUMNS: list[tuple[str, str, str]] = [
    ("well_tag_number", "WTN", "numeric"),
    ("reassigned_material", "Reassigned Material", "text"),
    ("sad_m", "SAD (m)", "numeric"),
    ("drawdown_m", "Impact (m)", "numeric"),
    ("impact_pct", "Impact %", "numeric"),
]

_NUMERIC_FORMAT_BY_COLUMN: dict[str, str] = {
    "well_tag_number": "{:d}",
    "aquifer_id": "{:d}",
    "finished_well_depth_m": "{:.2f}",
    "total_depth_drilled_m": "{:.2f}",
    "bedrock_depth_m": "{:.2f}",
    "yield_m3_per_day": "{:.2f}",
    "static_water_level_m": "{:.2f}",
    "stickup_m": "{:.2f}",
    "distance_m": "{:.1f}",
    "drawdown_m": "{:.4f}",
    "sad_m": "{:.3f}",
    "impact_pct": "{:.1f}",
}

_STATUS_PALETTE: dict[WellStatus, tuple[str, str]] = {
    WellStatus.OK: ("#e8f5e9", "#2e7d32"),
    WellStatus.AT_RISK: ("#ffebee", "#c62828"),
    WellStatus.INSUFFICIENT_DATA: ("#f5f5f5", "#616161"),
    WellStatus.SUSPECT_DATA: ("#fff3e0", "#ef6c00"),
    WellStatus.OUTSIDE_VALIDITY: ("#f3e5f5", "#7b1fa2"),
}

# Per-column widths for the full per-well table. Numeric columns are
# tightened so 17 columns fit a 1366-wide screen with horizontal scroll
# only kicking in below ~1200 px. Text columns are wider since they
# carry longer values ("Commercial and Industrial", "Unconsolidated").
_COLUMN_WIDTHS: dict[str, str] = {
    "well_tag_number": "95px",
    "intended_water_use": "140px",
    "aquifer_id": "70px",
    "finished_well_depth_m": "95px",
    "total_depth_drilled_m": "85px",
    "bedrock_depth_m": "90px",
    "yield_m3_per_day": "95px",
    "static_water_level_m": "75px",
    "stickup_m": "80px",
    "aquifer_material_gwells": "120px",
    "reassigned_material": "130px",
    "distance_m": "85px",
    "drawdown_m": "90px",
    "top_of_fracture_or_aquifer_or_screen_m": "115px",
    "sad_m": "75px",
    "impact_pct": "75px",
    "well_status": "150px",
}


def _per_column_widths() -> list[dict]:
    """Build the dash_table ``style_cell_conditional`` width rules."""
    return [
        {
            "if": {"column_id": cid},
            "minWidth": w,
            "width": w,
            "maxWidth": w,
        }
        for cid, w in _COLUMN_WIDTHS.items()
    ]


def _format_cell(column_id: str, value: object) -> object:
    if value is None:
        return ""
    fmt = _NUMERIC_FORMAT_BY_COLUMN.get(column_id)
    if fmt is None:
        return value
    try:
        return fmt.format(value)
    except (TypeError, ValueError):
        return value


def _row_dict(w: WellResult, column_ids: list[str]) -> dict[str, object]:
    """Project a `WellResult` to the dict shape `dash_table` expects.

    Pre-formats numeric values as strings so `dash_table` displays them
    consistently regardless of whether the column ends up sortable as
    numeric or text.
    """
    impact_pct = w.impact_fraction * 100 if w.impact_fraction is not None else None
    raw: dict[str, object] = {
        "well_tag_number": w.well_tag_number,
        "intended_water_use": w.intended_water_use,
        "aquifer_id": w.aquifer_id,
        "finished_well_depth_m": w.finished_well_depth_m,
        "total_depth_drilled_m": w.total_depth_drilled_m,
        "bedrock_depth_m": w.bedrock_depth_m,
        "yield_m3_per_day": w.yield_m3_per_day,
        "static_water_level_m": w.static_water_level_m,
        "stickup_m": w.stickup_m,
        "aquifer_material_gwells": w.aquifer_material_gwells,
        "reassigned_material": w.reassigned_material,
        "distance_m": w.distance_m,
        "drawdown_m": w.drawdown_m,
        "top_of_fracture_or_aquifer_or_screen_m": w.top_of_fracture_or_aquifer_or_screen_m,
        "sad_m": w.sad_m,
        "impact_pct": impact_pct,
        "well_status": w.well_status.value,
    }
    return {col: _format_cell(col, raw.get(col)) for col in column_ids}


def _columns_for(spec: list[tuple[str, str, str]]) -> list[dict]:
    return [{"id": cid, "name": name, "type": ctype} for cid, name, ctype in spec]


def _status_conditional_styles(column_id: str = "well_status") -> list[dict]:
    """Background+text colour rules applied to the Status cell."""
    rules: list[dict] = []
    for status, (bg, fg) in _STATUS_PALETTE.items():
        rules.append(
            {
                "if": {
                    "filter_query": f'{{{column_id}}} = "{status.value}"',
                    "column_id": column_id,
                },
                "backgroundColor": bg,
                "color": fg,
                "fontWeight": "bold",
            }
        )
    return rules


def make_at_risk_table(result: AnalysisResult) -> html.Div:
    """Filtered to ``WellStatus.AT_RISK`` only.

    SUSPECT_DATA wells deliberately do not appear here even though
    their Impact % may be non-trivial — the at-risk summary is what's
    attached to the licence file and a "data review needed" row would
    be misleading there. They appear only in the full table.
    """
    column_ids = [c[0] for c in _AT_RISK_COLUMNS]
    at_risk = [
        _row_dict(w, column_ids)
        for w in sorted(
            (w for w in result.wells if w.well_status == WellStatus.AT_RISK),
            key=lambda w: -(w.impact_fraction or 0),
        )
    ]

    if not at_risk:
        body: object = html.P(
            "No wells flagged AT_RISK at the configured threshold.",
            style={"color": "#555", "fontStyle": "italic"},
        )
    else:
        body = dash_table.DataTable(
            id="at-risk-summary",
            columns=_columns_for(_AT_RISK_COLUMNS),
            data=at_risk,
            sort_action="native",
            filter_action="native",
            page_action="native",
            page_size=10,
            fixed_rows={"headers": True},
            style_table={
                "overflowX": "auto",
                "overflowY": "auto",
                "maxHeight": "60vh",
                "minWidth": "100%",
            },
            style_cell={
                "fontFamily": "sans-serif",
                "fontSize": "0.9rem",
                "padding": "0.5rem",
                "textAlign": "left",
                "whiteSpace": "normal",
            },
            style_cell_conditional=_per_column_widths(),
            style_header={
                "backgroundColor": "#fafafa",
                "fontWeight": "bold",
                "borderBottom": "2px solid #ccc",
                "whiteSpace": "normal",
            },
        )

    return html.Div(
        [
            html.H2(
                f"At-risk wells ({result.n_at_risk})",
                style={"marginTop": "0.5rem"},
            ),
            html.P(
                "Wells whose predicted drawdown reaches "
                f"{int(result.inputs.at_risk_fraction * 100)}% of "
                "their Safe Available Drawdown.",
                style={"fontSize": "0.9rem", "color": "#555"},
            ),
            html.Button(
                "Export CSV",
                id="at-risk-export-btn",
                n_clicks=0,
                style={**_EXPORT_BUTTON_STYLE, "marginBottom": "0.5rem"},
            ),
            dcc.Download(id="at-risk-download"),
            body,
        ],
        style={"marginBottom": "2rem"},
    )


def make_full_well_table(result: AnalysisResult) -> html.Div:
    """All observation wells, sorted ascending by distance by default."""
    column_ids = [c[0] for c in _FULL_COLUMNS]
    rows = [
        _row_dict(w, column_ids)
        for w in sorted(result.wells, key=lambda w: w.distance_m)
    ]

    if not rows:
        body: object = html.P(
            "No wells returned by the buffer query.",
            style={"color": "#555", "fontStyle": "italic"},
        )
    else:
        body = dash_table.DataTable(
            id="per-well-details",
            columns=_columns_for(_FULL_COLUMNS),
            data=rows,
            sort_action="native",
            filter_action="native",
            page_action="native",
            page_size=10,
            # Export is rendered as a separate button below; dash_table's
            # built-in `export_format` would put it inside the table
            # chrome, which we don't want.
            #
            # Sticky header row so column names stay visible during
            # vertical scroll. We deliberately do NOT use fixed_columns:
            # dash_table renders fixed-column filter inputs in a
            # separate DOM region with different CSS, leading to a
            # visible inconsistency vs. the non-fixed filter inputs
            # ("filter data..." placeholder shows in the fixed area
            # but not the non-fixed area). page_size=10 keeps the table
            # short enough that horizontal scrolling without a pinned
            # WTN column is manageable.
            fixed_rows={"headers": True},
            style_table={
                "overflowX": "auto",
                "overflowY": "auto",
                "maxHeight": "60vh",
                "minWidth": "100%",
            },
            style_cell={
                "fontFamily": "sans-serif",
                "fontSize": "0.85rem",
                "padding": "0.4rem 0.6rem",
                "textAlign": "left",
                "whiteSpace": "normal",
            },
            style_cell_conditional=_per_column_widths(),
            style_header={
                "backgroundColor": "#fafafa",
                "fontWeight": "bold",
                "borderBottom": "2px solid #ccc",
                "whiteSpace": "normal",
            },
            style_data_conditional=_status_conditional_styles(),
        )

    return html.Div(
        [
            html.H2(
                f"All wells in buffer ({result.n_total})",
                style={"marginTop": "0.5rem"},
            ),
            html.P(
                "Sortable / filterable. Export downloads the table in "
                "its current sort + filter state.",
                style={"fontSize": "0.9rem", "color": "#555"},
            ),
            html.Button(
                "Export CSV",
                id="per-well-export-btn",
                n_clicks=0,
                style={**_EXPORT_BUTTON_STYLE, "marginBottom": "0.5rem"},
            ),
            dcc.Download(id="per-well-download"),
            body,
        ],
        style={"marginBottom": "2rem"},
    )


def _table_to_csv(rows: list[dict], columns: list[dict]) -> str:
    """Serialise dash_table data + columns to a CSV string with display headers."""
    buf = io.StringIO()
    fieldnames = [c["id"] for c in columns]
    headers = {c["id"]: c["name"] for c in columns}
    writer = csv.DictWriter(buf, fieldnames=fieldnames, extrasaction="ignore")
    writer.writerow(headers)
    for row in rows:
        writer.writerow({k: row.get(k, "") for k in fieldnames})
    return buf.getvalue()


@callback(
    Output("per-well-download", "data"),
    Input("per-well-export-btn", "n_clicks"),
    State("per-well-details", "derived_virtual_data"),
    State("per-well-details", "data"),
    State("per-well-details", "columns"),
    prevent_initial_call=True,
)
def export_per_well_csv(
    _n_clicks: int,
    filtered_rows: list[dict] | None,
    raw_rows: list[dict] | None,
    columns: list[dict] | None,
) -> object:
    """Build a CSV from the per-well table's current view.

    ``derived_virtual_data`` is dash_table's post-sort, post-filter row
    list — exactly what the user sees. Falls back to the unfiltered
    ``data`` if the user hasn't interacted with the table yet
    (derived_virtual_data is then None).
    """
    rows = filtered_rows if filtered_rows is not None else raw_rows
    if not rows or not columns:
        return no_update
    return dcc.send_string(_table_to_csv(rows, columns), "per-well-details.csv")


@callback(
    Output("at-risk-download", "data"),
    Input("at-risk-export-btn", "n_clicks"),
    State("at-risk-summary", "derived_virtual_data"),
    State("at-risk-summary", "data"),
    State("at-risk-summary", "columns"),
    prevent_initial_call=True,
)
def export_at_risk_csv(
    _n_clicks: int,
    filtered_rows: list[dict] | None,
    raw_rows: list[dict] | None,
    columns: list[dict] | None,
) -> object:
    """Build a CSV from the at-risk table's current view (sort + filter aware)."""
    rows = filtered_rows if filtered_rows is not None else raw_rows
    if not rows or not columns:
        return no_update
    return dcc.send_string(_table_to_csv(rows, columns), "at-risk-summary.csv")
