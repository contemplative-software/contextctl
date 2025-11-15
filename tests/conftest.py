"""Shared pytest fixtures for contextctl."""

from __future__ import annotations

from pathlib import Path
from textwrap import dedent

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


@pytest.fixture
def sample_prompt_store(tmp_path: Path) -> Path:
    """Create a synthetic prompt library with multiple prompts and rules."""
    store_root = tmp_path / "prompt_store"
    prompts_dir = store_root / "prompts" / "reviews"
    rules_dir = store_root / "rules" / "python"
    prompts_dir.mkdir(parents=True)
    rules_dir.mkdir(parents=True)

    (prompts_dir / "review-pr.md").write_text(
        dedent(
            """
            ---
            id: review-pr
            tags:
              - reviews
            repos:
              - contextctl
            agents:
              - cursor
            version: 0.2.0
            ---
            Provide a detailed pull request review.
            """,
        ).strip(),
        encoding="utf-8",
    )

    (prompts_dir / "incident.md").write_text(
        dedent(
            """
            ---
            id: incident-response
            tags:
              - incidents
            repos:
              - ops
            agents:
              - claude
            version: 0.1.0
            ---
            Assist with incident response coordination.
            """,
        ).strip(),
        encoding="utf-8",
    )

    (rules_dir / "python-style.md").write_text(
        dedent(
            """
            ---
            id: python-style
            tags:
              - python
            repos:
              - contextctl
            agents:
              - cursor
            version: 1.0.0
            ---
            Follow the standard Python style guidelines.
            """,
        ).strip(),
        encoding="utf-8",
    )

    (rules_dir / "security.md").write_text(
        dedent(
            """
            ---
            id: security
            tags:
              - security
            repos:
              - ops
            agents:
              - claude
            version: 2.3.1
            ---
            Enforce security reviews for all changes.
            """,
        ).strip(),
        encoding="utf-8",
    )

    return store_root
