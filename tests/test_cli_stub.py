from click.testing import CliRunner

from rails_mcp_server.server import cli


def test_cli_help_displays_commands() -> None:
    runner = CliRunner()
    result = runner.invoke(cli, ["--help"])
    assert result.exit_code == 0
    assert "fetch-records" in result.output
