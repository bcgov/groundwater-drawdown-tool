"""Inline-SVG icons used in section headings and buttons.

Each icon is a stroked outline drawn at 24x24 (viewBox), then sized
by the consumer via CSS / inline style. ``currentColor`` on the
stroke means the icon picks up its parent's text colour — section
headings styled in BC navy get navy icons automatically.

Kept as inline ``html.Img`` data URIs rather than served files so
the tool ships without binary assets and so the auto-updater doesn't
have to copy a separate ``icons/`` directory.
"""

from __future__ import annotations

import urllib.parse

from dash import html

# Default icon colour — matches the BC navy used in section headings,
# so an iconified heading reads as one cohesive ink-on-paper unit.
_DEFAULT_COLOR = "#003366"

# Each path is a stroke-only ("fill: none") SVG body. The viewBox is
# 0 0 24 24 — standard for icon libraries like Feather / Lucide which
# inspired the shapes here.
#
# The body uses the literal token ``__STROKE__`` for stroke and
# ``__FILL__`` for fill; ``icon()`` substitutes them with the actual
# colour. We can't use ``currentColor`` because the data-URI ``<img>``
# rendering context doesn't inherit ``color`` from its CSS parent
# — the stroke would render black regardless of the parent's text
# colour. Hardcoding the colour avoids that trap.
_ICONS: dict[str, str] = {
    # Map pin — pumping well location.
    "location": (
        '<path d="M12 22s-7-7.5-7-13a7 7 0 1 1 14 0c0 5.5-7 13-7 13z"/>'
        '<circle cx="12" cy="9" r="2.5"/>'
    ),
    # Stacked horizontal layers — aquifer (geology).
    "layers": (
        '<path d="M12 3 2 8l10 5 10-5-10-5z"/>'
        '<path d="M2 13l10 5 10-5"/>'
        '<path d="M2 18l10 5 10-5"/>'
    ),
    # Sliders / settings — pumping parameters.
    "sliders": (
        '<line x1="4" y1="7" x2="20" y2="7"/>'
        '<line x1="4" y1="12" x2="20" y2="12"/>'
        '<line x1="4" y1="17" x2="20" y2="17"/>'
        '<circle cx="9" cy="7" r="2.2" fill="__STROKE__" stroke="none"/>'
        '<circle cx="15" cy="12" r="2.2" fill="__STROKE__" stroke="none"/>'
        '<circle cx="7" cy="17" r="2.2" fill="__STROKE__" stroke="none"/>'
    ),
    # Play / triangle — primary action (Run analysis).
    "play": (
        '<polygon points="6,4 20,12 6,20" fill="__STROKE__" stroke="none"/>'
    ),
}


def icon(
    name: str,
    *,
    size: int = 22,
    color: str = _DEFAULT_COLOR,
    className: str = "",
) -> html.Img:
    """Return an inline-SVG icon as a Dash ``html.Img`` data-URI.

    Args:
        name: One of the keys in `_ICONS`. KeyError if unknown.
        size: Square pixel size for the rendered icon (sets both
            width and height on the ``<img>``).
        color: Hex / CSS colour string for the stroke (and any
            stroke-none fills inside the icon body). Defaults to BC
            navy so headings read as one unit.
        className: Optional CSS class hook; defaults to none.
    """
    body = _ICONS[name].replace("__STROKE__", color)
    svg = (
        '<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 24 24" '
        f'fill="none" stroke="{color}" stroke-width="2" '
        'stroke-linecap="round" stroke-linejoin="round">'
        f"{body}</svg>"
    )
    return html.Img(
        src=f"data:image/svg+xml;utf8,{urllib.parse.quote(svg)}",
        className=className,
        style={
            "width": f"{size}px",
            "height": f"{size}px",
            "display": "inline-block",
            "verticalAlign": "middle",
        },
        alt="",
    )
