"""Filtering and searching utilities for documents."""

from __future__ import annotations

import re
from collections.abc import Mapping, Sequence
from pathlib import Path
from typing import Final

from contextctl import PromptDocument, search_prompts
from contextctl.content import BaseDocument

_VARIABLE_PATTERN: Final[re.Pattern[str]] = re.compile(r"{{\s*([A-Za-z0-9_.-]+)\s*}}")


def paginate_items[DocumentT: BaseDocument](
    items: Sequence[DocumentT], page: int, per_page: int
) -> tuple[list[DocumentT], int, int]:
    """Return paginated items, total pages, and the resolved page number.
    
    Args:
        items: Items to paginate.
        page: Requested page number (1-indexed).
        per_page: Number of items per page.
        
    Returns:
        Tuple of (paginated_items, total_pages, resolved_page).
    """
    if not items:
        return [], 1, 1
    total = len(items)
    total_pages = max(1, (total + per_page - 1) // per_page)
    resolved_page = min(page, total_pages)
    start = (resolved_page - 1) * per_page
    end = start + per_page
    return list(items[start:end]), total_pages, resolved_page


def execute_search(documents: Sequence[PromptDocument], query: str, *, exact: bool) -> list[PromptDocument]:
    """Execute a fuzzy or exact search across prompt documents.
    
    Args:
        documents: Documents to search.
        query: Search query string.
        exact: Whether to require exact phrase matches.
        
    Returns:
        List of matching documents.
    """
    if exact:
        normalized_query = query.casefold()
        results: list[PromptDocument] = []
        for document in documents:
            if normalized_query in prompt_search_haystack(document):
                results.append(document)
        return results
    return search_prompts(documents, query)


def prompt_search_haystack(document: PromptDocument) -> str:
    """Return the lowercased haystack string for prompt searching.
    
    Args:
        document: Prompt document to build haystack from.
        
    Returns:
        Lowercased searchable text.
    """
    metadata = document.metadata
    parts = [
        metadata.prompt_id,
        metadata.title or "",
        " ".join(metadata.tags),
        " ".join(metadata.repos),
        " ".join(metadata.agents),
        document.body,
    ]
    return " ".join(parts).casefold()


def find_prompt_by_id(documents: Sequence[PromptDocument], prompt_id: str) -> PromptDocument | None:
    """Return the prompt document whose id matches the provided value.
    
    Args:
        documents: Documents to search.
        prompt_id: Prompt identifier to find.
        
    Returns:
        Matching document or None if not found.
    """
    normalized = prompt_id.strip().casefold()
    if not normalized:
        return None
    for document in documents:
        if document.metadata.prompt_id.casefold() == normalized:
            return document
    return None


def parse_variable_assignments(assignments: Sequence[str] | None) -> dict[str, str]:
    """Parse `--var` key=value pairs into a dictionary.
    
    Args:
        assignments: List of KEY=VALUE strings.
        
    Returns:
        Dictionary of variable assignments.
        
    Raises:
        ValueError: If assignments are malformed.
    """
    if not assignments:
        return {}
    parsed: dict[str, str] = {}
    for assignment in assignments:
        if "=" not in assignment:
            msg = f"Invalid variable assignment '{assignment}'. Expected KEY=VALUE."
            raise ValueError(msg)
        key, value = assignment.split("=", 1)
        normalized_key = key.strip()
        if not normalized_key:
            msg = "Variable names cannot be blank."
            raise ValueError(msg)
        parsed[normalized_key] = value
    return parsed


def apply_prompt_variables(
    body: str,
    assignments: Mapping[str, str],
) -> tuple[str, set[str], set[str]]:
    """Substitute `{{variable}}` placeholders using the provided assignments.
    
    Args:
        body: Prompt body with variable placeholders.
        assignments: Variable name to value mappings.
        
    Returns:
        Tuple of (rendered_body, missing_variables, used_variables).
    """
    if not assignments:
        return body, set(), set()

    missing: set[str] = set()
    used: set[str] = set()

    def replacer(match: re.Match[str]) -> str:
        key = match.group(1)
        value = assignments.get(key)
        if value is None:
            missing.add(key)
            return match.group(0)
        used.add(key)
        return value

    rendered = _VARIABLE_PATTERN.sub(replacer, body)
    return rendered, missing, used


def write_output_file(path: Path, content: str) -> Path:
    """Persist rendered prompt content to disk and return the resulting path.
    
    Args:
        path: Output file path.
        content: Content to write.
        
    Returns:
        Resolved path to the written file.
        
    Raises:
        OSError: If the path is a directory or write fails.
    """
    target = path.expanduser()
    if target.exists() and target.is_dir():
        msg = f"{target} is a directory"
        raise OSError(msg)
    target.parent.mkdir(parents=True, exist_ok=True)
    target.write_text(content, encoding="utf-8")
    return target.resolve()


def write_cursor_rules_file(content: str, *, repo_root: Path) -> Path:
    """Persist Cursor-formatted rules within `.cursor/rules/`.
    
    Args:
        content: Rule content to write.
        repo_root: Repository root directory.
        
    Returns:
        Path to the written file.
    """
    rules_dir = repo_root / ".cursor" / "rules"
    rules_dir.mkdir(parents=True, exist_ok=True)
    target = rules_dir / "contextctl.mdc"
    target.write_text(content, encoding="utf-8")
    return target
