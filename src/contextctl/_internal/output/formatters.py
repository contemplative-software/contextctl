"""Output formatting utilities for rules and prompts."""

from __future__ import annotations

import json
from collections.abc import Sequence
from pathlib import Path
from typing import Final

from contextctl import PromptDocument, RuleDocument

_RULE_SECTION_DIVIDER: Final[str] = "\n\n---\n\n"


def format_rules(documents: Sequence[RuleDocument], format_name: str, store_path: Path) -> str:
    """Return the merged rule content formatted according to the requested output.

    Args:
        documents: Rule documents to format.
        format_name: Output format (text, json, or cursor).
        store_path: Path to the prompt store for relative path resolution.

    Returns:
        Formatted rule content.

    Raises:
        ValueError: If format_name is not supported.
    """
    if format_name == "text":
        return format_rules_as_text(documents)
    if format_name == "json":
        return format_rules_as_json(documents, store_path)
    if format_name == "cursor":
        return format_rules_as_cursor(documents)
    msg = f"Unsupported format: {format_name}"
    raise ValueError(msg)


def format_rules_as_text(documents: Sequence[RuleDocument]) -> str:
    """Return merged rule content as plain text with lightweight headings.

    Args:
        documents: Rule documents to format.

    Returns:
        Text-formatted rule content.
    """
    sections: list[str] = []
    for document in documents:
        header = f"# {document.metadata.rule_id}"
        body = document.body.strip()
        sections.append(f"{header}\n\n{body}")
    return _RULE_SECTION_DIVIDER.join(sections).strip()


def format_rules_as_json(documents: Sequence[RuleDocument], store_path: Path) -> str:
    """Return merged rule content as a JSON array.

    Args:
        documents: Rule documents to format.
        store_path: Path to the prompt store for relative path resolution.

    Returns:
        JSON-formatted rule content.
    """
    payload: list[dict[str, object]] = []
    for document in documents:
        metadata = document.metadata
        payload.append(
            {
                "id": metadata.rule_id,
                "tags": metadata.tags,
                "repos": metadata.repos,
                "agents": metadata.agents,
                "version": metadata.version,
                "body": document.body,
                "source": relative_source(document.path, store_path),
            }
        )
    return json.dumps(payload, indent=2, ensure_ascii=False)


def format_rules_as_cursor(documents: Sequence[RuleDocument]) -> str:
    """Return merged rule content optimized for `.cursor/rules` consumption.

    Args:
        documents: Rule documents to format.

    Returns:
        Cursor-formatted rule content.
    """
    sections: list[str] = []
    for document in documents:
        metadata = document.metadata
        lines = [
            f"# {metadata.rule_id}",
            "",
            f"*Version:* {metadata.version}",
        ]
        if metadata.tags:
            lines.append(f"*Tags:* {', '.join(metadata.tags)}")
        if metadata.repos:
            lines.append(f"*Repos:* {', '.join(metadata.repos)}")
        if metadata.agents:
            lines.append(f"*Agents:* {', '.join(metadata.agents)}")
        lines.append("")
        lines.append(document.body.strip())
        sections.append("\n".join(lines).strip())
    return f"{_RULE_SECTION_DIVIDER}".join(sections).strip() + "\n"


def format_prompt_output(
    document: PromptDocument,
    body: str,
    format_name: str,
    store_path: Path,
) -> str:
    """Return the rendered prompt in the requested output format.

    Args:
        document: Prompt document to format.
        body: Rendered prompt body (with variables substituted).
        format_name: Output format (text or json).
        store_path: Path to the prompt store for relative path resolution.

    Returns:
        Formatted prompt output.

    Raises:
        ValueError: If format_name is not supported.
    """
    if format_name == "text":
        if body.endswith("\n"):
            return body
        return f"{body}\n"

    if format_name == "json":
        metadata = document.metadata
        payload = {
            "id": metadata.prompt_id,
            "title": metadata.title,
            "tags": metadata.tags,
            "repos": metadata.repos,
            "agents": metadata.agents,
            "version": metadata.version,
            "body": body,
            "source": relative_source(document.path, store_path),
        }
        return json.dumps(payload, indent=2, ensure_ascii=False)

    msg = f"Unsupported prompt output format: {format_name}"
    raise ValueError(msg)


def relative_source(path: Path, store_path: Path) -> str:
    """Return the document path relative to the store root, if possible.

    Args:
        path: Absolute path to the document.
        store_path: Path to the prompt store.

    Returns:
        Relative path string or absolute path if not within store.
    """
    try:
        return path.relative_to(store_path).as_posix()
    except ValueError:
        return path.as_posix()
