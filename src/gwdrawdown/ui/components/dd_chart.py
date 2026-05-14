"""Distance-drawdown chart for the results page.

Implements the legacy Excel `InputValues` chart described in
`references/excel_chart_layout.md` (also deck slide 21). Three Plotly
scatter traces, inverted Y axis, log-spaced X sampling for the
Cooper-Jacob curve:

1. **SAD bars (orange)** — one vertical segment per well from its
   drawdown point down to its SAD value. Drawn first so the wells
   and curve render on top.
2. **Drawdown curve (black)** — Cooper-Jacob evaluated at ~40
   log-spaced X values from 0.1 m to 1.1x max well distance, using
   the same `core.drawdown.cooper_jacob` kernel as the per-well
   pipeline. ``u_threshold=inf`` so the curve plots across the whole
   distance range regardless of the small-``u`` advisory (the
   validity-flag visual lives on the per-well table tint).
3. **Wells (red dots, WTN labels)** — one marker per observation
   well; pumping well rendered as a distinct triangle at the
   ``r=0.1 m`` fallback location. Marker ``customdata`` carries the
   integer WTN so the results-page callback can map a chart click
   back to a well for cross-linking with the map.

The result page also injects a translucent ring around the
``selected_wtn`` so the user can see which well the chart and map
are agreeing on at any moment.
"""

from __future__ import annotations

import math
from typing import Any

import plotly.graph_objects as go

from gwdrawdown.analysis import AnalysisResult, WellResult
from gwdrawdown.core.drawdown import PumpingSource, cooper_jacob
from gwdrawdown.ui.components.palette import (
    PUMPING_COLOR as _PUMPING_COLOR,
)
from gwdrawdown.ui.components.palette import (
    SELECTION_COLOR as _SELECTED_RING_COLOR,
)
from gwdrawdown.ui.components.palette import (
    STATUS_COLOR,
)

# Curve and SAD-bar colours match the legacy Excel chart from deck
# slide 21. The well markers themselves are coloured per-point from
# the shared status palette so the chart, the per-well table cells,
# and the map markers all read consistently.
_CURVE_COLOR = "#000000"
_SAD_COLOR = "#FFA500"
_DEFAULT_WELL_COLOR = "#616161"

# r → 0 fallback used in core.drawdown — the pumping well is plotted
# at this distance rather than at exactly 0 m so it appears on the
# chart (and the log-spaced curve sampling can include it).
_PUMP_R_M = 0.1

# Number of points used to draw the smooth Cooper-Jacob curve.
# Matches the legacy Excel (`Lookup_DB!N4:N43` is 40 rows).
_CURVE_SAMPLE_COUNT = 40


def _logspace(x_min: float, x_max: float, n: int) -> list[float]:
    """Pure-Python log-spaced range; avoids a NumPy import here.

    NumPy is already a transitive dep via pandas / plotly, but the
    chart needs only ~40 points and a tiny loop is clearer than
    pulling NumPy in.
    """
    if n < 2:
        return [x_min]
    lo = math.log10(x_min)
    hi = math.log10(x_max)
    step = (hi - lo) / (n - 1)
    return [10.0 ** (lo + i * step) for i in range(n)]


def _sample_curve(
    result: AnalysisResult,
    xs: list[float],
) -> list[float]:
    """Evaluate Cooper-Jacob drawdown at each x for plotting the curve.

    Uses ``u_threshold=inf`` so the helper always returns a number;
    the per-row "outside validity" visual is the per-well table tint,
    not a gap in the curve.
    """
    inputs = result.inputs
    ys: list[float] = []
    for r in xs:
        res = cooper_jacob(
            [
                PumpingSource(
                    Q_m3_per_day=inputs.Q_m3_per_day,
                    T_m2_per_day=inputs.transmissivity_m2_per_day,
                    S=inputs.storativity,
                    r_m=r,
                )
            ],
            t_days=inputs.duration_days,
            u_threshold=float("inf"),
        )
        ys.append(res.drawdown_m)
    return ys


