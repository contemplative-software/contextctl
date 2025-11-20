"""Integration tests for the Typer CLI entrypoint."""

from __future__ import annotations

from pathlib import Path
from textwrap import dedent

import yaml
from pytest_mock import MockerFixture
from rich.tree import Tree
from typer.testing import CliRunner

from contextctl import __version__
from contextctl._internal.output.renderers import _populate_tree_branch
from contextctl.cli import app
from contextctl.content import RuleDocument
from contextctl.models import RuleMetadata
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


def _create_rule_store_with_documents(root: Path) -> Path:
    """Create a prompt store populated with rule documents containing metadata."""
    store_root = root / "rule-store"
    python_dir = store_root / "rules" / "python"
    security_dir = store_root / "rules" / "security"
    python_dir.mkdir(parents=True)
    security_dir.mkdir(parents=True)

    (python_dir / "python-style.md").write_text(
        dedent(
            """
            ---
            id: python-style
            tags:
              - python
            repos:
              - contextctl
            agents:
              - cursor
            version: 1.0.0
            ---
            Follow the standard Python style guidelines.
            """
        ).strip(),
        encoding="utf-8",
    )

    (security_dir / "security.md").write_text(
        dedent(
            """
            ---
            id: security
            tags:
              - security
            repos:
              - ops
            agents:
              - claude
            version: 2.3.1
            ---
            Enforce security reviews for every change.
            """
        ).strip(),
        encoding="utf-8",
    )

    return store_root


def _create_prompt_store_with_prompts(root: Path, repo_slug: str) -> Path:
    """Create a prompt store populated with prompts tailored for list/search tests."""
    store_root = root / "prompt-library"
    reviews_dir = store_root / "prompts" / "reviews"
    incidents_dir = store_root / "prompts" / "incidents"
    reviews_dir.mkdir(parents=True)
    incidents_dir.mkdir(parents=True)

    (reviews_dir / "review-pr.md").write_text(
        dedent(
            f"""
            ---
            id: review-pr
            title: Review Pull Requests
            tags:
              - reviews
              - python
            repos:
              - {repo_slug}
            agents:
              - cursor
            version: 0.3.0
            ---
            Provide a detailed pull request review with actionable feedback.
            """
        ).strip(),
        encoding="utf-8",
    )

    (reviews_dir / "global-guidance.md").write_text(
        dedent(
            """
            ---
            id: global-guidance
            title: General Guidance
            tags:
              - general
            repos: []
            agents: []
            version: 0.1.0
            ---
            Use this template for AI requests that apply to every repository.
            """
        ).strip(),
        encoding="utf-8",
    )

    (incidents_dir / "incident-response.md").write_text(
        dedent(
            """
            ---
            id: incident-response
            title: Incident Response
            tags:
              - incidents
            repos:
              - ops
            agents:
              - claude
            version: 0.2.0
            ---
            Use this script to coordinate an incident prompt and capture follow-ups.
            """
        ).strip(),
        encoding="utf-8",
    )

    return store_root


def _create_prompt_store_with_template(root: Path, repo_slug: str) -> Path:
    """Create a prompt store containing a template prompt for run command tests."""
    store_root = root / "prompt-run-store"
    template_dir = store_root / "prompts" / "templates"
    template_dir.mkdir(parents=True)

    (template_dir / "templated.md").write_text(
        dedent(
            f"""
            ---
            id: templated
            title: Templated Prompt
            tags:
              - automation
            repos:
              - {repo_slug}
            agents:
              - cursor
            version: 1.2.3
            ---
            Hello {{{{name}}}}!
            Repo: {{{{repo}}}}
            """
        ).strip(),
        encoding="utf-8",
    )

    return store_root


