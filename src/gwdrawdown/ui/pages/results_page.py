"""Results page — sub-stage 4b dump.

For 4b this page reads the ``analysis-inputs`` store written by the
setup page, runs ``analysis.run_analysis`` against the live BCGW
pool, and dumps the resulting ``AnalysisResult`` as a ``<pre>`` block
of formatted text. Sub-stage 4c replaces the dump with the real
dashboard (at-risk summary table, stat cards, distance-drawdown
chart, colour-coded map, full per-well table).
"""

from __future__ import annotations

import logging
from typing import Any

import dash
from dash import Input, Output, callback, dcc, html

from gwdrawdown.analysis import AnalysisInputs, AnalysisResult, run_analysis
from gwdrawdown.ui.components.footer import make_footer
from gwdrawdown.ui.session import is_authenticated

dash.register_page(__name__, path="/results", name="Results")

logger = logging.getLogger(__name__)

_PAGE_STYLE = {
    "fontFamily": "sans-serif",
    "padding": "1.5rem 2rem",
    "maxWidth": "1100px",
    "margin": "0 auto",
}
_PRE_STYLE = {
    "backgroundColor": "#f5f5f5",
    "padding": "1rem",
    "borderRadius": "4px",
    "fontSize": "0.8rem",
    "overflowX": "auto",
    "whiteSpace": "pre",
}


def layout(**_kwargs: object) -> html.Div:
    if not is_authenticated():
        return html.Div(
            dcc.Location(href="/login", id="results-redirect-login", refresh=True)
        )
    return html.Div(
        [
            html.H1("Results"),
            html.P(
                "Sub-stage 4b dump — pipeline output as raw text. "
                "Sub-stage 4c will replace this with the chart, tables, "
                "and map."
            ),
            html.Div(id="results-output"),
            make_footer(),
        ],
        style=_PAGE_STYLE,
    )


def _format_result(result: AnalysisResult) -> str:
    inputs = result.inputs
    lines: list[str] = []
    lines.append("=" * 78)
    lines.append("INPUTS")
    lines.append("=" * 78)
    lines.append(
        f"Pumping point:       WGS84 ({inputs.pumping_lon:.6f}, "
        f"{inputs.pumping_lat:.6f})"
    )
    lines.append(
        f"                     BC Albers ({inputs.pumping_x_albers:.1f}, "
        f"{inputs.pumping_y_albers:.1f})"
    )
    lines.append(
        f"Source aquifer:      {inputs.source_aquifer_name} "
        f"(id {inputs.source_aquifer_id}, subtype "
        f"{inputs.source_subtype_code!r})"
    )
    lines.append(
        f"T / S used:          T = {inputs.transmissivity_m2_per_day} m²/day, "
        f"S = {inputs.storativity}"
    )
    lines.append(
        f"Pumping rate:        Q = {inputs.Q_value} {inputs.Q_unit} "
        f"= {inputs.Q_m3_per_day:.3f} m³/day"
    )
    lines.append(f"Duration:            {inputs.duration_days} days")
    lines.append(f"Buffer radius:       {inputs.buffer_radius_m} m")
    lines.append(
        f"Same-aquifer filter: {'ON' if inputs.same_aquifer_filter else 'off'}"
    )
    lines.append(f"Run timestamp:       {result.run_timestamp.isoformat(timespec='seconds')}")
    lines.append("")
    lines.append("=" * 78)
    lines.append("SUMMARY")
    lines.append("=" * 78)
    lines.append(f"Total wells in buffer:   {result.n_total}")
    lines.append(f"  At risk:               {result.n_at_risk}")
    lines.append(f"  OK:                    {result.n_ok}")
    lines.append(f"  Insufficient data:     {result.n_insufficient_data}")
    lines.append(f"  Suspect data:          {result.n_suspect_data}")
    lines.append(f"  Outside C-J validity:  {result.n_outside_validity}")
    if result.max_drawdown_m is not None:
        lines.append(f"Max drawdown (valid):    {result.max_drawdown_m:.4f} m")
    lines.append("")
    lines.append("=" * 78)
    lines.append("WELLS")
    lines.append("=" * 78)
    if not result.wells:
        lines.append("(no wells returned)")
    else:
        lines.append(
            f"{'WTN':>8}  {'Aquifer':>7}  {'Dist m':>8}  "
            f"{'Drawdown m':>10}  {'SAD m':>8}  "
            f"{'Impact %':>8}  {'Material':<14}  Status"
        )
        for w in sorted(result.wells, key=lambda w: w.distance_m):
            sad_text = f"{w.sad_m:.3f}" if w.sad_m is not None else "  (na)"
            impact_text = (
                f"{w.impact_fraction * 100:.1f}"
                if w.impact_fraction is not None
                else "  (na)"
            )
            lines.append(
                f"{w.well_tag_number:>8}  "
                f"{(w.aquifer_id if w.aquifer_id is not None else '-'):>7}  "
                f"{w.distance_m:>8.1f}  "
                f"{w.drawdown_m:>10.4f}  "
                f"{sad_text:>8}  "
                f"{impact_text:>8}  "
                f"{w.reassigned_material:<14}  {w.well_status.value}"
            )
    return "\n".join(lines)


@callback(
    Output("results-output", "children"),
    Input("analysis-inputs", "data"),
)
def render_results(inputs_data: dict[str, Any] | None) -> Any:
    if not inputs_data:
        return html.Div(
            [
                html.P(
                    "No analysis has been run in this browser session yet.",
                    style={"marginBottom": "0.5rem"},
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

    return html.Pre(_format_result(result), style=_PRE_STYLE)
