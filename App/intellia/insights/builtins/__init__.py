"""Built-in insights.

These are seeded ``InsightConfig`` rows, not bespoke Python. Builtins and
AI-created insights therefore travel exactly one code path: they get filters,
versioning, the info panel and Edit-with-AI for free, and there is only one
rendering path to keep correct.
"""

from __future__ import annotations

from typing import List

from intellia.models.insight import (
    InsightConfig, InsightMetadata, RefreshSpec, ScopeBinding, VizSpec,
)
from intellia.utils.dates import fmt, quarter_bounds, today, window, ytd_bounds

OPEN = "d.stage NOT IN ('Stage 5 - Closed Won', 'Stage 5 - Closed Lost')"
WON = "d.stage = 'Stage 5 - Closed Won'"


def _config(key: str, title: str, subtitle: str, sql: str, viz: VizSpec,
            calculation: str, personas: List[str], span: int = 1,
            category: str = "insights", cadence: str = "Hourly",
            source_label: str = "Intellia CRM (SQLite)") -> InsightConfig:
    return InsightConfig(
        id=key,
        title=title,
        subtitle=subtitle,
        description=subtitle,
        generated_sql=sql.strip(),
        nl_definition=subtitle,
        category=category,
        viz=viz,
        personas=personas,
        span=span,
        scope_binding=ScopeBinding(persona_scoped=True),
        refresh=RefreshSpec(mode="on_load", cadence_label=cadence),
        metadata=InsightMetadata(
            source="builtin",
            calculation=calculation,
            data_source=source_label,
            model="Deterministic SQL (no model call)",
        ),
    )