def _create_combined_store(root: Path, repo_slug: str) -> Path:
    """Create a prompt store containing both prompts and rules for tree tests."""
    store_root = root / "full-store"
    reviews_dir = store_root / "prompts" / "reviews"
    general_dir = store_root / "prompts" / "general"
    python_rules_dir = store_root / "rules" / "python"
    ops_rules_dir = store_root / "rules" / "ops"

    reviews_dir.mkdir(parents=True)
    general_dir.mkdir(parents=True)
    python_rules_dir.mkdir(parents=True)
    ops_rules_dir.mkdir(parents=True)

    (reviews_dir / "review-pr.md").write_text(
        dedent(
            f"""
            ---
            id: review-pr
            title: Review PR
            tags:
              - reviews
            repos:
              - {repo_slug}
            version: 1.0.0
            ---
            Review instructions.
            """
        ).strip(),
        encoding="utf-8",
    )

    (general_dir / "global-guidance.md").write_text(
        dedent(
            """
            ---
            id: global-guidance
            title: Global Guidance
            tags:
              - global
            repos: []
            version: 1.0.0
            ---
            Applies everywhere.
            """
        ).strip(),
        encoding="utf-8",
    )

    (python_rules_dir / "python-style.md").write_text(
        dedent(
            f"""
            ---
            id: python-style
            tags:
              - python
            repos:
              - {repo_slug}
            version: 1.0.0
            ---
            Python style guide.
            """
        ).strip(),
        encoding="utf-8",
    )

    (ops_rules_dir / "ops-checklist.md").write_text(
        dedent(
            """
            ---
            id: ops-checklist
            tags:
              - ops
            repos:
              - ops
            version: 1.0.0
            ---
            Ops checklist.
            """
        ).strip(),
        encoding="utf-8",
    )

    return store_root


def test_version_command_runs_without_preparation(mocker: MockerFixture) -> None:
    """`contextctl version` should display without requiring repo prep."""
    runner = CliRunner()
    with runner.isolated_filesystem():
        sync_mock = mocker.patch("contextctl.cli.sync_central_repo")

        result = runner.invoke(app, ["version"], catch_exceptions=False)

        assert result.exit_code == 0
        assert __version__ in result.stdout
        sync_mock.assert_not_called()


def test_cli_reports_missing_repo_configuration() -> None:
    """Missing `.promptlib.yml` should yield a friendly error."""
    runner = CliRunner()
    with runner.isolated_filesystem():
        Path(".git").mkdir()

        result = runner.invoke(app, ["rules"], catch_exceptions=False)

        assert result.exit_code == 1
        assert "Missing .promptlib.yml" in result.stdout


def test_cli_respects_no_sync_flag(mocker: MockerFixture) -> None:
    """The --no-sync flag should skip git operations."""
    runner = CliRunner()
    with runner.isolated_filesystem():
        Path(".git").mkdir()
        store_path = _create_rule_store_with_documents(Path())
        Path(".promptlib.yml").write_text(
            dedent(
                """
                central_repo: https://example.com/library.git
                rules:
                  - python
                """
            ).strip(),
            encoding="utf-8",
        )
        sync_mock = mocker.patch("contextctl.cli.sync_central_repo")
        mocker.patch("contextctl.cli.get_store_path", return_value=store_path)

        result = runner.invoke(app, ["--no-sync", "rules"], catch_exceptions=False)

        assert result.exit_code == 0
        sync_mock.assert_not_called()


def test_cli_surfaces_sync_errors(mocker: MockerFixture) -> None:
    """Sync failures should be surfaced as styled error messages."""
    runner = CliRunner()
    with runner.isolated_filesystem():
        Path(".git").mkdir()
        Path(".promptlib.yml").write_text(
            dedent(
                """
                central_repo: https://example.com/library.git
                rules:
                  - python
                """
            ).strip(),
            encoding="utf-8",
        )
        mocker.patch("contextctl.cli.sync_central_repo", side_effect=StoreSyncError("network failure"))

        result = runner.invoke(app, ["rules"], catch_exceptions=False)

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


def test_rules_command_merges_rule_sets_in_config_order(mocker: MockerFixture) -> None:
    """`contextctl rules` should load the configured sets and respect their order."""
    runner = CliRunner()
    with runner.isolated_filesystem():
        Path(".git").mkdir()
        store_path = _create_rule_store_with_documents(Path())
        Path(".promptlib.yml").write_text(
            dedent(
                """
                central_repo: https://example.com/library.git
                rules:
                  - security
                  - python
                """
            ).strip(),
            encoding="utf-8",
        )
        mocker.patch("contextctl.cli.sync_central_repo", return_value=store_path)

        result = runner.invoke(app, ["rules"], catch_exceptions=False)

        assert result.exit_code == 0
        assert "Rule Sources" in result.stdout
        security_index = result.stdout.index("# security")
        python_index = result.stdout.index("# python-style")
        assert security_index < python_index
        assert "Enforce security reviews for every change." in result.stdout


