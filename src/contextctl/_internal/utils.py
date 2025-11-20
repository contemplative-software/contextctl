"""General utility functions."""

from __future__ import annotations

from collections.abc import Sequence
from dataclasses import dataclass
from pathlib import Path
from typing import TypeVar

from contextctl import ConfigError, find_repo_root
from contextctl.content import BaseDocument

DocumentT = TypeVar("DocumentT", bound=BaseDocument)


@dataclass(frozen=True, slots=True)
class SetPreview:
    """Simple representation of the available rule or prompt sets.

    Attributes:
        name: Set name/identifier.
        item_count: Number of items in the set.
        sample_items: Sample of item names from the set.
    """

    name: str
    item_count: int
    sample_items: list[str]


@dataclass(frozen=True, slots=True)
class StorePreview:
    """Collection of preview information for store contents.

    Attributes:
        rule_sets: Preview of available rule sets.
        prompt_sets: Preview of available prompt sets.
    """

    rule_sets: list[SetPreview]
    prompt_sets: list[SetPreview]


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


def resolve_repo_slug() -> str | None:
    """Return the repository slug derived from the git root directory name.

    Returns:
        Repository slug or None if not in a git repository.
    """
    try:
        return find_repo_root().name
    except ConfigError:
        return None


def write_output_file(path: Path, content: str) -> Path:
    """Persist rendered prompt content to disk and return the resulting path.

    Args:
        path: Target file path.
        content: Content to write.

    Returns:
        Resolved path to the written file.

    Raises:
        OSError: If the path is a directory or writing fails.
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
        content: Formatted rules content.
        repo_root: Repository root directory.

    Returns:
        Path to the written rules file.
    """
    rules_dir = repo_root / ".cursor" / "rules"
    rules_dir.mkdir(parents=True, exist_ok=True)
    target = rules_dir / "contextctl.mdc"
    target.write_text(content, encoding="utf-8")
    return target


def normalize_csv(raw_value: str) -> list[str]:
    """Split comma-separated input and remove duplicates.

    Args:
        raw_value: Comma-separated string.

    Returns:
        List of unique normalized values.
    """
    seen: set[str] = set()
    results: list[str] = []
    for part in raw_value.split(","):
        trimmed = part.strip()
        if not trimmed:
            continue
        key = trimmed.casefold()
        if key in seen:
            continue
        seen.add(key)
        results.append(trimmed)
    return results


def summarize_files(files: Sequence[Path], limit: int = 3) -> list[str]:
    """Return a short preview of file stems for display.

    Args:
        files: File paths to summarize.
        limit: Maximum number of items to include.

    Returns:
        List of file stems with ellipsis if truncated.
    """
    items = [path.stem for path in files[:limit]]
    if len(files) > limit:
        items.append("...")
    return items
