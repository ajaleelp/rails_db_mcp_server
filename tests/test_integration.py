from pathlib import Path
import sqlite3

from rails_mcp_server.config_loader import MCPConfig
from rails_mcp_server.data_masker import DataMasker
from rails_mcp_server.query_validator import QueryValidator
from rails_mcp_server.rate_limiter import RateLimiter
from rails_mcp_server.schema_parser import SchemaParser
from rails_mcp_server.query_executor import QueryExecutor
from rails_mcp_server.server import AppComponents, RailsMCPServer


FIXTURES = Path(__file__).parent / "fixtures"


def setup_sqlite_db(tmp_path: Path) -> str:
    db_path = tmp_path / "integration.db"
    conn = sqlite3.connect(db_path)
    cursor = conn.cursor()
    cursor.execute(
        """
        CREATE TABLE users (
            id INTEGER PRIMARY KEY,
            email TEXT,
            company_id INTEGER,
            created_at TEXT,
            updated_at TEXT
        );
        """
    )
    cursor.execute(
        "CREATE INDEX index_users_on_company_and_created ON users (company_id, created_at);"
    )
    cursor.execute(
        "INSERT INTO users (email, company_id, created_at, updated_at) VALUES (?, ?, ?, ?)",
        ("user@example.com", 1, "2024-01-01", "2024-01-02"),
    )
    conn.commit()
    conn.close()
    return f"sqlite:///{db_path}"


def build_server(database_url: str) -> RailsMCPServer:
    schema_parser = SchemaParser(FIXTURES / "schema_rails_7.rb")
    config = MCPConfig.from_dict(
        {
            "masking_rules": {"email": "partial"},
            "return_columns": {"users": ["id", "email", "company_id"]},
        }
    )
    validator = QueryValidator(schema_parser, config)
    executor = QueryExecutor(database_url)
    masker = DataMasker(config)
    rate_limiter = RateLimiter(config.rate_limit.requests_per_minute)
    components = AppComponents(
        schema_parser=schema_parser,
        config=config,
        validator=validator,
        executor=executor,
        masker=masker,
        rate_limiter=rate_limiter,
    )
    return RailsMCPServer(components)


def test_end_to_end_fetch_records(tmp_path) -> None:
    database_url = setup_sqlite_db(tmp_path)
    server = build_server(database_url)
    payload = {
        "table_name": "users",
        "filters": {"company_id": 1, "created_at": {"gte": "2023-12-31"}},
        "order_by": {"column": "created_at", "direction": "desc"},
    }
    response = server.fetch_records(payload)
    assert response["count"] == 1
    record = response["records"][0]
    assert record["email"].startswith("u***@example.com")
    assert "name" not in record  # filtered by return_columns
