"""Document filtering and search utilities."""

from __future__ import annotations

import re
from collections.abc import Sequence
from typing import Final

from contextctl import PromptDocument, search_prompts

_VARIABLE_PATTERN: Final[re.Pattern[str]] = re.compile(r"{{\s*([A-Za-z0-9_.-]+)\s*}}")


def execute_search(documents: Sequence[PromptDocument], query: str, *, exact: bool) -> list[PromptDocument]:
    """Execute a fuzzy or exact search across prompt documents.
    
    Args:
        documents: Prompt documents to search.
        query: Search query string.
        exact: Whether to require exact phrase matches.
        
    Returns:
        List of matching prompt documents.
    """
    if exact:
        normalized_query = query.casefold()
        results: list[PromptDocument] = []
        for document in documents:
            if normalized_query in _prompt_search_haystack(document):
                results.append(document)
        return results
    return search_prompts(documents, query)


def _prompt_search_haystack(document: PromptDocument) -> str:
    """Return the lowercased haystack string for prompt searching.
    
    Args:
        document: Prompt document to build haystack from.
        
    Returns:
        Lowercase combined string of all searchable fields.
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
        documents: Prompt documents to search.
        prompt_id: Identifier to search for.
        
    Returns:
        Matching prompt document or None if not found.
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
        Dictionary of parsed variable assignments.
        
    Raises:
        ValueError: If an assignment is malformed.
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
    assignments: dict[str, str],
) -> tuple[str, set[str], set[str]]:
    """Substitute `{{variable}}` placeholders using the provided assignments.
    
    Args:
        body: Prompt body with variable placeholders.
        assignments: Dictionary of variable assignments.
        
    Returns:
        Tuple of (rendered_body, missing_vars, used_vars).
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
