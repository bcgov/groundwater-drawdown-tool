"""Results page — sub-stage 4c.1 read-only dashboard.

Layout from top:

1. Header — H1 + "Back to Setup" link.
2. Run summary — timestamp, signed-in user, source aquifer, T/S used
   (with "(override)" tag when applicable), Q in m³/day, duration,
   buffer radius, filter on/off.
3. Stat cards — six status counts + max drawdown.
4. At-risk wells table — `dash_table.DataTable` filtered to
   ``WellStatus.AT_RISK`` only, with built-in CSV export. This is
   the artifact attached to the licence-assessment file.
5. Per-well details table — full 17-column table with sort, filter,
   pagination (25/page), CSV export, fixed first column. Status cell
   colour-coded per `WellStatus`.
6. Footer.

Sub-stage 4c.2 turns four cells of the per-well table into editable
overrides (NPL, finished depth, stickup, top of fracture/screen) with
per-row live recompute. Sub-stage 4c.3 adds the distance-drawdown
chart and the colour-coded map.
"""

from __future__ import annotations

import logging
from typing import Any

import dash
from dash import Input, Output, callback, dcc, html

from gwdrawdown.analysis import AnalysisInputs, AnalysisResult, run_analysis
from gwdrawdown.ui.components.footer import make_footer
from gwdrawdown.ui.components.results_table import (
    make_at_risk_table,
    make_full_well_table,
)
from gwdrawdown.ui.components.stat_cards import make_stat_cards
from gwdrawdown.ui.session import current_user, is_authenticated

dash.register_page(__name__, path="/results", name="Results")

logger = logging.getLogger(__name__)

_PAGE_STYLE = {
    "fontFamily": "sans-serif",
    "padding": "1.5rem 2rem",
    "maxWidth": "1400px",
    "margin": "0 auto",
}
_SUMMARY_STYLE = {
    "border": "1px solid #d0d0d0",
    "borderRadius": "4px",
    "padding": "0.75rem 1rem",
    "marginBottom": "1.5rem",
    "backgroundColor": "#fafafa",
    "fontSize": "0.9rem",
    "lineHeight": 1.6,
}
_PRE_STYLE = {
    "backgroundColor": "#fdecea",
    "padding": "1rem",
    "borderRadius": "4px",
    "color": "#b00020",
    "whiteSpace": "pre-wrap",
}


def layout(**_kwargs: object) -> html.Div:
    if not is_authenticated():
        return html.Div(
            dcc.Location(href="/login", id="results-redirect-login", refresh=True)
        )
    return html.Div(
        [
            html.Div(
                [
                    html.H1("Results", style={"display": "inline-block", "marginRight": "1.5rem"}),
                    dcc.Link(
                        "← Back to Setup",
                        href="/setup",
                        style={"color": "#1565c0", "textDecoration": "none"},
                    ),
                ],
                style={"display": "flex", "alignItems": "baseline", "gap": "1rem"},
            ),
            html.Div(id="results-output"),
            make_footer(),
        ],
        style=_PAGE_STYLE,
    )


def _summary_block(inputs: AnalysisInputs, result: AnalysisResult) -> html.Div:
    user = current_user() or "—"
    ts = result.run_timestamp.strftime("%Y-%m-%d %H:%M:%S")
    ts_tag = " (override)" if inputs.ts_overridden else ""
    filter_tag = "ON" if inputs.same_aquifer_filter else "off"

    def row(label: str, value: str) -> html.Div:
        return html.Div(
            [
                html.Span(
                    label,
                    style={
                        "display": "inline-block",
                        "width": "180px",
                        "color": "#555",
                    },
                ),
                html.Span(value, style={"fontWeight": "500"}),
            ]
        )

    return html.Div(
        [
            row("Run timestamp:", ts),
            row("BCGW user:", user),
            row(
                "Source aquifer:",
                f"{inputs.source_aquifer_name} (id {inputs.source_aquifer_id}, "
                f"subtype {inputs.source_subtype_code or '—'})",
            ),
            row(
                "T / S used:",
                f"T = {inputs.transmissivity_m2_per_day} m²/day, "
                f"S = {inputs.storativity}{ts_tag}",
            ),
            row(
                "Pumping rate:",
                f"{inputs.Q_value} {inputs.Q_unit} = {inputs.Q_m3_per_day:.3f} m³/day",
            ),
            row("Duration:", f"{inputs.duration_days:g} days"),
            row("Buffer radius:", f"{inputs.buffer_radius_m:g} m"),
            row("Same-aquifer filter:", filter_tag),
        ],
        style=_SUMMARY_STYLE,
    )


@callback(
    Output("results-output", "children"),
    Input("analysis-inputs", "data"),
)
def render_results(inputs_data: dict[str, Any] | None) -> Any:
    if not inputs_data:
        return html.Div(
            [
                html.P(
                    "No analysis has been run in this browser tab yet.",
                    style={"marginTop": "1rem"},
                ),
                dcc.Link("Go to Setup", href="/setup"),
            ]
        )
    try:
        inputs = AnalysisInputs.from_json(inputs_data)
    except (TypeError, KeyError) as e:
        logger.exception("Bad analysis-inputs payload: %s", inputs_data)
        return html.Pre(f"Invalid stored inputs: {e}", style=_PRE_STYLE)

    try:
        result = run_analysis(inputs)
    except Exception as e:
        logger.exception("Pipeline failed")
        return html.Pre(f"Pipeline error: {e}", style=_PRE_STYLE)

    return html.Div(
        [
            _summary_block(inputs, result),
            make_stat_cards(result),
            make_at_risk_table(result),
            make_full_well_table(result),
        ]
    )
