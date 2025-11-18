"""Typer CLI application for contextctl."""

from __future__ import annotations

from pathlib import Path
from typing import Final

import typer
from rich.console import Console

from contextctl import (
    REPO_CONFIG_FILENAME,
    ConfigError,
    ContentError,
    PromptLibConfig,
    RepoConfig,
    StoreSyncError,
    __version__,
    clear_store_cache,
    filter_by_repo,
    filter_by_tags,
    find_repo_root,
    get_store_path,
    load_repo_config,
    scan_prompts_dir,
    scan_rules_dir,
    sync_central_repo,
)
from contextctl._internal.clipboard import copy_to_clipboard
from contextctl._internal.commands.init_cmd import (
    confirm_overwrite,
    load_existing_config,
    load_store_preview,
    prompt_central_repo,
    prompt_set_selection,
    write_repo_config_file,
)
from contextctl._internal.filters import (
    apply_prompt_variables,
    execute_search,
    find_prompt_by_id,
    parse_variable_assignments,
)
from contextctl._internal.loaders import load_prompt_documents, load_selected_rules
from contextctl._internal.output.formatters import format_prompt_output, format_rules
from contextctl._internal.output.renderers import (
    render_library_tree,
    render_prompt_table,
    render_rule_summary,
    render_search_results,
)
from contextctl._internal.state import CLIState, build_console
from contextctl._internal.utils import (
    paginate_items,
    resolve_repo_slug,
    write_cursor_rules_file,
    write_output_file,
)

_SKIP_PREP_COMMANDS: Final[set[str]] = {"init"}
_RULE_OUTPUT_FORMATS: Final[tuple[str, ...]] = ("text", "json", "cursor")
_PROMPT_OUTPUT_FORMATS: Final[tuple[str, ...]] = ("text", "json")
_DEFAULT_PAGE_SIZE: Final[int] = 20
_MAX_PAGE_SIZE: Final[int] = 200

app = typer.Typer(
    add_completion=False,
    no_args_is_help=True,
    pretty_exceptions_enable=False,
    help="Manage repo-aware prompt and rule libraries.",
)


@app.callback()
def main(
    ctx: typer.Context,
    verbose: bool = typer.Option(False, "--verbose", "-v", help="Enable verbose console output."),
    no_sync: bool = typer.Option(False, "--no-sync", help="Skip automatic prompt store synchronization."),
    force_sync: bool = typer.Option(
        False,
        "--force-sync",
        help="Force a fresh prompt store synchronization before running the command.",
    ),
) -> None:
    """Parse global options, configure shared state, and optionally sync.

    Args:
        ctx: Typer context that stores shared CLI state.
        verbose: Whether to enable verbose console logging.
        no_sync: Whether to skip prompt store synchronization.
        force_sync: Whether to force a fresh sync before running the command.

    Raises:
        typer.BadParameter: When mutually exclusive sync flags are combined.
    """
    if force_sync and no_sync:
        raise typer.BadParameter("--force-sync cannot be combined with --no-sync")

    state = _get_state(ctx, verbose=verbose, skip_sync=no_sync, force_sync=force_sync)
    command = ctx.invoked_subcommand
    if command is None or command in _SKIP_PREP_COMMANDS or state.prepared:
        return

    _prepare_environment(state)


@app.command()
def version(ctx: typer.Context) -> None:
    """Display the installed contextctl version.

    Args:
        ctx: Typer context for the current invocation.
    """
    state = _ensure_state(ctx)
    state.console.print(f"[success]contextctl {__version__}[/success]")


