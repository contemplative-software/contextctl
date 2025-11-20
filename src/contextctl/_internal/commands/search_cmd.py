"""Search command implementation."""

from __future__ import annotations

from collections.abc import Sequence
from pathlib import Path

from contextctl import filter_by_repo, filter_by_tags
from contextctl._internal.filters import execute_search
from contextctl._internal.loaders import load_prompt_documents
from contextctl._internal.output.renderers import render_search_results
from contextctl._internal.state import CLIState


def execute_search_command(
    state: CLIState,
    store_path: Path,
    prompt_selections: list[str],
    repo_slug: str | None,
    query: str,
    tag_filters: Sequence[str],
    all_prompts: bool,
    exact: bool,
    limit: int,
) -> None:
    """Execute the search command logic.

    Args:
        state: CLI state.
        store_path: Path to the prompt store.
        prompt_selections: List of prompt set identifiers to load.
        repo_slug: Repository slug for filtering.
        query: Search query string.
        tag_filters: Tags to filter by.
        all_prompts: Whether to search across all repositories.
        exact: Whether to require exact matches.
        limit: Maximum number of results to display.

    Raises:
        ContentError: If prompts cannot be loaded.
    """
    documents = load_prompt_documents(store_path, prompt_selections)

    filtered = documents if all_prompts else filter_by_repo(documents, repo_slug)
    filtered = filter_by_tags(filtered, tag_filters)

    results = execute_search(filtered, query, exact=exact)
    if not results:
        scope = "all prompts" if all_prompts else f"repo '{repo_slug or 'unknown'}'"
        state.console.print(
            f"[warning]No prompts matched query '{query}' within {scope}. "
            f"Try --all or adjust the search terms.[/warning]"
        )
        return

    limited_results = results[:limit]
    render_search_results(
        state.console,
        limited_results,
        query=query,
        total=len(results),
        limit=limit,
        repo_slug=repo_slug,
        include_repo_filter=not all_prompts,
        filtered_tags=tag_filters,
        exact=exact,
    )
