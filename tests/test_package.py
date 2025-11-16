"""Tests for package-level helpers in contextctl."""

from __future__ import annotations

import importlib
from importlib.metadata import PackageNotFoundError
from unittest import mock

import contextctl


def test_load_local_version_reads_pyproject() -> None:
    """_load_local_version should return the version defined in pyproject.toml."""
    assert contextctl._load_local_version() == "0.1.0"


def test_version_falls_back_when_distribution_missing() -> None:
    """When the package metadata is missing, __version__ should use pyproject."""
    with mock.patch("importlib.metadata.version", side_effect=PackageNotFoundError):
        reloaded = importlib.reload(contextctl)
        assert reloaded.__version__ == reloaded._load_local_version()
    importlib.reload(contextctl)
