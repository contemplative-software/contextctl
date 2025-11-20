"""Rules command implementation."""

from __future__ import annotations

from pathlib import Path

from contextctl import find_repo_root
from contextctl._internal.loaders import load_selected_rules
from contextctl._internal.output.formatters import format_rules
from contextctl._internal.output.renderers import render_rule_summary
from contextctl._internal.state import CLIState
from contextctl._internal.utils import write_cursor_rules_file


def execute_rules_command(
    state: CLIState,
    store_path: Path,
    rule_selections: list[str],
    output_format: str,
    save: bool,
) -> None:
    """Execute the rules command logic.

    Args:
        state: CLI state.
        store_path: Path to the prompt store.
        rule_selections: List of rule set identifiers to load.
        output_format: Output format (text, json, or cursor).
        save: Whether to save Cursor-formatted output.

    Raises:
        ContentError: If rules cannot be loaded.
    """
    documents = load_selected_rules(store_path, rule_selections)

    render_rule_summary(state.console, documents, store_path)
    formatted_output = format_rules(documents, output_format, store_path)
    state.console.print()
    state.console.print(formatted_output, markup=False)

    if save:
        repo_root = find_repo_root()
        cursor_payload = format_rules(documents, "cursor", store_path)
        saved_path = write_cursor_rules_file(cursor_payload, repo_root=repo_root)
        relative_path = saved_path.relative_to(repo_root)
        state.console.print(f"[success]Saved Cursor rules to {relative_path}[/success]")
