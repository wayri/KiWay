"""Versioned transaction-manifest helpers."""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any

from kilo.identity import TRANSACTION_SCHEMA, TRANSACTION_SCHEMAS


def write_manifest(path: Path, data: dict[str, Any]) -> None:
    """Write stable, readable JSON transaction metadata."""

    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(data, indent=2, sort_keys=True) + "\n", encoding="utf-8")


def read_manifest(path: Path) -> dict[str, Any]:
    """Read and minimally validate a transaction manifest."""

    data = json.loads(path.read_text(encoding="utf-8"))
    if not isinstance(data, dict) or data.get("schema") not in TRANSACTION_SCHEMAS:
        raise ValueError(f"unsupported transaction manifest: {path}")
    return data
