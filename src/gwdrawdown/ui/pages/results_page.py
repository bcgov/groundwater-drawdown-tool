"""Results page — sub-stage 4c.3 dashboard with chart, map and overrides.

Layout from top:

1. Header — H1 + "Back to Setup" link.
2. Run summary — timestamp, signed-in user, source aquifer, T/S used
   (with "(override)" tag when applicable), Q in m³/day, duration,
   buffer radius, source-aquifer filter on/off (spatial).
3. Stat cards — six status counts + max drawdown.
4. Distance-drawdown chart — three traces (wells, Cooper-Jacob
   curve, SAD bars), inverted Y, log-spaced X. Click a point to
   select it; the map highlights the matching marker.
5. Colour-coded map — pumping well + buffer + per-well markers
   (status colour, impact-magnitude radius). Click a marker to
   select it; the chart highlights the matching point.
6. At-risk wells table — filtered to ``WellStatus.AT_RISK`` only.
7. Per-well details table — full 17-column table with sort, filter,
   pagination (10/page), CSV export, four editable columns (NPL,
   finished depth, stickup, top of fracture/screen), and a Reset
   button. Status cell colour-coded per `WellStatus`. Rows with
   active overrides are tinted light yellow; rows failing the
   Cooper-Jacob u<threshold advisory are tinted light purple
   (purple wins on rows tripping both). A row-tint legend +
   pagination reminder sit just above the table.
8. Footer.

Render flow: the layout in `layout()` is a *static skeleton* —
named-id containers (`summary-block-container`, `stat-cards-container`,
``dd-chart``, the map skeleton from `results_map.build_map_skeleton`,
the at-risk and per-well sections from `results_table`) — that
exists from page mount. The dash_table components, the chart, and
the map's LayerGroups stay mounted across renders so their props
update in isolation.

Five page-level callbacks drive the page:

- `run_pipeline_if_needed` reads `analysis-inputs`, calls
  `run_analysis` only when the inputs change, and writes the
  JSON-serialised `AnalysisResult` to `analysis-result`. Also resets
  `well-overrides` and `selected-well` on a new run so state from a
  previous analysis doesn't leak across the wells.
- `render` reads `analysis-result` + `well-overrides`, applies
  overrides via `analysis.apply_overrides`, and writes the summary
  block, stat cards, and both tables. No BCGW round-trip happens
  here — overrides edit the cached result in place.
- `render_chart_and_map` reads the same inputs plus
  `selected-well`, applies overrides, and writes the chart figure
  and the map's pumping and wells layers. Selection changes don't
  re-touch the tables.
- `centre_map_on_new_result` flies the map to the new pumping
  point exactly once per `analysis-result` change — selection or
  override edits don't disturb the officer's pan/zoom.
- `select_from_chart` / `select_from_map` capture chart clickData
  and marker n_clicks (pattern-matching) and update
  `selected-well`. Both chart and map listen on this store, so the
  highlight stays in sync.
"""

from __future__ import annotations

import json
import logging
from typing import Any

import dash
from dash import (
    ALL,
    Input,
    Output,
    callback,
    clientside_callback,
    ctx,
    dcc,
    html,
    no_update,
)

