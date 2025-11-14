"""Database execution layer using SQLAlchemy."""

from __future__ import annotations

from typing import Any, Dict, List

from sqlalchemy import create_engine, text
from sqlalchemy.engine import Engine
from sqlalchemy.engine import Connection
from sqlalchemy.exc import SQLAlchemyError


class QueryExecutionError(Exception):
    """Raised when a SQL query fails to execute."""


class QueryExecutor:
    """Manage DB connections and enforce read-only execution."""

    def __init__(self, database_url: str, statement_timeout_ms: int = 5000) -> None:
        self.engine: Engine = create_engine(database_url, future=True)
        self.statement_timeout_ms = statement_timeout_ms

    def execute(self, query: Any, params: Dict[str, Any]) -> List[Dict[str, Any]]:
        try:
            with self.engine.connect() as conn:
                self._configure_connection(conn)
                result = conn.execute(query, params)
                rows = result.mappings().all()
                return [dict(row) for row in rows]
        except SQLAlchemyError as exc:
            raise QueryExecutionError(str(exc)) from exc

    def _configure_connection(self, conn: Connection) -> None:
        dialect = conn.dialect.name
        if dialect == "postgresql":
            conn.execute(text("SET SESSION CHARACTERISTICS AS TRANSACTION READ ONLY"))
            conn.execute(text("SET LOCAL statement_timeout = :timeout"), {"timeout": f"{self.statement_timeout_ms}ms"})
        elif dialect == "sqlite":
            conn.exec_driver_sql("PRAGMA query_only = ON")
            conn.exec_driver_sql(f"PRAGMA busy_timeout = {self.statement_timeout_ms}")