@app.command()
def init(ctx: typer.Context) -> None:
    """Run the interactive wizard that creates `.promptlib.yml`.

    Args:
        ctx: Typer context for the current invocation.
    """
    state = _ensure_state(ctx)
    console = state.console

    try:
        repo_root = find_repo_root()
    except ConfigError as exc:
        _abort(state, str(exc))
        return

    config_path = repo_root / REPO_CONFIG_FILENAME
    existing_config = load_existing_config(repo_root, console)
    if config_path.exists() and not confirm_overwrite(console):
        console.print("[warning]Initialization cancelled; existing configuration preserved.")
        return

    console.print("[info]Welcome to the contextctl initialization wizard.[/info]")
    central_repo = prompt_central_repo(existing_config)

    preview = None
    if state.skip_sync:
        console.print("[warning]Skipping store preview because --no-sync was provided.[/warning]")
    else:
        if state.force_sync:
            store_path = get_store_path(state.promptlib_config, central_repo)
            store_root = state.promptlib_config.store_root
            try:
                store_path.relative_to(store_root)
                clear_store_cache(store_path)
            except ValueError:
                pass  # Don't clear local stores; they're not caches
        preview = load_store_preview(
            central_repo,
            promptlib_config=state.promptlib_config,
            console=console,
        )

    rule_sets = prompt_set_selection(
        console,
        label="rule",
        previews=preview.rule_sets if preview else [],
        defaults=existing_config.rules if existing_config else None,
    )
    prompt_sets = prompt_set_selection(
        console,
        label="prompt",
        previews=preview.prompt_sets if preview else [],
        defaults=existing_config.prompt_sets if existing_config else None,
    )

    from contextctl import create_default_config

    repo_config = create_default_config(
        central_repo,
        rules=rule_sets,
        prompt_sets=prompt_sets,
    )

    console.print("\n[info]Configuration summary[/info]")
    console.print(f"  central_repo: [text]{repo_config.central_repo}[/text]")
    console.print(f"  rules: [text]{', '.join(repo_config.rules) or 'none'}[/text]")
    console.print(f"  prompt_sets: [text]{', '.join(repo_config.prompt_sets) or 'none'}[/text]")

    if not typer.confirm(f"Write configuration to {config_path}?", default=True):
        console.print("[warning]Initialization cancelled before writing configuration.")
        return

    write_repo_config_file(config_path, repo_config)
    console.print(f"[success]Created {config_path.relative_to(repo_root)}[/success]")


@app.command()
def rules(
    ctx: typer.Context,
    output_format: str = typer.Option(
        None,
        "--format",
        "-f",
        help="Output format for merged rules. Supported values: text, json, cursor.",
    ),
    save: bool = typer.Option(
        False,
        "--save",
        help="Write Cursor-formatted output to `.cursor/rules/contextctl.mdc`.",
    ),
) -> None:
    """Render configured rule sets and optionally save the output.

    Args:
        ctx: Typer context for the current invocation.
        output_format: Preferred output format for rule content.
        save: Whether to persist Cursor-formatted output in `.cursor/rules`.
    """
    state = _ensure_state(ctx)
    if not state.prepared:
        _prepare_environment(state)
        if not state.prepared:
            return

    repo_config = state.repo_config
    if repo_config is None:
        _abort(state, "Repository configuration is not available.")
        return
    if not repo_config.rules:
        _abort(state, "No rule sets are configured in .promptlib.yml.")
        return

    store_path = _require_store_path(state, repo_config)
    try:
        documents = load_selected_rules(store_path, repo_config.rules)
    except ContentError as exc:
        _abort(state, str(exc))
        return

    format_value = output_format or state.promptlib_config.default_output_format
    normalized_format = format_value.strip().casefold()
    if normalized_format not in _RULE_OUTPUT_FORMATS:
        supported = ", ".join(_RULE_OUTPUT_FORMATS)
        _abort(state, f"Unsupported format '{format_value}'. Supported values: {supported}.")
        return

    render_rule_summary(state.console, documents, store_path)
    formatted_output = format_rules(documents, normalized_format, store_path)
    state.console.print()
    state.console.print(formatted_output, markup=False)

    if save:
        repo_root = find_repo_root()
        cursor_payload = format_rules(documents, "cursor", store_path)
        saved_path = write_cursor_rules_file(cursor_payload, repo_root=repo_root)
        relative_path = saved_path.relative_to(repo_root)
        state.console.print(f"[success]Saved Cursor rules to {relative_path}[/success]")


