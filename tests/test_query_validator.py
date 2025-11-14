from pathlib import Path

import pytest

from rails_mcp_server.config_loader import MCPConfig
from rails_mcp_server.query_validator import QueryValidator, ValidationError
from rails_mcp_server.schema_parser import SchemaParser


FIXTURES = Path(__file__).parent / "fixtures"


def make_validator() -> QueryValidator:
    parser = SchemaParser(FIXTURES / "schema_rails_7.rb")
    config = MCPConfig.from_dict({"max_limit": 50})
    return QueryValidator(parser, config)


def test_validation_succeeds_for_index_prefix() -> None:
    validator = make_validator()
    payload = {
        "table_name": "users",
        "filters": {"company_id": 1, "created_at": {"gte": "2024-01-01"}},
        "limit": 25,
        "order_by": {"column": "created_at", "direction": "desc"},
    }
    validated = validator.validate(payload)
    assert validated.table_name == "users"
    assert validated.limit == 25


def test_validation_fails_for_missing_index_prefix() -> None:
    validator = make_validator()
    payload = {
        "table_name": "users",
        "filters": {"created_at": {"gte": "2024-01-01"}},
    }
    with pytest.raises(ValidationError) as exc:
        validator.validate(payload)
    assert exc.value.code == "index_required"


def test_limit_exceeds_max() -> None:
    validator = make_validator()
    payload = {
        "table_name": "users",
        "filters": {"id": 1},
        "limit": 999,
    }
    with pytest.raises(ValidationError) as exc:
        validator.validate(payload)
    assert exc.value.code == "limit_exceeded"


def test_order_by_requires_index() -> None:
    validator = make_validator()
    payload = {
        "table_name": "users",
        "filters": {"id": 1},
        "order_by": {"column": "name", "direction": "asc"},
    }
    with pytest.raises(ValidationError) as exc:
        validator.validate(payload)
    assert exc.value.code == "order_index_required"
