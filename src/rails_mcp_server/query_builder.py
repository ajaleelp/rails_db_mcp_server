"""SQL query builder with equality and range support."""

from __future__ import annotations

import re
from typing import Any, Dict, Tuple

from sqlalchemy.sql import text

from .query_validator import ALLOWED_RANGE_OPERATORS

_OPERATOR_SQL = {
    "gte": ">=",
    "gt": ">",
    "lte": "<=",
    "lt": "<",
}

_IDENTIFIER_RE = re.compile(r"^[A-Za-z_][A-Za-z0-9_]*$")


def sanitize_identifier(identifier: str) -> str:
    """Ensure table/column names are safe to include in SQL."""
    if not _IDENTIFIER_RE.match(identifier):
        raise ValueError(f"Invalid identifier '{identifier}'")
    return identifier


def build_query(
    table: str,
    filters: Dict[str, Any],
    limit: int,
    order_by: Dict[str, str] | None,
) -> Tuple[Any, Dict[str, Any]]:
    table_sql = sanitize_identifier(table)
    where_clauses = []
    params: Dict[str, Any] = {}
    param_counter = 0

    for column, value in filters.items():
        column_sql = sanitize_identifier(column)
        if isinstance(value, dict):
            for operator, operand in value.items():
                if operator not in ALLOWED_RANGE_OPERATORS:
                    raise ValueError(f"Unsupported operator '{operator}'")
                param_counter += 1
                param_name = f"{operator}_{column}_{param_counter}"
                where_clauses.append(f"{column_sql} {_OPERATOR_SQL[operator]} :{param_name}")
                params[param_name] = operand
            continue
        param_counter += 1
        param_name = f"eq_{column}_{param_counter}"
        where_clauses.append(f"{column_sql} = :{param_name}")
        params[param_name] = value

    query = f"SELECT * FROM {table_sql}"
    if where_clauses:
        query += " WHERE " + " AND ".join(where_clauses)

    if order_by:
        column = sanitize_identifier(order_by["column"])
        direction = order_by.get("direction", "asc").lower()
        direction_sql = "DESC" if direction == "desc" else "ASC"
        query += f" ORDER BY {column} {direction_sql}"

    query += " LIMIT :limit"
    params["limit"] = limit

    return text(query), params