@app.command("list")
def list_prompts(
    ctx: typer.Context,
    tag: list[str] | None = typer.Option(
        None,
        "--tag",
        "-t",
        help="Filter prompts by tag. Provide multiple --tag options for additional filters.",
    ),
    all_prompts: bool = typer.Option(
        False,
        "--all",
        help="Display prompts from every repository instead of restricting to the current repo.",
    ),
    page: int = typer.Option(
        1,
        "--page",
        min=1,
        help="Page number to display (1-indexed).",
    ),
    per_page: int = typer.Option(
        _DEFAULT_PAGE_SIZE,
        "--per-page",
        min=1,
        max=_MAX_PAGE_SIZE,
        help="Number of prompts to show per page.",
    ),
    match_all_tags: bool = typer.Option(
        False,
        "--match-all-tags",
        help="Require prompts to include every provided tag instead of matching any tag.",
    ),
) -> None:
    """Render a paginated table of prompts for the current repository.

    Args:
        ctx: Typer context for the current invocation.
        tag: Optional tag filters applied before pagination.
        all_prompts: Whether to ignore repo associations during listing.
        page: Page number to display (1-indexed).
        per_page: Number of prompts to show per page.
        match_all_tags: Whether prompts must include every provided tag.
    """
    state = _ensure_state(ctx)
    if not state.prepared:
        _prepare_environment(state)
        if not state.prepared:
            return

    repo_config = state.repo_config
    if repo_config is None:
        _abort(state, "Repository configuration is not available.")
        return

    store_path = _require_store_path(state, repo_config)
    try:
        documents = load_prompt_documents(store_path, repo_config.prompt_sets)
    except ContentError as exc:
        _abort(state, str(exc))
        return

    repo_slug = resolve_repo_slug()
    filtered = documents if all_prompts else filter_by_repo(documents, repo_slug)
    tag_filters = list(tag or [])
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


@app.command()
def search(
    ctx: typer.Context,
    terms: list[str] = typer.Argument(
        ...,
        help="Search terms. Provide multiple values to widen the query.",
    ),
    tag: list[str] | None = typer.Option(
        None,
        "--tag",
        "-t",
        help="Filter prompts by tag before applying the search.",
    ),
    all_prompts: bool = typer.Option(
        False,
        "--all",
        help="Search across every repository instead of restricting to the current repo.",
    ),
    exact: bool = typer.Option(
        False,
        "--exact",
        help="Require exact phrase matches instead of fuzzy token matching.",
    ),
    limit: int = typer.Option(
        20,
        "--limit",
        min=1,
        max=200,
        help="Maximum number of results to display.",
    ),
) -> None:
    """Search prompt content and display contextual snippets.

    Args:
        ctx: Typer context for the current invocation.
        terms: Search terms that define the query.
        tag: Optional tag filters applied before searching.
        all_prompts: Whether to search outside the current repo scope.
        exact: Whether to require exact phrase matches.
        limit: Maximum number of search results to display.
    """
    state = _ensure_state(ctx)
    if not state.prepared:
        _prepare_environment(state)
        if not state.prepared:
            return

    repo_config = state.repo_config
    if repo_config is None:
        _abort(state, "Repository configuration is not available.")
        return

    query = " ".join(part for part in terms if part.strip()).strip()
    if not query:
        _abort(state, "Search terms cannot be empty.")
        return

    store_path = _require_store_path(state, repo_config)
    try:
        documents = load_prompt_documents(store_path, repo_config.prompt_sets)
    except ContentError as exc:
        _abort(state, str(exc))
        return

    repo_slug = resolve_repo_slug()
    filtered = documents if all_prompts else filter_by_repo(documents, repo_slug)
    tag_filters = list(tag or [])
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


