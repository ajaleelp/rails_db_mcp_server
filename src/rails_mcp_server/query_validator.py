"""Validation logic for fetch_records requests."""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any, Dict, Iterable, List, Mapping, Optional

from .config_loader import MCPConfig
from .schema_parser import SchemaParser


ALLOWED_RANGE_OPERATORS = {"gte", "gt", "lte", "lt"}


class ValidationError(Exception):
    """Raised when a request payload fails validation."""

    def __init__(self, code: str, message: str, details: Optional[Dict[str, Any]] = None) -> None:
        super().__init__(message)
        self.code = code
        self.message = message
        self.details = details or {}

    def to_payload(self) -> Dict[str, Any]:
        payload = {"error": self.code, "message": self.message}
        if self.details:
            payload.update(self.details)
        return payload


@dataclass
class ValidatedQuery:
    """Container returned on successful validation."""

    table_name: str
    filters: Dict[str, Any]
    limit: int
    order_by: Optional[Dict[str, str]]


class QueryValidator:
    """Validate incoming fetch_records requests against schema + config."""

    def __init__(self, schema_parser: SchemaParser, config: MCPConfig) -> None:
        self.schema_parser = schema_parser
        self.config = config
        self._excluded_tables = {table.lower() for table in config.excluded_tables}

    def validate(self, payload: Mapping[str, Any]) -> ValidatedQuery:
        table_name = payload.get("table_name")
        if not table_name or not isinstance(table_name, str):
            raise ValidationError("table_required", "'table_name' must be provided")

        table_key = table_name
        table_lookup = self.schema_parser.tables.get(table_key)
        if not table_lookup:
            raise ValidationError("unknown_table", f"Table '{table_name}' not found in schema")
        if table_name.lower() in self._excluded_tables:
            raise ValidationError("table_excluded", f"Table '{table_name}' is excluded by configuration")

        filters_raw = payload.get("filters") or {}
        if not isinstance(filters_raw, Mapping):
            raise ValidationError("invalid_filters", "'filters' must be an object")
        if not filters_raw:
            raise ValidationError("missing_filters", "At least one filter using indexed columns is required")

        filter_keys = self._extract_filter_keys(filters_raw)
        self._ensure_columns_exist(table_name, filter_keys)
        matching_index = self._find_matching_index(table_name, filter_keys)
        if not matching_index:
            raise ValidationError(
                "index_required",
                "Filters don't match any index prefix",
                details={
                    "table": table_name,
                    "provided_filters": filter_keys,
                    "available_indexes": self.schema_parser.tables[table_name]["indexes"],
                },
            )

        limit = self._resolve_limit(payload.get("limit"))
        order_by_payload = payload.get("order_by")
        order_by = self._validate_order_by(table_name, order_by_payload) if order_by_payload else None

        return ValidatedQuery(
            table_name=table_name,
            filters=dict(filters_raw),
            limit=limit,
            order_by=order_by,
        )

    def _extract_filter_keys(self, filters: Mapping[str, Any]) -> List[str]:
        keys: List[str] = []
        for key, value in filters.items():
            if not isinstance(key, str):
                raise ValidationError("invalid_filter_key", "Filter keys must be strings")
            if isinstance(value, Mapping):
                if not value:
                    raise ValidationError("invalid_filter_value", f"Filter '{key}' range object cannot be empty")
                for op in value:
                    if op not in ALLOWED_RANGE_OPERATORS:
                        raise ValidationError(
                            "invalid_range_operator",
                            f"Filter '{key}' uses unsupported operator '{op}'",
                        )
                keys.append(key)
                continue
            if isinstance(value, (list, tuple, set)):
                raise ValidationError(
                    "unsupported_filter_value",
                    f"Filter '{key}' uses unsupported value '{type(value).__name__}'",
                )
            keys.append(key)
        return keys

    def _ensure_columns_exist(self, table: str, columns: Iterable[str]) -> None:
        table_columns = set(self.schema_parser.tables[table]["columns"])
        missing = [col for col in columns if col not in table_columns]
        if missing:
            raise ValidationError(
                "unknown_columns",
                f"Columns {missing} are not defined on '{table}'",
                details={"table": table, "columns": missing},
            )

    def _find_matching_index(self, table: str, filter_keys: List[str]) -> Optional[str]:
        indexes = self.schema_parser.tables[table]["indexes"]
        if not indexes:
            return None
        filter_set = set(filter_keys)
        for index_name, index_columns in indexes.items():
            prefix: List[str] = []
            for column in index_columns:
                if column in filter_set:
                    prefix.append(column)
                    continue
                break
            if prefix and filter_set.issubset(prefix):
                return index_name
        return None

    def _resolve_limit(self, requested_limit: Any) -> int:
        limit = self.config.default_limit if requested_limit in (None, "") else int(requested_limit)
        if limit <= 0:
            raise ValidationError("invalid_limit", "Limit must be greater than zero")
        if limit > self.config.max_limit:
            raise ValidationError(
                "limit_exceeded",
                f"Limit {limit} exceeds max_limit {self.config.max_limit}",
                details={"max_limit": self.config.max_limit},
            )
        return limit

    def _validate_order_by(self, table: str, order_payload: Mapping[str, Any]) -> Dict[str, str]:
        column = order_payload.get("column") if isinstance(order_payload, Mapping) else None
        if not column or not isinstance(column, str):
            raise ValidationError("invalid_order_by", "order_by.column must be provided")
        direction = (order_payload.get("direction") or "asc").lower()
        if direction not in {"asc", "desc"}:
            raise ValidationError("invalid_order_by", "order_by.direction must be 'asc' or 'desc'")

        table_columns = set(self.schema_parser.tables[table]["columns"])
        if column not in table_columns:
            raise ValidationError(
                "unknown_order_column",
                f"Column '{column}' does not exist on '{table}'",
            )

        indexed_columns = self.schema_parser.get_indexed_columns(table)
        if column not in indexed_columns:
            raise ValidationError(
                "order_index_required",
                f"Column '{column}' is not indexed and cannot be used for ordering",
            )

        return {"column": column, "direction": direction}
