"""Configuration loading utilities for contextctl."""

from __future__ import annotations

import os
from collections.abc import Iterable, Mapping
from pathlib import Path
from typing import Any

import yaml
from pydantic import ValidationError

from contextctl.models import PromptLibConfig, RepoConfig

REPO_CONFIG_FILENAME = ".promptlib.yml"

EnvMapping = Mapping[str, str]


class ConfigError(RuntimeError):
    """Raised when repository configuration cannot be loaded or parsed."""


def find_repo_root(start_path: Path | None = None) -> Path:
    """Return the git repository root for the provided path."""
    path = (start_path or Path.cwd()).resolve()
    if path.is_file():
        path = path.parent

    for candidate in (path, *path.parents):
        if (candidate / ".git").exists():
            return candidate

    msg = f"Unable to locate a git repository starting from {path}"
    raise ConfigError(msg)


def load_repo_config(
    start_path: Path | None = None,
    *,
    env: EnvMapping | None = None,
    promptlib_config: PromptLibConfig | None = None,
    config_filename: str = REPO_CONFIG_FILENAME,
) -> RepoConfig:
    """Load `.promptlib.yml` from the repository root and apply overrides."""
    repo_root = find_repo_root(start_path)
    config_path = repo_root / config_filename
    if not config_path.exists():
        msg = f"Missing {config_filename} in {repo_root}"
        raise ConfigError(msg)

    raw_data = _load_yaml_mapping(config_path)
    env_mapping = env or os.environ
    merged = {**raw_data, **_extract_env_overrides(env_mapping, promptlib_config)}

    try:
        return RepoConfig(**merged)
    except ValidationError as exc:
        msg = f"Invalid repository configuration: {exc}"
        raise ConfigError(msg) from exc


def create_default_config(
    central_repo: str,
    *,
    rules: Iterable[str] | None = None,
    prompt_sets: Iterable[str] | None = None,
    version_lock: str | None = None,
) -> RepoConfig:
    """Create a RepoConfig instance populated with sensible defaults."""
    payload: dict[str, Any] = {
        "central_repo": central_repo,
        "rules": list(rules or []),
        "prompt_sets": list(prompt_sets or []),
        "version_lock": version_lock,
    }
    return RepoConfig(**payload)


def _load_yaml_mapping(config_path: Path) -> dict[str, Any]:
    """Load YAML data from disk ensuring a mapping result."""
    try:
        raw = yaml.safe_load(config_path.read_text())
    except yaml.YAMLError as exc:
        msg = f"Unable to parse {config_path.name}: {exc}"
        raise ConfigError(msg) from exc

    if raw is None:
        return {}
    if not isinstance(raw, dict):
        msg = f"{config_path.name} must contain a YAML mapping"
        raise ConfigError(msg)
    return raw


def _extract_env_overrides(
    env: EnvMapping,
    promptlib_config: PromptLibConfig | None,
) -> dict[str, Any]:
    """Return configuration overrides sourced from environment variables."""
    config = promptlib_config or PromptLibConfig()
    prefix = config.env_prefix
    upper_env = {key.upper(): value for key, value in env.items()}

    overrides: dict[str, Any] = {}
    mapping: dict[str, str] = {
        f"{prefix}CENTRAL_REPO": "central_repo",
        f"{prefix}VERSION_LOCK": "version_lock",
    }
    list_mapping: dict[str, str] = {
        f"{prefix}RULES": "rules",
        f"{prefix}PROMPT_SETS": "prompt_sets",
    }

    for env_key, field_name in mapping.items():
        if env_key in upper_env:
            overrides[field_name] = upper_env[env_key].strip()

    for env_key, field_name in list_mapping.items():
        if env_key in upper_env:
            overrides[field_name] = _parse_env_list(upper_env[env_key])

    return overrides


def _parse_env_list(raw_value: str) -> list[str]:
    """Parse a comma-separated string into a normalized list."""
    values = [part.strip() for part in raw_value.split(",")]
    return [value for value in values if value]
