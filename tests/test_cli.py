"""Integration tests for the Typer CLI entrypoint."""

from __future__ import annotations

from pathlib import Path
from unittest.mock import ANY

from pytest_mock import MockerFixture
from typer.testing import CliRunner

from contextctl import __version__
from contextctl.cli import app
from contextctl.store import StoreSyncError


def _prepare_repo_files(central_repo: str = "https://example.com/promptlib.git") -> None:
    Path(".git").mkdir()
    Path(".promptlib.yml").write_text(f"central_repo: {central_repo}\n", encoding="utf-8")


def test_version_command_triggers_sync(mocker: MockerFixture) -> None:
    """Running `contextctl version` should load config and sync the store."""
    runner = CliRunner()
    with runner.isolated_filesystem():
        _prepare_repo_files()
        sync_mock = mocker.patch("contextctl.cli.sync_central_repo", return_value=Path("/tmp/store"))

        result = runner.invoke(app, ["version"], catch_exceptions=False)

        assert result.exit_code == 0
        assert __version__ in result.stdout
        sync_mock.assert_called_once_with(
            "https://example.com/promptlib.git",
            promptlib_config=ANY,
            console=ANY,
        )


def test_cli_reports_missing_repo_configuration() -> None:
    """Missing `.promptlib.yml` should yield a friendly error."""
    runner = CliRunner()
    with runner.isolated_filesystem():
        Path(".git").mkdir()

        result = runner.invoke(app, ["version"], catch_exceptions=False)

        assert result.exit_code == 1
        assert "Missing .promptlib.yml" in result.stdout


def test_cli_respects_no_sync_flag(mocker: MockerFixture) -> None:
    """The --no-sync flag should skip git operations."""
    runner = CliRunner()
    with runner.isolated_filesystem():
        _prepare_repo_files()
        sync_mock = mocker.patch("contextctl.cli.sync_central_repo")

        result = runner.invoke(app, ["--no-sync", "version"], catch_exceptions=False)

        assert result.exit_code == 0
        sync_mock.assert_not_called()


def test_cli_surfaces_sync_errors(mocker: MockerFixture) -> None:
    """Sync failures should be surfaced as styled error messages."""
    runner = CliRunner()
    with runner.isolated_filesystem():
        _prepare_repo_files()
        mocker.patch("contextctl.cli.sync_central_repo", side_effect=StoreSyncError("network failure"))

        result = runner.invoke(app, ["version"], catch_exceptions=False)

        assert result.exit_code == 1
        assert "network failure" in result.stdout


def test_cli_rejects_conflicting_sync_flags() -> None:
    """--force-sync and --no-sync should not be allowed together."""
    runner = CliRunner()
    with runner.isolated_filesystem():
        _prepare_repo_files()

        result = runner.invoke(app, ["--no-sync", "--force-sync", "version"], catch_exceptions=False)

        assert result.exit_code != 0
        assert "cannot be combined" in result.stderr
