"""Data masking utilities."""

from __future__ import annotations

from fnmatch import fnmatch
from typing import Any, Dict, Iterable, List, Optional

from .config_loader import MCPConfig


class DataMasker:
    """Apply masking rules based on config."""

    REDACTED_VALUE = "[REDACTED]"

    def __init__(self, config: MCPConfig) -> None:
        self.config = config
        self._masking_rules = list(config.masking_rules.items())
        self._sensitive_fields = {
            table: {column.lower() for column in columns}
            for table, columns in config.sensitive_fields.items()
        }

    def mask(self, rows: List[Dict[str, Any]], table_name: str) -> List[Dict[str, Any]]:
        allowed_columns = self.config.return_columns.get(table_name)
        masked_rows: List[Dict[str, Any]] = []
        for row in rows:
            filtered_row = self._filter_columns(row, allowed_columns)
            masked_rows.append(self._mask_row(filtered_row, table_name))
        return masked_rows

    def _filter_columns(self, row: Dict[str, Any], allowed: Optional[Iterable[str]]) -> Dict[str, Any]:
        if not allowed:
            return dict(row)
        allowed_set = set(allowed)
        return {key: value for key, value in row.items() if key in allowed_set}

    def _mask_row(self, row: Dict[str, Any], table_name: str) -> Dict[str, Any]:
        masked: Dict[str, Any] = {}
        for column, value in row.items():
            strategy = self._resolve_strategy(table_name, column)
            masked[column] = self._apply_strategy(strategy, value) if strategy else value
        return masked

    def _resolve_strategy(self, table_name: str, column: str) -> Optional[str]:
        column_lc = column.lower()
        table_sensitive = self._sensitive_fields.get(table_name, set())
        is_sensitive = column_lc in table_sensitive
        is_sensitive = is_sensitive or self._matches_global_pattern(column)

        explicit_strategy = self._match_masking_rule(column)
        if explicit_strategy:
            return explicit_strategy
        if is_sensitive:
            return "redact"
        return None

    def _matches_global_pattern(self, column: str) -> bool:
        column_lc = column.lower()
        for pattern in self.config.compiled_sensitive_patterns:
            if pattern.match(column_lc):
                return True
        return False

    def _match_masking_rule(self, column: str) -> Optional[str]:
        for pattern, strategy in self._masking_rules:
            if fnmatch(column.lower(), pattern.lower()):
                return strategy
        return None

    def _apply_strategy(self, strategy: str, value: Any) -> Any:
        if value is None:
            return None
        if strategy == "redact":
            return self.REDACTED_VALUE
        if strategy == "partial":
            return self._partial_mask(value)
        return value

    def _partial_mask(self, value: Any) -> Any:
        text = str(value)
        if "@" in text:
            local, domain = text.split("@", 1)
            if not local:
                return f"***@{domain}"
            return f"{local[0]}***@{domain}"
        if len(text) <= 1:
            return "*"
        return f"{text[0]}***"
