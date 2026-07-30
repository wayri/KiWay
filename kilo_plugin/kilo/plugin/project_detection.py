"""Current-project detection for standalone and pcbnew-hosted launches."""

from __future__ import annotations

from pathlib import Path


def current_project_path() -> Path | None:
    """Return the active pcbnew board directory when the stable API is available."""

    try:
        import pcbnew  # type: ignore[import-not-found]

        board = pcbnew.GetBoard()
        filename = board.GetFileName() if board else ""
        return Path(filename).resolve().parent if filename else None
    except (ImportError, AttributeError, RuntimeError):
        return None
