#!/usr/bin/env bash

set -euo pipefail

if [[ $# -ne 1 ]]; then
  echo "Usage: $0 vX.Y.Z" >&2
  exit 1
fi

VERSION="$1"

echo "==> Ensuring working tree is clean"
if ! git diff --quiet || ! git diff --cached --quiet; then
  echo "Working tree is dirty. Commit or stash changes before releasing." >&2
  exit 1
fi

echo "==> Installing dependencies"
uv sync --frozen

echo "==> Running ruff (format + lint)"
uv run --frozen ruff format .
uv run --frozen ruff check .

echo "==> Running mypy"
uv run --frozen mypy

echo "==> Running pytest with coverage"
uv run --frozen pytest --cov=src/contextctl --cov-report=term-missing

if git tag --list "${VERSION}" | grep -q "${VERSION}"; then
  echo "Tag ${VERSION} already exists. Delete it first if you want to recreate." >&2
  exit 1
fi

echo "==> Creating git tag ${VERSION}"
git tag -s "${VERSION}" -m "contextctl ${VERSION}" || git tag -a "${VERSION}" -m "contextctl ${VERSION}"

echo "==> Release ready"
echo "Push the tag with: git push origin ${VERSION}"

