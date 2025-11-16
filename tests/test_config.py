"""Tests for configuration helpers."""

from __future__ import annotations

from pathlib import Path

import pytest

from contextctl.config import (
    ConfigError,
    create_default_config,
    find_repo_root,
    load_repo_config,
)
from contextctl.models import PromptLibConfig


def _make_repo(tmp_path: Path) -> Path:
    """Create a minimal git repo structure in the tmp path."""
    repo_root = tmp_path / "repo"
    (repo_root / ".git").mkdir(parents=True)
    return repo_root


def _write_config(repo_root: Path, contents: str) -> None:
    """Write contents to `.promptlib.yml` in the repo root."""
    (repo_root / ".promptlib.yml").write_text(contents)


def test_find_repo_root_returns_git_root(tmp_path: Path) -> None:
    """The helper should walk parent directories until it finds .git."""
    repo_root = _make_repo(tmp_path)
    nested = repo_root / "nested" / "src"
    nested.mkdir(parents=True)

    assert find_repo_root(nested) == repo_root


def test_find_repo_root_handles_file_paths(tmp_path: Path) -> None:
    """Providing a file path should resolve to its parent git root."""
    repo_root = _make_repo(tmp_path)
    file_path = repo_root / "nested" / "file.txt"
    file_path.parent.mkdir(parents=True)
    file_path.write_text("data")

    assert find_repo_root(file_path) == repo_root


def test_find_repo_root_errors_when_git_missing(tmp_path: Path) -> None:
    """Missing .git directories should raise a ConfigError."""
    with pytest.raises(ConfigError):
        find_repo_root(tmp_path)


def test_load_repo_config_parses_yaml(tmp_path: Path) -> None:
    """load_repo_config should return a RepoConfig with values from YAML."""
    repo_root = _make_repo(tmp_path)
    _write_config(
        repo_root,
        """
central_repo: git@example.com:org/promptlib.git
rules:
  - python
prompt_sets:
  - reviews
        """.strip(),
    )

    nested = repo_root / "pkg"
    nested.mkdir()
    result = load_repo_config(nested)

    assert result.central_repo == "git@example.com:org/promptlib.git"
    assert result.rules == ["python"]
    assert result.prompt_sets == ["reviews"]


def test_load_repo_config_applies_environment_overrides(tmp_path: Path) -> None:
    """Environment variables should override file-based values."""
    repo_root = _make_repo(tmp_path)
    _write_config(
        repo_root,
        """
central_repo: https://example.com/original.git
rules: []
prompt_sets: []
        """.strip(),
    )

    overrides = PromptLibConfig(env_prefix="CTX_")
    env_with_custom_prefix = {
        "CTX_CENTRAL_REPO": "https://override.git",
        "CTX_RULES": "alpha, beta",
        "CTX_PROMPT_SETS": "core,extra",
        "CTX_VERSION_LOCK": "1.2.3",
        "CONTEXTCTL_RULES": "ignored",
    }

    result = load_repo_config(
        repo_root,
        env=env_with_custom_prefix,
        promptlib_config=overrides,
    )

    assert result.central_repo == "https://override.git"
    assert result.rules == ["alpha", "beta"]
    assert result.prompt_sets == ["core", "extra"]
    assert result.version_lock == "1.2.3"


def test_load_repo_config_accepts_empty_file_when_env_provides_values(tmp_path: Path) -> None:
    """Blank configuration files should allow env vars to supply settings."""
    repo_root = _make_repo(tmp_path)
    _write_config(repo_root, "")

    env = {
        "CONTEXTCTL_CENTRAL_REPO": "file:///tmp/promptlib",
        "CONTEXTCTL_RULES": "alpha",
    }

    result = load_repo_config(repo_root, env=env)

    assert result.central_repo == "file:///tmp/promptlib"
    assert result.rules == ["alpha"]
    assert result.prompt_sets == []


def test_load_repo_config_rejects_invalid_yaml(tmp_path: Path) -> None:
    """Non-mapping YAML files should raise errors."""
    repo_root = _make_repo(tmp_path)
    _write_config(repo_root, "- not-a-mapping")

    with pytest.raises(ConfigError):
        load_repo_config(repo_root)


def test_load_repo_config_surfaces_yaml_parse_errors(tmp_path: Path) -> None:
    """Low-level YAML parser errors should propagate as ConfigError."""
    repo_root = _make_repo(tmp_path)
    _write_config(
        repo_root,
        """
        ---
        : bad
          indentation
        """.strip(),
    )

    with pytest.raises(ConfigError):
        load_repo_config(repo_root)


def test_create_default_config_generates_expected_payload() -> None:
    """Default config helper should populate RepoConfig with sane defaults."""
    config = create_default_config(
        "git@example.com:org/promptlib.git",
        rules=["python"],
        prompt_sets=["reviews"],
    )

    assert config.central_repo.endswith("promptlib.git")
    assert config.rules == ["python"]
    assert config.prompt_sets == ["reviews"]
