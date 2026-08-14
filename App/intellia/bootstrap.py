"""Composition root.

Wires the whole object graph exactly once per process. Nothing else in the
application constructs a repository, provider or engine. Swapping the SQLite
connectors for Salesforce / Microsoft Graph is a change to this file alone.
"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import date
from typing import Any, Dict, Optional

from intellia.actions.executor import MockActionExecutor
from intellia.ai.cache import LLMCache
from intellia.ai.claude_provider import ClaudeProvider
from intellia.ai.mock_provider import MockProvider
from intellia.ai.service import AIService
from intellia.config.personas import PERSONA_REGISTRY, Persona, get_persona
from intellia.config.settings import AppSettings, load_settings
from intellia.data.connectors.sqlite_connectors import (
    SqliteCRMConnector, SqliteCalendarConnector, SqliteEmailConnector,
    SqliteSignalConnector, SqliteTaskConnector,
)
from intellia.data.database import Database
from intellia.data.repositories.activity import (
    EmailRepository, MeetingRepository, SignalRepository, TaskRepository,
)
from intellia.data.repositories.crm import AccountRepository, ContactRepository, DealRepository
from intellia.data.repositories.users import TargetRepository, UserRepository
from intellia.data.scope import Scope, resolve_scope
from intellia.insights.builtins import builtin_insights
from intellia.insights.executor import SqlExecutor
from intellia.insights.insight_engine import InsightEngine
from intellia.insights.store import InsightStore
from intellia.insights.widget_registry import (
    DEFAULT_DEPARTMENT, VIZ_ICONS, WidgetRegistry, WidgetSpec,
)
from intellia.services.action_service import ActionService
from intellia.services.context_service import ContextService
from intellia.services.daily_brief import DailyBriefService
from intellia.services.meeting_prep import MeetingPrepService
from intellia.services.metrics_service import MetricsService
from intellia.utils.formatting import short_sentence
from intellia.utils.logging import configure, get_logger

log = get_logger("bootstrap")

# Bespoke panels that are not SQL-backed. Rendering is attached by the UI layer.
# (key, title, category, subtitle, span, removable, short title, icon)
COMPONENT_WIDGETS = [
    ("component.daily_brief", "Daily brief", "focus",
     "What changed overnight and what it means.", 2, False,
     "Daily brief", ":material/summarize:"),
    ("component.meetings", "Today's meetings", "focus",
     "Your calendar for today, with prep on every row.", 1, True,
     "Meetings", ":material/event:"),
    ("component.actions", "Your actions", "actions",
     "Ranked from your meetings, mail, deals and signals.", 1, True,
     "Actions", ":material/checklist:"),
]

# (key, title, short title)
KPI_WIDGETS = {
    "rep": [
        ("kpi.my_open_pipeline", "Open pipeline", "Pipeline"),
        ("kpi.my_bookings_qtd", "Bookings QTD", "Bookings"),
        ("kpi.my_quota_attainment", "Quota attainment", "Attainment"),
    ],
    "manager": [
        ("kpi.team_open_pipeline", "Team open pipeline", "Team pipeline"),
        ("kpi.team_bookings_qtd", "Team bookings QTD", "Team bookings"),
        ("kpi.team_win_rate", "Team win rate", "Win rate"),
    ],
}


@dataclass
class AppContext:
    settings: AppSettings
    db: Database
    reporting_date: date

    users: UserRepository
    targets: TargetRepository
    accounts: AccountRepository
    contacts: ContactRepository
    deals: DealRepository
    meetings: MeetingRepository
    emails: EmailRepository
    signals: SignalRepository
    tasks: TaskRepository

    crm: SqliteCRMConnector
    calendar: SqliteCalendarConnector
    mail: SqliteEmailConnector
    signal_feed: SqliteSignalConnector
    task_feed: SqliteTaskConnector

    metrics: MetricsService
    context: ContextService
    actions: ActionService
    brief: DailyBriefService
    prep: MeetingPrepService

    ai: AIService
    engine: InsightEngine
    store: InsightStore
    registry: WidgetRegistry
    executor: MockActionExecutor

    _scopes: Dict[str, Scope] = None  # type: ignore[assignment]

    def scope_for(self, persona_id: str) -> Scope:
        if self._scopes is None:
            self._scopes = {}
        if persona_id not in self._scopes:
            with self.db.raw_reader() as conn:
                self._scopes[persona_id] = resolve_scope(conn, get_persona(persona_id))
        return self._scopes[persona_id]

    def persona(self, persona_id: str) -> Persona:
        return get_persona(persona_id)


def build_context(settings: Optional[AppSettings] = None,
                  force_rebuild: bool = False) -> AppContext:
    settings = settings or load_settings()
    configure(settings.debug)

    db = Database(settings)
    rebuilt = db.ensure_built(force=force_rebuild)
    if rebuilt:
        log.info("Analytics database rebuilt from CSV seed.")

    users = UserRepository(db)
    targets = TargetRepository(db)
    accounts = AccountRepository(db)
    contacts = ContactRepository(db)
    deals = DealRepository(db)
    meetings = MeetingRepository(db)
    emails = EmailRepository(db)
    signals = SignalRepository(db)
    tasks = TaskRepository(db)

    crm = SqliteCRMConnector(accounts, deals, contacts)
    calendar = SqliteCalendarConnector(meetings)
    mail = SqliteEmailConnector(emails)
    signal_feed = SqliteSignalConnector(signals)
    task_feed = SqliteTaskConnector(tasks)

    metrics = MetricsService(db, targets)
    context = ContextService(accounts, deals, contacts, meetings, emails, signals, tasks)
    action_service = ActionService(deals, meetings, emails, signals, tasks)

    cache = LLMCache(settings.cache_dir, db)
    mock = MockProvider()
    provider: Any = mock
    if settings.llm_available:
        claude = ClaudeProvider(settings.api_key or "", settings.model,
                                settings.fast_model)
        provider = claude if claude.available else mock
        if provider is mock:
            log.info("ANTHROPIC_API_KEY set but the client is unavailable; "
                     "running in prepared mode.")
    ai = AIService(provider, cache, mock, settings.reporting_date.isoformat(),
                   settings.debug)

    brief = DailyBriefService(ai, context, metrics)
    prep = MeetingPrepService(ai, context)

    store = InsightStore(db)
    sql_executor = SqlExecutor(db, settings.max_rows, settings.query_timeout_seconds)
    engine = InsightEngine(db, sql_executor, store, ai, settings.reporting_date)

    store.seed(builtin_insights())
    registry = _build_registry(store)

    for persona_id, persona in PERSONA_REGISTRY.items():
        store.seed_layout(persona_id, persona.default_widgets)

    return AppContext(
        settings=settings, db=db, reporting_date=settings.reporting_date,
        users=users, targets=targets, accounts=accounts, contacts=contacts,
        deals=deals, meetings=meetings, emails=emails, signals=signals, tasks=tasks,
        crm=crm, calendar=calendar, mail=mail, signal_feed=signal_feed,
        task_feed=task_feed,
        metrics=metrics, context=context, actions=action_service,
        brief=brief, prep=prep,
        ai=ai, engine=engine, store=store, registry=registry,
        executor=MockActionExecutor(settings.reporting_date),
        _scopes={},
    )


def _build_registry(store: InsightStore) -> WidgetRegistry:
    registry = WidgetRegistry()

    for key, title, category, subtitle, span, removable, short, icon in COMPONENT_WIDGETS:
        registry.register(WidgetSpec(
            key=key, title=title, category=category, kind="component",
            subtitle=subtitle, span=span, removable=removable,
            short_title=short, icon=icon, department=DEFAULT_DEPARTMENT,
        ))

    seen = set()
    for persona_id, entries in KPI_WIDGETS.items():
        for key, title, short in entries:
            if key in seen:
                continue
            seen.add(key)
            registry.register(WidgetSpec(
                key=key, title=title, category="insights", kind="kpi",
                subtitle="Live metric, computed from SQL.",
                short_title=short, icon=":material/speed:",
                department=DEFAULT_DEPARTMENT,
                default_visible_for=[persona_id],
            ))

    refresh_insight_widgets(registry, store)
    return registry


def refresh_insight_widgets(registry: WidgetRegistry, store: InsightStore) -> None:
    """Sync registry entries with whatever insights exist (builtin + user-created)."""
    for config in store.list_all():
        registry.register(WidgetSpec(
            key=config.id,
            title=config.title,
            category=config.category,
            kind="insight",
            # Normalised here rather than only at save time, so a card saved
            # before the subtitle rule existed still reads like its neighbours.
            subtitle=short_sentence(config.subtitle),
            short_title=config.title,
            icon=VIZ_ICONS.get(config.viz.type, ":material/insights:"),
            department=DEFAULT_DEPARTMENT,
            insight_id=config.id,
            viz_type=config.viz.type,
            default_visible_for=list(config.personas),
            span=config.span,
            source=config.metadata.source,
        ))
