"""Distance-drawdown chart for the results page.

Implements the legacy Excel `InputValues` chart described in
`references/excel_chart_layout.md` (also deck slide 21). Three Plotly
scatter traces, inverted Y axis, log-spaced X sampling for the
Cooper-Jacob curve:

1. **SAD bars** — one vertical segment per well spanning from its
   predicted drawdown to its SAD value. Drawn first so the wells and
   curve render on top. Split across two traces by direction:

   - **orange** where SAD is deeper than the predicted drawdown, so
     the bar hangs *below* the well point. This is the usual case and
     the bar reads as remaining headroom.
   - **red** where the predicted drawdown meets or exceeds SAD, so the
     bar runs *upward* from the well point. Geometrically the same
     segment, but the reading inverts — a tester reasonably read a
     screen full of upward bars as a rendering fault rather than as
     "every one of these wells is over-impacted" (client feedback,
     2026-07). Colouring the exceedance case makes the flip read as a
     warning instead of a glitch.
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
from gwdrawdown.core.flagging import WellStatus
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
# Exceedance bars (drawdown >= SAD) reuse the shared AT_RISK red, so a
# red bar on the chart and a red status cell in the table are saying
# the same thing in the same colour.
_SAD_EXCEEDED_COLOR = STATUS_COLOR[WellStatus.AT_RISK]
_DEFAULT_WELL_COLOR = "#616161"

# Reference line at zero drawdown — the pre-pumping water level, which
# every SAD bar and well point is measured down from. Without it the
# chart has no visual datum (client feedback, 2026-07); the y-range
# below is forced to include 0 so the line always has somewhere to sit.
#
# Slate blue-grey, dashed, 2 px. The first attempt (1.5 px dotted
# #9e9e9e) was in the figure but effectively invisible on screen: a
# y-axis gridline is drawn at 0 as well, so a faint grey dotted line
# landed straight on top of it and read as part of the grid. This has
# to be distinguishable from both the #eee gridlines and the black
# Cooper-Jacob curve.
_ZERO_LINE_COLOR = "#546e7a"

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


def _sad_segment_arrays(
    wells: list[WellResult],
    *,
    exceeded: bool,
) -> tuple[list[Any], list[Any]]:
    """Build the X/Y arrays for one of the two SAD vertical-bar traces.

    Each well contributes two points (the ends of its bar) separated
    from the next well by a ``None`` sentinel, which Plotly renders as
    a gap. Wells without a valid positive SAD are skipped — there is no
    bar to draw.

    Args:
        wells: The wells to consider.
        exceeded: When ``True``, return only wells whose predicted
            drawdown meets or exceeds SAD (bar runs upward from the
            well point — the over-impacted case, drawn red). When
            ``False``, return only wells with headroom remaining (bar
            hangs below the well point, drawn orange).

    Returns:
        ``(xs, ys)`` ready to hand to a ``mode="lines"`` scatter.
    """
    xs: list[Any] = []
    ys: list[Any] = []
    for w in wells:
        if w.sad_m is None or w.sad_m <= 0:
            continue
        # Y grows downward on this chart, so "drawdown deeper than SAD"
        # is drawdown_m >= sad_m.
        if (w.drawdown_m >= w.sad_m) != exceeded:
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

    # 1. SAD vertical bars, split by direction so the over-impacted
    # case is visually distinct from the ordinary headroom case.
    for exceeded, colour, label in (
        (False, _SAD_COLOR, "SAD (headroom remaining)"),
        (True, _SAD_EXCEEDED_COLOR, "Drawdown exceeds SAD"),
    ):
        sad_x, sad_y = _sad_segment_arrays(wells, exceeded=exceeded)
        if not sad_x:
            continue
        fig.add_trace(
            go.Scatter(
                x=sad_x,
                y=sad_y,
                mode="lines",
                line={"color": colour, "width": 4},
                name=label,
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

    # Explicit reversed Y range (large drawdown at the bottom — the
    # hydrogeology convention). Set explicitly rather than via
    # autorange="reversed" so the modebar "Reset axes" deterministically
    # restores the inverted view. Paired with removing the "Autoscale"
    # button on the results page, this closes a Plotly quirk a tester hit
    # where autoscaling a zoomed chart flipped the axis upright and would
    # not recover.
    # Zero is forced into the range so the 0 m reference line always has
    # somewhere to sit: every plotted drawdown is positive, so a range
    # derived purely from the data would leave `add_hline(y=0)` outside
    # the visible area and silently draw nothing.
    y_values = list(curve_y) + list(well_ys) + [pump_y, 0.0]
    y_values += [w.sad_m for w in wells if w.sad_m is not None and w.sad_m > 0]
    y_lo = min(y_values)
    y_hi = max(y_values)
    span = y_hi - y_lo
    base_pad = span * 0.05 if span > 0 else max(abs(y_hi), 1.0) * 0.05
    # Asymmetric padding: WTN labels are drawn above their marker
    # ("top center"), so the top of the chart — the small-drawdown
    # end — needs roughly triple the headroom or labels on the
    # shallowest wells get clipped against the plot edge (client
    # feedback, 2026-07).
    y_range = [y_hi + base_pad, y_lo - base_pad * 3.0]

    fig.update_layout(
        title={
            "text": "Distance-Drawdown",
            "x": 0.5,
            "xanchor": "center",
            "font": {"size": 13},
        },
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
        # The right-hand margin is widened from the old flush `x_max`:
        # the furthest well sits at ~0.91 * x_max and its WTN label is
        # centred on the marker, so a 5-digit tag could overhang the
        # plot edge and get clipped (client feedback, 2026-07).
        xaxis={
            "title": "Distance [m]",
            "type": "linear",
            "range": [-x_max * 0.03, x_max * 1.04],
            "showgrid": True,
            "gridcolor": "#eee",
        },
        # Inverted Y axis is the hydrogeology convention — water
        # level drops, so the curve drops. Officers read this chart
        # routinely; flipping the Y to grow upward would be a
        # usability mistake (see references/excel_chart_layout.md).
        yaxis={
            "title": "Drawdown Impact [m]",
            "range": y_range,
            "autorange": False,
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

    # Zero-drawdown datum, requested by the client. Added after
    # `update_layout` so it is drawn against the final axis range.
    # `layer="below"` keeps it behind the curve, the SAD bars, and the
    # well markers — it is a reference, not data.
    #
    # Deliberately unlabelled: the Y axis already carries a "0" tick
    # directly beside it, so an annotation here is duplicate ink.
    fig.add_hline(
        y=0.0,
        line={"color": _ZERO_LINE_COLOR, "width": 2, "dash": "dash"},
        layer="below",
    )
    return fig
