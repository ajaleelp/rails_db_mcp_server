"""Schema parser for Rails db/schema.rb files."""

from __future__ import annotations

from pathlib import Path
import re
from typing import Dict, List, Any


class SchemaParser:
    """Parse Rails schema.rb into structured metadata."""

    _CREATE_TABLE_RE = re.compile(r'create_table\s+"(?P<table>[^"]+)"(?P<options>.*) do \|(?P<var>\w+)\|')
    _ADD_INDEX_RE = re.compile(r'add_index\s+"(?P<table>[^"]+)",\s*(?P<columns>\[[^\]]+\]|:[\w_]+|"[^"]+")(?P<rest>.*)')
    _ADD_FOREIGN_KEY_RE = re.compile(r'add_foreign_key\s+"(?P<from>[^"]+)",\s+"(?P<to>[^"]+)"(?P<rest>.*)')
    _INLINE_INDEX_RE = re.compile(r'\.(?:index)\s+(?P<columns>\[[^\]]+\]|:[\w_]+|"[^"]+")(?P<rest>.*)')

    def __init__(self, schema_path: Path) -> None:
        self.schema_path = schema_path
        self.tables: Dict[str, Dict[str, Any]] = self._parse()

    def _parse(self) -> Dict[str, Dict[str, Any]]:
        content = self.schema_path.read_text()
        lines = content.splitlines()
        tables: Dict[str, Dict[str, Any]] = {}
        i = 0
        while i < len(lines):
            line = lines[i]
            stripped = line.strip()
            if stripped.startswith('create_table'):
                block_lines, next_index = self._collect_block(lines, i)
                table_name, metadata = self._parse_create_table_block(block_lines)
                tables[table_name] = metadata
                i = next_index
                continue
            i += 1
        # add indexes after tables collected
        for line in lines:
            stripped = line.strip()
            if stripped.startswith('add_index'):
                self._apply_add_index_line(stripped, tables)
            elif stripped.startswith('add_foreign_key'):
                self._apply_add_foreign_key_line(stripped, tables)
        return tables

    def _collect_block(self, lines: List[str], start: int) -> tuple[List[str], int]:
        block = [lines[start]]
        depth = 1
        i = start + 1
        while i < len(lines) and depth > 0:
            current = lines[i]
            block.append(current)
            stripped = current.strip()
            if stripped.endswith('do'):
                depth += 1
            if stripped == 'end':
                depth -= 1
            i += 1
        return block, i

    def _parse_create_table_block(self, block_lines: List[str]) -> tuple[str, Dict[str, Any]]:
        header = block_lines[0].strip()
        header_match = self._CREATE_TABLE_RE.search(header)
        if not header_match:
            raise ValueError(f"Unable to parse create_table header: {header}")
        table_name = header_match.group('table')
        options = header_match.group('options') or ''
        primary_key = self._extract_primary_key(options)
        columns: List[str] = []
        indexes: Dict[str, List[str]] = {}
        block_body = block_lines[1:-1]
        for line in block_body:
            stripped = line.strip()
            if not stripped:
                continue
            if self._is_timestamp_declaration(stripped):
                self._ensure_timestamp_columns(columns)
                continue
            column = self._extract_column_name(stripped)
            if column and column not in columns:
                columns.append(column)
                continue
            index_data = self._extract_inline_index(stripped, table_name)
            if index_data:
                name, cols = index_data
                indexes[name] = cols
        if primary_key and primary_key not in columns:
            columns.insert(0, primary_key)
        if primary_key:
            indexes.setdefault('PRIMARY', [primary_key])
        return table_name, {
            'columns': columns,
            'indexes': indexes,
            'primary_key': primary_key,
            'foreign_keys': [],
        }

    def _extract_primary_key(self, options: str) -> str | None:
        pk_match = re.search(r'primary_key:\s*"(?P<pk>[^"]+)"', options)
        if pk_match:
            return pk_match.group('pk')
        if 'id: false' in options or 'id:false' in options:
            return None
        return 'id'

    def _extract_column_name(self, line: str) -> str | None:
        column_match = re.match(r'\w+\.(?!index)(?!timestamps)(\w+)\s+"(?P<name>[^"]+)"', line)
        if column_match:
            return column_match.group('name')
        return None

    def _is_timestamp_declaration(self, line: str) -> bool:
        return bool(re.match(r'\w+\.timestamps', line))

    def _ensure_timestamp_columns(self, columns: List[str]) -> None:
        for col in ('created_at', 'updated_at'):
            if col not in columns:
                columns.append(col)

    def _extract_inline_index(self, line: str, table_name: str) -> tuple[str, List[str]] | None:
        match = self._INLINE_INDEX_RE.search(line)
        if not match:
            return None
        columns = self._parse_columns(match.group('columns'))
        name_match = re.search(r'name:\s*"(?P<name>[^"]+)"', match.group('rest'))
        name = name_match.group('name') if name_match else self._default_index_name(table_name, columns)
        return name, columns

    def _apply_add_index_line(self, line: str, tables: Dict[str, Dict[str, Any]]) -> None:
        match = self._ADD_INDEX_RE.match(line)
        if not match:
            return
        table = match.group('table')
        columns = self._parse_columns(match.group('columns'))
        rest = match.group('rest')
        name_match = re.search(r'name:\s*"(?P<name>[^"]+)"', rest)
        name = name_match.group('name') if name_match else self._default_index_name(table, columns)
        table_entry = tables.setdefault(table, {'columns': [], 'indexes': {}, 'primary_key': None})
        table_entry['indexes'][name] = columns

    def _apply_add_foreign_key_line(self, line: str, tables: Dict[str, Dict[str, Any]]) -> None:
        match = self._ADD_FOREIGN_KEY_RE.match(line)
        if not match:
            return
        from_table = match.group('from')
        to_table = match.group('to')
        rest = match.group('rest') or ''
        name_match = re.search(r'name:\s*"(?P<name>[^"]+)"', rest)
        column_match = re.search(r'column:\s*"(?P<column>[^"]+)"', rest)
        pk_match = re.search(r'primary_key:\s*"(?P<pk>[^"]+)"', rest)

        entry = {
            'to_table': to_table,
            'column': column_match.group('column') if column_match else None,
            'primary_key': pk_match.group('pk') if pk_match else 'id',
            'name': name_match.group('name') if name_match else None,
        }
        table_entry = tables.setdefault(from_table, {'columns': [], 'indexes': {}, 'primary_key': 'id', 'foreign_keys': []})
        table_entry.setdefault('foreign_keys', []).append(entry)

    def _parse_columns(self, raw: str) -> List[str]:
        raw = raw.strip()
        if raw.startswith('[') and raw.endswith(']'):
            inner = raw[1:-1]
            return [part.strip().strip('"').strip(':') for part in inner.split(',') if part.strip()]
        cleaned = raw.strip('"')
        if cleaned.startswith(':'):
            cleaned = cleaned[1:]
        return [cleaned]

    def _default_index_name(self, table: str, columns: List[str]) -> str:
        suffix = '_and_'.join(columns)
        return f"index_{table}_on_{suffix}"

    def format_for_display(self) -> str:
        """Return JSON-like string for MCP schema resource."""
        import json
        return json.dumps(self.tables, indent=2, sort_keys=True)

    def get_indexed_columns(self, table: str) -> List[str]:
        table_data = self.tables.get(table)
        if not table_data:
            return []
        seen: List[str] = []
        for cols in table_data['indexes'].values():
            for col in cols:
                if col not in seen:
                    seen.append(col)
        return seen
