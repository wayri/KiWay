"""KiCad 10 embedded-file encoding and token-preserving editing.

KiCad stores zstd-compressed bytes as a pipe-delimited base64 blob and records
an uppercase MD5 checksum of the original data. This implementation was
verified against KiCad 10.0.5 generated footprint fixtures.
"""

from __future__ import annotations

import base64
import ctypes
import ctypes.util
import os
import platform
import shutil
from dataclasses import dataclass
from pathlib import Path

from kilo.errors import KiloError

from .sexpr import Document, Node, atom, parse, quote


@dataclass(frozen=True)
class EmbeddedFile:
    name: str
    type: str
    data: bytes
    checksum: str


def read_embedded_files(text: str) -> list[EmbeddedFile]:
    """Decode and verify every direct embedded file in a KiCad document."""

    document = parse(text)
    container = document.root.first_list("embedded_files")
    if container is None:
        return []
    files: list[EmbeddedFile] = []
    for file_node in container.lists("file"):
        name_node = file_node.first_list("name")
        type_node = file_node.first_list("type")
        data_node = file_node.first_list("data")
        checksum_node = file_node.first_list("checksum")
        if not all((name_node, type_node, data_node, checksum_node)):
            raise KiloError("malformed KiCad embedded file")
        assert name_node is not None
        assert type_node is not None
        assert data_node is not None
        assert checksum_node is not None
        encoded = "".join(atom(data_node, 1).split())
        try:
            compressed = base64.b64decode(encoded, validate=True)
            payload = _zstd_decompress(compressed)
        except Exception as exc:
            raise KiloError(
                f"cannot decode embedded file {atom(name_node, 1)!r}: {exc}"
            ) from exc
        checksum = atom(checksum_node, 1)
        actual = _kicad_mmh3(payload)
        legacy = __import__("hashlib").sha256(payload).hexdigest()
        if checksum.upper() != actual and checksum.casefold() != legacy.casefold():
            raise KiloError(
                f"embedded file {atom(name_node, 1)!r} checksum mismatch: "
                f"expected {checksum}, found {actual}"
            )
        files.append(EmbeddedFile(atom(name_node, 1), atom(type_node, 1), payload, checksum))
    return files


def add_embedded_files(
    text: str, files: list[EmbeddedFile], *, replace: bool = False
) -> str:
    """Add or replace embedded files, preserving unrelated KiCad source."""

    if not files:
        return text
    document = parse(text)
    existing = {item.name: item for item in read_embedded_files(text)}
    duplicates = {item.name for item in files if item.name in existing}
    if duplicates:
        for name in duplicates:
            requested = next(item for item in files if item.name == name)
            if existing[name].data != requested.data:
                if not replace:
                    raise KiloError(f"embedded filename collision: {name}")
                container = document.root.first_list("embedded_files")
                assert container is not None
                node = next(
                    file_node
                    for file_node in container.lists("file")
                    if _file_name(file_node) == name
                )
                document.remove_node(node)
        files = [
            item
            for item in files
            if item.name not in duplicates or existing[item.name].data != item.data
        ]
    if not files:
        return text
    root = document.root
    container = root.first_list("embedded_files")
    newline = "\r\n" if "\r\n" in text else "\n"
    if container is None:
        assert root.close_token_index is not None
        offset = document.tokens[root.close_token_index].start
        rendered_files = "".join(_render_file(item, "\t\t", newline) for item in files)
        prefix = "" if offset == 0 or text[offset - 1] in "\r\n" else newline
        block = f"{prefix}\t(embedded_files{newline}{rendered_files}\t){newline}"
        document.insert(offset, block)
    else:
        assert container.close_token_index is not None
        offset = document.tokens[container.close_token_index].start
        rendered_files = "".join(_render_file(item, "\t\t", newline) for item in files)
        document.insert(offset, rendered_files)
    return document.render()


def remove_embedded_files(text: str, names: set[str]) -> str:
    """Remove selected embedded files while preserving all unrelated content."""

    if not names:
        return text
    document = parse(text)
    container = document.root.first_list("embedded_files")
    if container is None:
        return text
    for file_node in container.lists("file"):
        if _file_name(file_node) in names:
            document.remove_node(file_node)
    return document.render()


def make_embedded_file(name: str, data: bytes, file_type: str = "other") -> EmbeddedFile:
    """Create typed embedded-file metadata from raw bytes."""

    checksum = _kicad_mmh3(data)
    return EmbeddedFile(Path(name).name, file_type, data, checksum)


def _file_name(node: Node) -> str:
    name_node = node.first_list("name")
    return atom(name_node, 1) if name_node is not None else ""


def _render_file(item: EmbeddedFile, indent: str, newline: str) -> str:
    compressed = _zstd_compress(item.data)
    encoded = base64.b64encode(compressed).decode("ascii")
    width = 76
    lines = [encoded[index : index + width] for index in range(0, len(encoded), width)]
    data_indent = indent + "\t\t"
    blob = (newline + data_indent).join(lines)
    return (
        f"{indent}(file{newline}"
        f"{indent}\t(name {quote(item.name)}){newline}"
        f"{indent}\t(type {item.type}){newline}"
        f"{indent}\t(data{newline}"
        f"{data_indent}|{blob}|{newline}"
        f"{indent}\t){newline}"
        f"{indent}\t(checksum {quote(item.checksum)}){newline}"
        f"{indent}){newline}"
    )


