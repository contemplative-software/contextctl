"""Init command implementation for interactive configuration setup."""

from __future__ import annotations

from collections.abc import Sequence
from pathlib import Path

import typer
import yaml
from pydantic import ValidationError
from rich import box
from rich.console import Console
from rich.table import Table

from contextctl import (
    REPO_CONFIG_FILENAME,
    PromptLibConfig,
    RepoConfig,
    StoreSyncError,
    sync_central_repo,
)
from contextctl._internal.loaders import list_allowed_files
from contextctl._internal.utils import SetPreview, StorePreview, normalize_csv, summarize_files


def load_existing_config(repo_root: Path, console: Console) -> RepoConfig | None:
    """Attempt to load an existing `.promptlib.yml` for default values.

    Loads the YAML file directly without applying environment overrides to avoid
    baking transient environment values into the persisted configuration.

    Args:
        repo_root: Repository root directory.
        console: Rich console for warnings.

    Returns:
        Loaded RepoConfig or None if not found or invalid.
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


def confirm_overwrite(console: Console) -> bool:
    """Prompt the user before overwriting an existing config file.

    Args:
        console: Rich console (unused but kept for consistency).

    Returns:
        True if user confirms overwrite.
    """
    return typer.confirm(
        "[warning].promptlib.yml already exists. Overwrite it?[/warning]",
        default=False,
    )


def prompt_central_repo(existing_config: RepoConfig | None) -> str:
    """Prompt the user for the central prompt repository location.

    Args:
        existing_config: Existing configuration for default value.

    Returns:
        Central repository URL or path.
    """
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


def load_store_preview(
    central_repo: str,
    *,
    promptlib_config: PromptLibConfig,
    console: Console,
) -> StorePreview | None:
    """Sync the store once to preview available rule and prompt sets.

    Args:
        central_repo: Central repository URL or path.
        promptlib_config: Global prompt library configuration.
        console: Rich console for output.

    Returns:
        StorePreview with available sets or None if sync fails.
    """
    try:
        store_path = sync_central_repo(
            central_repo,
            promptlib_config=promptlib_config,
            console=console,
        )
    except StoreSyncError as exc:
        console.print(f"[warning]Unable to preview central store: {exc}[/warning]")
        return None

    rule_sets = collect_set_previews(store_path / "rules")
    prompt_sets = collect_set_previews(store_path / "prompts")

    if rule_sets:
        render_set_preview(console, "Rule Sets", rule_sets)
    else:
        console.print("[warning]No rule sets were discovered in the central store.[/warning]")

    if prompt_sets:
        render_set_preview(console, "Prompt Sets", prompt_sets)
    else:
        console.print("[warning]No prompt sets were discovered in the central store.[/warning]")

    return StorePreview(rule_sets=rule_sets, prompt_sets=prompt_sets)


def collect_set_previews(base_dir: Path) -> list[SetPreview]:
    """Inspect the provided directory and return previews for each set.

    Args:
        base_dir: Directory containing sets (rules or prompts).

    Returns:
        List of SetPreview instances.
    """
    if not base_dir.exists() or not base_dir.is_dir():
        return []

    directories = sorted(child for child in base_dir.iterdir() if child.is_dir())
    previews: list[SetPreview] = []

    for directory in directories:
        files = list_allowed_files(directory)
        if not files:
            continue
        previews.append(
            SetPreview(
                name=directory.name,
                item_count=len(files),
                sample_items=summarize_files(files),
            )
        )

    if previews:
        return previews

    files = list_allowed_files(base_dir)
    return [
        SetPreview(
            name=path.stem,
            item_count=1,
            sample_items=[path.stem],
        )
        for path in files
    ]


def render_set_preview(console: Console, title: str, previews: Sequence[SetPreview]) -> None:
    """Render a table describing available prompt or rule sets.

    Args:
        console: Rich console for output.
        title: Table title.
        previews: Set previews to display.
    """
    table = Table(title=title, header_style="bold", show_lines=False, box=box.MINIMAL_DOUBLE_HEAD)
    table.add_column("Set", style="info")
    table.add_column("Items", justify="right")
    table.add_column("Sample documents", style="text")

    for preview in previews:
        sample = ", ".join(preview.sample_items) if preview.sample_items else "-"
        table.add_row(preview.name, str(preview.item_count), sample)

    console.print(table)


def prompt_set_selection(
    console: Console,
    *,
    label: str,
    previews: Sequence[SetPreview],
    defaults: Sequence[str] | None,
) -> list[str]:
    """Prompt the user to select rule or prompt sets.

    Args:
        console: Rich console for output.
        label: Label for the sets (e.g., "rule" or "prompt").
        previews: Available set previews.
        defaults: Default selections.

    Returns:
        List of selected set identifiers.
    """
    available = {preview.name.casefold(): preview.name for preview in previews}
    default_value = ",".join(defaults) if defaults else ""

    while True:
        response: str = typer.prompt(
            f"Select {label} sets (comma-separated, blank for none)",
            default=default_value,
        )
        selections = normalize_csv(response)
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


def write_repo_config_file(config_path: Path, config: RepoConfig) -> None:
    """Serialize the RepoConfig to YAML on disk.

    Args:
        config_path: Path to write the configuration file.
        config: Repository configuration to write.
    """
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
