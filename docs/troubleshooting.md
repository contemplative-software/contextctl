# Troubleshooting Guide

This document collects the most common issues encountered when running `contextctl` and how to fix them quickly.

## Missing `.promptlib.yml`

- **Symptom:** Every command fails with `Missing .promptlib.yml in /path/to/repo`.
- **Fix:** Run `contextctl init` from the repository root. The wizard will create `.promptlib.yml` and validate the central repository path.
- **Verify:** `ls .promptlib.yml` should succeed and commands such as `contextctl list` should no longer error.

## Unable to locate git repository

- **Symptom:** `Unable to locate a git repository starting from ...`
- **Fix:** Ensure you run the CLI from inside a git repository. If using a subdirectory, `cd` to the repo root or pass `--project /path/to/repo` when invoking from scripts.

## Central repo sync failures

- **Symptom:** `Unable to synchronize central prompt repository` or Rich warning about cached fallback.
- **Fixes:**
  - Confirm the device has network access to the Git remote.
  - Re-run with `--force-sync` to drop stale caches: `contextctl list --force-sync`.
  - For offline work, point `.promptlib.yml` `central_repo` at a local clone (e.g., `/opt/promptlib`).
- **Verify:** `~/.contextctl/store/<slug>/.git` should exist and `contextctl tree` should show documents.

## Invalid YAML or metadata

- **Symptom:** Errors such as `Invalid metadata in ...` or `Document must begin with YAML frontmatter`.
- **Fix:** Each markdown file must start with `---` frontmatter that matches the schema. Run `pytest tests/test_content.py::test_sample_payloads` to validate changes before committing.

## Clipboard failures

- **Symptom:** `Clipboard integration is not available on this platform.`
- **Fix:** Install `pyperclip` (`uv add pyperclip`) or ensure a supported clipboard utility exists (`pbcopy`, `clip`, `xclip`, or `wl-copy`). You can also redirect command output to a file via `--output`.

## Rule export path issues

- **Symptom:** `contextctl rules --save` fails with a permission error.
- **Fix:** Ensure the repository contains a writable `.cursor/rules/` directory or run the command with appropriate permissions. As a fallback, omit `--save` and redirect CLI output: `contextctl rules > rules.mdc`.

## Unit tests or type checks fail locally

- **Symptom:** `pytest`, `ruff`, or `mypy` fails despite CI passing elsewhere.
- **Fix:** Run the full quality gate locally:

```bash
uv run ruff format .
uv run ruff check .
uv run mypy
uv run pytest --cov=src/contextctl --cov-report=term-missing
```

Compare your tool versions with `uv tree --depth 1` to confirm parity with CI.

