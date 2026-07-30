"""Standalone entry point."""

from __future__ import annotations

import sys

from .cli import main

if __name__ == "__main__":
    if sys.argv[1:]:
        raise SystemExit(main(sys.argv[1:]))
    from .ui.main_frame import launch

    launch()
