"""Altair chart builders and themes.

Design rules applied here (from the dataviz guidance):

* One hue. The whole system is navy monochromatic, so series separate by
  lightness and never by colour. A six-slot categorical ramp still reads as one
  family, and nothing depends on colour vision to be legible.
* No gridlines on the category axis; a single hairline grid on the value axis.
* No chart titles. The card header already names it.
* Bars capped at 20px with a rounded data end; values direct-labelled, after
  which the value axis is dropped entirely (direct labels beat gridlines).
* One series gets no legend; the card title identifies it.
* Never a dual axis. Two measures means two cards.
* Funnel is not a native Vega-Lite mark, so it is a horizontal bar on the
  ordinal ramp, which is also more honest since funnels distort area.

``theme=None`` is passed on every ``st.altair_chart`` call so our registered
theme is the single source of truth rather than being merged with Streamlit's.
"""

from __future__ import annotations

from typing import Any, Dict, List, Optional

import altair as alt
import pandas as pd

from intellia.theme import tokens
from intellia.utils.formatting import by_unit, humanize_column

FONT = "Inter, system-ui, sans-serif"
HEIGHT = 224

_REGISTERED = False


def _theme(dark: bool) -> Dict[str, Any]:
    palette = tokens.DARK if dark else tokens.LIGHT
    series = tokens.CATEGORICAL_DARK if dark else tokens.CATEGORICAL_LIGHT
    ordinal = tokens.SEQUENTIAL_DARK if dark else tokens.SEQUENTIAL_LIGHT
    grid = palette["border"]

    return {
        "config": {
            "background": "transparent",
            "font": FONT,
            "view": {"stroke": "transparent", "continuousHeight": HEIGHT},
            "padding": {"left": 0, "top": 4, "right": 4, "bottom": 0},
            "axis": {
                "domainColor": grid,
                "tickColor": grid,
                "ticks": False,
                "grid": False,
                "labelColor": palette["text-muted"],
                "labelFontSize": 10.5,
                "labelPadding": 7,
                "titleColor": palette["text-faint"],
                "titleFontSize": 10.5,
                "titleFontWeight": 500,
                "title": None,
            },
            "axisY": {"grid": True, "gridColor": grid, "gridDash": [],
                      "domain": False, "labelLimit": 170},
            "axisX": {"grid": False, "domain": True},
            "bar": {"cornerRadiusEnd": 3, "size": 20},
            "line": {"strokeWidth": 2, "strokeCap": "round", "strokeJoin": "round"},
            "point": {"filled": True, "size": 60},
            "area": {"fillOpacity": 0.12, "line": {"strokeWidth": 2}},
            "arc": {"stroke": palette["surface"], "strokeWidth": 2},
            "text": {"font": FONT, "fontSize": 10.5, "fill": palette["text-secondary"]},
            "legend": {
                "orient": "top", "direction": "horizontal", "title": None,
                "labelFontSize": 10.5, "symbolType": "circle", "symbolSize": 60,
                "offset": 2, "labelColor": palette["text-secondary"],
            },
            "range": {"category": series, "ordinal": ordinal, "ramp": ordinal},
        }
    }


def register_themes() -> None:
    global _REGISTERED
    if _REGISTERED:
        return
    try:
        @alt.theme.register("intellia_light", enable=True)
        def _light() -> Any:
            return alt.theme.ThemeConfig(_theme(False))

        @alt.theme.register("intellia_dark", enable=False)
        def _dark() -> Any:
            return alt.theme.ThemeConfig(_theme(True))

        _REGISTERED = True
    except Exception:  # pragma: no cover - older altair
        _REGISTERED = True


def use_theme(dark: bool) -> None:
    try:
        alt.theme.enable("intellia_dark" if dark else "intellia_light")
    except Exception:  # pragma: no cover
        pass


# -- helpers ---------------------------------------------------------------------------

def _fmt(unit: str) -> str:
    return {"$": "$,.0f", "%": ".1f", "x": ".2f"}.get(unit, ",.0f")


def _label_expr(unit: str) -> str:
    if unit == "$":
        return ("datum.value >= 1000000 ? '$' + format(datum.value/1000000, '.1f') + 'M'"
                " : datum.value >= 1000 ? '$' + format(datum.value/1000, ',.0f') + 'K'"
                " : '$' + format(datum.value, ',.0f')")
    if unit == "%":
        return "format(datum.value, '.0f') + '%'"
    if unit == "x":
        return "format(datum.value, '.1f') + 'x'"
    return "format(datum.value, ',.0f')"


