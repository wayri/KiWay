"""Token-preserving KiCad S-expression parsing and patching.

The parser keeps every byte of trivia (spacing and comments) in the token
stream. Callers replace only selected atom tokens or explicitly insert/remove
node spans, so unrelated and unknown KiCad nodes round-trip unchanged.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from enum import Enum
from typing import Iterator

from kilo.errors import ParseError


class TokenKind(str, Enum):
    LPAREN = "lparen"
    RPAREN = "rparen"
    ATOM = "atom"
    STRING = "string"
    BLOB = "blob"
    WHITESPACE = "whitespace"
    COMMENT = "comment"


@dataclass(frozen=True)
class Token:
    kind: TokenKind
    raw: str
    value: str
    start: int
    end: int


@dataclass
class Node:
    """Parsed significant S-expression node."""

    document: "Document"
    token_index: int | None = None
    children: list["Node"] = field(default_factory=list)
    parent: "Node | None" = None
    close_token_index: int | None = None

    @property
    def is_list(self) -> bool:
        return self.token_index is None

    @property
    def value(self) -> str:
        if self.token_index is None:
            raise TypeError("list nodes do not have atom values")
        return self.document.tokens[self.token_index].value

    @property
    def head(self) -> str | None:
        if not self.is_list or not self.children or self.children[0].is_list:
            return None
        return self.children[0].value

    @property
    def atoms(self) -> list["Node"]:
        return [child for child in self.children if not child.is_list]

    def lists(self, head: str | None = None) -> list["Node"]:
        result = [child for child in self.children if child.is_list]
        return result if head is None else [child for child in result if child.head == head]

    def first_list(self, head: str) -> "Node | None":
        return next(iter(self.lists(head)), None)

    def walk(self, head: str | None = None) -> Iterator["Node"]:
        if self.is_list and (head is None or self.head == head):
            yield self
        for child in self.children:
            if child.is_list:
                yield from child.walk(head)

    @property
    def start(self) -> int:
        if self.is_list:
            if not self.children and self.close_token_index is None:
                raise ParseError("unclosed list")
            opening = self.document.list_open_tokens[id(self)]
            return self.document.tokens[opening].start
        assert self.token_index is not None
        return self.document.tokens[self.token_index].start

    @property
    def end(self) -> int:
        if self.is_list:
            if self.close_token_index is None:
                raise ParseError("unclosed list")
            return self.document.tokens[self.close_token_index].end
        assert self.token_index is not None
        return self.document.tokens[self.token_index].end

    @property
    def source(self) -> str:
        return self.document.source[self.start : self.end]


@dataclass
class Document:
    source: str
    tokens: list[Token]
    roots: list[Node]
    list_open_tokens: dict[int, int]
    replacements: dict[int, str] = field(default_factory=dict)
    removals: list[tuple[int, int]] = field(default_factory=list)
    insertions: list[tuple[int, str]] = field(default_factory=list)

    @property
    def root(self) -> Node:
        if len(self.roots) != 1:
            raise ParseError(f"expected one root expression, found {len(self.roots)}")
        return self.roots[0]

    def replace_atom(self, node: Node, value: str, *, quoted: bool | None = None) -> None:
        """Replace exactly one atom while preserving all surrounding text."""

        if node.is_list or node.token_index is None:
            raise TypeError("replace_atom requires an atom node")
        token = self.tokens[node.token_index]
        use_quotes = token.kind is TokenKind.STRING if quoted is None else quoted
        self.replacements[node.token_index] = quote(value) if use_quotes else value

    def remove_node(self, node: Node) -> None:
        """Remove exactly a parsed node span."""

        self.removals.append((node.start, node.end))

    def insert(self, offset: int, text: str) -> None:
        """Insert text at a source character offset."""

        self.insertions.append((offset, text))

    def render(self) -> str:
        """Render source plus patches; untouched source is byte-for-byte stable."""

        edits: list[tuple[int, int, str]] = [
            (start, end, "") for start, end in self.removals
        ]
        for token_index, raw in self.replacements.items():
            token = self.tokens[token_index]
            edits.append((token.start, token.end, raw))
        edits.extend((offset, offset, text) for offset, text in self.insertions)
        edits.sort(key=lambda edit: (edit[0], edit[1]), reverse=True)
        output = self.source
        previous_start = len(output) + 1
        for start, end, text in edits:
            if end > previous_start:
                raise ParseError("overlapping S-expression edits")
            output = output[:start] + text + output[end:]
            previous_start = start
        return output


def quote(value: str) -> str:
    """Encode a KiCad quoted string without normalizing its contents."""

    escaped = value.replace("\\", "\\\\").replace('"', '\\"').replace("\n", "\\n")
    return f'"{escaped}"'


def _decode_string(raw: str) -> str:
    chars: list[str] = []
    index = 1
    while index < len(raw) - 1:
        char = raw[index]
        if char == "\\" and index + 1 < len(raw) - 1:
            index += 1
            escaped = raw[index]
            chars.append({"n": "\n", "r": "\r", "t": "\t"}.get(escaped, escaped))
        else:
            chars.append(char)
        index += 1
    return "".join(chars)


def tokenize(source: str) -> list[Token]:
    """Tokenize KiCad S-expressions, retaining comments and whitespace."""

    tokens: list[Token] = []
    index = 0
    length = len(source)
    while index < length:
        start = index
        char = source[index]
        if char.isspace():
            index += 1
            while index < length and source[index].isspace():
                index += 1
            raw = source[start:index]
            tokens.append(Token(TokenKind.WHITESPACE, raw, raw, start, index))
        elif char == ";":
            index += 1
            while index < length and source[index] not in "\r\n":
                index += 1
            raw = source[start:index]
            tokens.append(Token(TokenKind.COMMENT, raw, raw, start, index))
        elif char == "(":
            index += 1
            tokens.append(Token(TokenKind.LPAREN, char, char, start, index))
        elif char == ")":
            index += 1
            tokens.append(Token(TokenKind.RPAREN, char, char, start, index))
        elif char == '"':
            index += 1
            escaped = False
            while index < length:
                current = source[index]
                index += 1
                if escaped:
                    escaped = False
                elif current == "\\":
                    escaped = True
                elif current == '"':
                    break
            else:
                raise ParseError(f"unterminated string at offset {start}")
            raw = source[start:index]
            tokens.append(Token(TokenKind.STRING, raw, _decode_string(raw), start, index))
        elif char == "|":
            index += 1
            while index < length and source[index] != "|":
                index += 1
            if index >= length:
                raise ParseError(f"unterminated data blob at offset {start}")
            index += 1
            raw = source[start:index]
            tokens.append(Token(TokenKind.BLOB, raw, raw[1:-1], start, index))
        else:
            index += 1
            while index < length and not source[index].isspace() and source[index] not in "();":
                index += 1
            raw = source[start:index]
            tokens.append(Token(TokenKind.ATOM, raw, raw, start, index))
    return tokens


def parse(source: str) -> Document:
    """Parse one or more S-expressions from *source*."""

    tokens = tokenize(source)
    document = Document(source, tokens, [], {})
    stack: list[Node] = []
    for token_index, token in enumerate(tokens):
        if token.kind in {TokenKind.WHITESPACE, TokenKind.COMMENT}:
            continue
        if token.kind is TokenKind.LPAREN:
            node = Node(document)
            document.list_open_tokens[id(node)] = token_index
            if stack:
                node.parent = stack[-1]
                stack[-1].children.append(node)
            else:
                document.roots.append(node)
            stack.append(node)
        elif token.kind is TokenKind.RPAREN:
            if not stack:
                raise ParseError(f"unexpected ')' at offset {token.start}")
            stack.pop().close_token_index = token_index
        else:
            if not stack:
                raise ParseError(f"atom outside a list at offset {token.start}")
            node = Node(document, token_index=token_index, parent=stack[-1])
            stack[-1].children.append(node)
    if stack:
        raise ParseError("unterminated list")
    return document


def atom(node: Node, index: int, default: str = "") -> str:
    """Get an atom by its position among direct atom children."""

    atoms = node.atoms
    return atoms[index].value if len(atoms) > index else default
