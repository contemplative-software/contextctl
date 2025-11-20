"""Rich console rendering utilities for tables and trees."""

from __future__ import annotations

from collections.abc import Sequence
from pathlib import Path
from typing import Final

from rich import box
from rich.console import Console
from rich.table import Table
from rich.tree import Tree

from contextctl import PromptDocument, RuleDocument
from contextctl.content import BaseDocument

_REPO_MATCH_ICON: Final[str] = "[success]●[/success]"
_REPO_NON_MATCH_ICON: Final[str] = "[dim]○[/dim]"
_SNIPPET_CONTEXT_CHARS: Final[int] = 120


def render_rule_summary(console: Console, documents: Sequence[RuleDocument], store_path: Path) -> None:
    """Render a table summarizing the merged rule metadata.

    Args:
        console: Rich console for output.
        documents: Rule documents to display.
        store_path: Path to the prompt store for relative path resolution.
    """
    from contextctl._internal.output.formatters import relative_source

    table = Table(title="Rule Sources", header_style="bold", show_lines=False, box=box.MINIMAL_DOUBLE_HEAD)
    table.add_column("Rule ID", style="info")
    table.add_column("Version", justify="right")
    table.add_column("Tags")
    table.add_column("Repos")
    table.add_column("Source", style="text")

    for document in documents:
        metadata = document.metadata
        tags = ", ".join(metadata.tags) or "-"
        repos = ", ".join(metadata.repos) or "all"
        source = relative_source(document.path, store_path)
        table.add_row(
            metadata.rule_id,
            metadata.version,
            tags,
            repos,
            source,
        )

    console.print(table)


def render_prompt_table(
    console: Console,
    prompts: Sequence[PromptDocument],
    page: int,
    total_pages: int,
    *,
    total: int,
    repo_slug: str | None,
    filtered_tags: Sequence[str],
    include_repo_filter: bool,
) -> None:
    """Render a Rich table summarizing prompts for the list command.

    Args:
        console: Rich console for output.
        prompts: Prompt documents to display.
        page: Current page number.
        total_pages: Total number of pages.
        total: Total number of prompts before pagination.
        repo_slug: Repository slug for filtering context.
        filtered_tags: Tags used for filtering.
        include_repo_filter: Whether repo filtering is active.
    """
    table = Table(title="Prompts", header_style="bold", show_lines=False, box=box.MINIMAL_DOUBLE_HEAD)
    table.add_column("Prompt ID", style="info")
    table.add_column("Title", style="text")
    table.add_column("Tags")
    table.add_column("Agents")

    for document in prompts:
        metadata = document.metadata
        tags = ", ".join(metadata.tags) or "-"
        agents = ", ".join(metadata.agents) or "all"
        title = prompt_display_title(document)
        table.add_row(metadata.prompt_id, title, tags, agents)

    console.print(table)
    repo_scope = "all repositories"
    if include_repo_filter:
        repo_scope = f"repo '{repo_slug or 'unknown'}'"
    tag_scope = f"; tags: {', '.join(filtered_tags)}" if filtered_tags else ""
    console.print(
        f"[info]Showing page {page} of {total_pages} ({len(prompts)} of {total} prompts, "
        f"{repo_scope}{tag_scope}).[/info]"
    )


def render_search_results(
    console: Console,
    prompts: Sequence[PromptDocument],
    *,
    query: str,
    total: int,
    limit: int,
    repo_slug: str | None,
    include_repo_filter: bool,
    filtered_tags: Sequence[str],
    exact: bool,
) -> None:
    """Display search results with contextual snippets.

    Args:
        console: Rich console for output.
        prompts: Prompt documents to display.
        query: Search query string.
        total: Total number of search results.
        limit: Maximum number of results to display.
        repo_slug: Repository slug for filtering context.
        include_repo_filter: Whether repo filtering is active.
        filtered_tags: Tags used for filtering.
        exact: Whether exact matching was used.
    """
    table = Table(
        title=f"Search results for '{query}'",
        header_style="bold",
        show_lines=False,
        box=box.MINIMAL_DOUBLE_HEAD,
    )
    table.add_column("Prompt ID", style="info")
    table.add_column("Title", style="text")
    table.add_column("Snippet", style="text")
    table.add_column("Tags")

    for document in prompts:
        metadata = document.metadata
        snippet = build_search_snippet(document, query)
        table.add_row(
            metadata.prompt_id,
            prompt_display_title(document),
            snippet,
            ", ".join(metadata.tags) or "-",
        )

    console.print(table)
    repo_scope = "all repositories"
    if include_repo_filter:
        repo_scope = f"repo '{repo_slug or 'unknown'}'"
    tag_scope = f"; tags: {', '.join(filtered_tags)}" if filtered_tags else ""
    search_mode = "Exact" if exact else "Fuzzy"

    if total > len(prompts):
        console.print(
            f"[info]Showing {len(prompts)} of {total} matches (limit={limit}) "
            f"within {repo_scope}{tag_scope}. {search_mode} search applied.[/info]"
        )
    else:
        console.print(
            f"[info]Found {total} matches within {repo_scope}{tag_scope}. {search_mode} search applied.[/info]"
        )


