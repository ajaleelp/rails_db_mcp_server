from pathlib import Path

from rails_mcp_server.config_loader import ConfigLoader, MCPConfig


FIXTURES = Path(__file__).parent / "fixtures"


def test_returns_defaults_when_file_missing(tmp_path) -> None:
    loader = ConfigLoader(tmp_path / "missing.yml")
    config = loader.load()
    assert isinstance(config, MCPConfig)
    assert config.default_limit == 10
    assert config.max_limit == 100
    assert config.rate_limit.requests_per_minute == 30
    assert config.sensitive_patterns  # inherited defaults


def test_merges_user_config_with_defaults() -> None:
    loader = ConfigLoader(FIXTURES / "mcp_config.yml")
    config = loader.load()

    assert config.default_limit == 25  # overridden
    assert config.max_limit == 50
    assert config.rate_limit.requests_per_minute == 10
    assert config.sensitive_fields["users"] == ["email", "phone"]
    # merged patterns should include defaults + custom pattern
    assert any("credit_card" in pattern.pattern for pattern in config.compiled_sensitive_patterns)
    assert "audit_logs" in config.excluded_tables
