# Implementation Plan: contextctl CLI - Phase 1 MVP

**Date:** 2025-11-15  
**Related Problem Definition:** `docs/problem_definition.md`  
**Related Design Proposal:** `docs/design.md`

## Overview
Build a Python-based CLI tool that manages a centralized prompt library and repo-specific rule associations. The MVP (Phase 1) will deliver core functionality: initialization, rule fetching, prompt listing/searching, and prompt execution with automatic background syncing from a central Git repository.

## Approach & Design

### High-Level Architecture
- **CLI Framework:** Typer for command-line interface with rich output formatting
- **Configuration:** YAML-based `.promptlib.yml` for repo-specific settings
- **Storage:** Git-based central repository containing prompts and rules with YAML frontmatter
- **Syncing:** Automatic pull from central repo before each command execution
- **Type Safety:** Full type hints with Pydantic models for validation

### Key Design Decisions
1. **Flat module structure** - Keep dependencies at package root per standards
2. **Dependency injection** - Pass Git clients, config loaders explicitly
3. **Immutable configs** - Use frozen dataclasses/Pydantic for state
4. **Tool-agnostic output** - Support multiple formats (text, JSON, structured)
5. **Auto-sync model** - Eliminate manual sync commands; always fresh data

### Data Flow
```
CLI Command → Sync Central Repo → Load Config → Parse Metadata → Execute Action → Format Output
```

## Implementation Steps

### Phase 1: Foundation & Setup
**Goal:** Establish project structure, dependencies, and core data models

1. [x] Configure pyproject.toml with dependencies (typer, pydantic, pyyaml, gitpython, rich)
2. [x] Create core package structure under `src/contextctl/`
3. [x] Set up pytest configuration and test fixtures
4. [x] Configure ruff and mypy rules
5. [x] Define `PromptMetadata` Pydantic model (id, tags, repo associations, agent compatibility, version)
6. [x] Define `RuleMetadata` Pydantic model with similar fields
7. [x] Define `RepoConfig` model for `.promptlib.yml` structure (central_repo_url, rules, prompt_sets, version_lock)
8. [x] Define `PromptLibConfig` model for global settings
9. [x] Add validation logic and custom validators to models
10. [x] Write unit tests for all models and validation logic

### Phase 2: Configuration & Storage Layer
**Goal:** Implement configuration management and Git-based central store syncing

11. [x] Implement `find_repo_root()` to locate git repo boundary
12. [x] Implement `load_repo_config()` function to read/parse `.promptlib.yml`
13. [x] Implement `create_default_config()` for initial setup
14. [x] Add config validation with helpful error messages
15. [x] Add support for environment variable overrides (CONTEXTCTL_*)
16. [x] Implement `get_store_path()` to determine local cache location (~/.contextctl/store)
17. [x] Implement `sync_central_repo()` using GitPython to clone/pull central repo (support both Git URLs and local paths)
18. [x] Add error handling for network failures, timeouts (5s max), and git conflicts
19. [x] Implement fallback to stale cache with warning when sync fails
20. [x] Implement cleanup/cache management utilities
21. [x] Add progress indicators using rich for sync operations
22. [x] Write unit tests for config loading, parsing, and store management
23. [x] Mock Git operations for testing

### Phase 3: Content Parsing & Indexing
**Goal:** Parse YAML frontmatter and build prompt/rule index

24. [x] Implement `parse_frontmatter()` to extract YAML metadata from markdown files
25. [x] Implement `load_prompt()` to parse individual prompt files
26. [x] Implement `load_rule()` to parse rule files
27. [x] Add validation for required metadata fields
28. [x] Implement `scan_prompts_dir()` to index all prompts in store
29. [x] Implement `scan_rules_dir()` to index all rules in store
30. [x] Write unit tests for frontmatter parsing and indexing
31. [x] Create test fixtures for sample prompts/rules with various metadata

### Phase 4: Filtering & Search Engine
**Goal:** Implement filtering and search capabilities

32. [ ] Implement `filter_by_repo()` to match prompts/rules to current repo
33. [ ] Implement `filter_by_tags()` for tag-based filtering
34. [ ] Implement `filter_by_agent()` for agent compatibility filtering
35. [ ] Implement `search_prompts()` for text search across content
36. [ ] Add fuzzy matching for prompt IDs
37. [ ] Write unit tests for filtering and search logic
38. [ ] Test edge cases (empty results, malformed queries, special characters)

### Phase 5: CLI Framework & Base Commands
**Goal:** Set up Typer CLI framework with core infrastructure

