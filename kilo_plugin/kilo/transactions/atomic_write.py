"""Validated atomic file replacement."""

from __future__ import annotations

import json
import os
import tempfile
from pathlib import Path
from typing import Callable

from kilo.kicad.sexpr import parse


def validate_content(path: Path, data: bytes) -> None:
    """Parse formats Kilo writes before replacing their destination."""

    if path.suffix in {".kicad_sch", ".kicad_pcb", ".kicad_mod"} or path.name == "fp-lib-table":
        text = data.decode("utf-8")
        parse(text)
    elif path.suffix == ".json":
        text = data.decode("utf-8")
        json.loads(text)


def atomic_write_bytes(
    path: Path,
    data: bytes,
    *,
    validator: Callable[[Path, bytes], None] = validate_content,
) -> None:
    """Write and fsync a same-directory temporary file, then atomically replace."""

    path.parent.mkdir(parents=True, exist_ok=True)
    validator(path, data)
    descriptor, temporary_name = tempfile.mkstemp(
        prefix=f".{path.name}.kilo-", suffix=".tmp", dir=path.parent
    )
    temporary = Path(temporary_name)
    try:
        with os.fdopen(descriptor, "wb") as stream:
            stream.write(data)
            stream.flush()
            os.fsync(stream.fileno())
        os.replace(temporary, path)
        _fsync_directory(path.parent)
    except BaseException:
        try:
            temporary.unlink(missing_ok=True)
        finally:
            raise


def _fsync_directory(directory: Path) -> None:
    if os.name == "nt":
        return
    descriptor = os.open(directory, os.O_RDONLY)
    try:
        os.fsync(descriptor)
    finally:
        os.close(descriptor)
