"""CLI entry point for the Rails MCP server."""

from __future__ import annotations

import json
from dataclasses import dataclass
from datetime import date, datetime, time
from decimal import Decimal
from pathlib import Path
from typing import Any, Dict, Optional

import anyio
import click
from mcp.server import NotificationOptions, Server as MCPServer
from mcp.server.lowlevel.helper_types import ReadResourceContents
from mcp.server.stdio import stdio_server
import mcp.types as mcp_types

from . import __version__
from .config_loader import ConfigLoader, MCPConfig
from .data_masker import DataMasker
from .query_builder import build_query
from .query_executor import QueryExecutor, QueryExecutionError
from .query_validator import QueryValidator, ValidationError
from .rate_limiter import RateLimiter, RateLimitExceeded
from .schema_parser import SchemaParser

FETCH_RECORDS_INPUT_SCHEMA = {
    "type": "object",
    "properties": {
        "table_name": {"type": "string"},
        "filters": {"type": "object", "additionalProperties": True},
        "limit": {"type": "integer", "default": 10, "maximum": 100},
        "order_by": {
            "type": "object",
            "properties": {
                "column": {"type": "string"},
                "direction": {"type": "string", "enum": ["asc", "desc"], "default": "asc"},
            },
        },
    },
    "required": ["table_name"],
}


@dataclass
class AppComponents:
    schema_parser: SchemaParser
    config: MCPConfig
    validator: QueryValidator
    executor: QueryExecutor
    masker: DataMasker
    rate_limiter: RateLimiter


class RailsMCPServer:
    """Coordinate validation, execution, masking, and tooling metadata."""

    def __init__(self, components: AppComponents) -> None:
        self.components = components

    def list_resources(self) -> list[dict[str, Any]]:
        return [
            {
                "uri": "schema://database",
                "name": "Database Schema",
                "description": "Rails schema with indexed columns",
                "mimeType": "application/json",
            }
        ]

    def read_resource(self, uri: str) -> str:
        if uri != "schema://database":
            raise ValueError(f"Unknown resource '{uri}'")
        return self.components.schema_parser.format_for_display()

    def list_tools(self) -> list[dict[str, Any]]:
        return [
            {
                "name": "fetch_records",
                "description": "Fetch records using indexed columns only",
                "input_schema": FETCH_RECORDS_INPUT_SCHEMA,
            }
        ]

    def fetch_records(self, payload: Dict[str, Any]) -> Dict[str, Any]:
        self.components.rate_limiter.check_and_record()
        validated = self.components.validator.validate(payload)
        query, params = build_query(
            validated.table_name,
            validated.filters,
            validated.limit,
            validated.order_by,
        )
        rows = self.components.executor.execute(query, params)
        masked = self.components.masker.mask(rows, validated.table_name)
        return {"records": masked, "count": len(masked)}


@click.group(context_settings={"auto_envvar_prefix": "MCP"})
@click.option("--schema-path", type=click.Path(path_type=Path), required=True, help="Path to Rails db/schema.rb")
@click.option("--database-url", envvar="DATABASE_URL", required=True, help="Database connection string")
@click.option(
    "--config-path",
    type=click.Path(path_type=Path),
    help="Optional path to mcp_config.yml (default: alongside schema)",
)
@click.pass_context
def cli(ctx: click.Context, schema_path: Path, database_url: str, config_path: Optional[Path]) -> None:
    """Initialize application components shared across commands."""
    resolved_config = config_path or schema_path.parent / "mcp_config.yml"
    components = _build_components(schema_path, resolved_config, database_url)
    ctx.ensure_object(dict)
    ctx.obj["server"] = RailsMCPServer(components)


@cli.command("list-resources")
@click.pass_context
def list_resources(ctx: click.Context) -> None:
    server: RailsMCPServer = ctx.obj["server"]
    click.echo(_json_dump(server.list_resources()))


@cli.command("read-resource")
@click.option("--uri", default="schema://database", show_default=True)
@click.pass_context
def read_resource(ctx: click.Context, uri: str) -> None:
    server: RailsMCPServer = ctx.obj["server"]
    try:
        content = server.read_resource(uri)
        click.echo(content)
    except ValueError as exc:
        raise click.ClickException(str(exc)) from exc


@cli.command("list-tools")
@click.pass_context
def list_tools(ctx: click.Context) -> None:
    server: RailsMCPServer = ctx.obj["server"]
    click.echo(_json_dump(server.list_tools()))


@cli.command("fetch-records")
@click.option("--table-name", required=True, help="Table name to query")
@click.option("--filters", default="{}", show_default=True, help="JSON object of filters")
@click.option("--limit", type=int, help="Override default limit")
@click.option("--order-by-column", help="Indexed column used for ordering")
@click.option("--order-by-direction", type=click.Choice(["asc", "desc"]), default="asc")
@click.pass_context
def fetch_records(
    ctx: click.Context,
    table_name: str,
    filters: str,
    limit: Optional[int],
    order_by_column: Optional[str],
    order_by_direction: str,
) -> None:
    server: RailsMCPServer = ctx.obj["server"]
    payload = _build_payload(table_name, filters, limit, order_by_column, order_by_direction)
    try:
        response = server.fetch_records(payload)
        click.echo(_json_dump(response))
    except ValidationError as exc:
        _emit_error(exc.to_payload())
    except RateLimitExceeded as exc:
        _emit_error({"error": "rate_limit_exceeded", "message": str(exc)})
    except QueryExecutionError as exc:
        _emit_error({"error": "query_failed", "message": str(exc)})
    except ValueError as exc:
        _emit_error({"error": "invalid_request", "message": str(exc)})


