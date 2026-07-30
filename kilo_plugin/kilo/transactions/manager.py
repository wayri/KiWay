"""Transactional project writes with complete backup and rollback."""

from __future__ import annotations

import json
import shutil
import uuid
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from kilo.errors import TransactionError
from kilo.identity import STATE_SCHEMA, control_path
from kilo.util.hashing import sha256_bytes, sha256_file

from .atomic_write import atomic_write_bytes
from .manifest import TRANSACTION_SCHEMA, write_manifest


def new_transaction_id() -> str:
    """Return a sortable UTC transaction identifier."""

    stamp = datetime.now(timezone.utc).strftime("%Y-%m-%dT%H%M%SZ")
    return f"{stamp}-{uuid.uuid4().hex[:6]}"


def execute_transaction(
    *,
    project_root: Path,
    operation: str,
    outputs: dict[Path, bytes],
    metadata: dict[str, Any],
    expected_hashes: dict[Path, str | None] | None = None,
) -> dict[str, Any]:
    """Back up, atomically write, and roll back an operation as one transaction."""

    transaction_id = new_transaction_id()
    control = control_path(project_root)
    transaction_root = control / "backups" / transaction_id
    backup_files = transaction_root / "files"

    relative_outputs: dict[Path, Path] = {}
    files_manifest: list[dict[str, Any]] = []
    for destination, data in outputs.items():
        resolved = destination.resolve()
        try:
            relative = resolved.relative_to(project_root.resolve())
        except ValueError as exc:
            raise TransactionError(f"transaction target escapes project: {destination}") from exc
        relative_outputs[destination] = relative
        before = sha256_file(destination) if destination.exists() else None
        expected = (expected_hashes or {}).get(destination, before)
        if before != expected:
            raise TransactionError(
                f"{relative} changed after the operation plan was built "
                f"(expected {expected}, found {before})"
            )
        files_manifest.append(
            {
                "path": relative.as_posix(),
                "before_sha256": before,
                "after_sha256": sha256_bytes(data),
                "backup_path": (
                    f"files/{relative.as_posix()}" if destination.exists() else None
                ),
                "created": not destination.exists(),
            }
        )

    transaction_root.mkdir(parents=True, exist_ok=False)
    manifest: dict[str, Any] = {
        "schema": TRANSACTION_SCHEMA,
        "transaction_id": transaction_id,
        "operation": operation,
        "status": "prepared",
        **metadata,
        "files": files_manifest,
        "warnings": list(metadata.get("warnings", [])),
        "errors": [],
    }
    try:
        for destination, relative in relative_outputs.items():
            if destination.exists():
                backup = backup_files / relative
                backup.parent.mkdir(parents=True, exist_ok=True)
                shutil.copy2(destination, backup)
        write_manifest(transaction_root / "transaction.json", manifest)

        written: list[Path] = []
        for destination in sorted(outputs, key=lambda item: relative_outputs[item].as_posix()):
            atomic_write_bytes(destination, outputs[destination])
            written.append(destination)
        manifest["status"] = "completed"
        write_manifest(transaction_root / "transaction.json", manifest)
        _record_history(control, manifest)
        _write_state(control, metadata.get("state", {}), transaction_id)
        try:
            _write_reports(control, manifest)
        except OSError as report_exc:
            manifest["warnings"].append(f"could not write auxiliary report/log: {report_exc}")
            write_manifest(transaction_root / "transaction.json", manifest)
        return manifest
    except BaseException as exc:
        rollback_errors: list[str] = []
        for destination, relative in reversed(list(relative_outputs.items())):
            try:
                backup = backup_files / relative
                if backup.exists():
                    atomic_write_bytes(destination, backup.read_bytes())
                elif destination.exists():
                    # It was created by this transaction and is identified exactly.
                    destination.unlink()
            except BaseException as rollback_exc:
                rollback_errors.append(f"{relative}: {rollback_exc}")
        manifest["status"] = "rollback-failed" if rollback_errors else "rolled-back"
        manifest["errors"] = [str(exc), *rollback_errors]
        write_manifest(transaction_root / "transaction.json", manifest)
        detail = f"transaction failed and was {manifest['status']}: {exc}"
        if rollback_errors:
            detail += "; rollback errors: " + "; ".join(rollback_errors)
        raise TransactionError(detail) from exc


def _record_history(control: Path, manifest: dict[str, Any]) -> None:
    path = control / "history.json"
    if path.exists():
        try:
            history = json.loads(path.read_text(encoding="utf-8"))
        except (OSError, json.JSONDecodeError):
            history = []
    else:
        history = []
    if not isinstance(history, list):
        history = []
    history.append(
        {
            "transaction_id": manifest["transaction_id"],
            "operation": manifest["operation"],
            "status": manifest["status"],
        }
    )
    atomic_write_bytes(
        path, (json.dumps(history, indent=2, sort_keys=True) + "\n").encode("utf-8")
    )


def _write_state(control: Path, state: dict[str, Any], transaction_id: str) -> None:
    path = control / "state.json"
    current: dict[str, Any] = {}
    if path.exists():
        try:
            loaded = json.loads(path.read_text(encoding="utf-8"))
            if isinstance(loaded, dict):
                current = loaded
        except (OSError, json.JSONDecodeError):
            pass
    current.update(state)
    current["last_transaction"] = transaction_id
    current["schema"] = STATE_SCHEMA
    atomic_write_bytes(
        path, (json.dumps(current, indent=2, sort_keys=True) + "\n").encode("utf-8")
    )


def _write_reports(control: Path, manifest: dict[str, Any]) -> None:
    transaction_id = manifest["transaction_id"]
    report = control / "reports" / f"{transaction_id}.json"
    log = control / "logs" / f"{transaction_id}.log"
    atomic_write_bytes(
        report, (json.dumps(manifest, indent=2, sort_keys=True) + "\n").encode("utf-8")
    )
    lines = [
        f"transaction_id={transaction_id}",
        f"operation={manifest['operation']}",
        f"status={manifest['status']}",
        f"files={len(manifest.get('files', []))}",
        f"warnings={len(manifest.get('warnings', []))}",
        f"errors={len(manifest.get('errors', []))}",
    ]
    atomic_write_bytes(log, ("\n".join(lines) + "\n").encode("utf-8"))
