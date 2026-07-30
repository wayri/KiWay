"""Read-only project dependency scanner."""

from __future__ import annotations

from pathlib import Path

from kilo.errors import KiloError
from kilo.kicad.embedded_files import read_embedded_files
from kilo.kicad.footprint import (
    extract_board_footprint,
    footprint_from_text,
    read_footprint,
)
from kilo.kicad.lib_tables import (
    LibraryTable,
    flatten_library_entries,
)
from kilo.kicad.path_variables import collect_path_variables
from kilo.kicad.pcb import read_board
from kilo.kicad.project import (
    Project,
    detect_kicad_version,
    global_fp_lib_table,
)
from kilo.kicad.schematic import split_library_id, traverse_schematics
from kilo.util.hashing import sha256_text

from .footprint_resolver import match_board_footprint, resolve_library_footprint
from .model_resolver import resolve_model
from .models import FootprintDependency, ScanResult


def scan_project(project: Project) -> ScanResult:
    """Resolve every non-empty schematic Footprint field without mutating files."""

    schematics = traverse_schematics(project.root_schematic)
    board = read_board(project.board) if project.board and project.board.exists() else None
    variables = collect_path_variables(project)

    project_table = (
        LibraryTable.read(project.fp_lib_table)
        if project.fp_lib_table.exists()
        else LibraryTable.empty(project.fp_lib_table)
    )
    project_entries = flatten_library_entries([project_table], variables, project.root)
    global_path = global_fp_lib_table()
    global_entries = (
        flatten_library_entries([LibraryTable.read(global_path)], variables, project.root)
        if global_path
        else []
    )
    ordered_entries = project_entries + global_entries

    dependencies: list[FootprintDependency] = []
    warnings: list[str] = []
    conflicts: list[str] = []
    for schematic in schematics:
        for symbol in schematic.symbols:
            library_id = split_library_id(symbol.footprint)
            if library_id is None:
                dependency = FootprintDependency(
                    symbol,
                    "",
                    symbol.footprint,
                    "invalid-library-id",
                    None,
                    None,
                    None,
                    None,
                    None,
                )
                dependencies.append(dependency)
                warnings.append(
                    f"{symbol.reference or symbol.uuid}: invalid footprint identifier "
                    f"{symbol.footprint!r}"
                )
                continue
            nickname, name = library_id
            library_path = resolve_library_footprint(
                nickname, name, ordered_entries, variables, project.root
            )
            board_footprint = match_board_footprint(
                board,
                reference=symbol.reference,
                symbol_uuid=symbol.uuid,
                footprint_name=name,
            )
            library_text = (
                library_path.read_text(encoding="utf-8-sig") if library_path is not None else None
            )
            board_text = (
                extract_board_footprint(board_footprint, name) if board_footprint else None
            )
            library_hash = sha256_text(library_text) if library_text is not None else None
            board_hash = sha256_text(board_text) if board_text is not None else None
            conflict = None
            if library_text is not None and board_text is not None and library_hash != board_hash:
                assert library_path is not None and board_footprint is not None
                conflict = (
                    f"{name} differs between source library {library_path.parent} "
                    f"and board footprint {board_footprint.reference}; using board version"
                )
                conflicts.append(conflict)
            # The validated board copy is authoritative whenever it exists and differs.
            if board_text is not None and (library_text is None or conflict):
                source_kind = "board"
                source_path = project.board
                source_text = board_text
                source_hash = board_hash
                parsed_footprint = footprint_from_text(board_text)
                model_parent = project.root
            elif library_text is not None:
                assert library_path is not None
                source_kind = "project-library" if library_path and _under(
                    library_path, project.root
                ) else "library"
                source_path = library_path
                source_text = library_text
                source_hash = library_hash
                parsed_footprint = read_footprint(library_path)
                model_parent = library_path.parent
            else:
                dependency = FootprintDependency(
                    symbol,
                    nickname,
                    name,
                    "unresolved",
                    None,
                    None,
                    None,
                    None,
                    board_footprint,
                )
                dependencies.append(dependency)
                warnings.append(
                    f"{symbol.reference or symbol.uuid}: footprint {symbol.footprint!r} unresolved"
                )
                continue
            try:
                embedded_names = {item.name for item in read_embedded_files(source_text)}
            except KiloError as exc:
                embedded_names = set()
                warnings.append(f"{name}: {exc}")
            models = [
                resolve_model(
                    model.path,
                    variables,
                    project_root=project.root,
                    source_parent=model_parent,
                    embedded_names=embedded_names,
                )
                for model in parsed_footprint.models
            ]
            for model in models:
                if model.status == "missing":
                    warnings.append(
                        f"{symbol.reference or symbol.uuid}: 3D model "
                        f"{model.original_path!r} unresolved"
                    )
            dependencies.append(
                FootprintDependency(
                    symbol=symbol,
                    nickname=nickname,
                    name=name,
                    status="resolved",
                    source_kind=source_kind,
                    source_path=source_path,
                    source_text=source_text,
                    source_sha256=source_hash,
                    board_footprint=board_footprint,
                    library_sha256=library_hash,
                    board_sha256=board_hash,
                    conflict=conflict,
                    models=models,
                )
            )

    return ScanResult(
        project_name=project.name,
        project_root=project.root,
        kicad_version=detect_kicad_version(),
        schematics=list(schematics),
        board=board,
        dependencies=dependencies,
        warnings=warnings,
        conflicts=conflicts,
    )


def _under(path: Path, root: Path) -> bool:
    try:
        path.resolve().relative_to(root.resolve())
        return True
    except ValueError:
        return False
