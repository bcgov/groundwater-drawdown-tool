"""Setup page — define the inputs to one analysis run.

Three input modes for the pumping point (radio at the top):
- "Map click": click anywhere on the dash-leaflet map below.
- "Lat / Lon": type WGS84 coordinates directly.
- "Well tag number": enter a WTN, click Look up; the well's
  geometry and (when available) ``AQUIFER_ID`` are pulled from BCGW.

Each mode feeds the same ``point-store`` (memory-scoped — only
relevant while the page is open). Whenever the point changes, two
follow-up queries fire:

1. ``aquifers_at_point`` -> populate the source-aquifer picker. If
   one polygon contains the point it's auto-selected; for stacked
   polygons (e.g. bedrock under sand-and-gravel) the user picks one.
2. Once a source aquifer is picked, ``subtype_code_for_aquifer`` +
   ``aquifer_lookup.lookup`` -> default T/S. The defaults are shown
   read-only with an "Override" checkbox to expose editable T/S
   inputs. When the lookup yields no default (e.g. subtype ``5b``
   karstic or ``UNK``), override is auto-enabled and required.

Other inputs:
- Pumping rate: numeric + unit dropdown driven by
  ``core.units.load_pumping_rate_units``. Default ``L/s``.
- Pumping duration: numeric, default 100 d (legacy Excel
  convention; CLIENT_TBD: Q4, Q10), with quick presets.
- Buffer radius: 1000 m by default (matches the legacy deck).
- Same-aquifer filter: **off by default** (Q12 confirmed). When on,
  it's a SPATIAL filter — wells whose geometry lies inside the
  source aquifer polygon — not a GWELLS ``AQUIFER_ID`` attribute
  match. Passes ``aquifer_id=None`` to ``nearby_wells`` when off.

"Run Analysis" validates everything, packs an ``AnalysisInputs``
into the app-level ``analysis-inputs`` store, and navigates to
``/results``.
"""

from __future__ import annotations

import logging
from typing import Any

