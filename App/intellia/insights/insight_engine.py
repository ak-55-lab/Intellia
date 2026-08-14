"""Insight engine.

    NL -> LLM -> validate -> describe -> execute -> classify -> pick viz -> save

Replay runs the saved SQL and never calls the LLM again. That is the whole
economic argument of the product, so it is enforced structurally: ``render()``
touches neither the AI service nor any prompt.
"""

from __future__ import annotations

import time
import uuid
from dataclasses import asdict
from datetime import date
from typing import Any, Dict, List, Optional, Tuple

import pandas as pd

from intellia.ai.prompts import knowledge, tasks
from intellia.ai.service import AIService
from intellia.data.database import Database
from intellia.data.scope import Scope
from intellia.insights import filters as filter_mod
from intellia.insights import visualization_selector as viz_mod
from intellia.insights.executor import QueryResult, SqlExecutor
from intellia.insights.store import InsightStore
from intellia.models.insight import (
    FilterSpec, InsightConfig, InsightMetadata, RefreshSpec, ScopeBinding, VizSpec,
)
from intellia.utils.errors import InsightGenerationError, SqlSafetyError
from intellia.utils.formatting import short_sentence
from intellia.utils.logging import get_logger

log = get_logger("insight_engine")


class RenderedInsight:
    def __init__(self, config: InsightConfig, result: QueryResult,
                 error: Optional[str] = None) -> None:
        self.config = config
        self.result = result
        self.error = error

    @property
    def frame(self) -> pd.DataFrame:
        return self.result.dataframe

    @property
    def ok(self) -> bool:
        return self.error is None


