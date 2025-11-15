"""Shared TypedDict payloads for tests."""

from __future__ import annotations

from pathlib import Path
from typing import Literal, NotRequired, TypedDict


class PromptMetadataPayload(TypedDict):
    """Schema for prompt metadata fixture."""

    id: str
    title: NotRequired[str]
    tags: list[str]
    repos: list[str]
    agents: list[str]
    version: str


class RuleMetadataPayload(TypedDict):
    """Schema for rule metadata fixture."""

    id: str
    tags: list[str]
    repos: list[str]
    agents: list[str]
    version: str


class RepoConfigPayload(TypedDict):
    """Schema for repo config fixture."""

    central_repo: str
    rules: list[str]
    prompt_sets: list[str]
    version_lock: str


class PromptLibConfigPayload(TypedDict):
    """Schema for prompt lib config fixture."""

    store_root: Path
    sync_timeout_seconds: int
    default_output_format: Literal["text", "json", "cursor"]
    env_prefix: str
