"""Design tokens: the single source of truth for colour, type and spacing.

This module generates BOTH the CSS custom properties and the Altair chart
palettes, so the two can never drift apart.

The system is navy monochromatic by design decision, not by accident:

  * Brand navy ``#12285C`` (the Intellia mark) anchors the ramp.
  * Charts use ONE hue. Series separate by lightness, never by colour, so a
    six-series chart still reads as one system and stays legible to every kind
    of colour vision. Every categorical slot is at least 1.3x apart in relative
    luminance from its neighbours, and direct value labels carry the reading.
  * Red / amber / green survive only as *status* colours (risk, caution, good)
    on chips and rails. They never enter a chart.
  * The left navigation is fixed dark navy in both themes. It is chrome, not
    canvas, so it does not invert.
"""

from __future__ import annotations

from typing import Dict, List

BRAND_NAVY = "#12285C"

# -- categorical series colours ----------------------------------------------------------
# Monochromatic navy. Ordered dark to light on the light surface, light to
# mid on the dark surface, so slot 1 always carries the most weight.

CATEGORICAL_LIGHT: List[str] = [
    "#1D3E76",
    "#2F5C9C",
    "#4B7BBC",
    "#7099D0",
    "#9BB9E2",
    "#C3D6EF",
]

CATEGORICAL_DARK: List[str] = [
    "#8FB2E8",
    "#6D97D8",
    "#5480C6",
    "#3F69AE",
    "#2F5390",
    "#233F72",
]

# Single-hue ramp for ordinal work (stage progression, funnels, heat).
SEQUENTIAL_LIGHT: List[str] = [
    "#EDF2FA", "#DCE6F5", "#C3D6EF", "#A8C2E6", "#8AAADB",
    "#6B90CC", "#4E76B8", "#365D9E", "#22447F", "#12285C",
]
SEQUENTIAL_DARK: List[str] = [
    "#12285C", "#22447F", "#365D9E", "#4E76B8", "#6B90CC",
    "#8AAADB", "#A8C2E6", "#C3D6EF", "#DCE6F5", "#EDF2FA",
]

# -- the fixed navigation surface ---------------------------------------------------------
# Identical in both themes. Defined once and merged into each palette below.

NAV: Dict[str, str] = {
    "nav-bg": "#0B1B36",
    "nav-bg-deep": "#081428",
    "nav-surface": "#12294B",
    "nav-border": "rgba(255,255,255,.09)",
    "nav-text": "#EEF3FB",
    "nav-muted": "#93A6C6",
    "nav-faint": "#6D80A0",
    "nav-hover": "rgba(255,255,255,.07)",
    "nav-active": "rgba(255,255,255,.13)",
    "nav-accent": "#8FB2E8",
}

LIGHT: Dict[str, str] = dict(NAV, **{
    "canvas": "#F6F8FB",
    "surface": "#FFFFFF",
    "surface-sunken": "#F1F4F9",
    "surface-raised": "#FFFFFF",
    "border": "#E4E8F0",
    "border-strong": "#CBD3E1",
    "text-primary": "#0E1729",
    "text-secondary": "#41506B",
    "text-muted": "#5E6B84",
    "text-faint": "#8794AB",
    "accent": "#1D3E76",
    "accent-hover": "#152F5C",
    "accent-soft": "#2F5C9C",
    "accent-wash": "rgba(29, 62, 118, 0.055)",
    "accent-ring": "rgba(29, 62, 118, 0.16)",
    "risk": "#A82A22",
    "risk-wash": "rgba(168, 42, 34, 0.07)",
    "caution": "#8A5A00",
    "caution-wash": "rgba(138, 90, 0, 0.08)",
    "good": "#15694A",
    "good-wash": "rgba(21, 105, 74, 0.07)",
    "shadow-sm": "0 1px 2px rgba(14,23,41,.05)",
    "shadow-md": "0 6px 18px -6px rgba(14,23,41,.12)",
    "shadow-lg": "0 24px 48px -16px rgba(14,23,41,.22)",
})

