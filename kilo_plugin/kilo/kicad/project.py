"""KiCad project discovery and installed-version detection."""

from __future__ import annotations

import json
import os
import platform
import subprocess
from dataclasses import dataclass
from pathlib import Path
from typing import Any

from kilo.errors import KiloError


@dataclass(frozen=True)
class Project:
    """Discovered KiCad project files."""

    root: Path
    name: str
    project_file: Path | None
    root_schematic: Path
    board: Path | None
    fp_lib_table: Path


def discover_project(path: Path) -> Project:
    """Discover one KiCad project from a directory or project member path."""

    supplied = path.expanduser().resolve()
    root = supplied.parent if supplied.is_file() else supplied
    if not root.is_dir():
        raise KiloError(f"project directory does not exist: {root}")

    project_files = sorted(root.glob("*.kicad_pro"))
    preferred_stem = supplied.stem if supplied.is_file() else None
    project_file = _choose_by_stem(project_files, preferred_stem)
    name = project_file.stem if project_file else (preferred_stem or root.name)

    schematics = sorted(root.glob("*.kicad_sch"))
    root_schematic = _choose_by_stem(schematics, name)
    if root_schematic is None:
        if len(schematics) == 1:
            root_schematic = schematics[0]
        else:
            raise KiloError(
                f"cannot identify root schematic in {root}; expected {name}.kicad_sch"
            )

    boards = sorted(root.glob("*.kicad_pcb"))
    board = _choose_by_stem(boards, name)
    if board is None and len(boards) == 1:
        board = boards[0]
    return Project(
        root=root,
        name=name,
        project_file=project_file,
        root_schematic=root_schematic,
        board=board,
        fp_lib_table=root / "fp-lib-table",
    )


def _choose_by_stem(paths: list[Path], stem: str | None) -> Path | None:
    if stem:
        return next((path for path in paths if path.stem.casefold() == stem.casefold()), None)
    return paths[0] if len(paths) == 1 else None


def read_project_json(project: Project) -> dict[str, Any]:
    """Read a `.kicad_pro` file, returning an empty object when absent."""

    if project.project_file is None:
        return {}
    try:
        data = json.loads(project.project_file.read_text(encoding="utf-8-sig"))
    except (OSError, json.JSONDecodeError) as exc:
        raise KiloError(f"cannot read project file {project.project_file}: {exc}") from exc
    return data if isinstance(data, dict) else {}


def detect_kicad_version() -> str | None:
    """Detect KiCad, preferring its CLI and falling back to pcbnew."""

    candidates: list[Path | str] = ["kicad-cli"]
    if platform.system() == "Windows":
        program_files = Path(os.environ.get("ProgramFiles", r"C:\Program Files"))
        candidates.extend(
            path
            for version in ("10.0", "10.99", "9.0")
            if (path := program_files / "KiCad" / version / "bin" / "kicad-cli.exe").exists()
        )
    for candidate in candidates:
        try:
            result = subprocess.run(
                [str(candidate), "version"],
                check=True,
                capture_output=True,
                text=True,
                timeout=8,
            )
        except (OSError, subprocess.SubprocessError):
            continue
        version = result.stdout.strip()
        if version:
            return version
    try:
        import pcbnew  # type: ignore[import-not-found]

        return str(pcbnew.GetBuildVersion())
    except (ImportError, AttributeError):
        return None


def global_fp_lib_table(version_major: int = 10) -> Path | None:
    """Return the current user's KiCad global footprint table if present."""

    if platform.system() == "Windows":
        appdata = os.environ.get("APPDATA")
        candidate = (
            Path(appdata) / "kicad" / f"{version_major}.0" / "fp-lib-table"
            if appdata
            else None
        )
    elif platform.system() == "Darwin":
        candidate = (
            Path.home()
            / "Library"
            / "Preferences"
            / "kicad"
            / f"{version_major}.0"
            / "fp-lib-table"
        )
    else:
        candidate = Path.home() / ".config" / "kicad" / f"{version_major}.0" / "fp-lib-table"
    return candidate if candidate and candidate.exists() else None
