"""Results-page tables: at-risk summary + full per-well details.

Two tables share styling so the at-risk summary looks like a focused
extract of the full table. Both expose a custom Export CSV button that
serialises the table's current sort + filter state.

All numeric values are in SI (metres, m³/day, m²/day) — client-confirmed
display convention (vs the legacy iMap CSV's mix of feet + US GPM).

Per-well overrides (4c.2). The full table marks four columns editable —
NPL, finished depth, stickup, top of fracture/aquifer/screen — and
fires `_capture_overrides` on every cell edit. That callback diffs the
edited row against the original BCGW value carried in a hidden
``_<field>_base`` cell, writes per-WTN deltas into the
``well-overrides`` Store, and triggers the page-level render callback
that calls `analysis.apply_overrides` and rebuilds the summary block,
stat cards, at-risk table, and the per-well table itself. Empty string
or non-numeric input is treated as "revert to base". Overridden rows
are tinted light yellow; the cell content stays as a plain numeric
string so dash_table's ``type="numeric"`` editing (including clearing
a cell back to empty) behaves normally.
"""

from __future__ import annotations

import csv
import io
from typing import Any

from dash import Input, Output, State, callback, dash_table, dcc, html, no_update

from gwdrawdown.analysis import OVERRIDABLE_FIELDS, AnalysisResult, WellResult
from gwdrawdown.core.flagging import WellStatus
from gwdrawdown.ui import disclaimers
from gwdrawdown.ui.components.palette import STATUS_PALETTE
from gwdrawdown.ui.format_utils import format_licence_status

# Light yellow row tint for any well that has an active override.
_OVERRIDE_ROW_BG = "#fff8e1"
# Light purple row tint for wells failing the Cooper-Jacob u<threshold
# advisory. Purple takes precedence over the yellow override tint
# (validity advisory is more important to surface than "you edited
# this row"), so the rule is appended AFTER the override rule in
# `style_data_conditional`.
_OUTSIDE_VALIDITY_ROW_BG = "#f3e5f5"

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
# PROJECT_PLAN.md §4.1 point 5; "Edited" is appended at the right
# as a summary of which editable cells (if any) carry an override.
_FULL_COLUMNS: list[tuple[str, str, str]] = [
    # (column id, display name, type)
    ("well_tag_number", "WTN", "numeric"),
    ("intended_water_use", "Intended Use", "text"),
    # Display-only context, never an input to any classification
    # (client-confirmed, 2026-07). Sits beside Intended Use because
    # both answer "what kind of well is this?".
    ("licence_status", "Licence", "text"),
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
    ("edited_fields", "Edited", "text"),
]

# Short, human-readable labels for the editable fields, used both in
# the "Edited" summary column and as a single source of truth if we
# ever surface them elsewhere (CSV header tooltips, PDF, etc.).
_EDITABLE_FIELD_LABELS: dict[str, str] = {
    "static_water_level_m": "NPL",
    "finished_well_depth_m": "Finished Depth",
    "stickup_m": "Stickup",
    "top_of_fracture_or_aquifer_or_screen_m": "Top of Frac/Screen",
}

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
    "top_of_fracture_or_aquifer_or_screen_m": "{:.2f}",
    "distance_m": "{:.1f}",
    "drawdown_m": "{:.4f}",
    "sad_m": "{:.3f}",
    "impact_pct": "{:.1f}",
}

# Columns the officer can override on the per-well table. Must match
# `analysis.OVERRIDABLE_FIELDS` exactly — keep the constant in lockstep.
_EDITABLE_COLUMNS: tuple[str, ...] = OVERRIDABLE_FIELDS

# Status cell colour palette is defined once in `palette.py` so the
# table, stat cards, and map markers can't drift out of sync.
_STATUS_PALETTE = STATUS_PALETTE