DARK: Dict[str, str] = dict(NAV, **{
    "canvas": "#0A101C",
    "surface": "#111A2B",
    "surface-sunken": "#162033",
    "surface-raised": "#141E31",
    "border": "#243149",
    "border-strong": "#33425C",
    "text-primary": "#EEF2F9",
    "text-secondary": "#B4C0D4",
    "text-muted": "#8D9AB2",
    "text-faint": "#6E7C95",
    "accent": "#7FA6E8",
    "accent-hover": "#9BBAF0",
    "accent-soft": "#5480C6",
    "accent-wash": "rgba(127, 166, 232, 0.12)",
    "accent-ring": "rgba(127, 166, 232, 0.28)",
    "risk": "#F0A7A1",
    "risk-wash": "rgba(240, 167, 161, 0.12)",
    "caution": "#E3B25C",
    "caution-wash": "rgba(227, 178, 92, 0.12)",
    "good": "#5EC79A",
    "good-wash": "rgba(94, 199, 154, 0.12)",
    "shadow-sm": "0 1px 2px rgba(0,0,0,.45)",
    "shadow-md": "0 6px 18px -6px rgba(0,0,0,.55)",
    "shadow-lg": "0 24px 48px -16px rgba(0,0,0,.65)",
})


def css_variables(tokens: Dict[str, str]) -> str:
    return "\n".join("  --{}: {};".format(k, v) for k, v in tokens.items())


def root_css(dark: bool = False) -> str:
    """The `:root` token block for whichever theme Streamlit is actually running.

    Deliberately NOT a `prefers-color-scheme` media query. Streamlit themes its
    own widgets from `config.toml`, which pins explicit colours, so a CSS-level
    flip would repaint our cards dark while every input, dataframe and popover
    stayed light. `st.context.theme.type` would still read "light" too, so the
    charts would keep the light palette on a dark canvas: three sources of truth
    disagreeing at once.

    One signal drives all of it instead. The caller passes the same ``dark`` flag
    it passes to ``charts.use_theme``, and that flag comes from Streamlit's own
    resolved theme, so tokens, widgets and chart palette cannot drift.

    The app therefore ships committed to the light palette, because config.toml
    pins the light colours. To run it dark, replace the `[theme]` colour keys
    with the output of ``config_theme_toml(dark=True)``; the values come from
    ``DARK`` below, so the two can never disagree.
    """
    return ":root {{\n{}\n}}\n".format(css_variables(DARK if dark else LIGHT))


# Which token feeds which Streamlit config key. Keeping this mapping here is what
# lets config.toml be generated from the palette rather than hand-copied.
CONFIG_KEYS = (
    ("base", None),
    ("primaryColor", "accent"),
    ("backgroundColor", "canvas"),
    ("secondaryBackgroundColor", "surface"),
    ("textColor", "text-primary"),
    ("borderColor", "border"),
    ("dataframeBorderColor", "border"),
    ("dataframeHeaderBackgroundColor", "surface-sunken"),
)


def config_theme_toml(dark: bool = False) -> str:
    """The `[theme]` colour block for config.toml, generated from the palette."""
    palette = DARK if dark else LIGHT
    lines = ["[theme]"]
    for key, token in CONFIG_KEYS:
        value = ("dark" if dark else "light") if token is None else palette[token]
        lines.append('{} = "{}"'.format(key, value))
    series = CATEGORICAL_DARK if dark else CATEGORICAL_LIGHT
    ramp = SEQUENTIAL_DARK if dark else SEQUENTIAL_LIGHT
    lines.append("chartCategoricalColors = {}".format(
        "[" + ", ".join('"{}"'.format(c) for c in series) + "]"))
    lines.append("chartSequentialColors = {}".format(
        "[" + ", ".join('"{}"'.format(c) for c in ramp) + "]"))
    return "\n".join(lines)
