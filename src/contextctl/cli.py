"""Typer CLI application for contextctl."""

from __future__ import annotations

import json
import re
import shutil
import subprocess
import sys
from collections.abc import Mapping, Sequence
from dataclasses import dataclass
from pathlib import Path
from typing import Final, TypeVar

import typer
import yaml
from pydantic import ValidationError
from rich import box
from rich.console import Console
from rich.table import Table
from rich.theme import Theme
from rich.tree import Tree

from contextctl import (
    REPO_CONFIG_FILENAME,
    ConfigError,
    ContentError,
    PromptDocument,
    PromptLibConfig,
    RepoConfig,
    RuleDocument,
    StoreSyncError,
    __version__,
    clear_store_cache,
    create_default_config,
    filter_by_repo,
    filter_by_tags,
    find_repo_root,
    get_store_path,
    load_prompt,
    load_repo_config,
    load_rule,
    scan_prompts_dir,
    scan_rules_dir,
    search_prompts,
    sync_central_repo,
)
from contextctl.content import BaseDocument

CLI_THEME: Final[Theme] = Theme(
    {
        "info": "cyan",
        "warning": "yellow",
        "error": "bold red",
        "success": "green",
        "text": "white",
    }
)

app = typer.Typer(
    add_completion=False,
    no_args_is_help=True,
    pretty_exceptions_enable=False,
    help="Manage repo-aware prompt and rule libraries.",
)


@dataclass(slots=True)
class CLIState:
    """State shared between CLI commands during a single invocation."""

    console: Console
    promptlib_config: PromptLibConfig
    verbose: bool
    skip_sync: bool
    force_sync: bool
    prepared: bool = False
    repo_config: RepoConfig | None = None
    store_path: Path | None = None


@dataclass(frozen=True, slots=True)
class SetPreview:
    """Simple representation of the available rule or prompt sets."""

    name: str
    item_count: int
    sample_items: list[str]


@dataclass(frozen=True, slots=True)
class StorePreview:
    """Collection of preview information for store contents."""

    rule_sets: list[SetPreview]
    prompt_sets: list[SetPreview]


_SKIP_PREP_COMMANDS: Final[set[str]] = {"init"}
_SET_FILE_SUFFIXES: Final[tuple[str, ...]] = (".md", ".markdown", ".yml", ".yaml")
_RULE_FILE_SUFFIXES: Final[tuple[str, ...]] = (".md", ".markdown")
_RULE_OUTPUT_FORMATS: Final[tuple[str, ...]] = ("text", "json", "cursor")
_CURSOR_RULE_FILENAME: Final[str] = "contextctl.mdc"
_RULE_SECTION_DIVIDER: Final[str] = "\n\n---\n\n"
_PROMPT_FILE_SUFFIXES: Final[tuple[str, ...]] = (".md", ".markdown")
_DEFAULT_PAGE_SIZE: Final[int] = 20
_MAX_PAGE_SIZE: Final[int] = 200
_SNIPPET_CONTEXT_CHARS: Final[int] = 120
_PROMPT_OUTPUT_FORMATS: Final[tuple[str, ...]] = ("text", "json")
_VARIABLE_PATTERN: Final[re.Pattern[str]] = re.compile(r"{{\s*([A-Za-z0-9_.-]+)\s*}}")
_REPO_MATCH_ICON: Final[str] = "[success]●[/success]"
_REPO_NON_MATCH_ICON: Final[str] = "[dim]○[/dim]"

