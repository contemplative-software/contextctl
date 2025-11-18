"""Document loading utilities."""

from __future__ import annotations

from collections.abc import Sequence
from pathlib import Path
from typing import Final

from contextctl import ContentError, PromptDocument, RuleDocument, load_prompt, load_rule

_SET_FILE_SUFFIXES: Final[tuple[str, ...]] = (".md", ".markdown", ".yml", ".yaml")
_RULE_FILE_SUFFIXES: Final[tuple[str, ...]] = (".md", ".markdown")
_PROMPT_FILE_SUFFIXES: Final[tuple[str, ...]] = (".md", ".markdown")


def load_selected_rules(store_path: Path, selections: Sequence[str]) -> list[RuleDocument]:
    """Load and return rule documents that match the configured selections.
    
    Args:
        store_path: Root of the synchronized prompt store.
        selections: List of rule set identifiers to load.
        
    Returns:
        List of loaded RuleDocument instances.
        
    Raises:
        ContentError: If selections cannot be resolved or loaded.
    """
    rules_root = (store_path / "rules").resolve()
    if not rules_root.exists() or not rules_root.is_dir():
        msg = f"No rules directory found under {store_path}"
        raise ContentError(msg)

    documents: list[RuleDocument] = []
    for selection in selections:
        normalized = selection.strip()
        if not normalized:
            continue
        matched = _load_rules_for_selection(rules_root, normalized)
        if not matched:
            msg = f"No rule documents matched '{selection}'."
            raise ContentError(msg)
        documents.extend(matched)

    if not documents:
        msg = "No rule documents were loaded for the configured rule sets."
        raise ContentError(msg)
    return documents


def _load_rules_for_selection(rules_root: Path, selection: str) -> list[RuleDocument]:
    """Return RuleDocument instances for a specific selection entry.
    
    Args:
        rules_root: Path to the rules directory.
        selection: Rule set identifier.
        
    Returns:
        List of loaded rule documents.
    """
    directory = _resolve_selection_directory(rules_root, selection)
    if directory is not None:
        files = _collect_rule_files(directory)
        return [load_rule(path) for path in files]

    files = _resolve_selection_files(rules_root, selection)
    return [load_rule(path) for path in files]


def _resolve_selection_directory(rules_root: Path, selection: str) -> Path | None:
    """Return the directory that matches the selection, if present.
    
    Args:
        rules_root: Path to the rules directory.
        selection: Directory name to resolve.
        
    Returns:
        Resolved directory path or None if not found.
    """
    candidate = (rules_root / selection).resolve()
    root = rules_root.resolve()
    if not _is_within_root(candidate, root):
        return None
    if candidate.is_dir():
        return candidate
    return None


def _resolve_selection_files(rules_root: Path, selection: str) -> list[Path]:
    """Return file paths that match a selection string.
    
    Args:
        rules_root: Path to the rules directory.
        selection: File name or stem to resolve.
        
    Returns:
        List of matching file paths.
    """
    root = rules_root.resolve()

    candidate = (rules_root / selection).resolve()
    if candidate.is_file() and _is_within_root(candidate, root):
        return [candidate]

    selection_path = Path(selection)
    if not selection_path.suffix:
        for suffix in _RULE_FILE_SUFFIXES:
            candidate_with_suffix = (rules_root / selection_path).with_suffix(suffix).resolve()
            if candidate_with_suffix.is_file() and _is_within_root(candidate_with_suffix, root):
                return [candidate_with_suffix]

    if len(selection_path.parts) == 1:
        matches = [path for path in _collect_rule_files(rules_root) if path.stem == selection_path.stem]
        if matches:
            return matches

    return []


def _collect_rule_files(directory: Path) -> list[Path]:
    """Return rule documents discovered beneath the provided directory.
    
    Args:
        directory: Directory to search for rule files.
        
    Returns:
        Sorted list of rule file paths.
    """
    return [
        path for path in sorted(directory.rglob("*")) if path.is_file() and path.suffix.lower() in _RULE_FILE_SUFFIXES
    ]


