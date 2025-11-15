# Prompt Library CLI "contextctl" – High-Level Implementation Plan

## 1. Overview
This document outlines the architectural and implementation plan for a Python-based CLI tool that manages a central prompt library and repo-specific rule associations, allowing teams to share prompts and rules without duplicating them across repositories.

## 2. Goals
- Centralized prompt and rule management
- Repo-aware CLI that pulls correct prompts based on configuration
- Tool-agnostic output for Claude, Cursor, JetBrains, etc.
- Prevent duplication and drift of prompt content
- Easy developer workflow for browsing, running, and retrieving prompts

## 3. Architecture
### Components
- **Central Prompt Store Repo**  
  Contains:
  - `/prompts/*.md`
  - `/rules/*.yml`
  - `/metadata/*.yml`

- **Per-Repo Config**  
  `.promptlib.yml` storing rule/prompt mappings.

- **CLI Tool**  
  Built in Python using Typer:
  - `prompt init`
  - `prompt sync`
  - `prompt rules`
  - `prompt list`
  - `prompt search`
  - `prompt run <prompt_id>`

- **Metadata Schema**
  Prompts and rules include YAML frontmatter indicating:
  - ids
  - repo associations
  - tags
  - agent compatibility
  - version

## 4. Workflow
### Developer Workflow
1. Run `prompt init` in repo → creates `.promptlib.yml`
2. Select rules + prompt sets
3. Run `prompt rules` to fetch merged rules
4. Run `prompt list` / `prompt search` to browse library
5. Run `prompt run <id>` to inject prompt into selected AI tool

### Admin Workflow
1. Add/update prompts centrally  
2. Update metadata for repo associations  
3. Developers pull changes with `prompt sync`

## 5. Implementation Phases
### Phase 1 — MVP
- Basic CLI commands (`init`, `rules`, `list`, `run`)
- Prompt store in Git
- YAML frontmatter parsing
- Repo-specific config lookup

### Phase 2 — Enhancements
- Semantic versioning for prompt sets
- Configurable output format (json, text, structured)
- Local overrides
- Automated testing

### Phase 3 — Advanced
- Central registry API (optional)
- Teams, permissions, analytics
- JetBrains/VSCode plugin integrations

## 6. File Structure
```
promptlib/
    cli/
        main.py
        commands/
            init.py
            sync.py
            list.py
            rules.py
            run.py
    core/
        store.py
        loader.py
        config.py
        models.py
    config/
        defaults.yml
```

## 7. Risks & Mitigations
- **Drift between repos** → Centralized model with versioning
- **Breaking changes** → Semantic version locks in `.promptlib.yml`
- **Developer adoption** → Provide shortcuts + agent integration

## 8. Summary
This CLI provides a durable, tool-agnostic system for managing prompts across many repositories. It eliminates duplication, accelerates prompt updates, and creates a shared knowledge base.
