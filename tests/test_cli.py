"""Integration tests for the Typer CLI entrypoint."""

from __future__ import annotations

from pathlib import Path
from textwrap import dedent
from unittest.mock import ANY

import yaml
from pytest_mock import MockerFixture
from typer.testing import CliRunner

from contextctl import __version__
from contextctl.cli import app
from contextctl.store import StoreSyncError


def _prepare_repo_files(central_repo: str = "https://example.com/promptlib.git") -> None:
    Path(".git").mkdir()
    Path(".promptlib.yml").write_text(f"central_repo: {central_repo}\n", encoding="utf-8")


def _create_prompt_store(root: Path) -> Path:
    """Create a simple prompt/rule store on disk."""
    store_root = root / "prompt-store"
    prompt_reviews = store_root / "prompts" / "reviews"
    prompt_incidents = store_root / "prompts" / "incidents"
    rules_python = store_root / "rules" / "python"
    rules_security = store_root / "rules" / "security"
    prompt_reviews.mkdir(parents=True)
    prompt_incidents.mkdir(parents=True)
    rules_python.mkdir(parents=True)
    rules_security.mkdir(parents=True)

    (prompt_reviews / "review-pr.md").write_text(
        dedent(
            """
            ---
            id: review-pr
            tags:
              - reviews
            ---
            Review PR template.
            """
        ).strip(),
        encoding="utf-8",
    )
    (prompt_incidents / "pager-duty.md").write_text(
        dedent(
            """
            ---
            id: pager-duty
            tags:
              - incidents
            ---
            Incident prompt.
            """
        ).strip(),
        encoding="utf-8",
    )
    (rules_python / "style.md").write_text("content", encoding="utf-8")
    (rules_security / "security.md").write_text("content", encoding="utf-8")
    return store_root


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


def test_init_creates_config_with_selected_sets() -> None:
    """The init wizard should write .promptlib.yml using chosen sets."""
    runner = CliRunner()
    with runner.isolated_filesystem():
        Path(".git").mkdir()
        store_root = _create_prompt_store(Path())
        user_input = "\n".join(
            [
                str(store_root),
                "python",
                "reviews",
                "y",
                "",
            ]
        )

        result = runner.invoke(app, ["init"], input=user_input, catch_exceptions=False)

        assert result.exit_code == 0
        config_path = Path(".promptlib.yml")
        assert config_path.exists()
        payload = yaml.safe_load(config_path.read_text(encoding="utf-8"))
        assert payload["central_repo"] == str(store_root)
        assert payload["rules"] == ["python"]
        assert payload["prompt_sets"] == ["reviews"]
        assert "Created .promptlib.yml" in result.stdout


def test_init_requires_git_repository() -> None:
    """Running init outside of a git repo should surface an error."""
    runner = CliRunner()
    with runner.isolated_filesystem():
        result = runner.invoke(app, ["init"], input="prompt-store\n", catch_exceptions=False)

        assert result.exit_code == 1
        assert "Unable to locate a git repository" in result.stdout


def test_init_respects_existing_configuration() -> None:
    """Existing configs should not be overwritten without confirmation."""
    runner = CliRunner()
    with runner.isolated_filesystem():
        _prepare_repo_files()
        original_contents = Path(".promptlib.yml").read_text(encoding="utf-8")

        result = runner.invoke(app, ["init"], input="n\n", catch_exceptions=False)

        assert result.exit_code == 0
        assert Path(".promptlib.yml").read_text(encoding="utf-8") == original_contents
        assert "preserved" in result.stdout
