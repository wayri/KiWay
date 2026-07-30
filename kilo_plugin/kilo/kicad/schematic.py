"""Schematic traversal and exact Footprint-field patching."""

from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path

from kilo.errors import KiloError

from .sexpr import Document, Node, atom, parse


@dataclass
class SchematicSymbol:
    file: Path
    sheet_path: str
    uuid: str
    reference: str
    footprint: str
    symbol_node: Node
    footprint_value_node: Node


@dataclass
class SchematicFile:
    path: Path
    sheet_path: str
    text: str
    document: Document
    symbols: list[SchematicSymbol]
    child_sheets: list[tuple[str, str]]


def read_schematic(path: Path, sheet_path: str = "/") -> SchematicFile:
    """Read one schematic and collect instance symbols and child-sheet filenames."""

    text = path.read_text(encoding="utf-8-sig")
    document = parse(text)
    if document.root.head != "kicad_sch":
        raise KiloError(f"{path} is not a KiCad schematic")
    symbols: list[SchematicSymbol] = []
    for node in document.root.lists("symbol"):
        properties = _properties(node)
        footprint_node = properties.get("Footprint")
        if footprint_node is None or len(footprint_node.atoms) < 3:
            continue
        value_node = footprint_node.atoms[2]
        if not value_node.value:
            continue
        symbols.append(
            SchematicSymbol(
                file=path,
                sheet_path=sheet_path,
                uuid=_child_atom(node, "uuid"),
                reference=_property_value(properties.get("Reference")),
                footprint=value_node.value,
                symbol_node=node,
                footprint_value_node=value_node,
            )
        )
    children: list[tuple[str, str]] = []
    for sheet in document.root.lists("sheet"):
        properties = _properties(sheet)
        filename = _property_value(properties.get("Sheetfile")) or _property_value(
            properties.get("Sheet file")
        )
        if filename:
            child_uuid = _child_atom(sheet, "uuid") or filename
            children.append((child_uuid, filename))
    return SchematicFile(path, sheet_path, text, document, symbols, children)


def traverse_schematics(root: Path) -> list[SchematicFile]:
    """Recursively traverse hierarchical sheets, detecting cycles and escapes."""

    project_root = root.parent.resolve()
    output: list[SchematicFile] = []
    visited: set[Path] = set()

    def visit(path: Path, sheet_path: str) -> None:
        resolved = path.resolve()
        if resolved in visited:
            return
        if not resolved.is_relative_to(project_root):
            raise KiloError(f"hierarchical sheet escapes project: {resolved}")
        if not resolved.exists():
            raise KiloError(f"hierarchical schematic is missing: {resolved}")
        visited.add(resolved)
        schematic = read_schematic(resolved, sheet_path)
        output.append(schematic)
        for child_uuid, child_name in schematic.child_sheets:
            child_path = (resolved.parent / child_name).resolve()
            child_sheet_path = sheet_path.rstrip("/") + "/" + child_uuid
            visit(child_path, child_sheet_path)

    visit(root, "/")
    return output


def replace_footprints(
    schematic: SchematicFile, replacements: dict[tuple[str, str], str]
) -> tuple[str, list[tuple[SchematicSymbol, str]]]:
    """Patch selected symbols, keyed by `(sheet_path, UUID)`."""

    changed: list[tuple[SchematicSymbol, str]] = []
    for symbol in schematic.symbols:
        new_value = replacements.get((symbol.sheet_path, symbol.uuid))
        if new_value is not None and new_value != symbol.footprint:
            schematic.document.replace_atom(symbol.footprint_value_node, new_value, quoted=True)
            changed.append((symbol, new_value))
    return schematic.document.render(), changed


def split_library_id(value: str) -> tuple[str, str] | None:
    """Split at the first nickname separator, preserving the complete source elsewhere."""

    if ":" not in value:
        return None
    nickname, name = value.split(":", 1)
    return (nickname, name) if nickname and name else None


def _properties(node: Node) -> dict[str, Node]:
    return {
        atom(child, 1): child
        for child in node.lists("property")
        if len(child.atoms) >= 3
    }


def _property_value(node: Node | None) -> str:
    return atom(node, 2) if node is not None else ""


def _child_atom(node: Node, head: str) -> str:
    child = node.first_list(head)
    return atom(child, 1) if child else ""
