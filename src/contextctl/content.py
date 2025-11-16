"""Parsing and indexing helpers for prompt and rule documents."""

from __future__ import annotations

import re
from collections.abc import Callable, Iterable, Sequence
from dataclasses import dataclass
from difflib import SequenceMatcher
from pathlib import Path
from typing import Any, Final, TypeVar

import yaml
from pydantic import ValidationError

from contextctl.models import PromptMetadata, RuleMetadata

DocumentT = TypeVar("DocumentT", bound="BaseDocument")


_FRONTMATTER_BOUNDARY: Final[re.Pattern[str]] = re.compile(r"^---\s*$", re.MULTILINE)
_PROMPT_SUFFIXES: Final[tuple[str, ...]] = (".md", ".markdown")
_RULE_SUFFIXES: Final[tuple[str, ...]] = (".md", ".markdown")


class ContentError(RuntimeError):
    """Raised when prompt or rule content cannot be parsed."""


@dataclass(frozen=True, slots=True)
class BaseDocument:
    """Common fields shared across prompt and rule documents.

    Attributes:
        metadata: Parsed metadata describing the document.
        body: Markdown body without YAML frontmatter.
        path: Filesystem path that produced the document.
    """

    metadata: PromptMetadata | RuleMetadata
    body: str
    path: Path


@dataclass(frozen=True, slots=True)
class PromptDocument(BaseDocument):
    """Parsed prompt content.

    Attributes:
        metadata: PromptMetadata describing the prompt.
    """

    metadata: PromptMetadata


@dataclass(frozen=True, slots=True)
class RuleDocument(BaseDocument):
    """Parsed rule content.

    Attributes:
        metadata: RuleMetadata describing the rule.
    """

    metadata: RuleMetadata


def parse_frontmatter(raw_text: str) -> tuple[dict[str, Any], str]:
    """Extract YAML metadata and body content from a markdown document.

    Args:
        raw_text: Full markdown contents including YAML frontmatter.

    Returns:
        Tuple containing the metadata mapping and stripped body content.

    Raises:
        ContentError: If the document lacks valid frontmatter or cannot be parsed.
    """
    text = raw_text.lstrip("\ufeff")
    opening = _FRONTMATTER_BOUNDARY.match(text)
    if opening is None:
        msg = "Document must begin with YAML frontmatter delimited by ---"
        raise ContentError(msg)

    closing = _FRONTMATTER_BOUNDARY.search(text, opening.end())
    if closing is None:
        msg = "Frontmatter block is not properly terminated"
        raise ContentError(msg)

    yaml_block = text[opening.end() : closing.start()]
    try:
        metadata = yaml.safe_load(yaml_block) or {}
    except yaml.YAMLError as exc:
        msg = "Unable to parse YAML frontmatter"
        raise ContentError(msg) from exc

    if not isinstance(metadata, dict):
        msg = "YAML frontmatter must deserialize to a mapping"
        raise ContentError(msg)

    body = text[closing.end() :]
    body = body.lstrip("\r\n")
    body = body.rstrip("\r\n")
    return metadata, body


def load_prompt(path: Path) -> PromptDocument:
    """Load a prompt file and return its metadata and body.

    Args:
        path: Filesystem path to the prompt document.

    Returns:
        PromptDocument instance containing metadata and body text.

    Raises:
        ContentError: If the file is missing or contains invalid metadata.
    """
    metadata, body = _load_document(path, PromptMetadata)
    return PromptDocument(metadata=metadata, body=body, path=path)


def load_rule(path: Path) -> RuleDocument:
    """Load a rule file and return its metadata and body.

    Args:
        path: Filesystem path to the rule document.

    Returns:
        RuleDocument instance containing metadata and body text.

    Raises:
        ContentError: If the file is missing or contains invalid metadata.
    """
    metadata, body = _load_document(path, RuleMetadata)
    return RuleDocument(metadata=metadata, body=body, path=path)


