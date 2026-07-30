"""Board footprint inspection and minimal library-link editing."""

from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path

from kilo.errors import KiloError

from .sexpr import Document, Node, atom, parse


@dataclass
class BoardModel:
    path: str
    node: Node
    path_node: Node


@dataclass
class BoardFootprint:
    library_id: str
    reference: str
    uuid: str
    path: str
    node: Node
    library_id_node: Node
    models: list[BoardModel]

    @property
    def name(self) -> str:
        return self.library_id.split(":", 1)[-1]


@dataclass
class BoardFile:
    path: Path
    text: str
    document: Document
    footprints: list[BoardFootprint]
    track_count: int
    zone_count: int


def read_board(path: Path) -> BoardFile:
    """Read a board without using unstable SWIG object mutation."""

    text = path.read_text(encoding="utf-8-sig")
    document = parse(text)
    root = document.root
    if root.head != "kicad_pcb":
        raise KiloError(f"{path} is not a KiCad board")
    footprints: list[BoardFootprint] = []
    for node in root.lists("footprint"):
        atoms = node.atoms
        if len(atoms) < 2:
            continue
        properties = {
            atom(child, 1): atom(child, 2)
            for child in node.lists("property")
            if len(child.atoms) >= 3
        }
        models = [
            BoardModel(atom(model, 1), model, model.atoms[1])
            for model in node.lists("model")
            if len(model.atoms) >= 2
        ]
        footprints.append(
            BoardFootprint(
                library_id=atoms[1].value,
                reference=properties.get("Reference", ""),
                uuid=_child_atom(node, "uuid") or _child_atom(node, "tstamp"),
                path=_child_atom(node, "path"),
                node=node,
                library_id_node=atoms[1],
                models=models,
            )
        )
    return BoardFile(
        path,
        text,
        document,
        footprints,
        track_count=sum(1 for child in root.lists() if child.head in {"segment", "arc", "via"}),
        zone_count=len(root.lists("zone")),
    )


def replace_library_links(
    board: BoardFile, replacements: dict[str, str]
) -> tuple[str, list[tuple[BoardFootprint, str]]]:
    """Update only top-level board footprint library-link atoms."""

    changed: list[tuple[BoardFootprint, str]] = []
    for footprint in board.footprints:
        new_value = replacements.get(footprint.uuid)
        if new_value is not None and new_value != footprint.library_id:
            board.document.replace_atom(footprint.library_id_node, new_value, quoted=True)
            changed.append((footprint, new_value))
    return board.document.render(), changed


def board_invariants(board: BoardFile) -> dict[str, int]:
    """Count board structures that localization must never change."""

    return {
        "footprints": len(board.footprints),
        "pads": sum(len(footprint.node.lists("pad")) for footprint in board.footprints),
        "tracks": board.track_count,
        "zones": board.zone_count,
        "nets": len(board.document.root.lists("net")),
    }


def board_invariants_from_text(text: str) -> dict[str, int]:
    """Count immutable localization structures in rendered board text."""

    root = parse(text).root
    footprints = root.lists("footprint")
    return {
        "footprints": len(footprints),
        "pads": sum(len(footprint.lists("pad")) for footprint in footprints),
        "tracks": sum(
            1 for child in root.lists() if child.head in {"segment", "arc", "via"}
        ),
        "zones": len(root.lists("zone")),
        "nets": len(root.lists("net")),
    }


def _child_atom(node: Node, head: str) -> str:
    child = node.first_list(head)
    return atom(child, 1) if child else ""
