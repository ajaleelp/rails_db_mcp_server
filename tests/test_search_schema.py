from pathlib import Path

import pytest

from rails_mcp_server.config_loader import MCPConfig
from rails_mcp_server.schema_parser import SchemaParser
from rails_mcp_server.query_validator import QueryValidator, ValidationError
from rails_mcp_server.rate_limiter import RateLimiter
from rails_mcp_server.data_masker import DataMasker
from rails_mcp_server.server import AppComponents, RailsMCPServer


def build_server() -> RailsMCPServer:
    fixtures = Path(__file__).parent / "fixtures"
    schema_parser = SchemaParser(fixtures / "schema_rails_7.rb")
    config = MCPConfig.from_dict({})
    components = AppComponents(
        schema_parser=schema_parser,
        config=config,
        validator=QueryValidator(schema_parser, config),
        executor=None,  # not used by search
        masker=DataMasker(config),
        rate_limiter=RateLimiter(30),
    )
    return RailsMCPServer(components)


def test_search_schema_matches_table_and_columns() -> None:
    server = build_server()
    result = server.search_schema("users")
    assert result["match_count"] >= 1
    assert any(match["table_name"] == "users" for match in result["matches"])

    column_result = server.search_schema("email")
    assert any("email" in match["matching_columns"] or "email" in match["all_columns"] for match in column_result["matches"])
    assert "foreign_keys" in column_result["matches"][0]


def test_search_schema_requires_keyword() -> None:
    server = build_server()
    with pytest.raises(ValidationError):
        server.search_schema("   ")
