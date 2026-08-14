"""The Intellia mark.

One four-point sparkle with two smaller companions, drawn as a path rather than
shipped as a raster so it stays crisp at 14px in a nav row and at 96px in an
empty state.

It reaches the page as a CSS mask, not as inline SVG: ``st.html`` runs its body
through a sanitiser that strips ``<svg>`` outright (verified, the element never
reaches the DOM). A mask keeps the single-asset advantage and goes further than
inline SVG would, because ``background-color: currentColor`` means the mark
inherits its colour from whatever it sits in: white in the navy rail, accent on
the canvas, no second file.
"""

from __future__ import annotations

import base64


def _spark(cx: float, cy: float, r: float) -> str:
    """One four-point star. Concave sides, drawn with four cubics."""
    waist, shoulder = r * 0.085, r * 0.36
    return (
        "M{cx} {t}"
        "C{cx1} {ty},{tx1} {cy1},{r_} {cy}"
        "C{tx1} {cy2},{cx1} {by},{cx} {b}"
        "C{cx2} {by},{tx2} {cy2},{l} {cy}"
        "C{tx2} {cy1},{cx2} {ty},{cx} {t}Z"
    ).format(
        cx=round(cx, 2), cy=round(cy, 2),
        t=round(cy - r, 2), b=round(cy + r, 2),
        l=round(cx - r, 2), r_=round(cx + r, 2),
        cx1=round(cx + waist, 2), cx2=round(cx - waist, 2),
        cy1=round(cy - waist, 2), cy2=round(cy + waist, 2),
        ty=round(cy - shoulder, 2), by=round(cy + shoulder, 2),
        tx1=round(cx + shoulder, 2), tx2=round(cx - shoulder, 2),
    )


MARK_PATH = " ".join([
    _spark(59, 50, 40),
    _spark(17, 22, 12),
    _spark(17, 74, 10),
])


def svg(fill: str = "currentColor") -> str:
    return (
        '<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 100 100">'
        '<path fill="{c}" d="{p}"/></svg>'
    ).format(c=fill, p=MARK_PATH)


def mark_css() -> str:
    """The mask variable plus the one rule every instance of the mark uses.

    The payload is base64, not percent-encoded: a raw ``<svg`` inside the
    injected style block gets mangled by the HTML sanitiser (verified, the rule
    silently vanishes while the rest of the stylesheet survives). base64 has no
    character the sanitiser cares about.
    """
    data = base64.b64encode(svg("#000").encode("utf-8")).decode("ascii")
    return (
        ':root {{ --ix-mark: url("data:image/svg+xml;base64,{data}"); }}\n'
        ".ix-mark {{\n"
        "  display: inline-block; flex: none; vertical-align: -0.12em;\n"
        "  background-color: currentColor;\n"
        "  -webkit-mask: var(--ix-mark) center / contain no-repeat;\n"
        "  mask: var(--ix-mark) center / contain no-repeat;\n"
        "}}\n"
    ).format(data=data)


def mark(size: int = 20, extra_class: str = "") -> str:
    """A span carrying the mark. Colour comes from the surrounding text colour."""
    return ('<span class="ix-mark {cls}" style="width:{s}px;height:{s}px" '
            'aria-hidden="true"></span>').format(s=size, cls=extra_class)


def wordmark(subtitle: str = "", size: int = 21) -> str:
    """Mark plus the name, for the top of the navigation."""
    sub = ('<span class="ix-wordmark-sub">{}</span>'.format(subtitle)) if subtitle else ""
    return (
        '<div class="ix-wordmark">{mark}'
        '<span class="ix-wordmark-name">intellia</span>{sub}</div>'
    ).format(mark=mark(size), sub=sub)


def favicon_svg() -> str:
    """Standalone file contents, used to build the browser tab icon."""
    from intellia.theme.tokens import BRAND_NAVY

    return svg(BRAND_NAVY)
