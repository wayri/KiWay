"""Deterministic KiCad-safe naming."""

from __future__ import annotations

import re

_UNSAFE = re.compile(r"[^A-Za-z0-9_.+-]+")


def sanitize_name(value: str, fallback: str = "Kilo") -> str:
    """Create a deterministic filename and library-nickname component."""

    cleaned = _UNSAFE.sub("_", value.strip()).strip("._")
    return cleaned or fallback


def collision_name(name: str, digest: str) -> str:
    """Append a stable short hash while retaining the original stem."""

    return f"{sanitize_name(name)}__{digest[:8]}"
