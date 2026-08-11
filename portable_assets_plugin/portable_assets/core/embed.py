"""KiCad native embedded-file codec (KiCad 9/10 format)."""
from __future__ import annotations

import base64
from dataclasses import dataclass
from pathlib import Path
from typing import Iterable

from . import sexpr

SEED = 0xABBA2345
MASK64 = 0xFFFFFFFFFFFFFFFF
MODEL_EXTS = {".stp", ".stpz", ".step", ".wrl", ".wrz"}
FONT_EXTS = {".woff", ".woff2", ".ttf", ".otf"}


def _rotl64(x: int, r: int) -> int:
    return ((x << r) | (x >> (64 - r))) & MASK64


def _fmix64(k: int) -> int:
    k ^= k >> 33
    k = (k * 0xFF51AFD7ED558CCD) & MASK64
    k ^= k >> 33
    k = (k * 0xC4CEB9FE1A85EC53) & MASK64
    k ^= k >> 33
    return k & MASK64


def murmur3_x64_128(data: bytes, seed: int = SEED) -> tuple[int, int]:
    """One-shot MurmurHash3 x64 128, matching KiCad's current MMH3_HASH for byte blobs."""
    h1 = seed & MASK64
    h2 = seed & MASK64
    c1 = 0x87C37B91114253D5
    c2 = 0x4CF5AD432745937F
    nblocks = len(data) // 16

    for i in range(nblocks):
        off = i * 16
        k1 = int.from_bytes(data[off:off + 8], "little")
        k2 = int.from_bytes(data[off + 8:off + 16], "little")
        k1 = (k1 * c1) & MASK64
        k1 = _rotl64(k1, 31)
        k1 = (k1 * c2) & MASK64
        h1 ^= k1
        h1 = _rotl64(h1, 27)
        h1 = (h1 + h2) & MASK64
        h1 = (h1 * 5 + 0x52DCE729) & MASK64
        k2 = (k2 * c2) & MASK64
        k2 = _rotl64(k2, 33)
        k2 = (k2 * c1) & MASK64
        h2 ^= k2
        h2 = _rotl64(h2, 31)
        h2 = (h2 + h1) & MASK64
        h2 = (h2 * 5 + 0x38495AB5) & MASK64

    tail = data[nblocks * 16:]
    k1 = 0
    k2 = 0
    if len(tail) > 8:
        for i, b in enumerate(tail[8:]):
            k2 |= b << (8 * i)
        k2 = (k2 * c2) & MASK64
        k2 = _rotl64(k2, 33)
        k2 = (k2 * c1) & MASK64
        h2 ^= k2
    if tail:
        for i, b in enumerate(tail[:8]):
            k1 |= b << (8 * i)
        k1 = (k1 * c1) & MASK64
        k1 = _rotl64(k1, 31)
        k1 = (k1 * c2) & MASK64
        h1 ^= k1

    length = len(data)
    h1 ^= length
    h2 ^= length
    h1 = (h1 + h2) & MASK64
    h2 = (h2 + h1) & MASK64
    h1 = _fmix64(h1)
    h2 = _fmix64(h2)
    h1 = (h1 + h2) & MASK64
    h2 = (h2 + h1) & MASK64
    return h1, h2


def checksum(data: bytes) -> str:
    h1, h2 = murmur3_x64_128(data)
    return f"{h1:016X}{h2:016X}"


def _compress_zstd(data: bytes, level: int = 15) -> bytes:
    try:
        import zstandard as zstd
        return zstd.ZstdCompressor(level=level).compress(data)
    except ImportError:
        pass
    # Fallback to the native libzstd already present on many KiCad/system installs.
    import ctypes
    import ctypes.util
    import sys
    candidates = [ctypes.util.find_library("zstd")]
    exe_dir = Path(sys.executable).resolve().parent
    candidates += [str(exe_dir / n) for n in ("zstd.dll", "libzstd.dll", "libzstd.so", "libzstd.dylib")]
    lib = None
    for c in candidates:
        if not c:
            continue
        try:
            lib = ctypes.CDLL(c)
            break
        except OSError:
            continue
    if lib is None:
        raise RuntimeError("Native KiCad embedding needs Zstandard. Install the 'zstandard' Python package or make libzstd available.")
    lib.ZSTD_compressBound.argtypes = [ctypes.c_size_t]
    lib.ZSTD_compressBound.restype = ctypes.c_size_t
    lib.ZSTD_compress.argtypes = [ctypes.c_void_p, ctypes.c_size_t, ctypes.c_void_p, ctypes.c_size_t, ctypes.c_int]
    lib.ZSTD_compress.restype = ctypes.c_size_t
    lib.ZSTD_isError.argtypes = [ctypes.c_size_t]
    lib.ZSTD_isError.restype = ctypes.c_uint
    cap = lib.ZSTD_compressBound(len(data))
    dst = ctypes.create_string_buffer(cap)
    src = ctypes.create_string_buffer(data, len(data))
    size = lib.ZSTD_compress(dst, cap, src, len(data), level)
    if lib.ZSTD_isError(size):
        raise RuntimeError("libzstd failed to compress an embedded file")
    return dst.raw[:size]


