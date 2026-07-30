"""Portable design-block packaging using KiCad 10 embedded files."""

from __future__ import annotations

import json
import os
import shutil
import tempfile
from dataclasses import dataclass
from pathlib import Path
from typing import Any

from kilo.dependencies.scanner import scan_project
from kilo.errors import ConflictError, KiloError
from kilo.identity import (
    CONTROL_DIRECTORIES,
    MANIFEST_EMBEDDED_NAME,
    MANIFEST_EMBEDDED_NAMES,
    PACKAGE_SCHEMA,
    PACKAGE_SCHEMAS,
    PRODUCT_TITLE,
)
from kilo.kicad.design_block import DesignBlock, discover_design_block
from kilo.kicad.embedded_files import (
    add_embedded_files,
    make_embedded_file,
    read_embedded_files,
    remove_embedded_files,
)
from kilo.kicad.project import Project
from kilo.transactions.manager import execute_transaction
from kilo.util.hashing import sha256_bytes, sha256_file
from kilo.util.naming import collision_name, sanitize_name


@dataclass(frozen=True)
class PackageSettings:
    output: Path | None = None
    package_id: str | None = None
    package_name: str | None = None
    version: str = "1.0.0"
    strict: bool = False


@dataclass
class PackagePlan:
    block: DesignBlock
    settings: PackageSettings
    destination: Path
    schematic_relative: Path
    packaged_schematic: bytes
    manifest: dict[str, Any]
    source_hashes: dict[Path, str]
    actions: list[str]
    warnings: list[str]

    def summary(self) -> dict[str, Any]:
        return {
            "block": self.block.name,
            "source": str(self.block.root),
            "destination": str(self.destination),
            "package_id": self.manifest["package_id"],
            "footprints": len(self.manifest["footprints"]),
            "models": len(self.manifest["models"]),
            "actions": self.actions,
            "warnings": self.warnings,
        }


