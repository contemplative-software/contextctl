"""Typer CLI application for contextctl."""

from __future__ import annotations

from collections.abc import Sequence
from dataclasses import dataclass
from pathlib import Path
from typing import Final

import typer
import yaml
from rich import box
from rich.console import Console
from rich.table import Table
from rich.theme import Theme

from contextctl import (
    REPO_CONFIG_FILENAME,
    ConfigError,
    PromptLibConfig,
    RepoConfig,
    StoreSyncError,
    __version__,
    clear_store_cache,
    create_default_config,
    find_repo_root,
    get_store_path,
    load_repo_config,
    sync_central_repo,
)

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
    """Parse global options, configure shared state, and trigger pre-command sync."""
    if force_sync and no_sync:
        raise typer.BadParameter("--force-sync cannot be combined with --no-sync")

    state = _get_state(ctx, verbose=verbose, skip_sync=no_sync, force_sync=force_sync)
    command = ctx.invoked_subcommand
    if command is None or command in _SKIP_PREP_COMMANDS or state.prepared:
        return

    _prepare_environment(state)


@app.command()
def version(ctx: typer.Context) -> None:
    """Display the installed contextctl version."""
    state = _ensure_state(ctx)
    state.console.print(f"[success]contextctl {__version__}[/success]")


@app.command()
def init(ctx: typer.Context) -> None:
    """Interactive wizard that creates `.promptlib.yml` in the current repository."""
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
    """Attempt to load an existing `.promptlib.yml` for default values."""
    config_path = repo_root / REPO_CONFIG_FILENAME
    if not config_path.exists():
        return None
    try:
        return load_repo_config(repo_root)
    except ConfigError as exc:
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
