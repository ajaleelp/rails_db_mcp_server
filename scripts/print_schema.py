"""Utility to print parsed schema metadata for a given schema.rb."""

from __future__ import annotations

import argparse
from pathlib import Path
from typing import Any

from rails_mcp_server.schema_parser import SchemaParser


def main() -> None:
    parser = argparse.ArgumentParser(description="Inspect Rails schema metadata")
    parser.add_argument("schema_path", type=Path, help="Path to db/schema.rb")
    parser.add_argument(
        "--table",
        dest="table",
        help="Optional table name to display only that entry",
    )
    args = parser.parse_args()

    schema_parser = SchemaParser(args.schema_path)
    if args.table:
        table = args.table
        tables = schema_parser.tables
        if table not in tables:
            raise SystemExit(f"Table '{table}' not found in schema")
        pretty_print(tables[table])
    else:
        print(schema_parser.format_for_display())


def pretty_print(data: Any) -> None:
    import json

    print(json.dumps(data, indent=2, sort_keys=True))


if __name__ == "__main__":
    main()
