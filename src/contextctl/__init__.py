"""Public exports for the contextctl package."""

from .config import (
    REPO_CONFIG_FILENAME,
    ConfigError,
    create_default_config,
    find_repo_root,
    load_repo_config,
)
from .content import (
    ContentError,
    PromptDocument,
    RuleDocument,
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
from .models import PromptLibConfig, PromptMetadata, RepoConfig, RuleMetadata
from .store import (
    StoreSyncError,
    clear_store_cache,
    ensure_store_root,
    get_store_path,
    sync_central_repo,
)

__all__ = [
    "REPO_CONFIG_FILENAME",
    "ConfigError",
    "ContentError",
    "PromptDocument",
    "PromptLibConfig",
    "PromptMetadata",
    "RepoConfig",
    "RuleDocument",
    "RuleMetadata",
    "StoreSyncError",
    "clear_store_cache",
    "create_default_config",
    "ensure_store_root",
    "filter_by_agent",
    "filter_by_repo",
    "filter_by_tags",
    "find_repo_root",
    "get_store_path",
    "load_prompt",
    "load_repo_config",
    "load_rule",
    "parse_frontmatter",
    "scan_prompts_dir",
    "scan_rules_dir",
    "search_prompts",
    "sync_central_repo",
]