@app.command()
def run(
    ctx: typer.Context,
    prompt_id: str = typer.Argument(..., help="Prompt identifier to render."),
    var: list[str] | None = typer.Option(
        None,
        "--var",
        "-v",
        help="Provide key=value pairs to substitute within the prompt body.",
    ),
    output_format: str | None = typer.Option(
        None,
        "--format",
        "-f",
        help="Output format for the rendered prompt (text or json).",
    ),
    copy_to_clipboard: bool = typer.Option(
        False,
        "--copy",
        help="Copy the rendered prompt to the clipboard.",
    ),
    output_path: Path | None = typer.Option(
        None,
        "--output",
        "-o",
        help="Write the rendered prompt to a file.",
    ),
    all_prompts: bool = typer.Option(
        False,
        "--all",
        help="Allow running prompts that are not associated with the current repository.",
    ),
) -> None:
    """Render a prompt by id with optional variable interpolation.

    Args:
        ctx: Typer context for the current invocation.
        prompt_id: Identifier of the prompt to render.
        var: Optional `KEY=VALUE` assignments applied to the body.
        output_format: Preferred output format for the rendered prompt.
        copy_to_clipboard: Whether to copy the rendered prompt to the clipboard.
        output_path: Optional file path to persist the rendered prompt.
        all_prompts: Whether to include prompts outside the current repo scope.
    """
    state = _ensure_state(ctx)
    if not state.prepared:
        _prepare_environment(state)
        if not state.prepared:
            return

    repo_config = state.repo_config
    if repo_config is None:
        _abort(state, "Repository configuration is not available.")
        return
    prompt_id = prompt_id.strip()
    if not prompt_id:
        _abort(state, "Prompt id cannot be blank.")
        return

    store_path = _require_store_path(state, repo_config)
    try:
        documents = load_prompt_documents(store_path, repo_config.prompt_sets)
    except ContentError as exc:
        _abort(state, str(exc))
        return

    repo_slug = resolve_repo_slug()
    search_space = documents if all_prompts else filter_by_repo(documents, repo_slug)
    document = find_prompt_by_id(search_space, prompt_id)
    if document is None:
        scope = "all prompts" if all_prompts else f"repo '{repo_slug or 'unknown'}'"
        available = ", ".join(sorted(doc.metadata.prompt_id for doc in search_space)) or "none"
        msg = f"Prompt '{prompt_id}' was not found within {scope}. Available prompts: {available}."
        _abort(state, msg)
        return

    try:
        assignments = parse_variable_assignments(var)
    except ValueError as exc:
        _abort(state, str(exc))
        return

    rendered_body, missing_vars, used_vars = apply_prompt_variables(document.body, assignments)
    unused_vars = sorted(set(assignments) - used_vars)

    format_value = output_format or state.promptlib_config.default_output_format
    normalized_format = format_value.strip().casefold() or "text"
    if normalized_format not in _PROMPT_OUTPUT_FORMATS:
        if output_format is None:
            normalized_format = "text"
        else:
            supported = ", ".join(_PROMPT_OUTPUT_FORMATS)
            _abort(state, f"Unsupported format '{format_value}'. Supported values: {supported}.")
            return

    formatted_output = format_prompt_output(document, rendered_body, normalized_format, store_path)

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

    if copy_to_clipboard:
        try:
            copy_to_clipboard(formatted_output)
        except RuntimeError as exc:
            _abort(state, f"Unable to copy prompt to clipboard: {exc}")
            return
        state.console.print(f"[success]Copied prompt '{document.metadata.prompt_id}' to clipboard.[/success]")

    if output_path is not None:
        try:
            written_path = write_output_file(output_path, formatted_output)
        except OSError as exc:
            _abort(state, f"Unable to write output file: {exc}")
            return
        state.console.print(f"[success]Wrote prompt output to {written_path}[/success]")


@app.command()
def tree(
    ctx: typer.Context,
    collapse_prompts: bool = typer.Option(
        False,
        "--collapse-prompts",
        help="Render the prompts section in a collapsed state.",
    ),
    collapse_rules: bool = typer.Option(
        False,
        "--collapse-rules",
        help="Render the rules section in a collapsed state.",
    ),
    repo_only: bool = typer.Option(
        False,
        "--repo-only",
        help="Only display prompts and rules associated with the current repository.",
    ),
) -> None:
    """Render a hierarchical view of the prompt and rule library.

    Args:
        ctx: Typer context for the current invocation.
        collapse_prompts: Whether to collapse the prompts section.
        collapse_rules: Whether to collapse the rules section.
        repo_only: Whether to restrict the tree to repo-relevant items.
    """
    state = _ensure_state(ctx)
    if not state.prepared:
        _prepare_environment(state)
        if not state.prepared:
            return

    repo_config = state.repo_config
    if repo_config is None:
        _abort(state, "Repository configuration is not available.")
        return

    store_path = _require_store_path(state, repo_config)
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

    repo_slug = resolve_repo_slug()
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


