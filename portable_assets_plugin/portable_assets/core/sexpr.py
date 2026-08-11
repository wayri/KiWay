"""Small loss-minimising KiCad S-expression scanner.

This deliberately does not pretty-print whole KiCad files.  It records source spans so
callers can replace only the atoms/forms they intend to change and leave everything
else byte-for-byte alone.
"""
from __future__ import annotations

from dataclasses import dataclass, field
from typing import Iterator, Optional


@dataclass(slots=True)
class Atom:
    value: str
    start: int
    end: int
    quoted: bool = False


@dataclass(slots=True)
class Node:
    start: int
    end: int = -1
    atoms: list[Atom] = field(default_factory=list)   # direct atoms only
    children: list["Node"] = field(default_factory=list)
    parent: Optional["Node"] = None

    @property
    def head(self) -> str:
        return self.atoms[0].value if self.atoms else ""

    def child(self, head: str) -> Optional["Node"]:
        return next((c for c in self.children if c.head == head), None)

    def children_named(self, head: str) -> list["Node"]:
        return [c for c in self.children if c.head == head]

    def atom(self, index: int) -> Optional[Atom]:
        return self.atoms[index] if len(self.atoms) > index else None

    def ancestors(self) -> Iterator["Node"]:
        p = self.parent
        while p is not None:
            yield p
            p = p.parent

    def walk(self) -> Iterator["Node"]:
        yield self
        for c in self.children:
            yield from c.walk()


class ParseError(ValueError):
    pass


def _unescape_string(raw: str) -> str:
    # KiCad strings use C-like escapes for backslash and quote. Keep support narrow
    # on purpose: unknown escapes are preserved as the escaped character.
    out: list[str] = []
    i = 0
    while i < len(raw):
        if raw[i] == "\\" and i + 1 < len(raw):
            nxt = raw[i + 1]
            mapping = {"n": "\n", "r": "\r", "t": "\t", '"': '"', "\\": "\\"}
            out.append(mapping.get(nxt, nxt))
            i += 2
        else:
            out.append(raw[i])
            i += 1
    return "".join(out)


def quote(value: str) -> str:
    return '"' + value.replace("\\", "\\\\").replace('"', '\\"').replace("\n", "\\n").replace("\r", "\\r").replace("\t", "\\t") + '"'


def parse(text: str) -> Node:
    """Parse text and return a synthetic document node whose children are roots."""
    doc = Node(0, len(text))
    stack: list[Node] = [doc]
    i = 0
    n = len(text)

    while i < n:
        ch = text[i]
        if ch.isspace():
            i += 1
            continue
        if ch == ";":  # tolerated comment syntax
            j = text.find("\n", i + 1)
            i = n if j < 0 else j + 1
            continue
        if ch == "(":
            node = Node(i, parent=stack[-1])
            stack[-1].children.append(node)
            stack.append(node)
            i += 1
            continue
        if ch == ")":
            if len(stack) == 1:
                raise ParseError(f"Unexpected ')' at offset {i}")
            stack[-1].end = i + 1
            stack.pop()
            i += 1
            continue
        if len(stack) == 1:
            # Bare text outside a root is not useful, but tolerate it so trailing BOMs/
            # comments do not make an otherwise valid file unreadable.
            i += 1
            continue
        if ch == '"':
            start = i
            i += 1
            raw_start = i
            escaped = False
            while i < n:
                c = text[i]
                if escaped:
                    escaped = False
                    i += 1
                    continue
                if c == "\\":
                    escaped = True
                    i += 1
                    continue
                if c == '"':
                    raw = text[raw_start:i]
                    i += 1
                    stack[-1].atoms.append(Atom(_unescape_string(raw), start, i, True))
                    break
                i += 1
            else:
                raise ParseError(f"Unterminated string at offset {start}")
            continue
        if ch == "|":
            # Embedded file data is bar-delimited and may be huge. Treat the whole block
            # as one opaque atom so parentheses within data could never affect nesting.
            start = i
            j = text.find("|", i + 1)
            if j < 0:
                raise ParseError(f"Unterminated bar-delimited token at offset {start}")
            stack[-1].atoms.append(Atom(text[i + 1:j], start, j + 1, False))
            i = j + 1
            continue

        start = i
        while i < n and (not text[i].isspace()) and text[i] not in "()\"|;":
            i += 1
        if i == start:
            # A punctuation character not otherwise handled; consume it as an atom.
            i += 1
        stack[-1].atoms.append(Atom(text[start:i], start, i, False))

    if len(stack) != 1:
        raise ParseError(f"Unclosed form beginning at offset {stack[-1].start}")
    return doc


def apply_replacements(text: str, replacements: list[tuple[int, int, str]]) -> str:
    """Apply non-overlapping source-span replacements from right to left."""
    if not replacements:
        return text
    reps = sorted(replacements, key=lambda x: (x[0], x[1]))
    for a, b in zip(reps, reps[1:]):
        if a[1] > b[0]:
            raise ValueError(f"Overlapping replacements: {a[:2]} and {b[:2]}")
    out = text
    for start, end, new in reversed(reps):
        out = out[:start] + new + out[end:]
    return out


def root_named(doc: Node, head: str) -> Optional[Node]:
    return next((n for n in doc.children if n.head == head), None)


def direct_property(node: Node, name: str) -> Optional[Node]:
    for c in node.children:
        if c.head == "property" and len(c.atoms) >= 3 and c.atoms[1].value == name:
            return c
    return None


def atom_replacement(atom: Atom, value: str) -> tuple[int, int, str]:
    return (atom.start, atom.end, quote(value) if atom.quoted else value)