import dash
import dash_leaflet as dl
import oracledb
from dash import (
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
from gwdrawdown.core import aquifer_lookup, crs_utils, units
from gwdrawdown.data_access import get_connection
from gwdrawdown.data_access import queries as q
from gwdrawdown.ui.components.footer import make_footer
from gwdrawdown.ui.session import is_authenticated

dash.register_page(__name__, path="/setup", name="Setup")

logger = logging.getLogger(__name__)

# --- Static input metadata ---------------------------------------------------

DURATION_PRESETS: list[tuple[str, float]] = [
    ("30 d", 30.0),
    ("100 d", 100.0),
    ("1 yr", 365.25),
    ("10 yr", 3652.5),
]

# Vancouver Island default view; covers the Cowichan Bay test point.
MAP_CENTER = [48.8, -123.5]
MAP_ZOOM = 7

# --- Styles ------------------------------------------------------------------

_PAGE_STYLE = {
    "fontFamily": "sans-serif",
    "padding": "1.5rem 2rem",
    "maxWidth": "1100px",
    "margin": "0 auto",
}
_SECTION_STYLE = {
    "border": "1px solid #d0d0d0",
    "borderRadius": "4px",
    "padding": "1rem 1.25rem",
    "marginBottom": "1rem",
    "backgroundColor": "#fafafa",
}
_LABEL_STYLE = {"display": "block", "fontSize": "0.85rem", "marginBottom": "0.25rem"}
_INPUT_STYLE = {"padding": "0.4rem", "marginRight": "0.5rem"}
_BUTTON_STYLE = {
    "padding": "0.45rem 0.9rem",
    "marginRight": "0.5rem",
    "border": "1px solid #1565c0",
    "backgroundColor": "white",
    "color": "#1565c0",
    "borderRadius": "3px",
    "cursor": "pointer",
}
_PRIMARY_BUTTON_STYLE = {
    **_BUTTON_STYLE,
    "backgroundColor": "#1565c0",
    "color": "white",
    "padding": "0.6rem 1.5rem",
    "fontSize": "1rem",
}
_ERROR_STYLE = {"color": "#b00020", "marginTop": "0.5rem", "minHeight": "1.2rem"}


def _build_pumping_rate_options() -> list[dict[str, str]]:
    return [{"label": u.unit, "value": u.unit} for u in units.load_pumping_rate_units()]


def _default_pumping_rate_unit() -> str:
    return units.default_pumping_rate_unit().unit


def _format_float(value: float | None) -> str:
    """Render a float in fixed-point with trailing zeros stripped.

    Python's default ``str(0.00003)`` yields ``"3e-05"``, which is hard
    to read in a Water Officer-facing UI for storativity values like
    ``0.00003`` (subtype 5a) or ``0.00064`` (6a/6b). Force fixed-point.
    """
    if value is None:
        return ""
    formatted = f"{value:.10f}".rstrip("0").rstrip(".")
    return formatted if formatted else "0"


# --- Layout ------------------------------------------------------------------


def layout(**_kwargs: object) -> html.Div:
    if not is_authenticated():
        return html.Div(
            dcc.Location(href="/login", id="setup-redirect-login", refresh=True)
        )

    return html.Div(
        [
            html.H1("Define analysis"),
            # ------------------------------------------------------------------
            # Pumping point input
            # ------------------------------------------------------------------
            html.Div(
                [
                    html.H3("Pumping well location", style={"marginTop": 0}),
                    dcc.RadioItems(
                        id="setup-input-mode",
                        options=[
                            {"label": "Map click", "value": "map"},
                            {"label": "Lat / Lon", "value": "latlon"},
                            {"label": "Well tag number", "value": "wtn"},
                        ],
                        value="map",
                        inline=True,
                        labelStyle={"marginRight": "1rem"},
                        style={"marginBottom": "0.75rem"},
                    ),
                    # Lat/Lon panel
                    html.Div(
                        [
                            dcc.Input(
                                id="setup-latlon-lon",
                                type="number",
                                placeholder="Longitude (e.g. -123.682)",
                                step="any",
                                style={**_INPUT_STYLE, "width": "12rem"},
                            ),
                            dcc.Input(
                                id="setup-latlon-lat",
                                type="number",
                                placeholder="Latitude (e.g. 48.759)",
                                step="any",
                                style={**_INPUT_STYLE, "width": "12rem"},
                            ),
                            html.Button(
                                "Place",
                                id="setup-latlon-submit",
                                n_clicks=0,
                                style=_BUTTON_STYLE,
                            ),
                        ],
                        id="setup-latlon-panel",
                        style={"display": "none", "marginBottom": "0.75rem"},
                    ),
                    # WTN panel
                    html.Div(
                        [
                            dcc.Input(
                                id="setup-wtn-input",
                                type="number",
                                placeholder="WELL_TAG_NUMBER",
                                style={**_INPUT_STYLE, "width": "14rem"},
                            ),
                            html.Button(
                                "Look up",
                                id="setup-wtn-lookup",
                                n_clicks=0,
                                style=_BUTTON_STYLE,
                            ),
                            html.Span(id="setup-wtn-error", style=_ERROR_STYLE),
                        ],
                        id="setup-wtn-panel",
                        style={"display": "none", "marginBottom": "0.75rem"},
                    ),
                    # Map (always visible)
                    dl.Map(
                        id="setup-map",
                        center=MAP_CENTER,
                        zoom=MAP_ZOOM,
                        style={"height": "380px", "width": "100%", "marginBottom": "0.5rem"},
                        children=[
                            dl.TileLayer(),
                            dl.LayerGroup(id="setup-marker-layer", children=[]),
                        ],
                    ),
                    html.Div(id="setup-point-display", style={"fontSize": "0.85rem"}),
                    html.Div(id="setup-mode-error", style=_ERROR_STYLE),
                ],
                style=_SECTION_STYLE,
            ),
            # ------------------------------------------------------------------
            # Source aquifer + T/S
            # ------------------------------------------------------------------
            html.Div(
                [
                    html.H3("Source aquifer", style={"marginTop": 0}),
                    html.Div(
                        "Place a pumping point above to populate this section.",
                        id="setup-aquifer-help",
                        style={"color": "#777", "fontSize": "0.9rem"},
                    ),
                    dcc.RadioItems(
                        id="setup-aquifer-picker",
                        options=[],
                        value=None,
                        labelStyle={"display": "block", "marginBottom": "0.25rem"},
                        style={"marginBottom": "0.5rem"},
                    ),
                    html.Div(
                        id="setup-ts-default-display",
                        style={"fontSize": "0.9rem", "marginBottom": "0.5rem"},
                    ),
                    dcc.Checklist(
                        id="setup-ts-override-toggle",
                        options=[{"label": " Override default T / S", "value": "override"}],
                        value=[],
                        style={"marginBottom": "0.5rem"},
                    ),
                    html.Div(
                        [
                            html.Label("Transmissivity T (m²/day)", style=_LABEL_STYLE),
                            dcc.Input(
                                id="setup-ts-T",
                                type="number",
                                step="any",
                                disabled=True,
                                style={**_INPUT_STYLE, "width": "10rem"},
                            ),
                            html.Label(
                                "Storativity S (dimensionless)",
                                style={**_LABEL_STYLE, "marginTop": "0.5rem"},
                            ),
                            dcc.Input(
                                id="setup-ts-S",
                                type="number",
                                step="any",
                                disabled=True,
                                style={**_INPUT_STYLE, "width": "10rem"},
                            ),
                        ],
                    ),
                ],
                style=_SECTION_STYLE,
            ),
            # ------------------------------------------------------------------
            # Pumping rate, duration, buffer, filter
            # ------------------------------------------------------------------
            html.Div(
                [
                    html.H3("Pumping parameters", style={"marginTop": 0}),
                    html.Label("Pumping rate Q", style=_LABEL_STYLE),
                    html.Div(
                        [
                            dcc.Input(
                                id="setup-q-value",
                                type="number",
                                value=3.97,
                                step="any",
                                min=0,
                                style={**_INPUT_STYLE, "width": "8rem"},
                            ),
                            dcc.Dropdown(
                                id="setup-q-unit",
                                options=_build_pumping_rate_options(),
                                value=_default_pumping_rate_unit(),
                                clearable=False,
                                style={
                                    "width": "8rem",
                                    "display": "inline-block",
                                    "verticalAlign": "middle",
                                },
                            ),
                        ],
                        style={"marginBottom": "0.75rem"},
                    ),
                    html.Label("Pumping duration (days)", style=_LABEL_STYLE),
                    html.Div(
                        [
                            dcc.Input(
                                id="setup-duration",
                                type="number",
                                value=config.DEFAULT_PUMPING_DURATION_DAYS,
                                min=0.001,
                                step="any",
                                style={**_INPUT_STYLE, "width": "8rem"},
                            ),
                        ]
                        + [
                            html.Button(
                                label,
                                id=f"setup-duration-preset-{int(days * 100)}",
                                n_clicks=0,
                                style=_BUTTON_STYLE,
                            )
                            for label, days in DURATION_PRESETS
                        ],
                        style={"marginBottom": "0.75rem"},
                    ),
                    html.Label("Buffer radius (m)", style=_LABEL_STYLE),
                    dcc.Input(
                        id="setup-radius",
                        type="number",
                        value=1000,
                        min=1,
                        step="any",
                        style={**_INPUT_STYLE, "width": "8rem", "marginBottom": "0.75rem"},
                    ),
                    html.Br(),
                    dcc.Checklist(
                        id="setup-filter-toggle",
                        options=[
                            {
                                "label": (
                                    " Filter out wells spatially outside "
                                    "source aquifer"
                                ),
                                "value": "filter",
                            }
                        ],
                        # Default off (Q12 confirmed). The officer
                        # sees every well in the buffer first and
                        # opts in to the spatial filter when needed.
                        value=[],
                        style={"marginTop": "0.5rem"},
                    ),
                ],
                style=_SECTION_STYLE,
            ),
            # ------------------------------------------------------------------
            # Run analysis
            # ------------------------------------------------------------------
            html.Div(
                [
                    html.Button(
                        "Run Analysis",
                        id="setup-run",
                        n_clicks=0,
                        style=_PRIMARY_BUTTON_STYLE,
                    ),
                    html.Div(id="setup-run-error", style=_ERROR_STYLE),
                ],
                style={"marginTop": "1rem"},
            ),
            # Hidden state
            dcc.Store(id="setup-point-store", storage_type="memory"),
            dcc.Store(id="setup-lookup-ts-store", storage_type="memory"),
            # Counter incremented on each successful Run Analysis click;
            # a clientside callback watches this and opens /results in
            # a new browser tab. The new tab inherits sessionStorage at
            # the moment of opening, so each tab carries its own
            # snapshot of analysis-inputs and re-runs in the parent
            # don't disturb earlier results tabs.
            dcc.Store(id="setup-results-trigger", storage_type="memory", data=0),
            # Page-mount trigger for `hydrate_setup_form`. Re-created
            # on every visit to /setup so the hydration callback fires
            # each time the user comes back from /results.
            dcc.Store(id="setup-mount-trigger", storage_type="memory", data={}),
            # One-shot flag: True until `restore_saved_aquifer` has
            # re-selected the previously-run aquifer. Subsequent point
            # changes leave it False so the auto-pick logic in
            # `fetch_aquifers` takes over again.
            dcc.Store(id="setup-restore-pending", storage_type="memory", data=True),
            html.Div(id="setup-results-noop", style={"display": "none"}),
            make_footer(),
        ],
        style=_PAGE_STYLE,
    )


# --- Callbacks ---------------------------------------------------------------


@callback(
    Output("setup-latlon-panel", "style"),
    Output("setup-wtn-panel", "style"),
    Input("setup-input-mode", "value"),
)
def toggle_input_panels(mode: str) -> tuple[dict, dict]:
    base = {"marginBottom": "0.75rem"}
    return (
        {**base, "display": "block" if mode == "latlon" else "none"},
        {**base, "display": "block" if mode == "wtn" else "none"},
    )


@callback(
    Output("setup-point-store", "data", allow_duplicate=True),
    Output("setup-mode-error", "children"),
    Output("setup-wtn-error", "children"),
    Input("setup-map", "n_clicks"),
    Input("setup-latlon-submit", "n_clicks"),
    Input("setup-wtn-lookup", "n_clicks"),
    State("setup-map", "clickData"),
    State("setup-input-mode", "value"),
    State("setup-latlon-lon", "value"),
    State("setup-latlon-lat", "value"),
    State("setup-wtn-input", "value"),
    prevent_initial_call=True,
)
def update_point_store(
    _map_n: int,
    _latlon_n: int,
    _wtn_n: int,
    map_click_data: dict | None,
    mode: str,
    lon_in: float | None,
    lat_in: float | None,
    wtn_in: int | None,
) -> tuple[Any, str, str]:
    triggered = ctx.triggered_id

    if triggered == "setup-map":
        if mode != "map" or not map_click_data:
            return no_update, "", ""
        latlng = map_click_data.get("latlng") or {}
        lat = latlng.get("lat")
        lon = latlng.get("lng")
        if lat is None or lon is None:
            return no_update, "", ""
        lat, lon = float(lat), float(lon)
        x, y = crs_utils.to_albers(lon, lat)
        return (
            {"lon": lon, "lat": lat, "x": x, "y": y, "mode": "map"},
            "",
            "",
        )

    if triggered == "setup-latlon-submit":
        if mode != "latlon":
            return no_update, "Switch input mode to 'Lat / Lon' first.", ""
        if lon_in is None or lat_in is None:
            return no_update, "Enter both longitude and latitude.", ""
        lon, lat = float(lon_in), float(lat_in)
        x, y = crs_utils.to_albers(lon, lat)
        return (
            {"lon": lon, "lat": lat, "x": x, "y": y, "mode": "latlon"},
            "",
            "",
        )

    if triggered == "setup-wtn-lookup":
        if mode != "wtn":
            return no_update, "", "Switch input mode to 'Well tag number' first."
        if not wtn_in:
            return no_update, "", "Enter a well tag number."
        try:
            with get_connection() as conn:
                row = q.well_by_tag(conn, int(wtn_in))
        except oracledb.DatabaseError as e:
            logger.warning("WTN lookup failed for %r: %s", wtn_in, e)
            return no_update, "", f"Lookup failed: {e}"
        if row is None:
            return no_update, "", f"WTN {int(wtn_in)} not found."
        x = float(row["X_ALBERS"])
        y = float(row["Y_ALBERS"])
        lon, lat = crs_utils.to_wgs84(x, y)
        auto = row.get("AQUIFER_ID")
        return (
            {
                "lon": lon,
                "lat": lat,
                "x": x,
                "y": y,
                "mode": "wtn",
                "auto_aquifer_id": int(auto) if auto is not None else None,
                "wtn": int(wtn_in),
            },
            "",
            "",
        )

    return no_update, "", ""


@callback(
    Output("setup-marker-layer", "children"),
    Output("setup-point-display", "children"),
    Input("setup-point-store", "data"),
)
def update_marker_and_display(point: dict | None) -> tuple[list, str]:
    if not point:
        return [], "No point placed yet."
    marker = dl.Marker(position=[point["lat"], point["lon"]])
    label = (
        f"WGS84: ({point['lon']:.6f}, {point['lat']:.6f}) | "
        f"BC Albers: ({point['x']:.1f}, {point['y']:.1f}) | "
        f"input: {point['mode']}"
    )
    if point.get("wtn") is not None:
        label += f" | WTN {point['wtn']}"
    return [marker], label


@callback(
    Output("setup-aquifer-picker", "options"),
    Output("setup-aquifer-picker", "value", allow_duplicate=True),
    Output("setup-aquifer-help", "children"),
    Input("setup-point-store", "data"),
    prevent_initial_call="initial_duplicate",
)
def fetch_aquifers(point: dict | None) -> tuple[list[dict], int | None, str]:
    if not point:
        return [], None, "Place a pumping point above to populate this section."
    try:
        with get_connection() as conn:
            aquifers = q.aquifers_at_point(conn, x_albers=point["x"], y_albers=point["y"])
    except oracledb.DatabaseError as e:
        logger.warning("aquifers_at_point failed: %s", e)
        return [], None, f"Aquifer query failed: {e}"
    except Exception as e:
        logger.exception("Unexpected aquifers_at_point error")
        return [], None, f"Unexpected error: {e}"

    options = [
        {
            "label": f"{a['NAME']} (id {a['AQUIFER_ID']}, {a['SUBTYPE']})",
            "value": int(a["AQUIFER_ID"]),
        }
        for a in aquifers
    ]
    if not options:
        return [], None, "No aquifer polygon contains this point."

    auto = point.get("auto_aquifer_id")
    if auto is not None and any(o["value"] == auto for o in options):
        value: int | None = auto
    elif len(options) == 1:
        value = options[0]["value"]
    else:
        value = None

    help_text = (
        "One aquifer at this point — auto-selected."
        if len(options) == 1
        else f"{len(options)} aquifers at this point — pick the source."
    )
    return options, value, help_text


@callback(
    Output("setup-lookup-ts-store", "data"),
    Output("setup-ts-default-display", "children"),
    Output("setup-ts-override-toggle", "value"),
    Input("setup-aquifer-picker", "value"),
)
def fetch_ts_lookup(
    aquifer_id: int | None,
) -> tuple[dict | None, str, list[str]]:
    if aquifer_id is None:
        return None, "", []
    try:
        with get_connection() as conn:
            subtype = q.subtype_code_for_aquifer(conn, aquifer_id)
    except oracledb.DatabaseError as e:
        logger.warning("subtype lookup failed for aquifer %d: %s", aquifer_id, e)
        return None, f"Subtype lookup failed: {e}", ["override"]

    props = aquifer_lookup.lookup(subtype)
    if props is None:
        return (
            {"subtype_code": subtype, "T": None, "S": None},
            f"Subtype {subtype!r} has no T/S default — override required.",
            ["override"],
        )
    return (
        {"subtype_code": subtype, "T": props.T_m2_per_day, "S": props.S},
        (
            f"Subtype {subtype}: default T = {_format_float(props.T_m2_per_day)} "
            f"m²/day, S = {_format_float(props.S)}"
        ),
        [],
    )


@callback(
    Output("setup-ts-T", "disabled"),
    Output("setup-ts-S", "disabled"),
    Output("setup-ts-T", "value"),
    Output("setup-ts-S", "value"),
    Input("setup-ts-override-toggle", "value"),
    Input("setup-lookup-ts-store", "data"),
)
def toggle_override_inputs(
    toggle: list[str],
    lookup: dict | None,
) -> tuple[bool, bool, float | None, float | None]:
    """Always show the lookup defaults in the T/S boxes; toggle just controls editability.

    Picking a different aquifer resets the boxes to that aquifer's
    defaults (and clears any prior override). To customise, the user
    ticks "Override default T / S" and edits in place.
    """
    enabled = "override" in (toggle or [])
    default_T = (lookup or {}).get("T")
    default_S = (lookup or {}).get("S")
    return (not enabled), (not enabled), default_T, default_S


@callback(
    Output("setup-duration", "value", allow_duplicate=True),
    [
        Input(f"setup-duration-preset-{int(days * 100)}", "n_clicks")
        for _, days in DURATION_PRESETS
    ],
    prevent_initial_call=True,
)
def apply_duration_preset(*_n_clicks: int) -> float:
    triggered = ctx.triggered_id
    for _, days in DURATION_PRESETS:
        if triggered == f"setup-duration-preset-{int(days * 100)}":
            return days
    return no_update  # type: ignore[return-value]


@callback(
    Output("analysis-inputs", "data"),
    Output("setup-results-trigger", "data"),
    Output("setup-run-error", "children"),
    Input("setup-run", "n_clicks"),
    State("setup-point-store", "data"),
    State("setup-aquifer-picker", "value"),
    State("setup-aquifer-picker", "options"),
    State("setup-lookup-ts-store", "data"),
    State("setup-ts-override-toggle", "value"),
    State("setup-ts-T", "value"),
    State("setup-ts-S", "value"),
    State("setup-q-value", "value"),
    State("setup-q-unit", "value"),
    State("setup-duration", "value"),
    State("setup-radius", "value"),
    State("setup-filter-toggle", "value"),
    State("setup-results-trigger", "data"),
    prevent_initial_call=True,
)
def run_analysis_click(
    _n: int,
    point: dict | None,
    aquifer_id: int | None,
    aquifer_options: list[dict] | None,
    lookup: dict | None,
    override_toggle: list[str],
    override_T: float | None,
    override_S: float | None,
    q_value: float | None,
    q_unit: str | None,
    duration_days: float | None,
    radius_m: float | None,
    filter_toggle: list[str],
    current_trigger: int | None,
) -> tuple[Any, Any, str]:
    if not point:
        return no_update, no_update, "Place a pumping point first."
    if aquifer_id is None:
        return no_update, no_update, "Pick a source aquifer."

    override_on = "override" in (override_toggle or [])
    if override_on:
        T_value, S_value = override_T, override_S
    else:
        T_value = (lookup or {}).get("T")
        S_value = (lookup or {}).get("S")
    if T_value is None or S_value is None:
        return no_update, no_update, (
            "T and S are required. Tick 'Override default T / S' and enter values."
        )
    if T_value <= 0 or S_value <= 0:
        return no_update, no_update, "T and S must be positive."

    if not q_value or q_value <= 0:
        return no_update, no_update, "Pumping rate Q must be positive."
    if not q_unit:
        return no_update, no_update, "Pick a pumping-rate unit."
    if not duration_days or duration_days <= 0:
        return no_update, no_update, "Duration must be positive."
    if not radius_m or radius_m <= 0:
        return no_update, no_update, "Buffer radius must be positive."

    aquifer_name = next(
        (
            o["label"]
            for o in (aquifer_options or [])
            if o.get("value") == aquifer_id
        ),
        f"Aquifer {aquifer_id}",
    )

    Q_m3_per_day = units.pumping_rate_to_m3_per_day(float(q_value), q_unit)

    inputs = {
        "pumping_lon": float(point["lon"]),
        "pumping_lat": float(point["lat"]),
        "pumping_x_albers": float(point["x"]),
        "pumping_y_albers": float(point["y"]),
        "source_aquifer_id": int(aquifer_id),
        "source_aquifer_name": aquifer_name,
        "source_subtype_code": (lookup or {}).get("subtype_code"),
        "transmissivity_m2_per_day": float(T_value),
        "storativity": float(S_value),
        "ts_overridden": bool(override_on),
        "Q_value": float(q_value),
        "Q_unit": q_unit,
        "Q_m3_per_day": float(Q_m3_per_day),
        "duration_days": float(duration_days),
        "buffer_radius_m": float(radius_m),
        "same_aquifer_filter": "filter" in (filter_toggle or []),
        "u_threshold": config.COOPER_JACOB_U_THRESHOLD,
        "at_risk_fraction": config.AT_RISK_DRAWDOWN_FRACTION,
    }
    next_trigger = (current_trigger or 0) + 1
    return inputs, next_trigger, ""


# Clientside: watch the trigger counter and open /results in a new
# tab when it increments. The new tab inherits the parent's
# sessionStorage at the moment of window.open, so it carries the
# just-stored analysis-inputs without further server roundtrip.
clientside_callback(
    """
    function(trigger) {
        if (trigger && trigger > 0) {
            window.open('/results', '_blank');
        }
        return '';
    }
    """,
    Output("setup-results-noop", "children"),
    Input("setup-results-trigger", "data"),
    prevent_initial_call=True,
)


# --- Form hydration on Back-to-Setup ----------------------------------------
#
# The setup page re-mounts on every visit, so all `dcc.Input` / `dcc.Dropdown`
# / `dcc.RadioItems` values reset to their hardcoded defaults. To avoid making
# the officer re-key Q, duration, radius, etc. on every iteration, these two
# callbacks read `analysis-inputs` (sessionStorage, populated by the last
# successful Run Analysis) and replay it into the form.
#
# T/S override values are NOT restored. The existing
# `toggle_override_inputs` callback unconditionally rewrites T/S from the
# lookup whenever the override toggle or the lookup store changes, and
# layering a one-shot replay on top of that is fragile. If you customised
# T and S, re-tick "Override default T / S" and re-enter — uncommon
# enough that the simpler logic wins.


@callback(
    Output("setup-point-store", "data", allow_duplicate=True),
    Output("setup-input-mode", "value"),
    Output("setup-latlon-lon", "value"),
    Output("setup-latlon-lat", "value"),
    Output("setup-q-value", "value"),
    Output("setup-q-unit", "value"),
    Output("setup-duration", "value", allow_duplicate=True),
    Output("setup-radius", "value"),
    Output("setup-filter-toggle", "value"),
    Input("setup-mount-trigger", "data"),
    State("analysis-inputs", "data"),
    prevent_initial_call="initial_duplicate",
)
def hydrate_setup_form(
    _trigger: dict[str, Any],
    inputs_data: dict[str, Any] | None,
) -> tuple[Any, ...]:
    """Replay the last `analysis-inputs` into the form on page mount.

    Fires once per /setup mount via the always-present
    ``setup-mount-trigger`` Store. When the user has never run an
    analysis (or their session has been cleared), `inputs_data` is
    ``None`` and every output is `no_update`, so the form keeps its
    hardcoded defaults.
    """
    if not inputs_data:
        return tuple(no_update for _ in range(9))
    point = {
        "lon": float(inputs_data["pumping_lon"]),
        "lat": float(inputs_data["pumping_lat"]),
        "x": float(inputs_data["pumping_x_albers"]),
        "y": float(inputs_data["pumping_y_albers"]),
        # `mode` is informational on the marker label only; we don't
        # remember which input mode the officer used last time.
        "mode": "map",
    }
    return (
        point,
        "map",
        float(inputs_data["pumping_lon"]),
        float(inputs_data["pumping_lat"]),
        float(inputs_data["Q_value"]),
        inputs_data["Q_unit"],
        float(inputs_data["duration_days"]),
        float(inputs_data["buffer_radius_m"]),
        ["filter"] if inputs_data.get("same_aquifer_filter") else [],
    )


@callback(
    Output("setup-aquifer-picker", "value", allow_duplicate=True),
    Output("setup-restore-pending", "data"),
    Input("setup-aquifer-picker", "options"),
    State("analysis-inputs", "data"),
    State("setup-restore-pending", "data"),
    prevent_initial_call=True,
)
def restore_saved_aquifer(
    options: list[dict] | None,
    inputs_data: dict[str, Any] | None,
    pending: bool | None,
) -> tuple[Any, Any]:
    """Re-select the saved aquifer once `fetch_aquifers` populates options.

    One-shot: ``setup-restore-pending`` flips to ``False`` after the
    first try (success or not) so subsequent point changes go through
    the normal auto-pick logic in `fetch_aquifers` instead of jumping
    back to the previous run's aquifer.
    """
    if not pending:
        return no_update, no_update
    if not inputs_data or not options:
        return no_update, False
    saved_id = inputs_data.get("source_aquifer_id")
    if saved_id is None:
        return no_update, False
    if any(o.get("value") == saved_id for o in options):
        return saved_id, False
    return no_update, False
