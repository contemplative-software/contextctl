# contextctl

`contextctl` is a repo-aware CLI that keeps prompts and rules consistent across every codebase. It pulls the right content from a central Git repository, filters it for the current repo, and outputs the result in formats that work with Cursor, Claude Code, and other coding agents.

## Features

- 🔄 Automatic background sync from a central prompt store (with 5 s timeout + cache fallback)
- 📁 Repo-scoped `.promptlib.yml` that declares rule and prompt sets
- 🧭 Browse (`list`), search (`search`), render (`run`), and tree views (`tree`)
- 🧩 Rich filtering by repo, tags, and agent compatibility
- 🧮 Fuzzy search with contextual snippets
- 📜 Cursor-friendly rule exports and optional clipboard/file output

## Installation

### From Source (recommended for now)

```bash
git clone https://github.com/contemplative-software/contextctl.git
cd contextctl

# Install dependencies into a UV-managed environment
uv sync

# Run the CLI
uv run python main.py --help
# or invoke the module directly
uv run python -m contextctl.cli --help
```

### As a UV tool (once published)

```bash
uv tool install contextctl
contextctl --help
```

## Quick Start

1. **Initialize** the current repo:

   ```bash
   contextctl init
   ```

   This writes `.promptlib.yml` at the repo root and lets you pick rule/prompt sets.

2. **Fetch rules** and send them to Cursor:

   ```bash
   contextctl rules --format cursor --save
   ```

3. **Browse prompts**:

   ```bash
   contextctl list --tag onboarding --per-page 30
   ```

4. **Search prompts**:

   ```bash
   contextctl search onboarding backend --tag hiring --limit 10
   ```

5. **Run a prompt**:

   ```bash
   contextctl run incident-review --var incident_id=1234 --copy
   ```

6. **Inspect the tree**:

   ```bash
   contextctl tree --repo-only
   ```

## Repository Configuration (`.promptlib.yml`)

Each repository contains a lightweight YAML file that points to the central store and declares which sets to load:

```yaml
central_repo: git@github.com:org/promptlib.git
rules:
  - platform
  - SRE
prompt_sets:
  - engineering/oncall
  - engineering/postmortem
version_lock: 0.1.0
```

### Fields

| Field        | Description                                                                 |
|--------------|-----------------------------------------------------------------------------|
| `central_repo` | Git URL or local path for the shared prompt library (required).            |
| `rules`        | Ordered list of rule sets to concatenate when running `contextctl rules`.  |
| `prompt_sets`  | Ordered list of prompt sets to expose to the repo.                         |
| `version_lock` | Optional semantic version pin if your central repo uses tags/releases.     |

### Environment Overrides

All settings can be overridden at runtime via environment variables:

| Variable                      | Effect                         | Example                                   |
|-------------------------------|--------------------------------|-------------------------------------------|
| `CONTEXTCTL_CENTRAL_REPO`     | Replaces `central_repo`        | `CONTEXTCTL_CENTRAL_REPO=/tmp/promptlib`  |
| `CONTEXTCTL_RULES`            | CSV list of rule sets          | `CONTEXTCTL_RULES=platform,SRE`           |
| `CONTEXTCTL_PROMPT_SETS`      | CSV list of prompt sets        | `CONTEXTCTL_PROMPT_SETS=engineering/oncall` |
| `CONTEXTCTL_VERSION_LOCK`     | Overrides `version_lock`       | `CONTEXTCTL_VERSION_LOCK=0.2.0`           |

## Example Central Repository Structure

```
promptlib/
├── prompts/
│   ├── engineering/
│   │   ├── oncall/
│   │   │   ├── incident-review.md
│   │   │   └── handoff.md
│   │   └── postmortem/
│   │       └── template.md
│   └── product/
│       └── launch-readiness.md
├── rules/
│   ├── platform/
│   │   ├── build.mdc
│   │   └── deploy.mdc
│   └── sre/
│       └── pager.mdc
└── metadata/
    └── README.md
```

Each markdown file starts with YAML frontmatter:

```markdown
---
id: incident-review
title: Incident Review Checklist
tags: [sre, oncall]
repos: [production-api]
agents: [cursor]
version: 1.2.0
---
...prompt body...
```

## Troubleshooting

See `docs/troubleshooting.md` for detailed failure modes, including:

- Missing `.promptlib.yml`
- Git sync failures and offline mode
- Invalid metadata or schema violations
- Clipboard or file-output issues on various platforms

## Development

```bash
# Install dependencies
uv sync

# Format & lint
uv run ruff format .
uv run ruff check .

# Type check
uv run mypy

# Run unit tests with coverage
uv run pytest --cov=src/contextctl --cov-report=term-missing

# Install pre-commit hooks
uv run pre-commit install
```

### Optional Docker/Devcontainer Workflows

```bash
uv sync
docker compose build
docker compose up
```

You can also open the repo in VS Code and choose **Reopen in Container** for the provided devcontainer setup.
