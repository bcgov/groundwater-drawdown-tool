"""Results page — sub-stage 4c.2 dashboard with editable overrides.

Layout from top:

1. Header — H1 + "Back to Setup" link.
2. Run summary — timestamp, signed-in user, source aquifer, T/S used
   (with "(override)" tag when applicable), Q in m³/day, duration,
   buffer radius, filter on/off.
3. Stat cards — six status counts + max drawdown.
4. At-risk wells table — filtered to ``WellStatus.AT_RISK`` only.
5. Per-well details table — full 17-column table with sort, filter,
   pagination (10/page), CSV export, four editable columns (NPL,
   finished depth, stickup, top of fracture/screen), and a Reset
   button. Status cell colour-coded per `WellStatus`. Rows with
   active overrides are tinted light yellow; the rightmost "Edited"
   column lists which fields each row has overridden (carried
   through to CSV export).
6. Footer.

Render flow (rebuilt in 4c.2 to fix a dash_table reconciliation
issue): the layout in `layout()` is a *static skeleton* —
named-id containers (`summary-block-container`, `stat-cards-container`,
the at-risk and per-well sections built by
`results_table.build_*_section`) — that exists from page mount. The
dash_table components live inside that skeleton from the start, so
their props (especially ``data``) can be updated in isolation by
the render callback rather than via a full ``children`` rebuild.

Two callbacks drive the page:

- `run_pipeline_if_needed` reads `analysis-inputs`, calls
  `run_analysis` only when the inputs change, and writes the
  JSON-serialised `AnalysisResult` to `analysis-result`. Also resets
  `well-overrides` on a new run so edits from a previous analysis
  don't leak across the wells.
- `render` reads `analysis-result` + `well-overrides`, applies
  overrides via `analysis.apply_overrides`, and writes each dynamic
  region directly (summary block, stat cards, at-risk heading/helper/
  data, per-well heading, per-well data). No BCGW round-trip happens
  here — overrides edit the cached result in place — and crucially
  the two dash_tables stay mounted across renders, which keeps cell
  clears and Edited-column refreshes consistent.

Sub-stage 4c.3 will plug the distance-drawdown chart and the colour-
coded map into the same render callback.
"""

from __future__ import annotations

import json
import logging
from typing import Any

import dash
from dash import Input, Output, callback, dcc, html, no_update

