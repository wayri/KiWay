"""Token-preserving KiCad footprint-library table handling."""

from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
from typing import Iterable, Mapping

from kilo.errors import ConflictError, ParseError
from kilo.util.paths import resolve_existing_path

from .sexpr import Document, Node, atom, parse


@dataclass(frozen=True)
class LibraryEntry:
    name: str
    type: str
    uri: str
    options: str = ""
    description: str = ""
    source_table: Path | None = None
    disabled: bool = False


@dataclass
class LibraryTable:
    path: Path
    text: str
    document: Document
    entries: list[LibraryEntry]

    @classmethod
    def read(
        cls, path: Path, *, expected_root: str | None = "fp_lib_table"
    ) -> "LibraryTable":
        text = path.read_text(encoding="utf-8-sig")
        document = parse(text)
        if expected_root is not None and document.root.head != expected_root:
            raise ParseError(f"{path} is not a {expected_root}")
        entries = [_entry_from_node(node, path) for node in document.root.lists("lib")]
        return cls(path, text, document, entries)

    @classmethod
    def empty(cls, path: Path, *, root_head: str = "fp_lib_table") -> "LibraryTable":
        text = f"({root_head}\n)\n"
        return cls(path, text, parse(text), [])

    def find(self, name: str) -> LibraryEntry | None:
        return next((entry for entry in self.entries if entry.name == name), None)

    def merged_text(self, entry: LibraryEntry) -> tuple[str, bool]:
        """Return text with *entry* added, preserving all existing table text."""

        existing = self.find(entry.name)
        if existing:
            if _normalize_uri(existing.uri) != _normalize_uri(entry.uri):
                raise ConflictError(
                    f"library nickname {entry.name!r} already maps to {existing.uri!r}, "
                    f"not {entry.uri!r}"
                )
            return self.text, False
        root = self.document.root
        assert root.close_token_index is not None
        offset = self.document.tokens[root.close_token_index].start
        indent = "\t" if "\t(lib " in self.text else "  "
        newline = "\r\n" if "\r\n" in self.text else "\n"
        rendered = (
            f'{indent}(lib (name "{_escape(entry.name)}") (type "{_escape(entry.type)}") '
            f'(uri "{_escape(entry.uri)}") (options "{_escape(entry.options)}") '
            f'(descr "{_escape(entry.description)}")){newline}'
        )
        self.document.insert(offset, rendered)
        return self.document.render(), True

    def without_entry_text(self, name: str, *, expected_uri: str | None = None) -> tuple[str, bool]:
        """Remove one exact library entry while preserving all other table content."""

        for node in self.document.root.lists("lib"):
            fields = {child.head: atom(child, 1) for child in node.lists() if child.head}
            if fields.get("name") != name:
                continue
            if expected_uri is not None and _normalize_uri(fields.get("uri", "")) != _normalize_uri(
                expected_uri
            ):
                raise ConflictError(
                    f"refusing to remove {name!r}: its path changed to {fields.get('uri')!r}"
                )
            self.document.remove_node(node)
            return self.document.render(), True
        return self.text, False


def read_tables(paths: Iterable[Path]) -> list[LibraryTable]:
    """Read existing tables only."""

    return [LibraryTable.read(path) for path in paths if path.exists()]


def flatten_library_entries(
    tables: Iterable[LibraryTable],
    variables: Mapping[str, str],
    project_root: Path,
) -> list[LibraryEntry]:
    """Expand `Table` entries recursively while retaining override order."""

    output: list[LibraryEntry] = []
    visited: set[Path] = set()

    def visit(table: LibraryTable) -> None:
        resolved_table = table.path.resolve()
        if resolved_table in visited:
            return
        visited.add(resolved_table)
        for entry in table.entries:
            if entry.type.casefold() == "table":
                nested = resolve_existing_path(
                    entry.uri,
                    variables,
                    project_root=project_root,
                    source_parent=table.path.parent,
                )
                if nested and nested.is_file():
                    visit(LibraryTable.read(nested))
            else:
                output.append(entry)

    for item in tables:
        visit(item)
    return output


def _entry_from_node(node: Node, path: Path) -> LibraryEntry:
    fields = {child.head: atom(child, 1) for child in node.lists() if child.head}
    return LibraryEntry(
        name=fields.get("name", ""),
        type=fields.get("type", "KiCad"),
        uri=fields.get("uri", ""),
        options=fields.get("options", ""),
        description=fields.get("descr", ""),
        source_table=path,
        disabled=fields.get("disabled", "").casefold() in {"yes", "true", "1"},
    )


def _normalize_uri(uri: str) -> str:
    return uri.replace("\\", "/").rstrip("/").casefold()


def _escape(value: str) -> str:
    return value.replace("\\", "\\\\").replace('"', '\\"')
