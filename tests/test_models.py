"""Unit tests for Pydantic models."""

from __future__ import annotations

from pathlib import Path

import pytest

from contextctl.models import PromptLibConfig, PromptMetadata, RepoConfig, RuleMetadata

from .payloads import (
    PromptLibConfigPayload,
    PromptMetadataPayload,
    RepoConfigPayload,
    RuleMetadataPayload,
)


def test_prompt_metadata_dedupes_lists(prompt_metadata_payload: PromptMetadataPayload) -> None:
    """Lists should be trimmed and deduplicated."""
    metadata = PromptMetadata(**prompt_metadata_payload)

    assert metadata.title == "Review PR"
    assert metadata.tags == ["reviews", "python"]
    assert metadata.repos == ["contextctl"]
    assert metadata.agents == ["cursor", "claude"]


def test_prompt_metadata_requires_slug_id(prompt_metadata_payload: PromptMetadataPayload) -> None:
    """Prompt identifiers must be slug friendly."""
    prompt_metadata_payload["id"] = "Invalid Slug"
    with pytest.raises(ValueError):
        PromptMetadata(**prompt_metadata_payload)


def test_prompt_metadata_drops_blank_list_entries(prompt_metadata_payload: PromptMetadataPayload) -> None:
    """Blank list entries should be removed during normalization."""
    prompt_metadata_payload["tags"] = ["python", "  ", "PYTHON"]
    metadata = PromptMetadata(**prompt_metadata_payload)

    assert metadata.tags == ["python"]


def test_prompt_metadata_rejects_blank_id(prompt_metadata_payload: PromptMetadataPayload) -> None:
    """Blank prompt identifiers should raise errors."""
    prompt_metadata_payload["id"] = " "
    with pytest.raises(ValueError):
        PromptMetadata(**prompt_metadata_payload)


def test_prompt_metadata_requires_list_inputs(prompt_metadata_payload: PromptMetadataPayload) -> None:
    """Non-list metadata fields should raise TypeError."""
    prompt_metadata_payload["tags"] = "not-a-list"  # type: ignore[typeddict-item]
    with pytest.raises(TypeError):
        PromptMetadata(**prompt_metadata_payload)


def test_prompt_metadata_rejects_blank_version(prompt_metadata_payload: PromptMetadataPayload) -> None:
    """Blank version strings should be rejected."""
    prompt_metadata_payload["version"] = " "
    with pytest.raises(ValueError):
        PromptMetadata(**prompt_metadata_payload)


def test_prompt_metadata_normalizes_blank_title(prompt_metadata_payload: PromptMetadataPayload) -> None:
    """Blank titles should be normalized to None."""
    prompt_metadata_payload["title"] = "   "
    metadata = PromptMetadata(**prompt_metadata_payload)

    assert metadata.title is None


def test_rule_metadata_semver_validation(rule_metadata_payload: RuleMetadataPayload) -> None:
    """Rules should reject malformed versions."""
    rule_metadata_payload["version"] = "v1"
    with pytest.raises(ValueError):
        RuleMetadata(**rule_metadata_payload)


def test_rule_metadata_requires_id(rule_metadata_payload: RuleMetadataPayload) -> None:
    """Blank rule identifiers should raise errors."""
    rule_metadata_payload["id"] = " "
    with pytest.raises(ValueError):
        RuleMetadata(**rule_metadata_payload)


def test_repo_config_normalizes_entries(repo_config_payload: RepoConfigPayload) -> None:
    """Repo config should dedupe rule/prompt lists."""
    repo_config_payload["rules"].append("python-standards")
    repo_config_payload["prompt_sets"].append("reviews")

    config = RepoConfig(**repo_config_payload)

    assert config.rules == ["python-standards", "security"]
    assert config.prompt_sets == ["reviews", "incidents"]


def test_repo_config_rejects_non_list_inputs(repo_config_payload: RepoConfigPayload) -> None:
    """Non-list rule inputs should raise TypeError."""
    repo_config_payload["rules"] = "invalid"  # type: ignore[typeddict-item]
    with pytest.raises(TypeError):
        RepoConfig(**repo_config_payload)


def test_repo_config_handles_empty_lists(repo_config_payload: RepoConfigPayload) -> None:
    """Empty rule or prompt lists should round-trip as empty."""
    repo_config_payload["rules"] = []
    repo_config_payload["prompt_sets"] = []

    config = RepoConfig(**repo_config_payload)

    assert config.rules == []
    assert config.prompt_sets == []


def test_repo_config_requires_central_repo(repo_config_payload: RepoConfigPayload) -> None:
    """Central repo is mandatory."""
    repo_config_payload["central_repo"] = " "
    with pytest.raises(ValueError):
        RepoConfig(**repo_config_payload)


def test_promptlib_config_defaults(tmp_path: Path) -> None:
    """Ensure PromptLibConfig produces reasonable defaults."""
    config = PromptLibConfig(store_root=tmp_path)

    assert config.store_root == tmp_path
    assert config.sync_timeout_seconds == 5
    assert config.default_output_format == "text"
    assert config.env_prefix == "CONTEXTCTL_"


def test_promptlib_config_applies_overrides(promptlib_config_payload: PromptLibConfigPayload) -> None:
    """Overrides should be respected and normalized."""
    config = PromptLibConfig(**promptlib_config_payload)

    assert config.store_root == promptlib_config_payload["store_root"]
    assert config.sync_timeout_seconds == 3
    assert config.default_output_format == "json"
    assert config.env_prefix == "CTX_"


def test_promptlib_config_expands_string_paths(tmp_path: Path) -> None:
    """String inputs for store_root should be expanded to Paths."""
    config = PromptLibConfig(store_root=str(tmp_path))  # type: ignore[arg-type]

    assert config.store_root == tmp_path


def test_promptlib_config_requires_prefix_value() -> None:
    """Blank env prefixes should raise ValueError."""
    with pytest.raises(ValueError):
        PromptLibConfig(env_prefix="  ")