from gwdrawdown.analysis import (
    AnalysisInputs,
    AnalysisResult,
    apply_overrides,
    run_analysis,
)
from gwdrawdown.ui.components.footer import make_footer
from gwdrawdown.ui.components.results_table import (
    at_risk_helper_text,
    build_at_risk_section,
    build_per_well_section,
    make_at_risk_rows,
    make_per_well_rows,
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
_EMPTY_STATE_STYLE = {"marginTop": "1rem"}


def layout(**_kwargs: object) -> html.Div:
    """Static page skeleton.

    Components with stable ids exist from page mount; the render
    callback only writes their dynamic props. The two dash_tables
    in particular are NEVER re-created mid-session — that's the
    point of this restructure.
    """
    if not is_authenticated():
        return html.Div(
            dcc.Location(href="/login", id="results-redirect-login", refresh=True)
        )
    return html.Div(
        [
            html.Div(
                [
                    html.H1(
                        "Results",
                        style={"display": "inline-block", "marginRight": "1.5rem"},
                    ),
                    dcc.Link(
                        "← Back to Setup",
                        href="/setup",
                        style={"color": "#1565c0", "textDecoration": "none"},
                    ),
                ],
                style={"display": "flex", "alignItems": "baseline", "gap": "1rem"},
            ),
            # Either the empty/error message OR the results content is
            # shown at any time; the render callback toggles each via
            # its ``style.display``.
            html.Div(id="results-empty-state", style=_EMPTY_STATE_STYLE),
            html.Div(
                id="results-content",
                style={"display": "none"},
                children=[
                    html.Div(id="summary-block-container"),
                    html.Div(id="stat-cards-container"),
                    build_at_risk_section(),
                    build_per_well_section(),
                ],
            ),
            make_footer(),
        ],
        style=_PAGE_STYLE,
    )


def _summary_block(result: AnalysisResult) -> html.Div:
    inputs = result.inputs
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


def _inputs_fingerprint(inputs_data: dict[str, Any]) -> str:
    """Stable JSON hash of the analysis inputs.

    Used to decide whether the cached `analysis-result` is still valid
    for the current `analysis-inputs`. ``sort_keys=True`` so two equal
    dicts with different key orders don't trigger a re-run.
    """
    return json.dumps(inputs_data, sort_keys=True, default=str)


@callback(
    Output("analysis-result", "data"),
    Output("well-overrides", "data", allow_duplicate=True),
    Input("analysis-inputs", "data"),
    prevent_initial_call="initial_duplicate",
)
def run_pipeline_if_needed(
    inputs_data: dict[str, Any] | None,
) -> tuple[Any, Any]:
    """Run the BCGW pipeline when `analysis-inputs` changes.

    Caches the result in `analysis-result` so override edits and tab
    refreshes don't replay the pipeline. Also clears `well-overrides`
    on a new run — the previous overrides referenced WTNs that may
    not appear in the new well set.
    """
    if not inputs_data:
        return no_update, no_update
    try:
        inputs = AnalysisInputs.from_json(inputs_data)
    except (TypeError, KeyError) as exc:
        logger.exception("Bad analysis-inputs payload")
        return {"_error": f"Invalid stored inputs: {exc}"}, {}
    try:
        result = run_analysis(inputs)
    except Exception as exc:
        # Surface any pipeline failure to the UI rather than 500-ing.
        logger.exception("Pipeline failed")
        return {"_error": f"Pipeline error: {exc}"}, {}
    payload = result.to_json()
    payload["_fingerprint"] = _inputs_fingerprint(inputs_data)
    return payload, {}


def _coerce_overrides(
    raw: dict[str, Any] | None,
) -> dict[int, dict[str, float | None]]:
    """Re-key the JSON-stored overrides to int(WTN).

    Dash sessionStorage stringifies dict keys; `analysis.apply_overrides`
    expects ``{int: {field: float | None}}``. Drops any key that
    doesn't parse as an int.
    """
    if not raw:
        return {}
    out: dict[int, dict[str, float | None]] = {}
    for k, v in raw.items():
        try:
            wtn = int(k)
        except (TypeError, ValueError):
            continue
        if isinstance(v, dict):
            out[wtn] = v
    return out


_HIDE = {"display": "none"}
_SHOW = {}
# Reveal styling for the at-risk / per-well empty-state messages.
# Matches `_EMPTY_MESSAGE_STYLE` in `results_table` (the hidden form
# carries the same color + italic so toggling display alone reveals it).
_EMPTY_VISIBLE = {"color": "#555", "fontStyle": "italic"}


def _empty_state(message: str, style: dict[str, str]) -> html.Div:
    return html.Div(
        [
            html.P(message, style=style),
            dcc.Link("Go to Setup", href="/setup"),
        ]
    )


@callback(
    Output("results-empty-state", "children"),
    Output("results-empty-state", "style"),
    Output("results-content", "style"),
    Output("summary-block-container", "children"),
    Output("stat-cards-container", "children"),
    Output("at-risk-heading", "children"),
    Output("at-risk-helper", "children"),
    Output("at-risk-summary", "data"),
    Output("at-risk-table-wrapper", "style"),
    Output("at-risk-empty-message", "style"),
    Output("per-well-heading", "children"),
    Output("per-well-details", "data"),
    Output("per-well-table-wrapper", "style"),
    Output("per-well-empty-message", "style"),
    Input("analysis-result", "data"),
    Input("well-overrides", "data"),
)
def render(
    result_data: dict[str, Any] | None,
    overrides_data: dict[str, Any] | None,
) -> tuple[Any, ...]:
    """Update each dynamic region from the cached result + overrides.

    No BCGW. Writes each part of the page through its own ``Output``
    so the two ``dash_table.DataTable`` components stay mounted —
    only their ``data`` props change. This was the fix for cell clears
    not re-rendering after a server-pushed override drop: rebuilding
    the whole tree was causing dash_table to preserve stale row state
    for some cells (notably the ``edited_fields`` summary and the
    style-driven row tint).
    """
    # Empty / error states: hide the content, show a message. The
    # 11 trailing no_updates correspond to the 11 dynamic outputs
    # inside ``results-content`` — leaving them untouched while the
    # content is hidden keeps the last successful render intact for
    # the moment the user navigates back.
    n_dynamic_outputs = 11
    if not result_data:
        return (
            _empty_state(
                "No analysis has been run in this browser tab yet.",
                _EMPTY_STATE_STYLE,
            ),
            _EMPTY_STATE_STYLE,
            _HIDE,
            *([no_update] * n_dynamic_outputs),
        )
    if "_error" in result_data:
        return (
            html.Pre(result_data["_error"], style=_PRE_STYLE),
            _EMPTY_STATE_STYLE,
            _HIDE,
            *([no_update] * n_dynamic_outputs),
        )
    try:
        base = AnalysisResult.from_json(result_data)
    except (TypeError, KeyError, ValueError) as exc:
        logger.exception("Bad analysis-result payload")
        return (
            html.Pre(f"Invalid cached result: {exc}", style=_PRE_STYLE),
            _EMPTY_STATE_STYLE,
            _HIDE,
            *([no_update] * n_dynamic_outputs),
        )

    overrides = _coerce_overrides(overrides_data)
    current = apply_overrides(base, overrides)
    base_wells_by_wtn = {w.well_tag_number: w for w in base.wells}
    at_risk_rows = make_at_risk_rows(current)
    per_well_rows = make_per_well_rows(
        current,
        base_wells_by_wtn=base_wells_by_wtn,
        overrides_by_wtn=overrides,
    )

    return (
        "",  # clear any prior empty-state message
        _HIDE,  # hide empty-state container
        _SHOW,  # show results content
        _summary_block(current),
        make_stat_cards(current),
        f"At-risk wells ({current.n_at_risk})",
        at_risk_helper_text(current),
        at_risk_rows,
        _SHOW if at_risk_rows else _HIDE,
        _HIDE if at_risk_rows else _EMPTY_VISIBLE,
        f"All wells in buffer ({current.n_total})",
        per_well_rows,
        _SHOW if per_well_rows else _HIDE,
        _HIDE if per_well_rows else _EMPTY_VISIBLE,
    )