@cli.command("serve")
@click.pass_context
def serve(ctx: click.Context) -> None:
    """Start an MCP stdio server for integrations like Claude Desktop."""
    server: RailsMCPServer = ctx.obj["server"]
    anyio.run(_run_mcp_server, server)


def _emit_error(payload: Dict[str, Any]) -> None:
    click.echo(_json_dump(payload), err=True)
    raise SystemExit(1)


def _build_payload(
    table_name: str,
    filters: str,
    limit: Optional[int],
    order_by_column: Optional[str],
    order_by_direction: str,
) -> Dict[str, Any]:
    try:
        parsed_filters = json.loads(filters)
    except json.JSONDecodeError as exc:
        raise ValueError(f"Failed to parse filters JSON: {exc}") from exc
    if not isinstance(parsed_filters, dict):
        raise ValueError("Filters JSON must serialize to an object")

    payload: Dict[str, Any] = {
        "table_name": table_name,
        "filters": parsed_filters,
    }
    if limit is not None:
        payload["limit"] = limit
    if order_by_column:
        payload["order_by"] = {"column": order_by_column, "direction": order_by_direction}
    return payload


def _build_components(schema_path: Path, config_path: Path, database_url: str) -> AppComponents:
    schema_parser = SchemaParser(schema_path)
    config = ConfigLoader(config_path).load()
    validator = QueryValidator(schema_parser, config)
    executor = QueryExecutor(database_url)
    masker = DataMasker(config)
    rate_limiter = RateLimiter(config.rate_limit.requests_per_minute)
    return AppComponents(
        schema_parser=schema_parser,
        config=config,
        validator=validator,
        executor=executor,
        masker=masker,
        rate_limiter=rate_limiter,
    )


async def _run_mcp_server(app_server: RailsMCPServer) -> None:
    mcp_server = MCPServer(name="rails-db", version=__version__)
    components = app_server.components

    @mcp_server.list_resources()
    async def _list_resources() -> list[mcp_types.Resource]:
        resource = mcp_types.Resource(
            uri="schema://database",
            name="Database Schema",
            description="Rails schema with indexed columns",
            mimeType="application/json",
        )
        return [resource]

    @mcp_server.read_resource()
    async def _read_resource(uri: mcp_types.AnyUrl):
        if str(uri) != "schema://database":
            raise ValueError(f"Unknown resource '{uri}'")
        schema_json = components.schema_parser.format_for_display()
        return [ReadResourceContents(content=schema_json, mime_type="application/json")]

    @mcp_server.list_tools()
    async def _list_tools() -> list[mcp_types.Tool]:
        tool = mcp_types.Tool(
            name="fetch_records",
            description="Fetch records using indexed columns only",
            inputSchema=FETCH_RECORDS_INPUT_SCHEMA,
        )
        return [tool]

    @mcp_server.call_tool()
    async def _call_tool(name: str, arguments: dict[str, Any] | None) -> Dict[str, Any]:
        if name != "fetch_records":
            raise ValueError(f"Unknown tool '{name}'")

        payload = arguments or {}

        def _invoke() -> Dict[str, Any]:
            try:
                return app_server.fetch_records(payload)
            except ValidationError as exc:
                raise ValueError(json.dumps(exc.to_payload()))
            except RateLimitExceeded as exc:
                raise ValueError(str(exc))
            except QueryExecutionError as exc:
                raise ValueError(str(exc))

        result = await anyio.to_thread.run_sync(_invoke)
        return _make_json_safe(result)

    init_options = mcp_server.create_initialization_options(NotificationOptions())
    async with stdio_server() as (read_stream, write_stream):
        await mcp_server.run(read_stream, write_stream, init_options)


def _json_dump(payload: Any) -> str:
    return json.dumps(payload, indent=2, default=_json_default)


def _json_default(value: Any) -> Any:
    if isinstance(value, (datetime, date, time)):
        return value.isoformat()
    if isinstance(value, Decimal):
        return str(value)
    return str(value)


def _make_json_safe(value: Any) -> Any:
    if isinstance(value, dict):
        return {key: _make_json_safe(val) for key, val in value.items()}
    if isinstance(value, list):
        return [_make_json_safe(item) for item in value]
    if isinstance(value, tuple):
        return [_make_json_safe(item) for item in value]
    if isinstance(value, (datetime, date, time)):
        return value.isoformat()
    if isinstance(value, Decimal):
        return str(value)
    return value


main = cli


if __name__ == "__main__":
    main()
