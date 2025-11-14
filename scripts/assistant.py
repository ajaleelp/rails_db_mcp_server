#!/usr/bin/env python3
"""Terminal REPL that lets Claude call local MCP tools."""

from __future__ import annotations

import json
import os
from pathlib import Path
from typing import Any, Dict, List
import itertools
import sys
import threading
import time

from anthropic import Anthropic

from rails_mcp_server.config_loader import ConfigLoader
from rails_mcp_server.data_masker import DataMasker
from rails_mcp_server.query_executor import QueryExecutor, QueryExecutionError
from rails_mcp_server.query_validator import QueryValidator, ValidationError
from rails_mcp_server.rate_limiter import RateLimiter, RateLimitExceeded
from rails_mcp_server.schema_parser import SchemaParser
from rails_mcp_server.server import AppComponents, RailsMCPServer
from rails_mcp_server.server import _make_json_safe

SYSTEM_PROMPT = (
    "You are a database assistant. Always inspect the schema via the search_schema tool before "
    "querying unfamiliar tables. Use fetch_records only with indexed columns."
)
DEFAULT_MODEL = os.environ.get("CLAUDE_MODEL", "claude-3-5-sonnet-20240620")


def build_server(schema_path: Path, config_path: Path, database_url: str) -> RailsMCPServer:
    schema_parser = SchemaParser(schema_path)
    config = ConfigLoader(config_path).load()
    components = AppComponents(
        schema_parser=schema_parser,
        config=config,
        validator=QueryValidator(schema_parser, config),
        executor=QueryExecutor(database_url),
        masker=DataMasker(config),
        rate_limiter=RateLimiter(config.rate_limit.requests_per_minute),
    )
    return RailsMCPServer(components)


def get_tools(server: RailsMCPServer) -> List[Dict[str, Any]]:
    return [
        {
            "name": "fetch_records",
            "description": "Fetch records using indexed columns only",
            "input_schema": server.list_tools()[0]["input_schema"],
        },
        {
            "name": "search_schema",
            "description": "Search schema tables/columns by keyword",
            "input_schema": {
                "type": "object",
                "properties": {
                    "keyword": {"type": "string"},
                    "limit": {"type": "integer", "default": 10, "minimum": 1, "maximum": 100},
                },
                "required": ["keyword"],
            },
        },
    ]


def execute_tool(server: RailsMCPServer, name: str, args: Dict[str, Any]) -> Dict[str, Any]:
    try:
        if name == "fetch_records":
            return server.fetch_records(args)
        if name == "search_schema":
            keyword = args.get("keyword", "")
            limit = int(args.get("limit", 10))
            return server.search_schema(keyword, limit)
        raise ValueError(f"Unknown tool '{name}'")
    except ValidationError as exc:
        return {"error": exc.code, "message": exc.message, "details": exc.details}
    except RateLimitExceeded as exc:
        return {"error": "rate_limit", "message": str(exc)}
    except QueryExecutionError as exc:
        return {"error": "query_failed", "message": str(exc)}


class Spinner:
    def __init__(self, message: str = "Analyzing"):
        self.message = message
        self._stop = threading.Event()
        self._thread = threading.Thread(target=self._run, daemon=True)

    def __enter__(self):
        self._thread.start()
        return self

    def __exit__(self, exc_type, exc, tb):
        self._stop.set()
        self._thread.join()
        sys.stdout.write("\r" + " " * (len(self.message) + 4) + "\r")
        sys.stdout.flush()

    def _run(self):
        for frame in itertools.cycle("|/-\\"):
            if self._stop.is_set():
                break
            sys.stdout.write(f"\r{self.message} {frame}")
            sys.stdout.flush()
            time.sleep(0.1)


def format_tool_summary(name: str, result: Dict[str, Any]) -> str:
    if "error" in result:
        return f"[{name}] error: {result['error']} - {result.get('message', '')}"
    if name == "fetch_records":
        count = result.get("count")
        return f"[{name}] returned {count} record(s)"
    if name == "search_schema":
        matches = result.get("match_count")
        return f"[{name}] found {matches} match(es)"
    return f"[{name}] completed"


def main() -> None:
    required_env = ["SCHEMA_PATH", "DATABASE_URL", "ANTHROPIC_API_KEY"]
    missing = [var for var in required_env if not os.environ.get(var)]
    if missing:
        raise SystemExit(f"Missing required env vars: {', '.join(missing)}")

    schema_path = Path(os.environ["SCHEMA_PATH"])
    config_path = Path(os.environ.get("MCP_CONFIG_PATH", schema_path.parent / "mcp_config.yml"))
    database_url = os.environ["DATABASE_URL"]

    server = build_server(schema_path, config_path, database_url)
    tools = get_tools(server)

    client = Anthropic()
    history: List[Dict[str, Any]] = []

    print("Assistant ready. Type 'quit' to exit.")
    while True:
        try:
            prompt = input("You> ").strip()
        except (EOFError, KeyboardInterrupt):
            print("\nBye!")
            break
        if not prompt:
            continue
        if prompt.lower() in {"quit", "exit"}:
            print("Bye!")
            break

        history.append({"role": "user", "content": prompt})

        while True:
            with Spinner():
                response = client.messages.create(
                    model=DEFAULT_MODEL,
                    system=SYSTEM_PROMPT,
                    messages=history,
                    tools=tools,
                    max_tokens=800,
                    temperature=0.1,
                )

            assistant_blocks: List[Dict[str, Any]] = []
            tool_results: List[tuple[str, str]] = []

            for block in response.content:
                if block.type == "text":
                    print(f"Claude> {block.text}")
                    assistant_blocks.append({"type": "text", "text": block.text})
                elif block.type == "tool_use":
                    assistant_blocks.append(
                        {
                            "type": "tool_use",
                            "id": block.id,
                            "name": block.name,
                            "input": block.input,
                        }
                    )
                    result = execute_tool(server, block.name, block.input)
                    serialized = json.dumps(_make_json_safe(result), indent=2)
                    print(format_tool_summary(block.name, result))
                    tool_results.append((block.id, serialized))

            if assistant_blocks:
                history.append({"role": "assistant", "content": assistant_blocks})

            if not tool_results:
                break

            for tool_use_id, serialized in tool_results:
                history.append(
                    {
                        "role": "user",
                        "content": [
                            {
                                "type": "tool_result",
                                "tool_use_id": tool_use_id,
                                "content": [
                                    {
                                        "type": "text",
                                        "text": serialized,
                                    }
                                ],
                            }
                        ],
                    }
                )


if __name__ == "__main__":
    main()
