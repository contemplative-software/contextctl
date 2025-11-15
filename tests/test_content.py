"""Tests for prompt and rule content parsing."""

from __future__ import annotations

from collections.abc import Iterator
from contextlib import contextmanager
from pathlib import Path
from textwrap import dedent

from contextctl import (
    ContentError,
    PromptDocument,
    PromptMetadata,
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


@contextmanager
def expect_raises(exc_type: type[BaseException]) -> Iterator[None]:
    """Context manager that asserts an exception is raised."""
    try:
        yield
    except exc_type:
        return
    raise AssertionError(f"Expected {exc_type.__name__} to be raised")


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
    with expect_raises(ContentError):
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

    with expect_raises(ContentError):
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

    with expect_raises(ContentError):
        scan_rules_dir(store_root)


def test_filter_by_repo_matches_specific_repo(sample_prompt_store: Path) -> None:
    """filter_by_repo should include prompts tied to the requested repo."""
    prompts = scan_prompts_dir(sample_prompt_store)

    filtered = filter_by_repo(prompts, "ContextCTL")

    assert [doc.metadata.prompt_id for doc in filtered] == ["review-pr"]


def test_filter_by_repo_includes_repo_agnostic_prompts(
    sample_prompt_store: Path,
    tmp_path: Path,
) -> None:
    """Prompts without repo restrictions should match any repo."""
    prompts = scan_prompts_dir(sample_prompt_store)
    prompt = PromptDocument(
        metadata=PromptMetadata(
            prompt_id="global",
            tags=["general"],
            repos=[],
            agents=[],
            version="0.1.0",
        ),
        body="General guidance",
        path=tmp_path / "global.md",
    )

    filtered = filter_by_repo([*prompts, prompt], "ops")

    assert {doc.metadata.prompt_id for doc in filtered} == {"incident-response", "global"}


def test_filter_by_tags_supports_any_and_all_modes(
    sample_prompt_store: Path,
    tmp_path: Path,
) -> None:
    """filter_by_tags should handle any vs. all tag matching."""
    prompts = scan_prompts_dir(sample_prompt_store)
    prompt = PromptDocument(
        metadata=PromptMetadata(
            prompt_id="multi",
            tags=["reviews", "python"],
            repos=["contextctl"],
            agents=["cursor"],
            version="0.3.0",
        ),
        body="Multi-tag prompt",
        path=tmp_path / "multi.md",
    )
    extended = [*prompts, prompt]

    any_match = filter_by_tags(extended, ["reviews"])
    all_match = filter_by_tags(extended, ["reviews", "python"], match_all=True)

    assert {doc.metadata.prompt_id for doc in any_match} >= {"review-pr", "multi"}
    assert [doc.metadata.prompt_id for doc in all_match] == ["multi"]


def test_filter_by_agent_matches_requested_agents(sample_prompt_store: Path) -> None:
    """filter_by_agent should return prompts compatible with specified agents."""
    prompts = scan_prompts_dir(sample_prompt_store)

    filtered = filter_by_agent(prompts, "cursor")

    assert [doc.metadata.prompt_id for doc in filtered] == ["review-pr"]


def test_filter_by_agent_includes_agent_agnostic_prompts(
    sample_prompt_store: Path,
    tmp_path: Path,
) -> None:
    """Prompts without agent restrictions should match every agent filter."""
    prompts = scan_prompts_dir(sample_prompt_store)
    neutral = PromptDocument(
        metadata=PromptMetadata(
            prompt_id="neutral",
            tags=["general"],
            repos=[],
            agents=[],
            version="0.1.0",
        ),
        body="Neutral prompt",
        path=tmp_path / "neutral.md",
    )

    filtered = filter_by_agent([*prompts, neutral], "cursor")

    assert {doc.metadata.prompt_id for doc in filtered} == {"review-pr", "neutral"}


def test_search_prompts_matches_body_tokens(sample_prompt_store: Path) -> None:
    """search_prompts should locate prompts by body text tokens."""
    prompts = scan_prompts_dir(sample_prompt_store)

    results = search_prompts(prompts, "pull request")

    assert [doc.metadata.prompt_id for doc in results] == ["review-pr"]


def test_search_prompts_supports_fuzzy_prompt_ids(sample_prompt_store: Path) -> None:
    """search_prompts should return prompts when ids nearly match."""
    prompts = scan_prompts_dir(sample_prompt_store)

    results = search_prompts(prompts, "reviewpr")

    assert [doc.metadata.prompt_id for doc in results] == ["review-pr"]


def test_search_prompts_handles_special_characters(sample_prompt_store: Path) -> None:
    """Queries containing special characters should be treated literally."""
    prompts = scan_prompts_dir(sample_prompt_store)

    results = search_prompts(prompts, "incident-response")

    assert [doc.metadata.prompt_id for doc in results] == ["incident-response"]


def test_search_prompts_returns_empty_for_unknown_terms(sample_prompt_store: Path) -> None:
    """Unknown queries should yield an empty result set."""
    prompts = scan_prompts_dir(sample_prompt_store)

    results = search_prompts(prompts, "nonexistent term")

    assert results == []


def test_search_prompts_rejects_blank_queries(sample_prompt_store: Path) -> None:
    """Blank queries should raise a ContentError."""
    prompts = scan_prompts_dir(sample_prompt_store)

    with expect_raises(ContentError):
        search_prompts(prompts, "   ")
