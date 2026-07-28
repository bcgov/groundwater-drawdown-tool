"""Setup page — define the inputs to one analysis run.

Three input modes for the pumping point (radio at the top):
- "Map click": click anywhere on the dash-leaflet map below.
- "Lat / Lon": type WGS84 coordinates directly.
- "Well tag number": enter a WTN, click Look up; the well's
  geometry and (when available) ``AQUIFER_ID`` are pulled from BCGW.

Each mode feeds the same ``point-store`` (memory-scoped — only
relevant while the page is open). Whenever the point changes, two
follow-up queries fire:

1. ``aquifers_at_point`` + ``aquifers_near_point`` -> populate the
   source-aquifer picker. Both run on every point placement: direct
   hits are listed first (tagged "directly overlapping"; a single
   hit is auto-selected, stacked polygons leave the pick to the
   user), and aquifers within 1000 m (top 3 nearest) are listed
   below tagged with distance — so a nearby aquifer can be picked
   even when the well directly overlaps a different one. When **no**
   polygon contains the point, a "No mapped aquifer at this location
   — enter materials manually" option is pinned at the bottom; if no
   aquifers are found within 1000 m either, the picker shows only
   that manual option with a note explaining nothing nearby was
   found.
2. Once a source aquifer is picked, ``subtype_code_for_aquifer`` +
   ``aquifer_lookup.lookup`` -> default T/S. The defaults are shown
   read-only with an "Override" checkbox to expose editable T/S
   inputs. When the lookup yields no default (e.g. subtype ``5b``
   karstic or ``UNK``), override is auto-enabled and required. In
   manual-entry mode there's no subtype lookup — the material
   dropdown is shown instead and T/S inputs are mandatory.

Other inputs:
- Pumping rate: numeric + unit dropdown driven by
  ``core.units.load_pumping_rate_units``. Default ``L/s``.
- Pumping duration: numeric, default 90 d (client-confirmed
  for all of BC), with quick presets.
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
from gwdrawdown.analysis import MANUAL_AQUIFER_MATERIALS
from gwdrawdown.core import aquifer_lookup, crs_utils, units
from gwdrawdown.data_access import get_connection
from gwdrawdown.data_access import queries as q
from gwdrawdown.ui.components.basemaps import (
    WMD_OVERLAY_NAME,
    WMP_OVERLAY_NAME,
    make_layers_control,
    make_wms_legend,
    wms_legend_children,
)
from gwdrawdown.ui.components.footer import make_footer
from gwdrawdown.ui.components.header import make_header
from gwdrawdown.ui.components.icons import icon
from gwdrawdown.ui.components.map_labels import build_boundary_label_markers
from gwdrawdown.ui.format_utils import format_float
from gwdrawdown.ui.session import is_authenticated

dash.register_page(__name__, path="/setup", name="Setup")

logger = logging.getLogger(__name__)

# --- Static input metadata ---------------------------------------------------

DURATION_PRESETS: list[tuple[str, float]] = [
    ("30 d", 30.0),
    ("90 d", 90.0),
    ("180 d", 180.0),
    ("1 yr", 365.25),
    ("10 yr", 3652.5),
]

# Vancouver Island default view; covers the Cowichan Bay test point.
MAP_CENTER = [48.8, -123.5]
MAP_ZOOM = 7

# Sentinel value for the picker's "No mapped aquifer" option. Picked
# as a negative int so it can share a single-type RadioItems with real
# AQUIFER_IDs (which are always positive in BCGW). The Run Analysis
# packer translates this to ``source_aquifer_id=None`` on
# ``AnalysisInputs``; the rest of the pipeline keys off
# ``AnalysisInputs.is_manual_mode``.
MANUAL_AQUIFER_VALUE: int = -1

# Search radius (metres) for the nearby-aquifer fallback when no
# polygon directly contains the point. 1000 m balances catching wells
# that fall just outside a re-delineated boundary against returning
# polygons too distant to be the "correct" association. Changing this
# is a code release, not user-tunable.
NEARBY_AQUIFER_RADIUS_M: float = 1000.0

# Maximum nearby polygons surfaced in the picker. Keeps the radio
# list short when the search radius hits a busy area; the SQL ORDER
# BY DISTANCE_M guarantees these are the closest ones. Raised from 3
# to 5 at client request — parts of the Lower Mainland carry several
# small aquifers within the search radius and three options weren't
# enough to reach the right one.
MAX_NEARBY_AQUIFERS: int = 5


def _section_heading(icon_name: str, label: str) -> html.H3:
    """Render an icon + label as a section heading (h3).

    Uses the .bc-form-section__heading flex layout so the icon and
    text share a baseline.
    """
    return html.H3(
        [icon(icon_name, size=22), html.Span(label)],
        className="bc-form-section__heading",
    )


def _build_pumping_rate_options() -> list[dict[str, str]]:
    return [{"label": u.unit, "value": u.unit} for u in units.load_pumping_rate_units()]


def _default_pumping_rate_unit() -> str:
    return units.default_pumping_rate_unit().unit


# --- Layout ------------------------------------------------------------------


def layout(**_kwargs: object) -> html.Div:
    if not is_authenticated():
        return html.Div(
            dcc.Location(href="/login", id="setup-redirect-login", refresh=True)
        )

    return html.Div(
        [
            make_header(),
            html.Main(
                [
                    html.H1("Define analysis"),
                    # ----------------------------------------------------------
                    # Pumping point input
                    # ----------------------------------------------------------
                    html.Section(
                        [
                            _section_heading("location", "Pumping well location"),
                            html.Div(
                                dcc.RadioItems(
                                    id="setup-input-mode",
                                    options=[
                                        {"label": "Map click", "value": "map"},
                                        {"label": "Lat / Lon", "value": "latlon"},
                                        {"label": "Well tag number", "value": "wtn"},
                                    ],
                                    value="map",
                                    inline=True,
                                ),
                                className="bc-segmented",
                                style={"marginBottom": "0.75rem"},
                            ),
                            # Lat/Lon panel. Inputs are compact and
                            # fixed-width (12rem each); the action
                            # button sits on its own row below with
                            # margin so it reads as the explicit
                            # commit step, not as a third column.
                            html.Div(
                                [
                                    html.Div(
                                        [
                                            dcc.Input(
                                                id="setup-latlon-lon",
                                                type="number",
                                                placeholder="Longitude (e.g. -123.682)",
                                                step="any",
                                                className="bc-form-input",
                                                style={"width": "12rem"},
                                            ),
                                            dcc.Input(
                                                id="setup-latlon-lat",
                                                type="number",
                                                placeholder="Latitude (e.g. 48.759)",
                                                step="any",
                                                className="bc-form-input",
                                                style={"width": "12rem"},
                                            ),
                                        ],
                                        style={
                                            "display": "flex",
                                            "gap": "0.5rem",
                                            "flexWrap": "wrap",
                                            "marginBottom": "0.75rem",
                                        },
                                    ),
                                    html.Button(
                                        "Place",
                                        id="setup-latlon-submit",
                                        n_clicks=0,
                                        type="button",
                                        className="bc-btn bc-btn--secondary",
                                    ),
                                    # Inline validation next to the button —
                                    # same red format and placement as the
                                    # WTN lookup error, so a missing/partial
                                    # lat-lon entry is flagged right where the
                                    # user clicked rather than below the map.
                                    html.Span(
                                        id="setup-latlon-error",
                                        className="bc-form-error",
                                        style={"marginLeft": "0.75rem"},
                                    ),
                                ],
                                id="setup-latlon-panel",
                                style={"display": "none", "marginBottom": "0.75rem"},
                            ),
                            # WTN panel — same shape as Lat/Lon: a
                            # compact input above and the Look up
                            # button on its own row below.
                            html.Div(
                                [
                                    dcc.Input(
                                        id="setup-wtn-input",
                                        type="number",
                                        placeholder="WELL_TAG_NUMBER",
                                        className="bc-form-input",
                                        style={
                                            "width": "14rem",
                                            "marginBottom": "0.75rem",
                                            "display": "block",
                                        },
                                    ),
                                    html.Button(
                                        "Look up",
                                        id="setup-wtn-lookup",
                                        n_clicks=0,
                                        type="button",
                                        className="bc-btn bc-btn--secondary",
                                    ),
                                    html.Span(
                                        id="setup-wtn-error",
                                        className="bc-form-error",
                                        style={"marginLeft": "0.75rem"},
                                    ),
                                    # For officers who don't have the WTN to
                                    # hand: the GWELLS web map lets them find a
                                    # well's tag number by location. Opens in a
                                    # new tab so it doesn't disturb the in-
                                    # progress setup form.
                                    html.Div(
                                        [
                                            "Don't have the well tag number? "
                                            "Find it by location on the ",
                                            html.A(
                                                "BC Groundwater Wells and "
                                                "Aquifers map",
                                                href="https://apps.nrs.gov.bc.ca/gwells/",
                                                target="_blank",
                                                rel="noopener noreferrer",
                                            ),
                                            " (opens in a new tab).",
                                        ],
                                        className="bc-form-hint",
                                        style={"marginTop": "0.5rem"},
                                    ),
                                ],
                                id="setup-wtn-panel",
                                style={"display": "none", "marginBottom": "0.75rem"},
                            ),
                            # Map (always visible). The wrapper div
                            # carries the cursor-mode class. It's a
                            # plain div dash-leaflet never re-renders,
                            # so the class survives the Map's
                            # post-mount prop updates — a class set
                            # directly on the Leaflet container gets
                            # wiped when dash-leaflet pushes the
                            # initial viewport. The cursor CSS is a
                            # descendant selector, so it applies the
                            # moment the container mounts regardless
                            # of callback timing.
                            html.Div(
                                [
                                    dl.Map(
                                        id="setup-map",
                                        center=MAP_CENTER,
                                        zoom=MAP_ZOOM,
                                        # Grows with the viewport on larger
                                        # monitors but floors at the original
                                        # 380px so small laptops still fit the
                                        # aquifer picker below without scrolling.
                                        style={
                                            "height": "clamp(380px, 55vh, 680px)",
                                            "width": "100%",
                                            "borderRadius": "var(--bc-radius, 4px)",
                                        },
                                        children=[
                                            make_layers_control(
                                                mode="setup",
                                                control_id="setup-layers-control",
                                            ),
                                            dl.LayerGroup(
                                                id="setup-marker-layer", children=[]
                                            ),
                                            dl.LayerGroup(
                                                id="setup-map-labels", children=[]
                                            ),
                                        ],
                                    ),
                                    make_wms_legend(
                                        "setup-wms-legend", aquifers_on=True
                                    ),
                                ],
                                id="setup-map-wrap",
                                # Initial class matches the default
                                # input mode ("map") so the crosshair
                                # is correct on first paint without
                                # waiting for the cursor callback.
                                # `position: relative` anchors the
                                # absolutely-positioned legend panel.
                                className="gw-cursor-cross",
                                style={
                                    "position": "relative",
                                    "marginBottom": "0.5rem",
                                },
                            ),
                            html.Div(
                                id="setup-point-display",
                                className="bc-form-hint",
                            ),
                            html.Div(
                                id="setup-mode-error",
                                className="bc-form-error",
                            ),
                        ],
                        className="bc-form-section",
                    ),
                    # ----------------------------------------------------------
                    # Source aquifer + T/S
                    # ----------------------------------------------------------
                    html.Section(
                        [
                            _section_heading("layers", "Source aquifer"),
                            html.Div(
                                "Place a pumping point above to populate this section.",
                                id="setup-aquifer-help",
                                className="bc-form-section__hint",
                                style={"marginBottom": "1rem"},
                            ),
                            # Aquifer picker — vertical radio list. More
                            # vertical spacing per option (0.5rem) keeps
                            # the choices from feeling stacked.
                            html.Div(
                                dcc.RadioItems(
                                    id="setup-aquifer-picker",
                                    options=[],
                                    value=None,
                                    labelStyle={
                                        "display": "block",
                                        "marginBottom": "0.5rem",
                                    },
                                ),
                                className="bc-radio-group",
                                style={"marginBottom": "1rem"},
                            ),
                            # Manual-entry panel — shown only when the
                            # picker value is the manual sentinel. Carries
                            # the material dropdown and a hint that T/S
                            # below are mandatory. The dropdown's value
                            # is captured at Run Analysis time into
                            # ``AnalysisInputs.manual_material``.
                            html.Div(
                                [
                                    html.Div(
                                        [
                                            html.Label(
                                                "Aquifer material",
                                                className="bc-form-label",
                                            ),
                                            html.Div(
                                                dcc.Dropdown(
                                                    id="setup-manual-material",
                                                    options=[
                                                        {"label": m, "value": m}
                                                        for m in MANUAL_AQUIFER_MATERIALS
                                                    ],
                                                    value=None,
                                                    placeholder="Select material...",
                                                    clearable=False,
                                                ),
                                                className="bc-dropdown",
                                                style={"maxWidth": "20rem"},
                                            ),
                                        ],
                                        className="bc-form-field",
                                        style={"marginBottom": "0.75rem"},
                                    ),
                                    html.Div(
                                        "Enter the transmissivity (T) and storativity (S) "
                                        "values for this material in the fields below. "
                                        "Both are required.",
                                        className="bc-form-hint",
                                        style={"fontStyle": "italic"},
                                    ),
                                ],
                                id="setup-manual-panel",
                                style={
                                    "display": "none",
                                    "padding": "0.75rem",
                                    "backgroundColor": "rgba(204, 102, 0, 0.06)",
                                    "borderLeft": "3px solid #cc6600",
                                    "borderRadius": "var(--bc-radius)",
                                    "marginBottom": "1.25rem",
                                },
                            ),
                            # Subtype + default T/S values, shown as a
                            # soft tinted badge so it reads as a value
                            # display rather than crowding the radios.
                            html.Div(
                                id="setup-ts-default-display",
                                style={
                                    "padding": "0.5rem 0.75rem",
                                    "backgroundColor": "rgba(0, 51, 102, 0.04)",
                                    "borderLeft": "3px solid var(--bc-brand)",
                                    "borderRadius": "var(--bc-radius)",
                                    "fontSize": "0.9rem",
                                    "color": "var(--bc-text)",
                                    "marginBottom": "1.25rem",
                                    "minHeight": "0",
                                },
                            ),
                            # Override toggle — same iOS-style switch as
                            # the same-aquifer filter for visual
                            # consistency. Wrapped in its own Div so
                            # the toggle can be hidden cleanly in
                            # manual-entry mode (T/S editing is
                            # mandatory there, no "default" to
                            # override against).
                            html.Div(
                                dcc.Checklist(
                                    id="setup-ts-override-toggle",
                                    options=[
                                        {
                                            "label": "Override default T / S",
                                            "value": "override",
                                        }
                                    ],
                                    value=[],
                                ),
                                id="setup-ts-override-wrapper",
                                className="bc-toggle",
                                style={"marginBottom": "1rem"},
                            ),
                            html.Div(
                                [
                                    html.Div(
                                        [
                                            html.Label(
                                                "Transmissivity T (m²/day)",
                                                className="bc-form-label",
                                            ),
                                            dcc.Input(
                                                id="setup-ts-T",
                                                type="number",
                                                step="any",
                                                disabled=True,
                                                className="bc-form-input",
                                            ),
                                        ],
                                        className="bc-form-field",
                                    ),
                                    html.Div(
                                        [
                                            html.Label(
                                                "Storativity S (dimensionless)",
                                                className="bc-form-label",
                                            ),
                                            dcc.Input(
                                                id="setup-ts-S",
                                                type="number",
                                                step="any",
                                                disabled=True,
                                                className="bc-form-input",
                                            ),
                                        ],
                                        className="bc-form-field",
                                    ),
                                ],
                                className="bc-form-grid",
                            ),
                        ],
                        className="bc-form-section",
                    ),
                    # ----------------------------------------------------------
                    # Pumping rate, duration, buffer, filter
                    # ----------------------------------------------------------
                    html.Section(
                        [
                            _section_heading("sliders", "Pumping parameters"),
                            html.Div(
                                [
                                    # Q value + unit
                                    html.Div(
                                        [
                                            html.Label(
                                                "Pumping rate Q",
                                                className="bc-form-label",
                                            ),
                                            html.Div(
                                                [
                                                    dcc.Input(
                                                        id="setup-q-value",
                                                        type="number",
                                                        value=200,
                                                        step="any",
                                                        min=0,
                                                        className="bc-form-input",
                                                        style={"flex": "1 1 6rem"},
                                                    ),
                                                    html.Div(
                                                        dcc.Dropdown(
                                                            id="setup-q-unit",
                                                            options=_build_pumping_rate_options(),
                                                            value=_default_pumping_rate_unit(),
                                                            clearable=False,
                                                        ),
                                                        className="bc-dropdown",
                                                        style={
                                                            "flex": "1 1 7rem",
                                                            "minWidth": "7rem",
                                                        },
                                                    ),
                                                ],
                                                style={
                                                    "display": "flex",
                                                    "gap": "0.5rem",
                                                    "alignItems": "stretch",
                                                },
                                            ),
                                            html.Div(
                                                "Enter the proposed withdrawal "
                                                "rate and its units.",
                                                className="bc-form-hint",
                                                # One line — the field sits in a
                                                # narrow grid column with empty
                                                # space to its right, so the hint
                                                # extends there rather than wrapping.
                                                style={"whiteSpace": "nowrap"},
                                            ),
                                        ],
                                        className="bc-form-field",
                                    ),
                                    # Duration + presets
                                    html.Div(
                                        [
                                            html.Label(
                                                "Pumping duration (days)",
                                                className="bc-form-label",
                                            ),
                                            html.Div(
                                                [
                                                    dcc.Input(
                                                        id="setup-duration",
                                                        type="number",
                                                        value=config.DEFAULT_PUMPING_DURATION_DAYS,
                                                        min=0.001,
                                                        step="any",
                                                        className="bc-form-input",
                                                        style={
                                                            "flex": "0 0 7rem",
                                                            "marginRight": "0.5rem",
                                                        },
                                                    ),
                                                    *[
                                                        html.Button(
                                                            label,
                                                            id=f"setup-duration-preset-{int(days * 100)}",
                                                            n_clicks=0,
                                                            type="button",
                                                            className="bc-btn bc-btn--preset",
                                                        )
                                                        for label, days in DURATION_PRESETS
                                                    ],
                                                ],
                                                className="bc-btn-row",
                                            ),
                                            html.Div(
                                                "Enter the proposed duration or "
                                                "pick a preset.",
                                                className="bc-form-hint",
                                            ),
                                        ],
                                        className="bc-form-field bc-form-field--wide",
                                    ),
                                    # Buffer radius
                                    html.Div(
                                        [
                                            html.Label(
                                                "Buffer radius (m)",
                                                className="bc-form-label",
                                            ),
                                            dcc.Input(
                                                id="setup-radius",
                                                type="number",
                                                value=1000,
                                                min=1,
                                                step="any",
                                                className="bc-form-input",
                                            ),
                                            html.Div(
                                                "Wells within this distance of "
                                                "the pumping point are assessed.",
                                                className="bc-form-hint",
                                                # One line — see the pumping-rate
                                                # hint above; extends into the
                                                # empty grid space rather than
                                                # wrapping.
                                                style={"whiteSpace": "nowrap"},
                                            ),
                                        ],
                                        className="bc-form-field",
                                    ),
                                ],
                                className="bc-form-grid",
                                style={"marginBottom": "1rem"},
                            ),
                            # Same-aquifer filter — toggle switch. Default
                            # off (Q12 confirmed). The officer sees every
                            # well in the buffer first and opts in to the
                            # spatial filter when needed.
                            html.Div(
                                dcc.Checklist(
                                    id="setup-filter-toggle",
                                    options=[
                                        {
                                            "label": "Filter out wells spatially outside source aquifer",
                                            "value": "filter",
                                        }
                                    ],
                                    value=[],
                                ),
                                className="bc-toggle",
                            ),
                        ],
                        className="bc-form-section",
                    ),
                    # ----------------------------------------------------------
                    # Run analysis
                    # ----------------------------------------------------------
                    html.Div(
                        [
                            html.Button(
                                [icon("play", size=18, color="#FFFFFF"), "Run Analysis"],
                                id="setup-run",
                                n_clicks=0,
                                type="button",
                                # Starts disabled until a pumping point is
                                # placed (see `toggle_run_enabled`). Removes
                                # the "Place a pumping point first" dead-end
                                # a tester hit by clicking Run too early.
                                disabled=True,
                                className="bc-btn bc-btn--primary bc-btn--large",
                            ),
                            html.Button(
                                "Clear",
                                id="setup-clear",
                                n_clicks=0,
                                type="button",
                                title="Reset all inputs to start a new analysis",
                                className="bc-btn bc-btn--secondary",
                            ),
                            html.Div(
                                id="setup-run-error",
                                className="bc-form-error",
                                style={"margin": 0, "flex": "1 1 auto"},
                            ),
                        ],
                        className="bc-action-bar",
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
                ],
                className="bc-page__content bc-page__content--medium",
            ),
            make_footer(),
        ],
        className="bc-page",
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
    Output("setup-input-mode", "value", allow_duplicate=True),
    Output("setup-latlon-lon", "value", allow_duplicate=True),
    Output("setup-latlon-lat", "value", allow_duplicate=True),
    Output("setup-wtn-input", "value", allow_duplicate=True),
    Output("setup-q-value", "value", allow_duplicate=True),
    Output("setup-q-unit", "value", allow_duplicate=True),
    Output("setup-duration", "value", allow_duplicate=True),
    Output("setup-radius", "value", allow_duplicate=True),
    Output("setup-filter-toggle", "value", allow_duplicate=True),
    Output("setup-manual-material", "value", allow_duplicate=True),
    Output("setup-mode-error", "children", allow_duplicate=True),
    Output("setup-wtn-error", "children", allow_duplicate=True),
    Output("setup-latlon-error", "children", allow_duplicate=True),
    Output("setup-run-error", "children", allow_duplicate=True),
    Output("setup-restore-pending", "data", allow_duplicate=True),
    Input("setup-clear", "n_clicks"),
    prevent_initial_call=True,
)
def clear_form(_n_clicks: int) -> tuple[Any, ...]:
    """Reset every input to its default for a fresh analysis.

    Tester request: a "start over" control so the officer doesn't have
    to refresh the page. Clearing ``setup-point-store`` cascades to the
    aquifer picker, the T/S fields, the run-button enabled state, and
    the map marker, so those don't need to be reset directly here.
    ``analysis-inputs`` is left untouched so an open /results tab is not
    disturbed; ``setup-restore-pending`` is reset to False so the next
    point placement doesn't auto-restore the previously-run aquifer.
    """
    return (
        None,  # setup-point-store
        "map",  # setup-input-mode
        None,  # setup-latlon-lon
        None,  # setup-latlon-lat
        None,  # setup-wtn-input
        200,  # setup-q-value
        _default_pumping_rate_unit(),  # setup-q-unit
        config.DEFAULT_PUMPING_DURATION_DAYS,  # setup-duration
        1000,  # setup-radius
        [],  # setup-filter-toggle
        None,  # setup-manual-material
        "",  # setup-mode-error
        "",  # setup-wtn-error
        "",  # setup-latlon-error
        "",  # setup-run-error
        False,  # setup-restore-pending
    )


@callback(
    Output("setup-point-store", "data", allow_duplicate=True),
    Output("setup-mode-error", "children"),
    Output("setup-wtn-error", "children"),
    Output("setup-latlon-error", "children"),
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
) -> tuple[Any, str, str, str]:
    # Returns (point, mode_error, wtn_error, latlon_error). Each input
    # mode owns its own inline error slot so a message lands next to the
    # control the user just used, not below the map.
    triggered = ctx.triggered_id

    if triggered == "setup-map":
        if mode != "map" or not map_click_data:
            return no_update, "", "", ""
        latlng = map_click_data.get("latlng") or {}
        lat = latlng.get("lat")
        lon = latlng.get("lng")
        if lat is None or lon is None:
            return no_update, "", "", ""
        lat, lon = float(lat), float(lon)
        x, y = crs_utils.to_albers(lon, lat)
        return (
            {"lon": lon, "lat": lat, "x": x, "y": y, "mode": "map"},
            "",
            "",
            "",
        )

    if triggered == "setup-latlon-submit":
        if mode != "latlon":
            return no_update, "", "", "Switch input mode to 'Lat / Lon' first."
        if lon_in is None or lat_in is None:
            return no_update, "", "", "Enter both longitude and latitude."
        lon, lat = float(lon_in), float(lat_in)
        x, y = crs_utils.to_albers(lon, lat)
        return (
            {"lon": lon, "lat": lat, "x": x, "y": y, "mode": "latlon"},
            "",
            "",
            "",
        )

    if triggered == "setup-wtn-lookup":
        if mode != "wtn":
            return no_update, "", "Switch input mode to 'Well tag number' first.", ""
        if not wtn_in:
            return no_update, "", "Enter a well tag number.", ""
        try:
            with get_connection() as conn:
                row = q.well_by_tag(conn, int(wtn_in))
        except oracledb.DatabaseError as e:
            logger.warning("WTN lookup failed for %r: %s", wtn_in, e)
            return no_update, "", f"Lookup failed: {e}", ""
        if row is None:
            return no_update, "", f"WTN {int(wtn_in)} not found.", ""
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
            "",
        )

    return no_update, "", "", ""


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
    Output("setup-run", "disabled"),
    Output("setup-run-error", "children", allow_duplicate=True),
    Input("setup-point-store", "data"),
    prevent_initial_call="initial_duplicate",
)
def toggle_run_enabled(point: dict | None) -> tuple[bool, Any]:
    """Gate Run Analysis on a placed pumping point.

    The button starts disabled; placing a point by any input mode
    (map click, lat/lon, or WTN lookup) enables it and clears any
    stale "Place a pumping point first" error. Tester feedback: that
    error appeared after an early click and did not clear once a point
    was placed, so officers scrolled back up to re-check they'd set a
    point. Disabling the trigger removes the dead-end entirely.
    """
    if point:
        return False, ""
    return True, no_update


def _manual_option() -> dict[str, object]:
    """Picker option for the manual-entry fallback.

    Pinned at the bottom of the picker only when no aquifer directly
    contains the point — a point that overlaps a polygon is, by
    definition, in mapped territory. Selecting it puts the page into
    manual mode (material dropdown + mandatory T/S).
    """
    return {
        "label": "No mapped aquifer at this location — enter materials manually",
        "value": MANUAL_AQUIFER_VALUE,
    }


def _containing_option(aquifer: dict[str, object]) -> dict[str, object]:
    """Picker option for an aquifer whose polygon contains the point.

    Tagged "directly overlapping" — the neutral counterpart to the
    "nearby" tag — so the officer can tell at a glance which options
    are direct hits and which are fallback choices.
    """
    return {
        "label": (
            f"{aquifer['NAME']} (id {aquifer['AQUIFER_ID']}, "
            f"{aquifer['SUBTYPE']}) — directly overlapping"
        ),
        "value": int(aquifer["AQUIFER_ID"]),
    }


def _nearby_option(aquifer: dict[str, object]) -> dict[str, object]:
    """Picker option for a nearby (but not containing) aquifer.

    Carries the distance in the label so officers can see at a glance
    how far the polygon sits from the click point; tagged "(nearby —
    not directly overlapping)" so it's clear it isn't a direct hit.
    """
    dist_m = float(aquifer["DISTANCE_M"])
    return {
        "label": (
            f"{aquifer['NAME']} (id {aquifer['AQUIFER_ID']}, "
            f"{aquifer['SUBTYPE']}) — {dist_m:.0f} m away "
            "(nearby — not directly overlapping)"
        ),
        "value": int(aquifer["AQUIFER_ID"]),
    }


@callback(
    Output("setup-aquifer-picker", "options"),
    Output("setup-aquifer-picker", "value", allow_duplicate=True),
    Output("setup-aquifer-help", "children"),
    Input("setup-point-store", "data"),
    prevent_initial_call="initial_duplicate",
)
def fetch_aquifers(point: dict | None) -> tuple[list[dict], int | None, str]:
    """Populate the aquifer picker: containing + nearby + manual.

    Both spatial queries run on every point placement —
    ``aquifers_at_point`` for direct hits and ``aquifers_near_point``
    (``NEARBY_AQUIFER_RADIUS_M``) for nearby polygons — so the
    officer can pick a nearby aquifer even when the well directly
    overlaps a different one. This is the common stacked-polygon
    case: a well completed in unconsolidated material can sit inside
    the underlying bedrock polygon yet just outside the
    unconsolidated polygon it should be associated with.

    Picker contents:

    - Direct hits first, tagged "directly overlapping". A single
      direct hit is auto-selected; stacked polygons leave the pick
      to the officer.
    - Up to ``MAX_NEARBY_AQUIFERS`` nearby polygons below, tagged
      with distance. The nearby query also returns the containing
      polygons (distance 0), so those are de-duplicated out here.
    - The manual-entry sentinel, appended only when there are no
      direct hits.
    """
    if not point:
        return [], None, "Place a pumping point above to populate this section."
    try:
        with get_connection() as conn:
            containing = q.aquifers_at_point(
                conn, x_albers=point["x"], y_albers=point["y"]
            )
            nearby = q.aquifers_near_point(
                conn,
                x_albers=point["x"],
                y_albers=point["y"],
                radius_m=NEARBY_AQUIFER_RADIUS_M,
            )
    except oracledb.DatabaseError as e:
        logger.warning("aquifer query failed: %s", e)
        return [], None, f"Aquifer query failed: {e}"
    except Exception as e:
        logger.exception("Unexpected aquifer query error")
        return [], None, f"Unexpected error: {e}"

    # SDO_WITHIN_DISTANCE returns the containing polygons too (distance
    # 0); drop them so an aquifer can't appear as both a direct hit and
    # a nearby option.
    containing_ids = {int(a["AQUIFER_ID"]) for a in containing}
    nearby = [a for a in nearby if int(a["AQUIFER_ID"]) not in containing_ids]

    containing_options = [_containing_option(a) for a in containing]
    nearby_options = [_nearby_option(a) for a in nearby[:MAX_NEARBY_AQUIFERS]]

    if containing_options:
        options: list[dict[str, object]] = [*containing_options, *nearby_options]
        auto = point.get("auto_aquifer_id")
        if auto is not None and any(o["value"] == auto for o in options):
            value: int | None = auto
        elif len(containing_options) == 1:
            value = containing_options[0]["value"]
        else:
            value = None
        n_contain = len(containing_options)
        base = (
            "This point is inside one mapped aquifer."
            if n_contain == 1
            else f"This point is inside {n_contain} mapped aquifers."
        )
        if nearby_options:
            help_text = (
                base + f" Aquifers within {NEARBY_AQUIFER_RADIUS_M:.0f} m are "
                "also listed below — pick a nearby aquifer instead if it is "
                "the correct association."
            )
        else:
            help_text = base + " Pick the source aquifer below."
        return options, value, help_text

    # No aquifer contains the point — nearby + manual fallback.
    options = [*nearby_options, _manual_option()]
    if nearby_options:
        help_text = (
            "No aquifer directly contains this point. The closest "
            f"{len(nearby_options)} mapped aquifer"
            f"{'s are' if len(nearby_options) != 1 else ' is'} listed "
            "below as fallback choices; pick the best match, or choose "
            "manual entry if none apply."
        )
    else:
        help_text = (
            f"No mapped aquifers found within {NEARBY_AQUIFER_RADIUS_M:.0f} m "
            "of this point. Use manual entry to specify the material and "
            "supply T and S values."
        )
    return options, None, help_text


@callback(
    Output("setup-lookup-ts-store", "data"),
    Output("setup-ts-default-display", "children"),
    Output("setup-ts-override-toggle", "value"),
    Input("setup-aquifer-picker", "value"),
)
def fetch_ts_lookup(
    aquifer_id: int | None,
) -> tuple[dict | None, str, list[str]]:
    """Resolve T/S defaults for the picked aquifer.

    Three cases:

    - ``aquifer_id is None`` (no pick yet): clear everything.
    - ``aquifer_id == MANUAL_AQUIFER_VALUE`` (manual mode): no subtype
      lookup, no defaults — the manual-mode panel handles T/S entry.
      The lookup store is cleared so `toggle_override_inputs` doesn't
      try to populate the inputs with stale defaults from a previous
      picked aquifer.
    - Any positive AQUIFER_ID: normal subtype lookup against
      ``GW_AQUIFER_ATTRS`` and the ``ts_lookup`` CSV.
    """
    if aquifer_id is None:
        return None, "", []
    if aquifer_id == MANUAL_AQUIFER_VALUE:
        # Manual mode — clear the lookup store and the default badge;
        # the manual panel above the badge carries the explanatory
        # text instead. Override toggle reset to off so its callback
        # treatment is consistent (the wrapper is hidden anyway).
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
            f"Subtype {subtype}: default T = {format_float(props.T_m2_per_day)} "
            f"m²/day, S = {format_float(props.S)}"
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
    Input("setup-aquifer-picker", "value"),
)
def toggle_override_inputs(
    toggle: list[str],
    lookup: dict | None,
    aquifer_id: int | None,
) -> tuple[bool, bool, float | None, float | None]:
    """Manage T/S input editability and prefilled values.

    Three modes:

    - **Manual entry** (``aquifer_id == MANUAL_AQUIFER_VALUE``): both
      inputs are always enabled, with no default — the officer types
      values matching their chosen material.
    - **Override toggle ON** for a mapped aquifer: both inputs are
      enabled and pre-filled with the lookup defaults so the officer
      can adjust in place.
    - **Override toggle OFF** for a mapped aquifer: both inputs are
      disabled, showing the read-only defaults.

    Picking a different mapped aquifer resets the boxes to that
    aquifer's defaults. Switching from a mapped aquifer to manual
    entry clears the boxes (no defaults exist for manual mode).
    """
    if aquifer_id == MANUAL_AQUIFER_VALUE:
        return False, False, None, None
    enabled = "override" in (toggle or [])
    default_T = (lookup or {}).get("T")
    default_S = (lookup or {}).get("S")
    return (not enabled), (not enabled), default_T, default_S


@callback(
    Output("setup-filter-toggle", "options"),
    Output("setup-filter-toggle", "value", allow_duplicate=True),
    Input("setup-aquifer-picker", "value"),
    State("setup-filter-toggle", "value"),
    prevent_initial_call="initial_duplicate",
)
def disable_filter_in_manual_mode(
    aquifer_id: int | None,
    current_value: list[str] | None,
) -> tuple[list[dict], Any]:
    """Disable the same-aquifer spatial filter when manual mode is active.

    Manual mode has no aquifer polygon, so the spatial filter has
    nothing to test against. The option is greyed out and the label
    spells out why, so the officer doesn't try to tick it and wonder
    why nothing happens. Any prior tick is cleared so the stored
    inputs stay coherent (the Run Analysis packer also forces this
    off, but clearing the toggle keeps the UI honest).
    """
    if aquifer_id == MANUAL_AQUIFER_VALUE:
        options = [
            {
                "label": (
                    "Filter out wells spatially outside source aquifer "
                    "(not applicable in manual entry)"
                ),
                "value": "filter",
                "disabled": True,
            }
        ]
        return options, []
    options = [
        {
            "label": "Filter out wells spatially outside source aquifer",
            "value": "filter",
        }
    ]
    return options, current_value or []


@callback(
    Output("setup-manual-panel", "style"),
    Output("setup-ts-override-wrapper", "style"),
    Output("setup-ts-default-display", "style"),
    Input("setup-aquifer-picker", "value"),
    State("setup-manual-panel", "style"),
    State("setup-ts-override-wrapper", "style"),
    State("setup-ts-default-display", "style"),
)
def toggle_manual_panel_visibility(
    aquifer_id: int | None,
    manual_style: dict | None,
    override_style: dict | None,
    display_style: dict | None,
) -> tuple[dict, dict, dict]:
    """Show the manual panel — and hide the override toggle and default badge — when manual is picked.

    The three controls live in the same section and split into two
    visually exclusive groups: in manual mode the orange manual panel
    is shown and the blue default-T/S badge + override toggle are
    hidden; otherwise the badge + toggle are shown and the manual
    panel hides. Carries the existing style dict forward so we don't
    have to repeat the padding/colour rules in the callback.
    """
    is_manual = aquifer_id == MANUAL_AQUIFER_VALUE
    manual_next = {**(manual_style or {}), "display": "block" if is_manual else "none"}
    override_next = {
        **(override_style or {}),
        "display": "none" if is_manual else "block",
    }
    display_next = {
        **(display_style or {}),
        "display": "none" if is_manual else "block",
    }
    return manual_next, override_next, display_next


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
    State("setup-manual-material", "value"),
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
    manual_material: str | None,
    q_value: float | None,
    q_unit: str | None,
    duration_days: float | None,
    radius_m: float | None,
    filter_toggle: list[str],
    current_trigger: int | None,
) -> tuple[Any, Any, str]:
    """Validate and pack the setup form into ``analysis-inputs``.

    Two packing paths share the bulk of the validation:

    - **Mapped mode** (``aquifer_id`` is a positive AQUIFER_ID): T/S
      come from the lookup defaults unless the override toggle is on,
      in which case the inputs are taken from the editable fields.
      The picker label is copied into ``source_aquifer_name`` so the
      results summary reads naturally.
    - **Manual mode** (``aquifer_id == MANUAL_AQUIFER_VALUE``): a
      material must be picked, T/S are mandatory and read directly
      from the input fields (always editable in this mode), the
      stored ``source_aquifer_id`` is ``None`` (the
      ``AnalysisInputs.is_manual_mode`` flag), and
      ``source_aquifer_name`` is "Manual entry (material)".
    """
    if not point:
        return no_update, no_update, "Place a pumping point first."
    if aquifer_id is None:
        return no_update, no_update, "Pick a source aquifer."

    is_manual = aquifer_id == MANUAL_AQUIFER_VALUE
    if is_manual:
        if not manual_material:
            return no_update, no_update, "Pick an aquifer material for manual entry."
        if override_T is None or override_S is None:
            return no_update, no_update, (
                "Manual entry requires T and S values — fill in both fields above."
            )
        T_value, S_value = override_T, override_S
        ts_overridden = True
    else:
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
        ts_overridden = override_on
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

    if is_manual:
        aquifer_name = f"Manual entry ({manual_material})"
        stored_aquifer_id: int | None = None
        stored_subtype: str | None = None
        # In manual mode the spatial filter has no polygon to test
        # against; force it off in the stored inputs so the results
        # summary doesn't display a misleading "filter ON" indicator.
        same_aquifer_filter = False
    else:
        aquifer_name = next(
            (
                o["label"]
                for o in (aquifer_options or [])
                if o.get("value") == aquifer_id
            ),
            f"Aquifer {aquifer_id}",
        )
        stored_aquifer_id = int(aquifer_id)
        stored_subtype = (lookup or {}).get("subtype_code")
        same_aquifer_filter = "filter" in (filter_toggle or [])

    Q_m3_per_day = units.pumping_rate_to_m3_per_day(float(q_value), q_unit)

    inputs = {
        "pumping_lon": float(point["lon"]),
        "pumping_lat": float(point["lat"]),
        "pumping_x_albers": float(point["x"]),
        "pumping_y_albers": float(point["y"]),
        "source_aquifer_id": stored_aquifer_id,
        "source_aquifer_name": aquifer_name,
        "source_subtype_code": stored_subtype,
        "transmissivity_m2_per_day": float(T_value),
        "storativity": float(S_value),
        "ts_overridden": bool(ts_overridden),
        "Q_value": float(q_value),
        "Q_unit": q_unit,
        "Q_m3_per_day": float(Q_m3_per_day),
        "duration_days": float(duration_days),
        "buffer_radius_m": float(radius_m),
        "same_aquifer_filter": same_aquifer_filter,
        "u_threshold": config.COOPER_JACOB_U_THRESHOLD,
        "at_risk_fraction": config.AT_RISK_DRAWDOWN_FRACTION,
        "manual_material": manual_material if is_manual else None,
        # Present only when the point was located by WTN lookup; carried
        # for the usage log, not used by the pipeline.
        "pumping_well_tag_number": point.get("wtn"),
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


# --- Map cursor: crosshair in "Map click" mode, grab otherwise --------------
#
# A crosshair reads as "click to place a point"; the grab hand reads
# as "pan only". The class lives on the `#setup-map-wrap` div as a
# real Dash-managed `className` prop — its initial value is set in the
# layout (so the crosshair is right on first paint) and this callback
# updates it on every input-mode change. The CSS in assets/styles.css
# is a descendant selector reaching the Leaflet container and its
# interactive child layers, so the cursor is consistent everywhere on
# the map.

clientside_callback(
    """
    function(mode) {
        return mode === 'map' ? 'gw-cursor-cross' : 'gw-cursor-grab';
    }
    """,
    Output("setup-map-wrap", "className"),
    Input("setup-input-mode", "value"),
)


# --- Auto-zoom on lat/lon entry and WTN lookup ------------------------------
#
# Map-click mode doesn't need this — the user is already looking at the
# place they clicked. Lat/lon and WTN entry, on the other hand, are
# "navigate me there" gestures; the marker is dropped but the map view
# stays put unless we move it. Zoom level 14 frames the point in its
# immediate-neighbourhood context (a city block or two), which matches
# what the officer typically wants to see next.


@callback(
    Output("setup-map", "viewport"),
    Input("setup-point-store", "data"),
    prevent_initial_call=True,
)
def zoom_to_point(point: dict | None) -> dict[str, Any] | str:
    if not point:
        return no_update
    if point.get("mode") not in ("latlon", "wtn"):
        return no_update
    return {
        "center": [point["lat"], point["lon"]],
        "zoom": 14,
        "transition": "flyTo",
    }


# --- Dynamic water management boundary labels --------------------------------
#
# Fires on map moveend (`bounds`) and on overlay toggles (`overlays`).
# `build_boundary_label_markers` clips each WMD/WMP polygon to the
# current viewport and anchors a name label at the visible centre, so
# a label stays on screen while the officer pans within one polygon.
# Labels appear only for overlays that are toggled on.


@callback(
    Output("setup-map-labels", "children"),
    Input("setup-map", "bounds"),
    Input("setup-layers-control", "overlays"),
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
# Shows a GetLegendGraphic swatch for each WMS overlay (aquifers,
# wells) that is currently toggled on. Fires on overlay toggles.


@callback(
    Output("setup-wms-legend", "children"),
    Input("setup-layers-control", "overlays"),
)
def update_wms_legend(overlays: list[str] | None) -> list[Any]:
    return wms_legend_children(overlays, include_wells=True)


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
    Output("setup-filter-toggle", "value", allow_duplicate=True),
    Output("setup-manual-material", "value"),
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

    ``manual_material`` is replayed for continuity when the officer
    bounces between /setup and /results on a manual-mode run; the
    field stays hidden in mapped mode so a stale value doesn't
    surface unless they explicitly re-pick manual.
    """
    if not inputs_data:
        return tuple(no_update for _ in range(10))
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
        inputs_data.get("manual_material"),
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

    Manual-mode replay: ``source_aquifer_id is None`` on the saved
    inputs means the prior run was manual. We restore to the manual
    sentinel as long as it appears in the current picker options
    (it only appears when the new point also has no containing
    aquifer); otherwise auto-pick from `fetch_aquifers` runs.
    """
    if not pending:
        return no_update, no_update
    if not inputs_data or not options:
        return no_update, False
    saved_id = inputs_data.get("source_aquifer_id")
    if saved_id is None:
        if any(o.get("value") == MANUAL_AQUIFER_VALUE for o in options):
            return MANUAL_AQUIFER_VALUE, False
        return no_update, False
    if any(o.get("value") == saved_id for o in options):
        return saved_id, False
    return no_update, False