class InsightEngine:
    def __init__(self, db: Database, executor: SqlExecutor, store: InsightStore,
                 ai: AIService, reporting_date: date) -> None:
        self.db = db
        self.executor = executor
        self.store = store
        self.ai = ai
        self.reporting_date = reporting_date

    # -- schema context ----------------------------------------------------------------

    def schema_text(self) -> str:
        lines: List[str] = []
        for table, columns in sorted(self.db.allowlist().items()):
            lines.append("- {}({})".format(table, ", ".join(sorted(columns))))
        return "\n".join(lines)

    # -- create ------------------------------------------------------------------------

    def create_from_prompt(self, question: str, scope: Scope, persona_id: str,
                           category: str = "insights", prior: str = "") -> InsightConfig:
        """Full generation path. This is the only place an insight costs an LLM call.

        ``prior`` is the previous turn rendered by ``tasks.prior_turn_block``. It is
        part of the cache key as well as the prompt: the same follow-up wording
        means a different query after a different question, so caching on the
        wording alone would serve one thread's chart to another.
        """
        started = time.monotonic()

        generated = self.ai.run(
            task=tasks.INSIGHT_SQL,
            system=tasks.insight_sql_system(
                self.schema_text(), self.reporting_date.isoformat(), scope.label),
            user=tasks.insight_sql_user(question, prior),
            cacheable_system=knowledge.sql_knowledge(),
            cache_inputs={"question": question.strip().lower(),
                          "prior": prior,
                          "schema": self.db.schema_fingerprint()},
            fallback=lambda: self._fallback_insight(question),
            persona_id=persona_id,
        )
        if generated is None or not generated.sql:
            raise InsightGenerationError()

        # The subtitle is the one-line caption on the card and the description is
        # the full text the info panel shows. Storing the same string in both is
        # what put a model-length sentence in a 11.5px slot beside built-in cards
        # whose subtitles are all one short sentence.
        description = (generated.description or "").strip()

        config = InsightConfig(
            id="ins-" + uuid.uuid4().hex[:12],
            title=generated.title or question[:60],
            subtitle=short_sentence(description),
            description=description,
            generated_sql=generated.sql.strip().rstrip(";"),
            nl_definition=question,
            category=category,
            schema_fingerprint=self.db.schema_fingerprint(),
            viz=VizSpec(type=generated.visualization or "table",
                        unit=generated.unit or "#"),
            scope_binding=ScopeBinding(persona_scoped=True),
            refresh=RefreshSpec(mode="on_load", cadence_label=generated.refresh or "Hourly"),
            metadata=InsightMetadata(
                source="ai",
                created_by_persona=persona_id,
                model=self.ai.mode_label,
                prompt_version=tasks.INSIGHT_SQL.prompt_version,
                calculation=generated.calculation or generated.description or "",
            ),
        )

        rendered = self.render(config, scope)
        if not rendered.ok:
            raise InsightGenerationError(
                "I couldn't run that query against your data. "
                "Try rephrasing. For example: pipeline by rep, by stage, or by account.",
                detail=rendered.error)

        config.metadata.generation_ms = int((time.monotonic() - started) * 1000)
        config.metadata.row_count_at_creation = rendered.result.row_count
        return config

    def _fallback_insight(self, question: str) -> Dict[str, Any]:
        """Deterministic answer when no model is available: open pipeline by stage."""
        return {
            "title": "Open Pipeline by Stage",
            "description": ("Prepared fallback: open pipeline grouped by stage, "
                            "shown because the assistant could not generate a query."),
            "sql": (
                "SELECT stage AS stage, SUM(amount) AS open_pipeline\n"
                "FROM deals\n"
                "WHERE stage NOT IN ('Stage 5 - Closed Won', 'Stage 5 - Closed Lost')\n"
                "GROUP BY stage\nORDER BY open_pipeline DESC"
            ),
            "visualization": "hbar",
            "x": "open_pipeline",
            "y": "stage",
            "unit": "$",
            "calculation": "Sum of amount for deals that are not closed, grouped by stage.",
            "refresh": "Hourly",
        }

    # -- edit --------------------------------------------------------------------------

    def edit_with_ai(self, config: InsightConfig, instruction: str,
                     scope: Scope, persona_id: str) -> Tuple[InsightConfig, RenderedInsight]:
        """Ask for a full replacement config, validate it, and return the candidate.

        The candidate is NOT saved here. If it fails validation or execution the
        caller keeps showing the existing version, so a bad edit can't break a card.
        """
        prompt = (
            "The current insight is titled \"{title}\" and was defined as: {nl}\n\n"
            "Its current SQL is:\n{sql}\n\n"
            "Apply this change: {instruction}\n\n"
            "Return the complete updated insight definition, not a diff."
        ).format(title=config.title, nl=config.nl_definition or config.title,
                 sql=config.generated_sql, instruction=instruction)

        generated = self.ai.run(
            task=tasks.INSIGHT_SQL,
            system=tasks.insight_sql_system(
                self.schema_text(), self.reporting_date.isoformat(), scope.label),
            user=prompt,
            cacheable_system=knowledge.sql_knowledge(),
            cache_inputs={"edit": instruction.strip().lower(), "base": config.id,
                          "version": config.version,
                          "schema": self.db.schema_fingerprint()},
            fallback=None,
            persona_id=persona_id,
        )
        if generated is None or not generated.sql:
            raise InsightGenerationError(
                "I couldn't apply that change. The insight is unchanged.")

        candidate = InsightConfig.from_dict(asdict(config))
        candidate.generated_sql = generated.sql.strip().rstrip(";")
        candidate.title = generated.title or config.title
        candidate.description = (generated.description or config.description).strip()
        candidate.subtitle = short_sentence(candidate.description) or config.subtitle
        candidate.viz = VizSpec(type=generated.visualization or config.viz.type,
                                unit=generated.unit or config.viz.unit)
        candidate.filters = []          # a new base query invalidates old post-filters
        candidate.metadata.source = "ai"
        candidate.metadata.calculation = generated.calculation or config.metadata.calculation
        candidate.metadata.model = self.ai.mode_label

        rendered = self.render(candidate, scope)
        if not rendered.ok:
            raise InsightGenerationError(
                "That change produced a query I couldn't run, so I kept the current "
                "version.", detail=rendered.error)
        return candidate, rendered

    # -- render (no LLM) ---------------------------------------------------------------

    def render(self, config: InsightConfig, scope: Scope,
               extra_filters: Optional[List[FilterSpec]] = None) -> RenderedInsight:
        """Execute a saved insight. Never calls the LLM."""
        all_filters = list(config.filters) + list(extra_filters or [])
        try:
            if all_filters:
                legal = self.executor.probe_columns(config.generated_sql, scope)
                sql, params = filter_mod.wrap(config.generated_sql, all_filters, legal)
            else:
                sql, params = config.generated_sql, []

            result = self.executor.run(sql, scope, params)
        except SqlSafetyError as exc:
            log.info("Insight %s failed: %s", config.id, exc.detail or exc.user_message)
            return RenderedInsight(config, QueryResult(pd.DataFrame()), exc.user_message)
        except Exception as exc:  # pragma: no cover - defensive
            log.exception("Unexpected failure rendering insight %s", config.id)
            return RenderedInsight(
                config, QueryResult(pd.DataFrame()),
                "Something went wrong loading this insight.")

        specs = viz_mod.classify_columns(result.dataframe)
        if not config.result_columns:
            config.result_columns = specs
        # ``metric`` is re-derived every replay rather than trusted from the saved
        # config. Selection is deterministic, so a genuine one-number result gets
        # the identical spec back; a saved card that claims one number over a row
        # of four (which the old renderer hid, by printing the first cell and
        # ignoring its own ``y``) falls back to the honest table.
        if config.viz.type in ("table", "metric") or not config.viz.y:
            config.viz = viz_mod.select(result.dataframe, config.viz.type, specs)
        return RenderedInsight(config, result)

    def filter_options(self, config: InsightConfig, scope: Scope) -> List[str]:
        return self.executor.probe_columns(config.generated_sql, scope)

    def is_stale(self, config: InsightConfig) -> bool:
        return bool(config.schema_fingerprint
                    and config.schema_fingerprint != self.db.schema_fingerprint())
