"""Footprint library and board-copy resolution."""

from __future__ import annotations

from pathlib import Path
from typing import Mapping, Sequence

from kilo.kicad.lib_tables import LibraryEntry
from kilo.kicad.pcb import BoardFile, BoardFootprint
from kilo.util.paths import resolve_existing_path


def resolve_library_footprint(
    nickname: str,
    name: str,
    entries: Sequence[LibraryEntry],
    variables: Mapping[str, str],
    project_root: Path,
) -> Path | None:
    """Resolve one footprint using ordered project/global table entries."""

    for entry in entries:
        if entry.disabled or entry.name != nickname:
            continue
        library = resolve_existing_path(
            entry.uri,
            variables,
            project_root=project_root,
            source_parent=entry.source_table.parent if entry.source_table else project_root,
        )
        if library is None or not library.is_dir():
            continue
        exact = library / f"{name}.kicad_mod"
        if exact.exists():
            return exact.resolve()
        folded = f"{name}.kicad_mod".casefold()
        candidate = next(
            (path for path in library.glob("*.kicad_mod") if path.name.casefold() == folded),
            None,
        )
        if candidate:
            return candidate.resolve()
    return None


def match_board_footprint(
    board: BoardFile | None,
    *,
    reference: str,
    symbol_uuid: str,
    footprint_name: str,
) -> BoardFootprint | None:
    """Match board geometry by exact reference/name, UUID path, then unique name."""

    if board is None:
        return None
    if reference:
        matches = [
            footprint
            for footprint in board.footprints
            if footprint.reference == reference and footprint.name == footprint_name
        ]
        if len(matches) == 1:
            return matches[0]
        matches = [
            footprint for footprint in board.footprints if footprint.reference == reference
        ]
        if len(matches) == 1:
            return matches[0]
    if symbol_uuid:
        matches = [
            footprint
            for footprint in board.footprints
            if symbol_uuid in footprint.path or symbol_uuid == footprint.uuid
        ]
        if len(matches) == 1:
            return matches[0]
    matches = [footprint for footprint in board.footprints if footprint.name == footprint_name]
    return matches[0] if len(matches) == 1 else None