def builtin_insights() -> List[InsightConfig]:
    as_of = today()
    q_start, q_end = quarter_bounds(as_of)
    y_start, y_end = ytd_bounds(as_of)
    # Three weeks before the reporting date. The old expression fell back to the
    # reporting date itself for the first 21 days of any month, so "deals at risk"
    # listed EVERY open deal while the card claimed they had not moved in three
    # weeks. Same 21 days DealRepository.stalled() uses, so the card and the
    # action queue can no longer disagree about what "stalled" means.
    stalled_cutoff = fmt(window(21)[0])

    q0, q1 = fmt(q_start), fmt(q_end)
    y0, y1 = fmt(y_start), fmt(y_end)
    today_str = fmt(as_of)

    both = ["rep", "manager"]
    rep_only = ["rep"]
    mgr_only = ["manager"]

    return [
        # -- shared ---------------------------------------------------------------------
        _config(
            "insight.pipeline_by_stage",
            "Pipeline by stage",
            "Open pipeline value at each stage of the sales process.",
            """
            SELECT d.stage AS stage, SUM(d.amount) AS open_pipeline
            FROM deals d
            WHERE {open}
            GROUP BY d.stage
            ORDER BY d.stage
            """.format(open=OPEN),
            VizSpec(type="hbar", x="open_pipeline", y="stage", unit="$", sort="-x"),
            "Sum of amount for deals that are not Closed Won or Closed Lost, grouped by stage.",
            both,
        ),
        _config(
            "insight.deals_closing",
            "Deals closing this quarter",
            "Open opportunities with a close date inside the current quarter.",
            """
            SELECT a.account_name AS account,
                   d.stage        AS stage,
                   d.amount       AS amount,
                   d.close_date   AS close_date,
                   d.probability  AS probability
            FROM deals d
            JOIN accounts a ON d.account_id = a.account_id
            WHERE {open} AND d.close_date BETWEEN '{q0}' AND '{q1}'
            ORDER BY d.amount DESC
            LIMIT 15
            """.format(open=OPEN, q0=q0, q1=q1),
            VizSpec(type="table", unit="$"),
            "Open deals whose close date falls between {} and {}.".format(q0, q1),
            both, span=2,
        ),
        _config(
            "insight.pipeline_trend",
            "Pipeline created by month",
            "New pipeline generated each month, on a created-date cohort.",
            """
            SELECT strftime('%Y-%m', d.created_date) AS month,
                   SUM(d.amount)                     AS pipeline_created
            FROM deals d
            GROUP BY month
            ORDER BY month
            """,
            VizSpec(type="line", x="month", y="pipeline_created", unit="$"),
            "Sum of amount grouped by the month a deal was created. Pipeline "
            "generation is always a created-date cohort, per the semantic layer.",
            both, span=2, cadence="Daily",
        ),
        _config(
            "insight.at_risk_deals",
            "Deals at risk",
            "Open deals that have not moved stage in three weeks or more.",
            """
            SELECT a.account_name AS account,
                   d.amount       AS amount,
                   d.stage        AS stage,
                   d.close_date   AS close_date,
                   CAST(julianday('{today}') - julianday(d.stage_entered_at) AS INTEGER)
                       AS days_in_stage
            FROM deals d
            JOIN accounts a ON d.account_id = a.account_id
            WHERE {open} AND d.stage_entered_at <= '{cutoff}'
            ORDER BY d.amount DESC
            LIMIT 12
            """.format(open=OPEN, today=today_str, cutoff=stalled_cutoff),
            VizSpec(type="table", unit="$"),
            "Open deals whose stage last changed on or before {} (three weeks "
            "before today), ranked by value.".format(stalled_cutoff),
            both, span=2, cadence="Hourly",
        ),
        _config(
            "insight.deal_type_mix",
            "Deal type mix",
            "How open pipeline splits across new logo, upsell and renewal.",
            """
            SELECT d.deal_type AS deal_type, SUM(d.amount) AS open_pipeline
            FROM deals d
            WHERE {open}
            GROUP BY d.deal_type
            ORDER BY open_pipeline DESC
            """.format(open=OPEN),
            VizSpec(type="donut", x="deal_type", y="open_pipeline", unit="$"),
            "Open pipeline grouped by deal type. A genuine three-way part-to-whole.",
            both,
        ),
        _config(
            "insight.top_accounts",
            "Top accounts by open pipeline",
            "Accounts carrying the most open opportunity value.",
            """
            SELECT a.account_name AS account, SUM(d.amount) AS open_pipeline
            FROM deals d
            JOIN accounts a ON d.account_id = a.account_id
            WHERE {open}
            GROUP BY a.account_name
            ORDER BY open_pipeline DESC
            LIMIT 10
            """.format(open=OPEN),
            VizSpec(type="hbar", x="open_pipeline", y="account", unit="$", sort="-x"),
            "Sum of open deal amount per account, top ten.",
            both,
        ),
        _config(
            "insight.win_rate_by_type",
            "Win rate by deal type",
            "Revenue-weighted win rate for each deal type, year to date.",
            """
            SELECT d.deal_type AS deal_type,
                   ROUND(100.0 * SUM(CASE WHEN {won} THEN d.amount ELSE 0 END)
                         / NULLIF(SUM(d.amount), 0), 1) AS win_rate_pct
            FROM deals d
            WHERE d.stage IN ('Stage 5 - Closed Won', 'Stage 5 - Closed Lost')
              AND d.close_date BETWEEN '{y0}' AND '{y1}'
            GROUP BY d.deal_type
            ORDER BY win_rate_pct DESC
            """.format(won=WON, y0=y0, y1=y1),
            VizSpec(type="hbar", x="win_rate_pct", y="deal_type", unit="%", sort="-x"),
            "Closed Won amount divided by all closed amount, year to date, by deal "
            "type. Revenue-weighted by default, per the semantic layer.",
            both, cadence="Daily",
        ),
        _config(
            "insight.signals_watchlist",
            "Signals to watch",
            "Unactioned buying and risk signals scored 80 or above.",
            """
            SELECT a.account_name AS account,
                   s.signal_type  AS signal,
                   s.signal_title AS detail,
                   s.score        AS score
            FROM signals s
            JOIN accounts a ON s.account_id = a.account_id
            WHERE s.status = 'New' AND s.score >= 80
            ORDER BY s.score DESC
            LIMIT 10
            """,
            VizSpec(type="table", unit="#"),
            "New signals with a score of 80 or higher, most severe first.",
            both, span=2, cadence="Hourly",
            source_label="Intellia Signals (local)",
        ),

        # -- rep ------------------------------------------------------------------------
        _config(
            "insight.my_next_steps",
            "Your committed next steps",
            "Open deals with a next step and the date you committed to.",
            """
            SELECT a.account_name       AS account,
                   d.next_step          AS next_step,
                   d.next_step_due_date AS due_date,
                   d.amount             AS amount
            FROM deals d
            JOIN accounts a ON d.account_id = a.account_id
            WHERE {open} AND d.next_step != ''
            ORDER BY d.next_step_due_date
            LIMIT 12
            """.format(open=OPEN),
            VizSpec(type="table", unit="$"),
            "Open deals that carry a next step, ordered by the committed date.",
            rep_only, span=2,
        ),

        # -- manager --------------------------------------------------------------------
        _config(
            "insight.pipeline_by_rep",
            "Pipeline by rep",
            "Open pipeline owned by each rep on the team.",
            """
            SELECT u.full_name AS rep, SUM(d.amount) AS open_pipeline
            FROM deals d
            JOIN users u ON d.owner_id = u.user_id
            WHERE {open}
            GROUP BY u.full_name
            ORDER BY open_pipeline DESC
            """.format(open=OPEN),
            VizSpec(type="hbar", x="open_pipeline", y="rep", unit="$", sort="-x"),
            "Sum of open deal amount grouped by deal owner.",
            mgr_only,
        ),
        _config(
            "insight.attainment_by_rep",
            "Quota attainment by rep",
            "Closed-won bookings against each rep's quarterly target.",
            """
            SELECT u.full_name AS rep,
                   ROUND(100.0 * SUM(CASE WHEN {won}
                                          AND d.close_date BETWEEN '{q0}' AND '{q1}'
                                     THEN d.amount ELSE 0 END)
                         / NULLIF(MAX(t.target_amount), 0), 1) AS attainment_pct
            FROM deals d
            JOIN users u ON d.owner_id = u.user_id
            LEFT JOIN targets t
                   ON t.user_id = u.user_id
                  AND t.period_type = 'quarter'
                  AND t.period_start = '{q0}'
            WHERE u.quota_annual > 0
            GROUP BY u.full_name
            ORDER BY attainment_pct DESC
            """.format(won=WON, q0=q0, q1=q1),
            VizSpec(type="hbar", x="attainment_pct", y="rep", unit="%", sort="-x"),
            "Closed Won bookings this quarter divided by the rep's quarterly "
            "target from the targets table.",
            mgr_only, cadence="Daily",
        ),
        _config(
            "insight.rep_activity",
            "Meeting activity by rep",
            "Meetings organised by each rep over the last 30 days.",
            """
            SELECT u.full_name         AS rep,
                   COUNT(m.meeting_id) AS meetings
            FROM meetings m
            JOIN users u ON m.organizer_id = u.user_id
            WHERE date(m.scheduled_start) >= date('{today}', '-30 days')
            GROUP BY u.full_name
            ORDER BY meetings DESC
            """.format(today=today_str),
            VizSpec(type="hbar", x="meetings", y="rep", unit="#", sort="-x"),
            "Count of meetings whose scheduled start falls in the last 30 days, "
            "grouped by organiser.",
            mgr_only, cadence="Hourly",
            source_label="Outlook Calendar (local)",
        ),
        _config(
            "insight.coverage_by_rep",
            "Pipeline coverage by rep",
            "Open pipeline divided by each rep's remaining quarterly target.",
            """
            SELECT u.full_name AS rep,
                   ROUND(SUM(CASE WHEN {open}
                                       AND d.close_date BETWEEN '{q0}' AND '{q1}'
                                  THEN d.amount ELSE 0 END)
                         / NULLIF(MAX(t.target_amount), 0), 2) AS coverage
            FROM deals d
            JOIN users u ON d.owner_id = u.user_id
            LEFT JOIN targets t
                   ON t.user_id = u.user_id
                  AND t.period_type = 'quarter'
                  AND t.period_start = '{q0}'
            WHERE u.quota_annual > 0
            GROUP BY u.full_name
            ORDER BY coverage DESC
            """.format(open=OPEN, q0=q0, q1=q1),
            VizSpec(type="hbar", x="coverage", y="rep", unit="x", sort="-x"),
            "Open pipeline closing this quarter divided by the rep's quarterly target.",
            mgr_only, cadence="Daily",
        ),
    ]