def build_package_plan(
    block_path: Path, settings: PackageSettings | None = None
) -> PackagePlan:
    """Resolve, deduplicate, manifest, embed, and validate a design block in memory."""

    settings = settings or PackageSettings()
    block = discover_design_block(block_path)
    project = Project(
        root=block.root,
        name=block.name,
        project_file=None,
        root_schematic=block.schematic,
        board=block.board,
        fp_lib_table=block.root / "fp-lib-table",
    )
    scan = scan_project(project)
    if scan.missing and settings.strict:
        raise KiloError(
            "strict packaging aborted; unresolved footprints: "
            + ", ".join(item.symbol.footprint for item in scan.missing)
        )
    if settings.strict:
        missing_models = [
            model.original_path
            for dependency in scan.resolved
            for model in dependency.models
            if model.status == "missing"
        ]
        if missing_models:
            raise KiloError(
                "strict packaging aborted; unresolved models: " + ", ".join(missing_models)
            )
    package_id = settings.package_id or f"local.{sanitize_name(block.name).lower()}"
    package_name = settings.package_name or block.name
    destination = settings.output.resolve() if settings.output else block.root
    if destination != block.root and destination.is_relative_to(block.root):
        raise KiloError("package output cannot be placed inside the source block")
    if destination != block.root and destination.exists():
        raise ConflictError(f"package output already exists: {destination}")

    embedded = []
    footprints: list[dict[str, Any]] = []
    models: list[dict[str, Any]] = []
    licenses: list[dict[str, Any]] = []
    symbol_mappings: list[dict[str, Any]] = []
    footprint_by_hash: dict[str, dict[str, Any]] = {}
    model_by_hash: dict[str, dict[str, Any]] = {}
    license_by_hash: dict[str, dict[str, Any]] = {}
    used_names: dict[str, str] = {}
    warnings = list(scan.warnings)
    source_hashes = {
        path: sha256_file(path)
        for path in block.root.rglob("*")
        if path.is_file() and not any(part in CONTROL_DIRECTORIES for part in path.parts)
    }

    for dependency in scan.resolved:
        assert dependency.source_text is not None and dependency.source_sha256 is not None
        footprint_entry = footprint_by_hash.get(dependency.source_sha256)
        if footprint_entry is None:
            local_name = sanitize_name(dependency.name)
            prior = used_names.get(local_name.casefold())
            if prior and prior != dependency.source_sha256:
                local_name = collision_name(local_name, dependency.source_sha256)
            used_names[local_name.casefold()] = dependency.source_sha256
            embedded_name = f"kilo__footprint__{local_name}.kicad_mod"
            payload = dependency.source_text.encode("utf-8")
            embedded.append(make_embedded_file(embedded_name, payload, "other"))
            footprint_entry = {
                "key": f"fp-{dependency.source_sha256[:8]}",
                "name": local_name,
                "original_library_id": dependency.symbol.footprint,
                "embedded_file": embedded_name,
                "sha256": sha256_bytes(payload),
                "source": dependency.source_kind,
                "source_path": str(dependency.source_path) if dependency.source_path else None,
                "license": {"status": "unknown"},
                "license_files": [],
                "models": [],
            }
            footprints.append(footprint_entry)
            footprint_by_hash[dependency.source_sha256] = footprint_entry
        if dependency.source_path and dependency.source_path.is_file():
            footprint_entry["license_files"].extend(
                _collect_license_files(
                    dependency.source_path,
                    embedded,
                    licenses,
                    license_by_hash,
                )
            )
        for model in dependency.models:
            if model.resolved_path is None or model.source_sha256 is None:
                continue
            model_entry = model_by_hash.get(model.source_sha256)
            if model_entry is None:
                embedded_name = (
                    f"kilo__model__{model.source_sha256[:8]}__"
                    f"{sanitize_name(model.resolved_path.name)}"
                )
                payload = model.resolved_path.read_bytes()
                embedded.append(make_embedded_file(embedded_name, payload, "model"))
                model_entry = {
                    "key": f"model-{model.source_sha256[:8]}",
                    "original_path": model.original_path,
                    "original_paths": [model.original_path],
                    "embedded_file": embedded_name,
                    "filename": model.resolved_path.name,
                    "sha256": sha256_bytes(payload),
                    "license": {"status": "unknown"},
                    "license_files": [],
                }
                models.append(model_entry)
                model_by_hash[model.source_sha256] = model_entry
                model_entry["license_files"].extend(
                    _collect_license_files(
                        model.resolved_path,
                        embedded,
                        licenses,
                        license_by_hash,
                    )
                )
            elif model.original_path not in model_entry["original_paths"]:
                model_entry["original_paths"].append(model.original_path)
            if model_entry["key"] not in footprint_entry["models"]:
                footprint_entry["models"].append(model_entry["key"])
        symbol_mappings.append(
            {
                "schematic": dependency.symbol.file.relative_to(block.root).as_posix(),
                "sheet_path": dependency.symbol.sheet_path,
                "symbol_uuid": dependency.symbol.uuid,
                "reference": dependency.symbol.reference,
                "original": dependency.symbol.footprint,
                "footprint_key": footprint_entry["key"],
            }
        )

    manifest = {
        "schema": PACKAGE_SCHEMA,
        "package_id": package_id,
        "name": package_name,
        "version": settings.version,
        "minimum_kicad_version": "10.0",
        "created_by": PRODUCT_TITLE,
        "footprints": footprints,
        "models": models,
        "licenses": licenses,
        "symbol_mappings": symbol_mappings,
        "warnings": warnings,
    }
    manifest_payload = (
        json.dumps(manifest, indent=2, sort_keys=True) + "\n"
    ).encode("utf-8")
    embedded.append(make_embedded_file(MANIFEST_EMBEDDED_NAME, manifest_payload, "other"))
    schematic_text = block.schematic.read_text(encoding="utf-8-sig")
    packaged_text = add_embedded_files(
        _remove_existing_package_payload(schematic_text),
        embedded,
        replace=True,
    )
    decoded = {item.name: item.data for item in read_embedded_files(packaged_text)}
    for entry in [*footprints, *models, *licenses]:
        if sha256_bytes(decoded[entry["embedded_file"]]) != entry["sha256"]:
            raise KiloError(f"packaging validation failed for {entry['embedded_file']}")
    actions = [
        f"Embed {len(footprints)} footprint payload(s)",
        f"Embed {len(models)} model payload(s)",
        f"Embed {MANIFEST_EMBEDDED_NAME}",
        (
            f"Save portable copy to {destination}"
            if destination != block.root
            else f"Back up and update {block.schematic.name}"
        ),
    ]
    if any(entry["license"]["status"] == "unknown" for entry in [*footprints, *models]):
        warnings.append(
            "Redistribution permission is unknown for one or more dependencies; "
            "review licensing before public export"
        )
    return PackagePlan(
        block,
        settings,
        destination,
        block.schematic.relative_to(block.root),
        packaged_text.encode("utf-8"),
        manifest,
        source_hashes,
        actions,
        warnings,
    )


