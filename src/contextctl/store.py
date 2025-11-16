"""Central prompt store synchronization helpers."""

from __future__ import annotations

import hashlib
import re
import shutil
from pathlib import Path

from git import GitCommandError, InvalidGitRepositoryError, NoSuchPathError, Repo
from rich.console import Console
from rich.progress import Progress, SpinnerColumn, TextColumn, TimeElapsedColumn

from contextctl.models import PromptLibConfig


class StoreSyncError(RuntimeError):
    """Raised when the central prompt library cannot be synchronized."""


def ensure_store_root(store_root: Path) -> Path:
    """Create the store root if it does not already exist.

    Args:
        store_root: Directory that should host cached prompt stores.

    Returns:
        Path pointing to the ensured store root directory.
    """
    store_root.mkdir(parents=True, exist_ok=True)
    return store_root


def clear_store_cache(store_path: Path) -> None:
    """Remove the cached repository at the provided path.

    Args:
        store_path: Path to the cached repository clone.
    """
    if store_path.exists():
        shutil.rmtree(store_path)


def get_store_path(config: PromptLibConfig, central_repo: str) -> Path:
    """Return the path that should host the cached prompt store.

    Args:
        config: Global prompt library configuration.
        central_repo: Remote URL or local path to the central repository.

    Returns:
        Path to either a cache directory or the provided local reference.
    """
    cleaned = central_repo.strip()
    if _is_local_reference(cleaned):
        return _resolve_local_path(cleaned)

    ensure_store_root(config.store_root)
    slug = _slugify_repo(cleaned)
    return config.store_root / slug


def sync_central_repo(
    central_repo: str,
    *,
    promptlib_config: PromptLibConfig | None = None,
    console: Console | None = None,
) -> Path:
    """Clone or update the cached prompt store and return its path.

    Args:
        central_repo: Remote URL or local path to sync.
        promptlib_config: Global prompt library configuration overrides.
        console: Optional Rich console used for progress reporting.

    Returns:
        Path pointing to the up-to-date prompt store.

    Raises:
        StoreSyncError: If synchronization fails and no cache is available.
    """
    config = promptlib_config or PromptLibConfig()
    cleaned = central_repo.strip()
    store_path = get_store_path(config, cleaned)

    if _is_local_reference(cleaned):
        if not store_path.exists():
            msg = f"Local prompt store not found at {store_path}"
            raise StoreSyncError(msg)
        return store_path

    ensure_store_root(config.store_root)
    store_path.parent.mkdir(parents=True, exist_ok=True)
    console_to_use = console or Console()

    progress_columns = (
        SpinnerColumn(),
        TextColumn("[progress.description]{task.description}"),
        TimeElapsedColumn(),
    )

    with Progress(*progress_columns, console=console_to_use, transient=True) as progress:
        task_id = progress.add_task("Syncing prompt library", start=True)
        try:
            repo = _prepare_repo(store_path, cleaned, timeout=config.sync_timeout_seconds)
            _update_repo(repo, timeout=config.sync_timeout_seconds)
        except (GitCommandError, OSError) as exc:
            if _has_valid_cache(store_path):
                console_to_use.print(
                    f"[yellow]Sync failed ({exc}). Falling back to cached content at {store_path}.[/yellow]"
                )
                return store_path
            msg = "Unable to synchronize central prompt repository"
            raise StoreSyncError(msg) from exc
        finally:
            progress.update(task_id, completed=1)

    return store_path


def _prepare_repo(store_path: Path, central_repo: str, *, timeout: int) -> Repo:
    """Return a Repo instance, cloning if necessary."""
    if store_path.exists():
        try:
            return Repo(store_path)
        except (InvalidGitRepositoryError, NoSuchPathError):
            clear_store_cache(store_path)

    return Repo.clone_from(
        central_repo,
        store_path,
        depth=1,
        single_branch=True,
        env={"GIT_TERMINAL_PROMPT": "0"},
        multi_options=["--no-tags"],
        timeout=timeout,
    )


def _update_repo(repo: Repo, *, timeout: int) -> None:
    """Fetch and fast-forward the cached repository."""
    git_cmd = repo.git
    git_cmd.fetch("--all", "--tags", "--prune", timeout=timeout)
    git_cmd.reset("--hard", "origin/HEAD", timeout=timeout)
    git_cmd.clean("-xdf", timeout=timeout)
    git_cmd.pull(timeout=timeout)


def _has_valid_cache(store_path: Path) -> bool:
    """Return True if the store path appears to host a git repository."""
    return (store_path / ".git").exists()


def _is_local_reference(value: str) -> bool:
    """Determine whether the provided repo reference is a local path."""
    cleaned = value.strip()
    if not cleaned:
        return False

    if _looks_like_remote(cleaned):
        return False

    candidate = Path(cleaned).expanduser()
    if candidate.exists() or candidate.is_absolute():
        return True
    return cleaned.startswith((".", ".."))


def _looks_like_remote(value: str) -> bool:
    """Return True if the reference resembles a remote Git URL."""
    if "://" in value:
        return True
    return value.startswith(("git@", "ssh://"))


def _resolve_local_path(value: str) -> Path:
    """Expand and resolve a local filesystem path."""
    return Path(value).expanduser().resolve()


def _slugify_repo(value: str) -> str:
    """Create a stable, filesystem-friendly slug for the remote repo."""
    tail = value.rsplit("/", 1)[-1].rsplit(":", 1)[-1]
    tail = tail.removesuffix(".git")
    cleaned = re.sub(r"[^a-z0-9\-]+", "-", tail.lower()).strip("-") or "store"
    digest = hashlib.sha256(value.encode("utf-8")).hexdigest()[:12]
    return f"{cleaned}-{digest}"
