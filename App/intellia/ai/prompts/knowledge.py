"""Knowledge blob assembly.

These files are large and stable, which makes them the right prefix to mark for
prompt caching -- they are sent as one cached system block on every call.
"""

from __future__ import annotations

from functools import lru_cache
from typing import List

from intellia.config.settings import KNOWLEDGE_DIR
from intellia.utils.logging import get_logger

log = get_logger("prompts")


@lru_cache(maxsize=8)
def _read(name: str) -> str:
    path = KNOWLEDGE_DIR / name
    try:
        return path.read_text(encoding="utf-8")
    except OSError:
        log.warning("Knowledge file missing: %s", path)
        return ""


@lru_cache(maxsize=4)
def company_context() -> str:
    """brain.md -- ICP, personas, playbooks, messaging, tone."""
    return _read("brain.md")


@lru_cache(maxsize=4)
def semantic_layer() -> str:
    """The metric definitions the model must not re-invent."""
    return _read("semantic_layer.md")


@lru_cache(maxsize=4)
def sql_few_shots() -> str:
    return _read("text_to_sql_few_shots.md")


@lru_cache(maxsize=4)
def narrative_knowledge() -> str:
    """Cached prefix for brief / prep / action tasks."""
    parts: List[str] = []
    if company_context():
        parts.append("# Company and GTM context\n\n" + company_context())
    if semantic_layer():
        parts.append("# Metric definitions (never recompute these yourself)\n\n"
                     + semantic_layer())
    return "\n\n---\n\n".join(parts)


@lru_cache(maxsize=4)
def sql_knowledge() -> str:
    """Cached prefix for the text-to-SQL task."""
    parts: List[str] = []
    if semantic_layer():
        parts.append("# Semantic layer\n\n" + semantic_layer())
    if sql_few_shots():
        parts.append("# Worked examples\n\n" + sql_few_shots())
    return "\n\n---\n\n".join(parts)