39. [ ] Set up Typer app with global options (--verbose, --no-sync, --force-sync, --help)
40. [ ] Implement pre-command hook for automatic syncing (5s timeout, fallback to cache on failure)
41. [ ] Add rich console configuration for styled output
42. [ ] Implement error handling and user-friendly messages
43. [ ] Add version command
44. [ ] Write integration tests for CLI framework and error handling

### Phase 6: CLI Command - init
**Goal:** Implement repository initialization workflow

45. [ ] Implement interactive wizard for initial setup
46. [ ] Prompt for central repository URL or local path with validation
47. [ ] Allow selection of rule sets (with preview)
48. [ ] Allow selection of prompt sets (with preview)
49. [ ] Generate `.promptlib.yml` in repo root with `central_repo` field
50. [ ] Add validation and confirmation before writing config
51. [ ] Write integration tests for init command (happy path and errors)

### Phase 7: CLI Command - rules
**Goal:** Implement rule fetching and merging

52. [ ] Implement rule fetching based on repo config
53. [ ] Concatenate multiple rule files in order specified in `.promptlib.yml`
54. [ ] Support output formats (text, json, cursor-format) via --format flag
55. [ ] Add --save option to write to `.cursor/rules/`
56. [ ] Display rule metadata and sources
57. [ ] Write integration tests for rules command with multiple scenarios

### Phase 8: CLI Commands - list & search
**Goal:** Implement prompt browsing and search commands

58. [ ] Implement prompt listing with rich table output
59. [ ] Show ID, title, tags, agent compatibility in list
60. [ ] Filter list by repo associations from config
61. [ ] Add --all flag to show all prompts regardless of repo
62. [ ] Add --tags filter option to list command
63. [ ] Add pagination for large lists
64. [ ] Implement text search across prompt content
65. [ ] Search in titles, descriptions, and tags
66. [ ] Display search results with context snippets
67. [ ] Add --exact flag for exact matching
68. [ ] Support multiple search terms
69. [ ] Write integration tests for list and search commands

### Phase 9: CLI Commands - run & tree
**Goal:** Implement prompt execution and tree view

70. [ ] Implement prompt retrieval by ID in run command
71. [ ] Strip frontmatter and output clean prompt content
72. [ ] Support variable substitution using {{variable}} syntax
73. [ ] Parse --var key=value flags (support multiple)
74. [ ] Add --format option (text, json) to run command
75. [ ] Add --copy flag to copy to clipboard
76. [ ] Add --output flag to write to file
77. [ ] Implement tree view of prompt library structure
78. [ ] Show hierarchical organization of prompts/rules
79. [ ] Highlight repo-relevant items in tree view
80. [ ] Add collapsible/expandable sections to tree
81. [ ] Write integration tests for run and tree commands

### Phase 10: Documentation & Polish
**Goal:** Complete documentation and prepare for release

82. [ ] Write docstrings for all public functions and classes (Google style)
83. [ ] Create README with installation and usage examples
84. [ ] Document `.promptlib.yml` schema and options
85. [ ] Create example central repository structure
86. [ ] Add troubleshooting guide
87. [ ] Run ruff format and fix all linting issues
88. [ ] Run mypy and resolve all type errors
89. [ ] Ensure all tests pass with >80% coverage
90. [ ] Add pre-commit hooks configuration
91. [ ] Create release script/workflow
92. [ ] Tag v0.1.0 for MVP release

### Progress Tracking
- **Phase 1:** Steps 1-10 (Foundation)
- **Phase 2:** Steps 11-23 (Configuration & Storage)
- **Phase 3:** Steps 24-31 (Parsing & Indexing)
- **Phase 4:** Steps 32-38 (Filtering & Search)
- **Phase 5:** Steps 39-44 (CLI Framework)
- **Phase 6:** Steps 45-51 (init command)
- **Phase 7:** Steps 52-57 (rules command)
- **Phase 8:** Steps 58-69 (list & search commands)
- **Phase 9:** Steps 70-81 (run & tree commands)
- **Phase 10:** Steps 82-92 (Documentation & Release)

## Dependencies & External Requirements

### Python Packages
- `typer[all]` - CLI framework with rich output
- `pydantic` - Data validation and settings
- `pyyaml` - YAML parsing
- `gitpython` - Git operations
- `rich` - Terminal formatting and progress
- `click` - Core CLI utilities (via typer)

### Development Dependencies
- `pytest` - Testing framework
- `pytest-cov` - Coverage reporting
- `pytest-mock` - Mocking utilities
- `ruff` - Linting and formatting
- `mypy` - Type checking

### External Resources
- Central prompt library Git repository (TBD - need URL)
- Network access for git clone/pull operations

## Risks & Mitigations

