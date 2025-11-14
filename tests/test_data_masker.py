from rails_mcp_server.config_loader import MCPConfig
from rails_mcp_server.data_masker import DataMasker


def test_masks_email_partially() -> None:
    config = MCPConfig.from_dict({
        "masking_rules": {"email": "partial"},
    })
    masker = DataMasker(config)
    rows = [{"email": "user@example.com", "name": "Sam"}]
    masked = masker.mask(rows, "users")
    assert masked[0]["email"].startswith("u***@example.com")
    assert masked[0]["name"] == "Sam"


def test_default_redaction_for_sensitive_fields() -> None:
    config = MCPConfig.from_dict({
        "sensitive_fields": {"payments": ["credit_card_number"]},
    })
    masker = DataMasker(config)
    rows = [{"credit_card_number": "4111111111111111", "status": "ok"}]
    masked = masker.mask(rows, "payments")
    assert masked[0]["credit_card_number"] == "[REDACTED]"
    assert masked[0]["status"] == "ok"


def test_return_columns_filters_output() -> None:
    config = MCPConfig.from_dict({
        "return_columns": {"users": ["id", "email"]},
        "masking_rules": {"email": "partial"},
    })
    masker = DataMasker(config)
    rows = [{"id": 1, "email": "a@b.com", "name": "Hidden"}]
    masked = masker.mask(rows, "users")
    assert set(masked[0].keys()) == {"id", "email"}
