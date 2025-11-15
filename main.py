"""Console entrypoint for the contextctl CLI."""

from __future__ import annotations

from contextctl.cli import app


def main() -> None:
    """Invoke the Typer application."""
    app(prog_name="contextctl")


if __name__ == "__main__":
    main()
