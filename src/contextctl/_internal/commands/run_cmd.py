"""Run command implementation."""

from __future__ import annotations

from collections.abc import Sequence
from pathlib import Path

from contextctl import filter_by_repo
from contextctl._internal.clipboard import copy_to_clipboard
from contextctl._internal.filters import apply_prompt_variables, find_prompt_by_id, parse_variable_assignments
from contextctl._internal.loaders import load_prompt_documents
from contextctl._internal.output.formatters import format_prompt_output
from contextctl._internal.state import CLIState
from contextctl._internal.utils import write_output_file


def execute_run_command(
    state: CLIState,
    store_path: Path,
    prompt_selections: list[str],
    repo_slug: str | None,
    prompt_id: str,
    variable_assignments: Sequence[str] | None,
    output_format: str,
    copy_clipboard: bool,
    output_path: Path | None,
    all_prompts: bool,
) -> tuple[str | None, str | None]:
    """Execute the run command logic.

    Args:
        state: CLI state.
        store_path: Path to the prompt store.
        prompt_selections: List of prompt set identifiers to load.
        repo_slug: Repository slug for filtering.
        prompt_id: Prompt identifier to render.
        variable_assignments: Variable assignments in KEY=VALUE format.
        output_format: Output format (text or json).
        copy_clipboard: Whether to copy to clipboard.
        output_path: Optional file path to write output.
        all_prompts: Whether to search all repositories.

    Returns:
        Tuple of (error_message, formatted_output) - error_message is None on success.

    Raises:
        ContentError: If prompts cannot be loaded.
        ValueError: If variable assignments are malformed.
        RuntimeError: If clipboard copy fails.
        OSError: If file write fails.
    """
    documents = load_prompt_documents(store_path, prompt_selections)

    search_space = documents if all_prompts else filter_by_repo(documents, repo_slug)
    document = find_prompt_by_id(search_space, prompt_id)
    if document is None:
        scope = "all prompts" if all_prompts else f"repo '{repo_slug or 'unknown'}'"
        available = ", ".join(sorted(doc.metadata.prompt_id for doc in search_space)) or "none"
        error_msg = f"Prompt '{prompt_id}' was not found within {scope}. Available prompts: {available}."
        return error_msg, None

    assignments = parse_variable_assignments(variable_assignments)
    rendered_body, missing_vars, used_vars = apply_prompt_variables(document.body, assignments)
    unused_vars = sorted(set(assignments) - used_vars)

    formatted_output = format_prompt_output(document, rendered_body, output_format, store_path)

    if missing_vars:
        state.console.print(
            f"[warning]Missing values for variables: {', '.join(sorted(missing_vars))}. "
            "Placeholders were left intact.[/warning]"
        )
    if unused_vars:
        state.console.print(
            f"[warning]Ignored variable assignments: {', '.join(unused_vars)}. "
            "No matching placeholders were found.[/warning]"
        )

    state.console.print(formatted_output, markup=False)

    if copy_clipboard:
        copy_to_clipboard(formatted_output)
        state.console.print(f"[success]Copied prompt '{document.metadata.prompt_id}' to clipboard.[/success]")

    if output_path is not None:
        written_path = write_output_file(output_path, formatted_output)
        state.console.print(f"[success]Wrote prompt output to {written_path}[/success]")

    return None, formatted_output