def scan_prompts_dir(store_path: Path) -> list[PromptDocument]:
    """Return all prompts discovered under the `prompts/` directory.

    Args:
        store_path: Root of the synchronized prompt store.

    Returns:
        Alphabetically sorted list of prompt documents.

    Raises:
        ContentError: If the prompts directory is missing or malformed.
    """
    documents = _scan_directory(
        store_path=store_path,
        relative_dir="prompts",
        loader=load_prompt,
        allowed_suffixes=_PROMPT_SUFFIXES,
    )
    return sorted(documents, key=lambda doc: doc.metadata.prompt_id)


def scan_rules_dir(store_path: Path) -> list[RuleDocument]:
    """Return all rules discovered under the `rules/` directory.

    Args:
        store_path: Root of the synchronized prompt store.

    Returns:
        Alphabetically sorted list of rule documents.

    Raises:
        ContentError: If the rules directory is missing or malformed.
    """
    documents = _scan_directory(
        store_path=store_path,
        relative_dir="rules",
        loader=load_rule,
        allowed_suffixes=_RULE_SUFFIXES,
    )
    return sorted(documents, key=lambda doc: doc.metadata.rule_id)


def filter_by_repo(  # noqa: UP047
    documents: Iterable[DocumentT],
    repo_slug: str | None,
) -> list[DocumentT]:
    """Return documents whose repo list matches the provided slug.

    Args:
        documents: Documents to evaluate.
        repo_slug: Repository identifier derived from the git root.

    Returns:
        Documents whose metadata includes the provided slug or no repo list.
    """
    items = list(documents)
    if repo_slug is None:
        return items

    normalized = repo_slug.strip().casefold()
    if not normalized:
        return items

    results: list[DocumentT] = []
    for document in items:
        repos = _metadata_value_set(document.metadata.repos)
        if not repos or normalized in repos:
            results.append(document)
    return results


def filter_by_tags(  # noqa: UP047
    documents: Iterable[DocumentT],
    tags: Iterable[str] | None,
    *,
    match_all: bool = False,
) -> list[DocumentT]:
    """Return documents filtered by tag membership.

    Args:
        documents: Documents to evaluate.
        tags: Tags used to filter results.
        match_all: Whether documents must include every provided tag.

    Returns:
        Documents that satisfy the requested tag criteria.
    """
    items = list(documents)
    query_tags = _normalize_query_values(tags)
    if not query_tags:
        return items

    results: list[DocumentT] = []
    for document in items:
        document_tags = _metadata_value_set(document.metadata.tags)
        if not document_tags:
            continue
        if match_all and query_tags.issubset(document_tags):
            results.append(document)
            continue
        if not match_all and document_tags & query_tags:
            results.append(document)
    return results


def filter_by_agent(  # noqa: UP047
    documents: Iterable[DocumentT],
    agents: str | Sequence[str] | None,
) -> list[DocumentT]:
    """Return documents compatible with the provided agents.

    Args:
        documents: Documents to evaluate.
        agents: Single agent or collection of agents to match.

    Returns:
        Documents that either match or do not restrict the provided agents.
    """
    items = list(documents)
    query_agents = _normalize_query_values(agents)
    if not query_agents:
        return items

    results: list[DocumentT] = []
    for document in items:
        document_agents = _metadata_value_set(document.metadata.agents)
        if not document_agents:
            results.append(document)
            continue
        if document_agents & query_agents:
            results.append(document)
    return results


def search_prompts(
    documents: Iterable[PromptDocument],
    query: str,
    *,
    fuzzy_threshold: float = 0.72,
) -> list[PromptDocument]:
    """Return prompts that match the provided full-text query.

    Args:
        documents: Prompt documents to search.
        query: User-provided search text.
        fuzzy_threshold: Minimum fuzzy-match ratio for identifier matching.

    Returns:
        Sorted list of prompt documents that match the query.

    Raises:
        ContentError: If the query is empty.
    """
    tokens = _tokenize_query(query)
    if not tokens:
        msg = "Search query cannot be empty"
        raise ContentError(msg)

    normalized_query = query.strip()
    fuzzy_candidates = set(tokens)
    if normalized_query:
        fuzzy_candidates.add(normalized_query.casefold())

    results: list[tuple[float, PromptDocument]] = []
    for document in documents:
        haystack = _build_prompt_haystack(document)
        token_score = _token_match_score(tokens, haystack)
        fuzzy_score = _fuzzy_match_score(fuzzy_candidates, document.metadata.prompt_id)

        if token_score == 0.0 and fuzzy_score < fuzzy_threshold:
            continue

        score = max(token_score, fuzzy_score)
        results.append((score, document))

    results.sort(key=lambda item: (-item[0], item[1].metadata.prompt_id))
    return [document for _, document in results]


