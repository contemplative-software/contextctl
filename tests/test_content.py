"""Tests for prompt and rule content parsing."""

from __future__ import annotations

from pathlib import Path
from textwrap import dedent

import pytest

from contextctl import (
    ContentError,
    load_prompt,
    load_rule,
    parse_frontmatter,
    scan_prompts_dir,
    scan_rules_dir,
)


def test_parse_frontmatter_returns_metadata_and_body() -> None:
    """Frontmatter parser should return metadata and remaining body text."""
    raw = dedent(
        """
        ---
        id: sample
        tags:
          - demo
        ---
        Hello world
        """,
    ).lstrip()

    metadata, body = parse_frontmatter(raw)

    assert metadata["id"] == "sample"
    assert metadata["tags"] == ["demo"]
    assert body == "Hello world"


def test_parse_frontmatter_requires_delimiters() -> None:
    """Missing YAML delimiters should raise a ContentError."""
    with pytest.raises(ContentError):
        parse_frontmatter("id: missing-delimiters")


def test_load_prompt_parses_document(tmp_path: Path) -> None:
    """load_prompt should return metadata and content for a file."""
    prompt_path = tmp_path / "prompt.md"
    prompt_path.write_text(
        dedent(
            """
            ---
            id: load-test
            tags:
              - tests
            repos:
              - contextctl
            agents: []
            version: 0.1.0
            ---
            Prompt body
            """,
        ).strip(),
        encoding="utf-8",
    )

    document = load_prompt(prompt_path)

    assert document.metadata.prompt_id == "load-test"
    assert "Prompt body" in document.body
    assert document.path == prompt_path


def test_load_prompt_requires_required_metadata(tmp_path: Path) -> None:
    """Frontmatter missing required fields should raise helpful errors."""
    prompt_path = tmp_path / "invalid.md"
    prompt_path.write_text(
        dedent(
            """
            ---
            tags:
              - missing-id
            ---
            Invalid prompt
            """,
        ).strip(),
        encoding="utf-8",
    )

    with pytest.raises(ContentError):
        load_prompt(prompt_path)


def test_load_rule_parses_document(tmp_path: Path) -> None:
    """load_rule should parse rule files using shared helpers."""
    rule_path = tmp_path / "rule.md"
    rule_path.write_text(
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
            Follow PEP 8.
            """,
        ).strip(),
        encoding="utf-8",
    )

    document = load_rule(rule_path)

    assert document.metadata.rule_id == "python-style"
    assert "PEP 8" in document.body


def test_scan_prompts_dir_indexes_all_files(sample_prompt_store: Path) -> None:
    """scan_prompts_dir should read every markdown file under prompts/."""
    prompts = scan_prompts_dir(sample_prompt_store)
    prompt_ids = [doc.metadata.prompt_id for doc in prompts]

    assert prompt_ids == sorted(prompt_ids)
    assert {"incident-response", "review-pr"} == set(prompt_ids)


def test_scan_rules_dir_indexes_all_files(sample_prompt_store: Path) -> None:
    """scan_rules_dir should read every markdown file under rules/."""
    rules = scan_rules_dir(sample_prompt_store)
    rule_ids = {doc.metadata.rule_id for doc in rules}

    assert {"python-style", "security"} == rule_ids


def test_scan_rules_dir_requires_directory(tmp_path: Path) -> None:
    """Missing rules directory should raise a ContentError."""
    store_root = tmp_path / "empty-store"
    store_root.mkdir()

    with pytest.raises(ContentError):
        scan_rules_dir(store_root)
