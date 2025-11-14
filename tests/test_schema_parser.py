from pathlib import Path

from rails_mcp_server.schema_parser import SchemaParser


FIXTURES = Path(__file__).parent / "fixtures"


def test_parses_columns_and_indexes_from_schema_rails_7() -> None:
    parser = SchemaParser(FIXTURES / "schema_rails_7.rb")

    users = parser.tables["users"]
    assert users["primary_key"] == "id"
    assert "email" in users["columns"]
    assert users["indexes"]["index_users_on_email"] == ["email"]
    assert users["indexes"]["index_users_on_company_and_created"] == ["company_id", "created_at"]

    api_keys = parser.tables["api_keys"]
    assert api_keys["primary_key"] == "token"
    assert api_keys["indexes"]["PRIMARY"] == ["token"]
    assert api_keys["indexes"]["index_api_keys_on_user_id"] == ["user_id"]


def test_handles_timestamps_and_id_false_tables() -> None:
    parser = SchemaParser(FIXTURES / "schema_rails_5.rb")

    projects = parser.tables["projects"]
    assert "created_at" in projects["columns"]
    assert "updated_at" in projects["columns"]

    memberships = parser.tables["project_memberships"]
    assert memberships["primary_key"] is None
    assert "PRIMARY" not in memberships["indexes"]
    assert memberships["indexes"]["index_memberships_on_project_and_user"] == ["project_id", "user_id"]
    assert memberships["indexes"]["index_memberships_on_user_and_project"] == ["user_id", "project_id"]


def test_format_for_display_outputs_json() -> None:
    parser = SchemaParser(FIXTURES / "schema_rails_7.rb")
    rendered = parser.format_for_display()
    assert '"users"' in rendered
    assert '"indexes"' in rendered
