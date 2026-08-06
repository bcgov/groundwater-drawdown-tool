"""Results page — sub-stage 4c.3 dashboard with chart, map and overrides.

Layout from top:

1. Header — H1 + "Back to Setup" link.
2. Run summary — timestamp, signed-in user, source aquifer, T/S used
   (with "(override)" tag when applicable), Q in m³/day, duration,
   buffer radius, source-aquifer filter on/off (spatial).
3. Stat cards — six status counts. (No max-drawdown tile: removed at
   client request, see `ui/components/stat_cards.py`.)
4. "Method, assumptions and limitations" — a collapsed ``<details>``
   panel carrying the client-supplied guidance that isn't tied to a
   single control, plus the at-risk threshold explanation.
5. Distance-drawdown chart — four traces (wells, Cooper-Jacob curve,
   and SAD bars split into headroom / exceedance), inverted Y,
   log-spaced X, with a 0 m reference line. Click a point to select
   it; the map highlights the matching marker.
6. Colour-coded map — pumping well + buffer + per-well markers
   (status colour, impact-magnitude radius, dark ring on licensed
   wells). Click a marker to select it; the chart highlights the
   matching point.
7. At-risk wells table — filtered to ``WellStatus.AT_RISK`` only.
8. Per-well details table — full 19-column table with sort, filter,
   pagination (10/page), CSV export, four editable columns (NPL,
   finished depth, stickup, top of fracture/screen), and a Reset
   button. Status cell colour-coded per `WellStatus`. Rows with
   active overrides are tinted light yellow; rows failing the
   Cooper-Jacob u<threshold advisory are tinted light purple
   (purple wins on rows tripping both). A row-tint legend +
   pagination reminder sit just above the table.
9. Footer.

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
    State,
    callback,
    clientside_callback,
    ctx,
    dcc,
    html,
    no_update,
)

from gwdrawdown import config
from gwdrawdown.analysis import (
    AnalysisInputs,
    AnalysisResult,
    apply_overrides,
    run_analysis,
)
from gwdrawdown.ui import disclaimers
from gwdrawdown.ui.components.basemaps import (
    WMD_OVERLAY_NAME,
    WMP_OVERLAY_NAME,
    wms_legend_children,
)
from gwdrawdown.ui.components.dd_chart import make_distance_drawdown_figure
from gwdrawdown.ui.components.export_bar import build_export_bar
from gwdrawdown.ui.components.footer import make_footer
from gwdrawdown.ui.components.header import make_header
from gwdrawdown.ui.components.impact_chart import make_impact_chart
from gwdrawdown.ui.components.map_labels import build_boundary_label_markers
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
from gwdrawdown.ui.format_utils import format_float, format_source_aquifer
from gwdrawdown.ui.session import current_user, is_authenticated
from gwdrawdown.usage_logger import get_usage_logger

dash.register_page(__name__, path="/results", name="Results")

logger = logging.getLogger(__name__)

_SUMMARY_STYLE = {
    "border": "1px solid var(--bc-border, #D9D9D9)",
    "borderRadius": "var(--bc-radius-lg, 6px)",
    "padding": "1rem 1.25rem",
    "marginBottom": "1.5rem",
    "backgroundColor": "var(--bc-surface, #FFFFFF)",
    "boxShadow": "var(--bc-shadow-sm, 0 1px 2px rgba(0,0,0,0.06))",
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
            make_header(),
            html.Main(
                [
                    html.Div(
                        [
                            html.H1(
                                "Results",
                                style={"margin": 0, "flex": "1 1 auto"},
                            ),
                            dcc.Link(
                                "← Back to Setup",
                                href="/setup",
                                className="bc-btn bc-btn--secondary",
                            ),
                        ],
                        style={
                            "display": "flex",
                            "alignItems": "center",
                            "gap": "1rem",
                            "marginBottom": "1rem",
                        },
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
                    build_export_bar(),
                    _method_panel(),
                    html.H2(
                        "Distance-drawdown",
                        className="bc-results-heading",
                    ),
                    # The hover readout on this chart names s and r
                    # without defining them; officers less familiar with
                    # the notation asked for a plain-language key
                    # (client feedback, 2026-07).
                    html.P(
                        [
                            "Each point is one well. r = radial distance from "
                            "the pumping well (m); s = predicted drawdown at "
                            "that distance (m). The black curve is the "
                            "Cooper-Jacob solution; hover any point for its "
                            "values. The dotted line at 0 m is the "
                            "pre-pumping water level.",
                            html.Br(),
                            "Each vertical bar runs between a well's predicted "
                            "drawdown and its Safe Available Drawdown (SAD). ",
                            html.Strong("Orange"),
                            " bars hang below the well point — headroom "
                            "remains. ",
                            html.Strong("Red"),
                            " bars run upward, meaning predicted drawdown has "
                            "exceeded that well's SAD.",
                        ],
                        className="bc-results-helper",
                    ),
                    # Well tag numbers alternate above and below their
                    # point, which separates any adjacent pair. On a
                    # buffer crowded enough that no placement rule
                    # helps, this switches them off entirely — the
                    # client's own suggested fallback. Hover still
                    # names every well, and the PDF captures whatever
                    # is on screen.
                    dcc.Checklist(
                        id="dd-labels-toggle",
                        options=[
                            {
                                "label": " Show well tag numbers on the chart",
                                "value": "show",
                            }
                        ],
                        value=["show"],
                        className="bc-results-helper",
                        style={"marginBottom": "0.25rem"},
                        inputStyle={"marginRight": "0.3rem"},
                    ),
                    dcc.Graph(
                        id="dd-chart",
                        # Drop the "Autoscale" button: on the inverted Y
                        # axis it could flip the axis upright and not
                        # recover (tester report). "Reset axes" stays and
                        # restores the explicit reversed range.
                        config={
                            "displaylogo": False,
                            "modeBarButtonsToRemove": ["autoScale2d"],
                        },
                        style={"marginBottom": "1.5rem"},
                    ),
                    html.H2(
                        "Impact % per well",
                        className="bc-results-heading",
                    ),
                    # "dashed red line" was wrong — the threshold line is
                    # drawn dark on purpose so it doesn't blend into the
                    # red AT_RISK bars beside it. The caption follows the
                    # line, not the other way round (client feedback,
                    # 2026-07).
                    html.P(
                        "Sorted by magnitude of impact; the dashed vertical "
                        "line marks the at-risk threshold. Wells with no "
                        "computable impact (missing NPL or depth) are "
                        "excluded — see the details table below. For what "
                        "the threshold means, see \"Method, assumptions and "
                        "limitations\" above.",
                        className="bc-results-helper",
                    ),
                    dcc.Graph(
                        id="impact-chart",
                        config={"displaylogo": False},
                        style={"marginBottom": "1.5rem"},
                    ),
                    html.H2(
                        "Wells in buffer (map view)",
                        className="bc-results-heading",
                    ),
                    html.P(
                        [
                            "Marker colour matches the Status column; marker "
                            "size scales with predicted impact. A dark ring "
                            "marks a currently licensed well (Historical and "
                            "Unlicensed wells are unringed). Click a marker "
                            "to highlight the matching point on the chart "
                            "above.",
                        ],
                        className="bc-results-helper",
                    ),
                    build_map_skeleton(),
                    build_at_risk_section(),
                    build_per_well_section(),
                    # A second "Back to Setup" at the foot of the page so
                    # the officer doesn't have to scroll all the way back
                    # up after reading the per-well table. Right-aligned
                    # to line up with the header-row link.
                    html.Div(
                        dcc.Link(
                            "← Back to Setup",
                            href="/setup",
                            className="bc-btn bc-btn--secondary",
                        ),
                        style={
                            "marginTop": "1.5rem",
                            "display": "flex",
                            "justifyContent": "flex-end",
                        },
                    ),
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
                ],
                className="bc-page__content",
            ),
            make_footer(),
        ],
        className="bc-page",
    )


_MANUAL_BANNER_STYLE = {
    "border": "1px solid #cc6600",
    "borderLeft": "4px solid #cc6600",
    "backgroundColor": "rgba(204, 102, 0, 0.08)",
    "color": "#5c2e00",
    "padding": "0.75rem 1rem",
    "borderRadius": "var(--bc-radius-lg, 6px)",
    "marginBottom": "1rem",
    "fontSize": "0.9rem",
    "lineHeight": 1.5,
}


def _method_panel() -> html.Details:
    """Collapsible "Method, assumptions and limitations" disclosure.

    Carries the client-supplied guidance that isn't tied to one control
    (`disclaimers.METHOD_GUIDANCE`) plus the at-risk threshold
    explanation. The two paragraphs that *are* tied to a control live
    next to it instead — ``AQUIFER_DEFAULTS`` under the setup page's
    T/S inputs and ``VERIFY_SOURCES`` on the per-well table — so they
    are read at the moment they matter.

    Static, not callback-rendered. The threshold text reads
    ``config.AT_RISK_DRAWDOWN_FRACTION`` rather than the per-run
    ``inputs.at_risk_fraction``; the packer copies one into the other,
    so they agree, and keeping this static avoids adding a twelfth
    output to `render`'s hand-counted output list.

    A native ``<details>`` rather than a modal: no state to manage, it
    works before hydration, it prints expanded, and it is
    keyboard-accessible without extra work.
    """
    paragraphs = [
        *disclaimers.METHOD_GUIDANCE,
        disclaimers.at_risk_threshold_explanation(
            config.AT_RISK_DRAWDOWN_FRACTION
        ),
    ]
    return html.Details(
        [
            html.Summary("Method, assumptions and limitations"),
            *[html.P(text) for text in paragraphs],
        ],
        className="bc-method-panel",
    )


def _manual_entry_banner(inputs: AnalysisInputs) -> html.Div:
    """Warning banner shown above the run summary in manual-entry mode.

    Surfaces the fact that the run was based on user-supplied material
    and T/S rather than a mapped aquifer polygon. The reviewer sees this
    on /results, and the same text is carried into the PDF export.

    The banner deliberately no longer claims "no mapped aquifer contains
    this location": since the "Other" option became available even where
    polygons *do* overlap, the run means "the officer declared an
    undelineated aquifer", which is not the same statement. The nearest
    mapped aquifer is named instead so a reviewer can see what was
    passed over (client feedback, 2026-07).
    """
    material_txt = inputs.manual_material or "unspecified"
    parts: list[Any] = [
        html.Strong("Undelineated aquifer. "),
        "The pumping well was recorded as completed in an aquifer that has "
        f"not been delineated. Material ({material_txt}) and T / S values "
        "were supplied by the user.",
    ]
    if inputs.nearest_mapped_aquifer:
        parts.append(f" Nearest mapped aquifer: {inputs.nearest_mapped_aquifer}.")
    else:
        parts.append(" No mapped aquifer was found near this location.")
    return html.Div(parts, style=_MANUAL_BANNER_STYLE)


def _summary_block(result: AnalysisResult) -> html.Div:
    inputs = result.inputs
    user = current_user() or "—"
    ts = result.run_timestamp.strftime("%Y-%m-%d %H:%M:%S")
    ts_tag = " (override)" if inputs.ts_overridden else ""

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

    source_text = format_source_aquifer(inputs)
    filter_tag = (
        "n/a (manual entry)"
        if inputs.is_manual_mode
        else ("ON" if inputs.same_aquifer_filter else "off")
    )

    summary_card = html.Div(
        [
            row("Run timestamp:", ts),
            row("BCGW user:", user),
            row("Source aquifer:", source_text),
            row(
                "T / S used:",
                f"T = {format_float(inputs.transmissivity_m2_per_day)} m²/day, "
                f"S = {format_float(inputs.storativity)}{ts_tag}",
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

    if inputs.is_manual_mode:
        return html.Div(
            [_manual_entry_banner(inputs), summary_card]
        )
    return summary_card


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
    State("analysis-result", "data"),
    prevent_initial_call="initial_duplicate",
)
def run_pipeline_if_needed(
    inputs_data: dict[str, Any] | None,
    cached_result: dict[str, Any] | None,
) -> tuple[Any, Any, Any]:
    """Run the BCGW pipeline when `analysis-inputs` changes.

    Caches the result in `analysis-result` so override edits and tab
    refreshes don't replay the pipeline: when the cached result's
    ``_fingerprint`` still matches the current inputs (e.g. an F5 on
    this tab re-fires the initial call with unchanged sessionStorage),
    everything is left untouched — including any per-well overrides
    the officer has entered. Only a genuinely new run clears
    `well-overrides` and `selected-well`, because the previous state
    referenced WTNs that may not appear in the new well set. An error
    payload carries no fingerprint, so a refresh after a failed run
    retries the pipeline.
    """
    if not inputs_data:
        return no_update, no_update, no_update
    if (
        cached_result
        and cached_result.get("_fingerprint") == _inputs_fingerprint(inputs_data)
    ):
        return no_update, no_update, no_update
    bcgw_user = current_user()
    try:
        inputs = AnalysisInputs.from_json(inputs_data)
    except (TypeError, KeyError) as exc:
        logger.exception("Bad analysis-inputs payload")
        return {"_error": f"Invalid stored inputs: {exc}"}, {}, None
    try:
        result = run_analysis(inputs)
    except Exception as exc:
        # Surface any pipeline failure to the UI rather than 500-ing.
        # usage_logged=True so the UsageLogHandler doesn't forward this
        # as a duplicate of the log_analysis_error detail event below.
        logger.exception("Pipeline failed", extra={"usage_logged": True})
        get_usage_logger().log_analysis_error(
            f"Pipeline error: {exc}", bcgw_user=bcgw_user
        )
        return {"_error": f"Pipeline error: {exc}"}, {}, None
    # One usage-log summary record per fresh run. Override recomputes and
    # tab refreshes reuse the cached `analysis-result` and never reach here.
    get_usage_logger().log_analysis(result, bcgw_user=bcgw_user)
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
# Reveal styling for the at-risk / per-well empty-state messages. Kept in
# sync with `_EMPTY_MESSAGE_STYLE` in `results_table`; the render callback
# swaps in this whole dict to show the message as a bordered, tinted
# callout (the old grey italic line was easy to overlook).
_EMPTY_VISIBLE = {
    "display": "block",
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
    Input("dd-labels-toggle", "value"),
)
def render_chart_and_map(
    result_data: dict[str, Any] | None,
    overrides_data: dict[str, Any] | None,
    selected_data: int | dict[str, Any] | None,
    dd_label_toggle: list[str] | None,
) -> tuple[Any, Any, Any, Any]:
    """Redraw both charts and the well-marker layer.

    Independent of the tables/summary render so that clicking a chart
    point or a map marker (which updates ``selected-well`` only) does
    not retrigger dash_table reconciliation. The two charts and the
    map all consume the same `selected-well` so selection stays in
    sync across views.

    The WTN-label toggle only affects the distance-drawdown figure;
    it shares this callback rather than owning one so there is a
    single place that turns cached result + overrides into figures.
    Redrawing the map markers on a toggle click is wasted work, but
    it is cheap and keeps the render path undivided.
    """
    current = _resolve_current(result_data, overrides_data)
    if current is None:
        return no_update, no_update, no_update, no_update
    selected_wtn = _coerce_selected_wtn(selected_data)
    dd_figure = make_distance_drawdown_figure(
        current,
        selected_wtn=selected_wtn,
        show_labels="show" in (dd_label_toggle or []),
    )
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


# --- Dynamic water management boundary labels --------------------------------
#
# Mirrors the matching callback on the setup page. Fires on map
# moveend (`bounds`) and on overlay toggles (`overlays`); rebuilds the
# label LayerGroup so each visible WMD/WMP polygon carries a name
# anchored to its visible centre. See `ui/components/map_labels.py`.


@callback(
    Output("results-map-labels", "children"),
    Input("results-map", "bounds"),
    Input("results-layers-control", "overlays"),
)
def update_boundary_labels(
    bounds: list | None,
    overlays: list[str] | None,
) -> list[Any]:
    active = overlays or []
    return build_boundary_label_markers(
        bounds,
        show_wmd=WMD_OVERLAY_NAME in active,
        show_wmp=WMP_OVERLAY_NAME in active,
    )


# --- WMS symbology legend ----------------------------------------------------
#
# The results map offers only the aquifer WMS overlay (no wells), so
# the legend carries at most the aquifer swatch.


@callback(
    Output("results-wms-legend", "children"),
    Input("results-layers-control", "overlays"),
)
def update_wms_legend(overlays: list[str] | None) -> list[Any]:
    return wms_legend_children(overlays, include_wells=False)