def render_library_tree(
    console: Console,
    prompts: Sequence[PromptDocument],
    rules: Sequence[RuleDocument],
    *,
    store_path: Path,
    repo_slug: str | None,
    collapse_prompts: bool,
    collapse_rules: bool,
) -> None:
    """Render a Rich tree describing the prompt and rule library.

    Args:
        console: Rich console for output.
        prompts: Prompt documents to display.
        rules: Rule documents to display.
        store_path: Path to the prompt store.
        repo_slug: Repository slug for relevance marking.
        collapse_prompts: Whether to collapse the prompts section.
        collapse_rules: Whether to collapse the rules section.
    """
    root = Tree("[bold]Prompt Library[/bold]", guide_style="text")

    prompts_node = root.add("[bold]prompts[/bold]", expanded=not collapse_prompts)
    _populate_tree_branch(
        prompts_node,
        prompts,
        base_dir=store_path / "prompts",
        repo_slug=repo_slug,
    )
    if not prompts:
        prompts_node.add("[dim](no prompts discovered)[/dim]")

    rules_node = root.add("[bold]rules[/bold]", expanded=not collapse_rules)
    _populate_tree_branch(
        rules_node,
        rules,
        base_dir=store_path / "rules",
        repo_slug=repo_slug,
    )
    if not rules:
        rules_node.add("[dim](no rules discovered)[/dim]")

    console.print(root)


def _populate_tree_branch(
    root: Tree,
    documents: Sequence[BaseDocument],
    *,
    base_dir: Path,
    repo_slug: str | None,
) -> None:
    """Populate a Rich tree branch with document entries grouped by directory.

    Args:
        root: Root tree node to populate.
        documents: Documents to add to the tree.
        base_dir: Base directory for relative path calculation.
        repo_slug: Repository slug for relevance marking.
    """
    if not documents:
        return

    node_cache: dict[tuple[str, ...], Tree] = {}

    def sorter(document: BaseDocument) -> tuple[str, ...]:
        relative = _relative_to_base(document.path, base_dir)
        identifier = document_identifier(document)
        return (*relative.parts, identifier)

    for document in sorted(documents, key=sorter):
        relative_path = _relative_to_base(document.path, base_dir)
        parent_parts = relative_path.parts[:-1]
        current = root
        accumulated: list[str] = []

        for part in parent_parts:
            accumulated.append(part)
            key = tuple(accumulated)
            current = node_cache.setdefault(key, current.add(part))

        current.add(format_tree_label(document, repo_slug))


def format_tree_label(document: BaseDocument, repo_slug: str | None) -> str:
    """Return the textual label for a tree leaf node.

    Args:
        document: Document to create a label for.
        repo_slug: Repository slug for relevance marking.

    Returns:
        Formatted tree label string.
    """
    identifier = document_identifier(document)
    metadata = document.metadata
    relevant = is_repo_relevant(metadata.repos, repo_slug)
    icon = _REPO_MATCH_ICON if relevant else _REPO_NON_MATCH_ICON
    tags = ", ".join(metadata.tags) or "-"
    version = metadata.version
    return f"{icon} {identifier} [dim](v{version}; tags: {tags})[/dim]"


def document_identifier(document: BaseDocument) -> str:
    """Return the identifier for either a prompt or rule document.

    Args:
        document: Document to get identifier from.

    Returns:
        Document identifier string.
    """
    metadata = document.metadata
    prompt_id = getattr(metadata, "prompt_id", None)
    if isinstance(prompt_id, str):
        return prompt_id
    rule_id = getattr(metadata, "rule_id", None)
    if isinstance(rule_id, str):
        return rule_id
    return document.path.stem


def is_repo_relevant(repos: Sequence[str], repo_slug: str | None) -> bool:
    """Return True if the repo slug is included in the metadata repos.

    Args:
        repos: List of repository slugs from document metadata.
        repo_slug: Current repository slug.

    Returns:
        True if document is relevant to the current repository.
    """
    if not repos:
        return True
    if repo_slug is None:
        return False
    normalized = repo_slug.strip().casefold()
    if not normalized:
        return False
    return any(repo.strip().casefold() == normalized for repo in repos)


def _relative_to_base(path: Path, base_dir: Path) -> Path:
    """Return path relative to base_dir, falling back to filename on mismatch.

    Args:
        path: Path to make relative.
        base_dir: Base directory for relative calculation.

    Returns:
        Relative path or filename.
    """
    try:
        return path.resolve().relative_to(base_dir.resolve())
    except ValueError:
        return Path(path.name)


def prompt_display_title(document: PromptDocument) -> str:
    """Return a user-friendly prompt title.

    Args:
        document: Prompt document.

    Returns:
        Display title for the prompt.
    """
    metadata = document.metadata
    if metadata.title:
        return metadata.title
    candidate = metadata.prompt_id.replace("-", " ").replace("_", " ").strip()
    return candidate.title() or metadata.prompt_id


def build_search_snippet(document: PromptDocument, query: str) -> str:
    """Return a contextual snippet for a search result.

    Args:
        document: Prompt document to generate snippet from.
        query: Search query for highlighting.

    Returns:
        Formatted snippet with highlighted match.
    """
    body = document.body.strip()
    if not body:
        return "(no body content)"

    lowered = body.casefold()
    tokens = [token.casefold() for token in query.split() if token.strip()]
    match_index = -1
    match_length = 0

    if tokens:
        for token in sorted(tokens, key=len, reverse=True):
            idx = lowered.find(token)
            if idx != -1:
                match_index = idx
                match_length = len(token)
                break

    if match_index == -1:
        match_index = 0

    start = max(0, match_index - _SNIPPET_CONTEXT_CHARS // 2)
    end = min(len(body), start + _SNIPPET_CONTEXT_CHARS)
    snippet = body[start:end]

    if match_length:
        relative_index = match_index - start
        highlighted = (
            snippet[:relative_index]
            + f"[success]{body[match_index : match_index + match_length]}[/success]"
            + snippet[relative_index + match_length :]
        )
    else:
        highlighted = snippet

    prefix = "..." if start > 0 else ""
    suffix = "..." if end < len(body) else ""
    return f"{prefix}{highlighted}{suffix}"
