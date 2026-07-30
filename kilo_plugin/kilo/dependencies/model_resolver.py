"""3D-model dependency resolution."""

from __future__ import annotations

from pathlib import Path
from typing import Mapping

from kilo.util.hashing import sha256_file
from kilo.util.paths import resolve_existing_path

from .models import ModelDependency


def resolve_model(
    path_value: str,
    variables: Mapping[str, str],
    *,
    project_root: Path,
    source_parent: Path,
    embedded_names: set[str] | None = None,
) -> ModelDependency:
    """Resolve external model paths; embedded references remain explicitly embedded."""

    if path_value.startswith("kicad-embed://"):
        name = path_value.removeprefix("kicad-embed://")
        status = "embedded" if name in (embedded_names or set()) else "missing"
        return ModelDependency(path_value, None, status, source_parent)
    resolved = resolve_existing_path(
        path_value,
        variables,
        project_root=project_root,
        source_parent=source_parent,
    )
    return ModelDependency(
        original_path=path_value,
        resolved_path=resolved,
        status="resolved" if resolved else "missing",
        source_parent=source_parent,
        source_sha256=sha256_file(resolved) if resolved and resolved.is_file() else None,
    )