def _is_within_root(path: Path, root: Path) -> bool:
    """Return True if the provided path is within the expected root directory.
    
    Args:
        path: Path to check.
        root: Expected root directory.
        
    Returns:
        True if path is within root, False otherwise.
    """
    try:
        path.relative_to(root)
    except ValueError:
        return False
    return True


def load_prompt_documents(store_path: Path, selections: Sequence[str]) -> list[PromptDocument]:
    """Load prompt documents honoring the configured prompt set selections.
    
    Args:
        store_path: Root of the synchronized prompt store.
        selections: List of prompt set identifiers to load.
        
    Returns:
        List of loaded PromptDocument instances.
        
    Raises:
        ContentError: If selections cannot be resolved or loaded.
    """
    prompts_root = (store_path / "prompts").resolve()
    if not prompts_root.exists() or not prompts_root.is_dir():
        msg = f"No prompts directory found under {store_path}"
        raise ContentError(msg)

    if not selections:
        files = _collect_prompt_files(prompts_root)
        return [load_prompt(path) for path in files]

    seen: set[Path] = set()
    ordered_paths: list[Path] = []

    for selection in selections:
        normalized = selection.strip()
        if not normalized:
            continue
        matched_paths = _load_prompts_for_selection(prompts_root, normalized)
        if not matched_paths:
            msg = f"No prompt documents matched '{selection}'."
            raise ContentError(msg)
        for path in matched_paths:
            resolved = path.resolve()
            if resolved in seen:
                continue
            seen.add(resolved)
            ordered_paths.append(resolved)

    if not ordered_paths:
        msg = "No prompt documents were loaded for the configured prompt sets."
        raise ContentError(msg)

    return [load_prompt(path) for path in ordered_paths]


def _load_prompts_for_selection(prompts_root: Path, selection: str) -> list[Path]:
    """Return prompt file paths for a specific selection entry.
    
    Args:
        prompts_root: Path to the prompts directory.
        selection: Prompt set identifier.
        
    Returns:
        List of prompt file paths.
    """
    directory = _resolve_selection_directory(prompts_root, selection)
    if directory is not None:
        return _collect_prompt_files(directory)
    return _resolve_prompt_selection_files(prompts_root, selection)


def _resolve_prompt_selection_files(prompts_root: Path, selection: str) -> list[Path]:
    """Return prompt file paths that match a selection string.
    
    Args:
        prompts_root: Path to the prompts directory.
        selection: File name or stem to resolve.
        
    Returns:
        List of matching file paths.
    """
    root = prompts_root.resolve()

    candidate = (prompts_root / selection).resolve()
    if candidate.is_file() and _is_within_root(candidate, root):
        return [candidate]

    selection_path = Path(selection)
    if not selection_path.suffix:
        for suffix in _PROMPT_FILE_SUFFIXES:
            candidate_with_suffix = (prompts_root / selection_path).with_suffix(suffix).resolve()
            if candidate_with_suffix.is_file() and _is_within_root(candidate_with_suffix, root):
                return [candidate_with_suffix]

    if len(selection_path.parts) == 1:
        matches = [path for path in _collect_prompt_files(prompts_root) if path.stem == selection_path.stem]
        if matches:
            return matches

    return []


def _collect_prompt_files(directory: Path) -> list[Path]:
    """Return prompt documents discovered beneath the provided directory.
    
    Args:
        directory: Directory to search for prompt files.
        
    Returns:
        Sorted list of prompt file paths.
    """
    return [
        path
        for path in sorted(directory.rglob("*"))
        if path.is_file() and path.suffix.lower() in _PROMPT_FILE_SUFFIXES
    ]


def list_allowed_files(directory: Path) -> list[Path]:
    """Return files within the directory matching supported suffixes.
    
    Args:
        directory: Directory to search.
        
    Returns:
        List of files with allowed suffixes.
    """
    allowed = tuple(suffix.lower() for suffix in _SET_FILE_SUFFIXES)
    results = [path for path in sorted(directory.rglob("*")) if path.is_file() and path.suffix.lower() in allowed]
    return results
