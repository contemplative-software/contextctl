"""CLI state management."""

from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
from typing import Final

from rich.console import Console
from rich.theme import Theme

from contextctl.models import PromptLibConfig, RepoConfig

CLI_THEME: Final[Theme] = Theme(
    {
        "info": "cyan",
        "warning": "yellow",
        "error": "bold red",
        "success": "green",
        "text": "white",
    }
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


def build_console(verbose: bool) -> Console:
    """Return a Rich console configured with project-specific styling.

    Args:
        verbose: Whether to enable verbose logging with timestamps.

    Returns:
        Configured Console instance.
    """
    return Console(
        theme=CLI_THEME,
        highlight=False,
        soft_wrap=True,
        stderr=False,
        log_path=False,
        log_time=verbose,
    )
