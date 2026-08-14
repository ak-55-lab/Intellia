"""Metrics service -- 100% deterministic SQL straight from the semantic layer.

No LLM is involved anywhere in this module. Each metric mirrors a formula documented in
``Knowledge/semantic_layer.md`` so the app and the docs cannot disagree.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import date
from typing import Dict, List, Optional, Tuple

from intellia.data.database import Database
from intellia.data.repositories.users import TargetRepository
from intellia.data.scope import Scope
from intellia.utils.dates import quarter_bounds, quarter_label, ytd_bounds

OPEN_STAGES_SQL = "stage NOT IN ('Stage 5 - Closed Won', 'Stage 5 - Closed Lost')"
WON_SQL = "stage = 'Stage 5 - Closed Won'"
CLOSED_SQL = "stage IN ('Stage 5 - Closed Won', 'Stage 5 - Closed Lost')"


@dataclass
class Metric:
    key: str
    label: str
    value: Optional[float]
    unit: str = "$"
    delta: Optional[float] = None
    delta_label: str = ""
    caption: str = ""
    calculation: str = ""
    sparkline: List[float] = field(default_factory=list)


class MetricsService:
    def __init__(self, db: Database, targets: TargetRepository) -> None:
        self.db = db
        self.targets = targets

    # -- primitives --------------------------------------------------------------------

    def _scalar(self, scope: Scope, sql: str, params: Tuple = ()) -> float:
        with self.db.reader(scope) as conn:
            row = conn.execute(sql, params).fetchone()
        return float(row[0]) if row and row[0] is not None else 0.0

    def open_pipeline(self, scope: Scope, start: Optional[date] = None,
                      end: Optional[date] = None) -> float:
        if start and end:
            return self._scalar(
                scope,
                "SELECT COALESCE(SUM(amount), 0) FROM deals WHERE {} "
                "AND close_date BETWEEN ? AND ?".format(OPEN_STAGES_SQL),
                (start.isoformat(), end.isoformat()),
            )
        return self._scalar(
            scope, "SELECT COALESCE(SUM(amount), 0) FROM deals WHERE {}".format(OPEN_STAGES_SQL))

    def bookings(self, scope: Scope, start: date, end: date) -> float:
        return self._scalar(
            scope,
            "SELECT COALESCE(SUM(amount), 0) FROM deals WHERE {} "
            "AND close_date BETWEEN ? AND ?".format(WON_SQL),
            (start.isoformat(), end.isoformat()),
        )

    def win_rate(self, scope: Scope, start: date, end: date) -> Optional[float]:
        """Revenue-weighted by default, per the semantic layer's metric rules."""
        with self.db.reader(scope) as conn:
            row = conn.execute(
                """
                SELECT
                  COALESCE(SUM(CASE WHEN stage = 'Stage 5 - Closed Won' THEN amount END), 0) AS won,
                  COALESCE(SUM(amount), 0) AS closed
                FROM deals
                WHERE {} AND close_date BETWEEN ? AND ?
                """.format(CLOSED_SQL),
                (start.isoformat(), end.isoformat()),
            ).fetchone()
        if not row or not row["closed"]:
            return None
        return 100.0 * float(row["won"]) / float(row["closed"])

    def open_deal_count(self, scope: Scope) -> float:
        return self._scalar(
            scope, "SELECT COUNT(*) FROM deals WHERE {}".format(OPEN_STAGES_SQL))

    def avg_deal_size(self, scope: Scope) -> Optional[float]:
        value = self._scalar(
            scope, "SELECT COALESCE(AVG(amount), 0) FROM deals WHERE {}".format(OPEN_STAGES_SQL))
        return value or None

    def sales_cycle_days(self, scope: Scope) -> Optional[float]:
        value = self._scalar(
            scope,
            "SELECT COALESCE(AVG(julianday(close_date) - julianday(created_date)), 0) "
            "FROM deals WHERE {}".format(WON_SQL),
        )
        return value or None

    def quota_attainment(self, scope: Scope, start: date, end: date) -> Optional[float]:
        target = self.targets.sum_for_users(scope.user_ids or [], start, end)
        if not target:
            return None
        return 100.0 * self.bookings(scope, start, end) / target

    def coverage(self, scope: Scope, start: date, end: date) -> Optional[float]:
        """Open pipeline over *remaining* target.

        Undefined once the target is already met -- dividing by a near-zero
        remainder produces a meaningless four-digit multiple, so return None and
        let the caller say "target met" instead.
        """
        target = self.targets.sum_for_users(scope.user_ids or [], start, end)
        if not target:
            return None
        remaining = target - self.bookings(scope, start, end)
        if remaining <= target * 0.02:
            return None
        return self.open_pipeline(scope, start, end) / remaining

    def pipeline_generation_trend(self, scope: Scope, months: int = 6) -> List[float]:
        with self.db.reader(scope) as conn:
            rows = conn.execute(
                """
                SELECT strftime('%Y-%m', created_date) AS m, COALESCE(SUM(amount), 0) AS v
                FROM deals GROUP BY m ORDER BY m
                """
            ).fetchall()
        return [float(r["v"]) for r in rows][-months:]

    def bookings_trend(self, scope: Scope, months: int = 6) -> List[float]:
        with self.db.reader(scope) as conn:
            rows = conn.execute(
                """
                SELECT strftime('%Y-%m', close_date) AS m, COALESCE(SUM(amount), 0) AS v
                FROM deals WHERE {} GROUP BY m ORDER BY m
                """.format(WON_SQL)
            ).fetchall()
        return [float(r["v"]) for r in rows][-months:]

    # -- KPI tiles ---------------------------------------------------------------------

    def kpi(self, key: str, scope: Scope, as_of: date) -> Metric:
        q_start, q_end = quarter_bounds(as_of)
        y_start, y_end = ytd_bounds(as_of)
        label_q = quarter_label(as_of)

        if key.endswith("open_pipeline"):
            value = self.open_pipeline(scope, q_start, q_end)
            return Metric(
                key, "Open pipeline", value, "$",
                caption="closing in {}".format(label_q),
                calculation="Sum of amount for deals not Closed Won or Closed Lost, "
                            "with close date in {}.".format(label_q),
                sparkline=self.pipeline_generation_trend(scope),
            )

        if key.endswith("bookings_qtd"):
            value = self.bookings(scope, q_start, as_of)
            return Metric(
                key, "Bookings QTD", value, "$",
                caption="closed won in {}".format(label_q),
                calculation="Sum of amount for Closed Won deals with close date "
                            "between {} and {}.".format(q_start, as_of),
                sparkline=self.bookings_trend(scope),
            )

        if key.endswith("quota_attainment"):
            value = self.quota_attainment(scope, q_start, q_end)
            target = self.targets.sum_for_users(scope.user_ids or [], q_start, q_end)
            return Metric(
                key, "Quota attainment", value, "%",
                caption="of {} target".format(label_q),
                calculation="Closed Won bookings this quarter divided by the quarter's "
                            "target ({:,.0f}) from the targets table.".format(target),
            )

        if key.endswith("win_rate"):
            value = self.win_rate(scope, y_start, y_end)
            return Metric(
                key, "Win rate", value, "%",
                caption="revenue-weighted, YTD",
                calculation="Closed Won amount divided by all closed amount, "
                            "year to date. Revenue-weighted per the semantic layer.",
            )

        if key.endswith("coverage"):
            value = self.coverage(scope, q_start, q_end)
            return Metric(
                key, "Pipeline coverage", value, "x",
                caption="open pipeline vs remaining target",
                calculation="Open pipeline closing this quarter divided by the "
                            "quarter's remaining target.",
            )

        value = self.open_deal_count(scope)
        return Metric(key, "Open deals", value, "#", caption="currently in progress",
                      calculation="Count of deals not Closed Won or Closed Lost.")

    def summary(self, scope: Scope, as_of: date) -> Dict[str, float]:
        q_start, q_end = quarter_bounds(as_of)
        return {
            "open_pipeline": self.open_pipeline(scope, q_start, q_end),
            "bookings_qtd": self.bookings(scope, q_start, as_of),
            "open_deals": self.open_deal_count(scope),
            "avg_deal_size": self.avg_deal_size(scope) or 0.0,
            "win_rate": self.win_rate(scope, *ytd_bounds(as_of)) or 0.0,
            "coverage": self.coverage(scope, q_start, q_end) or 0.0,
            "attainment": self.quota_attainment(scope, q_start, q_end) or 0.0,
        }
