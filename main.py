"""Temporary CLI entrypoint used during early development."""

from __future__ import annotations

from contextctl import PromptLibConfig


def main() -> None:
    """Print the configured store root for smoke testing."""
    config = PromptLibConfig()
    print(f"contextctl store: {config.store_root}")


if __name__ == "__main__":
    main()
