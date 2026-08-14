"""Compose: the canvas control strip.

A single rectangle above the canvas. The top row is icons only, each with a
tooltip; picking one opens that group's components underneath as tiles. A tile
is a real toggle, so what you see lit is what is on the canvas.

Insights are grouped by department. Sales is the only one seeded today, and the
grouping key lives on ``WidgetSpec`` so adding Marketing or Service is data, not
a code change.

Deliberately NOT inside a fragment: toggling a widget genuinely changes the
canvas, so a full rerun is the correct behaviour.
"""

from __future__ import annotations

from typing import Callable, Dict, List, Sequence

import streamlit as st

from intellia.insights.widget_registry import (
    CATEGORY_DESCRIPTIONS, CATEGORY_ICONS, CATEGORY_LABELS, CATEGORY_ORDER, WidgetSpec,
)
from intellia.utils.formatting import esc, truncate

TILES_PER_ROW = 4


def render_composer(widgets: Sequence[WidgetSpec], visibility: Dict[str, bool],
                    on_toggle: Callable[[str], None],
                    on_select: Callable[[str], None],
                    on_create: Callable[[], None],
                    on_add: Callable[[], None],
                    on_add_block: Callable[[str], None]) -> None:
    shown = sum(1 for w in widgets if visibility.get(w.key, False))
    active = st.session_state.get("compose_tab")

    with st.container(key="ctl-compose"):
        _toolbar(widgets, active, shown, on_select, on_create, on_add)
        if active == "layout":
            _layout_group([w for w in widgets if w.category == "layout"],
                          visibility, on_toggle, on_add_block)
        elif active:
            _tiles([w for w in widgets if w.category == active], visibility, on_toggle)


def _layout_group(blocks: Sequence[WidgetSpec], visibility: Dict[str, bool],
                  on_toggle, on_add_block) -> None:
    """Headings and notes the user writes themselves.

    Streamlit has no drag-and-drop, so a block is added here and then positioned
    with the arrows on its own card, which is the same control every other widget
    on the canvas has.
    """
    st.html('<div style="height:2px;border-top:1px solid var(--border);margin-top:8px">'
            '</div><p class="ix-tile-group">Add your own</p>')
    row = st.container(key="row-add-block", horizontal=True)
    with row:
        with st.container(key="tile-new-heading"):
            st.button("Section title", key="add-heading",
                      icon=":material/title:", width="stretch",
                      help="A heading to group the cards below it",
                      on_click=on_add_block, args=("heading",))
        with st.container(key="tile-new-note"):
            st.button("Text note", key="add-note", icon=":material/notes:",
                      width="stretch", help="A free text block on your canvas",
                      on_click=on_add_block, args=("note",))

    if blocks:
        st.html('<p class="ix-tile-group">On your canvas</p>')
        _tile_grid(blocks, visibility, on_toggle)


def _toolbar(widgets: Sequence[WidgetSpec], active, shown: int,
             on_select, on_create, on_add) -> None:
    row = st.container(key="row-compose-bar", horizontal=True,
                       vertical_alignment="center")
    with row:
        st.html('<p class="ix-tool-head">Compose</p>')

        for category in CATEGORY_ORDER:
            count = sum(1 for w in widgets if w.category == category)
            # Layout is always offered: it is where blocks are created, so
            # hiding it until one exists would make the first one unreachable.
            if not count and category != "layout":
                continue
            key = ("tool-on-{}" if category == active else "tool-{}").format(category)
            with st.container(key=key):
                st.button("", key="toolbtn-{}".format(category),
                          icon=CATEGORY_ICONS[category],
                          help="{}: {}".format(CATEGORY_LABELS[category],
                                               CATEGORY_DESCRIPTIONS[category]),
                          on_click=on_select, args=(category,))

        st.html('<div class="ix-tool-div"></div>')
        with st.container(key="tool-add"):
            st.button("", key="composer-add", icon=":material/library_add:",
                      help="Add a component from the library", on_click=on_add)
        with st.container(key="tool-create"):
            st.button("", key="composer-create", icon=":material/auto_awesome:",
                      help="Create a new insight with AI", on_click=on_create)

        st.html('<p class="ix-meta" style="margin-left:auto;white-space:nowrap">'
                '{} on canvas</p>'.format(shown))


def _tiles(group: Sequence[WidgetSpec], visibility: Dict[str, bool], on_toggle) -> None:
    if not group:
        return
    st.html('<div style="height:2px;border-top:1px solid var(--border);margin-top:8px">'
            '</div>')

    for department in _departments(group):
        members = [w for w in group if (w.department or "General") == department]
        if len(_departments(group)) > 1 or department != "General":
            st.html('<p class="ix-tile-group">{}</p>'.format(esc(department)))
        _tile_grid(members, visibility, on_toggle)


def _departments(group: Sequence[WidgetSpec]) -> List[str]:
    out: List[str] = []
    for widget in group:
        name = widget.department or "General"
        if name not in out:
            out.append(name)
    return out


def _tile_grid(members: Sequence[WidgetSpec], visibility: Dict[str, bool],
               on_toggle) -> None:
    for start in range(0, len(members), TILES_PER_ROW):
        chunk = list(members[start:start + TILES_PER_ROW])
        columns = st.columns(TILES_PER_ROW, gap="small")
        for column, widget in zip(columns, chunk):
            on = visibility.get(widget.key, False)
            safe = widget.key.replace(".", "-")
            with column:
                with st.container(key=("tile-on-{}" if on else "tile-{}").format(safe)):
                    st.button(
                        truncate(widget.short_title or widget.title, 22),
                        key="vis-{}".format(safe),
                        icon=widget.icon,
                        help="{}{}".format(widget.subtitle or widget.title,
                                           " (on canvas)" if on else ""),
                        width="stretch",
                        on_click=on_toggle, args=(widget.key,),
                    )
