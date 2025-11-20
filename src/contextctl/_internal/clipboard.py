"""Clipboard integration utilities."""

from __future__ import annotations

import shutil
import subprocess
import sys


def copy_to_clipboard(content: str) -> None:
    """Copy the provided text to the system clipboard.

    Args:
        content: Text to copy to clipboard.

    Raises:
        RuntimeError: If clipboard integration is unavailable or fails.
    """
    try:
        import pyperclip  # type: ignore[import-untyped]
    except ImportError:  # pragma: no cover - optional dependency
        pyperclip = None

    if pyperclip is not None:  # pragma: no branch - simplified for readability
        try:
            pyperclip.copy(content)  # type: ignore[call-arg, unused-ignore]
            return
        except Exception as exc:  # pragma: no cover - pyperclip-specific
            raise RuntimeError(str(exc)) from exc

    platform = sys.platform
    if platform == "darwin":
        _run_clipboard_command(["pbcopy"], content)
        return
    if platform.startswith("win"):
        _run_clipboard_command(["clip"], content)
        return

    for command in (["xclip", "-selection", "clipboard"], ["wl-copy"]):
        if shutil.which(command[0]) is None:
            continue
        _run_clipboard_command(command, content)
        return

    msg = "Clipboard integration is not available on this platform."
    raise RuntimeError(msg)


def _run_clipboard_command(command: list[str], content: str) -> None:
    """Execute a clipboard command with the provided string content.

    Args:
        command: Command and arguments to execute.
        content: Text to pass to the command via stdin.

    Raises:
        RuntimeError: If the command fails.
    """
    try:
        subprocess.run(command, input=content.encode("utf-8"), check=True)
    except (OSError, subprocess.CalledProcessError) as exc:  # pragma: no cover - platform dependent
        msg = f"Clipboard command {' '.join(command)} failed: {exc}"
        raise RuntimeError(msg) from exc
