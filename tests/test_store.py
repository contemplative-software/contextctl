"""Tests for prompt store helpers."""

from __future__ import annotations

from pathlib import Path

import pytest
from git.exc import GitCommandError
from pytest_mock import MockerFixture
from rich.console import Console

from contextctl.models import PromptLibConfig
from contextctl.store import (
    StoreSyncError,
    clear_store_cache,
    get_store_path,
    sync_central_repo,
)


def test_get_store_path_returns_cache_location_for_remote(tmp_path: Path) -> None:
    """Remote references should map to hashed directories under store_root."""
    config = PromptLibConfig(store_root=tmp_path / "store")
    path = get_store_path(config, "https://example.com/org/promptlib.git")

    assert path.is_relative_to(config.store_root)
    assert path != config.store_root


def test_get_store_path_returns_local_path(tmp_path: Path) -> None:
    """Local paths should be returned directly."""
    local_repo = tmp_path / "promptlib"
    local_repo.mkdir()
    config = PromptLibConfig()

    path = get_store_path(config, str(local_repo))

    assert path == local_repo.resolve()


def test_sync_central_repo_clones_when_cache_missing(tmp_path: Path, mocker: MockerFixture) -> None:
    """sync_central_repo should clone when the cache does not exist."""
    config = PromptLibConfig(store_root=tmp_path / "store")
    repo_mock = mocker.Mock()
    repo_mock.git = mocker.Mock()

    repo_cls = mocker.patch("contextctl.store.Repo")
    repo_cls.clone_from.return_value = repo_mock

    console = Console(record=True)
    result = sync_central_repo(
        "https://example.com/org/promptlib.git",
        promptlib_config=config,
        console=console,
    )

    repo_cls.clone_from.assert_called_once()
    repo_mock.git.fetch.assert_called_once()
    assert result.parent == config.store_root


def test_sync_central_repo_updates_existing_cache(tmp_path: Path, mocker: MockerFixture) -> None:
    """Existing caches should be fast-forwarded."""
    config = PromptLibConfig(store_root=tmp_path / "store")
    store_path = get_store_path(config, "https://example.com/org/promptlib.git")
    store_path.mkdir(parents=True)
    (store_path / ".git").mkdir()

    repo_mock = mocker.Mock()
    repo_mock.git = mocker.Mock()

    repo_cls = mocker.patch("contextctl.store.Repo", return_value=repo_mock)

    console = Console(record=True)
    result = sync_central_repo(
        "https://example.com/org/promptlib.git",
        promptlib_config=config,
        console=console,
    )

    repo_cls.assert_called_with(store_path)
    repo_mock.git.fetch.assert_called_once()
    assert result == store_path


def test_sync_central_repo_warns_on_failure_but_uses_cache(
    tmp_path: Path,
    mocker: MockerFixture,
) -> None:
    """Failures during sync should fall back to the last cached content."""
    config = PromptLibConfig(store_root=tmp_path / "store")
    store_path = get_store_path(config, "https://example.com/org/promptlib.git")
    store_path.mkdir(parents=True)
    (store_path / ".git").mkdir()

    repo_mock = mocker.Mock()
    repo_mock.git = mocker.Mock()
    repo_mock.git.fetch.side_effect = GitCommandError("fetch", 1)

    mocker.patch("contextctl.store.Repo", return_value=repo_mock)

    console = Console(record=True)
    result = sync_central_repo(
        "https://example.com/org/promptlib.git",
        promptlib_config=config,
        console=console,
    )

    assert "Falling back to cached content" in console.export_text()
    assert result == store_path


def test_sync_central_repo_raises_when_cache_missing_and_sync_fails(
    tmp_path: Path,
    mocker: MockerFixture,
) -> None:
    """If cloning fails and there is no cache we should raise a StoreSyncError."""
    config = PromptLibConfig(store_root=tmp_path / "store")

    repo_cls = mocker.patch("contextctl.store.Repo")
    repo_cls.clone_from.side_effect = GitCommandError("clone", 1)

    with pytest.raises(StoreSyncError):
        sync_central_repo(
            "https://example.com/org/promptlib.git",
            promptlib_config=config,
            console=Console(record=True),
        )


def test_sync_central_repo_supports_local_paths(tmp_path: Path) -> None:
    """Local directories should be returned without invoking git."""
    local_repo = tmp_path / "promptlib"
    local_repo.mkdir()

    result = sync_central_repo(str(local_repo))

    assert result == local_repo.resolve()


def test_clear_store_cache_removes_directory(tmp_path: Path) -> None:
    """Clearing the cache should delete the on-disk repository."""
    store_path = tmp_path / "store" / "repo"
    store_path.mkdir(parents=True)
    (store_path / "file.txt").write_text("hello")

    clear_store_cache(store_path)

    assert not store_path.exists()