DocumentT = TypeVar("DocumentT")


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
    existing_config = _load_existing_config(repo_root, console)
    if config_path.exists() and not _confirm_overwrite(console):
        console.print("[warning]Initialization cancelled; existing configuration preserved.")
        return

    console.print("[info]Welcome to the contextctl initialization wizard.[/info]")
    central_repo = _prompt_central_repo(existing_config)

    preview: StorePreview | None = None
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
        preview = _load_store_preview(
            central_repo,
            promptlib_config=state.promptlib_config,
            console=console,
        )

    rule_sets = _prompt_set_selection(
        console,
        label="rule",
        previews=preview.rule_sets if preview else [],
        defaults=existing_config.rules if existing_config else None,
    )
    prompt_sets = _prompt_set_selection(
        console,
        label="prompt",
        previews=preview.prompt_sets if preview else [],
        defaults=existing_config.prompt_sets if existing_config else None,
    )

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

    _write_repo_config_file(config_path, repo_config)
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
        documents = _load_selected_rules(store_path, repo_config.rules)
    except ContentError as exc:
        _abort(state, str(exc))
        return

    format_value = output_format or state.promptlib_config.default_output_format
    normalized_format = format_value.strip().casefold()
    if normalized_format not in _RULE_OUTPUT_FORMATS:
        supported = ", ".join(_RULE_OUTPUT_FORMATS)
        _abort(state, f"Unsupported format '{format_value}'. Supported values: {supported}.")
        return

    _render_rule_summary(state.console, documents, store_path)
    formatted_output = _format_rules(documents, normalized_format, store_path)
    state.console.print()
    state.console.print(formatted_output, markup=False)

    if save:
        repo_root = find_repo_root()
        cursor_payload = _format_rules(documents, "cursor", store_path)
        saved_path = _write_cursor_rules_file(cursor_payload, repo_root=repo_root)
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
        documents = _load_prompt_documents(store_path, repo_config.prompt_sets)
    except ContentError as exc:
        _abort(state, str(exc))
        return

    repo_slug = _resolve_repo_slug()
    filtered = documents if all_prompts else filter_by_repo(documents, repo_slug)
    tag_filters = list(tag or [])
    filtered = filter_by_tags(filtered, tag_filters, match_all=match_all_tags)

    if not filtered:
        scope = "all prompts" if all_prompts else f"repo '{repo_slug or 'unknown'}'"
        if tag_filters:
            scope = f"{scope} with tags {', '.join(tag_filters)}"
        state.console.print(f"[warning]No prompts matched {scope}. Try relaxing the filters or use --all.[/warning]")
        return

    paginated, total_pages, resolved_page = _paginate_items(filtered, page, per_page)
    if page > total_pages:
        state.console.print(
            f"[warning]Requested page {page} exceeds total pages ({total_pages}). "
            f"Showing page {resolved_page} instead.[/warning]"
        )

    _render_prompt_table(
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
        documents = _load_prompt_documents(store_path, repo_config.prompt_sets)
    except ContentError as exc:
        _abort(state, str(exc))
        return

    repo_slug = _resolve_repo_slug()
    filtered = documents if all_prompts else filter_by_repo(documents, repo_slug)
    tag_filters = list(tag or [])
    filtered = filter_by_tags(filtered, tag_filters)

    results = _execute_search(filtered, query, exact=exact)
    if not results:
        scope = "all prompts" if all_prompts else f"repo '{repo_slug or 'unknown'}'"
        state.console.print(
            f"[warning]No prompts matched query '{query}' within {scope}. "
            f"Try --all or adjust the search terms.[/warning]"
        )
        return

    limited_results = results[:limit]
    _render_search_results(
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
        documents = _load_prompt_documents(store_path, repo_config.prompt_sets)
    except ContentError as exc:
        _abort(state, str(exc))
        return

    repo_slug = _resolve_repo_slug()
    search_space = documents if all_prompts else filter_by_repo(documents, repo_slug)
    document = _find_prompt_by_id(search_space, prompt_id)
    if document is None:
        scope = "all prompts" if all_prompts else f"repo '{repo_slug or 'unknown'}'"
        available = ", ".join(sorted(doc.metadata.prompt_id for doc in search_space)) or "none"
        msg = f"Prompt '{prompt_id}' was not found within {scope}. Available prompts: {available}."
        _abort(state, msg)
        return

    try:
        assignments = _parse_variable_assignments(var)
    except ValueError as exc:
        _abort(state, str(exc))
        return

    rendered_body, missing_vars, used_vars = _apply_prompt_variables(document.body, assignments)
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

    formatted_output = _format_prompt_output(document, rendered_body, normalized_format, store_path)

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
            _copy_to_clipboard(formatted_output)
        except RuntimeError as exc:
            _abort(state, f"Unable to copy prompt to clipboard: {exc}")
            return
        state.console.print(f"[success]Copied prompt '{document.metadata.prompt_id}' to clipboard.[/success]")

    if output_path is not None:
        try:
            written_path = _write_output_file(output_path, formatted_output)
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

    repo_slug = _resolve_repo_slug()
    if repo_only:
        prompt_documents = filter_by_repo(prompt_documents, repo_slug)
        rule_documents = filter_by_repo(rule_documents, repo_slug)

    _render_library_tree(
        state.console,
        prompt_documents,
        rule_documents,
        store_path=store_path,
        repo_slug=repo_slug,
        collapse_prompts=collapse_prompts,
        collapse_rules=collapse_rules,
    )


def _get_state(ctx: typer.Context, *, verbose: bool, skip_sync: bool, force_sync: bool) -> CLIState:
    """Return the CLI state stored on the Typer context, creating it if necessary."""
    state = ctx.obj
    if not isinstance(state, CLIState):
        ctx.obj = state = CLIState(
            console=_build_console(verbose),
            promptlib_config=PromptLibConfig(),
            verbose=verbose,
            skip_sync=skip_sync,
            force_sync=force_sync,
        )
        return state

    state.console = _build_console(verbose)
    state.verbose = verbose
    state.skip_sync = skip_sync
    state.force_sync = force_sync
    return state


def _prepare_environment(state: CLIState) -> None:
    """Load repo configuration and, unless disabled, sync the prompt store."""
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


def _build_console(verbose: bool) -> Console:
    """Return a Rich console configured with project-specific styling."""
    return Console(
        theme=CLI_THEME,
        highlight=False,
        soft_wrap=True,
        stderr=False,
        log_path=False,
        log_time=verbose,
    )


def _force_refresh_cache(state: CLIState, repo_config: RepoConfig) -> None:
    """Remove the cached store before syncing when `--force-sync` is provided."""
    store_path = get_store_path(state.promptlib_config, repo_config.central_repo)
    store_root = state.promptlib_config.store_root
    try:
        store_path.relative_to(store_root)
    except ValueError:
        return
    clear_store_cache(store_path)


def _abort(state: CLIState, message: str, *, exit_code: int = 1) -> None:
    """Print a styled error message and exit the CLI."""
    state.console.print(f"[error]Error:[/error] {message}")
    raise typer.Exit(code=exit_code)


def _ensure_state(ctx: typer.Context) -> CLIState:
    """Return the CLI state, creating a minimal default if the callback was bypassed."""
    state = ctx.obj
    if isinstance(state, CLIState):
        return state
    fallback_state = CLIState(
        console=_build_console(verbose=False),
        promptlib_config=PromptLibConfig(),
        verbose=False,
        skip_sync=True,
        force_sync=False,
    )
    ctx.obj = fallback_state
    return fallback_state


def _load_existing_config(repo_root: Path, console: Console) -> RepoConfig | None:
    """Attempt to load an existing `.promptlib.yml` for default values.

    Loads the YAML file directly without applying environment overrides to avoid
    baking transient environment values into the persisted configuration.
    """
    config_path = repo_root / REPO_CONFIG_FILENAME
    if not config_path.exists():
        return None
    try:
        raw_config = yaml.safe_load(config_path.read_text(encoding="utf-8")) or {}
        return RepoConfig.model_validate(raw_config)
    except (yaml.YAMLError, ValidationError) as exc:
        console.print(f"[warning]Existing configuration is invalid: {exc}[/warning]")
        return None


def _confirm_overwrite(console: Console) -> bool:
    """Prompt the user before overwriting an existing config file."""
    return typer.confirm(
        "[warning].promptlib.yml already exists. Overwrite it?[/warning]",
        default=False,
    )


def _prompt_central_repo(existing_config: RepoConfig | None) -> str:
    """Prompt the user for the central prompt repository location."""
    while True:
        if existing_config is not None:
            value: str = typer.prompt(
                "Central prompt repository URL or local path", default=existing_config.central_repo
            )
        else:
            value = typer.prompt("Central prompt repository URL or local path")
        normalized = value.strip()
        if normalized:
            return normalized
        typer.echo("Central repository cannot be blank. Please provide a value.")


def _load_store_preview(
    central_repo: str,
    *,
    promptlib_config: PromptLibConfig,
    console: Console,
) -> StorePreview | None:
    """Sync the store once to preview available rule and prompt sets."""
    try:
        store_path = sync_central_repo(
            central_repo,
            promptlib_config=promptlib_config,
            console=console,
        )
    except StoreSyncError as exc:
        console.print(f"[warning]Unable to preview central store: {exc}[/warning]")
        return None

    rule_sets = _collect_set_previews(store_path / "rules")
    prompt_sets = _collect_set_previews(store_path / "prompts")

    if rule_sets:
        _render_set_preview(console, "Rule Sets", rule_sets)
    else:
        console.print("[warning]No rule sets were discovered in the central store.[/warning]")

    if prompt_sets:
        _render_set_preview(console, "Prompt Sets", prompt_sets)
    else:
        console.print("[warning]No prompt sets were discovered in the central store.[/warning]")

    return StorePreview(rule_sets=rule_sets, prompt_sets=prompt_sets)


def _collect_set_previews(base_dir: Path) -> list[SetPreview]:
    """Inspect the provided directory and return previews for each set."""
    if not base_dir.exists() or not base_dir.is_dir():
        return []

    directories = sorted(child for child in base_dir.iterdir() if child.is_dir())
    previews: list[SetPreview] = []

    for directory in directories:
        files = _list_allowed_files(directory)
        if not files:
            continue
        previews.append(
            SetPreview(
                name=directory.name,
                item_count=len(files),
                sample_items=_summarize_files(files),
            )
        )

    if previews:
        return previews

    files = _list_allowed_files(base_dir)
    return [
        SetPreview(
            name=path.stem,
            item_count=1,
            sample_items=[path.stem],
        )
        for path in files
    ]


def _list_allowed_files(directory: Path) -> list[Path]:
    """Return files within the directory matching supported suffixes."""
    allowed = tuple(suffix.lower() for suffix in _SET_FILE_SUFFIXES)
    results = [path for path in sorted(directory.rglob("*")) if path.is_file() and path.suffix.lower() in allowed]
    return results


def _summarize_files(files: Sequence[Path], limit: int = 3) -> list[str]:
    """Return a short preview of file stems for display."""
    items = [path.stem for path in files[:limit]]
    if len(files) > limit:
        items.append("...")
    return items


def _render_set_preview(console: Console, title: str, previews: Sequence[SetPreview]) -> None:
    """Render a table describing available prompt or rule sets."""
    table = Table(title=title, header_style="bold", show_lines=False, box=box.MINIMAL_DOUBLE_HEAD)
    table.add_column("Set", style="info")
    table.add_column("Items", justify="right")
    table.add_column("Sample documents", style="text")

    for preview in previews:
        sample = ", ".join(preview.sample_items) if preview.sample_items else "-"
        table.add_row(preview.name, str(preview.item_count), sample)

    console.print(table)


def _prompt_set_selection(
    console: Console,
    *,
    label: str,
    previews: Sequence[SetPreview],
    defaults: Sequence[str] | None,
) -> list[str]:
    """Prompt the user to select rule or prompt sets."""
    available = {preview.name.casefold(): preview.name for preview in previews}
    default_value = ",".join(defaults) if defaults else ""

    while True:
        response: str = typer.prompt(
            f"Select {label} sets (comma-separated, blank for none)",
            default=default_value,
        )
        selections = _normalize_csv(response)
        if not selections:
            return []

        normalized: list[str] = []
        unknown: list[str] = []
        for selection in selections:
            key = selection.casefold()
            if available:
                match = available.get(key)
                if match is None:
                    unknown.append(selection)
                elif match not in normalized:
                    normalized.append(match)
            elif selection not in normalized:
                normalized.append(selection)

        if unknown and available:
            console.print(
                f"[warning]Unknown {label} sets: {', '.join(unknown)}. "
                f"Known sets: {', '.join(sorted(available.values()))}[/warning]"
            )
            continue

        return normalized


def _normalize_csv(raw_value: str) -> list[str]:
    """Split comma-separated input and remove duplicates."""
    seen: set[str] = set()
    results: list[str] = []
    for part in raw_value.split(","):
        trimmed = part.strip()
        if not trimmed:
            continue
        key = trimmed.casefold()
        if key in seen:
            continue
        seen.add(key)
        results.append(trimmed)
    return results


def _write_repo_config_file(config_path: Path, config: RepoConfig) -> None:
    """Serialize the RepoConfig to YAML on disk."""
    payload = {
        "central_repo": config.central_repo,
        "rules": config.rules,
        "prompt_sets": config.prompt_sets,
    }
    if config.version_lock is not None:
        payload["version_lock"] = config.version_lock

    config_path.write_text(
        yaml.safe_dump(payload, sort_keys=False),
        encoding="utf-8",
    )


def _require_store_path(state: CLIState, repo_config: RepoConfig) -> Path:
    """Return the path to the prompt store, ensuring it exists locally."""
    if state.store_path and state.store_path.exists():
        return state.store_path

    store_path = get_store_path(state.promptlib_config, repo_config.central_repo)
    if not store_path.exists():
        msg = "Prompt store is not available locally. Run without --no-sync or execute a sync-enabled command first."
        _abort(state, msg)
    state.store_path = store_path
    return store_path


def _load_selected_rules(store_path: Path, selections: Sequence[str]) -> list[RuleDocument]:
    """Load and return rule documents that match the configured selections."""
    rules_root = (store_path / "rules").resolve()
    if not rules_root.exists() or not rules_root.is_dir():
        msg = f"No rules directory found under {store_path}"
        raise ContentError(msg)

    documents: list[RuleDocument] = []
    for selection in selections:
        normalized = selection.strip()
        if not normalized:
            continue
        matched = _load_rules_for_selection(rules_root, normalized)
        if not matched:
            msg = f"No rule documents matched '{selection}'."
            raise ContentError(msg)
        documents.extend(matched)

    if not documents:
        msg = "No rule documents were loaded for the configured rule sets."
        raise ContentError(msg)
    return documents


def _load_rules_for_selection(rules_root: Path, selection: str) -> list[RuleDocument]:
    """Return RuleDocument instances for a specific selection entry."""
    directory = _resolve_selection_directory(rules_root, selection)
    if directory is not None:
        files = _collect_rule_files(directory)
        return [load_rule(path) for path in files]

    files = _resolve_selection_files(rules_root, selection)
    return [load_rule(path) for path in files]


def _resolve_selection_directory(rules_root: Path, selection: str) -> Path | None:
    """Return the directory that matches the selection, if present."""
    candidate = (rules_root / selection).resolve()
    root = rules_root.resolve()
    if not _is_within_root(candidate, root):
        return None
    if candidate.is_dir():
        return candidate
    return None


def _resolve_selection_files(rules_root: Path, selection: str) -> list[Path]:
    """Return file paths that match a selection string."""
    root = rules_root.resolve()

    candidate = (rules_root / selection).resolve()
    if candidate.is_file() and _is_within_root(candidate, root):
        return [candidate]

    selection_path = Path(selection)
    if not selection_path.suffix:
        for suffix in _RULE_FILE_SUFFIXES:
            candidate_with_suffix = (rules_root / selection_path).with_suffix(suffix).resolve()
            if candidate_with_suffix.is_file() and _is_within_root(candidate_with_suffix, root):
                return [candidate_with_suffix]

    if len(selection_path.parts) == 1:
        matches = [path for path in _collect_rule_files(rules_root) if path.stem == selection_path.stem]
        if matches:
            return matches

    return []


def _collect_rule_files(directory: Path) -> list[Path]:
    """Return rule documents discovered beneath the provided directory."""
    return [
        path for path in sorted(directory.rglob("*")) if path.is_file() and path.suffix.lower() in _RULE_FILE_SUFFIXES
    ]


def _is_within_root(path: Path, root: Path) -> bool:
    """Return True if the provided path is within the expected root directory."""
    try:
        path.relative_to(root)
    except ValueError:
        return False
    return True


def _render_rule_summary(console: Console, documents: Sequence[RuleDocument], store_path: Path) -> None:
    """Render a table summarizing the merged rule metadata."""
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
        source = _relative_source(document.path, store_path)
        table.add_row(
            metadata.rule_id,
            metadata.version,
            tags,
            repos,
            source,
        )

    console.print(table)


def _format_rules(documents: Sequence[RuleDocument], format_name: str, store_path: Path) -> str:
    """Return the merged rule content formatted according to the requested output."""
    if format_name == "text":
        return _format_rules_as_text(documents)
    if format_name == "json":
        return _format_rules_as_json(documents, store_path)
    if format_name == "cursor":
        return _format_rules_as_cursor(documents)
    msg = f"Unsupported format: {format_name}"
    raise ValueError(msg)


def _format_rules_as_text(documents: Sequence[RuleDocument]) -> str:
    """Return merged rule content as plain text with lightweight headings."""
    sections: list[str] = []
    for document in documents:
        header = f"# {document.metadata.rule_id}"
        body = document.body.strip()
        sections.append(f"{header}\n\n{body}")
    return _RULE_SECTION_DIVIDER.join(sections).strip()


def _format_rules_as_json(documents: Sequence[RuleDocument], store_path: Path) -> str:
    """Return merged rule content as a JSON array."""
    payload: list[dict[str, object]] = []
    for document in documents:
        metadata = document.metadata
        payload.append(
            {
                "id": metadata.rule_id,
                "tags": metadata.tags,
                "repos": metadata.repos,
                "agents": metadata.agents,
                "version": metadata.version,
                "body": document.body,
                "source": _relative_source(document.path, store_path),
            }
        )
    return json.dumps(payload, indent=2, ensure_ascii=False)


def _format_rules_as_cursor(documents: Sequence[RuleDocument]) -> str:
    """Return merged rule content optimized for `.cursor/rules` consumption."""
    sections: list[str] = []
    for document in documents:
        metadata = document.metadata
        lines = [
            f"# {metadata.rule_id}",
            "",
            f"*Version:* {metadata.version}",
        ]
        if metadata.tags:
            lines.append(f"*Tags:* {', '.join(metadata.tags)}")
        if metadata.repos:
            lines.append(f"*Repos:* {', '.join(metadata.repos)}")
        if metadata.agents:
            lines.append(f"*Agents:* {', '.join(metadata.agents)}")
        lines.append("")
        lines.append(document.body.strip())
        sections.append("\n".join(lines).strip())
    return f"{_RULE_SECTION_DIVIDER}".join(sections).strip() + "\n"


def _relative_source(path: Path, store_path: Path) -> str:
    """Return the document path relative to the store root, if possible."""
    try:
        return path.relative_to(store_path).as_posix()
    except ValueError:
        return path.as_posix()


def _write_cursor_rules_file(content: str, *, repo_root: Path) -> Path:
    """Persist Cursor-formatted rules within `.cursor/rules/`."""
    rules_dir = repo_root / ".cursor" / "rules"
    rules_dir.mkdir(parents=True, exist_ok=True)
    target = rules_dir / _CURSOR_RULE_FILENAME
    target.write_text(content, encoding="utf-8")
    return target


def _render_prompt_table(
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
    """Render a Rich table summarizing prompts for the list command."""
    table = Table(title="Prompts", header_style="bold", show_lines=False, box=box.MINIMAL_DOUBLE_HEAD)
    table.add_column("Prompt ID", style="info")
    table.add_column("Title", style="text")
    table.add_column("Tags")
    table.add_column("Agents")

    for document in prompts:
        metadata = document.metadata
        tags = ", ".join(metadata.tags) or "-"
        agents = ", ".join(metadata.agents) or "all"
        title = _prompt_display_title(document)
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


def _render_search_results(
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
    """Display search results with contextual snippets."""
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
        snippet = _build_search_snippet(document, query)
        table.add_row(
            metadata.prompt_id,
            _prompt_display_title(document),
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


def _prompt_display_title(document: PromptDocument) -> str:
    """Return a user-friendly prompt title."""
    metadata = document.metadata
    if metadata.title:
        return metadata.title
    candidate = metadata.prompt_id.replace("-", " ").replace("_", " ").strip()
    return candidate.title() or metadata.prompt_id


def _resolve_repo_slug() -> str | None:
    """Return the repository slug derived from the git root directory name."""
    try:
        return find_repo_root().name
    except ConfigError:
        return None


def _load_prompt_documents(store_path: Path, selections: Sequence[str]) -> list[PromptDocument]:
    """Load prompt documents honoring the configured prompt set selections."""
    prompts_root = (store_path / "prompts").resolve()
    if not prompts_root.exists() or not prompts_root.is_dir():
        msg = f"No prompts directory found under {store_path}"
        raise ContentError(msg)

    if not selections:
        files = _collect_prompt_files(prompts_root)
        return [load_prompt(path) for path in files]

    seen: set[Path] = set()
    ordered_paths: list[Path] = []

    for selection in selections:
        normalized = selection.strip()
        if not normalized:
            continue
        matched_paths = _load_prompts_for_selection(prompts_root, normalized)
        if not matched_paths:
            msg = f"No prompt documents matched '{selection}'."
            raise ContentError(msg)
        for path in matched_paths:
            resolved = path.resolve()
            if resolved in seen:
                continue
            seen.add(resolved)
            ordered_paths.append(resolved)

    if not ordered_paths:
        msg = "No prompt documents were loaded for the configured prompt sets."
        raise ContentError(msg)

    return [load_prompt(path) for path in ordered_paths]


def _load_prompts_for_selection(prompts_root: Path, selection: str) -> list[Path]:
    """Return prompt file paths for a specific selection entry."""
    directory = _resolve_selection_directory(prompts_root, selection)
    if directory is not None:
        return _collect_prompt_files(directory)
    return _resolve_prompt_selection_files(prompts_root, selection)


def _resolve_prompt_selection_files(prompts_root: Path, selection: str) -> list[Path]:
    """Return prompt file paths that match a selection string."""
    root = prompts_root.resolve()

    candidate = (prompts_root / selection).resolve()
    if candidate.is_file() and _is_within_root(candidate, root):
        return [candidate]

    selection_path = Path(selection)
    if not selection_path.suffix:
        for suffix in _PROMPT_FILE_SUFFIXES:
            candidate_with_suffix = (prompts_root / selection_path).with_suffix(suffix).resolve()
            if candidate_with_suffix.is_file() and _is_within_root(candidate_with_suffix, root):
                return [candidate_with_suffix]

    if len(selection_path.parts) == 1:
        matches = [path for path in _collect_prompt_files(prompts_root) if path.stem == selection_path.stem]
        if matches:
            return matches

    return []


def _collect_prompt_files(directory: Path) -> list[Path]:
    """Return prompt documents discovered beneath the provided directory."""
    return [
        path
        for path in sorted(directory.rglob("*"))
        if path.is_file() and path.suffix.lower() in _PROMPT_FILE_SUFFIXES
    ]


def _paginate_items[DocumentT: BaseDocument](
    items: Sequence[DocumentT], page: int, per_page: int
) -> tuple[list[DocumentT], int, int]:
    """Return paginated items, total pages, and the resolved page number."""
    if not items:
        return [], 1, 1
    total = len(items)
    total_pages = max(1, (total + per_page - 1) // per_page)
    resolved_page = min(page, total_pages)
    start = (resolved_page - 1) * per_page
    end = start + per_page
    return list(items[start:end]), total_pages, resolved_page


def _execute_search(documents: Sequence[PromptDocument], query: str, *, exact: bool) -> list[PromptDocument]:
    """Execute a fuzzy or exact search across prompt documents."""
    if exact:
        normalized_query = query.casefold()
        results: list[PromptDocument] = []
        for document in documents:
            if normalized_query in _prompt_search_haystack(document):
                results.append(document)
        return results
    return search_prompts(documents, query)


def _prompt_search_haystack(document: PromptDocument) -> str:
    """Return the lowercased haystack string for prompt searching."""
    metadata = document.metadata
    parts = [
        metadata.prompt_id,
        metadata.title or "",
        " ".join(metadata.tags),
        " ".join(metadata.repos),
        " ".join(metadata.agents),
        document.body,
    ]
    return " ".join(parts).casefold()


def _build_search_snippet(document: PromptDocument, query: str) -> str:
    """Return a contextual snippet for a search result."""
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


def _find_prompt_by_id(documents: Sequence[PromptDocument], prompt_id: str) -> PromptDocument | None:
    """Return the prompt document whose id matches the provided value."""
    normalized = prompt_id.strip().casefold()
    if not normalized:
        return None
    for document in documents:
        if document.metadata.prompt_id.casefold() == normalized:
            return document
    return None


def _parse_variable_assignments(assignments: Sequence[str] | None) -> dict[str, str]:
    """Parse `--var` key=value pairs into a dictionary."""
    if not assignments:
        return {}
    parsed: dict[str, str] = {}
    for assignment in assignments:
        if "=" not in assignment:
            msg = f"Invalid variable assignment '{assignment}'. Expected KEY=VALUE."
            raise ValueError(msg)
        key, value = assignment.split("=", 1)
        normalized_key = key.strip()
        if not normalized_key:
            msg = "Variable names cannot be blank."
            raise ValueError(msg)
        parsed[normalized_key] = value
    return parsed


def _apply_prompt_variables(
    body: str,
    assignments: Mapping[str, str],
) -> tuple[str, set[str], set[str]]:
    """Substitute `{{variable}}` placeholders using the provided assignments."""
    if not assignments:
        return body, set(), set()

    missing: set[str] = set()
    used: set[str] = set()

    def replacer(match: re.Match[str]) -> str:
        key = match.group(1)
        value = assignments.get(key)
        if value is None:
            missing.add(key)
            return match.group(0)
        used.add(key)
        return value

    rendered = _VARIABLE_PATTERN.sub(replacer, body)
    return rendered, missing, used


def _format_prompt_output(
    document: PromptDocument,
    body: str,
    format_name: str,
    store_path: Path,
) -> str:
    """Return the rendered prompt in the requested output format."""
    if format_name == "text":
        if body.endswith("\n"):
            return body
        return f"{body}\n"

    if format_name == "json":
        metadata = document.metadata
        payload = {
            "id": metadata.prompt_id,
            "title": metadata.title,
            "tags": metadata.tags,
            "repos": metadata.repos,
            "agents": metadata.agents,
            "version": metadata.version,
            "body": body,
            "source": _relative_source(document.path, store_path),
        }
        return json.dumps(payload, indent=2, ensure_ascii=False)

    msg = f"Unsupported prompt output format: {format_name}"
    raise ValueError(msg)


def _write_output_file(path: Path, content: str) -> Path:
    """Persist rendered prompt content to disk and return the resulting path."""
    target = path.expanduser()
    if target.exists() and target.is_dir():
        msg = f"{target} is a directory"
        raise OSError(msg)
    target.parent.mkdir(parents=True, exist_ok=True)
    target.write_text(content, encoding="utf-8")
    return target.resolve()


def _copy_to_clipboard(content: str) -> None:
    """Copy the provided text to the system clipboard."""
    try:
        import pyperclip  # type: ignore[import-untyped]
    except ImportError:  # pragma: no cover - optional dependency
        pyperclip = None

    if pyperclip is not None:  # pragma: no branch - simplified for readability
        try:
            pyperclip.copy(content)  # type: ignore[call-arg, unused-ignore]
            return
        except Exception as exc:  # pragma: no cover - pyperclip-specific
            raise RuntimeError(str(exc)) from exc

    platform = sys.platform
    if platform == "darwin":
        _run_clipboard_command(["pbcopy"], content)
        return
    if platform.startswith("win"):
        _run_clipboard_command(["clip"], content)
        return

    for command in (["xclip", "-selection", "clipboard"], ["wl-copy"]):
        if shutil.which(command[0]) is None:
            continue
        _run_clipboard_command(command, content)
        return

    msg = "Clipboard integration is not available on this platform."
    raise RuntimeError(msg)


def _run_clipboard_command(command: list[str], content: str) -> None:
    """Execute a clipboard command with the provided string content."""
    try:
        subprocess.run(command, input=content.encode("utf-8"), check=True)
    except (OSError, subprocess.CalledProcessError) as exc:  # pragma: no cover - platform dependent
        msg = f"Clipboard command {' '.join(command)} failed: {exc}"
        raise RuntimeError(msg) from exc


def _render_library_tree(
    console: Console,
    prompts: Sequence[PromptDocument],
    rules: Sequence[RuleDocument],
    *,
    store_path: Path,
    repo_slug: str | None,
    collapse_prompts: bool,
    collapse_rules: bool,
) -> None:
    """Render a Rich tree describing the prompt and rule library."""
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
    """Populate a Rich tree branch with document entries grouped by directory."""
    if not documents:
        return

    node_cache: dict[tuple[str, ...], Tree] = {}

    def sorter(document: BaseDocument) -> tuple[str, ...]:
        relative = _relative_to_base(document.path, base_dir)
        identifier = _document_identifier(document)
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

        current.add(_format_tree_label(document, repo_slug))


def _format_tree_label(document: BaseDocument, repo_slug: str | None) -> str:
    """Return the textual label for a tree leaf node."""
    identifier = _document_identifier(document)
    metadata = document.metadata
    relevant = _is_repo_relevant(metadata.repos, repo_slug)
    icon = _REPO_MATCH_ICON if relevant else _REPO_NON_MATCH_ICON
    tags = ", ".join(metadata.tags) or "-"
    version = metadata.version
    return f"{icon} {identifier} [dim](v{version}; tags: {tags})[/dim]"


def _document_identifier(document: BaseDocument) -> str:
    """Return the identifier for either a prompt or rule document."""
    metadata = document.metadata
    prompt_id = getattr(metadata, "prompt_id", None)
    if isinstance(prompt_id, str):
        return prompt_id
    rule_id = getattr(metadata, "rule_id", None)
    if isinstance(rule_id, str):
        return rule_id
    return document.path.stem


def _is_repo_relevant(repos: Sequence[str], repo_slug: str | None) -> bool:
    """Return True if the repo slug is included in the metadata repos."""
    if not repos:
        return True
    if repo_slug is None:
        return False
    normalized = repo_slug.strip().casefold()
    if not normalized:
        return False
    return any(repo.strip().casefold() == normalized for repo in repos)


def _relative_to_base(path: Path, base_dir: Path) -> Path:
    """Return path relative to base_dir, falling back to filename on mismatch."""
    try:
        return path.resolve().relative_to(base_dir.resolve())
    except ValueError:
        return Path(path.name)