def _palette(dark: bool) -> List[str]:
    return tokens.CATEGORICAL_DARK if dark else tokens.CATEGORICAL_LIGHT


def _accent(dark: bool) -> str:
    return _palette(dark)[0]


def _muted(dark: bool) -> str:
    """The fill for everything below the leader in a ranked bar chart."""
    return _palette(dark)[3]


def _text(dark: bool, slot: str = "text-secondary") -> str:
    return (tokens.DARK if dark else tokens.LIGHT)[slot]


def _headroom(top: Any, fraction: float) -> Any:
    """A value scale with room for a direct label past the longest mark."""
    try:
        limit = float(top)
    except (TypeError, ValueError):
        return alt.Undefined
    if limit <= 0:
        return alt.Undefined
    return alt.Scale(domain=[0, limit * (1 + fraction)], nice=False)


def _tooltip(dim: str, measure: str, unit: str) -> List[Any]:
    return [
        alt.Tooltip("{}:N".format(dim), title=humanize_column(dim)),
        alt.Tooltip("{}:Q".format(measure), title=humanize_column(measure),
                    format=_fmt(unit)),
    ]


# -- builders --------------------------------------------------------------------------

def hbar(frame: pd.DataFrame, dimension: str, measure: str, unit: str = "#",
         dark: bool = False, limit: int = 12) -> alt.Chart:
    """Horizontal bars: the default for named categories (reps, accounts, stages).

    The top bar carries the deepest navy and the rest step back one shade. That
    is rank encoded in lightness, which is the only encoding a one-hue system
    has left, and it costs nothing because the ordering is already there.
    """
    data = frame.head(limit).copy()
    data["__label"] = data[measure].map(lambda v: by_unit(v, unit))
    leader = data[measure].max()
    data["__lead"] = (data[measure] >= leader).map({True: "lead", False: "rest"})
    height = max(120, 27 * len(data) + 14)

    base = alt.Chart(data).encode(
        y=alt.Y("{}:N".format(dimension), sort="-x", title=None),
        # Headroom for the direct label on the longest bar: without it the
        # leader's value is clipped by the card edge, which is the one label
        # that matters most.
        x=alt.X("{}:Q".format(measure), title=None, axis=None,
                scale=_headroom(leader, 0.16)),
    )
    bars = base.mark_bar(cornerRadiusEnd=3, height=16).encode(
        color=alt.Color("__lead:N", legend=None, scale=alt.Scale(
            domain=["lead", "rest"], range=[_accent(dark), _muted(dark)])),
        tooltip=_tooltip(dimension, measure, unit),
    )
    # Direct labels replace the value axis entirely, and they are also the
    # relief a one-hue palette needs so nothing depends on the fill alone.
    labels = base.mark_text(align="left", dx=6, fontSize=10.5, fontWeight=500,
                            color=_text(dark)).encode(text=alt.Text("__label:N"))
    return (bars + labels).properties(height=height)


def vbar(frame: pd.DataFrame, dimension: str, measure: str, unit: str = "#",
         dark: bool = False) -> alt.Chart:
    data = frame.copy()
    data["__label"] = data[measure].map(lambda v: by_unit(v, unit))
    base = alt.Chart(data).encode(
        x=alt.X("{}:N".format(dimension), sort=None, title=None,
                axis=alt.Axis(labelAngle=0)),
        y=alt.Y("{}:Q".format(measure), title=None, axis=None,
                scale=_headroom(data[measure].max(), 0.12)),
    )
    bars = base.mark_bar(color=_accent(dark), cornerRadiusEnd=3, size=26).encode(
        tooltip=_tooltip(dimension, measure, unit))
    labels = base.mark_text(dy=-8, fontSize=10.5, fontWeight=500,
                            color=_text(dark)).encode(text=alt.Text("__label:N"))
    return (bars + labels).properties(height=HEIGHT)


