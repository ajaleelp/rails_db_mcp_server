# Rails MCP Server

Generic MCP server for safely querying any Rails database via schema-driven validation, PII masking, and rate limiting.

## Features
- Parses `db/schema.rb` to discover tables, columns, primary keys, and explicit indexes (composite order preserved)
- Validates filters so they always match the left-most prefix of an index (range operators supported day one)
- Enforces configurable row limits, read-only connections, request rate limiting, and indexed `ORDER BY`
- Applies config-driven masking rules plus optional per-table column allowlists before returning data
- Exposes a simple CLI that mirrors MCP concepts: list resources, list tools, and call `fetch-records`

## Development Setup
1. Ensure Python 3.10+ is available via `pyenv` or system Python.
2. Install in editable mode with dev extras:
   ```bash
   python -m pip install -e '.[dev]'
   ```
3. (Optional) Inspect any Rails schema:
   ```bash
   python scripts/print_schema.py ../some-app/db/schema.rb --table users
   ```

## CLI Usage
All commands share the same base options:
```
rails-mcp-server \
  --schema-path ./db/schema.rb \
  --database-url postgresql://user:pass@localhost:5432/app_production \
  [--config-path ./config/mcp_config.yml]
```

Example invocations:
- List exposed resources: `rails-mcp-server ... list-resources`
- Display schema metadata: `rails-mcp-server ... read-resource --uri schema://database`
- View available tools: `rails-mcp-server ... list-tools`
- Fetch rows (filters as JSON):
  ```bash
  rails-mcp-server \
    --schema-path ./db/schema.rb \
    --database-url postgresql://example \
    fetch-records \
    --table-name users \
    --filters '{"company_id": 1, "created_at": {"gte": "2024-01-01"}}' \
    --order-by-column created_at \
    --order-by-direction desc
  ```

## Configuration
See `config/mcp_config.example.yml` for supported keys:
- `sensitive_fields` / `sensitive_patterns`: declare columns requiring masking
- `masking_rules`: map field or glob patterns to strategies (`partial`, `redact`)
- `return_columns`: optional allowlist per table
- `excluded_tables`, `default_limit`, `max_limit`, and `rate_limit`
The CLI defaults to `<schema_dir>/mcp_config.yml` when `--config-path` is not supplied.

## Testing
Run the full suite once dependencies are installed:
```bash
python -m pytest
```
Tests cover schema parsing, config loading, query validation/building, masking, rate limiting, and an end-to-end fetch flow backed by SQLite.
