## Manual Testing Plan – contextctl v0.1.0

This checklist is for **pre-release manual testing** of `contextctl` using a local example prompt library.

- **Central store path**: `path/to/context-library`
- **Prompts**: reviews, incidents, frontend/Next.js
- **Rules**: python, nextjs

### 1. Environment & Setup

- **Python environment**
  - Run `uv sync` in the `contextctl` repo.
  - Verify `uv run python -m contextctl.cli version` prints a version string.
- **Central store sanity check**
  - Confirm the central store has:
    - `prompts/reviews/review-pr.md`
    - `prompts/incidents/incident-response.md`
    - `prompts/frontend/nextjs-feature-request.md`
    - `rules/python/python-style.md`, `rules/python/python-testing.md`
    - `rules/nextjs/nextjs-style.md`, `rules/nextjs/nextjs-api-guidelines.md`

### 2. Initialization Flow (`contextctl init`)

- From the `contextctl` repo root (a git repo):
  - Run `uv run python -m contextctl.cli init`.
  - When prompted for the central repo, provide:
    - `/path/to/context-library`
  - Ensure:
    - `.promptlib.yml` is created/updated.
    - The rule set preview shows both `python` and `nextjs` under `rules/`.
    - The prompt set preview shows `reviews`, `incidents`, and `frontend`.
  - Select:
    - **Rules**: `python,nextjs`
    - **Prompt sets**: `reviews,frontend` (incidents optional).

### 3. Rules Command (`contextctl rules`)

- Run `uv run python -m contextctl.cli rules --format text`.
  - Expect a “Rule Sources” table listing:
    - `python-style`, `python-testing`, `nextjs-style`, `nextjs-api-guidelines`.
  - Confirm merged text output includes:
    - A section headed `# python-style`.
    - A section headed `# nextjs-style`.
- Run `uv run python -m contextctl.cli rules --format cursor --save`.
  - Verify `.cursor/rules/contextctl.mdc` exists and contains multiple rule sections.

### 4. List Prompts (`contextctl list`)

- Base listing (repo-scoped):
  - Run `uv run python -m contextctl.cli list --per-page 50`.
  - Confirm prompts table includes:
    - `review-pr` (tags include `python`/`backend`).
    - `nextjs-feature-request` **only if** its `repos` includes `contextctl`; otherwise, it should be hidden by repo filter.
- Tag filtering:
  - Run `uv run python -m contextctl.cli list --tag reviews --per-page 50`.
    - Expect at least `review-pr`.
  - Run `uv run python -m contextctl.cli list --tag nextjs --all --per-page 50`.
    - Expect `nextjs-feature-request`.
  - Run `uv run python -m contextctl.cli list --tag python --match-all-tags --per-page 50`.
    - Ensure only prompts that include all requested tags remain.

### 5. Search Prompts (`contextctl search`)

- Fuzzy and full-text search:
  - Run `uv run python -m contextctl.cli search \"pull request\" --per-page 20`.
    - Expect `review-pr` with a snippet referencing PR review.
  - Run `uv run python -m contextctl.cli search reviewpr`.
    - Expect `review-pr` due to fuzzy id matching.
  - Run `uv run python -m contextctl.cli search nextjs --all --tag nextjs`.
    - Expect `nextjs-feature-request` in results.
- Empty/edge cases:
  - Run `uv run python -m contextctl.cli search \"   \"` and confirm a user-friendly error.

### 6. Run Prompt (`contextctl run`)

- Run Python review prompt:
  - `uv run python -m contextctl.cli run review-pr --var repo_name=contextctl`
  - Confirm:
    - The rendered body includes the substituted repo name.
    - No errors about missing variables when all placeholders are supplied.
- Missing/extra variables:
  - `uv run python -m contextctl.cli run review-pr --var unused=foo`
    - Expect a warning about ignored variable assignments.
  - `uv run python -m contextctl.cli run review-pr --var repo_name=contextctl --format json`
    - Confirm JSON payload includes `id`, `tags`, `repos`, `agents`, `version`, `body`, and `source`.

### 7. Tree View (`contextctl tree`)

- Base tree:
  - Run `uv run python -m contextctl.cli tree`.
  - Confirm:
    - `prompts` and `rules` sections are present.
    - Files appear under directory branches matching the central store.
- Repo-only filtering:
  - Run `uv run python -m contextctl.cli tree --repo-only`.
  - Ensure:
    - Python-focused rules and prompts relevant to `contextctl` are marked as repo matches.
    - Next.js-only rules (e.g. `nextjs-style` for `nextjs-app`) are excluded if their `repos` do not include `contextctl`.

### 8. Local Path & Sync Behavior

- Ensure `.promptlib.yml` uses the local path central repo (no network required).
- Run:
  - `uv run python -m contextctl.cli rules --no-sync`
  - `uv run python -m contextctl.cli rules --force-sync`
  - Confirm:
    - Local path is treated as an existing store (no git errors).
    - Commands still resolve rules and prompts correctly.

### 9. Environment Override Smoke Test

- Temporarily move or rename `.promptlib.yml`.
- Set environment variables:

```bash
export CONTEXTCTL_CENTRAL_REPO=/path/to/context-library
export CONTEXTCTL_RULES=python,nextjs
export CONTEXTCTL_PROMPT_SETS=reviews,frontend
```

- Run:
  - `uv run python -m contextctl.cli rules`
  - `uv run python -m contextctl.cli list --per-page 50`
- Confirm behavior matches the `.promptlib.yml`-based configuration (same visible rules and prompts).