def _decompress_zstd(data: bytes) -> bytes:
    try:
        import zstandard as zstd
        return zstd.ZstdDecompressor().decompress(data, max_output_size=1_000_000_000)
    except ImportError:
        pass
    import ctypes
    import ctypes.util
    import sys
    candidates = [ctypes.util.find_library("zstd")]
    exe_dir = Path(sys.executable).resolve().parent
    candidates += [str(exe_dir / n) for n in ("zstd.dll", "libzstd.dll", "libzstd.so", "libzstd.dylib")]
    lib = None
    for c in candidates:
        if not c:
            continue
        try:
            lib = ctypes.CDLL(c)
            break
        except OSError:
            continue
    if lib is None:
        raise RuntimeError("Cannot decode KiCad Embedded Files: Zstandard is unavailable")
    lib.ZSTD_getFrameContentSize.argtypes = [ctypes.c_void_p, ctypes.c_size_t]
    lib.ZSTD_getFrameContentSize.restype = ctypes.c_ulonglong
    lib.ZSTD_decompress.argtypes = [ctypes.c_void_p, ctypes.c_size_t, ctypes.c_void_p, ctypes.c_size_t]
    lib.ZSTD_decompress.restype = ctypes.c_size_t
    lib.ZSTD_isError.argtypes = [ctypes.c_size_t]
    lib.ZSTD_isError.restype = ctypes.c_uint
    src = ctypes.create_string_buffer(data, len(data))
    out_size = int(lib.ZSTD_getFrameContentSize(src, len(data)))
    if out_size < 0 or out_size > 1_000_000_000 or out_size >= (1 << 63):
        raise RuntimeError("Invalid or unknown Zstandard frame size in embedded file")
    dst = ctypes.create_string_buffer(out_size)
    actual = lib.ZSTD_decompress(dst, out_size, src, len(data))
    if lib.ZSTD_isError(actual):
        raise RuntimeError("libzstd failed to decompress an embedded file")
    return dst.raw[:actual]


def classify(name: str) -> str:
    ext = Path(name).suffix.lower()
    if ext in MODEL_EXTS:
        return "model"
    if ext in FONT_EXTS:
        return "font"
    if ext == ".pdf":
        return "datasheet"
    if ext == ".kicad_wks":
        return "worksheet"
    return "other"


@dataclass(slots=True)
class EmbeddedBlob:
    name: str
    data: bytes
    file_type: str | None = None

    @property
    def type(self) -> str:
        return self.file_type or classify(self.name)

    def form(self, indent: str = "\t") -> str:
        compressed = _compress_zstd(self.data, 15)
        encoded = base64.b64encode(compressed).decode("ascii")
        lines = [encoded[i:i + 76] for i in range(0, len(encoded), 76)] or [""]
        if len(lines) == 1:
            payload = f"|{lines[0]}|"
        else:
            payload = "|" + lines[0] + "\n" + "\n".join(lines[1:-1]) + "\n" + lines[-1] + "|"
        return (
            f'{indent}(file (name {sexpr.quote(self.name)})(type {self.type})(data\n'
            f'{indent}\t{payload}\n{indent})(checksum {sexpr.quote(checksum(self.data))}))'
        )


def existing_names(text: str, owner: sexpr.Node) -> set[str]:
    emb = next((c for c in owner.children if c.head == "embedded_files"), None)
    if not emb:
        return set()
    names: set[str] = set()
    for f in emb.children_named("file"):
        n = f.child("name")
        if n and len(n.atoms) >= 2:
            names.add(n.atoms[1].value)
    return names


def inject_blobs(text: str, owner: sexpr.Node, blobs: Iterable[EmbeddedBlob]) -> str:
    blobs = list(blobs)
    if not blobs:
        return text
    existing = existing_names(text, owner)
    blobs = [b for b in blobs if b.name not in existing]
    if not blobs:
        return text
    emb = next((c for c in owner.children if c.head == "embedded_files"), None)
    if emb:
        insertion = "\n" + "\n".join(b.form("\t\t") for b in blobs) + "\n\t"
        return text[:emb.end - 1] + insertion + text[emb.end - 1:]
    insertion = "\n\t(embedded_files\n" + "\n".join(b.form("\t\t") for b in blobs) + "\n\t)\n"
    return text[:owner.end - 1] + insertion + text[owner.end - 1:]


def decode_file_node(text: str, file_node: sexpr.Node) -> EmbeddedBlob:
    name_node = file_node.child("name")
    type_node = file_node.child("type")
    data_node = file_node.child("data")
    if not name_node or len(name_node.atoms) < 2 or not data_node or len(data_node.atoms) < 2:
        raise ValueError("Malformed embedded file entry")
    name = name_node.atoms[1].value
    file_type = type_node.atoms[1].value if type_node and len(type_node.atoms) >= 2 else "other"
    encoded = "".join(a.value for a in data_node.atoms[1:])
    compressed = base64.b64decode(encoded)
    data = _decompress_zstd(compressed)
    return EmbeddedBlob(name, data, file_type)