from gwdrawdown.analysis import (
    AnalysisInputs,
    AnalysisResult,
    apply_overrides,
    run_analysis,
)
from gwdrawdown.ui.components.dd_chart import make_distance_drawdown_figure
from gwdrawdown.ui.components.footer import make_footer
from gwdrawdown.ui.components.impact_chart import make_impact_chart
from gwdrawdown.ui.components.results_map import (
    build_map_skeleton,
    make_pumping_layer,
    make_well_markers,
    map_viewport_for,
)
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
                    html.H2(
                        "Distance-drawdown",
                        style={"marginTop": "1rem", "marginBottom": "0.5rem"},
                    ),
                    dcc.Graph(
                        id="dd-chart",
                        config={"displaylogo": False},
                        style={"marginBottom": "1.5rem"},
                    ),
                    html.H2(
                        "Impact % per well",
                        style={"marginTop": "1rem", "marginBottom": "0.5rem"},
                    ),
                    html.P(
                        "Horizontal bars sorted worst-to-best so the "
                        "wells nearest the at-risk threshold sit at the "
                        "top. The dashed red line marks the at-risk "
                        "threshold. Wells with no computable impact "
                        "(missing NPL or depth) are excluded — see the "
                        "per-well details table below for those rows.",
                        style={"fontSize": "0.85rem", "color": "#555"},
                    ),
                    dcc.Graph(
                        id="impact-chart",
                        config={"displaylogo": False},
                        style={"marginBottom": "1.5rem"},
                    ),
                    html.H2(
                        "Map",
                        style={"marginTop": "1rem", "marginBottom": "0.5rem"},
                    ),
                    html.P(
                        "Marker colour matches the Status column; marker size "
                        "scales with predicted impact. Click a marker to "
                        "highlight the matching point on the chart above.",
                        style={"fontSize": "0.85rem", "color": "#555"},
                    ),
                    build_map_skeleton(),
                    build_at_risk_section(),
                    build_per_well_section(),
                ],
            ),
            # selected-well is page-scoped (memory) so navigating away
            # and back clears the highlight; analysis-inputs changes
            # also explicitly reset it in `run_pipeline_if_needed`.
            dcc.Store(id="selected-well", storage_type="memory"),
            # Noop sink for the map-resize clientside callback. Leaflet
            # tiles fail to render when their container is `display:
            # none` at mount (no measurable size); we kick the map
            # with a window resize event the moment results-content
            # becomes visible.
            html.Div(id="results-map-resize-noop", style={"display": "none"}),
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
            row("Source-aquifer filter (spatial):", filter_tag),
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
    Output("selected-well", "data", allow_duplicate=True),
    Input("analysis-inputs", "data"),
    prevent_initial_call="initial_duplicate",
)
def run_pipeline_if_needed(
    inputs_data: dict[str, Any] | None,
) -> tuple[Any, Any, Any]:
    """Run the BCGW pipeline when `analysis-inputs` changes.

    Caches the result in `analysis-result` so override edits and tab
    refreshes don't replay the pipeline. Also clears `well-overrides`
    and `selected-well` on a new run — the previous state referenced
    WTNs that may not appear in the new well set.
    """
    if not inputs_data:
        return no_update, no_update, no_update
    try:
        inputs = AnalysisInputs.from_json(inputs_data)
    except (TypeError, KeyError) as exc:
        logger.exception("Bad analysis-inputs payload")
        return {"_error": f"Invalid stored inputs: {exc}"}, {}, None
    try:
        result = run_analysis(inputs)
    except Exception as exc:
        # Surface any pipeline failure to the UI rather than 500-ing.
        logger.exception("Pipeline failed")
        return {"_error": f"Pipeline error: {exc}"}, {}, None
    payload = result.to_json()
    payload["_fingerprint"] = _inputs_fingerprint(inputs_data)
    return payload, {}, None


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


# --- Chart + map render -----------------------------------------------------


def _resolve_current(
    result_data: dict[str, Any] | None,
    overrides_data: dict[str, Any] | None,
) -> AnalysisResult | None:
    """Return the override-applied `AnalysisResult`, or None.

    Shared between the chart/map render and the viewport callback so
    deserialisation lives in one place. Bad payloads return None;
    the caller emits `no_update`.
    """
    if not result_data or "_error" in result_data:
        return None
    try:
        base = AnalysisResult.from_json(result_data)
    except (TypeError, KeyError, ValueError):
        logger.exception("Bad analysis-result payload (chart/map)")
        return None
    overrides = _coerce_overrides(overrides_data)
    return apply_overrides(base, overrides)


@callback(
    Output("dd-chart", "figure"),
    Output("impact-chart", "figure"),
    Output("results-map-pumping", "children"),
    Output("results-map-wells", "children"),
    Input("analysis-result", "data"),
    Input("well-overrides", "data"),
    Input("selected-well", "data"),
)
def render_chart_and_map(
    result_data: dict[str, Any] | None,
    overrides_data: dict[str, Any] | None,
    selected_data: int | dict[str, Any] | None,
) -> tuple[Any, Any, Any, Any]:
    """Redraw both charts and the well-marker layer.

    Independent of the tables/summary render so that clicking a chart
    point or a map marker (which updates ``selected-well`` only) does
    not retrigger dash_table reconciliation. The two charts and the
    map all consume the same `selected-well` so selection stays in
    sync across views.
    """
    current = _resolve_current(result_data, overrides_data)
    if current is None:
        return no_update, no_update, no_update, no_update
    selected_wtn = _coerce_selected_wtn(selected_data)
    dd_figure = make_distance_drawdown_figure(current, selected_wtn=selected_wtn)
    impact_figure = make_impact_chart(current, selected_wtn=selected_wtn)
    pumping_layer = make_pumping_layer(current)
    well_markers = make_well_markers(current, selected_wtn=selected_wtn)
    return dd_figure, impact_figure, pumping_layer, well_markers


