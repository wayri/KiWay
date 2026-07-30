"""Footprint model inspection and board-footprint recovery."""

from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path

from kilo.errors import KiloError

from .pcb import BoardFootprint
from .sexpr import Document, Node, atom, parse


@dataclass
class ModelReference:
    path: str
    node: Node
    path_node: Node
    transform_source: str


@dataclass
class FootprintFile:
    path: Path | None
    name: str
    text: str
    document: Document
    models: list[ModelReference]


def read_footprint(path: Path) -> FootprintFile:
    """Read a `.kicad_mod` and retain exact model transformation source."""

    text = path.read_text(encoding="utf-8-sig")
    return footprint_from_text(text, path)


def footprint_from_text(text: str, path: Path | None = None) -> FootprintFile:
    document = parse(text)
    if document.root.head != "footprint":
        raise KiloError(f"{path or '<memory>'} is not a KiCad footprint")
    name = atom(document.root, 1)
    models = [
        ModelReference(atom(node, 1), node, node.atoms[1], node.source)
        for node in document.root.lists("model")
        if len(node.atoms) >= 2
    ]
    return FootprintFile(path, name, text, document, models)


def replace_model_paths(
    footprint: FootprintFile, replacements: dict[str, str]
) -> tuple[str, list[tuple[str, str]]]:
    """Replace model path atoms only, leaving transforms byte-for-byte unchanged."""

    changed: list[tuple[str, str]] = []
    for model in footprint.models:
        new_path = replacements.get(model.path)
        if new_path is not None and new_path != model.path:
            footprint.document.replace_atom(model.path_node, new_path, quoted=True)
            changed.append((model.path, new_path))
    return footprint.document.render(), changed


def extract_board_footprint(footprint: BoardFootprint, target_name: str) -> str:
    """Convert an embedded board footprint to a valid standalone library footprint.

    Board-only placement, schematic-link, and pad-net nodes are removed. Geometry,
    pads, UUIDs, fields, properties, and model transforms otherwise remain intact.
    """

    document = parse(footprint.node.source)
    root = document.root
    document.replace_atom(root.atoms[1], target_name, quoted=True)
    for child in root.lists():
        if child.head in {"at", "path", "sheetfile", "sheetname"}:
            document.remove_node(child)
        elif child.head in {"uuid", "tstamp"} and child.parent is root:
            document.remove_node(child)
        elif child.head == "property" and atom(child, 1) == "Reference" and len(child.atoms) >= 3:
            document.replace_atom(child.atoms[2], "REF**", quoted=True)
        elif child.head == "property" and atom(child, 1) == "Value" and len(child.atoms) >= 3:
            document.replace_atom(child.atoms[2], target_name, quoted=True)
    for pad in root.lists("pad"):
        for child in pad.lists():
            if child.head in {"net", "pinfunction", "pintype"}:
                document.remove_node(child)
    rendered = document.render()
    # KiCad library files need a version/generator header; board instances omit it.
    reparsed = parse(rendered)
    root = reparsed.root
    if root.first_list("version") is None:
        name_atom = root.atoms[1]
        insertion = name_atom.end
        reparsed.insert(
            insertion,
            '\n  (version 20240108)\n  (generator "kilo")'
            '\n  (generator_version "0.1")',
        )
        rendered = reparsed.render()
    return rendered.rstrip() + "\n"


def pad_numbers(footprint: FootprintFile) -> list[str]:
    """Return pad identifiers in source order."""

    return [atom(node, 1) for node in footprint.document.root.lists("pad")]
