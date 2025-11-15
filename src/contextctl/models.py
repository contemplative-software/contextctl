"""Core data models for the contextctl CLI."""

from __future__ import annotations

import re
from pathlib import Path
from typing import Any, Final, Literal

from pydantic import BaseModel, ConfigDict, Field, field_validator

_ID_PATTERN: Final[re.Pattern[str]] = re.compile(r"[a-z0-9][a-z0-9\-_]*")
_SEMVER_PATTERN: Final[re.Pattern[str]] = re.compile(r"(?:0|[1-9]\d*)\.(?:0|[1-9]\d*)\.(?:0|[1-9]\d*)")


def _normalize_list(values: list[str]) -> list[str]:
    """Return a trimmed, de-duplicated version of the provided string list."""
    seen: set[str] = set()
    normalized: list[str] = []
    for value in values:
        trimmed = str(value).strip()
        if not trimmed:
            continue
        fingerprint = trimmed.casefold()
        if fingerprint in seen:
            continue
        seen.add(fingerprint)
        normalized.append(trimmed)
    return normalized


class _BaseMetadata(BaseModel):
    """Shared metadata fields and validation for prompts and rules."""

    model_config = ConfigDict(populate_by_name=True, frozen=True)

    tags: list[str] = Field(default_factory=list)
    repos: list[str] = Field(default_factory=list)
    agents: list[str] = Field(default_factory=list)
    version: str = Field(default="0.1.0")

    @field_validator("tags", "repos", "agents", mode="before")
    @classmethod
    def normalize_lists(cls, values: Any) -> list[str]:
        """Trim and de-duplicate list inputs."""
        if not isinstance(values, list):
            msg = "Expected a list of strings"
            raise TypeError(msg)
        return _normalize_list(values)

    @field_validator("version")
    @classmethod
    def validate_version(cls, value: str) -> str:
        """Validate semantic version strings."""
        normalized = value.strip()
        if not normalized:
            msg = "Version cannot be blank"
            raise ValueError(msg)
        if not _SEMVER_PATTERN.fullmatch(normalized):
            msg = "Version must follow MAJOR.MINOR.PATCH format"
            raise ValueError(msg)
        return normalized


class PromptMetadata(_BaseMetadata):
    """Metadata parsed from a prompt markdown file."""

    prompt_id: str = Field(alias="id")
    title: str | None = None

    @field_validator("prompt_id")
    @classmethod
    def validate_prompt_id(cls, value: str) -> str:
        """Ensure the prompt identifier is a slug-style token."""
        normalized = value.strip()
        if not normalized:
            msg = "Prompt id cannot be blank"
            raise ValueError(msg)
        if not _ID_PATTERN.fullmatch(normalized):
            msg = "Prompt id must contain lowercase letters, numbers, dashes, or underscores"
            raise ValueError(msg)
        return normalized

    @field_validator("title")
    @classmethod
    def normalize_title(cls, value: str | None) -> str | None:
        """Trim optional prompt titles, returning None when blank."""
        if value is None:
            return None
        normalized = value.strip()
        if not normalized:
            return None
        return normalized


class RuleMetadata(_BaseMetadata):
    """Metadata parsed from a rule definition file."""

    rule_id: str = Field(alias="id")

    @field_validator("rule_id")
    @classmethod
    def validate_rule_id(cls, value: str) -> str:
        """Ensure the rule identifier is a slug-style token."""
        normalized = value.strip()
        if not normalized:
            msg = "Rule id cannot be blank"
            raise ValueError(msg)
        if not _ID_PATTERN.fullmatch(normalized):
            msg = "Rule id must contain lowercase letters, numbers, dashes, or underscores"
            raise ValueError(msg)
        return normalized


class RepoConfig(BaseModel):
    """Configuration stored in `.promptlib.yml` within a repository."""

    model_config = ConfigDict(populate_by_name=True, frozen=True)

    central_repo: str
    rules: list[str] = Field(default_factory=list)
    prompt_sets: list[str] = Field(default_factory=list)
    version_lock: str | None = None

    @field_validator("central_repo")
    @classmethod
    def validate_central_repo(cls, value: str) -> str:
        """Ensure the central repo URL or path is present."""
        normalized = value.strip()
        if not normalized:
            msg = "central_repo must be provided"
            raise ValueError(msg)
        return normalized

    @field_validator("rules", "prompt_sets", mode="before")
    @classmethod
    def normalize_entry_lists(cls, values: Any) -> list[str]:
        """Normalize rule and prompt set lists."""
        if not isinstance(values, list):
            msg = "Expected a list of strings"
            raise TypeError(msg)
        if not values:
            return []
        normalized = _normalize_list(values)
        return normalized

    @field_validator("version_lock")
    @classmethod
    def validate_version_lock(cls, value: str | None) -> str | None:
        """Ensure version locks align with semantic version expectations."""
        if value is None:
            return None
        normalized = value.strip()
        if not _SEMVER_PATTERN.fullmatch(normalized):
            msg = "version_lock must follow MAJOR.MINOR.PATCH format"
            raise ValueError(msg)
        return normalized


class PromptLibConfig(BaseModel):
    """Global tool configuration derived from environment variables or defaults."""

    model_config = ConfigDict(populate_by_name=True, frozen=True)

    store_root: Path = Field(default_factory=lambda: Path.home() / ".contextctl" / "store")
    sync_timeout_seconds: int = Field(default=5, ge=1, le=30)
    default_output_format: Literal["text", "json", "cursor"] = "text"
    env_prefix: str = Field(default="CONTEXTCTL_")

    @field_validator("store_root", mode="before")
    @classmethod
    def expand_store_root(cls, value: Any) -> Path:
        """Expand user paths while keeping lazy resolution."""
        if isinstance(value, Path):
            return value.expanduser()
        return Path(str(value)).expanduser()

    @field_validator("env_prefix")
    @classmethod
    def normalize_prefix(cls, value: str) -> str:
        """Ensure environment prefixes are uppercase and suffixed with an underscore."""
        normalized = value.strip().upper()
        if not normalized:
            msg = "env_prefix cannot be blank"
            raise ValueError(msg)
        if not normalized.endswith("_"):
            normalized = f"{normalized}_"
        return normalized
