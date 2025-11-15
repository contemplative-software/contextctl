"""Parsing and indexing helpers for prompt and rule documents."""

from __future__ import annotations

import re
from collections.abc import Callable
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Final, TypeVar

import yaml
from pydantic import ValidationError

from contextctl.models import PromptMetadata, RuleMetadata

_FRONTMATTER_BOUNDARY: Final[re.Pattern[str]] = re.compile(r"^---\s*$", re.MULTILINE)
_PROMPT_SUFFIXES: Final[tuple[str, ...]] = (".md", ".markdown")
_RULE_SUFFIXES: Final[tuple[str, ...]] = (".md", ".markdown")

MetadataModel = TypeVar("MetadataModel", PromptMetadata, RuleMetadata)
DocumentT = TypeVar("DocumentT", bound="BaseDocument")


class ContentError(RuntimeError):
    """Raised when prompt or rule content cannot be parsed."""


@dataclass(frozen=True, slots=True)
class BaseDocument:
    """Common fields shared across prompt and rule documents."""

    metadata: PromptMetadata | RuleMetadata
    body: str
    path: Path


@dataclass(frozen=True, slots=True)
class PromptDocument(BaseDocument):
    """Parsed prompt content."""

    metadata: PromptMetadata


@dataclass(frozen=True, slots=True)
class RuleDocument(BaseDocument):
    """Parsed rule content."""

    metadata: RuleMetadata


def parse_frontmatter(raw_text: str) -> tuple[dict[str, Any], str]:
    """Extract YAML metadata and body content from a markdown document."""
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
    """Load a prompt file and return its metadata and body."""
    metadata, body = _load_document(path, PromptMetadata)
    return PromptDocument(metadata=metadata, body=body, path=path)


def load_rule(path: Path) -> RuleDocument:
    """Load a rule file and return its metadata and body."""
    metadata, body = _load_document(path, RuleMetadata)
    return RuleDocument(metadata=metadata, body=body, path=path)


def scan_prompts_dir(store_path: Path) -> list[PromptDocument]:
    """Return all prompts discovered under the `prompts/` directory."""
    return _scan_directory(
        store_path=store_path,
        relative_dir="prompts",
        loader=load_prompt,
        allowed_suffixes=_PROMPT_SUFFIXES,
    )


def scan_rules_dir(store_path: Path) -> list[RuleDocument]:
    """Return all rules discovered under the `rules/` directory."""
    return _scan_directory(
        store_path=store_path,
        relative_dir="rules",
        loader=load_rule,
        allowed_suffixes=_RULE_SUFFIXES,
    )


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