def test_rules_command_supports_json_format_and_save(mocker: MockerFixture) -> None:
    """The rules command should emit JSON and persist Cursor files."""
    runner = CliRunner()
    with runner.isolated_filesystem():
        Path(".git").mkdir()
        store_path = _create_rule_store_with_documents(Path())
        Path(".promptlib.yml").write_text(
            dedent(
                """
                central_repo: https://example.com/library.git
                rules:
                  - python-style
                """
            ).strip(),
            encoding="utf-8",
        )
        mocker.patch("contextctl.cli.sync_central_repo", return_value=store_path)

        result = runner.invoke(app, ["rules", "--format", "json", "--save"], catch_exceptions=False)

        assert result.exit_code == 0
        assert '"id": "python-style"' in result.stdout
        saved_path = Path(".cursor") / "rules" / "contextctl.mdc"
        assert saved_path.exists()
        saved_contents = saved_path.read_text(encoding="utf-8")
        assert "# python-style" in saved_contents
        assert "Saved Cursor rules to .cursor/rules/contextctl.mdc" in result.stdout


def test_list_command_filters_prompts_and_supports_pagination(mocker: MockerFixture) -> None:
    """The list command should honor repo filters, tag filters, and pagination."""
    runner = CliRunner()
    with runner.isolated_filesystem():
        Path(".git").mkdir()
        repo_slug = Path.cwd().name
        store_path = _create_prompt_store_with_prompts(Path(), repo_slug)
        Path(".promptlib.yml").write_text(
            dedent(
                """
                central_repo: https://example.com/library.git
                prompt_sets:
                  - reviews
                  - incidents
                """
            ).strip(),
            encoding="utf-8",
        )
        mocker.patch("contextctl.cli.sync_central_repo", return_value=store_path)

        result = runner.invoke(app, ["list"], catch_exceptions=False)

        assert result.exit_code == 0
        assert "review-pr" in result.stdout
        assert "global-guidance" in result.stdout
        assert "incident-response" not in result.stdout

        tag_result = runner.invoke(app, ["list", "--all", "--tag", "incidents"], catch_exceptions=False)

        assert tag_result.exit_code == 0
        assert "incident-response" in tag_result.stdout
        assert "review-pr" not in tag_result.stdout

        page_result = runner.invoke(
            app,
            ["list", "--all", "--per-page", "2", "--page", "2"],
            catch_exceptions=False,
        )

        assert page_result.exit_code == 0
        assert "incident-response" in page_result.stdout
        assert "review-pr" not in page_result.stdout


def test_search_command_supports_exact_matches_and_snippets(mocker: MockerFixture) -> None:
    """The search command should provide snippets and respect the --exact flag."""
    runner = CliRunner()
    with runner.isolated_filesystem():
        Path(".git").mkdir()
        repo_slug = Path.cwd().name
        store_path = _create_prompt_store_with_prompts(Path(), repo_slug)
        Path(".promptlib.yml").write_text(
            dedent(
                """
                central_repo: https://example.com/library.git
                prompt_sets:
                  - reviews
                  - incidents
                """
            ).strip(),
            encoding="utf-8",
        )
        mocker.patch("contextctl.cli.sync_central_repo", return_value=store_path)

        fuzzy_result = runner.invoke(app, ["search", "pull", "request"], catch_exceptions=False)

        assert fuzzy_result.exit_code == 0
        assert "review-pr" in fuzzy_result.stdout
        assert "pull request review" in fuzzy_result.stdout

        exact_result = runner.invoke(
            app,
            ["search", "--exact", "--all", "incident prompt"],
            catch_exceptions=False,
        )

        assert exact_result.exit_code == 0
        assert "incident-response" in exact_result.stdout
        assert "review-pr" not in exact_result.stdout


