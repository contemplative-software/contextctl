"""Public exports for the contextctl package."""

from __future__ import annotations

import tomllib
from importlib.metadata import PackageNotFoundError
from importlib.metadata import version as pkg_version
from pathlib import Path

from .config import (
    REPO_CONFIG_FILENAME,
    ConfigError,
    create_default_config,
    find_repo_root,
    load_repo_config,
)
from .content import (
    ContentError,
    PromptDocument,
    RuleDocument,
    filter_by_agent,
    filter_by_repo,
    filter_by_tags,
    load_prompt,
    load_rule,
    parse_frontmatter,
    scan_prompts_dir,
    scan_rules_dir,
    search_prompts,
)
from .models import PromptLibConfig, PromptMetadata, RepoConfig, RuleMetadata
from .store import (
    StoreSyncError,
    clear_store_cache,
    ensure_store_root,
    get_store_path,
    sync_central_repo,
)


def _load_local_version() -> str:
    """Return the package version declared in pyproject.toml when metadata is unavailable."""
    pyproject_path = Path(__file__).resolve().parents[2] / "pyproject.toml"
    try:
        raw_text = pyproject_path.read_text(encoding="utf-8")
    except FileNotFoundError:
        return "0.0.0"

    try:
        data = tomllib.loads(raw_text)
    except tomllib.TOMLDecodeError:
        return "0.0.0"

    project_section = data.get("project")
    if isinstance(project_section, dict):
        version_value = project_section.get("version")
        if isinstance(version_value, str) and version_value.strip():
            return version_value.strip()
    return "0.0.0"


try:
    __version__ = pkg_version("contextctl")
except PackageNotFoundError:
    __version__ = _load_local_version()

__all__ = [
    "REPO_CONFIG_FILENAME",
    "ConfigError",
    "ContentError",
    "PromptDocument",
    "PromptLibConfig",
    "PromptMetadata",
    "RepoConfig",
    "RuleDocument",
    "RuleMetadata",
    "StoreSyncError",
    "__version__",
    "clear_store_cache",
    "create_default_config",
    "ensure_store_root",
    "filter_by_agent",
    "filter_by_repo",
    "filter_by_tags",
    "find_repo_root",
    "get_store_path",
    "load_prompt",
    "load_repo_config",
    "load_rule",
    "parse_frontmatter",
    "scan_prompts_dir",
    "scan_rules_dir",
    "search_prompts",
    "sync_central_repo",
]