@callback(
    Output("results-map", "viewport"),
    Input("analysis-result", "data"),
    prevent_initial_call=True,
)
def centre_map_on_new_result(
    result_data: dict[str, Any] | None,
) -> dict[str, Any]:
    """Fly the map to the pumping well exactly once per new pipeline run.

    Inputs are only `analysis-result`, not `well-overrides` or
    `selected-well` — overrides and selections must not snap the
    officer back to the pumping well after they've panned around.
    """
    if not result_data or "_error" in result_data:
        return no_update
    try:
        base = AnalysisResult.from_json(result_data)
    except (TypeError, KeyError, ValueError):
        return no_update
    return map_viewport_for(base)


# --- Selection (chart <-> map cross-linking) --------------------------------


def _coerce_selected_wtn(value: int | dict[str, Any] | None) -> int | None:
    """Normalise the `selected-well` store payload to int | None.

    sessionStorage round-trips can stringify; pattern-matching IDs
    arrive as dicts. Drop anything that doesn't resolve to a clean
    int so a malformed store value doesn't crash the renderer.
    """
    if value is None:
        return None
    if isinstance(value, dict):
        value = value.get("wtn")
    try:
        return int(value)  # type: ignore[arg-type]
    except (TypeError, ValueError):
        return None


def _wtn_from_click(click_data: dict[str, Any] | None) -> Any:
    """Pull a WTN out of a Plotly ``clickData`` payload, or no_update.

    Both charts carry the integer WTN in ``customdata`` on their
    well-bearing trace, so the same coercion logic works for both
    and lets us share a body across the two click callbacks.
    """
    if not click_data:
        return no_update
    points = click_data.get("points") or []
    if not points:
        return no_update
    wtn = points[0].get("customdata")
    if wtn is None:
        return no_update
    try:
        return int(wtn)
    except (TypeError, ValueError):
        return no_update


@callback(
    Output("selected-well", "data", allow_duplicate=True),
    Input("dd-chart", "clickData"),
    prevent_initial_call=True,
)
def select_from_dd_chart(click_data: dict[str, Any] | None) -> Any:
    """Capture a click on a well point in the distance-drawdown chart.

    Each Wells-trace point carries the WTN in ``customdata``; clicks
    on the curve or SAD bars have no customdata and are ignored, so
    the user can pan/zoom without accidentally clearing the highlight.
    """
    return _wtn_from_click(click_data)


@callback(
    Output("selected-well", "data", allow_duplicate=True),
    Input("impact-chart", "clickData"),
    prevent_initial_call=True,
)
def select_from_impact_chart(click_data: dict[str, Any] | None) -> Any:
    """Capture a click on a bar in the Impact-% chart.

    The impact-bar trace carries the WTN as ``customdata`` so this
    routes through the same kernel as the distance-drawdown click —
    clicking a bar selects the well across all three views (this
    chart, the distance-drawdown chart, and the map).
    """
    return _wtn_from_click(click_data)


@callback(
    Output("selected-well", "data", allow_duplicate=True),
    Input(
        {"type": "well-marker", "wtn": ALL, "status": ALL},
        "n_clicks",
    ),
    prevent_initial_call=True,
)
def select_from_map(_n_clicks_list: list[int | None]) -> Any:
    """Capture a click on a well marker and write its WTN to the store.

    Uses pattern-matching IDs (``{"type": "well-marker", "wtn":
    <int>, "status": <str>}``) so the callback fires for any marker
    without enumerating every well as an explicit Input. The
    ``status`` key in the marker id is what makes
    `results_map.make_well_markers` remount a marker when an
    override flips its status — we route on the same key here so
    the wider id pattern still matches. ``ctx.triggered_id`` carries
    the clicked marker's dict id; falls through to no_update for the
    "all markers freshly mounted" initial broadcast.
    """
    triggered = ctx.triggered_id
    if not isinstance(triggered, dict):
        return no_update
    wtn = triggered.get("wtn")
    if wtn is None:
        return no_update
    try:
        return int(wtn)
    except (TypeError, ValueError):
        return no_update


# Kick Leaflet to recompute its tile layout the moment the
# results-content container becomes visible. Leaflet measures its
# container at mount time; if the container is `display: none`, the
# map ends up with zero usable size and most tiles never load,
# leaving the user with a mostly-grey rectangle. Dispatching a
# window resize event triggers Leaflet's built-in resize listener,
# which calls invalidateSize() and reloads tiles correctly.
#
# Fires on every change to `results-content.style`; the inner guard
# (`style.display !== 'none'`) makes the transition-to-hidden a noop.
# The 50 ms timeout lets the browser apply the style change before
# we ask for the new dimensions.
clientside_callback(
    """
    function(style) {
        if (style && style.display !== 'none') {
            setTimeout(function() {
                window.dispatchEvent(new Event('resize'));
            }, 50);
        }
        return '';
    }
    """,
    Output("results-map-resize-noop", "children"),
    Input("results-content", "style"),
)