def _sad_segment_arrays(wells: list[WellResult]) -> tuple[list[Any], list[Any]]:
    """Build the X/Y arrays for the SAD vertical-bar trace.

    Each well contributes two points (top and bottom of its bar)
    separated from the next well by a ``None`` sentinel, which
    Plotly renders as a gap. Wells without a valid positive SAD
    are skipped — there's no headroom bar to draw.
    """
    xs: list[Any] = []
    ys: list[Any] = []
    for w in wells:
        if w.sad_m is None or w.sad_m <= 0:
            continue
        xs.extend([w.distance_m, w.distance_m, None])
        ys.extend([w.drawdown_m, w.sad_m, None])
    return xs, ys


def _empty_figure(message: str) -> go.Figure:
    """Tiny placeholder figure used when there's nothing to plot."""
    fig = go.Figure()
    fig.add_annotation(
        text=message,
        xref="paper",
        yref="paper",
        x=0.5,
        y=0.5,
        showarrow=False,
        font={"color": "#777", "size": 14},
    )
    fig.update_layout(
        xaxis={"visible": False},
        yaxis={"visible": False},
        height=320,
        margin={"l": 20, "r": 20, "t": 30, "b": 20},
    )
    return fig


def make_distance_drawdown_figure(
    result: AnalysisResult,
    *,
    selected_wtn: int | None = None,
) -> go.Figure:
    """Build the distance-drawdown Plotly figure for `result`.

    Args:
        result: The (override-applied) `AnalysisResult` driving the page.
        selected_wtn: Well tag number of the currently-selected well, if
            any. Drawn as a translucent ring around the well point so
            the map and chart visually agree.

    Returns:
        A `plotly.graph_objects.Figure`. The caller wraps it in a
        `dcc.Graph` (the page does this once at mount; the render
        callback only updates the figure prop).
    """
    wells = result.wells
    if not wells:
        return _empty_figure("No wells to plot.")

    # X axis range: log-spaced from the r→0 fallback out to ~110% of
    # the furthest observation well (legacy Excel's MAX*1.1). Cap the
    # max at a small floor so a single-close-well case still renders.
    max_dist = max(w.distance_m for w in wells)
    x_max = max(max_dist * 1.1, _PUMP_R_M * 100.0)
    curve_x = _logspace(_PUMP_R_M, x_max, _CURVE_SAMPLE_COUNT)
    curve_y = _sample_curve(result, curve_x)

    fig = go.Figure()

    # Trace order matters for both visual stacking AND Plotly click
    # routing — clicks land on the topmost trace at the cursor.
    # Wells go LAST (well markers must capture clicks for chart→map
    # cross-linking) except for the pumping triangle which sits on
    # top so it's visible at r=0.1. Selection ring goes BEFORE wells
    # so its 24-px radius doesn't intercept clicks meant for the
    # 10-px well marker beneath it.

    # 1. SAD vertical bars.
    sad_x, sad_y = _sad_segment_arrays(wells)
    if sad_x:
        fig.add_trace(
            go.Scatter(
                x=sad_x,
                y=sad_y,
                mode="lines",
                line={"color": _SAD_COLOR, "width": 4},
                name="SAD",
                hoverinfo="skip",
            )
        )

    # 2. Cooper-Jacob curve.
    fig.add_trace(
        go.Scatter(
            x=curve_x,
            y=curve_y,
            mode="lines",
            line={"color": _CURVE_COLOR, "width": 2},
            name="Drawdown Curve",
            hoverinfo="skip",
        )
    )

    # 3. Selection ring (drawn before Wells so the well marker stays
    # on top for click handling).
    if selected_wtn is not None:
        for w in wells:
            if w.well_tag_number == selected_wtn:
                fig.add_trace(
                    go.Scatter(
                        x=[w.distance_m],
                        y=[w.drawdown_m],
                        mode="markers",
                        marker={
                            "color": "rgba(0,0,0,0)",
                            "size": 24,
                            "line": {"color": _SELECTED_RING_COLOR, "width": 3},
                        },
                        name="Selected",
                        showlegend=False,
                        hoverinfo="skip",
                    )
                )
                break

    # 4. Well points with WTN labels.
    well_xs = [w.distance_m for w in wells]
    well_ys = [w.drawdown_m for w in wells]
    well_text = [str(w.well_tag_number) for w in wells]
    customdata = [w.well_tag_number for w in wells]
    well_hover = [
        (
            f"WTN {w.well_tag_number}<br>"
            f"r = {w.distance_m:.1f} m<br>"
            f"s = {w.drawdown_m:.3f} m<br>"
            f"SAD = {(f'{w.sad_m:.3f} m' if w.sad_m is not None else '—')}<br>"
            f"Status: {w.well_status.value}"
        )
        for w in wells
    ]
    # Per-point fill colours from the shared status palette so the
    # chart matches the per-well table status cells and the map
    # markers at a glance (red AT_RISK / green OK / grey
    # INSUFFICIENT_DATA / orange SUSPECT_DATA / purple
    # OUTSIDE_VALIDITY). A white marker outline keeps the dots
    # readable when they sit close to the Cooper-Jacob curve.
    well_colors = [
        STATUS_COLOR.get(w.well_status, _DEFAULT_WELL_COLOR) for w in wells
    ]
    fig.add_trace(
        go.Scatter(
            x=well_xs,
            y=well_ys,
            mode="markers+text",
            marker={
                "color": well_colors,
                "size": 11,
                "line": {"color": "white", "width": 1},
            },
            text=well_text,
            textposition="top center",
            textfont={"size": 10},
            name="Wells",
            customdata=customdata,
            hovertext=well_hover,
            hoverinfo="text",
        )
    )

    # 5. Pumping well at r=0.1 — distinct symbol so users see it but
    # don't confuse it with an observation.
    pump_y = _sample_curve(result, [_PUMP_R_M])[0]
    fig.add_trace(
        go.Scatter(
            x=[_PUMP_R_M],
            y=[pump_y],
            mode="markers",
            marker={
                "color": _PUMPING_COLOR,
                "size": 14,
                "symbol": "triangle-up",
                "line": {"color": "white", "width": 1},
            },
            name="Pumping well",
            hovertemplate=(
                "Pumping well<br>r = 0.1 m<br>s = %{y:.3f} m<extra></extra>"
            ),
        )
    )

    fig.update_layout(
        title={"text": "Distance-Drawdown", "x": 0.5, "xanchor": "center"},
        # Linear X-axis to match the legacy Excel chart (deck slide
        # 21). The curve is sampled on a log-spaced X grid so the
        # near-pumping shape is rendered smoothly even on a linear
        # axis; with a log axis the Cooper-Jacob curve degenerates
        # visually to a straight line (s is linear in log r) and
        # doesn't match what Water Officers expect to see.
        #
        # Explicit range with a small negative left margin so the
        # pumping triangle at r=0.1 m isn't clipped against the
        # y-axis (rangemode="tozero" snapped the axis to start
        # exactly at 0 and cut the marker in half).
        xaxis={
            "title": "Distance [m]",
            "type": "linear",
            "range": [-x_max * 0.025, x_max],
            "showgrid": True,
            "gridcolor": "#eee",
        },
        # Inverted Y axis is the hydrogeology convention — water
        # level drops, so the curve drops. Officers read this chart
        # routinely; flipping the Y to grow upward would be a
        # usability mistake (see references/excel_chart_layout.md).
        yaxis={
            "title": "Drawdown Impact [m]",
            "autorange": "reversed",
            "showgrid": True,
            "gridcolor": "#eee",
        },
        legend={
            "orientation": "h",
            "yanchor": "bottom",
            "y": -0.22,
            "xanchor": "center",
            "x": 0.5,
        },
        margin={"l": 60, "r": 30, "t": 50, "b": 70},
        height=480,
        plot_bgcolor="white",
        paper_bgcolor="white",
    )
    return fig