def test_run_command_renders_prompt_with_variables_and_copy(mocker: MockerFixture) -> None:
    """The run command should interpolate variables, copy output, and write files."""
    runner = CliRunner()
    with runner.isolated_filesystem():
        Path(".git").mkdir()
        repo_slug = Path.cwd().name
        store_path = _create_prompt_store_with_template(Path(), repo_slug)
        Path(".promptlib.yml").write_text(
            dedent(
                """
                central_repo: https://example.com/library.git
                prompt_sets:
                  - templates
                """
            ).strip(),
            encoding="utf-8",
        )
        mocker.patch("contextctl.cli.sync_central_repo", return_value=store_path)
        copy_mock = mocker.patch("contextctl._internal.commands.run_cmd.copy_to_clipboard")

        result = runner.invoke(
            app,
            [
                "run",
                "templated",
                "--var",
                "name=Developers",
                "--var",
                "repo=contextctl",
                "--copy",
                "--output",
                "prompt.txt",
            ],
            catch_exceptions=False,
        )

        assert result.exit_code == 0
        assert "Hello Developers!" in result.stdout
        assert "Repo: contextctl" in result.stdout
        copy_mock.assert_called_once_with("Hello Developers!\nRepo: contextctl\n")

        saved_path = Path("prompt.txt")
        assert saved_path.exists()
        assert "Repo: contextctl" in saved_path.read_text(encoding="utf-8")


def test_run_command_supports_json_format_and_all_flag(mocker: MockerFixture) -> None:
    """The run command should emit JSON and allow accessing other repo prompts with --all."""
    runner = CliRunner()
    with runner.isolated_filesystem():
        Path(".git").mkdir()
        store_path = _create_prompt_store_with_template(Path(), "other-repo")
        Path(".promptlib.yml").write_text(
            dedent(
                """
                central_repo: https://example.com/library.git
                prompt_sets:
                  - templates
                """
            ).strip(),
            encoding="utf-8",
        )
        mocker.patch("contextctl.cli.sync_central_repo", return_value=store_path)

        missing_result = runner.invoke(app, ["run", "templated"], catch_exceptions=False)
        assert missing_result.exit_code == 1
        assert "was not found" in missing_result.stdout

        json_result = runner.invoke(
            app,
            ["run", "templated", "--all", "--format", "json"],
            catch_exceptions=False,
        )
        assert json_result.exit_code == 0
        assert '"id": "templated"' in json_result.stdout
        assert '"version": "1.2.3"' in json_result.stdout


def test_tree_command_displays_hierarchy_and_repo_filtering(mocker: MockerFixture) -> None:
    """The tree command should render prompts/rules and support repo-only filtering."""
    runner = CliRunner()
    with runner.isolated_filesystem():
        Path(".git").mkdir()
        repo_slug = Path.cwd().name
        store_path = _create_combined_store(Path(), repo_slug)
        Path(".promptlib.yml").write_text(
            dedent(
                """
                central_repo: https://example.com/library.git
                """
            ).strip(),
            encoding="utf-8",
        )
        mocker.patch("contextctl.cli.sync_central_repo", return_value=store_path)

        result = runner.invoke(app, ["tree"], catch_exceptions=False)
        assert result.exit_code == 0
        assert "review-pr" in result.stdout
        assert "global-guidance" in result.stdout
        assert "python-style" in result.stdout
        assert "ops-checklist" in result.stdout

        filtered = runner.invoke(app, ["tree", "--repo-only", "--collapse-rules"], catch_exceptions=False)
        assert filtered.exit_code == 0
        assert "ops-checklist" not in filtered.stdout
        assert "review-pr" in filtered.stdout


def test_tree_branch_does_not_duplicate_directories(tmp_path: Path) -> None:
    """Tree rendering should only create one node per directory."""
    base_dir = tmp_path / "rules"
    python_dir = base_dir / "python"
    python_dir.mkdir(parents=True)

    style_path = python_dir / "python-style.md"
    testing_path = python_dir / "python-testing.md"
    style_path.write_text("---\n", encoding="utf-8")
    testing_path.write_text("---\n", encoding="utf-8")

    documents = [
        RuleDocument(
            metadata=RuleMetadata(id="python-style", tags=["python"], repos=["contextctl"], version="1.0.0"),
            body="body",
            path=style_path,
        ),
        RuleDocument(
            metadata=RuleMetadata(id="python-testing", tags=["python"], repos=["contextctl"], version="1.0.1"),
            body="body",
            path=testing_path,
        ),
    ]

    tree_root = Tree("rules")
    _populate_tree_branch(tree_root, documents, base_dir=base_dir, repo_slug=None)

    assert len(tree_root.children) == 1
    python_node = tree_root.children[0]
    assert str(python_node.label) == "python"
    assert len(python_node.children) == 2
