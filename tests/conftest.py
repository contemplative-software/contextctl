"""Shared pytest fixtures for contextctl."""

from __future__ import annotations

from pathlib import Path

import pytest

from .payloads import (
    PromptLibConfigPayload,
    PromptMetadataPayload,
    RepoConfigPayload,
    RuleMetadataPayload,
)


@pytest.fixture
def prompt_metadata_payload() -> PromptMetadataPayload:
    """Provide canonical prompt metadata for tests."""
    return {
        "id": "review-pr",
        "tags": ["reviews", "python", "reviews"],
        "repos": ["contextctl", " contextctl "],
        "agents": ["cursor", "claude"],
        "version": "0.2.0",
    }


@pytest.fixture
def rule_metadata_payload() -> RuleMetadataPayload:
    """Provide canonical rule metadata for tests."""
    return {
        "id": "python-standards",
        "tags": ["python", "style"],
        "repos": ["contextctl"],
        "agents": ["cursor"],
        "version": "1.0.0",
    }


@pytest.fixture
def repo_config_payload() -> RepoConfigPayload:
    """Provide a sample repo configuration payload."""
    return {
        "central_repo": "git@github.com:org/promptlib.git",
        "rules": ["python-standards", "security"],
        "prompt_sets": ["reviews", "incidents"],
        "version_lock": "1.2.3",
    }


@pytest.fixture
def promptlib_config_payload(tmp_path: Path) -> PromptLibConfigPayload:
    """Provide overrides for the PromptLibConfig model."""
    return {
        "store_root": tmp_path / "store",
        "sync_timeout_seconds": 3,
        "default_output_format": "json",
        "env_prefix": "ctx",
    }