def line(frame: pd.DataFrame, x: str, y: str, unit: str = "#",
         dark: bool = False, area: bool = True) -> alt.Chart:
    """Single series: no legend (the card title names it) plus a crosshair tooltip."""
    color = _accent(dark)
    palette = tokens.DARK if dark else tokens.LIGHT

    gradient = alt.Gradient(
        gradient="linear", x1=0, x2=0, y1=0, y2=1,
        stops=[alt.GradientStop(color=color, offset=0),
               alt.GradientStop(color=palette["surface"], offset=1)],
    )

    base = alt.Chart(frame).encode(
        x=alt.X("{}:N".format(x), title=None, axis=alt.Axis(labelAngle=0)),
        y=alt.Y("{}:Q".format(y), title=None,
                axis=alt.Axis(format=_fmt(unit), labelExpr=_label_expr(unit))),
    )
    mark = (base.mark_area(opacity=0.5, color=gradient,
                           line={"color": color, "strokeWidth": 2})
            if area else base.mark_line(color=color, strokeWidth=2))

    hover = alt.selection_point(on="mouseover", nearest=True, empty=False, fields=[x])
    rule = base.mark_rule(color=palette["border-strong"], strokeWidth=1).encode(
        opacity=alt.condition(hover, alt.value(1), alt.value(0)),
        tooltip=_tooltip(x, y, unit),
    ).add_params(hover)
    # Hover dot with a surface ring, per the overlapping-mark rule.
    points = base.mark_point(filled=True, size=64, color=color,
                             stroke=palette["surface"], strokeWidth=2).encode(
        opacity=alt.condition(hover, alt.value(1), alt.value(0)))
    return (mark + rule + points).properties(height=HEIGHT)


def donut(frame: pd.DataFrame, dimension: str, measure: str, unit: str = "#",
          dark: bool = False) -> alt.Chart:
    """Only for a genuine 3 to 6 way part-to-whole. Anything else is a bar."""
    return alt.Chart(frame).mark_arc(innerRadius=56, cornerRadius=2, padAngle=0.012).encode(
        theta=alt.Theta("{}:Q".format(measure), stack=True),
        color=alt.Color("{}:N".format(dimension), title=None,
                        scale=alt.Scale(range=_palette(dark)),
                        legend=alt.Legend(orient="right", direction="vertical")),
        tooltip=_tooltip(dimension, measure, unit),
    ).properties(height=HEIGHT)


def funnel(frame: pd.DataFrame, dimension: str, measure: str, unit: str = "#",
           dark: bool = False) -> alt.Chart:
    """Horizontal bar on the ordinal ramp. A true funnel distorts area."""
    height = max(140, 30 * len(frame) + 16)
    return alt.Chart(frame).mark_bar(cornerRadiusEnd=3, height=20).encode(
        y=alt.Y("{}:N".format(dimension), sort=None, title=None),
        x=alt.X("{}:Q".format(measure), title=None, axis=None),
        color=alt.Color("{}:N".format(dimension), legend=None,
                        scale=alt.Scale(range=_palette(dark))),
        tooltip=_tooltip(dimension, measure, unit),
    ).properties(height=height)


def sparkline(values: List[float], dark: bool = False) -> Optional[alt.Chart]:
    """A 40px strip for a stat tile: no axes, no labels, no interaction."""
    if not values or len(values) < 2:
        return None
    color = _accent(dark)
    palette = tokens.DARK if dark else tokens.LIGHT
    frame = pd.DataFrame({"i": list(range(len(values))), "v": values})
    gradient = alt.Gradient(
        gradient="linear", x1=0, x2=0, y1=0, y2=1,
        stops=[alt.GradientStop(color=color, offset=0),
               alt.GradientStop(color=palette["surface"], offset=1)],
    )
    return alt.Chart(frame).mark_area(
        opacity=0.4, color=gradient, line={"color": color, "strokeWidth": 1.5},
        interpolate="monotone",
    ).encode(
        x=alt.X("i:Q", axis=None), y=alt.Y("v:Q", axis=None,
                                           scale=alt.Scale(zero=False, nice=False)),
    ).properties(height=40)


def build(frame: pd.DataFrame, viz_type: str, x: Optional[str], y: Optional[str],
          unit: str = "#", dark: bool = False) -> Optional[alt.Chart]:
    """Dispatch a VizSpec onto a builder. Returns None when a table is right."""
    if frame is None or frame.empty:
        return None
    try:
        if viz_type == "hbar" and x and y:
            return hbar(frame, y, x, unit, dark)
        if viz_type == "bar" and x and y:
            return vbar(frame, x, y, unit, dark)
        if viz_type in ("line", "area") and x and y:
            return line(frame, x, y, unit, dark, area=True)
        if viz_type == "donut" and x and y:
            return donut(frame, x, y, unit, dark)
        if viz_type == "funnel" and x and y:
            return funnel(frame, x, y, unit, dark)
    except Exception:  # pragma: no cover - fall back to the table view
        return None
    return None