# Per-column widths for the full per-well table. Numeric columns are
# tightened so the table fits a 1366-wide screen with horizontal scroll
# only kicking in below ~1100 px. Text columns are wider since they
# carry longer values ("Commercial and Industrial", "Unconsolidated").
_COLUMN_WIDTHS: dict[str, str] = {
    "well_tag_number": "95px",
    "intended_water_use": "140px",
    "licence_status": "90px",
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
    "edited_fields": "180px",
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


def _well_value(w: WellResult, column_id: str) -> object:
    """Pull the column's raw value off a `WellResult`."""
    impact_pct = w.impact_fraction * 100 if w.impact_fraction is not None else None
    raw: dict[str, object] = {
        "well_tag_number": w.well_tag_number,
        "intended_water_use": w.intended_water_use,
        "licence_status": format_licence_status(w.licence_status),
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
    return raw.get(column_id)


def _row_dict(w: WellResult, column_ids: list[str]) -> dict[str, object]:
    """Project a `WellResult` to the dict shape `dash_table` expects.

    Pre-formats numeric values as strings so `dash_table` displays them
    consistently regardless of whether the column ends up sortable as
    numeric or text.
    """
    return {col: _format_cell(col, _well_value(w, col)) for col in column_ids}


def _per_well_row_dict(
    current: WellResult,
    base: WellResult,
    column_ids: list[str],
    active_overrides: dict[str, float | None],
    u_threshold: float,
) -> dict[str, Any]:
    """Build the per-well table row, including override and advisory markers.

    Editable cells carry the post-override formatted value as a plain
    numeric string. Each row also carries:

    - an ``edited_fields`` summary at the right-hand side listing the
      human-readable names of every editable cell carrying an
      override (e.g. ``"NPL, Stickup"``). This survives CSV export so
      reviewers can see at a glance which inputs the officer adjusted,
      AND drives the row's light-yellow tint via the
      ``style_data_conditional`` filter `{edited_fields} ne ""`;
    - hidden ``<col>_base`` cells holding the BCGW base value, used
      by `capture_overrides` to detect "edited back to original"
      without consulting the store;
    - a hidden ``_outside_validity`` cell ("yes" / "") driven by
      ``u_max >= u_threshold``. The pipeline's ``well_status`` no
      longer flips to ``OUTSIDE_VALIDITY`` (advisory-only per the
      client direction), so the row tint is the user-visible signal
      that Cooper-Jacob's small-``u`` assumption is being stretched
      at that distance/duration.
    """
    row: dict[str, Any] = {
        col: _format_cell(col, _well_value(current, col))
        for col in column_ids
        if col != "edited_fields"
    }
    row["edited_fields"] = ", ".join(
        _EDITABLE_FIELD_LABELS[col]
        for col in _EDITABLE_COLUMNS
        if col in active_overrides
    )
    for col in _EDITABLE_COLUMNS:
        row[f"{col}_base"] = _format_cell(col, _well_value(base, col))
    row["_outside_validity"] = "yes" if current.u_max >= u_threshold else ""
    return row


def _columns_for(spec: list[tuple[str, str, str]]) -> list[dict]:
    return [{"id": cid, "name": name, "type": ctype} for cid, name, ctype in spec]


def _full_columns_with_editing() -> list[dict]:
    """Per-well column spec with the four override columns marked editable.

    Editable columns are declared with ``type="any"`` rather than
    ``"numeric"``. dash_table's numeric-column editing treats an
    empty string as invalid input and silently reverts the cell to
    its previous value, which made "clear a cell to revert to the
    BCGW value" not work for cells whose base was ``NULL`` in BCGW.
    The trade-off is alphabetical (string) sort on those four
    columns; the other 13 numeric columns still sort numerically,
    and the Edited / Reset controls cover the workflow that those
    sorts would have served.
    """
    cols: list[dict] = []
    for cid, name, ctype in _FULL_COLUMNS:
        col_type = "any" if cid in _EDITABLE_COLUMNS else ctype
        col = {"id": cid, "name": name, "type": col_type}
        if cid in _EDITABLE_COLUMNS:
            col["editable"] = True
        cols.append(col)
    return cols


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


def _override_row_styles() -> list[dict]:
    """Row-level light-yellow tint, keyed off the declared
    ``edited_fields`` column.

    Both the tint and the visible "Edited" column are now driven by
    the same cell value, so they update together or not at all
    (previously the tint depended on an undeclared ``_overridden``
    cell, which dash_table doesn't reliably re-evaluate when the
    server pushes new ``data``). Listed before the outside-validity
    and status-cell rules so purple wins over yellow on rows that
    trip both, and the status colour still wins on the Status
    column.
    """
    return [
        {
            "if": {
                "filter_query": '{edited_fields} ne ""',
            },
            "backgroundColor": _OVERRIDE_ROW_BG,
        },
    ]


def _outside_validity_row_styles() -> list[dict]:
    """Row-level light-purple tint for the Cooper-Jacob advisory.

    Wells whose ``u_max`` meets or exceeds ``inputs.u_threshold`` get
    a purple tint regardless of their ``well_status``. The status
    cell itself is left for the status palette so officers can still
    read AT_RISK / OK at a glance — purple is a "treat this number
    cautiously" hint, not a status. Listed AFTER ``_override_row_styles``
    so purple visibly wins over yellow on rows that carry both.
    """
    return [
        {
            "if": {
                "filter_query": '{_outside_validity} = "yes"',
            },
            "backgroundColor": _OUTSIDE_VALIDITY_ROW_BG,
        },
    ]


def make_at_risk_rows(result: AnalysisResult) -> list[dict]:
    """Just the data rows for the at-risk table.

    Split out from the static shell so the render callback can write
    ``at-risk-summary.data`` directly instead of rebuilding the whole
    DataTable component. SUSPECT_DATA wells deliberately do not
    appear here even though their Impact % may be non-trivial — the
    at-risk summary is what's attached to the licence file and a
    "data review needed" row would be misleading there.
    """
    column_ids = [c[0] for c in _AT_RISK_COLUMNS]
    return [
        _row_dict(w, column_ids)
        for w in sorted(
            (w for w in result.wells if w.well_status == WellStatus.AT_RISK),
            key=lambda w: -(w.impact_fraction or 0),
        )
    ]


# Empty-state callout. Kept in sync with `_EMPTY_VISIBLE` in
# `results_page` (the render callback swaps the whole style dict when it
# reveals the message). A bordered, tinted box reads as a real notice —
# the previous grey italic line was easy to miss, so a tester clicked a
# dead Export button several times before noticing there was nothing to
# export.
_EMPTY_MESSAGE_STYLE = {
    "padding": "0.85rem 1.1rem",
    "marginBottom": "1rem",
    "backgroundColor": "#eef3f8",
    "border": "1px solid #b6cee4",
    "borderLeft": "4px solid var(--bc-brand, #003366)",
    "borderRadius": "var(--bc-radius, 4px)",
    "color": "#1a1a1a",
    "fontSize": "0.95rem",
    "fontWeight": "500",
}


def build_at_risk_section() -> html.Div:
    """Static at-risk section: heading + helper + buttons + empty table.

    The DataTable lives in `layout()` (via this helper) so it exists
    from page mount; the render callback then writes only to its
    ``data`` prop. This sidesteps a dash_table quirk where
    rebuilding the component via a parent ``children`` update can
    leave some cell renders stale after server-pushed data changes.

    A sibling ``at-risk-empty-message`` Div is hidden by default and
    revealed when there are no AT_RISK wells — the table wrapper is
    hidden at the same time so the user sees the message instead of
    an empty grid.
    """
    return html.Div(
        [
            html.H2(
                id="at-risk-heading",
                className="bc-results-heading",
            ),
            html.P(
                id="at-risk-helper",
                style={"fontSize": "0.9rem", "color": "#555"},
            ),
            dcc.Download(id="at-risk-download"),
            html.Div(
                id="at-risk-empty-message",
                children=(
                    "No wells were flagged at risk at the configured "
                    "threshold — predicted drawdown stays below the "
                    "at-risk cutoff for every well found in the buffer."
                ),
                style={"display": "none", **_EMPTY_MESSAGE_STYLE},
            ),
            html.Div(
                id="at-risk-table-wrapper",
                # The Export button lives inside the wrapper so it is
                # hidden along with the table when there are no at-risk
                # wells — no separate visibility callback needed, and no
                # dead "Export CSV" control over an empty table.
                children=[
                    html.Button(
                        "Export CSV",
                        id="at-risk-export-btn",
                        n_clicks=0,
                        style={**_EXPORT_BUTTON_STYLE, "marginBottom": "0.5rem"},
                    ),
                    dash_table.DataTable(
                        id="at-risk-summary",
                        columns=_columns_for(_AT_RISK_COLUMNS),
                        data=[],
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
                    ),
                    html.Div(
                        "Note: the table paginates at 10 rows per page — "
                        "use the page controls at the bottom to see the rest.",
                        style={
                            "fontSize": "0.8rem",
                            "color": "#555",
                            "fontStyle": "italic",
                            "marginTop": "0.4rem",
                        },
                    ),
                ],
            ),
        ],
        style={"marginBottom": "2rem"},
    )


def make_per_well_rows(
    current: AnalysisResult,
    *,
    base_wells_by_wtn: dict[int, WellResult],
    overrides_by_wtn: dict[int, dict[str, float | None]],
) -> list[dict]:
    """Just the data rows for the per-well details table.

    Pure projection of `current.wells` -> dash_table row dicts, sorted
    ascending by distance. Hidden ``<col>_base`` shadows, the
    ``edited_fields`` summary, and the ``_outside_validity`` advisory
    flag (driven by ``inputs.u_threshold``) are populated by
    `_per_well_row_dict`; the render callback feeds the result
    directly into ``per-well-details.data``.
    """
    column_ids = [c[0] for c in _FULL_COLUMNS]
    sorted_wells = sorted(current.wells, key=lambda w: w.distance_m)
    u_threshold = current.inputs.u_threshold
    return [
        _per_well_row_dict(
            w,
            base_wells_by_wtn.get(w.well_tag_number, w),
            column_ids,
            overrides_by_wtn.get(w.well_tag_number, {}),
            u_threshold,
        )
        for w in sorted_wells
    ]


_PER_WELL_HELPER_CHILDREN = [
    # NPL is used as a column header, in the SAD explanation, and in the
    # empty-state copy, but was never expanded anywhere in the UI
    # (client feedback, 2026-07).
    html.Strong("NPL "),
    "= non-pumping (static) water level — depth to water below ground "
    "when the well is not being pumped, in metres.",
    html.Br(),
    html.Strong("Licence "),
    "= the well's licensing status as recorded in GWELLS "
    "(Licensed / Unlicensed / Historical; Unknown where GWELLS does not "
    "say). Shown for context only — it does not affect any status or "
    "at-risk calculation.",
    html.Br(),
    html.Strong("Editable columns: "),
    "NPL, Finished Depth, Stickup, Top of Frac/Screen.",
    html.Br(),
    "Sortable and filterable. Edits update SAD, Impact %, and Status "
    "live for that row; clear a cell to revert to the BCGW value, or "
    "use Reset all overrides to clear every edit at once. Drawdown "
    "(m) is not affected by these edits — it depends on Q, T, S, "
    "duration, and the well's distance from the pumping point. The "
    "rightmost \"Edited\" column lists which fields you adjusted "
    "(carried through to the CSV export).",
    html.Br(),
    # Client guidance (2026-07) placed here rather than in the results
    # page's method panel: this table is where the GWELLS links and the
    # override cells live, so it is the moment the advice is actionable.
    html.Em(disclaimers.VERIFY_SOURCES),
]


def _legend_swatch(color: str) -> html.Span:
    return html.Span(
        style={
            "display": "inline-block",
            "width": "0.9rem",
            "height": "0.9rem",
            "backgroundColor": color,
            "border": "1px solid #bbb",
            "verticalAlign": "middle",
            "marginRight": "0.35rem",
        }
    )


_PER_WELL_LEGEND_STYLE = {
    "fontSize": "0.8rem",
    "color": "#555",
    "marginTop": "0.4rem",
    "marginBottom": "0.5rem",
    "lineHeight": 1.6,
}


def _per_well_legend() -> html.Div:
    """Row-tint legend, shown above the table.

    The pagination reminder used to sit on a second line here; it has
    moved below the table (next to the page controls themselves) so
    the legend stays focused on row-tint meaning and the reminder
    sits where the reader's eye naturally lands at end-of-table.
    """
    return html.Div(
        [
            html.Span("Row tints: ", style={"fontWeight": "500"}),
            _legend_swatch(_OVERRIDE_ROW_BG),
            html.Span("manual override active", style={"marginRight": "1rem"}),
            _legend_swatch(_OUTSIDE_VALIDITY_ROW_BG),
            html.Span(
                "outside Cooper-Jacob validity (advisory — "
                "drawdown number shown but should be treated with "
                "caution at this distance / duration). The CSV export "
                "carries this as an \"Outside Validity\" Yes/No column.",
            ),
        ],
        style=_PER_WELL_LEGEND_STYLE,
    )


def build_per_well_section() -> html.Div:
    """Static per-well section: heading + helper + buttons + empty table.

    Same shape as `build_at_risk_section` and for the same reason:
    keep the dash_table mounted across renders so its ``data`` prop
    can be updated in isolation. Edits, clears, the Reset button, and
    server-pushed override recomputes all flow through the same data
    prop, which removes the React-reconciliation hazard that was
    silently dropping cell updates after a clear.
    """
    return html.Div(
        [
            html.H2(
                id="per-well-heading",
                className="bc-results-heading",
            ),
            html.P(
                _PER_WELL_HELPER_CHILDREN,
                style={"fontSize": "0.9rem", "color": "#555"},
            ),
            dcc.Download(id="per-well-download"),
            html.Div(
                id="per-well-empty-message",
                children=(
                    "No groundwater wells were found within the buffer "
                    "radius of the pumping point. Try increasing the "
                    "buffer radius on the Setup page and running the "
                    "analysis again."
                ),
                style={"display": "none", **_EMPTY_MESSAGE_STYLE},
            ),
            html.Div(
                id="per-well-table-wrapper",
                # Export / reset controls live inside the wrapper so they
                # disappear with the table when no wells are returned —
                # nothing to export or reset when the buffer is empty.
                children=[
                    html.Div(
                        [
                            html.Button(
                                "Export CSV",
                                id="per-well-export-btn",
                                n_clicks=0,
                                style=_EXPORT_BUTTON_STYLE,
                            ),
                            html.Button(
                                "Reset all overrides",
                                id="per-well-reset-overrides-btn",
                                n_clicks=0,
                                style={**_EXPORT_BUTTON_STYLE, "marginLeft": "0.5rem"},
                            ),
                        ],
                        style={"marginBottom": "0.5rem"},
                    ),
                    _per_well_legend(),
                    dash_table.DataTable(
                        id="per-well-details",
                        columns=_full_columns_with_editing(),
                        data=[],
                        sort_action="native",
                        filter_action="native",
                        page_action="native",
                        page_size=10,
                        # Sticky header row so column names stay visible during
                        # vertical scroll. We deliberately do NOT use fixed_columns:
                        # dash_table renders fixed-column filter inputs in a
                        # separate DOM region with different CSS, leading to a
                        # visible inconsistency vs. the non-fixed filter inputs
                        # ("filter data..." placeholder shows in the fixed area
                        # but not the non-fixed area). page_size=10 keeps the
                        # table short enough that horizontal scrolling without a
                        # pinned WTN column is manageable.
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
                        # Order matters: yellow override tint, then
                        # purple outside-validity tint (so purple wins
                        # on rows tripping both), then the status
                        # palette (per-column, so it always wins on
                        # the Status column).
                        style_data_conditional=(
                            _override_row_styles()
                            + _outside_validity_row_styles()
                            + _status_conditional_styles()
                        ),
                    ),
                    html.Div(
                        "Note: the table paginates at 10 rows per page — "
                        "use the page controls at the bottom to see the rest.",
                        style={
                            "fontSize": "0.8rem",
                            "color": "#555",
                            "fontStyle": "italic",
                            "marginTop": "0.4rem",
                        },
                    ),
                ],
            ),
        ],
        style={"marginBottom": "2rem"},
    )


def at_risk_helper_text(result: AnalysisResult) -> str:
    """Dynamic helper paragraph below the at-risk heading.

    The percentage in the wording depends on
    ``inputs.at_risk_fraction`` so it can't be a static string in
    `build_at_risk_section`.
    """
    return (
        "Wells whose predicted drawdown reaches "
        f"{int(result.inputs.at_risk_fraction * 100)}% of "
        "their Safe Available Drawdown. Reflects any per-well "
        "overrides currently applied below."
    )


def _table_to_csv(
    rows: list[dict],
    columns: list[dict],
    *,
    extra_columns: list[tuple[str, str, Any]] | None = None,
) -> str:
    """Serialise dash_table data + columns to a CSV string with display headers.

    Columns whose id starts with ``_`` are treated as hidden bookkeeping
    fields (the override-marker flag and the per-column ``_base``
    shadow values) and excluded from the export.

    ``extra_columns`` appends derived columns the table itself doesn't
    show. Each entry is ``(field_id, display_header, fn)`` where ``fn``
    maps a row dict to the cell value — used to surface the
    outside-validity advisory (a hidden ``_`` cell) as a plain Yes/No
    column, since CSV can't carry the table's purple row tint.
    """
    extra_columns = extra_columns or []
    buf = io.StringIO()
    visible = [c for c in columns if not c["id"].startswith("_")]
    visible_ids = [c["id"] for c in visible]
    fieldnames = visible_ids + [fid for fid, _, _ in extra_columns]
    headers = {c["id"]: c["name"] for c in visible}
    for fid, header, _ in extra_columns:
        headers[fid] = header
    writer = csv.DictWriter(buf, fieldnames=fieldnames, extrasaction="ignore")
    writer.writerow(headers)
    for row in rows:
        out = {k: row.get(k, "") for k in visible_ids}
        for fid, _, fn in extra_columns:
            out[fid] = fn(row)
        writer.writerow(out)
    return buf.getvalue()


def _export_filename(
    result_data: dict[str, Any] | None,
    descriptor: str,
    ext: str,
) -> str:
    """Build ``drawdown-<descriptor>-<run-id>.<ext>``, matching the exports.

    Every artifact from one run shares the ``drawdown-<descriptor>-<run
    id first 8 chars>`` scheme so the files sort together and the run
    they belong to is obvious. Falls back to a plain name if the cached
    result carries no run id.
    """
    run_id = (result_data or {}).get("run_id")
    if isinstance(run_id, str) and run_id:
        return f"drawdown-{descriptor}-{run_id[:8]}.{ext}"
    return f"drawdown-{descriptor}.{ext}"


@callback(
    Output("per-well-download", "data"),
    Input("per-well-export-btn", "n_clicks"),
    State("per-well-details", "derived_virtual_data"),
    State("per-well-details", "data"),
    State("per-well-details", "columns"),
    State("analysis-result", "data"),
    prevent_initial_call=True,
)
def export_per_well_csv(
    _n_clicks: int,
    filtered_rows: list[dict] | None,
    raw_rows: list[dict] | None,
    columns: list[dict] | None,
    result_data: dict[str, Any] | None,
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
    # CSV can't carry the table's purple outside-validity row tint, so
    # the advisory is surfaced as a plain Yes/No column derived from
    # the hidden ``_outside_validity`` cell.
    extra = [
        (
            "outside_validity",
            "Outside Validity",
            lambda r: "Yes" if r.get("_outside_validity") == "yes" else "No",
        )
    ]
    return dcc.send_string(
        _table_to_csv(rows, columns, extra_columns=extra),
        _export_filename(result_data, "per-well", "csv"),
    )


@callback(
    Output("at-risk-download", "data"),
    Input("at-risk-export-btn", "n_clicks"),
    State("at-risk-summary", "derived_virtual_data"),
    State("at-risk-summary", "data"),
    State("at-risk-summary", "columns"),
    State("analysis-result", "data"),
    prevent_initial_call=True,
)
def export_at_risk_csv(
    _n_clicks: int,
    filtered_rows: list[dict] | None,
    raw_rows: list[dict] | None,
    columns: list[dict] | None,
    result_data: dict[str, Any] | None,
) -> object:
    """Build a CSV from the at-risk table's current view (sort + filter aware)."""
    rows = filtered_rows if filtered_rows is not None else raw_rows
    if not rows or not columns:
        return no_update
    return dcc.send_string(
        _table_to_csv(rows, columns),
        _export_filename(result_data, "at-risk", "csv"),
    )


def _parse_float(value: object) -> float | None:
    """Parse a dash_table cell value to float.

    Strips a trailing ``*`` (the override marker) and surrounding
    whitespace. Empty strings and unparseable input return None — the
    capture callback treats that as "revert to base".
    """
    if value is None:
        return None
    text = str(value).strip()
    if text.endswith("*"):
        text = text[:-1].strip()
    if not text:
        return None
    try:
        return float(text)
    except ValueError:
        return None


def _floats_equal(a: float | None, b: float | None, tol: float = 1e-9) -> bool:
    if a is None and b is None:
        return True
    if a is None or b is None:
        return False
    return abs(a - b) <= tol


@callback(
    Output("well-overrides", "data", allow_duplicate=True),
    Input("per-well-reset-overrides-btn", "n_clicks"),
    prevent_initial_call=True,
)
def reset_overrides(_n_clicks: int) -> dict[str, dict[str, float]]:
    """Wipe every per-well override.

    Belt-and-braces escape hatch for cases where dash_table's cell
    editing won't release a value (e.g. clearing a cell whose base is
    ``NULL`` in BCGW). After the click the page-level render callback
    rebuilds the table and stat cards from the cached pipeline result
    with no overrides applied.
    """
    return {}


@callback(
    Output("well-overrides", "data", allow_duplicate=True),
    Input("per-well-details", "data"),
    State("well-overrides", "data"),
    prevent_initial_call=True,
)
def capture_overrides(
    rows: list[dict] | None,
    existing: dict[str, dict[str, float]] | None,
) -> object:
    """Diff the per-well table against the hidden ``_base`` shadow cells.

    Builds the full per-WTN override map from the table state on every
    data change. Any cell whose parsed value matches the base (within
    tolerance) — or is empty / unparseable — is treated as "no
    override" and dropped. Keys are str(wtn) because Dash serialises
    the store as JSON, so the page-level render callback re-keys to
    int before calling `analysis.apply_overrides`.

    Triggers on `data` (not `data_timestamp`). dash_table only fires
    `data_timestamp` for edits it considers a "real" commit, and with
    `type="any"` columns clearing a cell back to empty doesn't always
    qualify — the cell looks empty but the store keeps the old
    override and SAD / Status / row tint never refresh. `data` fires
    on every prop change; the ``(existing or {}) == new`` early-out
    below prevents the render-callback rewrite from re-firing this
    callback in a loop.
    """
    if not rows:
        new: dict[str, dict[str, float]] = {}
    else:
        new = {}
        for row in rows:
            try:
                wtn = int(row["well_tag_number"])
            except (KeyError, TypeError, ValueError):
                continue
            per_well: dict[str, float] = {}
            for col in _EDITABLE_COLUMNS:
                edited = _parse_float(row.get(col))
                base = _parse_float(row.get(f"{col}_base"))
                if edited is None:
                    continue
                if _floats_equal(edited, base):
                    continue
                per_well[col] = edited
            if per_well:
                new[str(wtn)] = per_well
    if (existing or {}) == new:
        return no_update
    return new