def execute_package(plan: PackagePlan) -> dict[str, Any]:
    """Execute in-place packaging or an atomic save-as-copy workflow."""

    for path, expected in plan.source_hashes.items():
        current = sha256_file(path) if path.exists() else None
        if current != expected:
            raise KiloError(f"design-block source changed after scan: {path}")
    if plan.destination != plan.block.root:
        plan.destination.parent.mkdir(parents=True, exist_ok=True)
        temporary = Path(
            tempfile.mkdtemp(
                prefix=f".{plan.destination.name}.kilo-",
                dir=plan.destination.parent,
            )
        )
        try:
            shutil.copytree(
                plan.block.root,
                temporary,
                dirs_exist_ok=True,
                ignore=shutil.ignore_patterns(*CONTROL_DIRECTORIES, "__pycache__"),
            )
            copied_schematic = temporary / plan.schematic_relative
            copied_project = Project(
                temporary,
                plan.block.name,
                None,
                copied_schematic,
                (
                    temporary / plan.block.board.relative_to(plan.block.root)
                    if plan.block.board
                    else None
                ),
                temporary / "fp-lib-table",
            )
            result = execute_transaction(
                project_root=temporary,
                operation="package-block",
                outputs={copied_schematic: plan.packaged_schematic},
                metadata=_package_metadata(plan),
            )
            os.replace(temporary, plan.destination)
            return result
        except BaseException:
            if temporary.exists():
                shutil.rmtree(temporary)
            raise
    return execute_transaction(
        project_root=plan.block.root,
        operation="package-block",
        outputs={plan.block.schematic: plan.packaged_schematic},
        metadata=_package_metadata(plan),
    )


def read_package(block_path: Path) -> tuple[DesignBlock, dict[str, Any], dict[str, bytes]]:
    """Read and hash-verify a portable Kilo or legacy BlockPack design block."""

    block = discover_design_block(block_path)
    embedded = {
        item.name: item.data
        for item in read_embedded_files(block.schematic.read_text(encoding="utf-8-sig"))
    }
    payload = next(
        (embedded[name] for name in MANIFEST_EMBEDDED_NAMES if name in embedded),
        None,
    )
    if payload is None:
        raise KiloError(f"{block.root} has no Kilo or legacy BlockPack manifest")
    manifest = json.loads(payload.decode("utf-8"))
    if manifest.get("schema") not in PACKAGE_SCHEMAS:
        raise KiloError(f"unsupported Kilo package schema: {manifest.get('schema')}")
    for entry in [
        *manifest.get("footprints", []),
        *manifest.get("models", []),
        *manifest.get("licenses", []),
    ]:
        data = embedded.get(entry["embedded_file"])
        if data is None:
            raise KiloError(f"package payload missing: {entry['embedded_file']}")
        if sha256_bytes(data) != entry["sha256"]:
            raise KiloError(f"package payload hash mismatch: {entry['embedded_file']}")
    return block, manifest, embedded


def _package_metadata(plan: PackagePlan) -> dict[str, Any]:
    return {
        "package": {
            "package_id": plan.manifest["package_id"],
            "name": plan.manifest["name"],
            "version": plan.manifest["version"],
        },
        "warnings": plan.warnings,
    }


def _remove_existing_package_payload(schematic_text: str) -> str:
    reserved = {
        item.name
        for item in read_embedded_files(schematic_text)
        if item.name in MANIFEST_EMBEDDED_NAMES
        or item.name.startswith("kilo__")
        or item.name.startswith("blockpack__")
    }
    return remove_embedded_files(schematic_text, reserved)


def _collect_license_files(
    source: Path,
    embedded: list[Any],
    licenses: list[dict[str, Any]],
    by_hash: dict[str, dict[str, Any]],
) -> list[str]:
    keys: list[str] = []
    candidates: list[Path] = []
    for directory in (source.parent, source.parent.parent):
        for pattern in ("LICENSE*", "LICENCE*", "COPYING*", "NOTICE*"):
            candidates.extend(directory.glob(pattern))
    for candidate in sorted(set(candidates)):
        if not candidate.is_file() or candidate.stat().st_size > 2 * 1024 * 1024:
            continue
        payload = candidate.read_bytes()
        digest = sha256_bytes(payload)
        entry = by_hash.get(digest)
        if entry is None:
            embedded_name = (
                f"kilo__license__{digest[:8]}__{sanitize_name(candidate.name)}"
            )
            embedded.append(make_embedded_file(embedded_name, payload, "other"))
            entry = {
                "key": f"license-{digest[:8]}",
                "name": candidate.name,
                "source_path": str(candidate),
                "embedded_file": embedded_name,
                "sha256": digest,
            }
            licenses.append(entry)
            by_hash[digest] = entry
        if entry["key"] not in keys:
            keys.append(entry["key"])
    return keys
