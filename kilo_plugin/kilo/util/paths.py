"""Portable path helpers."""

from __future__ import annotations

import os
import re
from pathlib import Path
from typing import Mapping

_VARIABLE = re.compile(r"\$\{([^}]+)\}")
_WINDOWS_ABSOLUTE = re.compile(r"^[A-Za-z]:[\\/]")


def is_absolute_any_platform(value: str) -> bool:
    """Recognize POSIX, UNC, and drive-letter absolute paths on every host."""

    return value.startswith(("/", "\\\\")) or bool(_WINDOWS_ABSOLUTE.match(value))


def expand_kicad_path(value: str, variables: Mapping[str, str]) -> str:
    """Expand ``${NAME}`` references without consulting hidden global state."""

    expanded = value
    for _ in range(10):
        updated = _VARIABLE.sub(
            lambda match: variables.get(match.group(1), match.group(0)), expanded
        )
        if updated == expanded:
            break
        expanded = updated
    return expanded


def resolve_existing_path(
    value: str,
    variables: Mapping[str, str],
    *,
    project_root: Path,
    source_parent: Path | None = None,
) -> Path | None:
    """Resolve a KiCad path, trying the project and source directory for relatives."""

    if value.startswith("kicad-embed://"):
        return None
    expanded = expand_kicad_path(value, variables)
    if "${" in expanded:
        return None
    expanded = os.path.expanduser(expanded)
    if is_absolute_any_platform(expanded):
        candidate = Path(expanded)
        return candidate.resolve() if candidate.exists() else None
    candidates = [project_root / expanded]
    if source_parent is not None:
        candidates.append(source_parent / expanded)
    for candidate in candidates:
        if candidate.exists():
            return candidate.resolve()
    return None


def kiprjmod_path(relative: Path | str) -> str:
    """Return a forward-slash KiCad project-variable path."""

    return "${KIPRJMOD}/" + Path(relative).as_posix().lstrip("/")
