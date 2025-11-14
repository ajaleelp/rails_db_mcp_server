import pytest

from rails_mcp_server.query_builder import build_query


def test_build_query_with_equality_filters() -> None:
    query, params = build_query(
        table="users",
        filters={"id": 123, "status": "active"},
        limit=5,
        order_by=None,
    )
    sql = str(query)
    assert "SELECT * FROM users" in sql
    assert "id =" in sql and "status =" in sql
    assert params["eq_id_1"] == 123
    assert params["eq_status_2"] == "active"
    assert params["limit"] == 5


def test_build_query_with_range_filters_and_ordering() -> None:
    query, params = build_query(
        table="orders",
        filters={"created_at": {"gte": "2024-01-01", "lte": "2024-02-01"}},
        limit=50,
        order_by={"column": "created_at", "direction": "desc"},
    )
    sql = str(query)
    assert "ORDER BY created_at DESC" in sql
    assert params["gte_created_at_1"] == "2024-01-01"
    assert params["lte_created_at_2"] == "2024-02-01"


def test_invalid_identifier_raises() -> None:
    with pytest.raises(ValueError):
        build_query(
            table="users;DROP TABLE",
            filters={"id": 1},
            limit=1,
            order_by=None,
        )
