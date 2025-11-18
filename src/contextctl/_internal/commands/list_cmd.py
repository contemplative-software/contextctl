"""List command implementation."""

from __future__ import annotations

from collections.abc import Sequence
from pathlib import Path

from contextctl import filter_by_repo, filter_by_tags
from contextctl._internal.loaders import load_prompt_documents
from contextctl._internal.output.renderers import render_prompt_table
from contextctl._internal.state import CLIState
from contextctl._internal.utils import paginate_items


def execute_list_command(
    state: CLIState,
    store_path: Path,
    prompt_selections: list[str],
    repo_slug: str | None,
    tag_filters: Sequence[str],
    all_prompts: bool,
    page: int,
    per_page: int,
    match_all_tags: bool,
) -> None:
    """Execute the list command logic.

    Args:
        state: CLI state.
        store_path: Path to the prompt store.
        prompt_selections: List of prompt set identifiers to load.
        repo_slug: Repository slug for filtering.
        tag_filters: Tags to filter by.
        all_prompts: Whether to show prompts from all repositories.
        page: Page number to display.
        per_page: Number of items per page.
        match_all_tags: Whether to require all tags.

    Raises:
        ContentError: If prompts cannot be loaded.
    """
    documents = load_prompt_documents(store_path, prompt_selections)

    filtered = documents if all_prompts else filter_by_repo(documents, repo_slug)
    filtered = filter_by_tags(filtered, tag_filters, match_all=match_all_tags)

    if not filtered:
        scope = "all prompts" if all_prompts else f"repo '{repo_slug or 'unknown'}'"
        if tag_filters:
            scope = f"{scope} with tags {', '.join(tag_filters)}"
        state.console.print(f"[warning]No prompts matched {scope}. Try relaxing the filters or use --all.[/warning]")
        return

    paginated, total_pages, resolved_page = paginate_items(filtered, page, per_page)
    if page > total_pages:
        state.console.print(
            f"[warning]Requested page {page} exceeds total pages ({total_pages}). "
            f"Showing page {resolved_page} instead.[/warning]"
        )

    render_prompt_table(
        state.console,
        paginated,
        resolved_page,
        total_pages,
        total=len(filtered),
        repo_slug=repo_slug,
        filtered_tags=tag_filters,
        include_repo_filter=not all_prompts,
    )
