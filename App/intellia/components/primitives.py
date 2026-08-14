"""Render primitives.

The hybrid card pattern lives here.

``st.html`` output is inert (DOMPurify strips handlers and no JS runs) so a
button inside an HTML body can never call back into Python. The pattern is
therefore: **container is the shell, HTML is the body, widgets are the footer.**
The shell uses ``border=False`` and lets CSS draw the border, so ``.ix-card``
(used for bodies built entirely in HTML) and the hybrid shell share one rule and
cannot drift apart.

``st.html`` escapes nothing, so every value that reaches it goes through ``esc``.
"""

from __future__ import annotations

from contextlib import contextmanager
from typing import Any, Iterator, List, Optional, Sequence

import streamlit as st

from intellia.utils.dates import refreshed_label
from intellia.utils.formatting import esc, initials

BADGE_LABELS = {
    "priority": "Priority",
    "decision": "Decision",
    "opportunity": "Opportunity",
    "risk": "Risk",
    "followup": "Follow up",
}


@contextmanager
def card(key: str, variant: str = "") -> Iterator[Any]:
    """The hybrid shell. CSS draws the chrome; widgets may live inside."""
    container = st.container(key="card-{}".format(key), border=False)
    with container:
        yield container


def card_header(title: str, subtitle: str = "", eyebrow: str = "") -> str:
    parts = []
    if eyebrow:
        parts.append('<p class="ix-eyebrow">{}</p>'.format(esc(eyebrow)))
    parts.append('<p class="ix-card-title">{}</p>'.format(esc(title)))
    if subtitle:
        parts.append('<p class="ix-card-sub">{}</p>'.format(esc(subtitle)))
    return "".join(parts)


def section_header(title: str, count: Optional[int] = None, anchor: str = "") -> None:
    suffix = ' <span class="ix-count">{}</span>'.format(count) if count is not None else ""
    anchor_html = '<div id="{}" style="scroll-margin-top:20px"></div>'.format(
        esc(anchor)) if anchor else ""
    st.html(
        '{a}<div style="display:flex;align-items:center;gap:7px;margin:2px 0 8px">'
        '<span class="ix-eyebrow">{t}</span>{s}</div>'.format(
            a=anchor_html, t=esc(title), s=suffix)
    )


def badge(kind: str) -> str:
    label = BADGE_LABELS.get(kind, kind.title())
    return '<span class="ix-badge ix-badge--{k}"><i></i>{l}</span>'.format(
        k=esc(kind), l=esc(label))


def chip(text: str, tone: str = "") -> str:
    cls = " ix-chip--{}".format(esc(tone)) if tone else ""
    return '<span class="ix-chip{c}">{t}</span>'.format(c=cls, t=esc(text))


def dot(tone: str) -> str:
    return '<span class="ix-dot ix-dot--{}"></span>'.format(esc(tone))


def meta(*parts: str) -> str:
    clean = [esc(p) for p in parts if p]
    return '<p class="ix-row-meta">{}</p>'.format(" &middot; ".join(clean)) if clean else ""


def avatars(names: Sequence[str], limit: int = 3) -> str:
    if not names:
        return ""
    shown = list(names)[:limit]
    extra = len(names) - len(shown)
    bubbles = "".join(
        '<span class="ix-avatar">{}</span>'.format(esc(initials(n))) for n in shown)
    if extra > 0:
        bubbles += '<span class="ix-avatar ix-avatar--more">+{}</span>'.format(extra)
    return '<div class="ix-avatars">{}</div>'.format(bubbles)


def empty_state(headline: str, sub: str = "") -> None:
    st.html(
        '<div class="ix-empty"><p class="ix-empty-head">{h}</p>'
        '<p class="ix-empty-sub">{s}</p></div>'.format(h=esc(headline), s=esc(sub))
    )


def error_card(headline: str, sub: str = "") -> None:
    """The ONLY error surface. st.error / st.warning / st.exception are banned:
    they render Streamlit's blue and yellow alert boxes and wreck the palette."""
    st.html(
        '<div class="ix-error"><p class="ix-error-head">{h}</p>'
        '<p class="ix-error-sub">{s}</p></div>'.format(h=esc(headline), s=esc(sub))
    )


def skeleton(rows: int = 3, height: int = 12) -> None:
    """Sized to match the real content so the page does not jump on load."""
    bars = "".join(
        '<div class="ix-skel" style="height:{h}px;width:{w}%;margin-bottom:8px"></div>'
        .format(h=height, w=w) for w in ([92, 74, 84, 66, 88][:rows])
    )
    st.html('<div style="padding:4px 0">{}</div>'.format(bars))


def card_footer(source: str = "", stamp: str = "") -> str:
    """Every widget carries its provenance and its refresh stamp, bottom corners."""
    return '<div class="ix-card-foot"><span>{s}</span><span>{u}</span></div>'.format(
        s=esc(source), u=esc(stamp or refreshed_label()))


