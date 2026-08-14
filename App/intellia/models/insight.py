"""Insight configuration -- the serialized, deterministic definition of a widget.

Once an insight is saved, rendering it replays ``generated_sql`` and never calls the LLM.
"""

from __future__ import annotations

import json
from dataclasses import asdict, dataclass, field
from typing import Any, Dict, List, Optional

@dataclass
class ColumnSpec:
    name: str
    sqlite_type: str = "TEXT"
    role: str = "dimension"  # dimension | measure | temporal | id
    unit: str = "#"          # $ | % | x | #


@dataclass
class VizSpec:
    type: str = "table"
    x: Optional[str] = None
    y: Optional[str] = None
    series: Optional[str] = None
    sort: Optional[str] = None
    limit: Optional[int] = None
    unit: str = "#"
    goal_value: Optional[float] = None
    # A ``metric`` result may carry a second measure to move against, so a created
    # stat card can show the same delta pill a built-in KPI tile does.
    # ``compare`` names that column; ``compare_kind`` says how to read it:
    # "prior" is a value in the same unit (the card computes the change),
    # "change" is a percentage the query already computed.
    compare: Optional[str] = None
    compare_kind: str = ""
    delta_label: str = ""


@dataclass
class FilterSpec:
    column: str
    op: str
    values: List[Any] = field(default_factory=list)
    label: str = ""


@dataclass
class ScopeBinding:
    persona_scoped: bool = True
    date_field: Optional[str] = None
    default_period: str = "quarter"


@dataclass
class RefreshSpec:
    mode: str = "on_load"       # on_load | manual | ttl
    ttl_seconds: int = 300
    cadence_label: str = "Hourly"


@dataclass
class InsightMetadata:
    source: str = "builtin"     # builtin | ai | manual
    created_by_persona: str = ""
    created_at: str = ""
    updated_at: str = ""
    model: str = ""
    prompt_version: str = ""
    generation_ms: int = 0
    row_count_at_creation: int = 0
    validation_warnings: List[str] = field(default_factory=list)
    calculation: str = ""
    data_source: str = "Intellia CRM (SQLite)"


@dataclass
class InsightConfig:
    id: str
    title: str
    generated_sql: str
    version: int = 1
    subtitle: str = ""
    category: str = "insights"          # focus | actions | insights
    nl_definition: str = ""
    description: str = ""
    data_source: str = "intellia_sqlite"
    schema_fingerprint: str = ""
    result_columns: List[ColumnSpec] = field(default_factory=list)
    viz: VizSpec = field(default_factory=VizSpec)
    filters: List[FilterSpec] = field(default_factory=list)
    scope_binding: ScopeBinding = field(default_factory=ScopeBinding)
    refresh: RefreshSpec = field(default_factory=RefreshSpec)
    metadata: InsightMetadata = field(default_factory=InsightMetadata)
    personas: List[str] = field(default_factory=list)   # empty == all personas
    span: int = 1
    parent_version_id: Optional[str] = None
    change_note: str = ""

    # -- serialization -----------------------------------------------------------------

    def to_json(self) -> str:
        return json.dumps(asdict(self), sort_keys=True)

    @classmethod
    def from_dict(cls, raw: Dict[str, Any]) -> "InsightConfig":
        data = dict(raw)
        data["result_columns"] = [ColumnSpec(**c) for c in data.get("result_columns", [])]
        data["viz"] = VizSpec(**data.get("viz", {}) or {})
        data["filters"] = [FilterSpec(**f) for f in data.get("filters", [])]
        data["scope_binding"] = ScopeBinding(**data.get("scope_binding", {}) or {})
        data["refresh"] = RefreshSpec(**data.get("refresh", {}) or {})
        data["metadata"] = InsightMetadata(**data.get("metadata", {}) or {})
        known = {f for f in cls.__dataclass_fields__}  # type: ignore[attr-defined]
        return cls(**{k: v for k, v in data.items() if k in known})

    @classmethod
    def from_json(cls, raw: str) -> "InsightConfig":
        return cls.from_dict(json.loads(raw))
