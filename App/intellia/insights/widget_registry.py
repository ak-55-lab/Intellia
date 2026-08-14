"""Widget registry.

One interface for four kinds of widget:

* ``kind="insight"``   -- rendered entirely by the insight engine from a saved config
                          (all builtin analytics widgets, plus everything a user creates)
* ``kind="kpi"``       -- a single number from ``MetricsService``, no LLM, no saved SQL
* ``kind="component"`` -- the genuinely bespoke panels (brief, today)
* ``kind="block"``     -- a heading or note the user wrote themselves

The composer, the add menu, visibility, ordering and width treat all four
identically, because they only ever see a ``WidgetSpec``. A hand-written note is
therefore reorderable and resizable with no special case anywhere.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Callable, Dict, List, Optional

CATEGORY_ORDER = ("focus", "actions", "insights", "layout")

CATEGORY_LABELS = {
    "focus": "Focus",
    "actions": "Actions",
    "insights": "Insights",
    "layout": "Layout",
}

CATEGORY_DESCRIPTIONS = {
    "focus": "what needs attention now",
    "actions": "what you need to do",
    "insights": "what the data is telling you",
    "layout": "your own headings and notes",
}

CATEGORY_ICONS = {
    "focus": ":material/bolt:",
    "actions": ":material/checklist:",
    "insights": ":material/monitoring:",
    "layout": ":material/text_fields:",
}

# Insights group by department in the composer. Sales is the only one seeded
# today; adding Marketing or Service is data, not a code change.
DEFAULT_DEPARTMENT = "Sales"

VIZ_ICONS = {
    "table": ":material/table_rows:",
    "list": ":material/table_rows:",
    "line": ":material/show_chart:",
    "area": ":material/show_chart:",
    "bar": ":material/bar_chart:",
    "hbar": ":material/bar_chart:",
    "funnel": ":material/filter_alt:",
    "donut": ":material/donut_small:",
    "metric": ":material/speed:",
}


@dataclass
class WidgetSpec:
    key: str
    title: str
    category: str                       # focus | actions | insights
    kind: str                           # insight | kpi | component
    subtitle: str = ""
    short_title: str = ""               # what the composer tile shows
    icon: str = ":material/widgets:"
    department: str = ""                # grouping in the composer
    insight_id: Optional[str] = None
    # Mirrors the saved ``VizSpec.type``. The canvas splits the stat band from the
    # chart stream on this, so an insight that resolves to one number sits in the
    # stat row with the built-in KPIs instead of half width among the charts.
    viz_type: str = ""
    render: Optional[Callable[..., None]] = None
    default_visible_for: List[str] = field(default_factory=list)
    span: int = 1
    removable: bool = True
    source: str = "builtin"             # builtin | ai | manual


class WidgetRegistry:
    def __init__(self) -> None:
        self._widgets: Dict[str, WidgetSpec] = {}
        self._order: List[str] = []

    def register(self, spec: WidgetSpec) -> WidgetSpec:
        if spec.key not in self._widgets:
            self._order.append(spec.key)
        self._widgets[spec.key] = spec
        return spec

    def unregister(self, key: str) -> None:
        self._widgets.pop(key, None)
        if key in self._order:
            self._order.remove(key)

    def get(self, key: str) -> Optional[WidgetSpec]:
        return self._widgets.get(key)

    def all(self) -> List[WidgetSpec]:
        return [self._widgets[k] for k in self._order if k in self._widgets]

    def for_persona(self, persona_id: str) -> List[WidgetSpec]:
        return [w for w in self.all()
                if not w.default_visible_for or persona_id in w.default_visible_for]

    def by_category(self, category: str, persona_id: str) -> List[WidgetSpec]:
        return [w for w in self.for_persona(persona_id) if w.category == category]

    def __contains__(self, key: str) -> bool:
        return key in self._widgets

    def __len__(self) -> int:
        return len(self._widgets)