def kpi_html(label: str, value: str, caption: str = "", delta: str = "",
             delta_dir: str = "flat") -> str:
    delta_html = ('<span class="ix-delta ix-delta--{d}">{t}</span>'.format(
        d=esc(delta_dir), t=esc(delta)) if delta else "")
    caption_html = ('<span class="ix-kpi-caption">{}</span>'.format(esc(caption))
                    if caption else "")
    return (
        '<p class="ix-kpi-label">{l}</p>'
        '<p class="ix-kpi-value">{v}</p>'
        '<div class="ix-kpi-row">{d}{c}</div>'
    ).format(l=esc(label), v=esc(value), d=delta_html, c=caption_html)


def meter_slot(fraction: Optional[float]) -> str:
    """A fixed-height slot so tiles with and without a trend line up.

    A stat row where one tile is shorter than its neighbours reads as a bug, and
    equalising with a min-height on the card leaves the footer floating. Giving
    the visual its own constant-height slot fixes the alignment at the source.
    """
    if fraction is None:
        return '<div class="ix-meter-slot"></div>'
    pct = max(0.0, min(1.0, float(fraction))) * 100
    return ('<div class="ix-meter-slot"><div class="ix-meter">'
            '<i style="width:{:.1f}%"></i></div></div>').format(pct)


# Measured off the rendered grid, not guessed: the inner scroll content of a
# four-row table is 155px, so a band (header or row) is 31px.
ROW_HEIGHT = 31
GRID_PADDING = 2


def table_height(rows: int, cap: int = 7) -> int:
    """Header band plus whole row bands, and not one pixel more.

    ``st.dataframe`` requires an explicit integer (None is rejected) and honours
    it exactly, so any leftover space is painted as an empty band, which reads as
    a truncated row.
    """
    return ROW_HEIGHT * (max(1, min(rows, cap)) + 1) + GRID_PADDING


def esc_text(value: Any) -> str:
    """``esc`` re-exported for components that only need escaping."""
    return esc(value)


def definition_list(pairs: List[Any]) -> str:
    out = ['<dl class="ix-dl">']
    for term, value in pairs:
        out.append("<dt>{}</dt><dd>{}</dd>".format(esc(term), esc(value)))
    out.append("</dl>")
    return "".join(out)


def key_values(pairs: List[Any]) -> str:
    return "".join(
        '<div class="ix-kv"><span>{}</span><span>{}</span></div>'.format(
            esc(k), esc(v)) for k, v in pairs)


def bullet_section(label: str, items: Sequence[str], ordered: bool = False) -> str:
    if not items:
        return ""
    tag = "ol" if ordered else "ul"
    lis = "".join("<li>{}</li>".format(esc(i)) for i in items)
    return (
        '<div class="ix-section"><p class="ix-section-label">{l}</p>'
        "<{t}>{c}</{t}></div>"
    ).format(l=esc(label), t=tag, c=lis)


def text_section(label: str, body: str) -> str:
    if not body:
        return ""
    return (
        '<div class="ix-section"><p class="ix-section-label">{l}</p>'
        "<p>{b}</p></div>"
    ).format(l=esc(label), b=esc(body))


# -- the info panel ----------------------------------------------------------------------

def info_popover(key: str, title: str, pairs: List[Any], sql: str = "") -> None:
    """Metric provenance, opened beside the icon rather than over the canvas.

    Everything shown here is already computed, so rendering it inside a popover
    costs nothing: no query runs and no model is called to fill it.
    """
    with st.container(key="icon-info-{}".format(key)):
        with st.popover("ⓘ", help="Definition, source and refresh"):
            st.html('<p class="ix-pop-title">{}</p>{}'.format(
                esc(title), definition_list(pairs)))
            if sql:
                with st.expander("Query"):
                    st.code(sql, language="sql", wrap_lines=True)


def control_strip(key: str, controls: Sequence[Any]) -> None:
    """The top-right controls on every card, as icons rather than a dropdown.

    ``controls`` is a sequence of ``(icon, tooltip, callback, args)``. One click
    each: nothing the user needs sits two clicks deep behind a menu.

    Call this OUTSIDE any fragment. A button inside a fragment reruns only that
    fragment, so anything it sets for the app (a dialog intent, a layout write)
    is never picked up by the dispatcher.
    """
    if not controls:
        return
    # Keyed row-* so it inherits the tight-row rule: children take their
    # content width and never wrap, or the icons stack into a column.
    with st.container(key="row-tools-{}".format(key), horizontal=True):
        for index, entry in enumerate(controls):
            icon, tooltip, callback, args = entry
            with st.container(key="icon-c{}-{}".format(index, key)):
                st.button("", key="ctl-{}-{}".format(key, index), icon=icon,
                          help=tooltip, on_click=callback, args=args)
