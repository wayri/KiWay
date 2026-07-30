"""KiCad design-block directory discovery."""

from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path

from kilo.errors import KiloError


@dataclass(frozen=True)
class DesignBlock:
    root: Path
    name: str
    schematic: Path
    board: Path | None
    metadata: Path | None


def discover_design_block(path: Path) -> DesignBlock:
    """Inspect a `.kicad_block` directory without assuming internal capitalization."""

    root = path.expanduser().resolve()
    if not root.is_dir():
        raise KiloError(f"design block directory does not exist: {root}")
    schematics = sorted(root.glob("*.kicad_sch"))
    if not schematics:
        raise KiloError(f"design block has no .kicad_sch: {root}")
    preferred = root.name.removesuffix(".kicad_block")
    schematic = next(
        (item for item in schematics if item.stem.casefold() == preferred.casefold()),
        schematics[0] if len(schematics) == 1 else None,
    )
    if schematic is None:
        raise KiloError(f"design block has ambiguous root schematics: {root}")
    boards = sorted(root.glob("*.kicad_pcb"))
    board = next(
        (item for item in boards if item.stem.casefold() == schematic.stem.casefold()),
        boards[0] if len(boards) == 1 else None,
    )
    metadata_files = sorted(root.glob("*.json"))
    metadata = next(
        (item for item in metadata_files if item.stem.casefold() == schematic.stem.casefold()),
        metadata_files[0] if len(metadata_files) == 1 else None,
    )
    return DesignBlock(root, schematic.stem, schematic, board, metadata)