def _get_state(ctx: typer.Context, *, verbose: bool, skip_sync: bool, force_sync: bool) -> CLIState:
    """Return the CLI state stored on the Typer context, creating it if necessary.
    
    Args:
        ctx: Typer context.
        verbose: Whether verbose logging is enabled.
        skip_sync: Whether to skip synchronization.
        force_sync: Whether to force synchronization.
        
    Returns:
        CLIState instance.
    """
    state = ctx.obj
    if not isinstance(state, CLIState):
        ctx.obj = state = CLIState(
            console=build_console(verbose),
            promptlib_config=PromptLibConfig(),
            verbose=verbose,
            skip_sync=skip_sync,
            force_sync=force_sync,
        )
        return state

    state.console = build_console(verbose)
    state.verbose = verbose
    state.skip_sync = skip_sync
    state.force_sync = force_sync
    return state


def _prepare_environment(state: CLIState) -> None:
    """Load repo configuration and, unless disabled, sync the prompt store.
    
    Args:
        state: CLI state to update.
    """
    try:
        repo_config = load_repo_config()
    except ConfigError as exc:
        _abort(state, str(exc))
        return

    state.repo_config = repo_config
    state.prepared = True

    if state.skip_sync:
        return

    if state.force_sync:
        _force_refresh_cache(state, repo_config)

    try:
        state.store_path = sync_central_repo(
            repo_config.central_repo,
            promptlib_config=state.promptlib_config,
            console=state.console,
        )
    except StoreSyncError as exc:
        _abort(state, str(exc))


def _force_refresh_cache(state: CLIState, repo_config: RepoConfig) -> None:
    """Remove the cached store before syncing when `--force-sync` is provided.
    
    Args:
        state: CLI state.
        repo_config: Repository configuration.
    """
    store_path = get_store_path(state.promptlib_config, repo_config.central_repo)
    store_root = state.promptlib_config.store_root
    try:
        store_path.relative_to(store_root)
    except ValueError:
        return
    clear_store_cache(store_path)


def _abort(state: CLIState, message: str, *, exit_code: int = 1) -> None:
    """Print a styled error message and exit the CLI.
    
    Args:
        state: CLI state.
        message: Error message to display.
        exit_code: Exit code to use.
    """
    state.console.print(f"[error]Error:[/error] {message}")
    raise typer.Exit(code=exit_code)


def _ensure_state(ctx: typer.Context) -> CLIState:
    """Return the CLI state, creating a minimal default if the callback was bypassed.
    
    Args:
        ctx: Typer context.
        
    Returns:
        CLIState instance.
    """
    state = ctx.obj
    if isinstance(state, CLIState):
        return state
    fallback_state = CLIState(
        console=build_console(verbose=False),
        promptlib_config=PromptLibConfig(),
        verbose=False,
        skip_sync=True,
        force_sync=False,
    )
    ctx.obj = fallback_state
    return fallback_state


def _require_store_path(state: CLIState, repo_config: RepoConfig) -> Path:
    """Return the path to the prompt store, ensuring it exists locally.
    
    Args:
        state: CLI state.
        repo_config: Repository configuration.
        
    Returns:
        Path to the prompt store.
    """
    if state.store_path and state.store_path.exists():
        return state.store_path

    store_path = get_store_path(state.promptlib_config, repo_config.central_repo)
    if not store_path.exists():
        msg = "Prompt store is not available locally. Run without --no-sync or execute a sync-enabled command first."
        _abort(state, msg)
    state.store_path = store_path
    return store_path