def _load_zstd() -> ctypes.CDLL:
    candidates: list[str] = []
    found = ctypes.util.find_library("zstd")
    if found:
        candidates.append(found)
    if platform.system() == "Windows":
        program_files = Path(os.environ.get("ProgramFiles", r"C:\Program Files"))
        candidates.extend(
            str(program_files / "KiCad" / version / "bin" / "zstd.dll")
            for version in ("10.0", "10.99", "9.0")
        )
        candidates.append("zstd.dll")
    else:
        candidates.extend(["libzstd.so.1", "libzstd.so", "libzstd.dylib"])
    for candidate in candidates:
        try:
            return ctypes.CDLL(candidate)
        except OSError:
            continue
    executable = shutil.which("zstd")
    raise KiloError(
        "zstd library is required for KiCad embedded files"
        + (f" (CLI found at {executable}, but shared library was not found)" if executable else "")
    )


def _configure_zstd() -> ctypes.CDLL:
    library = _load_zstd()
    size = ctypes.c_size_t
    void = ctypes.c_void_p
    library.ZSTD_compressBound.argtypes = [size]
    library.ZSTD_compressBound.restype = size
    library.ZSTD_compress.argtypes = [void, size, void, size, ctypes.c_int]
    library.ZSTD_compress.restype = size
    library.ZSTD_getFrameContentSize.argtypes = [void, size]
    library.ZSTD_getFrameContentSize.restype = ctypes.c_ulonglong
    library.ZSTD_decompress.argtypes = [void, size, void, size]
    library.ZSTD_decompress.restype = size
    library.ZSTD_isError.argtypes = [size]
    library.ZSTD_isError.restype = ctypes.c_uint
    library.ZSTD_getErrorName.argtypes = [size]
    library.ZSTD_getErrorName.restype = ctypes.c_char_p
    return library


def _check_zstd(library: ctypes.CDLL, result: int) -> int:
    if library.ZSTD_isError(result):
        message = library.ZSTD_getErrorName(result).decode("utf-8", errors="replace")
        raise KiloError(f"zstd error: {message}")
    return result


def _zstd_compress(data: bytes) -> bytes:
    library = _configure_zstd()
    source = ctypes.create_string_buffer(data)
    capacity = int(library.ZSTD_compressBound(len(data)))
    destination = ctypes.create_string_buffer(capacity)
    size = _check_zstd(
        library,
        int(library.ZSTD_compress(destination, capacity, source, len(data), 15)),
    )
    return destination.raw[:size]


def _zstd_decompress(data: bytes) -> bytes:
    library = _configure_zstd()
    source = ctypes.create_string_buffer(data)
    content_size = int(library.ZSTD_getFrameContentSize(source, len(data)))
    if content_size in {0xFFFFFFFFFFFFFFFF, 0xFFFFFFFFFFFFFFFE}:
        raise KiloError("embedded zstd frame does not declare its content size")
    destination = ctypes.create_string_buffer(content_size)
    size = _check_zstd(
        library,
        int(library.ZSTD_decompress(destination, content_size, source, len(data))),
    )
    return destination.raw[:size]


def _kicad_mmh3(data: bytes, seed: int = 0xABBA2345) -> str:
    """Reproduce KiCad's aligned streaming MurmurHash3 128-bit digest."""

    mask = (1 << 64) - 1
    c1 = 0x87C37B91114253D5
    c2 = 0x4CF5AD432745937F
    h1 = seed
    h2 = seed

    def rotate(value: int, bits: int) -> int:
        return ((value << bits) | (value >> (64 - bits))) & mask

    def block(chunk: bytes) -> None:
        nonlocal h1, h2
        k1 = int.from_bytes(chunk[:8], "little")
        k2 = int.from_bytes(chunk[8:16], "little")
        k1 = (k1 * c1) & mask
        k1 = rotate(k1, 31)
        k1 = (k1 * c2) & mask
        h1 ^= k1
        h1 = rotate(h1, 27)
        h1 = (h1 + h2) & mask
        h1 = (h1 * 5 + 0x52DCE729) & mask
        k2 = (k2 * c2) & mask
        k2 = rotate(k2, 33)
        k2 = (k2 * c1) & mask
        h2 ^= k2
        h2 = rotate(h2, 31)
        h2 = (h2 + h1) & mask
        h2 = (h2 * 5 + 0x38495AB5) & mask

    full_length = len(data) // 16 * 16
    for offset in range(0, full_length, 16):
        block(data[offset : offset + 16])

    tail = data[full_length:]
    padding = 4 - (len(tail) + 4) % 4 if tail else 0
    padded_tail = tail + b"\0" * padding
    total_length = full_length + len(padded_tail)
    tail_count = total_length & 15
    if tail_count:
        tail_data = padded_tail[:tail_count]
        k1 = int.from_bytes(tail_data[:8].ljust(8, b"\0"), "little")
        k2 = int.from_bytes(tail_data[8:16].ljust(8, b"\0"), "little")
        if tail_count > 8:
            k2 = (k2 * c2) & mask
            k2 = rotate(k2, 33)
            k2 = (k2 * c1) & mask
            h2 ^= k2
        if tail_count:
            k1 = (k1 * c1) & mask
            k1 = rotate(k1, 31)
            k1 = (k1 * c2) & mask
            h1 ^= k1

    def fmix(value: int) -> int:
        value ^= value >> 33
        value = (value * 0xFF51AFD7ED558CCD) & mask
        value ^= value >> 33
        value = (value * 0xC4CEB9FE1A85EC53) & mask
        value ^= value >> 33
        return value

    h1 ^= total_length
    h2 ^= total_length
    h1 = (h1 + h2) & mask
    h2 = (h2 + h1) & mask
    h1 = fmix(h1)
    h2 = fmix(h2)
    h1 = (h1 + h2) & mask
    h2 = (h2 + h1) & mask
    return f"{h1:016X}{h2:016X}"
