"""Deterministic filters -- no LLM call, ever.

A filter wraps the saved SQL in a CTE and appends a fully parameterized predicate:

    WITH __insight_base AS ( <saved sql> )
    SELECT * FROM __insight_base WHERE "col" <op> ?

Safety comes from three rules, all enforced here:
  * the column must be one the engine itself reported (from ``cursor.description``),
    compared by exact string equality -- never a constructed pattern;
  * the operator comes from a closed enum;
  * every value is a bound parameter, so a value like ``'; DROP TABLE deals --``
    is just a string that matches nothing.

Known limitation, surfaced honestly in the UI: a filter can only reference a column
present in the result set. Filtering on something the query does not select requires
"Edit with AI" -- we do not rewrite the base query's WHERE clause with regex.
"""

from __future__ import annotations

from typing import Any, List, Optional, Sequence, Tuple

from intellia.models.insight import FilterSpec
from intellia.utils.errors import SqlSafetyError

BASE_CTE = "__insight_base"

# op -> (sql template using {col}, number of bound params or -1 for variable)
OPERATORS = {
    "eq": ("{col} = ?", 1),
    "ne": ("{col} != ?", 1),
    "gt": ("{col} > ?", 1),
    "gte": ("{col} >= ?", 1),
    "lt": ("{col} < ?", 1),
    "lte": ("{col} <= ?", 1),
    "in": ("{col} IN ({ph})", -1),
    "not_in": ("{col} NOT IN ({ph})", -1),
    "between": ("{col} BETWEEN ? AND ?", 2),
    "contains": ("{col} LIKE ? ESCAPE '\\'", 1),
    "starts_with": ("{col} LIKE ? ESCAPE '\\'", 1),
    "is_null": ("{col} IS NULL", 0),
    "not_null": ("{col} IS NOT NULL", 0),
}

OPERATOR_LABELS = {
    "eq": "is", "ne": "is not", "gt": "greater than", "gte": "at least",
    "lt": "less than", "lte": "at most", "in": "is one of", "not_in": "is not one of",
    "between": "between", "contains": "contains", "starts_with": "starts with",
    "is_null": "is empty", "not_null": "is not empty",
}


def _escape_like(value: str) -> str:
    return str(value).replace("\\", "\\\\").replace("%", "\\%").replace("_", "\\_")


def _quote_identifier(name: str) -> str:
    # Only reached after an exact-match check against engine-reported columns.
    return '"{}"'.format(name.replace('"', '""'))


def compile_filters(filters: Sequence[FilterSpec],
                    legal_columns: Sequence[str]) -> Tuple[str, List[Any]]:
    """Return (where_clause_without_WHERE, bound_params)."""
    clauses: List[str] = []
    params: List[Any] = []
    legal = list(legal_columns)

    for spec in filters:
        if spec.column not in legal:
            raise SqlSafetyError(
                "This insight cannot filter on \"{}\", because that column is not in its "
                "results. Use Edit with AI to add it.".format(spec.column),
                detail="column not in result set", code="filter_column")

        if spec.op not in OPERATORS:
            raise SqlSafetyError("Unsupported filter operation.",
                                 detail=spec.op, code="filter_op")

        template, arity = OPERATORS[spec.op]
        column = _quote_identifier(spec.column)
        values = list(spec.values or [])

        if arity == 0:
            clauses.append(template.format(col=column))
            continue

        if arity == -1:
            if not values:
                continue
            placeholders = ", ".join("?" for _ in values)
            clauses.append(template.format(col=column, ph=placeholders))
            params.extend(values)
            continue

        if len(values) < arity:
            continue

        if spec.op == "contains":
            params.append("%{}%".format(_escape_like(values[0])))
        elif spec.op == "starts_with":
            params.append("{}%".format(_escape_like(values[0])))
        else:
            params.extend(values[:arity])
        clauses.append(template.format(col=column))

    return " AND ".join(clauses), params


def wrap(base_sql: str, filters: Sequence[FilterSpec],
         legal_columns: Sequence[str],
         limit: Optional[int] = None) -> Tuple[str, List[Any]]:
    """Wrap saved SQL in a CTE with parameterized post-filters applied."""
    where, params = compile_filters(filters, legal_columns)
    sql = "WITH {cte} AS (\n{base}\n) SELECT * FROM {cte}".format(
        cte=BASE_CTE, base=base_sql.rstrip().rstrip(";"))
    if where:
        sql += "\nWHERE " + where
    if limit:
        sql += "\nLIMIT {:d}".format(int(limit))
    return sql, params


def describe(spec: FilterSpec) -> str:
    label = OPERATOR_LABELS.get(spec.op, spec.op)
    if spec.op in ("is_null", "not_null"):
        return "{} {}".format(spec.column, label)
    values = ", ".join(str(v) for v in (spec.values or []))
    return "{} {} {}".format(spec.column, label, values)
