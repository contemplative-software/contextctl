"""Tree command implementation."""

from __future__ import annotations

from pathlib import Path

from contextctl import ContentError, filter_by_repo, scan_prompts_dir, scan_rules_dir
from contextctl._internal.output.renderers import render_library_tree
from contextctl._internal.state import CLIState


def execute_tree_command(
    state: CLIState,
    store_path: Path,
    repo_slug: str | None,
    collapse_prompts: bool,
    collapse_rules: bool,
    repo_only: bool,
) -> None:
    """Execute the tree command logic.

    Args:
        state: CLI state.
        store_path: Path to the prompt store.
        repo_slug: Repository slug for relevance marking.
        collapse_prompts: Whether to collapse the prompts section.
        collapse_rules: Whether to collapse the rules section.
        repo_only: Whether to show only repo-relevant items.
    """
    try:
        prompt_documents = scan_prompts_dir(store_path)
    except ContentError as exc:
        state.console.print(f"[warning]Unable to load prompts for tree view: {exc}[/warning]")
        prompt_documents = []

    try:
        rule_documents = scan_rules_dir(store_path)
    except ContentError as exc:
        state.console.print(f"[warning]Unable to load rules for tree view: {exc}[/warning]")
        rule_documents = []

    if repo_only:
        prompt_documents = filter_by_repo(prompt_documents, repo_slug)
        rule_documents = filter_by_repo(rule_documents, repo_slug)

    render_library_tree(
        state.console,
        prompt_documents,
        rule_documents,
        store_path=store_path,
        repo_slug=repo_slug,
        collapse_prompts=collapse_prompts,
        collapse_rules=collapse_rules,
    )