def _scan_directory[DocumentT: BaseDocument](
    *,
    store_path: Path,
    relative_dir: str,
    loader: Callable[[Path], DocumentT],
    allowed_suffixes: tuple[str, ...],
) -> list[DocumentT]:
    directory = (store_path / relative_dir).resolve()
    if not directory.exists():
        msg = f"Missing {relative_dir} directory under {store_path}"
        raise ContentError(msg)
    if not directory.is_dir():
        msg = f"{directory} must be a directory"
        raise ContentError(msg)

    files = _list_files(directory, allowed_suffixes)
    return [loader(path) for path in files]


def _list_files(directory: Path, allowed_suffixes: tuple[str, ...]) -> list[Path]:
    allowed = tuple(suffix.lower() for suffix in allowed_suffixes)
    results = [
        candidate
        for candidate in sorted(directory.rglob("*"))
        if candidate.is_file() and candidate.suffix.lower() in allowed
    ]
    return results


def _normalize_query_values(values: str | Iterable[str] | None) -> set[str]:
    """Return a casefolded set of query terms."""
    if values is None:
        return set()
    if isinstance(values, str):
        candidates = [values]
    else:
        candidates = list(values)

    normalized: list[str] = []
    for candidate in candidates:
        trimmed = candidate.strip()
        if not trimmed:
            continue
        normalized.append(trimmed.casefold())
    return set(normalized)


def _metadata_value_set(values: Iterable[str]) -> set[str]:
    """Return a normalized set for metadata fields."""
    return {value.strip().casefold() for value in values if value.strip()}


def _tokenize_query(query: str) -> list[str]:
    """Split and normalize the search query."""
    return [token.casefold() for token in query.split() if token.strip()]


def _build_prompt_haystack(document: PromptDocument) -> str:
    """Concatenate metadata and body for search matching."""
    parts = [
        document.metadata.prompt_id,
        document.metadata.title or "",
        " ".join(document.metadata.tags),
        " ".join(document.metadata.repos),
        " ".join(document.metadata.agents),
        document.body,
    ]
    return " ".join(parts).casefold()


def _token_match_score(tokens: list[str], haystack: str) -> float:
    """Return a score based on token occurrences."""
    if not tokens:
        return 0.0
    if all(token in haystack for token in tokens):
        return 2.0 + 0.1 * len(tokens)
    if any(token in haystack for token in tokens):
        return 1.0
    return 0.0


def _fuzzy_match_score(candidates: set[str], prompt_id: str) -> float:
    """Return the best fuzzy match ratio for the provided prompt id."""
    identifier = prompt_id.casefold()
    scores = [SequenceMatcher(a=candidate, b=identifier).ratio() for candidate in candidates if candidate]
    if not scores:
        return 0.0
    return max(scores)


def _load_document[MetadataModel: (PromptMetadata, RuleMetadata)](
    path: Path, model_cls: type[MetadataModel]
) -> tuple[MetadataModel, str]:
    if not path.is_file():
        msg = f"Document not found: {path}"
        raise ContentError(msg)

    metadata_payload, body = parse_frontmatter(path.read_text(encoding="utf-8"))
    try:
        metadata = model_cls(**metadata_payload)
    except (ValidationError, TypeError, ValueError) as exc:
        msg = f"Invalid metadata in {path}: {exc}"
        raise ContentError(msg) from exc
    return metadata, body