| Risk | Impact | Mitigation |
|------|--------|-----------|
| Central repo unavailable | High - CLI unusable | Implement local cache fallback; allow offline mode |
| Large prompt library slow sync | Medium - poor UX | Implement shallow clone; cache strategy; show progress |
| YAML schema drift | Medium - parsing errors | Version lock mechanism; schema validation; migrations |
| Git conflicts in cache | Low - sync failures | Force pull with conflict resolution; clear cache option |
| Cross-platform path issues | Low - portability | Use pathlib; test on Windows/Mac/Linux |

## Success Criteria

1. ✅ Developer can run `contextctl init` and configure repo in <2 minutes
2. ✅ `contextctl list` shows all relevant prompts for current repo
3. ✅ `contextctl rules` outputs merged rules ready for AI tool consumption
4. ✅ `contextctl run <id>` retrieves and displays prompt content
5. ✅ All commands automatically sync in background (<5s typical)
6. ✅ Type checking passes with zero errors
7. ✅ Test coverage >80% on core modules
8. ✅ Works on macOS, Linux, Windows

## Phase 2 Preview (Out of Scope for MVP)

The following features are explicitly deferred to Phase 2:
- Semantic versioning and version locking
- Local overrides for prompts/rules
- Advanced output formats and transformations
- Plugin system for extensibility
- Analytics and usage tracking
- Automated testing beyond unit/integration tests

## Design Decisions (Clarifying Questions - Resolved)

### 1. Central Repository Location
**Decision:** User provides the Git URL or local directory path during `contextctl init`
- Support both Git URLs (https/ssh) and local filesystem paths
- Store in `.promptlib.yml` as `central_repo` field
- Allow override via `CONTEXTCTL_CENTRAL_REPO` environment variable

### 2. Authentication
**Decision:** Leverage Git's native credential management (simplest approach)
- Use system Git credentials (no custom auth layer)
- Git URLs with SSH keys: user's `~/.ssh/config` handles auth
- Git URLs with HTTPS: Git credential helper manages tokens
- Local paths: filesystem permissions apply
- **Rationale:** No need to reinvent the wheel; Git already solves this securely

### 3. Caching Strategy  
**Decision:** Cache is always valid; sync on every command (fast background operation)
- Sync timeout: 5 seconds max per command
- If sync fails (network/timeout), use stale cache with warning
- User can force fresh sync with `--force-sync` flag
- User can skip sync with `--no-sync` flag for offline work
- **Rationale:** Prompts change frequently; always having latest is worth 1-2s overhead

### 4. Offline Mode
**Decision:** Support local directory paths as "offline mode"
- User can provide local filesystem path instead of Git URL
- Path can be:
  - A Git repository (clone of central store)
  - A plain directory with prompt/rule structure
- No sync operation performed for local paths
- **Rationale:** Simple, explicit, no network detection complexity

### 5. Default Rules/Prompts
**Decision:** No defaults shipped with tool; require central repo setup
- Tool only provides the management infrastructure
- User must configure central repo during `contextctl init`
- Prompt user to set up central repo if missing
- **Rationale:** Keeps tool focused; organizations define their own standards

### 6. Agent Detection
**Decision:** Not implemented in MVP (Phase 1)
- Defer to Phase 2 or 3
- User manually specifies output format with `--format` flag
- **Rationale:** Keep MVP scope tight; easy to add later

### 7. Prompt Variable Substitution
**Decision:** Use `{{variable}}` syntax (Mustache-style)
- Variables passed via `--var key=value` flag to `contextctl run`
- Example: `contextctl run review-pr --var pr_number=123`
- Support multiple variables: `--var key1=val1 --var key2=val2`
- **Rationale:** Familiar syntax, widely used, clear boundaries

### 8. Rule Merging Precedence
**Decision:** User's responsibility to maintain clean prompt store
- Rules are concatenated in the order specified in `.promptlib.yml`
- No conflict resolution or deduplication
- If conflicts exist, behavior is tool-dependent (Cursor/Claude's problem)
- **Rationale:** Keeps implementation simple; users control their content

### 9. Multi-Repo Support
**Decision:** Not implemented in MVP
- One central repo per workspace
- Defer to Phase 2 if needed
- **Rationale:** Reduces complexity; can be added if users request it

### 10. Error Reporting / Telemetry
**Decision:** No telemetry in MVP
- Errors logged locally only
- User can enable verbose mode with `--verbose` flag
- **Rationale:** Privacy-first; avoids infrastructure complexity

## References

- Problem Definition: `docs/problem_definition.md`
- Design Proposal: `docs/design.md`
- Coding Standards: `.cursor/rules/standards.mdc`
- Testing Guidelines: `.cursor/rules/testing.mdc`
- Python Standards: PEP 8, PEP 484 (type hints)
- Typer Documentation: https://typer.tiangolo.com/
- Pydantic Documentation: https://docs.pydantic.dev/

